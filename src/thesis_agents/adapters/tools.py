"""Function tools and the code-side pre-tool-call deny gate.

This module defines the least-privilege function tools the four agents are
scoped to (architecture.md §5) and the **pre-tool-call deny guardrail**
(architecture.md §6.5): before any tool runs, a code-side check denies (a) any
nested agent/task-spawning call and (b) any tool call whose target touches
``.env`` or another secret. The gate is enforced *in code*, never by prompt.

Design for testability: the decision logic lives in a pure function,
:func:`evaluate_tool_call`, that takes a plain tool name and an arguments dict
and returns a :class:`ToolCallDecision`. The OpenAI Agents SDK guardrail
(:data:`deny_gate`) is a thin adapter that extracts the tool name/arguments from
the SDK's :class:`~agents.tool_guardrails.ToolInputGuardrailData` and delegates
to that pure function, so the security-critical logic is unit-testable in
isolation without constructing SDK run state.

Tool bodies are intentionally minimal but real: read-family tools are confined
to the configured ``data/`` directories, write-family tools to
``data/output/drafts/``, and web-family tools are thin seams. All path access is
funnelled through :func:`_resolve_within` so a tool can never escape its allowed
roots (defence in depth alongside the guardrail).
"""

from __future__ import annotations

import fnmatch
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import (
    FunctionTool,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrailData,
    function_tool,
    tool_input_guardrail,
)

from config import AppConfig

logger = logging.getLogger(__name__)

# --- Deny-gate policy constants -------------------------------------------

#: Substrings that mark a tool call as an attempt to spawn/delegate to another
#: agent or task. Routing is owned by the deterministic controller, never by a
#: model-issued tool call (architecture.md §6.5a).
_NESTED_SPAWN_MARKERS = (
    "agent",
    "task",
    "spawn",
    "delegate",
    "handoff",
    "subagent",
    "sub_agent",
)

#: Secret-bearing path fragments no tool may touch (architecture.md §6.5b).
_SECRET_MARKERS = (
    ".env",
    "secret",
    "credential",
    "api_key",
    "apikey",
    "id_rsa",
    ".pem",
)


@dataclass(frozen=True, slots=True)
class ToolCallDecision:
    """Outcome of the pre-tool-call deny check — a typed result, not a bool."""

    allowed: bool
    reason: str = ""


def _mentions_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _iter_arg_values(arguments: Any) -> list[str]:
    """Flatten an arguments payload to a list of string leaves for scanning."""
    values: list[str] = []
    if isinstance(arguments, dict):
        for value in arguments.values():
            values.extend(_iter_arg_values(value))
    elif isinstance(arguments, (list, tuple)):
        for value in arguments:
            values.extend(_iter_arg_values(value))
    elif arguments is not None:
        values.append(str(arguments))
    return values


def evaluate_tool_call(tool_name: str, arguments: Any) -> ToolCallDecision:
    """Decide whether a tool call may proceed. Pure, side-effect-free.

    Denies, regardless of any prompt:

    - **Nested agent/task spawning** — the tool name signals delegation to
      another agent/task (architecture.md §6.5a).
    - **Secret access** — the tool name or any argument value references
      ``.env`` or another secret-bearing path (architecture.md §6.5b).

    ``arguments`` may be a dict, a JSON string, or any nested structure; all
    string leaves are scanned.
    """
    name = tool_name or ""
    if _mentions_any(name, _NESTED_SPAWN_MARKERS):
        return ToolCallDecision(
            allowed=False,
            reason=(
                f"Denied: tool {name!r} looks like nested agent/task spawning; "
                "routing is owned by the controller, not by agents."
            ),
        )

    if isinstance(arguments, str):
        try:
            parsed: Any = json.loads(arguments)
        except ValueError:
            # JSONDecodeError subclasses ValueError; treat the raw string as-is.
            parsed = arguments
    else:
        parsed = arguments

    haystacks = [name, *_iter_arg_values(parsed)]
    for text in haystacks:
        if _mentions_any(text, _SECRET_MARKERS):
            return ToolCallDecision(
                allowed=False,
                reason=(
                    f"Denied: tool {name!r} targets a secret/.env path "
                    f"({text!r}); tools may never touch secrets."
                ),
            )

    return ToolCallDecision(allowed=True)


@tool_input_guardrail(name="deny_nested_spawn_and_secret_access")
def deny_gate(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
    """Pre-tool-call guardrail wrapping :func:`evaluate_tool_call`.

    Extracts the tool name and arguments from the SDK guardrail data and, on a
    deny decision, halts execution by raising (the tool never runs). This is the
    OpenAI Agents SDK ``tool_input_guardrail`` hook required by architecture.md
    §6.5; the decision itself is delegated so it can be tested in isolation.
    """
    context = data.context
    tool_name = getattr(context, "tool_name", "") or ""
    arguments = getattr(context, "tool_arguments", None)

    decision = evaluate_tool_call(tool_name, arguments)
    if decision.allowed:
        return ToolGuardrailFunctionOutput.allow()

    logger.warning(
        json.dumps(
            {
                "event": "tool_call_denied",
                "tool": tool_name,
                "reason": decision.reason,
            }
        )
    )
    return ToolGuardrailFunctionOutput.raise_exception(output_info=decision.reason)


# --- Path confinement ------------------------------------------------------


class ToolAccessError(RuntimeError):
    """Raised when a tool call escapes its allowed directory roots."""


def _resolve_within(target: str, roots: tuple[Path, ...]) -> Path:
    """Resolve ``target`` and confirm it stays within one of ``roots``.

    Defence in depth alongside :func:`evaluate_tool_call`: even a permitted tool
    may only touch paths under its configured roots.
    """
    candidate = Path(target).expanduser().resolve()
    for root in roots:
        root_resolved = root.resolve()
        if candidate == root_resolved or root_resolved in candidate.parents:
            return candidate
    allowed = ", ".join(str(r) for r in roots)
    raise ToolAccessError(f"Path {target!r} is outside the allowed roots: {allowed}.")


# --- Tool factories --------------------------------------------------------
#
# Tools are built from config so paths are never hard-coded (conventions.md §2)
# and the roots are injected (conventions.md §3). Each factory returns the SDK
# FunctionTool objects, with the deny gate attached to every one.


def _read_roots(config: AppConfig) -> tuple[Path, ...]:
    return (
        config.source_of_truth_dir,
        config.sources_dir,
        config.input_dir,
    )


def build_read_tools(config: AppConfig) -> list[FunctionTool]:
    """Read-family tools (`read_file`, `grep`, `glob`) confined to data inputs."""
    read_roots = _read_roots(config)

    @function_tool(tool_input_guardrails=[deny_gate])
    def read_file(path: str) -> str:
        """Read a UTF-8 text file from the project's data directories.

        Args:
            path: Path to the file, under a permitted data directory.
        """
        resolved = _resolve_within(path, read_roots)
        return resolved.read_text(encoding="utf-8")

    @function_tool(tool_input_guardrails=[deny_gate])
    def grep(pattern: str, path: str) -> str:
        """Return lines under ``path`` containing the literal ``pattern``.

        Args:
            pattern: Literal substring to search for.
            path: File or directory (recursively) to search, within data dirs.
        """
        resolved = _resolve_within(path, read_roots)
        files = [resolved] if resolved.is_file() else sorted(resolved.rglob("*"))
        hits: list[str] = []
        for file in files:
            if not file.is_file():
                continue
            try:
                for lineno, line in enumerate(
                    file.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if pattern in line:
                        hits.append(f"{file}:{lineno}:{line}")
            except UnicodeDecodeError, OSError:
                continue
        return "\n".join(hits)

    @function_tool(tool_input_guardrails=[deny_gate])
    def glob(pattern: str, root: str) -> str:
        """List files under ``root`` matching a glob ``pattern``.

        Args:
            pattern: Glob pattern (e.g. ``*.md``).
            root: Directory to search, within the data directories.
        """
        resolved = _resolve_within(root, read_roots)
        matches = [
            str(p)
            for p in sorted(resolved.rglob("*"))
            if p.is_file() and fnmatch.fnmatch(p.name, pattern)
        ]
        return "\n".join(matches)

    return [read_file, grep, glob]


def build_write_tools(config: AppConfig) -> list[FunctionTool]:
    """Write-family tools (`write_file`, `edit_file`) confined to drafts dir."""
    draft_roots = (config.drafts_dir,)

    @function_tool(tool_input_guardrails=[deny_gate])
    def write_file(path: str, content: str) -> str:
        """Write a working-copy draft under ``data/output/drafts/``.

        Args:
            path: Destination path, which must be under the drafts directory.
            content: UTF-8 text to write.
        """
        resolved = _resolve_within(path, draft_roots)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {resolved}"

    @function_tool(tool_input_guardrails=[deny_gate])
    def edit_file(path: str, old: str, new: str) -> str:
        """Replace ``old`` with ``new`` in a draft under the drafts directory.

        Args:
            path: Draft file to edit, under the drafts directory.
            old: Exact text to replace.
            new: Replacement text.
        """
        resolved = _resolve_within(path, draft_roots)
        text = resolved.read_text(encoding="utf-8")
        if old not in text:
            return f"no change: {old!r} not found in {resolved}"
        resolved.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"edited {resolved}"

    return [write_file, edit_file]


def build_web_tools(config: AppConfig) -> list[FunctionTool]:
    """Web-family tools (`web_search`, `web_fetch`) — thin, minimal seams.

    These are deliberately minimal placeholders (architecture grants web access
    to the Researcher only, to resolve citation metadata). A later feature wires
    a real web client; here they exist so the Researcher's tool scope is real
    and testable. ``config`` is accepted for signature parity with the other
    factories and future injection of a web client.
    """
    _ = config

    @function_tool(tool_input_guardrails=[deny_gate])
    def web_search(query: str) -> str:
        """Search the web for citation metadata (minimal seam — not yet wired).

        Args:
            query: Search query (e.g. a paper title or DOI).
        """
        logger.info(json.dumps({"event": "web_search", "query_len": len(query)}))
        return f"web_search seam: no live backend configured for query {query!r}"

    @function_tool(tool_input_guardrails=[deny_gate])
    def web_fetch(url: str) -> str:
        """Fetch a URL's text for citation metadata (minimal seam — not wired).

        Args:
            url: URL to fetch.
        """
        logger.info(json.dumps({"event": "web_fetch", "url_len": len(url)}))
        return f"web_fetch seam: no live backend configured for url {url!r}"

    return [web_search, web_fetch]


__all__ = [
    "ToolAccessError",
    "ToolCallDecision",
    "build_read_tools",
    "build_web_tools",
    "build_write_tools",
    "deny_gate",
    "evaluate_tool_call",
]

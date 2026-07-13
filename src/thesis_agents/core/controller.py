"""The deterministic controller — the instrumented ``run_agent()`` primitive.

This feature builds **only** the observability seam the future state machine
will route through: a ``run_id`` factory and an instrumented ``run_agent()``
that wraps the feature-2 :meth:`OpenRouterClient.run_stage` for a single
agent/stage, emitting exactly one structured log line per call and, when a
trace directory is provided, appending one full JSON record (untruncated prompt
and output) to a per-run JSONL transcript.

Intentionally **not** built here: the ``create_mode`` / ``review_mode`` state
machines (loop caps, human checkpoints, rubric gating). The backlog skipped the
controller state machine; that belongs to a future ``controller`` feature which
will call :func:`new_run_id` once per invocation and thread the resulting
``run_id`` through all four ``run_agent()`` calls so their log lines and their
shared ``<trace_dir>/<run_id>.jsonl`` transcript correlate.

Layering (architecture.md §4): ``core`` may import ``agents``, ``adapters``,
``config`` and ``schemas`` only — never ``entrypoints``. Externals (the model
client) are **injected**, so this module is unit-testable with no network.

Observability policy (architecture.md §6.7, §9; conventions.md §5): logging is
stdlib :mod:`logging` writing JSON lines, plus optional local JSONL files. No
LangChain, no LangSmith/Langfuse, no third-party telemetry — full draft/source
content stays local and no second secret is introduced. The INFO log line
carries only ids/lengths/usage; the untruncated prompt and output go **only**
to the local trace file.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from thesis_agents.adapters.openrouter import OpenRouterClient, StageResult
from thesis_agents.agents import AgentDefinition

logger = logging.getLogger(__name__)

#: Log/trace event name for a single instrumented agent stage.
RUN_AGENT_EVENT = "run_agent"


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Typed result of one instrumented agent stage — never a raw string blob.

    Carries the injected ``run_id`` that correlates every stage of one pipeline
    invocation alongside the feature-2 :class:`StageResult` (tier, model slug,
    usage/cost, duration, and the agent's output).
    """

    run_id: str
    agent: str
    result: StageResult


def new_run_id() -> str:
    """Generate a fresh, collision-resistant run id (stdlib only).

    The future controller calls this **once** per ``create_mode`` /
    ``review_mode`` invocation and threads the value through every
    :func:`run_agent` call so all stages of one run share it. A random UUID
    (not a wall-clock timestamp) avoids collisions between runs started in the
    same instant.
    """
    return uuid.uuid4().hex


def _summary_fields(
    *,
    agent: str,
    stage: str,
    run_id: str,
    result: StageResult,
) -> dict[str, object]:
    """Build the flat, JSON-serializable field set logged and traced per call."""
    return {
        "event": RUN_AGENT_EVENT,
        "agent": agent,
        "stage": stage,
        "run_id": run_id,
        "tier": result.tier,
        "model": result.model,
        "duration_ms": round(result.duration_ms, 3),
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "total_tokens": result.usage.total_tokens,
        "cost_usd": result.usage.cost_usd,
        "outcome": "ok",
    }


def _append_trace(
    trace_dir: Path,
    run_id: str,
    summary: dict[str, object],
    *,
    prompt: str,
    output: str,
) -> Path:
    """Append one full JSON record to ``<trace_dir>/<run_id>.jsonl``.

    The record is the logged summary plus the **untruncated** prompt and output,
    so the file is a complete, replayable, local-only transcript across every
    stage that shares ``run_id``. The directory is created with :mod:`pathlib`
    if missing.
    """
    trace_dir.mkdir(parents=True, exist_ok=True)
    record = {**summary, "prompt": prompt, "output": output}
    path = trace_dir / f"{run_id}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return path


async def run_agent(
    client: OpenRouterClient,
    *,
    agent: AgentDefinition,
    stage: str,
    run_id: str,
    prompt: str,
    trace_dir: Path | None = None,
) -> AgentRunResult:
    """Run one agent stage with full instrumentation.

    Invokes the **injected** ``client``'s :meth:`OpenRouterClient.run_stage` for
    ``agent`` at ``stage`` under the agent's own turn cap, then:

    1. emits **exactly one** structured log line (``logger.info(json.dumps(...))``
       on success, ``logger.error(...)`` with ``outcome="error"`` on failure)
       carrying agent name, stage, tier, model slug, ``run_id``, ``duration_ms``,
       prompt/completion token usage, derived cost, and outcome — never the raw
       prompt/output text (conventions.md §5);
    2. when ``trace_dir`` is not ``None``, appends **one** full JSON record
       (the same metadata plus the untruncated ``prompt`` and output) to
       ``<trace_dir>/<run_id>.jsonl``.

    ``run_id`` is injected by the caller (the future controller generates it once
    via :func:`new_run_id`), so all stages of one run correlate. Returns a typed
    :class:`AgentRunResult`; on a client failure the exception propagates after
    the error line is logged (no trace record is written for a failed call).
    """
    try:
        result = await client.run_stage(
            agent.agent,
            prompt,
            tier=agent.tier,
            stage=stage,
            max_turns=agent.max_turns,
        )
    except Exception:
        logger.error(
            json.dumps(
                {
                    "event": RUN_AGENT_EVENT,
                    "agent": agent.name,
                    "stage": stage,
                    "run_id": run_id,
                    "tier": agent.tier,
                    "outcome": "error",
                }
            )
        )
        raise

    summary = _summary_fields(
        agent=agent.name,
        stage=stage,
        run_id=run_id,
        result=result,
    )
    logger.info(json.dumps(summary))

    if trace_dir is not None:
        _append_trace(trace_dir, run_id, summary, prompt=prompt, output=result.output)

    return AgentRunResult(run_id=run_id, agent=agent.name, result=result)


__all__ = [
    "RUN_AGENT_EVENT",
    "AgentRunResult",
    "new_run_id",
    "run_agent",
]

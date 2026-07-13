"""The four agent definitions: per-agent model tier, tool scope, guardrail.

This module declares the pipeline's four agents — **Researcher, Writer,
Reviewer, Judge** — following architecture.md §5. Each agent is built with:

- its **per-agent model tier** resolved through :mod:`config` (never an inlined
  slug) and the feature-2 ``OpenRouterClient.model_for_tier`` wiring, so tier →
  ``OpenAIChatCompletionsModel`` is reused, not re-invented;
- its **least-privilege tool subset** from the §5 table (only the Researcher
  gets web tools; Reviewer and Judge are read-only; the Writer adds draft
  writes); every tool carries the code-side pre-tool-call deny gate;
- its **system prompt loaded from a file** under ``prompts/`` (never an inline
  string, conventions.md §9);
- the Judge's ``max_turns = 3`` cap (architecture.md §6.7 / §7).

Layering (architecture.md §4): this module imports only from ``adapters/`` and
``config`` — never from ``core/`` or ``entrypoints/``. Structured output for the
Reviewer and Judge is obtained by **prompting the schema** (embedded in their
prompt files) plus code-side validation in later features — never a native
``output_type`` that would force unreliable tool-call JSON (architecture.md
§6.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from agents import Agent

from config import TIER_FLASH, TIER_PRO, TIER_QWEN_PLUS, AppConfig
from thesis_agents.adapters.openrouter import OpenRouterClient
from thesis_agents.adapters.tools import (
    build_read_tools,
    build_web_tools,
    build_write_tools,
)

#: Directory holding the four agent system prompts (architecture.md §3).
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

#: The Judge runs under an explicit turn cap (architecture.md §6.7 / §7).
JUDGE_MAX_TURNS = 3


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """A built agent plus the routing metadata the controller needs.

    The SDK ``Agent`` has no per-agent turn cap field (``max_turns`` is a run
    argument), so it is carried here: the Judge's cap is ``3`` and the others
    inherit the per-stage default from ``config`` (``None`` = use default).
    """

    name: str
    tier: str
    agent: Agent
    max_turns: int | None = None


@cache
def load_prompt(name: str) -> str:
    """Read an agent system prompt from ``prompts/<name>.md``.

    Prompts are files, never inline strings (conventions.md §9). Cached because
    the prompt text is immutable for a process.
    """
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file for {name!r} is empty.")
    return text


def build_researcher(config: AppConfig, client: OpenRouterClient) -> AgentDefinition:
    """Researcher (pro): read + web tools, to gather grounded material."""
    tools = build_read_tools(config) + build_web_tools(config)
    agent = Agent(
        name="researcher",
        instructions=load_prompt("researcher"),
        model=client.model_for_tier(TIER_PRO),
        tools=tools,
    )
    return AgentDefinition(name="researcher", tier=TIER_PRO, agent=agent)


def build_writer(config: AppConfig, client: OpenRouterClient) -> AgentDefinition:
    """Writer (qwen_plus): read + draft-write tools, produces the deliverable."""
    tools = build_read_tools(config) + build_write_tools(config)
    agent = Agent(
        name="writer",
        instructions=load_prompt("writer"),
        model=client.model_for_tier(TIER_QWEN_PLUS),
        tools=tools,
    )
    return AgentDefinition(name="writer", tier=TIER_QWEN_PLUS, agent=agent)


def build_reviewer(config: AppConfig, client: OpenRouterClient) -> AgentDefinition:
    """Reviewer (flash): read-only soft gate, {approved, feedback} via prompt."""
    agent = Agent(
        name="reviewer",
        instructions=load_prompt("reviewer"),
        model=client.model_for_tier(TIER_FLASH),
        tools=build_read_tools(config),
    )
    return AgentDefinition(name="reviewer", tier=TIER_FLASH, agent=agent)


def build_judge(config: AppConfig, client: OpenRouterClient) -> AgentDefinition:
    """Judge (pro): read-only terminal gate, max_turns=3, Verdict via prompt."""
    agent = Agent(
        name="judge",
        instructions=load_prompt("judge"),
        model=client.model_for_tier(TIER_PRO),
        tools=build_read_tools(config),
    )
    return AgentDefinition(
        name="judge", tier=TIER_PRO, agent=agent, max_turns=JUDGE_MAX_TURNS
    )


def build_agents(
    config: AppConfig, client: OpenRouterClient
) -> dict[str, AgentDefinition]:
    """Build all four agent definitions keyed by name (injected client)."""
    return {
        definition.name: definition
        for definition in (
            build_researcher(config, client),
            build_writer(config, client),
            build_reviewer(config, client),
            build_judge(config, client),
        )
    }


__all__ = [
    "JUDGE_MAX_TURNS",
    "PROMPTS_DIR",
    "AgentDefinition",
    "build_agents",
    "build_judge",
    "build_researcher",
    "build_reviewer",
    "build_writer",
    "load_prompt",
]

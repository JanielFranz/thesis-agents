"""Unit tests for the four agent definitions, tool scoping, and the deny gate.

These tests never touch the network or a real model: the injected
``AsyncOpenAI`` client is built from the dummy API key the shared ``conftest``
fixture provides, and no run is ever executed — only agent *definitions* and the
pure guardrail logic are exercised.
"""

from __future__ import annotations

import pytest
from agents import Agent
from agents.tool_context import ToolContext
from agents.tool_guardrails import ToolInputGuardrailData

from config import (
    TIER_FLASH,
    TIER_PRO,
    TIER_QWEN_PLUS,
    AppConfig,
    load_config,
)
from thesis_agents.adapters.openrouter import OpenRouterClient, build_openrouter_client
from thesis_agents.adapters.tools import deny_gate, evaluate_tool_call
from thesis_agents.agents import (
    JUDGE_MAX_TURNS,
    build_agents,
    load_prompt,
)

# --- fixtures --------------------------------------------------------------


@pytest.fixture
def config() -> AppConfig:
    return load_config()


@pytest.fixture
def client(config: AppConfig) -> OpenRouterClient:
    # build_openrouter_client only constructs the client; no network call.
    return OpenRouterClient(config, build_openrouter_client(config))


@pytest.fixture
def agents(config: AppConfig, client: OpenRouterClient):
    return build_agents(config, client)


def _tool_names(agent: Agent) -> set[str]:
    return {tool.name for tool in agent.tools}


# --- per-agent model tier --------------------------------------------------


def test_agents_resolve_expected_tiers(agents, config: AppConfig) -> None:
    assert agents["researcher"].tier == TIER_PRO
    assert agents["writer"].tier == TIER_QWEN_PLUS
    assert agents["reviewer"].tier == TIER_FLASH
    assert agents["judge"].tier == TIER_PRO


def test_agent_model_slugs_match_configured_tier(agents, config: AppConfig) -> None:
    pro = config.model_for_tier(TIER_PRO)
    flash = config.model_for_tier(TIER_FLASH)
    qwen = config.model_for_tier(TIER_QWEN_PLUS)

    assert agents["researcher"].agent.model.model == pro
    assert agents["judge"].agent.model.model == pro
    assert agents["writer"].agent.model.model == qwen
    assert agents["reviewer"].agent.model.model == flash
    # Slugs come from config, not inlined constants at the call site.
    assert pro != flash != qwen


# --- least-privilege tool scoping -----------------------------------------


def test_researcher_has_read_and_web_tools(agents) -> None:
    names = _tool_names(agents["researcher"].agent)
    assert {"read_file", "grep", "glob"} <= names
    assert {"web_search", "web_fetch"} <= names
    # Researcher does not write.
    assert "write_file" not in names and "edit_file" not in names


def test_writer_has_read_and_draft_write_but_no_web(agents) -> None:
    names = _tool_names(agents["writer"].agent)
    assert {"read_file", "grep", "glob"} <= names
    assert {"write_file", "edit_file"} <= names
    assert "web_search" not in names and "web_fetch" not in names


def test_reviewer_is_read_only(agents) -> None:
    names = _tool_names(agents["reviewer"].agent)
    assert names == {"read_file", "grep", "glob"}
    assert "write_file" not in names and "web_search" not in names


def test_judge_is_read_only_with_turn_cap(agents) -> None:
    names = _tool_names(agents["judge"].agent)
    assert names == {"read_file", "grep", "glob"}
    assert "write_file" not in names and "web_search" not in names
    assert agents["judge"].max_turns == JUDGE_MAX_TURNS == 3


def test_every_tool_carries_the_deny_gate(agents) -> None:
    for definition in agents.values():
        for tool in definition.agent.tools:
            guardrails = tool.tool_input_guardrails or []
            assert deny_gate in guardrails, (
                f"{definition.name}/{tool.name} is missing the deny gate"
            )


# --- prompts loaded from files --------------------------------------------


def test_prompts_are_loaded_from_files(agents) -> None:
    for name in ("researcher", "writer", "reviewer", "judge"):
        instructions = agents[name].agent.instructions
        assert isinstance(instructions, str) and instructions.strip()
        assert instructions == load_prompt(name)


def test_judge_prompt_embeds_rubric_and_verdict_shape() -> None:
    judge = load_prompt("judge")
    for criterion in ("grounding", "references", "scope", "structure", "argument"):
        assert criterion in judge
    assert "quotedJustification" in judge
    assert "perCriterionScores" in judge


def test_reviewer_prompt_embeds_review_shape() -> None:
    reviewer = load_prompt("reviewer")
    assert '"approved"' in reviewer
    assert '"feedback"' in reviewer


# --- the pre-tool-call deny gate (pure logic) ------------------------------


def test_evaluate_allows_ordinary_read() -> None:
    decision = evaluate_tool_call("read_file", {"path": "data/sources/paper.md"})
    assert decision.allowed is True


def test_evaluate_denies_env_read() -> None:
    decision = evaluate_tool_call("read_file", {"path": "../.env"})
    assert decision.allowed is False
    assert ".env" in decision.reason.lower() or "secret" in decision.reason.lower()


def test_evaluate_denies_secret_in_json_string_args() -> None:
    decision = evaluate_tool_call("read_file", '{"path": "config/credentials.yaml"}')
    assert decision.allowed is False


def test_evaluate_denies_nested_agent_spawn() -> None:
    decision = evaluate_tool_call("spawn_agent", {"task": "do something"})
    assert decision.allowed is False
    assert "spawn" in decision.reason.lower() or "agent" in decision.reason.lower()


def test_evaluate_denies_task_delegation_tool() -> None:
    assert evaluate_tool_call("run_task", {}).allowed is False
    assert evaluate_tool_call("delegate_to_subagent", {}).allowed is False


# --- the deny gate as the SDK guardrail (synthetic inputs) -----------------


def _guardrail_data(
    agents, tool_name: str, tool_arguments: str
) -> ToolInputGuardrailData:
    ctx: ToolContext = ToolContext(
        context=None,
        tool_name=tool_name,
        tool_call_id="call-test",
        tool_arguments=tool_arguments,
    )
    return ToolInputGuardrailData(context=ctx, agent=agents["reviewer"].agent)


def test_deny_gate_raises_on_env_read(agents) -> None:
    data = _guardrail_data(agents, "read_file", '{"path": "/repo/.env"}')
    output = deny_gate.guardrail_function(data)
    assert output.behavior["type"] == "raise_exception"


def test_deny_gate_raises_on_nested_spawn(agents) -> None:
    data = _guardrail_data(agents, "spawn_subagent", "{}")
    output = deny_gate.guardrail_function(data)
    assert output.behavior["type"] == "raise_exception"


def test_deny_gate_allows_ordinary_call(agents) -> None:
    data = _guardrail_data(agents, "read_file", '{"path": "data/sources/paper.md"}')
    output = deny_gate.guardrail_function(data)
    assert output.behavior["type"] == "allow"

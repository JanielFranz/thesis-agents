"""Unit tests for the OpenRouter adapter.

No real network: the outbound ``AsyncOpenAI`` client and the SDK runner are
mocked/faked and injected. Tests assert concrete results — the client targets
the configured OpenRouter base URL, tier selection returns the right slug, and
per-call usage/cost land in the typed :class:`StageResult`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import ConfigError, load_config
from thesis_agents.adapters.openrouter import (
    OpenRouterClient,
    StageResult,
    build_openrouter_client,
)


@dataclass
class _FakeUsage:
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class _FakeRunner:
    """Injected stand-in for the SDK Runner; records args, returns a result."""

    def __init__(self, result: object) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def run(self, starting_agent, input, *, max_turns, run_config):  # noqa: A002
        self.calls.append(
            {
                "agent": starting_agent,
                "input": input,
                "max_turns": max_turns,
                "run_config": run_config,
            }
        )
        return self._result


class _RaisingRunner:
    async def run(self, *args, **kwargs):
        raise RuntimeError("model backend exploded")


def _fake_result(final_output: str, usage: _FakeUsage) -> SimpleNamespace:
    return SimpleNamespace(
        final_output=final_output,
        context_wrapper=SimpleNamespace(usage=usage),
    )


def test_build_openrouter_client_targets_base_url() -> None:
    config = load_config()
    client = build_openrouter_client(config)
    assert str(client.base_url).rstrip("/") == config.openrouter_base_url.rstrip("/")
    assert "openrouter.ai" in str(client.base_url)


def test_resolve_tier_returns_slug_for_each_tier() -> None:
    config = load_config()
    client = OpenRouterClient(config, client=MagicMock(), runner=MagicMock())
    assert client.resolve_tier("pro") == config.model_pro
    assert client.resolve_tier("flash") == config.model_flash
    assert client.resolve_tier("qwen_plus") == config.model_qwen_plus


def test_resolve_tier_unknown_raises() -> None:
    config = load_config()
    client = OpenRouterClient(config, client=MagicMock(), runner=MagicMock())
    with pytest.raises(ConfigError):
        client.resolve_tier("bogus")


def test_model_for_tier_uses_injected_client_and_slug() -> None:
    config = load_config()
    injected = MagicMock(name="async_openai")
    client = OpenRouterClient(config, client=injected, runner=MagicMock())

    model = client.model_for_tier("qwen_plus")

    assert model.model == config.model_qwen_plus
    assert model._client is injected


def test_run_stage_captures_usage_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Price the qwen_plus tier so cost derivation is exercised deterministically.
    monkeypatch.setenv("OPENROUTER_PRICE_QWEN_PLUS_INPUT", "2.0")
    monkeypatch.setenv("OPENROUTER_PRICE_QWEN_PLUS_OUTPUT", "6.0")
    config = load_config()

    usage = _FakeUsage(
        requests=1,
        input_tokens=1_000_000,
        output_tokens=500_000,
        total_tokens=1_500_000,
    )
    runner = _FakeRunner(_fake_result("final draft text", usage))
    client = OpenRouterClient(config, client=MagicMock(), runner=runner)

    result = asyncio.run(
        client.run_stage(
            MagicMock(name="agent"),
            "write the chapter",
            tier="qwen_plus",
            stage="writer_draft",
            max_turns=4,
        )
    )

    assert isinstance(result, StageResult)
    assert result.stage == "writer_draft"
    assert result.tier == "qwen_plus"
    assert result.model == config.model_qwen_plus
    assert result.output == "final draft text"
    assert result.usage.input_tokens == 1_000_000
    assert result.usage.output_tokens == 500_000
    assert result.usage.total_tokens == 1_500_000
    # 1M in @ $2 + 0.5M out @ $6 = 2.0 + 3.0 = 5.0
    assert result.usage.cost_usd == pytest.approx(5.0)
    assert result.duration_ms >= 0.0
    # per-stage max_turns cap was forwarded to the runner
    assert runner.calls[0]["max_turns"] == 4


def test_run_stage_defaults_max_turns_from_config() -> None:
    config = load_config()
    usage = _FakeUsage(requests=1, input_tokens=10, output_tokens=5, total_tokens=15)
    runner = _FakeRunner(_fake_result("ok", usage))
    client = OpenRouterClient(config, client=MagicMock(), runner=runner)

    asyncio.run(
        client.run_stage(MagicMock(name="agent"), "x", tier="pro", stage="judge")
    )

    assert runner.calls[0]["max_turns"] == config.max_turns


def test_run_stage_propagates_runner_error() -> None:
    config = load_config()
    client = OpenRouterClient(config, client=MagicMock(), runner=_RaisingRunner())
    with pytest.raises(RuntimeError, match="model backend exploded"):
        asyncio.run(
            client.run_stage(
                MagicMock(name="agent"), "x", tier="pro", stage="researcher"
            )
        )

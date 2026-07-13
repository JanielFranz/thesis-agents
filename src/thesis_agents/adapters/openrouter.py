"""OpenRouter model backend adapter.

This is the only module that wires the OpenAI Agents SDK to OpenRouter's
OpenAI-compatible gateway. It stands up the outbound client against
``config.openrouter_base_url``, resolves the per-agent model tier
(``pro`` / ``flash`` / ``qwen_plus``) to its configured slug — never inlining a
slug at a call site — and runs a single agent *stage* under a per-stage
``max_turns`` cap, returning a **typed** result that captures per-call token
usage and derived cost for accounting (architecture.md §5, §6.7).

Injection (conventions.md §3, §4): the outbound ``AsyncOpenAI`` client and the
SDK runner are passed in, never constructed inside the method that uses them, so
unit tests mock the client/runner layer and never touch the network.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.run import RunConfig
from openai import AsyncOpenAI

from config import AppConfig

if TYPE_CHECKING:
    from agents.result import RunResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StageUsage:
    """Per-call token usage and the cost derived from the tier's pricing."""

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True, slots=True)
class StageResult:
    """Typed result of one agent stage run — never a raw string blob."""

    stage: str
    tier: str
    model: str
    output: str
    usage: StageUsage
    duration_ms: float


class SupportsRun(Protocol):
    """Structural type for the SDK runner (injectable / mockable)."""

    async def run(
        self,
        starting_agent: Agent[Any],
        input: str,
        *,
        max_turns: int,
        run_config: RunConfig,
    ) -> RunResult: ...


def build_openrouter_client(config: AppConfig) -> AsyncOpenAI:
    """Construct the outbound ``AsyncOpenAI`` client pointed at OpenRouter.

    The base URL and API key come from :mod:`config` (the sole env reader); the
    key is never read or logged here. Callers inject the returned client into
    :class:`OpenRouterClient`, so this factory is the single construction site.
    """
    return AsyncOpenAI(
        base_url=config.openrouter_base_url,
        api_key=config.openrouter_api_key,
        timeout=config.request_timeout_s,
    )


class OpenRouterClient:
    """Runs agent stages against OpenRouter with tier selection and accounting.

    Both the outbound :class:`~openai.AsyncOpenAI` client and the SDK ``runner``
    are injected so the whole class is unit-testable without a network call.
    """

    def __init__(
        self,
        config: AppConfig,
        client: AsyncOpenAI,
        runner: SupportsRun | type[Runner] = Runner,
    ) -> None:
        self._config = config
        self._client = client
        self._runner = runner

    def resolve_tier(self, tier: str) -> str:
        """Resolve a tier name to its configured model slug (via config)."""
        return self._config.model_for_tier(tier)

    def model_for_tier(self, tier: str) -> OpenAIChatCompletionsModel:
        """Build the SDK model for ``tier`` bound to the injected client."""
        return OpenAIChatCompletionsModel(
            model=self.resolve_tier(tier),
            openai_client=self._client,
        )

    def _derive_cost(self, tier: str, input_tokens: int, output_tokens: int) -> float:
        price = self._config.price_for_tier(tier)
        return (
            input_tokens / 1_000_000 * price.input_usd_per_mtok
            + output_tokens / 1_000_000 * price.output_usd_per_mtok
        )

    async def run_stage(
        self,
        agent: Agent[Any],
        input: str,
        *,
        tier: str,
        stage: str,
        max_turns: int | None = None,
    ) -> StageResult:
        """Run one agent stage and return a typed :class:`StageResult`.

        ``tier`` selects the model slug from config; ``max_turns`` defaults to
        the per-stage cap in ``config.max_turns`` (architecture.md §6.7).
        """
        model = self.model_for_tier(tier)
        turn_cap = max_turns if max_turns is not None else self._config.max_turns
        run_config = RunConfig(model=model, tracing_disabled=True)

        started = time.monotonic()
        try:
            result = await self._runner.run(
                agent,
                input,
                max_turns=turn_cap,
                run_config=run_config,
            )
        except Exception:
            duration_ms = (time.monotonic() - started) * 1000
            logger.error(
                json.dumps(
                    {
                        "event": "run_stage",
                        "stage": stage,
                        "tier": tier,
                        "model": model.model,
                        "duration_ms": round(duration_ms, 3),
                        "outcome": "error",
                    }
                )
            )
            raise
        duration_ms = (time.monotonic() - started) * 1000

        raw = result.context_wrapper.usage
        cost_usd = self._derive_cost(tier, raw.input_tokens, raw.output_tokens)
        usage = StageUsage(
            requests=raw.requests,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            total_tokens=raw.total_tokens,
            cost_usd=cost_usd,
        )

        logger.info(
            json.dumps(
                {
                    "event": "run_stage",
                    "stage": stage,
                    "tier": tier,
                    "model": model.model,
                    "duration_ms": round(duration_ms, 3),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "cost_usd": usage.cost_usd,
                    "outcome": "ok",
                }
            )
        )

        return StageResult(
            stage=stage,
            tier=tier,
            model=model.model,
            output=str(result.final_output),
            usage=usage,
            duration_ms=duration_ms,
        )

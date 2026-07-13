"""Unit tests for the ``create_mode`` / ``review_mode`` state machines.

Fully mocked: the ``OpenRouterClient`` is replaced by a scripted fake whose
``run_stage`` returns canned per-stage outputs, and the four agents are
lightweight :class:`AgentDefinition` wrappers around stub SDK agents. No network,
no real model. The async entrypoints are driven with ``asyncio.run(...)`` — the
same pattern the feature-4 ``run_agent`` tests use, so no new test dependency is
introduced. Tests assert concrete results: loop-cap counters, a shared
``run_id``, unapproved completion, the code-side verify override, and that
``review_mode`` never invokes the Writer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import load_config
from thesis_agents.adapters.openrouter import StageResult, StageUsage
from thesis_agents.agents import AgentDefinition
from thesis_agents.core.controller import (
    RUN_AGENT_EVENT,
    CreateResult,
    ReviewResult,
    create_mode,
    review_mode,
)
from thesis_agents.schemas.models import DocSpec

CONTROLLER_LOGGER = "thesis_agents.core.controller"

# A draft whose sentences the verdict quotes are copied from verbatim.
DRAFT = (
    "# Introduction\n\n"
    "Machine learning models require careful evaluation before deployment.\n\n"
    "The literature review synthesizes recent advances in the field.\n\n"
    "Empirical results demonstrate consistent improvements across benchmarks.\n\n"
    "The methodology follows established experimental protocols closely.\n\n"
    "Formal academic register is maintained throughout this chapter.\n\n"
    "References are formatted according to APA seventh edition guidelines.\n"
)

# id -> (passing score, a verbatim quote from DRAFT that is >= 12 chars).
_CRITERIA = {
    "grounding": (5, "require careful evaluation before deployment"),
    "references": (4, "APA seventh edition guidelines"),
    "scope": (4, "synthesizes recent advances in the field"),
    "structure": (4, "The methodology follows established experimental protocols"),
    "argument": (4, "demonstrate consistent improvements across benchmarks"),
    "style": (4, "Formal academic register is maintained"),
}


def _verdict_json(
    *,
    approved: bool = True,
    score_overrides: dict[str, int] | None = None,
    quote_overrides: dict[str, str] | None = None,
) -> str:
    score_overrides = score_overrides or {}
    quote_overrides = quote_overrides or {}
    scores = []
    for cid, (score, quote) in _CRITERIA.items():
        scores.append(
            {
                "criterionId": cid,
                "score": score_overrides.get(cid, score),
                "quotedJustification": quote_overrides.get(cid, quote),
                "comment": f"{cid} looks fine",
            }
        )
    return json.dumps(
        {"approved": approved, "perCriterionScores": scores, "reasons": ["ok"]}
    )


def _review_json(*, approved: bool, feedback: str = "notes") -> str:
    return json.dumps({"approved": approved, "feedback": feedback})


def _stage_result(stage: str, tier: str, output: str) -> StageResult:
    return StageResult(
        stage=stage,
        tier=tier,
        model=f"vendor/{tier}-model",
        output=output,
        usage=StageUsage(
            requests=1,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
        ),
        duration_ms=1.0,
    )


class _ScriptedClient:
    """Injected fake: returns a canned output per stage and records every call."""

    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs
        self.stages: list[str] = []

    async def run_stage(self, agent, prompt, *, tier, stage, max_turns=None):  # noqa: ANN001
        self.stages.append(stage)
        return _stage_result(stage, tier, self._outputs[stage])


def _agent(name: str, tier: str, max_turns: int | None = None) -> AgentDefinition:
    return AgentDefinition(
        name=name, tier=tier, agent=MagicMock(name=name), max_turns=max_turns
    )


def _agents() -> dict[str, AgentDefinition]:
    return {
        "researcher": _agent("researcher", "pro"),
        "writer": _agent("writer", "qwen_plus"),
        "reviewer": _agent("reviewer", "flash"),
        "judge": _agent("judge", "pro", max_turns=3),
    }


def _spec() -> DocSpec:
    return DocSpec(
        title="Test Chapter",
        docType="thesis-chapter",
        format="docx",
        language="en",
        chapter={"number": 1, "title": "Introduction"},
        audience="thesis committee",
        targetWords=3000,
        citationStyle="APA",
        requirements=["ground every claim"],
        notes="none",
    )


@pytest.fixture
def config(tmp_path: Path):
    """Real AppConfig with output under tmp_path and tracing off."""
    return replace(load_config(), output_dir=tmp_path, trace_dir=None)


def _writer_outputs(draft: str) -> dict[str, str]:
    return {
        "researcher": "research notes",
        "writer_outline": "the outline",
        "writer_draft": draft,
        "writer_revision": draft,
    }


def test_create_mode_honors_review_cap(config) -> None:
    """Reviewer always disapproves -> exactly MAX_REVIEW_PASSES reviewer passes."""
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": _review_json(approved=False),
        "judge": _verdict_json(approved=True),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    assert isinstance(result, CreateResult)
    assert result.review_passes == config.max_review_passes
    assert client.stages.count("reviewer") == config.max_review_passes
    # One Writer revision happens between the two disapproving reviews, no more.
    assert client.stages.count("writer_revision") == config.max_review_passes - 1
    assert result.output_path.exists()


def test_create_mode_judge_cap_completes_unapproved(config) -> None:
    """Judge always rejected (sub-threshold) -> capped, still ships, not approved."""
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": _review_json(approved=True),
        # Model self-reports approved=True but grounding is below its threshold.
        "judge": _verdict_json(approved=True, score_overrides={"grounding": 2}),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    assert result.judge_passes == config.max_judge_retries
    assert client.stages.count("judge") == config.max_judge_retries
    assert result.approved is False
    # The run still completed with a rendered artifact (no human prompt/loop).
    assert result.output_path.exists()
    assert result.output_path.suffix == ".docx"
    assert any("grounding" in r for r in result.verdict.reasons)


def test_create_mode_threads_one_shared_run_id(
    config, caplog: pytest.LogCaptureFixture
) -> None:
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": _review_json(approved=True),
        "judge": _verdict_json(approved=True),
    }
    client = _ScriptedClient(outputs)

    with caplog.at_level(logging.INFO, logger=CONTROLLER_LOGGER):
        result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    run_ids = {
        json.loads(rec.getMessage())["run_id"]
        for rec in caplog.records
        if rec.name == CONTROLLER_LOGGER
        and json.loads(rec.getMessage()).get("event") == RUN_AGENT_EVENT
    }
    assert run_ids == {result.run_id}
    # Every stage of the run emitted a run_agent line under this run_id.
    assert len(run_ids) == 1


def test_create_mode_verify_gate_overrides_model_self_report(config) -> None:
    """approved=True verdict with a fabricated quote is rejected by verify."""
    fabricated = "this exact sentence never appears anywhere in the draft"
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": _review_json(approved=True),
        "judge": _verdict_json(
            approved=True, quote_overrides={"grounding": fabricated}
        ),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    # Model said approved; the code-side quote check must veto it.
    assert result.approved is False
    assert any("verbatim" in r.lower() for r in result.verdict.reasons)
    assert result.output_path.exists()


def test_create_mode_approves_on_clean_verdict(config) -> None:
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": _review_json(approved=True),
        "judge": _verdict_json(approved=True),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    assert result.approved is True
    assert result.judge_passes == 1
    assert client.stages.count("writer_revision") == 0
    assert result.output_path.exists()


def test_create_mode_reviewer_parse_failure_fails_safe(config) -> None:
    """Unparseable Reviewer output is treated as not-approved, not routed on."""
    outputs = _writer_outputs(DRAFT) | {
        "reviewer": "sorry, I could not comply with the JSON format",
        "judge": _verdict_json(approved=True),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(create_mode(_spec(), client, config, agents=_agents()))

    # Reviewer never approves -> the loop runs to the cap (proves no crash / no
    # routing on the raw text), and the run still completes.
    assert result.review_passes == config.max_review_passes
    assert result.review is not None and result.review.approved is False
    assert result.output_path.exists()


def test_review_mode_produces_report_without_writer(config) -> None:
    outputs = {
        "reviewer": _review_json(approved=True, feedback="solid draft"),
        "judge": _verdict_json(approved=True),
    }
    client = _ScriptedClient(outputs)

    result = asyncio.run(review_mode(DRAFT, _spec(), client, config, agents=_agents()))

    assert isinstance(result, ReviewResult)
    assert result.output_path.exists()
    assert result.output_path.name.startswith("review-report-")
    # No Writer (and no researcher) stage may run in review mode.
    assert not any(stage.startswith("writer") for stage in client.stages)
    assert "researcher" not in client.stages
    assert client.stages == ["reviewer", "judge"]
    assert result.approved is True

"""Unit tests for the instrumented ``run_agent()`` primitive.

No real network / no real model: the ``OpenRouterClient`` is replaced by a fake
whose ``run_stage`` returns a canned typed :class:`StageResult`, and the agent
is a lightweight :class:`AgentDefinition` around a stub SDK agent. Tests assert
concrete results — the exact log-line fields and types, a shared ``run_id``
across a simulated multi-agent run, one JSONL trace line per call (and none when
tracing is disabled), and the error-path log line + propagation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thesis_agents.adapters.openrouter import StageResult, StageUsage
from thesis_agents.agents import AgentDefinition
from thesis_agents.core.controller import (
    RUN_AGENT_EVENT,
    AgentRunResult,
    new_run_id,
    run_agent,
)

CONTROLLER_LOGGER = "thesis_agents.core.controller"


def _stage_result(stage: str, tier: str, output: str) -> StageResult:
    return StageResult(
        stage=stage,
        tier=tier,
        model=f"vendor/{tier}-model",
        output=output,
        usage=StageUsage(
            requests=1,
            input_tokens=1200,
            output_tokens=800,
            total_tokens=2000,
            cost_usd=0.0123,
        ),
        duration_ms=42.5,
    )


class _FakeClient:
    """Injected stand-in for OpenRouterClient; records calls, returns canned."""

    def __init__(self, result: StageResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def run_stage(self, agent, prompt, *, tier, stage, max_turns=None):  # noqa: ANN001
        self.calls.append(
            {
                "agent": agent,
                "prompt": prompt,
                "tier": tier,
                "stage": stage,
                "max_turns": max_turns,
            }
        )
        return self._result


class _RaisingClient:
    async def run_stage(self, *args, **kwargs):
        raise RuntimeError("model backend exploded")


def _agent(name: str, tier: str, max_turns: int | None = None) -> AgentDefinition:
    return AgentDefinition(
        name=name, tier=tier, agent=MagicMock(name=name), max_turns=max_turns
    )


def _controller_records(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [
        json.loads(rec.getMessage())
        for rec in caplog.records
        if rec.name == CONTROLLER_LOGGER
    ]


def test_new_run_id_is_unique_hex() -> None:
    ids = {new_run_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 32 and int(i, 16) >= 0 for i in ids)


def test_run_agent_logs_required_fields_with_types(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeClient(_stage_result("writer_draft", "qwen_plus", "the draft"))
    agent = _agent("writer", "qwen_plus")

    with caplog.at_level(logging.INFO, logger=CONTROLLER_LOGGER):
        result = asyncio.run(
            run_agent(
                client,
                agent=agent,
                stage="writer_draft",
                run_id="run-abc",
                prompt="write the chapter",
            )
        )

    assert isinstance(result, AgentRunResult)
    assert result.run_id == "run-abc"
    assert result.agent == "writer"
    assert result.result.output == "the draft"

    records = _controller_records(caplog)
    assert len(records) == 1
    line = records[0]
    assert line["event"] == RUN_AGENT_EVENT
    # string fields
    for key in ("agent", "stage", "run_id", "tier", "model", "outcome"):
        assert isinstance(line[key], str)
    assert line["agent"] == "writer"
    assert line["stage"] == "writer_draft"
    assert line["run_id"] == "run-abc"
    assert line["tier"] == "qwen_plus"
    assert line["outcome"] == "ok"
    # numeric fields
    assert isinstance(line["duration_ms"], (int, float))
    assert isinstance(line["cost_usd"], (int, float))
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        assert isinstance(line[key], int)
    assert line["input_tokens"] == 1200
    assert line["output_tokens"] == 800
    assert line["total_tokens"] == 2000
    # the INFO line must NOT carry raw prompt/output text (conventions §5)
    assert "prompt" not in line
    assert "output" not in line


def test_run_agent_forwards_agent_turn_cap_to_client() -> None:
    client = _FakeClient(_stage_result("judge", "pro", "verdict"))
    agent = _agent("judge", "pro", max_turns=3)

    asyncio.run(
        run_agent(client, agent=agent, stage="judge", run_id="r1", prompt="grade it")
    )

    assert client.calls[0]["max_turns"] == 3
    assert client.calls[0]["tier"] == "pro"
    assert client.calls[0]["stage"] == "judge"


def test_run_agent_shares_run_id_across_multi_agent_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_id = new_run_id()
    stages = [
        ("researcher", "pro", "research"),
        ("writer", "qwen_plus", "writer_draft"),
        ("reviewer", "flash", "reviewer"),
        ("judge", "pro", "judge"),
    ]

    with caplog.at_level(logging.INFO, logger=CONTROLLER_LOGGER):
        for name, tier, stage in stages:
            client = _FakeClient(_stage_result(stage, tier, f"{name} output"))
            asyncio.run(
                run_agent(
                    client,
                    agent=_agent(name, tier),
                    stage=stage,
                    run_id=run_id,
                    prompt=f"prompt for {name}",
                )
            )

    records = _controller_records(caplog)
    assert len(records) == 4
    assert {r["run_id"] for r in records} == {run_id}
    assert [r["agent"] for r in records] == [s[0] for s in stages]


def test_run_agent_appends_one_trace_line_per_call(tmp_path: Path) -> None:
    trace_dir = tmp_path / "traces"
    run_id = "run-xyz"

    for name, tier, stage in (
        ("researcher", "pro", "research"),
        ("writer", "qwen_plus", "writer_draft"),
    ):
        client = _FakeClient(_stage_result(stage, tier, f"{name} full output text"))
        asyncio.run(
            run_agent(
                client,
                agent=_agent(name, tier),
                stage=stage,
                run_id=run_id,
                prompt=f"full prompt for {name}",
                trace_dir=trace_dir,
            )
        )

    trace_file = trace_dir / f"{run_id}.jsonl"
    assert trace_file.exists()
    lines = trace_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["run_id"] == run_id
    assert first["agent"] == "researcher"
    # trace carries the FULL untruncated prompt and output plus the metadata
    assert first["prompt"] == "full prompt for researcher"
    assert first["output"] == "researcher full output text"
    assert first["stage"] == "research"
    assert first["tier"] == "pro"
    assert isinstance(first["total_tokens"], int)

    second = json.loads(lines[1])
    assert second["agent"] == "writer"
    assert second["output"] == "writer full output text"


def test_run_agent_writes_no_trace_when_disabled(
    tmp_path: Path,
) -> None:
    client = _FakeClient(_stage_result("writer_draft", "qwen_plus", "draft"))
    asyncio.run(
        run_agent(
            client,
            agent=_agent("writer", "qwen_plus"),
            stage="writer_draft",
            run_id="run-none",
            prompt="write",
            trace_dir=None,
        )
    )
    # No file created anywhere under tmp_path when tracing is disabled.
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_run_agent_logs_error_and_propagates(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    trace_dir = tmp_path / "traces"

    with caplog.at_level(logging.ERROR, logger=CONTROLLER_LOGGER):
        with pytest.raises(RuntimeError, match="model backend exploded"):
            asyncio.run(
                run_agent(
                    _RaisingClient(),
                    agent=_agent("researcher", "pro"),
                    stage="research",
                    run_id="run-err",
                    prompt="go",
                    trace_dir=trace_dir,
                )
            )

    records = _controller_records(caplog)
    assert len(records) == 1
    line = records[0]
    assert line["outcome"] == "error"
    assert line["agent"] == "researcher"
    assert line["stage"] == "research"
    assert line["run_id"] == "run-err"
    # a failed call writes no trace record
    assert not trace_dir.exists()

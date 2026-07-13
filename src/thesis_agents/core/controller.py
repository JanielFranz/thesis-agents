"""The deterministic controller — instrumented ``run_agent()`` + state machines.

This module owns **all** routing in code (architecture.md §2). It is built in
two layers:

- The observability seam every stage routes through: a ``run_id`` factory and an
  instrumented :func:`run_agent` that wraps the feature-2
  :meth:`OpenRouterClient.run_stage` for a single agent/stage, emitting exactly
  one structured log line per call and, when a trace directory is provided,
  appending one full JSON record (untruncated prompt and output) to a per-run
  JSONL transcript.
- The two deterministic workflows :func:`create_mode` (Researcher → Writer
  outline → Writer draft → Reviewer↔Writer → Judge↔Writer → render) and
  :func:`review_mode` (Reviewer → Judge → assemble report → render). Both call
  :func:`new_run_id` **once** and thread the resulting ``run_id`` through every
  :func:`run_agent` call so their log lines and their shared
  ``<trace_dir>/<run_id>.jsonl`` transcript correlate.

Both workflows run **unattended** — there are no human checkpoints
(architecture.md §6.2). Loop bounds are integer counters checked here in code
(§6.1); a final Judge rejection after the cap neither loops forever nor prompts
a human — the run completes and records the unapproved verdict alongside the
rendered output. The controller **never routes on unvalidated free text** (§6.3):
Reviewer/Judge output is parsed into its JSON object and validated against its
Pydantic schema (retried on failure), and a Judge verdict is only an approval if
it passes :func:`verify_verdict_quotes` plus the recomputed all-thresholds gate
(§6.4/§7) — the model's own ``approved`` field is never trusted.

Layering (architecture.md §4): ``core`` may import ``agents``, ``adapters``,
``config``, ``core`` siblings and ``schemas`` only — never ``entrypoints``.
Externals (the model client) are **injected**, so this module is unit-testable
with no network.

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

from pydantic import BaseModel, ValidationError

from config import AppConfig
from thesis_agents.adapters.formats import render_to_format
from thesis_agents.adapters.openrouter import OpenRouterClient, StageResult
from thesis_agents.agents import AgentDefinition, build_agents
from thesis_agents.core import rubric
from thesis_agents.core.verify import verify_verdict_quotes
from thesis_agents.schemas.models import DocSpec, Review, Verdict

logger = logging.getLogger(__name__)

#: Log/trace event name for a single instrumented agent stage.
RUN_AGENT_EVENT = "run_agent"

#: How many extra times a structured (Reviewer/Judge) stage is re-run when its
#: output cannot be parsed/validated, before the controller fails safe
#: (architecture.md §6.3). Total attempts = ``DEFAULT_MAX_PARSE_RETRIES + 1``.
DEFAULT_MAX_PARSE_RETRIES = 2


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


# --- Typed workflow results (conventions.md §4) ---------------------------


@dataclass(frozen=True, slots=True)
class CreateResult:
    """Typed result of a :func:`create_mode` run — never a raw path/dict.

    ``approved`` is the code-recomputed, quote-verified verdict result (never the
    model's self-report); when it is ``False`` the run still completed and
    shipped the draft (architecture.md §6.2), and ``verdict`` records why.
    ``review_passes`` / ``judge_passes`` expose the loop-cap counters for audit.
    """

    run_id: str
    output_path: Path
    approved: bool
    verdict: Verdict
    review: Review | None
    review_passes: int
    judge_passes: int


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """Typed result of a :func:`review_mode` run — the report path + verdict."""

    run_id: str
    output_path: Path
    approved: bool
    review: Review
    verdict: Verdict


# --- Structured-output parsing (architecture.md §6.3) ---------------------


def _extract_json_object(text: str) -> dict[str, object]:
    """Extract the first ``{...}`` JSON object from an agent's text output.

    Agents are prompted to return a single JSON object (optionally fenced in a
    ```json block); this slices from the first ``{`` to the last ``}`` so
    incidental prose or code fences around the object are tolerated. Raises
    :class:`ValueError` (which includes :class:`json.JSONDecodeError`) when no
    parseable object is present.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in agent output.")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Agent output JSON is not an object.")
    return parsed


async def _run_structured[StructuredT: BaseModel](
    client: OpenRouterClient,
    *,
    agent: AgentDefinition,
    stage: str,
    run_id: str,
    prompt: str,
    schema: type[StructuredT],
    trace_dir: Path | None,
    max_parse_retries: int = DEFAULT_MAX_PARSE_RETRIES,
) -> StructuredT | None:
    """Run a structured stage and validate its output against ``schema``.

    The controller never routes on unvalidated free text (architecture.md §6.3):
    the agent's output is parsed into its JSON object and validated against the
    Pydantic ``schema``. On a parse/validation failure the stage is re-run up to
    ``max_parse_retries`` extra times; if every attempt fails the function
    returns ``None`` so the caller can fail safe (treat as not-approved), rather
    than acting on garbage.
    """
    for attempt in range(1, max_parse_retries + 2):
        run_result = await run_agent(
            client,
            agent=agent,
            stage=stage,
            run_id=run_id,
            prompt=prompt,
            trace_dir=trace_dir,
        )
        try:
            payload = _extract_json_object(run_result.result.output)
            return schema.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "structured_parse_retry",
                        "stage": stage,
                        "run_id": run_id,
                        "schema": schema.__name__,
                        "attempt": attempt,
                        "error": type(exc).__name__,
                    }
                )
            )
    logger.warning(
        json.dumps(
            {
                "event": "structured_parse_failed",
                "stage": stage,
                "run_id": run_id,
                "schema": schema.__name__,
            }
        )
    )
    return None


# --- Prompt assembly (agent role lives in prompts/; context is supplied here)


def _spec_block(spec: DocSpec) -> str:
    return "## Document specification\n\n" + spec.model_dump_json(indent=2)


def _research_prompt(spec: DocSpec) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "Gather grounded material for this thesis chapter from the source-of-truth "
        "and the sources folder. Return organized research notes with the exact "
        "citation metadata for every source you will rely on. Do not invent sources."
    )


def _outline_prompt(spec: DocSpec, research_notes: str) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "## Research notes\n\n"
        f"{research_notes}\n\n"
        "Produce a detailed outline (headings and sub-points) for the chapter, "
        "faithful to the spec requirements and grounded in the research notes."
    )


def _draft_prompt(spec: DocSpec, outline: str) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "## Approved outline\n\n"
        f"{outline}\n\n"
        "Write the full chapter draft in Markdown following this outline. Ground "
        "every claim in the researched sources and include an APA reference list."
    )


def _review_prompt(spec: DocSpec, draft: str) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "## Draft to review\n\n"
        f"{draft}\n\n"
        "Review this draft and return your structured {approved, feedback} JSON."
    )


def _writer_revision_prompt(spec: DocSpec, draft: str, feedback: str) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "## Current draft\n\n"
        f"{draft}\n\n"
        "## Feedback to address\n\n"
        f"{feedback}\n\n"
        "Revise the draft to fix every listed defect. Return the full revised "
        "Markdown draft."
    )


def _judge_prompt(spec: DocSpec, draft: str) -> str:
    return (
        f"{_spec_block(spec)}\n\n"
        "## Rubric\n\n"
        f"{rubric.rubric_to_text()}\n\n"
        "## Draft to grade\n\n"
        f"{draft}\n\n"
        "Score every rubric criterion and return your structured Verdict JSON. "
        "Each quotedJustification must be copied verbatim from the draft above."
    )


def _review_report(spec: DocSpec, review: Review, verdict: Verdict) -> str:
    """Assemble the Markdown review report from the Review + verified Verdict."""
    lines = [
        f"# Review report: {spec.title}",
        "",
        f"**Overall verdict:** {'APPROVED' if verdict.approved else 'NOT APPROVED'}",
        "",
        "## Reviewer feedback",
        "",
        review.feedback or "(no feedback provided)",
        "",
        "## Rubric scores",
        "",
    ]
    if verdict.perCriterionScores:
        for score in verdict.perCriterionScores:
            lines.append(
                f"- **{score.criterionId}**: {score.score}/{rubric.MAX_SCORE}"
                f" — {score.comment}"
            )
    else:
        lines.append("- (no per-criterion scores recorded)")
    lines += ["", "## Reasons", ""]
    for reason in verdict.reasons or ["(none)"]:
        lines.append(f"- {reason}")
    return "\n".join(lines)


def _unparsed_review() -> Review:
    """Fail-safe Review when the Reviewer output could not be validated."""
    return Review(
        approved=False,
        feedback="Reviewer output could not be parsed; treating as not approved.",
    )


def _unparsed_verdict() -> Verdict:
    """Fail-safe Verdict when the Judge output could not be validated."""
    return Verdict(
        approved=False,
        perCriterionScores=[],
        reasons=["Judge output could not be parsed; treating as not approved."],
    )


# --- The two deterministic workflows (architecture.md §2) -----------------


async def create_mode(
    spec: DocSpec,
    client: OpenRouterClient,
    config: AppConfig,
    *,
    agents: dict[str, AgentDefinition] | None = None,
) -> CreateResult:
    """Generate a chapter end-to-end, unattended (architecture.md §2.1).

    Routing is entirely in code here. One ``run_id`` (via :func:`new_run_id`) is
    threaded through every :func:`run_agent` call. The Reviewer↔Writer and
    Judge↔Writer loops are bounded by the integer counters
    ``config.max_review_passes`` / ``config.max_judge_retries`` (§6.1); a Judge
    rejection after the cap does not loop or prompt a human — the run renders the
    draft and returns a :class:`CreateResult` recording the unapproved verdict
    (§6.2). The Judge verdict is only an approval after
    :func:`verify_verdict_quotes` and the recomputed thresholds (§6.4/§7).
    """
    if agents is None:
        agents = build_agents(config, client)
    run_id = new_run_id()
    trace_dir = config.trace_dir

    research = await run_agent(
        client,
        agent=agents["researcher"],
        stage="researcher",
        run_id=run_id,
        prompt=_research_prompt(spec),
        trace_dir=trace_dir,
    )
    outline = await run_agent(
        client,
        agent=agents["writer"],
        stage="writer_outline",
        run_id=run_id,
        prompt=_outline_prompt(spec, research.result.output),
        trace_dir=trace_dir,
    )
    draft_run = await run_agent(
        client,
        agent=agents["writer"],
        stage="writer_draft",
        run_id=run_id,
        prompt=_draft_prompt(spec, outline.result.output),
        trace_dir=trace_dir,
    )
    draft = draft_run.result.output

    # Reviewer <-> Writer loop, capped at MAX_REVIEW_PASSES (integer counter).
    review: Review | None = None
    review_passes = 0
    while review_passes < config.max_review_passes:
        review_passes += 1
        review = await _run_structured(
            client,
            agent=agents["reviewer"],
            stage="reviewer",
            run_id=run_id,
            prompt=_review_prompt(spec, draft),
            schema=Review,
            trace_dir=trace_dir,
        )
        if review is None:
            review = _unparsed_review()
        if review.approved or review_passes >= config.max_review_passes:
            break
        revised = await run_agent(
            client,
            agent=agents["writer"],
            stage="writer_revision",
            run_id=run_id,
            prompt=_writer_revision_prompt(spec, draft, review.feedback),
            trace_dir=trace_dir,
        )
        draft = revised.result.output

    # Judge <-> Writer loop, capped at MAX_JUDGE_RETRIES (integer counter).
    verdict = _unparsed_verdict()
    judge_passes = 0
    while judge_passes < config.max_judge_retries:
        judge_passes += 1
        raw_verdict = await _run_structured(
            client,
            agent=agents["judge"],
            stage="judge",
            run_id=run_id,
            prompt=_judge_prompt(spec, draft),
            schema=Verdict,
            trace_dir=trace_dir,
        )
        # Route on the code-verified verdict, never the model's self-report.
        verdict = (
            verify_verdict_quotes(raw_verdict, draft)
            if raw_verdict is not None
            else _unparsed_verdict()
        )
        if verdict.approved or judge_passes >= config.max_judge_retries:
            break
        fixed = await run_agent(
            client,
            agent=agents["writer"],
            stage="writer_revision",
            run_id=run_id,
            prompt=_writer_revision_prompt(spec, draft, "\n".join(verdict.reasons)),
            trace_dir=trace_dir,
        )
        draft = fixed.result.output

    if not verdict.approved:
        logger.warning(
            json.dumps(
                {
                    "event": "create_shipped_unapproved",
                    "run_id": run_id,
                    "review_passes": review_passes,
                    "judge_passes": judge_passes,
                    "reasons": verdict.reasons,
                }
            )
        )

    output_path = render_to_format(draft, spec, config.output_dir)
    logger.info(
        json.dumps(
            {
                "event": "create_complete",
                "run_id": run_id,
                "approved": verdict.approved,
                "output_path": str(output_path),
            }
        )
    )
    return CreateResult(
        run_id=run_id,
        output_path=output_path,
        approved=verdict.approved,
        verdict=verdict,
        review=review,
        review_passes=review_passes,
        judge_passes=judge_passes,
    )


async def review_mode(
    document: str,
    spec: DocSpec,
    client: OpenRouterClient,
    config: AppConfig,
    *,
    document_name: str | None = None,
    agents: dict[str, AgentDefinition] | None = None,
) -> ReviewResult:
    """Grade an existing document and render a review report (architecture §2.2).

    Reviewer (structured critique) → Judge (verdict, quotes verified against
    ``document``) → assemble a Markdown report → render. There is **no Writer and
    no revision loop** — the human owns the document; the pipeline only assesses
    it. One ``run_id`` is threaded through both stages.
    """
    if agents is None:
        agents = build_agents(config, client)
    run_id = new_run_id()
    trace_dir = config.trace_dir

    review = await _run_structured(
        client,
        agent=agents["reviewer"],
        stage="reviewer",
        run_id=run_id,
        prompt=_review_prompt(spec, document),
        schema=Review,
        trace_dir=trace_dir,
    )
    if review is None:
        review = _unparsed_review()

    raw_verdict = await _run_structured(
        client,
        agent=agents["judge"],
        stage="judge",
        run_id=run_id,
        prompt=_judge_prompt(spec, document),
        schema=Verdict,
        trace_dir=trace_dir,
    )
    verdict = (
        verify_verdict_quotes(raw_verdict, document)
        if raw_verdict is not None
        else _unparsed_verdict()
    )

    report = _review_report(spec, review, verdict)
    name = document_name if document_name is not None else spec.title
    output_path = render_to_format(
        report, spec, config.output_dir, name_hint=f"review-report-{name}"
    )
    logger.info(
        json.dumps(
            {
                "event": "review_complete",
                "run_id": run_id,
                "approved": verdict.approved,
                "output_path": str(output_path),
            }
        )
    )
    return ReviewResult(
        run_id=run_id,
        output_path=output_path,
        approved=verdict.approved,
        review=review,
        verdict=verdict,
    )


__all__ = [
    "DEFAULT_MAX_PARSE_RETRIES",
    "RUN_AGENT_EVENT",
    "AgentRunResult",
    "CreateResult",
    "ReviewResult",
    "create_mode",
    "new_run_id",
    "review_mode",
    "run_agent",
]

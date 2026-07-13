"""Unit tests for the code-side verdict gate (feature 7, architecture §6.4/§7).

Pure in-memory checks: no network, no filesystem, no env. Every test asserts the
concrete recomputed ``approved`` and, where relevant, that a human-readable
voiding reason was appended.
"""

from __future__ import annotations

from thesis_agents.core import rubric
from thesis_agents.core.verify import MIN_QUOTE_CHARS, verify_verdict_quotes
from thesis_agents.schemas.models import CriterionScore, Verdict

# A draft long enough that each quote below appears verbatim within it.
DRAFT = (
    "This chapter grounds every claim in the provided sources without fabrication. "
    "The reference list follows APA 7th edition with full in-text parity. "
    "The scope stays faithful to the source-of-truth and the DocSpec requirements. "
    "The structure follows the approved outline with coherent headings. "
    "Each argument is developed with evidence rather than merely asserted. "
    "The style keeps a formal academic register with consistent citations."
)

_QUOTES = {
    "grounding": "grounds every claim in the provided sources without fabrication",
    "references": "reference list follows APA 7th edition with full in-text parity",
    "scope": "scope stays faithful to the source-of-truth and the DocSpec requirements",
    "structure": "structure follows the approved outline with coherent headings",
    "argument": "argument is developed with evidence rather than merely asserted",
    "style": "style keeps a formal academic register with consistent citations",
}


def _passing_scores() -> list[CriterionScore]:
    thresholds = rubric.criterion_thresholds()
    return [
        CriterionScore(
            criterionId=cid,
            score=thresholds[cid],
            quotedJustification=_QUOTES[cid],
            comment=f"ok: {cid}",
        )
        for cid in rubric.criterion_ids()
    ]


def _verdict(scores: list[CriterionScore], *, approved: bool = True) -> Verdict:
    return Verdict(approved=approved, perCriterionScores=scores, reasons=[])


def test_valid_verdict_stays_approved_with_no_added_reason() -> None:
    result = verify_verdict_quotes(_verdict(_passing_scores()), DRAFT)
    assert result.approved is True
    assert result.reasons == []


def test_fabricated_quote_voids_verdict() -> None:
    scores = _passing_scores()
    scores[0] = CriterionScore(
        criterionId="grounding",
        score=5,
        quotedJustification="this exact sentence never appears in the draft text",
        comment="fabricated",
    )
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is False
    assert any("grounding" in r and "verbatim" in r for r in result.reasons)


def test_missing_criterion_voids_verdict() -> None:
    scores = [s for s in _passing_scores() if s.criterionId != "style"]
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is False
    assert any("not scored" in r and "style" in r for r in result.reasons)


def test_unknown_criterion_voids_verdict() -> None:
    scores = _passing_scores()
    scores.append(
        CriterionScore(
            criterionId="creativity",
            score=5,
            quotedJustification="grounds every claim in the provided sources without",
            comment="not a rubric criterion",
        )
    )
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is False
    assert any("unknown criterionId" in r and "creativity" in r for r in result.reasons)


def test_duplicate_criterion_voids_verdict() -> None:
    scores = _passing_scores()
    scores.append(scores[0])  # duplicate "grounding"
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is False
    assert any("duplicate criterionId" in r for r in result.reasons)


def test_single_subthreshold_score_flips_approved_via_recompute() -> None:
    scores = _passing_scores()
    # grounding threshold is 4; score 3 must fail even though model said approved.
    scores[0] = CriterionScore(
        criterionId="grounding",
        score=3,
        quotedJustification=_QUOTES["grounding"],
        comment="below threshold",
    )
    # Model self-reports approved=True; the recompute must override it.
    result = verify_verdict_quotes(_verdict(scores, approved=True), DRAFT)
    assert result.approved is False
    assert any("thresholds failed" in r and "grounding" in r for r in result.reasons)


def test_too_short_quote_voids_verdict() -> None:
    scores = _passing_scores()
    scores[0] = CriterionScore(
        criterionId="grounding",
        score=5,
        quotedJustification="x" * (MIN_QUOTE_CHARS - 1),
        comment="too short",
    )
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is False
    assert any("too short" in r and "grounding" in r for r in result.reasons)


def test_quote_with_line_break_still_matches_after_normalization() -> None:
    scores = _passing_scores()
    # Same words as the draft, but wrapped across lines with extra spaces.
    scores[0] = CriterionScore(
        criterionId="grounding",
        score=4,
        quotedJustification=(
            "grounds every claim\nin the   provided sources\nwithout fabrication"
        ),
        comment="reformatted whitespace",
    )
    result = verify_verdict_quotes(_verdict(scores), DRAFT)
    assert result.approved is True
    assert result.reasons == []


def test_original_reasons_are_preserved() -> None:
    verdict = Verdict(
        approved=False,
        perCriterionScores=_passing_scores(),
        reasons=["pre-existing note from the judge"],
    )
    result = verify_verdict_quotes(verdict, DRAFT)
    assert result.approved is True
    assert result.reasons == ["pre-existing note from the judge"]


def test_input_verdict_is_not_mutated() -> None:
    verdict = _verdict(_passing_scores())
    before = list(verdict.reasons)
    verify_verdict_quotes(verdict, "unrelated draft text with nothing matching")
    assert verdict.reasons == before
    assert verdict.approved is True

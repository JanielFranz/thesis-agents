"""Code-side verification of the Judge's rubric verdict (architecture §6.4, §7).

This is the *deterministic gate* that does not trust the model. Since create mode
runs unattended (no human final-draft checkpoint), this module plus the fixed
rubric are the primary defense against a false APPROVE. Every check below is
enforced in code, not by prompt or debate.

``verify_verdict_quotes(verdict, draft)`` voids a verdict — forcing
``approved = False`` and appending a human-readable reason — whenever any of:

1. **Criterion coverage** — every rubric criterion (``rubric.criterion_ids()``)
   must be scored exactly once, and no score may carry an unknown ``criterionId``.
   A missing criterion, an unknown/extra id, or a duplicate id voids the verdict.
2. **Quote minimum length** — each ``CriterionScore.quotedJustification`` must be
   at least :data:`MIN_QUOTE_CHARS` characters (after ``strip``). An empty or
   too-short quote voids the verdict.
3. **Verbatim quote presence** — each ``quotedJustification`` must occur verbatim
   in ``draft`` *after normalization* (see :func:`_normalize`). A quote absent
   from the normalized draft voids the verdict.

Independently, the approval is **recomputed in code** as
``all(score >= threshold)`` from ``perCriterionScores`` against the rubric
(``rubric.is_passing``); the model's own ``verdict.approved`` is never trusted.

A verdict counts as an approval **only if it passes BOTH** the recomputed
thresholds **AND** all of checks 1–3.

Purity (architecture §4): no env, no I/O, no network, no model calls. ``draft``
is passed in as a string by the caller (the future controller). The rubric's
criterion ids and thresholds are **imported**, never duplicated here.

Return type: :func:`verify_verdict_quotes` returns the **adjusted**
:class:`~thesis_agents.schemas.models.Verdict` — a new, Pydantic-validated
``Verdict`` copy whose ``approved`` is the code-recomputed value and whose
``reasons`` are the original reasons plus any appended voiding reasons. Returning
the validated schema model (rather than a bare bool/str) satisfies conventions §4
and lets the controller route on a trusted, typed object.
"""

from __future__ import annotations

from thesis_agents.core import rubric
from thesis_agents.schemas.models import Verdict

#: Minimum characters a ``quotedJustification`` must have (after ``strip``) to be
#: accepted as evidence. Guards against empty or trivially short "quotes" that
#: could not meaningfully anchor a score to the draft.
MIN_QUOTE_CHARS = 12


def _normalize(text: str) -> str:
    """Normalize text for verbatim comparison.

    Rule (documented + tested): collapse every run of whitespace — spaces, tabs,
    newlines — to a single space, strip leading/trailing whitespace, and
    case-fold. This lets a quote that a model re-wrapped across lines (or with
    incidental double spaces or differing case) still match the draft, while
    keeping the comparison anchored to the draft's actual words in order.
    """
    return " ".join(text.split()).casefold()


def verify_verdict_quotes(verdict: Verdict, draft: str) -> Verdict:
    """Verify and, if needed, void a Judge :class:`Verdict` against ``draft``.

    Returns a new :class:`Verdict` whose ``approved`` is recomputed in code and
    whose ``reasons`` include any appended voiding reasons. The input ``verdict``
    is not mutated.
    """
    reasons = list(verdict.reasons)
    expected_ids = list(rubric.criterion_ids())
    scored_ids = [score.criterionId for score in verdict.perCriterionScores]

    coverage_ok = True

    # Check 1a — unknown / extra criterion ids.
    unknown = [cid for cid in scored_ids if cid not in expected_ids]
    if unknown:
        coverage_ok = False
        reasons.append(
            "Verdict voided: unknown criterionId(s) not in the rubric: "
            + ", ".join(sorted(set(unknown)))
        )

    # Check 1b — duplicate criterion ids (a criterion scored more than once).
    seen: set[str] = set()
    duplicates: list[str] = []
    for cid in scored_ids:
        if cid in seen and cid not in duplicates:
            duplicates.append(cid)
        seen.add(cid)
    if duplicates:
        coverage_ok = False
        reasons.append(
            "Verdict voided: duplicate criterionId(s) scored more than once: "
            + ", ".join(sorted(duplicates))
        )

    # Check 1c — missing rubric criteria.
    missing = [cid for cid in expected_ids if cid not in scored_ids]
    if missing:
        coverage_ok = False
        reasons.append(
            "Verdict voided: rubric criterion(s) not scored: " + ", ".join(missing)
        )

    # Checks 2 & 3 — per-score quote length and verbatim presence.
    normalized_draft = _normalize(draft)
    quotes_ok = True
    for score in verdict.perCriterionScores:
        quote = score.quotedJustification.strip()
        if len(quote) < MIN_QUOTE_CHARS:
            quotes_ok = False
            reasons.append(
                f"Verdict voided: quote for criterion '{score.criterionId}' is "
                f"too short (< {MIN_QUOTE_CHARS} chars)."
            )
            continue
        if _normalize(score.quotedJustification) not in normalized_draft:
            quotes_ok = False
            reasons.append(
                f"Verdict voided: quote for criterion '{score.criterionId}' does "
                "not occur verbatim in the draft."
            )

    # Check 4 — recompute approval from the per-criterion scores (never trust the
    # model's self-reported verdict.approved). Only well-formed scores feed the
    # threshold check; is_passing() fails safe when a criterion is missing.
    scores = {
        score.criterionId: score.score
        for score in verdict.perCriterionScores
        if score.criterionId in expected_ids
    }
    thresholds_ok = rubric.is_passing(scores)
    if not thresholds_ok:
        below = [
            cid
            for cid, threshold in rubric.criterion_thresholds().items()
            if scores.get(cid, rubric.MIN_SCORE) < threshold
        ]
        reasons.append(
            "Verdict not approved: recomputed thresholds failed for criterion(s): "
            + ", ".join(below)
        )

    approved = coverage_ok and quotes_ok and thresholds_ok

    return Verdict(
        approved=approved,
        perCriterionScores=list(verdict.perCriterionScores),
        reasons=reasons,
    )

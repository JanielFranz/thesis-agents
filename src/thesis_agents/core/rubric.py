"""The fixed, compiled-in grading rubric (architecture.md §7).

This module is pure data plus text formatting — no I/O, no env, no model calls,
and no dependency on ``schemas``. The Judge scores a draft against these six
criteria, and feature 7 (``core/verify.py``) cross-checks the criterion ids and
thresholds declared here.

Passing rule (documented, load-bearing): a draft is **approved iff every
criterion's score is >= its threshold**. Scores range over ``MIN_SCORE..MAX_SCORE``
(0..5). Nothing here trusts the model's self-reported ``approved`` field —
``verify`` recomputes approval from these thresholds in code.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_SCORE = 0
MAX_SCORE = 5


@dataclass(frozen=True, slots=True)
class Criterion:
    """One immutable rubric criterion: its id, description, and pass threshold."""

    id: str
    description: str
    threshold: int


# The six-criterion rubric, in canonical order (architecture.md §7). Declared as
# a tuple of frozen dataclasses so it cannot be mutated at runtime. The ids match
# the `criterionId` values in prompts/judge.md exactly.
RUBRIC: tuple[Criterion, ...] = (
    Criterion(
        id="grounding",
        description=(
            "Grounding in sources: no fabricated or contradicted claims; every "
            "assertion is supported by the provided sources."
        ),
        threshold=4,
    ),
    Criterion(
        id="references",
        description=(
            "Complete, real APA 7th reference list with in-text citation to "
            "reference-entry parity; no invented or missing references."
        ),
        threshold=4,
    ),
    Criterion(
        id="scope",
        description=(
            "Scope fidelity to the source-of-truth and satisfaction of all "
            "DocSpec requirements."
        ),
        threshold=3,
    ),
    Criterion(
        id="structure",
        description=(
            "Follows the approved outline with coherent headings and transitions."
        ),
        threshold=3,
    ),
    Criterion(
        id="argument",
        description=("Claims are developed with evidence, not merely asserted."),
        threshold=3,
    ),
    Criterion(
        id="style",
        description="Formal academic register with consistent citations.",
        threshold=3,
    ),
)


def criterion_ids() -> tuple[str, ...]:
    """Return the six criterion ids in canonical rubric order."""
    return tuple(criterion.id for criterion in RUBRIC)


def criterion_thresholds() -> dict[str, int]:
    """Return an ``{id: threshold}`` mapping for parity/threshold checks."""
    return {criterion.id: criterion.threshold for criterion in RUBRIC}


def is_passing(scores: dict[str, int]) -> bool:
    """Return ``True`` iff every rubric criterion is scored at or above its
    threshold.

    ``scores`` maps criterion id -> score. A missing criterion, or any score
    below its threshold, fails. Unknown ids in ``scores`` are ignored (the
    verdict-voiding check for unknown/missing ids lives in ``verify``).
    """
    thresholds = criterion_thresholds()
    return all(
        criterion_id in scores and scores[criterion_id] >= threshold
        for criterion_id, threshold in thresholds.items()
    )


def rubric_to_text() -> str:
    """Render the rubric as prompt-embeddable text.

    Lists every criterion's id, description, and threshold, plus the passing
    rule, so the Judge prompt can reference the exact ids and thresholds.
    """
    lines = [
        f"Score each criterion from {MIN_SCORE} to {MAX_SCORE}. A criterion "
        "passes only if its score is at or above its threshold. The draft is "
        "approved iff every criterion passes.",
        "",
    ]
    for criterion in RUBRIC:
        lines.append(
            f"- {criterion.id} (pass >= {criterion.threshold}): {criterion.description}"
        )
    return "\n".join(lines)

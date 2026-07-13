"""Unit tests for the fixed rubric (feature 6, architecture §7).

Pure data: no network, no filesystem, no env. Asserts the exact six criterion
ids and thresholds, that ``rubric_to_text()`` mentions each criterion, and that
the passing-rule helper behaves on both branches.
"""

from __future__ import annotations

from thesis_agents.core.rubric import (
    MAX_SCORE,
    MIN_SCORE,
    RUBRIC,
    criterion_ids,
    criterion_thresholds,
    is_passing,
    rubric_to_text,
)

EXPECTED_THRESHOLDS = {
    "grounding": 4,
    "references": 4,
    "scope": 3,
    "structure": 3,
    "argument": 3,
    "style": 3,
}


def test_rubric_has_exactly_six_expected_ids() -> None:
    assert len(RUBRIC) == 6
    assert set(criterion_ids()) == set(EXPECTED_THRESHOLDS)
    # canonical order is preserved
    assert list(criterion_ids()) == list(EXPECTED_THRESHOLDS)


def test_rubric_thresholds_match_spec() -> None:
    assert criterion_thresholds() == EXPECTED_THRESHOLDS


def test_score_range_constants() -> None:
    assert MIN_SCORE == 0
    assert MAX_SCORE == 5


def test_rubric_to_text_mentions_every_criterion() -> None:
    text = rubric_to_text()
    assert text.strip()
    for criterion_id, threshold in EXPECTED_THRESHOLDS.items():
        assert criterion_id in text
        assert str(threshold) in text


def test_is_passing_true_when_all_scores_meet_threshold() -> None:
    scores = {cid: t for cid, t in EXPECTED_THRESHOLDS.items()}
    assert is_passing(scores) is True


def test_is_passing_false_when_one_score_below_threshold() -> None:
    scores = {cid: t for cid, t in EXPECTED_THRESHOLDS.items()}
    scores["grounding"] = 3  # below its threshold of 4
    assert is_passing(scores) is False


def test_is_passing_false_when_criterion_missing() -> None:
    scores = {cid: t for cid, t in EXPECTED_THRESHOLDS.items()}
    del scores["style"]
    assert is_passing(scores) is False


def test_rubric_is_immutable() -> None:
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        RUBRIC[0].threshold = 0  # type: ignore[misc]

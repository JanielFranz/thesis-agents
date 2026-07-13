"""Unit tests for the Pydantic contracts (feature 5, architecture §8).

These assert concrete parsed field values and that invalid input raises
``pydantic.ValidationError`` — never merely "does not throw". No network, no
filesystem, no env: pure validation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from thesis_agents.schemas import (
    CriterionScore,
    DocSpec,
    Review,
    Verdict,
)


def _valid_docspec_dict() -> dict:
    return {
        "title": "Foundations of Multi-Agent Systems",
        "docType": "thesis-chapter",
        "format": "docx",
        "language": "en",
        "chapter": {"number": 3, "title": "Related Work"},
        "audience": "thesis committee",
        "targetWords": 4500,
        "citationStyle": "APA 7th",
        "requirements": ["cite at least 10 sources", "include a summary table"],
        "notes": "Focus on grounding.",
    }


def _valid_verdict_dict() -> dict:
    return {
        "approved": True,
        "perCriterionScores": [
            {
                "criterionId": "grounding",
                "score": 5,
                "quotedJustification": "every claim maps to a source",
                "comment": "well grounded",
            },
            {
                "criterionId": "style",
                "score": 4,
                "quotedJustification": "formal academic register throughout",
                "comment": "consistent",
            },
        ],
        "reasons": ["all criteria meet threshold"],
    }


def test_docspec_parses_expected_field_values() -> None:
    spec = DocSpec.model_validate(_valid_docspec_dict())

    assert spec.title == "Foundations of Multi-Agent Systems"
    assert spec.docType == "thesis-chapter"
    assert spec.format == "docx"
    assert spec.language == "en"
    assert spec.chapter.number == 3
    assert spec.chapter.title == "Related Work"
    assert spec.audience == "thesis committee"
    assert spec.targetWords == 4500
    assert spec.citationStyle == "APA 7th"
    assert spec.requirements == ["cite at least 10 sources", "include a summary table"]
    assert spec.notes == "Focus on grounding."


def test_verdict_parses_nested_scores_and_lists() -> None:
    verdict = Verdict.model_validate(_valid_verdict_dict())

    assert verdict.approved is True
    assert verdict.reasons == ["all criteria meet threshold"]
    assert len(verdict.perCriterionScores) == 2
    first = verdict.perCriterionScores[0]
    assert isinstance(first, CriterionScore)
    assert first.criterionId == "grounding"
    assert first.score == 5
    assert first.quotedJustification == "every claim maps to a source"
    assert first.comment == "well grounded"
    assert verdict.perCriterionScores[1].score == 4


def test_review_parses_expected_field_values() -> None:
    review = Review.model_validate({"approved": False, "feedback": "add citations"})

    assert review.approved is False
    assert review.feedback == "add citations"


def test_docspec_rejects_bad_format_enum() -> None:
    bad = _valid_docspec_dict()
    bad["format"] = "pdf"

    with pytest.raises(ValidationError):
        DocSpec.model_validate(bad)


def test_docspec_rejects_bad_doctype_enum() -> None:
    bad = _valid_docspec_dict()
    bad["docType"] = "book"

    with pytest.raises(ValidationError):
        DocSpec.model_validate(bad)


def test_docspec_rejects_missing_title() -> None:
    bad = _valid_docspec_dict()
    del bad["title"]

    with pytest.raises(ValidationError):
        DocSpec.model_validate(bad)


def test_docspec_rejects_non_positive_target_words() -> None:
    bad = _valid_docspec_dict()
    bad["targetWords"] = 0

    with pytest.raises(ValidationError):
        DocSpec.model_validate(bad)


def test_chapter_rejects_negative_number() -> None:
    bad = _valid_docspec_dict()
    bad["chapter"] = {"number": -1, "title": "Intro"}

    with pytest.raises(ValidationError):
        DocSpec.model_validate(bad)


@pytest.mark.parametrize("bad_score", [7, -1, 6])
def test_criterion_score_rejects_out_of_range(bad_score: int) -> None:
    with pytest.raises(ValidationError):
        CriterionScore.model_validate(
            {
                "criterionId": "grounding",
                "score": bad_score,
                "quotedJustification": "q",
                "comment": "c",
            }
        )


def test_docspec_json_schema_exposes_property_names() -> None:
    schema = DocSpec.model_json_schema()

    assert isinstance(schema, dict)
    props = schema["properties"]
    for name in (
        "title",
        "docType",
        "format",
        "language",
        "chapter",
        "audience",
        "targetWords",
        "citationStyle",
        "requirements",
        "notes",
    ):
        assert name in props


def test_verdict_json_schema_exposes_property_names() -> None:
    schema = Verdict.model_json_schema()

    assert isinstance(schema, dict)
    for name in ("approved", "perCriterionScores", "reasons"):
        assert name in schema["properties"]


def test_criterion_score_json_schema_exposes_property_names() -> None:
    schema = CriterionScore.model_json_schema()

    for name in ("criterionId", "score", "quotedJustification", "comment"):
        assert name in schema["properties"]

"""Pydantic models crossing layer boundaries (architecture.md §8).

These are the input/output contracts shared by the CLI, controller and agents:

- :class:`DocSpec` — the input contract validated at the CLI boundary.
- :class:`Review` — the Reviewer's structured verdict.
- :class:`Verdict` / :class:`CriterionScore` — the Judge's structured rubric
  verdict, whose quotes are machine-verified downstream.

Per architecture §4 these models carry **no behavior beyond validation**: they
declare fields, enforce enums/types/constraints, and expose their JSON schema
via Pydantic's built-in :meth:`~pydantic.BaseModel.model_json_schema`. They read
no environment and do no I/O. Field names are kept **verbatim** from §8 (the
camelCase names ``docType``, ``targetWords``, ``perCriterionScores``,
``quotedJustification``, ``criterionId`` are the wire contract downstream
features and the agent prompts agree on), so no aliasing is used.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: The only supported document type in this build (architecture §8).
DocType = Literal["thesis-chapter"]

#: Output formats: ``docx`` is implemented; ``pptx`` is a documented stub.
DocFormat = Literal["docx", "pptx"]

#: Rubric score bounds (architecture §7: each criterion scored 0..5).
MIN_SCORE = 0
MAX_SCORE = 5


class Chapter(BaseModel):
    """The chapter a :class:`DocSpec` targets (architecture §8: ``chapter``)."""

    number: int = Field(ge=0)
    title: str


class DocSpec(BaseModel):
    """The pipeline's input contract (architecture §8).

    Validated at the CLI boundary before any model call (conventions §6).
    """

    title: str
    docType: DocType
    format: DocFormat
    language: str
    chapter: Chapter
    audience: str
    targetWords: int = Field(gt=0)
    citationStyle: str
    requirements: list[str]
    notes: str


class CriterionScore(BaseModel):
    """One rubric criterion's score plus its verbatim justifying quote."""

    criterionId: str
    score: int = Field(ge=MIN_SCORE, le=MAX_SCORE)
    quotedJustification: str
    comment: str


class Review(BaseModel):
    """The Reviewer's structured output (architecture §8)."""

    approved: bool
    feedback: str


class Verdict(BaseModel):
    """The Judge's structured rubric verdict (architecture §8)."""

    approved: bool
    perCriterionScores: list[CriterionScore]
    reasons: list[str]

"""Pydantic schemas crossing layer boundaries (architecture.md §8).

Re-exports the public models so callers do ``from thesis_agents.schemas import
DocSpec``. Each model's JSON schema is available via its built-in
:meth:`~pydantic.BaseModel.model_json_schema` (architecture §8).
"""

from __future__ import annotations

from thesis_agents.schemas.models import (
    Chapter,
    CriterionScore,
    DocSpec,
    Review,
    Verdict,
)

__all__ = [
    "Chapter",
    "CriterionScore",
    "DocSpec",
    "Review",
    "Verdict",
]

# Implementation Report — Feature 5 `schemas`

Status: `in_progress` (awaiting reviewer; NOT flipped to `done`).
Depends_on: [1] ✓ done.

## Summary

Added the four Pydantic v2 contracts from architecture §8 plus the nested
`Chapter` model, re-exported them from the package, and added `pydantic` via
`uv` with an exact pin. Models carry no behavior beyond validation (§4): no env,
no I/O.

## Dependency added (uv only, exact pin)

- `uv add pydantic==2.13.4` (latest release verified via PyPI at
  implementation time). Landed in `pyproject.toml`
  (`dependencies = [..., "pydantic==2.13.4"]`) and `uv.lock`
  (`name = "pydantic" / version = "2.13.4"`). No hand-editing of the
  dependency list. It is the only new dependency.

## Files touched (within feature 5 `paths`)

- `src/thesis_agents/schemas/models.py` — the models (was absent).
- `src/thesis_agents/schemas/__init__.py` — re-exports (was a stub).
- `tests/unit/test_schemas.py` — unit tests (new).
- `pyproject.toml` + `uv.lock` — pydantic pin via `uv add`.

No deviation from the declared `paths`.

## Models, fields, constraints (field names verbatim from §8)

- `Chapter`: `number: int (>= 0)`, `title: str`.
- `DocSpec`: `title: str`, `docType: Literal["thesis-chapter"]`,
  `format: Literal["docx","pptx"]`, `language: str`, `chapter: Chapter`,
  `audience: str`, `targetWords: int (> 0)`, `citationStyle: str`,
  `requirements: list[str]`, `notes: str`.
- `CriterionScore`: `criterionId: str`, `score: int (0..5)`,
  `quotedJustification: str`, `comment: str`.
- `Review`: `approved: bool`, `feedback: str`.
- `Verdict`: `approved: bool`, `perCriterionScores: list[CriterionScore]`,
  `reasons: list[str]`.

Constraints kept minimal per §8: enums via `Literal`, score bounds `0..5`
(`MIN_SCORE`/`MAX_SCORE` constants), `targetWords > 0`, `chapter.number >= 0`.
No over-constraining beyond what architecture implies.

## §8 field-name preservation / alias decision

The camelCase names (`docType`, `targetWords`, `perCriterionScores`,
`quotedJustification`, `criterionId`) are declared **directly as attribute
names** — no Pydantic `alias` is used. This keeps the wire contract identical
for construction, `.model_dump()`, and `model_json_schema()` (all round-trip on
the same names), so downstream features (verify, controller, cli) and the agent
prompts agree with zero alias bookkeeping.

## JSON schema exposure

Each model exposes its schema through Pydantic v2's built-in
`model_json_schema()` (no custom code). Tests assert the returned dict contains
the expected property names for `DocSpec`, `Verdict`, and `CriterionScore`.

## Verification evidence (pasted output)

1. `uv run ruff check .`
   ```
   All checks passed!
   ```
2. `uv run ruff format --check .`
   ```
   18 files already formatted
   ```
3. `uv run pytest tests -q -m "not integration"`
   ```
   53 passed in 3.18s
   ```
   With `OPENROUTER_API_KEY` unset in the shell (autouse conftest injects a
   dummy, so schemas never read the real secret):
   ```
   $ env | grep -c OPENROUTER_API_KEY   -> 0 (unset)
   $ uv run pytest tests/unit/test_schemas.py -q -m "not integration"
   14 passed in 0.08s
   ```
4. `bash init.sh`
   ```
   [OK]   feature_list.json valid (10 features, 4 done, 1 in progress)
   53 passed in 3.18s
   [OK]   Environment ready. You can start working.
   EXIT=0
   ```

## Notes

- `config.py` remains the only `os.environ` reader; schemas touch no env and no
  filesystem.
- 14 new tests: happy-path DocSpec/Verdict/Review value assertions, error paths
  (bad `format` enum, bad `docType`, missing `title`, non-positive
  `targetWords`, negative `chapter.number`, out-of-range score `7`/`-1`/`6`),
  and JSON-schema property presence.

# Feature 6 — `rubric` — Implementation Report

Status: `in_progress` (awaiting reviewer approval; NOT flipped to `done`).

## Files touched (within `paths`)
- `src/thesis_agents/core/rubric.py` (new)
- `tests/unit/test_rubric.py` (new)

No files outside the feature's `paths` were modified. No new dependency (stdlib
only). Pure data + text — no I/O, no env, no model calls, and no import of
`schemas/models.py`.

## Rubric representation
- `Criterion` = a `@dataclass(frozen=True, slots=True)` with `id: str`,
  `description: str`, `threshold: int` — immutable, cannot be mutated at runtime
  (assignment raises `FrozenInstanceError`, asserted in the tests).
- `RUBRIC: tuple[Criterion, ...]` — module-level constant, canonical order.
- Constants grouped at top: `MIN_SCORE = 0`, `MAX_SCORE = 5`.

### Six ids / thresholds (exactly per architecture §7)
| id | threshold (pass >=) |
|---|---|
| grounding | 4 |
| references | 4 |
| scope | 3 |
| structure | 3 |
| argument | 3 |
| style | 3 |

## Parity / threshold API exposed for feature 7 (`verify`)
- `criterion_ids() -> tuple[str, ...]` — the six ids in canonical order.
- `criterion_thresholds() -> dict[str, int]` — `{id: threshold}` mapping.
- `is_passing(scores: dict[str, int]) -> bool` — `True` iff every rubric
  criterion is present in `scores` and `>=` its threshold (missing criterion or
  any sub-threshold score ⇒ `False`). Unknown ids in `scores` are ignored here
  — the verdict-voiding "unknown/missing criterionId" check is `verify`'s job
  (feature 7, §6.4).
- `RUBRIC` and `Criterion` are exported for direct iteration.
- Documented passing rule (module docstring + `rubric_to_text()` header):
  **approved iff every criterion's score >= its threshold.**

## `rubric_to_text()` output shape
A non-empty multi-line string:
1. a header line stating the 0..5 range and the "approved iff every criterion
   passes" rule, then a blank line;
2. one bullet per criterion: `- <id> (pass >= <threshold>): <description>`.

Contains every id and every threshold value (asserted in tests). Suitable for
embedding in the Judge prompt.

## judge.md id-consistency check
`prompts/judge.md` (feature 3) embeds the rubric table with `criterionId`
values `grounding`, `references`, `scope`, `structure`, `argument`, `style`
and thresholds 4/4/3/3/3/3 — **an exact match** to the ids and thresholds
defined here and to architecture §7. No discrepancy; no reconciliation needed,
and judge.md was not touched (outside feature 6's paths).

## Deviations from `paths`
None.

## Self-verification (pasted output)

1. `uv run ruff check .`
```
All checks passed!
```

2. `uv run ruff format --check .`
```
20 files already formatted
```

3. `uv run pytest tests -q -m "not integration"`
```
61 passed in 3.26s
```
   With `OPENROUTER_API_KEY` unset (`env -u OPENROUTER_API_KEY uv run pytest
   tests/unit/test_rubric.py -q -m "not integration"`):
```
8 passed in 0.01s
```

4. `bash init.sh`
```
[OK]   feature_list.json valid (10 features, 5 done, 1 in progress)
── 4. Running tests ────────────────────────────────────
61 passed in 3.88s
[OK]   Unit tests passed (integration tests excluded; ...)
[OK]   Environment ready. You can start working.
EXIT=0
```

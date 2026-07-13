# Implementation report — Feature 7 `verify`

Status: `in_progress` (awaiting reviewer approval — NOT flipped to `done`).

## Files touched (within `paths` — no deviation)
- `src/thesis_agents/core/verify.py` (new)
- `tests/unit/test_verify.py` (new)
- `progress/current.md` (log/plan only)

No other application code touched. `feature_list.json` status left `in_progress`.

## Signature + return type
```python
def verify_verdict_quotes(verdict: Verdict, draft: str) -> Verdict
```
Chosen return type: the **adjusted `Verdict`** — a new, Pydantic-revalidated
`Verdict` copy whose `approved` holds the code-recomputed value and whose
`reasons` are the original reasons plus any appended voiding reasons. This is a
typed, validated schema model (conventions §4), not a bare bool/str. The input
`verdict` is never mutated (test `test_input_verdict_is_not_mutated`).

## Normalization rule + constant
- `MIN_QUOTE_CHARS = 12` (module constant).
- `_normalize(text)` = `" ".join(text.split()).casefold()`:
  collapse every whitespace run (spaces, tabs, newlines) to a single space,
  strip, and case-fold. Applied to both the draft and each quote before the
  verbatim substring check. Documented in the module docstring and proven by
  `test_quote_with_line_break_still_matches_after_normalization` (a quote wrapped
  across newlines with double spaces still matches).

## The five void conditions (enforced in code, not by debate)
1. **Unknown/extra `criterionId`** — any scored id not in `rubric.criterion_ids()`
   sets `coverage_ok = False` + reason.
2. **Duplicate `criterionId`** — a criterion scored more than once voids.
3. **Missing rubric criterion** — any expected id not scored voids.
4. **Too-short quote** — `len(quotedJustification.strip()) < MIN_QUOTE_CHARS` voids.
5. **Absent verbatim quote** — normalized quote not a substring of the normalized
   draft voids.

## Threshold recompute overriding the model self-report (§7 hardening)
Approval is recomputed as `rubric.is_passing({criterionId: score})` over the
known criteria — the model's `verdict.approved` is ignored entirely. Final:
`approved = coverage_ok and quotes_ok and thresholds_ok`. Test
`test_single_subthreshold_score_flips_approved_via_recompute` feeds
`approved=True` from the model with grounding=3 (threshold 4) and asserts the
result is `approved=False` with a "thresholds failed" reason naming grounding.

## Rubric imported, not duplicated
`from thesis_agents.core import rubric`; uses `criterion_ids()`,
`criterion_thresholds()`, `is_passing()`, `MIN_SCORE`. No criteria or thresholds
are re-listed in `verify.py`.

## Purity
No `os.environ`, no I/O, no network, no model calls. `draft` is an in-memory
string arg. `config.py` remains the only `os.environ` reader.

## Verification output (all commands via uv)

`uv run ruff check .`
```
All checks passed!
```

`uv run ruff format --check .`
```
22 files already formatted
```

`OPENROUTER_API_KEY= uv run pytest tests -q -m "not integration"` (key unset)
```
.......................................................................  [100%]
71 passed in 5.31s
```
(11 of these are the new `test_verify.py` tests; suite passes with the key unset
and no `.env` consulted.)

`bash init.sh`
```
[OK]   feature_list.json valid (10 features, 6 done, 1 in progress)
71 passed in 3.33s
[OK]   Unit tests passed (integration tests excluded; ...)
[OK]   Environment ready. You can start working.
EXIT=0
```

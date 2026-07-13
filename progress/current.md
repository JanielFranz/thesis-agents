# Current Session

> This file is cleared when each session closes and its summary moves to
> `history.md`. While working, **keep it updated in real time**, not at
> the end.

## Feature in progress

- **Feature 6 `rubric`** (status `in_progress`; depends_on: [1] ✓ done).
  Implementer dispatched. Unblocks 7 `verify`. (5 `schemas` done + approved.)

### Plan
- Add `pydantic` via `uv add` with an exact pin (only new dep). ✓ 2.13.4
- Build DocSpec/Chapter/CriterionScore/Review/Verdict in schemas/models.py
  with §8 field names verbatim (no aliases), enums via Literal, score 0..5. ✓
- Re-export public models from schemas/__init__.py. ✓
- Tests: happy-path value asserts + error paths + JSON-schema presence. ✓
- Verify: ruff clean, format clean, pytest green (key unset), init.sh EXIT=0. ✓

Report: progress/impl_schemas.md. Awaiting reviewer; not flipped to `done`.

## Backlog expanded — features 5–10 added (2026-07-13)

Added the six features that make the pipeline runnable end-to-end. `init.sh`:
10 features, 4 done, 0 in progress, deps valid (each dep strictly earlier + no
unknowns). Eligible now: **5 `schemas`** and **6 `rubric`** (both deps=[1] done).

Dependency chain (→ = depends on):
- 5 `schemas`   [1]              — DocSpec/Review/Verdict/CriterionScore + JSON schemas (adds pydantic)
- 6 `rubric`    [1]              — fixed 6-criterion rubric + rubric_to_text()
- 7 `verify`    [5,6]            — verify_verdict_quotes() + recomputed all(score>=threshold)
- 8 `formats`   [5]              — render_to_format switch; prose.py docx (adds python-docx); slides.py stub
- 9 `controller`[3,4,5,6,7,8]    — create_mode/review_mode state machines; unattended; loop caps
- 10 `cli`      [5,9]            — --spec/--mode/--input, .env load, `python -m thesis_agents`

Suggested build order: 5 → 6 → 7 → 8 → 9 → 10 (5 & 6 could run first in either
order). Awaiting user go-ahead to start dispatching, or to sanity-check the
acceptance criteria first.

## Carried-forward risks / housekeeping (non-blocking)

- Model slug existence (`qwen/qwen3.7-plus`, `deepseek-v4-*`) NOT independently
  confirmed on OpenRouter — re-verify before any integration run (config-driven;
  one-line env override fixes a wrong slug).
- Dev deps `pytest`/`ruff` use `>=`, not exact pins — future tidy.
- Stray root `main.py` (PyCharm sample) ruff-excluded rather than deleted.
- `_SECRET_MARKERS` guardrail hardening idea (feature-3 reviewer note).

## Log

- 2026-07-13: features 1, 2, 3, 4 all completed + approved (implementer →
  independent reviewer → done). writer→qwen_plus drift reconciled. Create-mode
  human checkpoints removed from architecture. Backlog complete; paused for
  user decision on next features.

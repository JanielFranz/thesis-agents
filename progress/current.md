# Current Session

> This file is cleared when each session closes and its summary moves to
> `history.md`. While working, **keep it updated in real time**, not at
> the end.

## Feature in progress

_(none)_ — **BACKLOG COMPLETE: all 10 features `done`.** Final `init.sh`:
10 done / 0 in progress / 101 tests passing / exit 0. `python -m thesis_agents
--help` runs (exit 0). Full detail in `progress/history.md` (2026-07-13 entries).

## Pipeline status

Assembled and runnable end-to-end (unit-tested with mocked models):
`uv run python -m thesis_agents --spec <DocSpec.json> --mode create|review
[--input <file>]`. A REAL run additionally needs: the OpenRouter model slugs
verified, an `OPENROUTER_API_KEY` in `.env`, populated `data/` inputs, and the
integration path exercised (`uv run pytest -m integration` — none written yet).

  Plan:
  - `entrypoints/cli.py`: `main(argv) -> int`; argparse `--spec` (required),
    `--mode {create,review}` (prompt if omitted), `--input` (review),
    `--env-file` (overridable so tests never read the real repo `.env`).
  - `.env` loaded via a tiny stdlib parser (no new dep); writes `os.environ`
    without overriding existing vars; config.py stays the only env *reader*.
  - DocSpec validated at the boundary (read spec JSON → `DocSpec.model_validate`)
    BEFORE building any client/controller call; invalid → clear error, rc!=0.
  - Build `OpenRouterClient` via module-level `build_client(config)` (mockable);
    `asyncio.run(create_mode/review_mode)`; print output path + approved.
  - `__main__.py`: `raise SystemExit(main())` for `python -m thesis_agents`.
  - `test_cli.py`: create dispatch, review dispatch (+doc text), invalid-spec
    boundary (no controller call), interactive mode prompt (stdin mocked).

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
- `verify.py` min-length guard measures RAW quote length, not normalized —
  a future pass could use `len(_normalize(quote))` (feature-7 reviewer note;
  does NOT admit fabricated text).

## Log

- 2026-07-13: features 1, 2, 3, 4 all completed + approved (implementer →
  independent reviewer → done). writer→qwen_plus drift reconciled. Create-mode
  human checkpoints removed from architecture. Backlog complete; paused for
  user decision on next features.

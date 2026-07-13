# Review — feature 10 cli
**Verdict:** APPROVED

Independently verified (secret `OPENROUTER_API_KEY` unset, real `.env` not consulted).

## Acceptance criteria
- "cli.py parses --spec/--mode/--input; validates DocSpec at the boundary before any model call; loads .env; dispatches to create_mode/review_mode; prints results; mode asked interactively if omitted" → **met**. `cli.py` `_build_parser` defines all three args + `--env-file` (cli.py:143-166). `main()` order: `load_env_file` (187) → `_load_spec` boundary validation (191) → `_resolve_mode` (197) → `--input` read for review (208) → `load_config` (214) → `build_client` (219) → `asyncio.run(create_mode/review_mode)` (222-227) → prints verdict + output path (229-231). Spec validation strictly precedes client build/model call.
- "Mode selection is the ONLY human interaction; entrypoint holds no routing beyond mode selection; never imports upward past core/" → **met**. Sole `input()` is in `_resolve_mode` (cli.py:129). No other prompt anywhere. Imports are composition-root-appropriate: `config`, `schemas.models.DocSpec`, `core.controller`, `adapters.openrouter` (cli.py:35-41); nothing lower imports cli.
- ".env loaded here (stdlib parser, not python-dotenv); OPENROUTER_API_KEY still resolved via config.py, no default / fail-loud" → **met**. `load_env_file` is a dependency-free parser (cli.py:60-90); no new runtime dep (git diff on `pyproject.toml` shows only `[build-system]`; `dependencies` list unchanged). `config.py` remains the only reader of env *values* for app logic (grep: cli only does a membership check + writes to load `.env`; config.py:147-194 read the values). `OPENROUTER_API_KEY` resolved with no default inside `load_config()`, surfaced as `ConfigError` → rc 2 (cli.py:214-217).
- "python -m thesis_agents runs the CLI" → **met**. `__main__.py` delegates `raise SystemExit(main())`. Smoke: `python -m thesis_agents --help` prints usage, exit 0.
- "Unit tests: valid --spec/--mode dispatches correct mode; invalid DocSpec rejected at boundary with clear error and NO model call; missing --mode triggers interactive prompt" → **met**. `test_main_create_dispatches_...`, `test_main_review_dispatches_...`, `test_main_invalid_spec_rejected_at_boundary_no_model_call` (asserts both `create.called is False` and `review.called is False`), `test_main_missing_required_field_...`, `test_main_missing_mode_triggers_interactive_prompt` (stdin monkeypatched). All 11 tests offline; `--env-file` points at nonexistent tmp path so real `.env` never read; dummy key from autouse conftest fixture.
- "uv run ruff check . clean; bash init.sh green" → **met**. `ruff check` → All checks passed; `ruff format --check` → 29 files already formatted; `bash init.sh` → `[OK] Environment ready.` exit 0 (101 passed).

## Build-system deviation assessment
- (a) Necessary: yes. `pyproject.toml` had no `[build-system]`, so uv treated the project as `virtual`; `python -m thesis_agents` could not resolve the package. Adding hatchling (git diff: build-system + `[tool.hatch.build.targets.wheel] packages=["src/thesis_agents"]`) makes the src-layout package installable — required for the "python -m" acceptance criterion.
- (b) No regression: FULL suite 101 passed (all 9 prior features + 11 new cli tests); `init.sh` green exit 0; ruff clean. `uv.lock` diff is a single line (`virtual` → `editable`); no new dependency.
- (c) `config.py` still importable at runtime: verified — `python -m thesis_agents` run from repo root resolves `from config import ...` via cwd on sys.path; smoke tests confirmed. Non-blocking observation: running `python -m thesis_agents` from a different cwd would fail to import root-level `config.py` (out of the wheel by design); documented in the pyproject comment. Not a defect in the documented run path.

## Smoke evidence (offline, secret unset)
- `python -m thesis_agents --help` → usage printed, exit 0.
- `python -m thesis_agents --spec <bad enum format=pdf> --mode create --env-file <nonexistent>` → `error: ... is not a valid DocSpec` (pydantic literal_error on `format`), exit 2, no client/controller call (it exited before `load_config`, which would have needed the unset secret).

## Checkpoints
- C1: [x]  Harness complete; `bash init.sh` exit 0.
- C2: [x]  Exactly one `in_progress` (feature 10); deps [5,9] both `done`; no dependent in a bad state; `current.md` describes the active session.
- C3: [x]  Layering holds (cli = composition root, imports downward only); typed models across boundaries (`DocSpec`, `CreateResult`/`ReviewResult`); no hard-coded paths/secrets (`ROOT_DIR`/`load_config` from config); no new dep, exact pins intact; CLI `print()` is user-facing entrypoint output (acceptance: "prints results"), env events go through `logger.info`.
- C4: [x]  `tests/unit/test_cli.py` mirrors the module; asserts concrete results (rc, dispatched mode, parsed DocSpec fields, document_name, no-call assertions); controller + client mocked, no network; `tmp_path` for spec/env/input; full suite green.
- C5: [x]  New entrypoint documented (impl_cli.md); untracked files are exactly the expected new sources/tests; feature 10 correctly still `in_progress` (implementer flips to `done` only after this approval). Reminder to leader: add a `history.md` entry at session close.

## Required Changes
None.

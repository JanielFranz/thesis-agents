# Review — feature 1 project_skeleton
**Verdict:** APPROVED

## Acceptance criteria
- "uv-managed package skeleton per §3 (config.py + package layers + tests)" → met.
  Evidence: root `config.py` (§3 places it at repo root, not under `src/`);
  `src/thesis_agents/` with layer stubs `core/`, `adapters/`, `adapters/formats/`,
  `entrypoints/`, `schemas/` (all empty: docstring + `from __future__ import
  annotations`, no feature-2/3/4 logic); `tests/conftest.py` + `tests/unit/
  test_config.py`; `uv.lock` present and committed-ready; `pyproject.toml`
  dev group pins pytest/ruff via uv, `dependencies = []`.
- "config.py is the only module reading os.environ; exposes load_config()" → met.
  Evidence: `Grep os.environ|getenv` across the tree matches only `config.py`
  (lines 82,87,92,102,112) plus docs. `load_config()` defined at config.py:121
  returning a frozen `AppConfig`.
- "uv run pytest -q -m 'not integration' green with ≥1 smoke test" → met.
  Independently ran: `7 passed in 0.04s`.
- "uv run ruff check . and ruff format --check . clean" → met.
  Independently ran: `All checks passed!` and `9 files already formatted`.
- "bash init.sh finishes with [OK] Environment ready" → met.
  Independently ran (with OPENROUTER_API_KEY stripped from the shell):
  `[OK] Environment ready. You can start working.` EXIT=0.

## Secret-isolation proof (critical)
- Ran `env -u OPENROUTER_API_KEY sh -c 'uv run pytest ...'`: in-shell key
  `[<UNSET>]`, `7 passed`. `config.py` contains no dotenv loader and never
  references `.env`; the dummy key is injected only by the autouse
  `_isolate_env` fixture (conftest.py:17-20). Suite passes with the real
  secret and real `.env` not consulted. PASS.
- Import safety: `test_importing_config_does_not_read_secret` deletes the key
  and asserts module constants + `ROOT_DIR.is_dir()`; `OPENROUTER_API_KEY` is
  read with no default only inside `load_config()` via `_require_secret`
  (config.py:111-118). Importing `config` never raises. PASS.

## Test quality
- Happy path asserts concrete field values (model_pro/flash slugs, base_url,
  api_key sentinel), loop caps `== 2`, and each data path equality — not "no
  exception". Error paths: missing-secret and empty-secret both assert
  `ConfigError` (match="OPENROUTER_API_KEY"). Env-override test uses `tmp_path`
  (real temp dir, no filesystem mocking).

## Declared deviations — judgment
- (a) Layer sub-package `__init__.py` stubs: ACCEPTED. Required by acceptance
  criterion 1 ("package layers per §3"); verified empty (docstring + future
  import), no premature logic.
- (b) `.env.example` edit: ACCEPTED. Doc-only, names not values; the secret
  line is `# OPENROUTER_API_KEY=` (no value); optional overrides are
  non-secret defaults. Consistent with architecture §9.
- (c) `extend-exclude = ["main.py"]` in pyproject.toml: ACCEPTED (minor note).
  `main.py` is a pre-existing stray PyCharm sample (`print_hi`) outside the
  §3 architecture, with a `print()` and >88-char lines. It is out of feature 1's
  scope to delete; excluding it via the owned config file keeps `ruff check .`
  clean without masking any real project code. Recommend deleting `main.py` in
  a later cleanup (tracked in the impl report).

## Out-of-scope observation (not blocking)
- `.claude/rules/architecture.md` shows as modified in git (removal of the two
  human checkpoints; create mode now runs unattended). This is a leader-level
  design-doc change consistent with `feature_list.json` stack.notes; it is not
  application code, not in feature 1's `paths`, and not the implementer's
  concern. No impact on this verdict.

## Checkpoints
- C1: [x] Harness files present; `bash init.sh` exits 0.
- C2: [x] Exactly one feature `in_progress` (id 1); no dep violations (id 1
  has no depends_on); current.md describes the active session; feature 1 NOT
  self-flipped to `done`.
- C3: [x] Layering respected (only stubs so far); no hard-coded paths/model
  names/secrets in code (slugs are config constants at config.py:27-28, nowhere
  inlined); `pathlib.Path` used throughout, no `os.path`; deps uv-pinned in
  pyproject + uv.lock, no requirements.txt; no stray `print()` in app code
  (main.py excluded and is not app code).
- C4: [x] Test file for the implemented module (test_config.py, 7 tests);
  asserts concrete results; no real external service; `tmp_path` for FS;
  `-m "not integration"` shows 7 > 0 green.
- C5: [x] No suspicious untracked artifacts (untracked = config.py, src/,
  tests/, impl report — all legitimate; __pycache__/.pytest_cache gitignored);
  feature reflected in correct state (`in_progress`); new config module and
  `.env.example` documented in the impl report. (history.md entry for THIS
  session is written at session close, after approval — expected pending.)

## Required Changes
None. Approved. (Non-blocking follow-up: delete the stray `main.py` in a later
cleanup so the ruff `extend-exclude` can be removed.)

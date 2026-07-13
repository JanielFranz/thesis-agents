# Implementation report — Feature 1 `project_skeleton`

Status: implemented, awaiting reviewer. Feature left `in_progress` in
`feature_list.json` (NOT flipped to `done`).

## Files created / modified

Within the feature's declared `paths`:

- `config.py` (repo root, per architecture §3 — NOT under `src/`): the only
  `os.environ` reader. Exposes module-level default constants, a frozen
  `AppConfig` dataclass, `ConfigError`, and `load_config()`.
- `src/thesis_agents/__init__.py`: package root with `__version__`.
- `tests/conftest.py`: autouse `_isolate_env` fixture that injects a dummy
  `OPENROUTER_API_KEY` via `monkeypatch.setenv`, so unit tests never read the
  real `.env`.
- `tests/unit/test_config.py`: 7 tests (happy path, loop caps, data paths,
  missing-secret error, empty-secret error, env overrides, import-safety).
- `pyproject.toml`: added `src` to pytest `pythonpath`; added ruff
  `extend-exclude = ["main.py"]` (see deviations).

Deviations from the literal `paths` list (all required by acceptance
criterion 1 — "package layers per §3" — or by "ruff check clean"):

- Layer sub-package stubs created as empty `__init__.py` (no feature-2/3/4
  bodies): `src/thesis_agents/core/`, `adapters/`, `adapters/formats/`,
  `entrypoints/`, `schemas/`. These establish the §3/§4 layering; they contain
  only a docstring + `from __future__ import annotations`.
- `.env.example` (doc-only): documented the required `OPENROUTER_API_KEY` and
  optional overrides. It documents variable names only, never values
  (architecture §9). Not application code.
- `pyproject.toml` `extend-exclude = ["main.py"]`: `main.py` is a pre-existing
  stray PyCharm sample (`print_hi`) that is NOT part of the architecture
  (§3 places the entrypoint at `src/thesis_agents/entrypoints/cli.py`). It has
  a `print()` and >88-char lines that would fail `ruff check .`. I did not edit
  or delete it (out of scope); excluding it via the config file I own keeps
  `ruff check .` clean without masking real issues. Recommend deleting `main.py`
  in a later cleanup.

## Key design decisions

- **Single env reader / typed config.** `config.py` is the only module reading
  `os.environ`. `load_config()` returns a `@dataclass(frozen=True, slots=True)`
  `AppConfig` carrying: data paths (§3.1), the two model slugs
  (`deepseek/deepseek-v4-pro` / `deepseek/deepseek-v4-flash`, env-overridable via
  `OPENROUTER_MODEL_PRO` / `OPENROUTER_MODEL_FLASH`), the OpenRouter base URL,
  request timeout, per-stage `max_turns`, and the loop caps
  `MAX_REVIEW_PASSES=2` / `MAX_JUDGE_RETRIES=2`. `pathlib.Path` throughout.
- **No new dependency.** Used a stdlib dataclass rather than Pydantic — the
  config is a flat, statically-known typed snapshot with no runtime coercion
  needs, so stdlib covers it (conventions §1 "don't add a library if the stdlib
  covers the need"). Pydantic can be added later for `DocSpec`/`Verdict`
  (feature-level schemas), where validation is actually needed.
- **Import-safe secret validation + test isolation.** Module import performs
  zero env-dependent work that can fail: constants use literal defaults and
  `ROOT_DIR` is derived from `__file__`. The required `OPENROUTER_API_KEY` is
  read with NO default and validated only inside `load_config()` via
  `_require_secret()`, which raises a loud `ConfigError` naming the variable.
  Empty string is treated as missing. Because validation is lazy, the suite
  imports `config` freely; `conftest.py` injects a dummy key so `load_config()`
  succeeds without the real secret, and the error-path tests use
  `monkeypatch.delenv` / `setenv("", ...)` to prove the loud failure.
- **`.env` never touched.** `config.py` contains no dotenv loading; nothing
  reads, prints, or references the real `.env` file, and no path points at it.
  Demonstrated below: the suite is green with `OPENROUTER_API_KEY` unset in the
  shell environment.
- **Package importability.** The project is a `virtual` uv package
  (`source = { virtual = "." }` in `uv.lock`), so `src/thesis_agents` is not
  installed. Added `src` to pytest `pythonpath` (alongside `.` for root
  `config.py`) so both import cleanly in tests without a build backend.

## Verification evidence (pasted output)

### 1. `uv run ruff check .` — clean

```
All checks passed!
```

### 2. `uv run ruff format --check .` — clean

```
9 files already formatted
```

### 3. `uv run pytest tests -q -m "not integration"` — green, with secret UNSET

Run in a shell where the real secret was stripped (`env -u OPENROUTER_API_KEY`):

```
key present in env? [<UNSET>]
.......                                                                  [100%]
7 passed in 0.05s
```

### 4. `bash init.sh` — exit 0, environment ready

```
── 4. Running tests ────────────────────────────────────
.......                                                                  [100%]
7 passed in 0.03s
[OK]   Unit tests passed (integration tests excluded; run them with: pytest -m integration)

── 5. Review ───────────────────────────────────────────
[OK]   Environment ready. You can start working.
EXIT=0
```

# Review — feature 2 openrouter_client
**Verdict:** APPROVED

Scope reviewed: `config.py`, `src/thesis_agents/adapters/openrouter.py`,
`tests/unit/test_openrouter_client.py`, `pyproject.toml`/`uv.lock`. All within
feature 2's declared `paths`. Feature 1 is `done` (dependency satisfied);
feature 2 is the only `in_progress` and was NOT self-flipped to `done`.

## Independently run (not trusting pasted output)
- `env -u OPENROUTER_API_KEY uv run ruff check .` → `All checks passed!`
- `env -u OPENROUTER_API_KEY uv run ruff format --check .` → `11 files already formatted`
- `env -u OPENROUTER_API_KEY uv run pytest tests -q -m "not integration"` → `14 passed`
- `env -u OPENROUTER_API_KEY bash init.sh` → `[OK] Environment ready.` EXIT=0
- Suite passes with `OPENROUTER_API_KEY` stripped from the process env. `config.py`
  does NOT load `.env` (no dotenv import anywhere in `src`/`config.py`); `conftest.py`
  injects a dummy key via `monkeypatch.setenv`. The green suite therefore does not
  rest on the real secret or the real `.env` (a `.env` file exists on disk but is
  never consulted by the test path).

## Acceptance criteria
- "SDK configured against OpenRouter base_url; API key read only in config.py from
  env, no default, fails loudly if missing" → **met**. `build_openrouter_client()`
  (openrouter.py:79-83) wires `AsyncOpenAI` with `config.openrouter_base_url` +
  `config.openrouter_api_key` + `config.request_timeout_s`; key comes from
  `_require_secret()` (config.py:176-183) with no default, raising `ConfigError`.
  `test_build_openrouter_client_targets_base_url` asserts `client.base_url` targets
  `openrouter.ai`.
- "Model slugs in stack.models (pro/flash/qwen_plus) are config constants, never
  inlined at call sites; tier selection resolves any configured tier by name" →
  **met**. `DEFAULT_MODEL_PRO/FLASH/QWEN_PLUS` (config.py:27-29), all three env-
  overridable and surfaced via `models_by_tier()`/`model_for_tier()` (raises
  `ConfigError` on unknown tier). Grep of openrouter.py for `openrouter.ai|deepseek/|qwen/`
  returns nothing — no inlined slug/host. Tests assert `resolve_tier` returns the
  correct slug for `pro`, `flash`, and `qwen_plus`, and raises on `bogus`.
- "Per-call token usage captured for cost accounting; per-stage maxTurns cap
  enforceable" → **met**. `StageUsage` (requests/input/output/total tokens + cost_usd)
  read from `result.context_wrapper.usage`; cost derived from per-tier `ModelPrice`.
  `run_stage(max_turns=None)` defaults to `config.max_turns`, overridable per call and
  forwarded to `Runner.run`. `test_run_stage_captures_usage_and_cost` asserts
  cost_usd == 5.0 (1M in @ $2 + 0.5M out @ $6) and max_turns forwarded == 4;
  `test_run_stage_defaults_max_turns_from_config` asserts the config default.
- "Unit test mocks HTTP/client (no real network), asserts base_url + tier selection"
  → **met**. Injected `MagicMock` client + `_FakeRunner`; no network. base_url and
  per-tier slug both asserted. `test_run_stage_propagates_runner_error` covers the
  error path (concrete assertion, not "no exception").
- "uv run ruff check . clean; bash init.sh green" → **met** (independently verified).

## Layering / conventions
- openrouter.py imports only `config` (down) + SDK `agents`/`openai` (externals). No
  import from `core/`, `entrypoints/`, or `thesis_agents.agents`. Boundary result is a
  typed frozen `StageResult`/`StageUsage`, never a raw string/dict.
- `config.py` remains the ONLY `os.environ` reader (grep confirms all reads live
  there); the adapter reads solely from the injected `AppConfig`.
- Outbound client built at a single site (`build_openrouter_client`) and injected;
  never constructed inside `run_stage`. Structured `logger.info/error(json.dumps(...))`
  per call; no `print()` in `src/`. `openai-agents==0.18.2` exact-pinned + locked.

## Notes / non-blocking observations
- Slug-existence claim (`qwen/qwen3.7-plus`, `deepseek/deepseek-v4-pro`,
  `deepseek/deepseek-v4-flash` present on OpenRouter) could NOT be independently
  confirmed from this environment. Not a rejection basis: the slugs are config-driven
  defaults (env-overridable), so the adapter code is correct regardless. Recorded as a
  run-time risk to re-verify before a live run.
- The implementer report says "8 new tests"; the file actually defines 7
  (`grep -c def test_` = 7). Cosmetic miscount only — total suite is 14 green.
- Dev-group deps (`pytest>=9.0.3`, `ruff>=0.15.17`) use `>=` rather than exact pins.
  These predate feature 2 (feature-1 skeleton scope, already approved) and are dev
  tooling, not the feature's runtime dep. Flagged for a future tidy; not blocking here.

## Checkpoints
- C1: [x] harness files + 3 rules present; `bash init.sh` exit 0.
- C2: [x] exactly one `in_progress` (id 2); no feature in_progress/done with an unmet
  dependency (id 1 done); current.md describes the active session.
- C3: [x] layering downward-only; typed `StageResult`/`StageUsage` cross the boundary;
  no hard-coded slugs/hosts/paths/secrets; `openai-agents==0.18.2` pinned + locked; no
  stray `print()`.
- C4: [x] test file per module; concrete-result assertions (base_url, slugs, cost,
  max_turns, error path); injected+mocked client/runner, no network; 14 tests green.
- C5: [x] no suspicious tmp/artifact files (untracked entries are the expected new
  source/tests); feature 2 correctly reflected as `in_progress` (not prematurely done);
  new adapter documented in the impl report. (Session-closure boxes apply at close;
  feature is mid-flight and consistent.)

## Required Changes
None.

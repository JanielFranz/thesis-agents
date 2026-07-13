# Implementation Report — Feature 2 `openrouter_client`

Status: implemented, `in_progress` (awaiting reviewer approval — not flipped to
`done`).

## Scope

Feature 2 only. Files within its declared `paths`; no other feature's scope
touched. No deviation from `paths`.

## Files created / changed

- **`config.py`** (extended): added the third tier slug + pricing, kept
  `config.py` the only `os.environ` reader and import crash-free.
  - `DEFAULT_MODEL_QWEN_PLUS = "qwen/qwen3.7-plus"` (env override
    `OPENROUTER_MODEL_QWEN_PLUS`).
  - Tier-name constants `TIER_PRO` / `TIER_FLASH` / `TIER_QWEN_PLUS`.
  - `ModelPrice` frozen dataclass (`input_usd_per_mtok`, `output_usd_per_mtok`)
    + per-tier `DEFAULT_PRICE_*_PER_MTOK = 0.0` defaults, env-overridable via
    `OPENROUTER_PRICE_<TIER>_INPUT` / `_OUTPUT` (helper `_env_price`).
  - `AppConfig` gained `model_qwen_plus`, `model_prices`, and three methods:
    `models_by_tier()`, `model_for_tier(tier)` (raises `ConfigError` on unknown
    tier), `price_for_tier(tier)`.
  - `OPENROUTER_API_KEY` remains read-with-no-default / fail-loud inside
    `load_config()`; nothing else reads env.
- **`src/thesis_agents/adapters/openrouter.py`** (new): the SDK ↔ OpenRouter
  wiring, tier selection, per-stage run + usage/cost accounting.
- **`tests/unit/test_openrouter_client.py`** (new): 8 unit tests, fully mocked.
- **`pyproject.toml` / `uv.lock`**: `openai-agents==0.18.2` added via `uv add`
  (exact pin) and locked via `uv sync`.

## How the client is injected + tier selection

- **Injection (conventions.md §3/§4):** `build_openrouter_client(config)` is the
  single construction site for the outbound `AsyncOpenAI` (base_url + api_key +
  timeout all from `config`, never inlined). `OpenRouterClient.__init__` takes
  the `AsyncOpenAI` client **and** the SDK `runner` as injected params
  (`runner` defaults to `agents.Runner`). Nothing outbound is constructed inside
  the method that uses it, so unit tests inject a `MagicMock` client + a fake
  runner and never hit the network.
- **Tier selection:** `resolve_tier(tier)` delegates to
  `config.model_for_tier(tier)`, which resolves ANY configured tier name
  (`pro` / `flash` / `qwen_plus`) to its slug from config and raises
  `ConfigError` on a typo. `model_for_tier(tier)` builds an
  `OpenAIChatCompletionsModel(model=<resolved slug>, openai_client=<injected>)`.
  No slug is ever inlined at a call site.
- **`max_turns` cap:** `run_stage(..., max_turns=None)` defaults to
  `config.max_turns` (per-stage cap, architecture.md §6.7) and forwards it to
  `Runner.run`; a caller (e.g. the Judge stage) can pass an explicit smaller cap.

## Typed usage/cost result shape

`run_stage()` returns a frozen `StageResult`:
- `stage: str`, `tier: str`, `model: str` (resolved slug), `output: str`,
  `duration_ms: float`, `usage: StageUsage`.
- `StageUsage` = `requests, input_tokens, output_tokens, total_tokens,
  cost_usd`. Usage is read from the SDK's `result.context_wrapper.usage`; cost
  is derived as `input/1e6*price_in + output/1e6*price_out` from the tier's
  `ModelPrice`. One structured `logger.info(json.dumps({...}))` line per call
  records stage/tier/model/duration/tokens/cost/outcome (no prompt content); on
  runner error a `logger.error` line with `outcome="error"` is emitted and the
  exception re-raised.

## `qwen_plus` slug verification — VERIFIED

Queried the live OpenRouter model list
(`GET https://openrouter.ai/api/v1/models`) at implementation time:
- `qwen/qwen3.7-plus` — present ✅
- `deepseek/deepseek-v4-pro` — present ✅
- `deepseek/deepseek-v4-flash` — present ✅

All three configured tier slugs are confirmed current on OpenRouter. (The
`stack.notes` "re-verify at implementation time" flag is satisfied.) Prices for
these slugs were not hardcoded — they default to 0.0 and are env-overridable,
since live per-token prices should be confirmed at run time.

## SDK version pinned

`openai-agents==0.18.2` (exact pin in `pyproject.toml`, locked in `uv.lock`).
Imports and runs on Python 3.14 / win32 — no compatibility issue; not blocked.

## Self-verification (pasted output)

### 1. `uv run ruff check .`
```
All checks passed!
```

### 2. `uv run ruff format --check .`
```
11 files already formatted
```

### 3. `uv run pytest tests -q -m "not integration"` (with `OPENROUTER_API_KEY` UNSET in the real env; conftest injects a dummy)
```
..............                                                           [100%]
14 passed in 1.95s
```
(8 new tests for this feature + 6 pre-existing feature-1 tests.)

### 4. `bash init.sh` (also with `OPENROUTER_API_KEY` unset)
```
── 4. Running tests ────────────────────────────────────
..............                                                           [100%]
14 passed in 1.51s
[OK]   Unit tests passed (integration tests excluded; ...)
── 5. Review ───────────────────────────────────────────
[OK]   Environment ready. You can start working.
EXIT=0
```

## Notes for reviewer

- No integration test added: feature 2 is the adapter wiring; a real-model call
  belongs to a later stage. Unit tests fully mock the client + runner.
- `config.py` stays the sole env reader; the adapter reads only from the
  injected `AppConfig`.

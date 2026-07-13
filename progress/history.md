# Session History (append-only)

> When a session closes, the summary from `progress/current.md` is appended
> here: date, feature, what was done, verification evidence, final status.

## 2026-07-12 — Harness created

- Ported the multi-agent harness from `AylluKhipu/server` (leader/implementer/
  reviewer agents, `.claude/rules/`, `AGENTS.md`, `CLAUDE.md`, `CHECKPOINTS.md`,
  `init.sh`, `feature_list.json`, `progress/`), generalized to a neutral
  Python + uv + ruff + pytest stack.
- Domain-specific rules content (`architecture.md` scope/layout/contracts) is
  a TEMPLATE to be filled with this project's real design.
- No application code exists yet; feature #1 (`project_skeleton`) is the entry
  point.

## 2026-07-13 — Feature 1 `project_skeleton` done

- **Docs/backlog (leader):** removed the two in-loop human checkpoints from
  create mode in `architecture.md` (§2.1, §2, §3, §4, §6.1–6.2) — create mode
  now runs unattended end-to-end, gated only by CLI mode selection; dropped
  `core/checkpoints.py` from the layout. Added feature 4 `agent_result_logging`
  (structured per-call logs + optional local JSONL trace; no LangChain/
  LangSmith — decision recorded in its acceptance).
- **Feature 1 (implementer → reviewer):** root `config.py` (sole `os.environ`
  reader; frozen `AppConfig` + `load_config()`; data paths, model slugs
  env-overridable, timeouts, loop caps `MAX_REVIEW_PASSES=2`/`MAX_JUDGE_RETRIES
  =2`), `src/thesis_agents/` layer stubs, `tests/conftest.py` (dummy key
  fixture) + `tests/unit/test_config.py` (7 tests). Stdlib only, no new dep.
- **Verification:** reviewer independently ran ruff check/format (clean),
  pytest (7 passed) with `OPENROUTER_API_KEY` stripped + `.env` not consulted
  (secret-isolation proof), `bash init.sh` exit 0. All C1–C5 green. APPROVED
  (`progress/review_project_skeleton.md`). Non-blocking follow-up: delete stray
  root `main.py` so the ruff `extend-exclude` can be removed.
- **Final status:** feature 1 `done`; feature 2 `openrouter_client` now
  eligible. Note: `stack.agent_models.writer` was changed out-of-band to
  `qwen_plus` (`qwen/qwen3.7-plus`) — derived docs not yet reconciled (see
  current.md).

## 2026-07-13 — writer→qwen_plus drift reconciled + Feature 2 `openrouter_client` done

- **Drift reconciliation (leader):** treated `stack` as single source of truth
  and updated all derived docs to `writer=qwen_plus` (`qwen/qwen3.7-plus`):
  `architecture.md` §5 (intro + Writer row), `feature_list.json`
  `stack.notes[0]/[1]` (the obsolete "Judge/Writer share a family" limitation is
  now removed by the change), `writer.why`, feature 2 acceptance ("two slugs" →
  three configured tiers), feature 3 acceptance ("writer=pro" → "writer=qwen_plus").
- **Feature 2 (implementer → reviewer):** `adapters/openrouter.py` — OpenAI
  Agents SDK wired to OpenRouter `base_url` (from config); `resolve_tier` /
  `config.model_for_tier` resolve any of the three tiers by name (no inlined
  slug); injected `AsyncOpenAI` client + runner (mocked in tests, no network);
  per-stage `max_turns` cap; typed `StageResult`/`StageUsage` capturing per-call
  tokens + derived cost; structured per-call log line. `config.py` extended with
  the `qwen_plus` slug + per-tier pricing, still the sole env reader.
  `openai-agents==0.18.2` exact-pinned + locked.
- **Verification:** reviewer independently ran ruff check/format (clean), 14
  tests (7 new) green with `OPENROUTER_API_KEY` stripped, `bash init.sh` exit 0.
  All C1–C5 green. APPROVED (`progress/review_openrouter_client.md`).
- **Non-blocking notes carried forward:** (1) slug existence
  (`qwen/qwen3.7-plus` etc.) could NOT be independently confirmed by the
  reviewer — run-time risk, re-verify before any integration run (config-driven,
  so a one-line env override fixes it). (2) dev deps `pytest`/`ruff` use `>=`,
  not exact pins — future tidy.
- **Final status:** feature 2 `done`; feature 3 `agent_definitions` eligible.

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

## 2026-07-13 — Feature 3 `agent_definitions` done

- **Feature 3 (implementer → reviewer):** the four agents (`researcher`/
  `writer`/`reviewer`/`judge`) in `agents.py` with per-agent tier (via
  feature-2 `client.model_for_tier`, no inlined slug) + least-privilege tool
  scoping (only researcher has web; reviewer/judge read-only; writer read +
  draft-write; judge `max_turns=3`). Four system prompts as files in `prompts/`
  (Judge prompt embeds the §7 rubric + Verdict shape + verbatim-quote rule;
  Reviewer embeds `{approved, feedback}`). Structured output is prompting-based
  (no native `output_type`, per the DeepSeek BFCL finding).
- **Deny guardrail (`adapters/tools.py`, pre-authorized deviation):** real SDK
  `tool_input_guardrail` delegating to a pure `evaluate_tool_call()` — denies
  nested-agent/task spawning and any `.env`/secret access, in code not prompt;
  reads confined to data dirs, writes to `data/output/drafts/`. The SDK's real
  hook was used (`ToolInputGuardrailData` / `ToolGuardrailFunctionOutput`).
- **Verification:** reviewer independently ran ruff (clean), 32 tests (18 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, and **independently
  probed the guardrail** with bypass vectors (`./.env`, `data/../.env`, `.ENV`,
  JSON-string args, nested `secret/api_key.txt`, spawn/delegate tool names) —
  all denied. All C1–C5 green. APPROVED (`progress/review_agent_definitions.md`).
- **Final status:** feature 3 `done`. Feature 4 `agent_result_logging` (deps
  [2,3]) now eligible — but see the controller-gap note in current.md.

## 2026-07-13 — Feature 4 `agent_result_logging` done — BACKLOG COMPLETE (4/4)

- **Scope decision (leader):** the backlog skipped the controller state machine,
  so feature 4 built ONLY the instrumented `run_agent()` primitive — NOT
  `create_mode`/`review_mode` (deferred to a future controller feature).
- **Feature 4 (implementer → reviewer):** new `core/controller.py` with
  `new_run_id()` (uuid4 hex) + async `run_agent()` wrapping the feature-2
  `OpenRouterClient.run_stage`; emits exactly one structured
  `logger.info(json.dumps(...))` line per call (agent/stage/tier/model/run_id/
  duration_ms/token usage/cost/outcome — no prompt text at INFO), and optionally
  appends one full untruncated JSON record (prompt+output) to
  `<trace_dir>/<run_id>.jsonl`. `config.py` gained env-overridable `trace_dir`
  (`THESIS_TRACE_DIR`/`THESIS_TRACE_ENABLED`, default `data/output/traces/`),
  still the sole env reader. Typed `AgentRunResult`. **No dependency added** —
  stdlib logging + local files (the no-LangChain/LangSmith decision, enforced).
- **Verification:** reviewer independently ran ruff (clean), 39 tests (7 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, and `git diff` on
  pyproject/uv.lock EMPTY (no dep). All C1–C5 green. APPROVED
  (`progress/review_agent_result_logging.md`).
- **Backlog status:** all 4 features `done`; `init.sh` = 4 done / 0 in progress
  / 39 passing / exit 0. The pipeline is NOT yet runnable end-to-end — the
  architecture still needs new features: controller state machines
  (`create_mode`/`review_mode`), `schemas/models.py`, `core/rubric.py`,
  `core/verify.py`, `entrypoints/cli.py`, `adapters/formats/`. Awaiting user
  decision on whether to add + build those next.

## 2026-07-13 — Backlog expanded (5–10) + Feature 5 `schemas` done

- **Backlog (leader):** added features 5 `schemas`, 6 `rubric`, 7 `verify`,
  8 `formats`, 9 `controller`, 10 `cli` with acceptance criteria + deps
  (chain: 5[1], 6[1], 7[5,6], 8[5], 9[3,4,5,6,7,8], 10[5,9]). Deps validated
  (each strictly earlier, no unknowns/cycles); `init.sh` green at 10 features.
- **Feature 5 (implementer → reviewer):** `schemas/models.py` — the four §8
  Pydantic v2 contracts (`DocSpec`, `Review`, `Verdict`, `CriterionScore`) +
  nested `Chapter`, field names verbatim from §8 (no aliases), score bounded
  0..5, `format`/`docType` true `Literal` enums, JSON schemas via built-in
  `model_json_schema()`. Pure validation, no I/O/env. `pydantic==2.13.4`
  exact-pinned (first runtime dep besides openai-agents).
- **Verification:** reviewer independently ran ruff (clean), 53 tests (14 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, and verified §8
  field-name fidelity line by line. All C1–C5 green. APPROVED
  (`progress/review_schemas.md`).
- **Final status:** feature 5 `done`. Eligible next: 6 `rubric` and 8 `formats`
  (deps satisfied). 6 `rubric` recommended next (unblocks 7 `verify`).

## 2026-07-13 — Feature 6 `rubric` done

- **Feature 6 (implementer → reviewer):** `core/rubric.py` — the fixed
  six-criterion rubric (grounding/references pass≥4; scope/structure/argument/
  style pass≥3; scores 0..5) as immutable frozen `Criterion` dataclasses in a
  module-level `RUBRIC` tuple. `rubric_to_text()` for prompt embedding; parity/
  threshold API for feature 7: `criterion_ids()`, `criterion_thresholds()`,
  `is_passing()`. Passing rule documented (approved iff every score ≥ threshold).
  Pure: no I/O, no env, no `schemas` import, no new dep.
- **Cross-file consistency:** rubric ids/thresholds match `prompts/judge.md`
  (feature 3) exactly — independently confirmed by the reviewer at both file:line
  locations. This matters because the Judge emits `Verdict.criterionId`s that
  feature 7 `verify` will check against this rubric.
- **Verification:** reviewer independently ran ruff (clean), 61 tests (8 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0. All C1–C5 green.
  APPROVED (`progress/review_rubric.md`).
- **Final status:** feature 6 `done`. Eligible next: 7 `verify` (deps [5,6] now
  both done) and 8 `formats` (deps [5]). 7 `verify` completes the gate logic.

## 2026-07-13 — Feature 7 `verify` done (the code-side gate)

- **Feature 7 (implementer → reviewer):** `core/verify.py` —
  `verify_verdict_quotes(verdict, draft) -> Verdict`. Ignores the model's
  self-reported `approved` and recomputes `all(score >= threshold)` against the
  imported rubric (not duplicated). Voids the verdict (forces approved=false +
  appends a reason) on: missing rubric criterion, unknown/extra criterionId,
  duplicate criterionId, too-short quote (`MIN_QUOTE_CHARS=12`), or a quote not
  present verbatim after normalization (`" ".join(text.split()).casefold()` —
  whitespace-collapse + case-fold). Approval requires BOTH thresholds AND all
  quote/coverage checks (plain 3-way AND, no short-circuit masking). Returns a
  revalidated Verdict; input never mutated. Pure (no env/IO/model). No new dep.
- **Verification:** reviewer independently ran ruff (clean), 71 tests (11 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, and probed for
  false-APPROVE holes (empty scores fail safe; duplicate/unknown ids can't
  smuggle a passing score; fabricated quotes can't pass). All C1–C5 green.
  APPROVED (`progress/review_verify.md`).
- **Non-blocking hardening note (tracked):** the min-length guard measures the
  RAW quote length, not the normalized length — a whitespace-padded quote can
  clear the 12-char floor while its normalized content is shorter. Does NOT
  admit fabricated text (normalized span must still appear in the draft); a
  future pass could measure `len(_normalize(quote))`.
- **Final status:** feature 7 `done`. Only 8 `formats` (deps [5]) now blocks
  9 `controller`. Then 10 `cli` makes the pipeline runnable.

## 2026-07-13 — Feature 8 `formats` done

- **Feature 8 (implementer → reviewer):** `adapters/formats/` — `__init__.py`
  with `slugify()` + `render_to_format(markdown, spec, output_dir,
  name_hint=None) -> Path` (routes by `spec.format`; `output_dir` is the
  caller's, never hard-coded); `prose.py` `render_docx()` renders the Writer's
  Markdown subset (#/##/### headings, paragraphs, -/* bullets, 1. numbered,
  **bold**/*italic*) to `.docx` via python-docx; `slides.py` `render_pptx()` is
  a `NotImplementedError` stub (python-pptx NOT added). `python-docx==1.1.2`
  exact-pinned (lxml transitive). Imports only `schemas` + stdlib + `docx`.
- **Verification:** reviewer independently ran ruff (clean), 84 tests (13 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, and verified the
  docx **round-trip** (reopened the file, asserted heading/paragraph text +
  bold/italic runs) plus inline-parser edge cases (`**bold**` not two italics;
  leading `*italic*` not a bullet). All C1–C5 green. APPROVED
  (`progress/review_formats.md`).
- **Final status:** feature 8 `done`. All deps for 9 `controller`
  [3,4,5,6,7,8] now satisfied — the state machines can be assembled next, then
  10 `cli`.

## 2026-07-13 — Feature 9 `controller` done (integration centerpiece)

- **Feature 9 (implementer → reviewer):** extended `core/controller.py` (feature-4
  `run_agent`/`new_run_id` left intact) with async `create_mode(spec, client,
  config, *, agents)` and `review_mode(document, spec, client, config, ...)` +
  typed frozen `CreateResult`/`ReviewResult`.
  - **create_mode (§2.1):** one `run_id` threaded through Researcher →
    Writer(outline) → Writer(draft) → Reviewer↔Writer (counter `< max_review_
    passes`) → Judge↔Writer (counter `< max_judge_retries`) → `render_to_format`.
    Unattended — no human checkpoints.
  - **Gate discipline:** `_run_structured()` extracts+validates the Reviewer/
    Judge JSON against `Review`/`Verdict` (bounded retry `=2`, then fail-safe
    not-approved); routing reads `verify_verdict_quotes(raw_verdict, draft)`,
    NEVER the model's self-reported `approved`.
  - **Post-cap (§6.2):** Judge never approving within the cap → logs
    `create_shipped_unapproved`, still renders, returns `approved=False`. No
    prompt, no infinite loop.
  - **review_mode (§2.2):** Reviewer → Judge(verify) → assemble Markdown report →
    render (`review-report-<name>`); no Writer, no loop.
- **Verification:** reviewer independently ran ruff (clean), 91 tests (7 new)
  green with `OPENROUTER_API_KEY` stripped, `init.sh` exit 0, verified consumed-
  module APIs against real signatures, confirmed **no feature-4 regression**, and
  confirmed the verify-gate/unattended/bounded-loop behaviors. All C1–C5 green.
  APPROVED (`progress/review_controller.md`).
- **Non-blocking note (tracked):** caps are config-driven; a pathological
  `max_*=0` override would skip a loop entirely — a future `max(1, cap)` guard
  could harden it (not reachable with defaults).
- **Final status:** feature 9 `done`. Only **10 `cli`** (deps [5,9]) remains —
  it makes the pipeline runnable via `python -m thesis_agents`.

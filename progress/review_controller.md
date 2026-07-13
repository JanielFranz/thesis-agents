# Review — feature 9 controller

**Verdict:** APPROVED

## Acceptance criteria
- "create_mode drives Researcher -> Writer(outline) -> Writer(draft) -> Reviewer<->Writer (capped) -> Judge<->Writer (capped) -> render_to_format, one run_id threaded, UNATTENDED no human checkpoints" → **met**. controller.py:462-561 runs exactly that chain; `new_run_id()` called once (l.459) and passed to every `run_agent`/`_run_structured` call. Grep of controller.py finds no `input()`/`stdin`/`checkpoint`/`print`. Test `test_create_mode_threads_one_shared_run_id` asserts every run_agent INFO line shares `result.run_id`.
- "Loop caps are integer counters; final Judge rejection after cap neither loops nor prompts a human — run completes and records unapproved verdict alongside rendered output" → **met**. Review loop l.491-514 and Judge loop l.519-546 are `while <counter> < config.max_*`, counter incremented at top, guaranteed termination. Post-cap: l.548-561 logs `create_shipped_unapproved` warning and still calls `render_to_format`, returning `approved=False`. Test `test_create_mode_judge_cap_completes_unapproved` proves `judge_passes == max_judge_retries`, a rendered `.docx` exists, and `approved is False`.
- "Never routes on unvalidated free text: Reviewer/Judge parsed+validated against Pydantic (retried), Judge verdict must pass verify_verdict_quotes + recomputed all(score>=threshold) before approval" → **met**. `_run_structured` (l.264-319) validates via `schema.model_validate`, retries `DEFAULT_MAX_PARSE_RETRIES=2` times, returns `None` → fail-safe `_unparsed_review`/`_unparsed_verdict` (approved=False). Routing reads `verify_verdict_quotes(raw_verdict, draft).approved` (l.531-536), never `raw_verdict.approved`. Tests `..._reviewer_parse_failure_fails_safe`, `..._verify_gate_overrides_model_self_report` (fabricated quote → False), `..._judge_cap_completes_unapproved` (sub-threshold score → False).
- "review_mode: Reviewer -> Judge (quotes verified) -> assemble Markdown report -> render; no Writer, no revision loop" → **met**. review_mode l.583-652: two structured stages, verify gate (l.625-629), `_review_report` Markdown, `render_to_format` with `name_hint="review-report-<name>"`. Test `test_review_mode_produces_report_without_writer` asserts `client.stages == ["reviewer", "judge"]`.
- "Unit tests (all mocked, no network) assert the five behaviors" → **met**. 7 controller tests, all pass with `OPENROUTER_API_KEY` unset (injected `_ScriptedClient` fake, `tmp_path` output dir, no network).
- "uv run ruff check . clean; bash init.sh green" → **met**. ruff check `All checks passed!`; ruff format `26 files already formatted`; `bash init.sh` → `91 passed`, `[OK] Environment ready.`, EXIT=0.

## Verification independently run (secret stripped)
- `uv run ruff check .` → All checks passed.
- `uv run ruff format --check .` → 26 files already formatted.
- `env -u OPENROUTER_API_KEY uv run pytest tests -q -m "not integration"` → 91 passed (includes feature-4 `test_agent_result_logging.py` + 7 new controller tests; no regression).
- `bash init.sh` → `[OK] Environment ready.` EXIT=0.
- Consumed-module APIs verified against real signatures: `config.AppConfig` (`max_review_passes`, `max_judge_retries`, `output_dir`, `trace_dir`), `render_to_format(markdown, spec, output_dir, name_hint=)`, `OpenRouterClient.run_stage`/`StageResult`, `AgentDefinition`/`build_agents`, `rubric.rubric_to_text`/`MAX_SCORE`, `verify_verdict_quotes(verdict, draft)->Verdict`, `DocSpec`/`Review`/`Verdict`. No assumed API.
- No feature-4 regression: `new_run_id`/`run_agent`/`AgentRunResult` unchanged (controller.py:71-206); logging/trace behavior intact; its test passes.
- Injection + layering: `client`/`config`/`agents` injected; `CreateResult`/`ReviewResult` typed frozen dataclasses; controller imports never reach `entrypoints/`; grep confirms `config.py` remains the only `os.environ` reader (no `os.environ` in `src/`).
- State: feature 9 still `in_progress` (diff shows only pending→in_progress, not self-flipped to done); exactly one in_progress; deps [3,4,5,6,7,8] all done; `pyproject.toml`/`uv.lock` unchanged (no new dependency).

## Checkpoints
- C1: [x] harness intact; init.sh exit 0.
- C2: [x] one in_progress (id 9); deps all done; feature 9 not marked done; current.md describes active session.
- C3: [x] layering downward (core → agents/adapters/schemas/config, never entrypoints); typed results not raw dict/path; no inlined slugs/paths/secrets; no new dep; no stray print/TODO.
- C4: [x] `test_controller.py` present; asserts concrete results (counters, run_id, approved flags, rendered file); client injected+mocked; `tmp_path` used; suite green > 0 tests.
- C5: [x] no suspicious artifacts; feature reflected as in_progress. (history.md entry is a session-close step for the leader, not this feature.)

## Notes (non-blocking)
1. Loop-cap semantics: caps bound the number of Reviewer/Judge *runs* (default 2), yielding cap-1 intervening Writer revisions. This is a defensible reading of MAX_REVIEW_PASSES/MAX_JUDGE_RETRIES and §2.1; the loops always terminate and run at least once under the shipped defaults. Acceptable.
2. Both caps are config-driven; a pathological override of `max_review_passes=0`/`max_judge_retries=0` would skip the loop entirely (review stays `None`, verdict stays the fail-safe unapproved). Not reachable with defaults; a future guard (`max(1, cap)`) could harden it. Non-blocking.
3. When the final Reviewer pass disapproves, no Writer revision runs before the Judge stage, so the Judge grades the last disapproved draft. This is the intended soft-gate design (Reviewer non-terminal, Judge is the backstop). Correct.

## Required Changes
None.

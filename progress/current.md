# Current Session

> This file is cleared when each session closes and its summary moves to
> `history.md`. While working, **keep it updated in real time**, not at
> the end.

## Feature in progress

- **Feature 4 `agent_result_logging`** (status `in_progress`; depends_on:
  [2 ✓, 3 ✓] done). Implementer dispatched.

## Done this session

- Features 1 `project_skeleton`, 2 `openrouter_client`, 3 `agent_definitions`
  → all `done` (approved). writer→qwen_plus drift reconciled. Full detail in
  `progress/history.md`.

## IMPORTANT — controller gap (scoping decision for feature 4)

Feature 4's acceptance references `run_agent()` and `create_mode`/`review_mode`
in `core/controller.py`, but **no prior feature built the controller** — the
backlog went agent_definitions → logging, skipping the state machine. Decision:
feature 4 builds only the **instrumented `run_agent()` primitive** (wraps the
feature-2 `OpenRouterClient.run_stage`, adds `run_id` + the structured log line
+ the optional JSONL trace) plus a `run_id` factory. It does **NOT** build the
`create_mode`/`review_mode` state machines — those belong to a future
`controller` feature that will generate the `run_id` once and thread it through
its `run_agent()` calls. Feature-4 tests simulate a multi-agent run by calling
`run_agent()` repeatedly with one shared `run_id`.

## Backlog status after feature 4

Feature 4 is the LAST item in the current backlog. The architecture (§2–§8)
describes much more that has no feature yet: the controller state machines
(`create_mode`/`review_mode`), `schemas/models.py` (DocSpec/Review/Verdict),
`core/rubric.py`, `core/verify.py` (quote verification), `entrypoints/cli.py`,
and `adapters/formats/` (docx renderer). These need new backlog entries before
the pipeline is runnable end-to-end. Propose to the user after feature 4.

## Carried-forward risks (non-blocking)

- Model slug existence not independently confirmed — re-verify on OpenRouter
  before any integration run (config-driven; one-line env override fixes it).
- Dev deps `pytest`/`ruff` use `>=`, not exact pins — future tidy.
- Stray root `main.py` still ruff-excluded rather than deleted — future cleanup.
- `_SECRET_MARKERS` guardrail hardening idea (reviewer note, feature 3).

## Plan (feature 4 — implementer)

- Add `trace_dir` to `config.py` (env `THESIS_TRACE_DIR` / `THESIS_TRACE_ENABLED`,
  default `data/output/traces/`); keep config the only `os.environ` reader.
- New `core/controller.py`: `new_run_id()` (uuid4 hex) + async `run_agent()`
  wrapping the injected feature-2 `OpenRouterClient.run_stage`; one structured
  log line per call + optional one-line JSONL trace under `<trace_dir>/<run_id>.jsonl`.
- Return typed `AgentRunResult` carrying `run_id` + the feature-2 `StageResult`.
- NOT building `create_mode`/`review_mode` state machines (future controller feat).
- Tests: field/type assertions, shared run_id across a simulated 4-agent run,
  JSONL exactly-one-line-per-call + disabled-no-file, error-path `outcome=error`.
- Stdlib logging + local files only — no LangChain/LangSmith/Langfuse dep.

## Log

- 2026-07-13: features 1–3 completed + approved.
- 2026-07-13: flipped feature 4 `pending → in_progress`; dispatching implementer
  (scoped to the run_agent logging seam — no state machines; see above).
- 2026-07-13: implementer started feature 4.

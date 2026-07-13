# Current Session

> This file is cleared when each session closes and its summary moves to
> `history.md`. While working, **keep it updated in real time**, not at
> the end.

## Feature in progress

- **Feature 3 `agent_definitions`** (status `in_progress`; depends_on: [2] ✓ done).
  Implementer dispatched.

## Done this session

- Feature 1 `project_skeleton` → `done` (approved).
- Feature 2 `openrouter_client` → `done` (approved).
- writer→qwen_plus stack drift reconciled across architecture.md + feature_list.json.
- Full detail in `progress/history.md` (two 2026-07-13 entries).

## Carried-forward risks (non-blocking)

- Model slug existence (`qwen/qwen3.7-plus`, `deepseek/deepseek-v4-pro/-flash`)
  not independently confirmed — re-verify on OpenRouter before any integration
  run. Config-driven, so a one-line env override fixes a wrong slug.
- Dev deps `pytest`/`ruff` use `>=`, not exact pins — future tidy.
- Stray root `main.py` (PyCharm sample) still excluded from ruff rather than
  deleted — future cleanup.

## Feature 3 scope notes (for the dispatched implementer)

- Known paths-vs-acceptance tension: acceptance criteria 2 & 5 require the
  pre-tool-call deny guardrail, which architecture §3/§6.5 places in
  `adapters/tools.py` — outside feature 3's literal `paths`. Implementer is
  authorized to add `adapters/tools.py` (function tools + guardrail) as a
  required extension, noting the deviation (mirrors feature 1's sub-package
  stubs). Tool bodies stay minimal; the emphasis is agent definitions, per-agent
  tier + least-privilege tool scoping, and the (explicitly tested) guardrail.
- `agents.py` must not import from `core/`/`entrypoints/`; structured output for
  Reviewer/Judge is prompting-based (schema embedded in the prompt files), NOT
  native tool-call JSON — the code-side validators live in later features.

## Log

- 2026-07-13: features 1 & 2 completed + approved; drift reconciled.
- 2026-07-13: flipped feature 3 `pending → in_progress`; dispatching implementer.

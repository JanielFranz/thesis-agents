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

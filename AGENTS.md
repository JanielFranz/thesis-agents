# AGENTS.md — Navigation Map for AI Agents

> This file is the **entry point** for any agent working in this repo.
> It is NOT a rulebook: it is a **map**. Read only what you need when you
> need it (progressive disclosure).

`thesis-agents-python` is a Python multi-agent project. <One-line description
of what it does — replace this with the real scope.>

---

## 1. Before you start (mandatory)

1. Run `bash init.sh` and verify it finishes without errors. If it fails,
   **stop** and fix the environment before touching any code.
2. Read `progress/current.md` to understand the state of the last session.
3. Read `feature_list.json` and choose **one** task with `pending` status whose
   `depends_on` list contains only `done` features. Do not work on more than
   one at a time.

## 2. Repository Map

| File / folder                  | What it contains                                              | When to read it |
|--------------------------------|---------------------------------------------------------------|-----------------|
| `feature_list.json`            | Project tasks with status and dependencies                    | Always, at the beginning |
| `progress/current.md`          | State of the current session                                  | Always, at the beginning |
| `progress/history.md`          | Append-only log of previous sessions                          | If you need historical context |
| `.claude/rules/architecture.md`| Layers, module map, what goes where                           | Before implementing |
| `.claude/rules/conventions.md` | Style, naming, uv/ruff/pytest rules                           | Before writing code |
| `.claude/rules/verification.md`| How to prove your work is functional                          | Before declaring a task `done` |
| `CHECKPOINTS.md`               | Objective criteria for a "correct final state"                | To self-assess |
| `.claude/agents/`              | Definitions of sub-agents (leader, implementer, reviewer)     | If you are orchestrating work |
| `config.py`, project package   | Application code                                              | For implementation |
| `tests/`                       | Unit + integration tests                                      | For verification |

## 3. Hard Rules (non-negotiable)

- **One feature at a time.** Do not mix changes from multiple tasks in the
  same session.
- **Respect dependencies.** Do not start a feature whose `depends_on` is not
  fully `done`.
- **Do not declare a task `done` without green tests.** Run `bash init.sh`
  and ensure the test suite passes 100%.
- **uv only.** Dependencies live in `pyproject.toml` (exact pins, added with
  `uv add`) and the committed `uv.lock`; install with `uv sync` and run every
  command through `uv run` (pytest, ruff, python). Never bare `pip install`,
  never create or activate a virtualenv manually.
- **Document what you do** in `progress/current.md` as you work, not at the end.
- **Leave the repository clean** before closing the session (see §5).
- **Never call a real external service in unit tests.** Mock external
  processes and HTTP clients. Real-service tests are `@pytest.mark.integration`.

## 4. How to choose a task

```
1. Open feature_list.json
2. Filter by status == "pending"
3. Discard any whose depends_on contains a feature not yet "done"
4. Take the remaining one with the lowest "id"
5. Change its status to "in_progress" and save
6. Note in progress/current.md: feature, start time, brief plan
```

## 5. Session Closure (lifecycle)

Before finishing:

1. Run `bash init.sh` — all green.
2. If the task is finished **and the reviewer approved**: set
   `status: "done"` in `feature_list.json`.
3. Move the summary from `progress/current.md` to the end of
   `progress/history.md`.
4. Empty `progress/current.md`, leaving only the template.
5. Do not leave temporary files, debug `print()` statements, or TODOs
   without context.

## 6. If you get stuck

- Reread the relevant rules file.
- If a tool does not do what you expect, **do not invent a workaround**:
  document the block in `progress/current.md`, set the feature's status to
  `blocked`, and stop the session.

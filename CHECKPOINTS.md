# CHECKPOINTS — Final State Evaluation

> In multi-agent systems, the destination is evaluated, not the path.
> These are the objective checkpoints that a judge (human or AI) can use
> to decide if the project is healthy. The reviewer agent walks through
> every box before any session closure is accepted.

## C1 — The harness is complete

- [ ] The base files exist: `AGENTS.md`, `CLAUDE.md`, `init.sh`,
      `feature_list.json`, `CHECKPOINTS.md`, `progress/current.md`,
      `progress/history.md`.
- [ ] The 3 rules exist: `.claude/rules/architecture.md`,
      `.claude/rules/conventions.md`, `.claude/rules/verification.md`.
- [ ] `bash init.sh` finishes with exit code 0.

## C2 — The state is coherent

- [ ] At most one feature is `in_progress` in `feature_list.json`.
- [ ] No feature is `in_progress` or `done` while one of its `depends_on`
      is not `done`.
- [ ] Every `done` feature has associated tests that pass (or, for
      script/doc-only features, the artifact named in `paths` exists).
- [ ] `progress/current.md` is empty (template only) or describes the active
      session — it does not contain garbage from previous sessions.

## C3 — The code respects the architecture

- [ ] Layering holds: dependency arrows point downward (entrypoints → core →
      externals; entrypoints/core → adapters). Core never imports from
      entrypoints; only adapters touch the outside world.
- [ ] Data crossing layer boundaries is a typed model, never a raw dict.
- [ ] No hard-coded absolute paths, hosts, model names, or secrets inside the
      code — everything comes from `config.py` / env.
- [ ] Every dependency used is pinned exactly in `pyproject.toml` and locked
      in the committed `uv.lock` (uv-managed; no `requirements.txt`, no bare
      pip, no manually created virtualenvs).
- [ ] There are no loose `print()` calls for debugging, nor TODOs without
      context.

## C4 — Verification is real

- [ ] `tests/` has at least one test file per implemented module.
- [ ] Tests assert the concrete result, not merely "no exception".
- [ ] Unit tests never invoke a real external service: external clients/
      subprocesses are injected and mocked. Tests that need real services are
      marked `@pytest.mark.integration`.
- [ ] Filesystem tests use a temporary dir (`tmp_path`), never real project
      data.
- [ ] `uv run pytest tests -m "not integration"` shows > 0 tests and all green.

## C5 — The session was closed correctly

- [ ] There are no suspicious untracked files (`*.tmp`, `__pycache__`, stray
      artifacts outside `.gitignore`).
- [ ] `progress/history.md` has an entry for the last session.
- [ ] The last feature worked on is reflected in its correct state in
      `feature_list.json`.
- [ ] New entrypoints/scripts/artifacts are documented.

---

**How to use this file:** the reviewer agent (`.claude/agents/reviewer.md`)
goes through each checkbox, marks `[x]` or `[ ]`, and rejects the session
closure if any boxes in C1-C5 remain empty.

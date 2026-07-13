# Verification — How to Prove the Work Functions

> Golden rule: **the agent doesn't say "it works", it proves it**.
> Every feature ends with executable evidence, not assertions.

## Verification Levels

### Level 1 — Unit Tests (mandatory for every feature)

Every public function in the code layers has at least one test in `tests/`
that:

1. Covers the happy path **and verifies the concrete result** (returned
   object fields, status), not merely "doesn't throw".
2. Covers at least one error path if the function can fail (timeout, missing
   input, malformed data).

Command (what `init.sh` runs):

```bash
uv run pytest tests -q -m "not integration"
```

### Level 2 — Smoke Test (mandatory for entrypoint features)

Actually run the thing end-to-end. For a CLI:

```bash
uv run python -m thesis_agents ...        # adjust to the real entrypoint
```

For anything with a numeric budget in its acceptance criterion (a latency, a
token count, an accuracy threshold), **measure it** and record the number in
`progress/current.md`.

### Level 3 — Integration Tests (when real services exist)

Tests that exercise a real external service (LLM API, tool, binary) are marked
`@pytest.mark.integration` and run on demand:

```bash
uv run pytest tests -q -m integration
```

They are required evidence for features whose acceptance criteria mention a
real model or service.

### Scripts and docs features

Features whose `paths` point at scripts or docs:

- Bash scripts: `bash -n file.sh` plus a real run when possible.
- PowerShell scripts: a parse check plus a real run on the current platform.
- Docs: the file exists, renders (valid Markdown), and matches what the code
  actually does.
- If a script targets the *other* OS, say so explicitly in
  `progress/current.md` ("parse-checked only, not executed — needs a <OS>
  run"). Never claim an untested script works.

## Anti-patterns (don't do these)

- ❌ "I added it, it should work." → missing executable test.
- ❌ A test that asserts only "no exception". → assert the concrete result.
- ❌ Unit tests that silently hit a real service because the mock wasn't
  wired. → the suite must pass with the service stopped.
- ❌ Mocking the filesystem. → use `tmp_path` and a real temp dir.
- ❌ Marking a feature `done` without `bash init.sh` green and reviewer
  approval.

## Final Verification Before Closing

```bash
bash init.sh        # must finish with [OK] Environment ready
```

If `init.sh` is red, do **not** mark anything as `done`. Log the blocker in
`progress/current.md` and set the feature's status to `blocked` in
`feature_list.json`.

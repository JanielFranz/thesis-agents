# Implementation report — Feature 4 `agent_result_logging`

Status: implemented, `in_progress` (awaiting reviewer). Depends on 2 ✓, 3 ✓.

## Scope decision (carried forward from current.md)

Built **only** the instrumented `run_agent()` primitive + `run_id` plumbing +
the JSONL trace writer. The `create_mode` / `review_mode` state machines were
**intentionally NOT built** — the backlog skipped the controller state machine,
so those belong to a future `controller` feature that will call `new_run_id()`
once per invocation and thread the resulting `run_id` through its four
`run_agent()` calls. Feature-4 tests simulate that multi-agent run by calling
`run_agent()` repeatedly with one shared `run_id`.

## Files touched

- `config.py` — added `trace_dir: Path | None` field to `AppConfig`; added
  `_env_bool()`; `load_config()` now resolves `trace_dir` from
  `THESIS_TRACE_DIR` (default `data/output/traces/`) and the
  `THESIS_TRACE_ENABLED` toggle (default on; when off, `trace_dir` is `None`).
  `config.py` remains the ONLY `os.environ` reader.
- `src/thesis_agents/core/controller.py` — **new.** `new_run_id()`,
  `run_agent()`, `AgentRunResult`, `RUN_AGENT_EVENT`, plus private
  `_summary_fields()` / `_append_trace()` helpers.
- `tests/unit/test_agent_result_logging.py` — **new**, 7 tests.
- `src/thesis_agents/adapters/openrouter.py` — **listed in `paths` but left
  unchanged** (see deviations below). Its `run_stage`/`StageResult`/`StageUsage`
  are reused as-is; usage/cost capture was not re-implemented.

## `run_agent()` signature and how `run_id` is threaded

```python
async def run_agent(
    client: OpenRouterClient,
    *,
    agent: AgentDefinition,
    stage: str,
    run_id: str,
    prompt: str,
    trace_dir: Path | None = None,
) -> AgentRunResult
```

- `client` is **injected** (never constructed here) — the feature-2
  `OpenRouterClient`. Tests inject a fake with an async `run_stage`.
- `agent` is the feature-3 `AgentDefinition`, which supplies `agent.name`,
  `agent.tier`, `agent.agent` (SDK agent), and `agent.max_turns` (e.g. the
  Judge's 3). `run_agent` forwards these to
  `client.run_stage(agent.agent, prompt, tier=agent.tier, stage=stage,
  max_turns=agent.max_turns)` — reusing the feature-2 accounting path verbatim.
- `run_id` is an **injected parameter**. The future controller generates it
  once via `new_run_id()` (`uuid.uuid4().hex`, 32 hex chars — random, not a
  wall-clock timestamp, so runs started in the same instant never collide) and
  passes the same value into every `run_agent()` call, giving all four agents'
  log lines and their shared `<trace_dir>/<run_id>.jsonl` transcript one
  correlation key.
- Returns typed `AgentRunResult(run_id, agent, result: StageResult)` — never a
  raw string.

## Exact structured log-line field set (one line per call)

`logger.info(json.dumps({...}))` on the `thesis_agents.core.controller` logger,
success case:

`event="run_agent"`, `agent`, `stage`, `run_id`, `tier`, `model`,
`duration_ms` (rounded), `input_tokens`, `output_tokens`, `total_tokens`,
`cost_usd`, `outcome="ok"`.

The raw `prompt`/`output` text is **deliberately excluded** from the INFO line
(conventions §5 — ids/lengths/usage only). On failure, exactly one
`logger.error(json.dumps({...}))` line with `event="run_agent"`, `agent`,
`stage`, `run_id`, `tier`, `outcome="error"`, then the exception propagates and
**no trace record is written**.

## Trace-file format and `trace_dir` toggle

- When `trace_dir is not None`, each call appends **one** JSON line to
  `<trace_dir>/<run_id>.jsonl` (dir created with `pathlib` if missing). The
  record is the log summary **plus** the untruncated `prompt` and `output` — a
  complete, local-only, replayable per-run transcript that accretes across every
  stage sharing `run_id`.
- When `trace_dir is None` (either injected as `None`, or config-disabled via
  `THESIS_TRACE_ENABLED=0`), no file is written; the INFO log line is still
  emitted.
- `data/output/` (hence the default `data/output/traces/`) is gitignored, and
  nothing leaves the machine.

## No tracing dependency added (acceptance 4)

No `uv add` was run for this feature. Logging is **stdlib `logging` + local
files** only. No LangChain, LangSmith, Langfuse, or any telemetry package.
`pyproject.toml`/`uv.lock` unchanged by this feature.

## Note on the feature-2 adapter's own log line

`OpenRouterClient.run_stage` already emits its own adapter-layer
`event="run_stage"` line. That is a separate layer/logger
(`thesis_agents.adapters.openrouter`); `run_agent` emits the authoritative
controller-layer `event="run_agent"` line carrying `agent` + `run_id`. Tests
assert "exactly one line per call" by filtering on the controller logger, so
the two layers do not interfere. Left `run_stage` untouched to avoid regressing
feature 2.

## Deviations from `paths`

`src/thesis_agents/adapters/openrouter.py` is listed in the feature's `paths`
but required no change — its `run_stage`/`StageResult`/`StageUsage` are reused
directly, per the task's "do NOT re-implement usage/cost capture." No other
files outside the listed `paths` were touched.

## Verification evidence (pasted)

1. `uv run ruff check .`
```
All checks passed!
```

2. `uv run ruff format --check .`
```
16 files already formatted
```

3. `uv run pytest tests -q -m "not integration"`
```
.......................................                                  [100%]
39 passed in 4.91s
```
   And with `OPENROUTER_API_KEY` unset in the environment (relying on the
   feature-1 conftest dummy), the new file alone:
```
OPENROUTER_API_KEY not in env
.......                                                                  [100%]
7 passed in 1.83s
```

4. `bash init.sh`
```
[OK]   feature_list.json valid (4 features, 3 done, 1 in progress)
── 4. Running tests ────────────────────────────────────
39 passed in 4.91s
[OK]   Unit tests passed (integration tests excluded; run them with: pytest -m integration)
[OK]   Environment ready. You can start working.
EXIT=0
```

## Tests (what they assert)

- `test_new_run_id_is_unique_hex` — 100 ids unique, 32-char hex.
- `test_run_agent_logs_required_fields_with_types` — all required keys present
  with correct types; `prompt`/`output` absent from the INFO line.
- `test_run_agent_forwards_agent_turn_cap_to_client` — Judge's `max_turns=3`,
  tier, stage forwarded to the injected client.
- `test_run_agent_shares_run_id_across_multi_agent_run` — 4 simulated agents,
  one shared `run_id` on every line.
- `test_run_agent_appends_one_trace_line_per_call` — exactly one JSONL line per
  call, each valid JSON carrying full prompt/output + metadata.
- `test_run_agent_writes_no_trace_when_disabled` — `trace_dir=None` → no file.
- `test_run_agent_logs_error_and_propagates` — `outcome="error"` line emitted,
  exception propagates, no trace file created.

Feature 4 left `in_progress` — not flipped to `done` (awaiting reviewer).

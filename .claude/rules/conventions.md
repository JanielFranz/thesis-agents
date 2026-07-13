# conventions.md — Development Standards

Applies to all code in `thesis-agents-python/`. Read this before writing any
code.

---

## 1. Language & Runtime

- **Python ≥ 3.14** (the pin in `pyproject.toml`). No compatibility shims for
  older versions.
- Format with **`ruff format`** (Black-compatible, line length 88) and lint
  with **`ruff check`** — one tool for both. Black itself is not used.
- Type hints on every function signature. Use
  `from __future__ import annotations` in all modules.
- Prefer `pathlib.Path` over `os.path` everywhere.
- **All Python tooling runs through `uv`** — never bare `pip install`,
  never `python -m venv`, never manual virtualenv activation. `uv sync`
  creates and updates `.venv` automatically, and every command is executed
  via `uv run` (`uv run pytest`, `uv run ruff check`, `uv run python ...`).
- Dependencies are declared in `pyproject.toml` with **exact pins** added
  via `uv add` (`uv add httpx==0.28.1`) and locked in a committed `uv.lock`.
  There is no `requirements.txt`. Do not add a library if the stdlib or an
  existing dep covers the need.

## 2. Naming

| Pattern | Convention | Example |
|---|---|---|
| Functions / variables / modules | `snake_case` | `run_agent`, `plan_steps` |
| Classes | `PascalCase` | `AgentState`, `ToolResult` |
| Calls to external systems | `call_*` / `fetch_*` / `run_*` | `call_llm`, `fetch_document` |
| I/O helpers | `load_*` / `save_*` | `load_config`, `save_transcript` |
| Generators | `iter_*` / `stream_*` | `stream_tokens` |
| Booleans | `is_` / `has_` / `should_` prefix | `is_complete`, `has_tool_calls` |
| Constants | `UPPER_SNAKE_CASE`, grouped at module top | `DEFAULT_MODEL` |

- Typed data models: `<Thing>Request` / `<Thing>Response` /
  `<Thing>State` as appropriate.
- **Never hard-code paths, hosts, ports, model names, or API bases** — they
  live in `config.py` and are read from env vars with defaults.
- **Secrets are never hard-coded and never defaulted.** They come from env
  vars (read in `config.py`) with **no** fallback; the code fails loudly at
  startup if a required one is missing. Never write a secret to a log or the
  repo.

## 3. Structure & Design

- Keep the layering in `architecture.md`: dependency arrows point downward,
  entrypoints stay thin, core is pure, adapters own all outside contact.
- Shared resources (clients, sessions, service instances) are **injected**
  (constructor arg or a `Depends`/factory), never constructed inside the
  function that uses them. This is what makes them mockable in tests.
- Blocking work (subprocess, large file decode, sync network) inside async
  code goes through a thread executor — never block the event loop.

## 4. External Process / Service Conventions

- Every function that calls an external service (LLM API, tool, subprocess)
  must:
  1. Accept the client/binary path as an **injected parameter**, never
     construct or resolve it internally.
  2. Return a **typed** result (dataclass / Pydantic model), not a raw
     string/bytes blob.
  3. Log duration and outcome (structured, see §5).
  4. Have a unit test with the client/subprocess mocked.
- Reach HTTP services over a proper client (e.g. `httpx`) with an **explicit
  timeout** from `config.py`. Do not shell out to a CLI when an API exists.
- Subprocesses run with explicit argument lists (never `shell=True`), temp
  files under `tempfile`, and cleanup in `finally`.
- For LLM calls, always set token limits / stop conditions explicitly; never
  rely on provider defaults.

## 5. Logging

Structured logging; never a bare `print()` in library/application code.

```python
import json, logging
logger = logging.getLogger(__name__)

logger.info(json.dumps({"event": "agent_step", "step": n, "latency_ms": ms}))
```

- Expected, recoverable failures: `logger.warning`, handle, continue.
- Unrecoverable failures: `logger.error`, raise.
- Don't log full prompts/completions at INFO in hot paths — log ids and
  lengths.

## 6. Error Handling

- **Validate at boundaries** (input schema, file, subprocess output). Trust
  internal data after that.
- Catch the specific exception you expect (`httpx.TimeoutException`,
  `FileNotFoundError`, …) — never a bare `except Exception` around a whole
  entrypoint.
- One failing call must never crash the whole run when it can be isolated.

## 7. Data & I/O

- File paths come from `config.py`; tests always override them to `tmp_path`.
- Never mock the filesystem — use `tmp_path` and real temp files/DBs.

## 8. Testing

- Tests live in `tests/`, mirroring the module path
  (`tests/unit/test_planner.py`).
- **pytest** only; no `unittest` subclasses.
- **Unit tests never touch real external services / network.** Tests that
  need real services or binaries are marked `@pytest.mark.integration` and
  excluded from `init.sh` (run manually: `uv run pytest -m integration`).
- Tests assert the **concrete result** (returned object fields, status), not
  merely "doesn't throw".
- Naming: `test_<function>_<scenario>` — e.g.
  `test_run_agent_stops_at_max_steps`, `test_call_llm_retries_on_timeout`.

## 9. AI-Specific Guardrails

| Concern | Rule |
|---|---|
| System / agent prompts | Store in files (e.g. `prompts/`), not inline strings |
| Model name | A constant in `config.py`, never inline |
| Determinism in tests | Never call a real model in unit tests — inject and mock the client |
| API keys | Read from env in `config.py`, no default, never logged or committed |

# Implementation report — Feature 3 `agent_definitions`

Status: implemented, `in_progress` (awaiting reviewer approval). Depends on
features 1 & 2 (both `done`).

## SDK API discovered (openai-agents 0.18.2)

Inspected the installed package before coding. Real symbol names used:

- **Function tools:** `agents.function_tool` decorator. Signature accepts
  `tool_input_guardrails: list[ToolInputGuardrail] | None` — so per-tool
  guardrails attach at tool-definition time. Decorated functions become
  `agents.tool.FunctionTool` objects exposing `.name` and
  `.tool_input_guardrails`. Docstrings supply the tool/arg descriptions.
- **Pre-tool-call guardrail (the real hook exists):** `agents.tool_input_guardrail`
  decorator produces an `agents.ToolInputGuardrail`, whose
  `.guardrail_function(data)` is the callable and `.run(data)` the async
  wrapper. It receives `agents.tool_guardrails.ToolInputGuardrailData` with
  fields `.context` (a `agents.tool_context.ToolContext`) and `.agent`.
  `ToolContext` carries `.tool_name` and `.tool_arguments` (a JSON string).
- **Guardrail result:** `agents.ToolGuardrailFunctionOutput` with classmethods
  `.allow()`, `.reject_content(message)`, `.raise_exception(output_info=...)`.
  Its `.behavior` is a **plain dict** `{"type": "allow" | "reject_content" |
  "raise_exception"}` (not an object with `.type` — tests assert
  `behavior["type"]`). We use `raise_exception` to halt so a denied tool never
  runs.
- **Agent:** `agents.Agent(name, instructions=..., model=..., tools=[...])`.
  There is **no** per-agent `max_turns` field (it is a `Runner.run` argument),
  so the Judge's cap is carried on our `AgentDefinition` wrapper instead.

Conclusion: the SDK **does** provide a genuine pre-tool-call guardrail hook, so
the deny gate is implemented as a real `tool_input_guardrail` (not a prompt and
not a hand-rolled dispatcher wrapper).

## Files created

- `prompts/researcher.md`, `prompts/writer.md`, `prompts/reviewer.md`,
  `prompts/judge.md` — the four system prompts as files (never inline). The
  Judge prompt embeds the fixed six-criterion rubric + thresholds (§7) and the
  `Verdict` JSON shape with the verbatim-quote requirement (§8); the Reviewer
  prompt embeds the `{approved, feedback}` `Review` shape. Structured output is
  obtained by **prompting the schema** — no native tool-call JSON.
- `src/thesis_agents/adapters/tools.py` — function tools + the deny guardrail
  (**deviation, see below**).
- `src/thesis_agents/agents.py` — the four agent definitions.
- `tests/unit/test_agent_definitions.py` — 18 unit tests.

## Per-agent tier + tool scoping + guardrail attachment

`agents.py` builds each agent via injected `OpenRouterClient` (feature 2),
reusing `client.model_for_tier(tier)` → `OpenAIChatCompletionsModel` — tier→slug
wiring is **not** re-invented. Tiers come from `config` constants
(`TIER_PRO`/`TIER_QWEN_PLUS`/`TIER_FLASH`); no slug is inlined anywhere.

| Agent | Tier | Tools (least privilege) | max_turns |
|---|---|---|---|
| researcher | pro | read (`read_file`,`grep`,`glob`) + web (`web_search`,`web_fetch`) | default |
| writer | qwen_plus | read + draft-write (`write_file`,`edit_file`) | default |
| reviewer | flash | read-only | default |
| judge | pro | read-only | **3** (`JUDGE_MAX_TURNS`) |

Only the Researcher has web tools; Reviewer/Judge cannot write or fetch; the
Judge carries `max_turns=3` on its `AgentDefinition`. Every tool (built by the
`build_*_tools` factories) attaches `deny_gate` via `tool_input_guardrails`, so
the code-side gate fires before any tool runs regardless of prompt.

The deny gate's decision logic is a **pure function** `evaluate_tool_call(name,
arguments)` returning a typed `ToolCallDecision`, so the security-critical logic
is unit-testable in isolation. It denies (a) nested agent/task spawning
(tool-name markers: agent/task/spawn/delegate/handoff/subagent) and (b) any
tool whose name or any argument leaf references `.env`/secret/credential/api_key/
etc. `arguments` may be a dict or a JSON string (both scanned). Defence in depth:
read tools are confined via `_resolve_within` to the configured data dirs and
write tools to `data/output/drafts/`.

## Structured-output-via-prompting (no native `output_type`)

Per architecture §6.3 and the BFCL finding, no agent sets an SDK `output_type`
(which would force native function-calling JSON that DeepSeek does unreliably).
Reviewer/Judge instead emit their JSON shape because the prompt files instruct
the exact schema; code-side jsonschema validation + the quote machine-check land
in later features (controller/verify). This keeps routing off unvalidated free
text without depending on native tool-call JSON.

## Deviations

- **`adapters/tools.py` created** (outside feature 3's literal `paths`). Required
  to satisfy acceptance criteria 2 (deny guardrail) and 5 (function tools the
  agents are scoped to), which architecture §3/§6.5 place in `adapters/`. This
  was pre-authorized in `progress/current.md` and mirrors feature 1's
  sub-package-stub deviation. Tool bodies are minimal but real; the web tools
  are clearly-marked seams (no full web stack).
- One `json.JSONDecodeError`/`ValueError` branch was collapsed to `except
  ValueError:` (JSONDecodeError subclasses ValueError) after a transient
  formatting artifact — no behavioral change.

## Layering check

`agents.py` imports only from `config` and `adapters/` (openrouter, tools) —
never `core/` or `entrypoints/`. `adapters/tools.py` imports only `config` and
the SDK. Arrows point downward.

## Verification (pasted output)

1. `uv run ruff check .` → `All checks passed!`
2. `uv run ruff format --check .` → `14 files already formatted`
3. `uv run pytest tests -q -m "not integration"` → `32 passed in 3.82s`
   (18 new). Ran again with `env -u OPENROUTER_API_KEY` (real secret stripped;
   conftest injects a dummy, `.env` never read) →
   `18 passed` for the new module.
4. `bash init.sh` → `[OK] Environment ready.` exit 0
   (`feature_list.json valid (4 features, 2 done, 1 in progress)`).

Unit tests assert concrete results: each agent's resolved model slug equals its
configured tier's slug; exact least-privilege tool sets (researcher HAS web,
reviewer/judge read-only and cannot write); the guardrail DENIES a `.env` read
and a nested-spawn attempt (both the pure function and the SDK guardrail wrapper
with synthetic `ToolInputGuardrailData`); prompts are non-empty and loaded from
files; Judge `max_turns == 3`.

Do NOT flip feature 3 to `done` — awaiting reviewer approval.

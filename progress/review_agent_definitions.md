# Review — feature 3 agent_definitions
**Verdict:** APPROVED

Reviewer independently re-ran every check (secret stripped via `env -u OPENROUTER_API_KEY`);
pasted implementer output was not trusted.

## Acceptance criteria
- "Four agents defined with per-agent tier (researcher=pro, writer=qwen_plus, reviewer=flash,
  judge=pro) and least-privilege tools (only researcher gets web)" → met.
  Evidence: `agents.py:75-120` builds each via `client.model_for_tier(TIER_*)` from `config`
  (no inlined slug — grep of `src/`+`prompts/` for `deepseek/|qwen/` = empty). Tests
  `test_agent_model_slugs_match_configured_tier` assert `agent.model.model == config.model_for_tier(tier)`.
  Tool sets exact: researcher read+web, writer read+draft-write, reviewer/judge read-only
  (`test_researcher_has_read_and_web_tools`, `test_writer_has_read_and_draft_write_but_no_web`,
  `test_reviewer_is_read_only`, `test_judge_is_read_only_with_turn_cap`). Judge `max_turns==3`.
- "Code-side pre-tool-call guardrail denies nested spawn + .env, in code not prompt" → met.
  Evidence: `adapters/tools.py:145-171` real SDK `@tool_input_guardrail deny_gate` delegating to
  pure `evaluate_tool_call` (`tools.py:99-142`); denies via `raise_exception` so the tool never
  runs. Independently probed: `./.env`, `data/../.env`, `.ENV`, JSON-string args,
  deeply-nested `secret/api_key.txt`, and `spawn_agent`/`delegate_to_subagent`/`run_task` all
  → allowed=False; ordinary read → allowed=True. Defense-in-depth: `_resolve_within`
  (`tools.py:181-193`) confines reads to data dirs and writes to drafts dir.
- "Prompts live in prompts/ as files, not inline" → met. `prompts/{researcher,writer,reviewer,judge}.md`
  present; `load_prompt` (`agents.py:63-72`) reads files and rejects empties;
  `test_prompts_are_loaded_from_files`.
- "Reviewer/Judge structured output via prompting (not native tool-call JSON); Judge quotes
  machine-verifiable" → met. No `output_type` set on any agent (grep: only a docstring mention).
  `prompts/judge.md` embeds all six rubric criteria + thresholds + `perCriterionScores`/
  `quotedJustification` verbatim-quote requirement; `prompts/reviewer.md` embeds `{approved, feedback}`.
- "Unit tests assert model slug + tool scope, and guardrail denies .env read and nested spawn" → met.
  18 feature-3 tests present asserting denial (allowed is False) both at the pure-function and SDK-
  wrapper level (`behavior["type"]=="raise_exception"`), plus tier/tool-scope assertions.
- "ruff check clean; init.sh green" → met (measured below).

## Independently measured evidence (secret unset)
- `uv run ruff check .` → All checks passed!
- `uv run ruff format --check .` → 14 files already formatted
- `uv run pytest tests -q -m "not integration"` → 32 passed. Passes with `OPENROUTER_API_KEY`
  unset: `conftest._isolate_env` injects a dummy key; `config.py` reads only `os.environ`
  (no dotenv — `.env` loaded by the CLI entrypoint, never in tests). Not secret/.env-dependent.
- `bash init.sh` → [OK] Environment ready. exit 0.

## Deviation judged acceptable
`adapters/tools.py` created outside feature 3's literal `paths`: required by criteria 2 & 5,
placed there per architecture §3/§6.5, pre-authorized in `current.md`. Tool bodies minimal
(web tools are marked seams; read/write path-confined). Layering holds: `agents.py` imports only
`config`+`adapters/`; `tools.py` imports only `config`+SDK. No `core/`/`entrypoints/` imports.

## Checkpoints
- C1: [x]  base files + rules exist; init.sh exit 0.
- C2: [x]  exactly one in_progress (feature 3, not self-flipped to done); dep [2] done.
- C3: [x]  layering downward; typed results (AgentDefinition, ToolCallDecision); no inlined
           slugs/paths/secrets; no stray print (only structured logger.warning/info).
- C4: [x]  test file present; concrete-result assertions; no network/real model (client injected,
           no run executed); 32 > 0 green.
- C5: [x]  no suspicious untracked files (only the expected feature-3 artifacts); feature state
           correct (in_progress); new files documented in impl report.

## Required Changes
None.

## Non-blocking notes
- `_SECRET_MARKERS` relies on the literal path fragment; a secret file with none of the listed
  fragments would rely solely on `_resolve_within` confinement. Adequate today; consider allow-
  listing readable roots explicitly if the marker list grows brittle.
- Carried-forward: model slugs (`qwen/qwen3.7-plus`, `deepseek-v4-*`) still not confirmed live on
  OpenRouter — config-driven, re-verify before integration run.

# Architecture — thesis-agents-python

Architecture reference for this project. This is the condensed, rules-level
reference the implementer and reviewer consult before touching code. Keep it
in sync with the code and with `feature_list.json` (its `stack` block is the
single source of truth for the model provider, SDK, and per-agent tiers — this
file summarizes and does not re-decide them).

> This project is a Python port of the TypeScript prototype at
> `../thesis-agents` (built on the Claude Agent SDK). It keeps that project's
> architecture — a **deterministic external controller** that owns all routing,
> two document workflows (create / review), and guardrails enforced in code —
> but runs on **DeepSeek via OpenRouter through the OpenAI Agents SDK** instead
> of Claude. The layering discipline in §4 and the guardrails in §6 are the
> load-bearing invariants; keep them even if concrete modules move.

---

## 1. Scope

The pipeline turns a **document spec** (a `DocSpec`) plus a folder of project
material into a finished thesis-chapter document, and can separately **grade an
existing document**. Four agents do the reasoning — **Researcher, Writer,
Reviewer, Judge** — and a hand-written state machine (the *controller*) decides
every transition between them.

**In scope (this build):**
- `create` mode: generate a thesis chapter from the source folders, render to
  `.docx`.
- `review` mode: assess an existing document against the rubric, render a
  review report.

**Explicitly out of scope (do not build):**
- Autonomous agent-to-agent delegation / a router the model can talk past.
  Routing is the controller's job, in code — agents never spawn other agents.
- Output formats beyond `.docx` (a `.pptx` renderer is a documented stub).
- Any Claude / Anthropic SDK dependency.

## 2. The two deterministic workflows

The controller runs the LLM **inside** each stage; it decides all routing
itself. Loop bounds are integer counters checked in code, not instructions the
model could ignore.

### 2.1 `create` mode — generate a chapter

```
Researcher ──► Writer(outline) ──► Writer(draft)
    ▼
Reviewer ↔ Writer   loop, capped at MAX_REVIEW_PASSES = 2
    │   (Reviewer returns {approved, feedback}; if not approved, Writer revises)
    ▼
Judge ↔ Writer      loop, capped at MAX_JUDGE_RETRIES = 2
    │   (Judge returns a rubric verdict; controller machine-verifies its quotes;
    │    if rejected, Writer fixes the listed defects and the Judge re-scores)
    │   └─ cap exhausted without approval ──► run completes anyway; the
    │      controller records the unapproved verdict alongside the output
    │      instead of pausing for a human decision
    ▼
render_to_format(draft) ──► data/output/<slug>.docx
```

Create mode runs **unattended, start to finish**, once launched — there is no
mid-run pause for approval anywhere in this diagram.

### 2.2 `review` mode — grade an existing document

```
document from data/input/  ──►  Reviewer (structured critique)
                           ──►  Judge (structured rubric verdict, quotes machine-verified)
                           ──►  controller assembles a review report (Markdown)
                           ──►  render_to_format(report) ──► data/output/review-report-<name>.docx
```

`review` mode has **no revision loop and no Writer** — the human owns the
document; the pipeline only assesses it and reports.

Both modes are entered from the CLI: `--spec <DocSpec.json>` plus
`--mode create|review` (and `--input <file>` for review). Mode is asked
interactively if omitted. **This mode choice is the pipeline's only point of
human interaction** — see the guardrail in §6.2 — after that, the run
proceeds unattended to a rendered output.

## 3. Target Layout

```
thesis-agents-python/
├── config.py                       ← all paths, model slugs, timeouts, loop caps; the ONLY os.environ reader
├── pyproject.toml                  ← project metadata + exact-pinned deps (uv)
├── uv.lock                         ← committed lockfile (uv sync)
├── feature_list.json               ← backlog + the `stack` block: authoritative provider/SDK/per-agent tiers (§5)
├── plan.md                         ← exploratory design notes / research findings (superseded where §5 differs)
├── prompts/                        ← the 4 agent system prompts, one file each (never inline strings)
│   ├── researcher.md
│   ├── writer.md
│   ├── reviewer.md
│   └── judge.md
├── data/                           ← the pipeline's I/O contract — see §3.1
│   ├── source-of-truth/            ← what the thesis is about (scope authority)
│   ├── sources/                    ← reference papers (.md) + a state-of-the-art index of citation metadata
│   ├── input/                      ← documents submitted for grading (review mode)
│   └── output/                     ← generated .docx / review reports (gitignored)
│       └── drafts/                 ← Writer's optional working copies
├── src/thesis_agents/
│   ├── entrypoints/
│   │   └── cli.py                  ← arg parsing (--spec/--mode/--input), interactive prompts, dispatch, .env load
│   ├── core/
│   │   ├── controller.py           ← the state machine: create_mode(), review_mode(), run_agent(); loop caps
│   │   ├── rubric.py               ← the FIXED rubric (compiled-in) + rubric_to_text()
│   │   └── verify.py               ← verify_verdict_quotes(): machine-check the Judge's quoted evidence
│   ├── agents.py                   ← the 4 agent definitions: per-agent model tier, tool scope, guardrail
│   ├── adapters/
│   │   ├── openrouter.py           ← OpenAI Agents SDK ↔ OpenRouter base_url; tier selection; usage/cost accounting
│   │   ├── tools.py                ← file/web function tools + the pre-tool-call deny guardrail
│   │   └── formats/
│   │       ├── __init__.py         ← render_to_format() switch + slugify()
│   │       ├── prose.py            ← Markdown → .docx (python-docx)
│   │       └── slides.py           ← .pptx renderer — stub, raises NotImplementedError
│   └── schemas/
│       └── models.py               ← DocSpec, Review, Verdict, CriterionScore (Pydantic) + their JSON schemas
└── tests/
    ├── conftest.py                 ← app fixtures, mocked model client, tmp data dirs
    ├── unit/                       ← fast, no network / no real model
    └── integration/                ← @pytest.mark.integration (real OpenRouter call)
```

### 3.1 Data folders — the I/O contract

Every path comes from `config.py`; agents address these folders by their
documented roles, never by hard-coded absolute paths.

| Folder | Role | Access rule |
|---|---|---|
| `data/source-of-truth/` | The document(s) defining what the thesis is about — the single authority on scope, goals, and terminology. | Read by Researcher/Writer/Reviewer/Judge. Read-only. |
| `data/sources/` | Reference papers as Markdown (`.md`), one per source, plus a state-of-the-art index file listing each source's citation metadata (title, authors, year, DOI/URL, category). Source PDFs are parsed to `.md` out of band before a run. | Read-only. The **only** place new citations may come from — agents must not invent sources. |
| `data/input/` | Pre-existing documents submitted for grading. | Read in `review` mode only. Read-only. |
| `data/output/` | Generated artifacts (`.docx`, review reports) and the Writer's `drafts/` working copies. | The Writer may write under `output/drafts/`. **No agent may read `data/output/` as evidence** — it is generated, not ground truth. Gitignored. |

## 4. Layering (binding)

Dependency arrows may only point **downward**. A module that needs something
from a higher layer is a design error — stop and report.

```
entrypoints/  ──►  core/        ──►  agents.py  ──►  adapters/  ──►  (OpenRouter / DeepSeek, files, web)
   (cli.py)      (controller,      (definitions)   (openrouter,
                  rubric, verify)                   tools, formats)
```

- **entrypoints/** — thin CLI driver: parse args, validate the `DocSpec`, load
  `.env`, dispatch to `create_mode`/`review_mode`, print results. No routing
  logic beyond mode selection.
- **core/** — the deterministic controller and its helpers. Owns every
  transition, the loop caps, the rubric, and the quote-verification. This is
  the part that makes the system *deterministic*; it is pure Python and
  unit-testable with the model client mocked. Never imports from
  `entrypoints/`.
- **agents.py** — declares the four agents (system prompt file, model tier,
  scoped tools, guardrail). Consumed by the controller via `run_agent()`.
- **adapters/** — the only layer that touches the outside world: the model
  (OpenRouter through the OpenAI Agents SDK), the filesystem/web tools, and the
  format renderers. Externals are **injected** so tests mock them.
- **schemas/** — Pydantic models crossing layer boundaries (`DocSpec`,
  `Review`, `Verdict`). No behavior beyond validation.
- **config.py** — single source for every path, model slug, timeout, and loop
  cap. The only module that reads `os.environ`.

## 5. Model backend and per-agent tiers

All model access goes through **OpenRouter** (OpenAI-compatible gateway),
driven by the **OpenAI Agents SDK** pointed at OpenRouter's `base_url`. Two
DeepSeek tiers (`pro` / `flash`) plus a Qwen tier (`qwen_plus`, used only by the
Writer) are configured; the authoritative slugs and per-agent assignment live
in `feature_list.json` → `stack` (re-verify the `deepseek-v4-*` and
`qwen3.7-plus` slugs on OpenRouter at implementation time). This OpenRouter + OpenAI Agents SDK choice
is the locked decision in `feature_list.json`; it supersedes the
DeepSeek-direct / hand-rolled-loop option explored in `plan.md` (and resolves
that document's open question about using an aggregator).

| Agent | Tier | Tools (least privilege) | Why this tier |
|---|---|---|---|
| Researcher | **pro** (`deepseek/deepseek-v4-pro`) | read + web (read_file, grep, glob, web_search, web_fetch) | Only heavy multi-turn tool user; cheap-tier tool-calling is least reliable here, and a fabricated citation is a hard-to-reverse leak into the thesis. |
| Writer | **qwen_plus** (`qwen/qwen3.7-plus`) | read + write/edit drafts (read_file, grep, glob, write_file, edit_file) | Produces the deliverable and is the only agent that repairs its own work across many revision turns; gates detect but never fix. A different model family from the Pro Judge, so the terminal verifier no longer shares the generator's blind spots. |
| Reviewer | **flash** (`deepseek/deepseek-v4-flash`) | read-only (read_file, grep, glob) | Non-terminal, 2-pass soft gate backstopped by the Pro Judge — the one bounded place to spend the cheap tier. |
| Judge | **pro** (`deepseek/deepseek-v4-pro`) | read-only (read_file, grep, glob), `max_turns = 3` | Terminal gate with no downstream check; the reasoning itself must be strongest. |

Web tools are granted to the **Researcher only**, and only to resolve citation
metadata (DOI/URL → APA) for sources already present in `data/sources/` — never
to introduce a new source or claim. The Writer's `write_file`/`edit_file`
mirror the reference's `Write`+`Edit` and only write optional working copies
under `data/output/drafts/`; the Writer's returned text is the artifact of
record.

## 6. Guardrails enforced in code (not by prompt)

These are the invariants that make routing deterministic and the gate
trustworthy. They live in `core/` and `adapters/`, and are enforced regardless
of what any agent outputs:

1. **Loop caps** — `MAX_REVIEW_PASSES` and `MAX_JUDGE_RETRIES` are integer
   counters in the controller. A final Judge rejection after the cap does
   **not** escalate to a human: the run still completes and still renders its
   output; the controller records the unapproved verdict alongside it. Every
   run terminates in bounded time without a stdin pause.
2. **Single human touchpoint: mode selection** — the only point where a
   human decides anything is at CLI invocation, choosing `--mode
   create|review` (asked interactively if omitted, see §2). Once a mode
   starts, both `create` and `review` run unattended to a rendered output —
   no stdin gate, no mid-run approval, no edit-and-loop, no escalation.
3. **Structured output is validated in code** — Reviewer returns
   `{approved, feedback}`; Judge returns `{approved, perCriterionScores[],
   reasons[]}`. The controller **never routes on unvalidated free text**:
   responses are parsed and validated against their Pydantic schema, retried on
   failure. Because DeepSeek's native function-calling is unreliable (see
   `plan.md` / the BFCL finding), structured output is obtained by
   **prompting the schema + code-side validation**, not by trusting native
   tool-call JSON.
4. **Judge quote verification (anti-hallucinated-gating)** — every criterion
   score must carry a **verbatim span copied from the draft**.
   `verify_verdict_quotes()` normalizes and checks that (a) every rubric
   criterion is scored — a missing or unknown criterion id voids the verdict —
   (b) each quote meets a minimum length, and (c) each quote occurs verbatim in
   the draft. Any failure **voids the verdict** (forces `approved = false` with
   the reason appended) — in code, not by debate.
5. **Pre-tool-call deny gate** — a guardrail (the OpenAI Agents SDK's
   `tool_input_guardrail`, or an equivalent wrapper around the tool
   dispatcher) runs **before** any tool executes and denies: (a) nested
   agent/task spawning (routing belongs to the controller) and (b) any tool
   touching `.env` or other secrets. This is the direct port of the reference's
   `blockNestedAgents` / `blockSensitiveFiles` hooks.
6. **Per-agent least privilege** — each agent gets only the tools and model
   tier in §5. The Reviewer and Judge cannot write; only the Researcher has web
   access.
7. **Turn cap + usage accounting** — the Judge stage runs under an explicit
   `max_turns = 3` cap (as in the reference); the other stages are bounded by
   the loop caps in (1) rather than a per-stage turn cap (a per-stage
   `max_turns` stays configurable in `config.py`). Per-call token usage (and
   derived cost) is captured per stage for accounting.

## 7. The fixed rubric and the gate

The Judge scores against a **fixed, compiled-in rubric** (`core/rubric.py`) so
verdicts are comparable across runs. Six criteria, each scored 0–5 with a
passing threshold; **`approved` is true iff every criterion meets its
threshold**:

| id | Criterion | Pass ≥ |
|---|---|---|
| `grounding` | Grounding in sources (no fabricated/contradicted claims) | 4 / 5 |
| `references` | Complete, real APA 7th reference list; in-text ↔ entry parity | 4 / 5 |
| `scope` | Scope fidelity to the source-of-truth + all `DocSpec` requirements | 3 / 5 |
| `structure` | Follows the approved outline; coherent headings and transitions | 3 / 5 |
| `argument` | Claims developed with evidence, not merely asserted | 3 / 5 |
| `style` | Formal academic register, consistent citations | 3 / 5 |

**Hardening over the reference:** the reference gates on the Judge's own
top-level `approved` field (the Judge is prompt- and schema-bound to set it
true iff every criterion meets its threshold), with the quote check in §6.4 as
the only code-side override. This port additionally **recomputes** `approved`
in code as `all(score ≥ threshold)` from the per-criterion scores, so routing
never rests on the model's self-reported pass/fail — the same
distrust-the-model principle that motivates the quote verification. A verdict
must pass **both** the recomputed thresholds **and** the quote check to count as
an approval.

## 8. Structured output, the DocSpec, and formats

- **`DocSpec`** (`schemas/models.py`, Pydantic) is the input contract: `title`,
  `docType` (`"thesis-chapter"`), `format` (`"docx"` | `"pptx"`), `language`,
  `chapter{number, title}`, `audience`, `targetWords`, `citationStyle`,
  `requirements[]`, `notes`. Validated at the CLI boundary before any model call.
- **`Review`** = `{approved: bool, feedback: str}`; **`Verdict`** =
  `{approved: bool, perCriterionScores: CriterionScore[], reasons: str[]}` where
  `CriterionScore = {criterionId, score, quotedJustification, comment}`.
- **Formats** (`adapters/formats/`): `render_to_format(markdown, spec,
  output_dir, name_hint?)` slugifies a filename and routes to a renderer.
  `prose.py` renders the Writer's Markdown subset (`#`/`##`/`###` headings,
  paragraphs, `-`/`*` bullets, `1.` numbered items, `**bold**`/`*italic*`) to
  `.docx` via `python-docx`. `slides.py` (`.pptx`) is a stub that raises until
  implemented (`python-pptx` later). Adding a format = new renderer module + a
  case in the switch.

## 9. Configuration and secrets

- Every path, model slug, timeout, and loop cap comes from `config.py`, read
  from env vars with safe defaults. Nothing else reads `os.environ`.
- The **only** secret is `OPENROUTER_API_KEY`, read in `config.py` with **no**
  default; the app fails loudly at startup if it is missing. Never log it, never
  commit it. `.env` is gitignored; `.env.example` documents variable names only.
- `data/output/` is gitignored (generated artifacts); the `data/` inputs a user
  supplies are theirs to manage.

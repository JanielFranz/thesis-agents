# Implementation report — Feature 9 `controller`

Status: `in_progress` (awaiting reviewer). Not flipped to `done`.

## Files touched (within `paths`)
- `src/thesis_agents/core/controller.py` — **extended** (feature-4's
  `new_run_id`/`run_agent`/`AgentRunResult` + logging left intact; only added
  imports, constants, typed results, structured-output helpers, prompt builders,
  and the two state machines).
- `tests/unit/test_controller.py` — **new**.

No other module edited. No deviation from `paths`. No new dependency added.

## Public API added

```python
@dataclass(frozen=True, slots=True)
class CreateResult:
    run_id: str
    output_path: Path
    approved: bool          # code-recomputed / quote-verified, NOT model self-report
    verdict: Verdict
    review: Review | None
    review_passes: int      # loop-cap counter, for audit
    judge_passes: int

@dataclass(frozen=True, slots=True)
class ReviewResult:
    run_id: str
    output_path: Path
    approved: bool
    review: Review
    verdict: Verdict

async def create_mode(spec: DocSpec, client: OpenRouterClient, config: AppConfig,
                      *, agents: dict[str, AgentDefinition] | None = None) -> CreateResult
async def review_mode(document: str, spec: DocSpec, client: OpenRouterClient,
                      config: AppConfig, *, document_name: str | None = None,
                      agents: dict[str, AgentDefinition] | None = None) -> ReviewResult
```

`client`, `config`, and `agents` are all **injected**; `agents` defaults to
`build_agents(config, client)` but tests pass fakes. `config` (typed `AppConfig`)
supplies the loop caps, `output_dir`, and `trace_dir` — the controller reads no
env (config stays the sole `os.environ` reader).

## create_mode flow (architecture §2.1)
`new_run_id()` once → threaded through every `run_agent()` call:
Researcher → Writer(outline) → Writer(draft) → Reviewer↔Writer loop →
Judge↔Writer loop → `render_to_format(draft, spec, config.output_dir)`.
Unattended: no human checkpoints.

## review_mode flow (architecture §2.2)
`new_run_id()` once → Reviewer(`_run_structured`→Review) → Judge
(`_run_structured`→Verdict, then `verify_verdict_quotes(verdict, document)`) →
`_review_report()` assembles Markdown → `render_to_format(report, spec,
output_dir, name_hint="review-report-<name>")`. **No Writer, no revision loop** —
proven by a test asserting `client.stages == ["reviewer", "judge"]`.

## How each requirement is met

**Loop caps as integer counters (§6.1).** Each loop is a `while <counter> <
config.max_*` with the counter incremented at the top. Review loop: run Reviewer;
`break` if `approved` OR counter reached the cap; otherwise Writer revises and
loops. Judge loop: identical shape against `max_judge_retries`. With an
always-negative agent the counters land exactly on the cap and the loop exits —
tests assert `client.stages.count("reviewer") == max_review_passes` and
`... "judge" == max_judge_retries`, plus one `writer_revision` between the two
review passes.

**Post-cap unapproved completion (§6.2).** After the Judge loop, if
`verdict.approved` is False the controller emits a structured
`logger.warning(event="create_shipped_unapproved", ...)`, then **still renders**
the draft and returns a `CreateResult` with `approved=False` and the unapproved
`verdict`. No human prompt, no infinite loop. Test
`test_create_mode_judge_cap_completes_unapproved` proves a rendered `.docx`
exists and `result.approved is False`.

**Never route on unvalidated free text (§6.3).** `_run_structured[StructuredT:
BaseModel]` runs the stage via `run_agent`, extracts the first `{...}` object
with `_extract_json_object` (tolerates code fences / surrounding prose), and
validates with `schema.model_validate`. On `ValueError`/`json.JSONDecodeError`/
`ValidationError` it re-runs the stage up to `DEFAULT_MAX_PARSE_RETRIES` (2) extra
times, logging a `structured_parse_retry` warning each time, then returns `None`.
Callers fail safe: Reviewer `None` → `Review(approved=False, ...)`; Judge `None`
→ `Verdict(approved=False, [], [...])`. Routing reads only validated fields.
Test `test_create_mode_reviewer_parse_failure_fails_safe` exercises the safe
fallback.

**Verify gate overrides the model (§6.4/§7).** The Judge's raw `Verdict` is
**always** passed through `verify_verdict_quotes(raw_verdict, draft)`; the
controller routes on that returned object's `approved` (recomputed thresholds +
quote check), never `raw_verdict.approved`.
`test_create_mode_verify_gate_overrides_model_self_report` sends a verdict with
`approved=True` but a fabricated grounding quote absent from the draft →
`result.approved is False` and a "verbatim" reason.
`test_create_mode_judge_cap_completes_unapproved` sends `approved=True` with a
sub-threshold grounding score → recompute flips it to False.

**Shared run_id.** `test_create_mode_threads_one_shared_run_id` collects every
controller `run_agent` INFO line and asserts `{run_ids} == {result.run_id}`.

## Async-test approach (no new dependency)
Reused feature-4's exact pattern: the async entrypoints are driven with
`asyncio.run(create_mode(...))` / `asyncio.run(review_mode(...))`, and the client
is a hand-written fake with an `async def run_stage(...)`. **No pytest-asyncio or
any other new dep** was added — confirmed: `pyproject.toml`/`uv.lock` unchanged.
The `config` fixture builds a real `AppConfig` via `load_config()` (dummy key
from `conftest`) and `dataclasses.replace(..., output_dir=tmp_path,
trace_dir=None)`, so rendered `.docx` files land in `tmp_path` (real temp dir, no
filesystem mocking).

## Layering / conventions
`controller.py` imports only `config`, `adapters/formats`, `adapters/openrouter`,
`agents`, `core.rubric`, `core.verify`, `schemas` — never `entrypoints`. Typed
results (§4), `from __future__ import annotations`, full hints, structured
`logger` lines (no `print`), ruff line length 88.

## Self-verification (pasted output)

1. `uv run ruff check .` → `All checks passed!`
2. `uv run ruff format --check .` → `26 files already formatted`
3. `uv run pytest tests -q -m "not integration"` → `91 passed in 5.48s`
   (includes the 7 new controller tests AND the pre-existing feature-4
   `test_agent_result_logging.py` tests — no regression).
   With the secret unset:
   `env -u OPENROUTER_API_KEY uv run pytest tests/unit/test_controller.py -q`
   → `7 passed in 1.44s`.
4. `bash init.sh` →
   `feature_list.json valid (10 features, 8 done, 1 in progress)`,
   `91 passed`, `[OK] Environment ready.`, `EXIT=0`.

## Notes for the reviewer
- Loop-cap interpretation: `MAX_REVIEW_PASSES` / `MAX_JUDGE_RETRIES` bound the
  number of Reviewer / Judge **runs** (not the revisions after the first). With
  an always-negative agent this yields `cap` reviewer/judge calls and `cap - 1`
  intervening writer revisions — the counter is never exceeded.
- Fail-safe on unparseable structured output = treat as not-approved (documented
  in `_run_structured` / `_unparsed_review` / `_unparsed_verdict`), chosen over
  raising so an unattended run still completes and records the reason.

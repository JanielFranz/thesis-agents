# Review — feature 7 verify

**Verdict:** APPROVED

## Independent verification (secret stripped; OPENROUTER_API_KEY unset)
- `uv run ruff check .` → `All checks passed!`
- `uv run ruff format --check .` → `22 files already formatted`
- `uv run pytest tests -q -m "not integration"` → `71 passed` (11 new in test_verify.py); green with key unset
- `bash init.sh` → `[OK] Environment ready.` EXIT=0
- `git diff HEAD -- pyproject.toml uv.lock` → empty (no new dependency)
- feature 7 = `in_progress` (not self-flipped); exactly one in_progress; deps [5,6] done
- Purity: grep for `os.environ`/`getenv` under `src/` → no matches; verify.py imports only `rubric` + `Verdict`; no I/O, no model calls (config.py remains sole env reader)

## Acceptance criteria
- "normalizes + checks (a) coverage/missing/unknown voids, (b) min length, (c) verbatim after normalization" → met. verify.py: 1a unknown (L77-83), 1b duplicate extra (L86-97), 1c missing (L100-105), min-length (L112-118), verbatim-presence (L119-124). Normalization `_normalize` L60.
- "any failure forces approved=false, reason appended, in code" → met. Each void path sets its flag False and appends a human-readable reason; final `approved = coverage_ok and quotes_ok and thresholds_ok` (L146).
- "approved recomputed as all(score>=threshold) from per-criterion scores vs rubric; approval needs BOTH thresholds AND quote check" → met. `thresholds_ok = rubric.is_passing(scores)` (L134); model's `verdict.approved` is never read. Composition is a plain three-way AND of independently-computed flags — no short-circuit can mask a failing check. Proven by test_single_subthreshold_score_flips_approved_via_recompute (model approved=True, grounding=3<4 → approved=False).
- "returns a typed result, never free text" → met. Returns a new Pydantic-revalidated `Verdict` (L148-152); input not mutated (reasons copied L70; new score list L150); test_input_verdict_is_not_mutated + test_original_reasons_are_preserved confirm.
- "unit tests assert stays-approved / fabricated voids / missing|unknown voids / subthreshold flips" → met. All four plus duplicate, too-short, normalization, immutability, reason-preservation. Every test asserts the concrete `approved` bool AND the specific reason substring — none assert only "no exception".
- "ruff clean; init.sh green" → met (see above).

## Security scrutiny (primary defense against false APPROVE)
- All five void conditions each have a test asserting concrete approved=False + reason: unknown, duplicate, missing, too-short, absent-verbatim.
- Empty / malformed perCriterionScores fail safe: missing-all → coverage_ok=False and is_passing({})=False → approved=False.
- Threshold recompute filters `scores` to known ids only (L129-133), so a duplicate/unknown id cannot smuggle a passing score; and any duplicate already sets coverage_ok=False independently.
- No way found for genuinely fabricated/unsupported text (a quote not present in the draft) to pass: verbatim-presence (L119) is an unconditional AND term.

## Non-blocking notes (not required changes)
1. Case-folding + whitespace-collapse normalization is a reasonable reading of §6.4 "verbatim after normalization"; case-insensitivity does not let materially different text pass (same words, same order). Acceptable.
2. The min-length guard (L112) measures `quotedJustification.strip()` raw length, not the *normalized* length. A quote padded with interior whitespace (e.g. "the\n\n\n\n\nend") can satisfy the 12-char length while its normalized content ("the end", 7 chars) is shorter than MIN_QUOTE_CHARS. This weakens the anti-coincidence guard but does NOT admit fabricated text — the normalized span must still occur verbatim in the draft. Consider measuring `len(_normalize(quote))` in a future hardening pass. Non-blocking per the review standard (no fabricated/unsupported quote gets through).

## Checkpoints
- C1: [x] harness intact; init.sh exit 0
- C2: [x] one in_progress (7); deps 5,6 done; no dep violated; current.md describes active session
- C3: [x] verify.py sits in core/, imports only rubric + schemas (downward); rubric imported not duplicated; typed Verdict crosses boundary; no hard-coded paths/secrets; no new dep; no stray print/TODO
- C4: [x] test_verify.py present; asserts concrete approved+reason; pure in-memory (no network/fs/env); pytest -m "not integration" > 0 and green
- C5: [x] no suspicious artifacts (only the two feature paths + progress logs untracked); feature left in_progress correctly for reviewer gate

## Required Changes
None.

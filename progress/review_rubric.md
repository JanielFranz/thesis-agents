# Review — feature 6 rubric
**Verdict:** APPROVED

## Acceptance criteria
- "Fixed six-criterion rubric compiled-in per architecture §7: grounding (>=4), references (>=4), scope (>=3), structure (>=3), argument (>=3), style (>=3), each scored 0..5" → met. `core/rubric.py:34-76` defines `RUBRIC` as a tuple of frozen `Criterion` with ids grounding/references/scope/structure/argument/style and thresholds 4/4/3/3/3/3; `MIN_SCORE=0`/`MAX_SCORE=5` (`rubric.py:18-19`). No missing/extra criterion, no wrong threshold.
- "rubric_to_text() returns text listing every criterion id, description, and threshold, for the Judge prompt" → met. `rubric.py:104-120` emits a header (0..5 range + approved-iff-all-pass rule) plus one bullet per criterion `- <id> (pass >= <threshold>): <description>`. Test `test_rubric_to_text_mentions_every_criterion` (`test_rubric.py:46-51`) asserts non-empty and that every id + every threshold value appears.
- "A helper exposes criterion ids and thresholds for parity; passing rule documented: approved iff every criterion meets its threshold" → met. `criterion_ids()` (`rubric.py:79`), `criterion_thresholds()` (`rubric.py:84`), `is_passing()` (`rubric.py:89`). Passing rule documented in module docstring (`rubric.py:8-11`) and the `rubric_to_text` header. These give feature 7 what it needs: `criterion_thresholds()` yields the {id: threshold} set to detect missing/unknown ids and to recompute all(score>=threshold); `is_passing()` is a ready recompute helper.
- "Unit tests assert the exact set of six ids and thresholds, and that rubric_to_text() mentions each" → met. `test_rubric_has_exactly_six_expected_ids` + `test_rubric_thresholds_match_spec` (`test_rubric.py:30-38`) assert the exact id set/order and the exact {id:threshold} map; `is_passing` tested on a passing set (`:54`), a sub-threshold-failing set (`:59`), and a missing-criterion set (`:65`); immutability tested (`:71`). No "no-exception-only" tests.
- "uv run ruff check . clean; bash init.sh green" → met. Independently ran (key unset): `ruff check` = All checks passed; `ruff format --check` = 20 files already formatted; `pytest -m "not integration"` = 61 passed (incl. 8 new feature-6 tests); `bash init.sh` = [OK] Environment ready, EXIT=0.

## Cross-file id consistency (feature 7 precondition)
- rubric.py ids/thresholds vs prompts/judge.md table (`judge.md:15-24`): grounding=4, references=4, scope=3, structure=3, argument=3, style=3 — exact match on both ids and thresholds. judge.md instructs "score all six, using exactly these criterionId values." No divergence.

## Purity (§4)
- No `os.environ`, no `schemas` import, no `open(`/`Path(` in rubric.py (grep clean). config.py remains the only env reader. RUBRIC is a tuple of `frozen=True, slots=True` dataclasses; mutation raises `FrozenInstanceError` (asserted `test_rubric.py:71-77`).

## State
- feature 6 still `in_progress` (not self-flipped to done). Exactly one `in_progress`; features 1-5 `done`; dep [1] done. No dependency added — `git diff` on pyproject.toml/uv.lock empty.

## Checkpoints
- C1: [x] harness intact; init.sh exit 0.
- C2: [x] one in_progress (6); no feature ahead of its deps; done features' tests pass; current.md describes the active session.
- C3: [x] rubric.py sits in core/ with no upward/outward deps, pure data, no hard-coded secrets/paths, no stray print/TODO; no new dep.
- C4: [x] test_rubric.py present; asserts concrete ids/thresholds/text/passing branches; no network/fs; 61 green.
- C5: [x] no suspicious artifacts (only expected new files); feature reflected as in_progress; no new entrypoint to document.

## Required Changes
None.

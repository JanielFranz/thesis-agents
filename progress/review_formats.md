# Review — feature 8 formats
**Verdict:** APPROVED

## Acceptance criteria
- "render_to_format(markdown, spec, output_dir, name_hint=None) ... slugifies ... routes by spec.format ... output_dir from caller, not hard-coded" → met. `__init__.py:44-70` has exact signature, slugifies base (`slugify(base)`), routes docx→`prose.render_docx` / pptx→`slides.render_pptx`, `output_dir` is caller-provided (`Path(output_dir)`, `mkdir`). Grep confirms `data/output` appears only in a docstring, never as code.
- "prose.py renders the Writer's Markdown subset (#/##/### headings, paragraphs, -/* bullets, 1. numbered, **bold**/*italic*) to .docx via python-docx and returns path under output_dir" → met. `prose.py:27-33` regexes cover exactly the documented subset; `render_docx` builds a `docx.Document` and returns `output_path` (prose.py:89-90). Test reopens the file and asserts headings, paragraph, bullet, numbered text present.
- "slides.py (.pptx) is a stub that raises NotImplementedError" → met. `slides.py:24-29` always raises `NotImplementedError`; asserted by `test_render_to_format_pptx_raises_not_implemented`.
- "python-docx added via uv add with exact pin (pyproject.toml + uv.lock)" → met. `pyproject.toml:8` `python-docx==1.1.2`; uv.lock:597-602 package + specifier `==1.1.2` (uv.lock:813). python-pptx NOT present; lxml is the expected transitive.
- "Unit tests (tmp_path, no fs mocking) assert docx content reflects Markdown; pptx raises; slugify expected" → met. `test_formats.py` uses `tmp_path` throughout (no mocking); reopens `.docx` with `docx.Document` asserting concrete heading/paragraph/bullet/numbered text (test:48-67) AND `run.bold`/`run.italic` True runs (test:70-94); pptx raises (test:115-119); parametrized slugify incl. `""`/`"***"`→`document` (test:122-136).
- "ruff check clean; init.sh green" → met (measured below).

## Independent verification (secret stripped, OPENROUTER_API_KEY unset)
- `uv run ruff check .` → All checks passed!
- `uv run ruff format --check .` → 25 files already formatted
- `uv run pytest tests -q -m "not integration"` → 84 passed (13 in test_formats.py)
- `bash init.sh` → [OK] Environment ready. EXIT=0

## Parser sanity (documented subset)
- `**bold**` not mis-parsed as two italics: inline regex bold-alternative first (`prose.py:33`) + `_add_inline` checks `startswith("**")` first (prose.py:41). Correct.
- Leading `*italic*` not mistaken for a bullet: `_BULLET_RE` requires `\s+` after the marker (prose.py:29); `*italic*` has no space after `*`. Correct.

## Checkpoints
- C1: [x] harness intact, init.sh exit 0.
- C2: [x] exactly one in_progress (id 8); dep [5] done; feature 8 NOT self-flipped to done; current.md describes active session.
- C3: [x] layering holds — `adapters/formats/` imports only `schemas.models` + stdlib + `docx` (no core/agents/entrypoints); DocSpec typed model crosses boundary; no hard-coded paths/secrets; python-docx==1.1.2 exact-pinned + locked; no stray print/TODO.
- C4: [x] test file per module; tests assert concrete content (reopened docx, bold/italic runs, slug cases), not just "no exception"; no external service; tmp_path used; 13 tests green.
- C5: [x] no stray artifacts in git status (only feature paths + progress); feature reflected as in_progress. (history.md entry is a session-close task, not blocking this feature review.)

## Required Changes
None.

# Implementation report — Feature 8 `formats`

Status: `in_progress` (awaiting reviewer approval; NOT flipped to `done`).
Depends on: [5] `schemas` (done).

## Scope

Implemented the format renderers + the `render_to_format` switch per
architecture.md §8. Touched only the files in the feature's `paths`.

## Files touched

- `src/thesis_agents/adapters/formats/__init__.py` — replaced the empty stub
  with `slugify()` + `render_to_format()` (the switch).
- `src/thesis_agents/adapters/formats/prose.py` — new; `render_docx()`
  (Markdown subset → `.docx` via python-docx).
- `src/thesis_agents/adapters/formats/slides.py` — new; `render_pptx()` stub
  that raises `NotImplementedError`.
- `tests/unit/test_formats.py` — new unit tests.
- `pyproject.toml` + `uv.lock` — `python-docx` dependency (via `uv add`).

No deviation from `paths`. `config.py` untouched (formats read no env;
`output_dir` is a caller-provided `Path`).

## Dependency

- `python-docx==1.1.2` added with `uv add python-docx==1.1.2` (exact pin,
  landed in `pyproject.toml` dependencies + `uv.lock`). Transitively pulled
  `lxml==6.1.1`. Import name is `docx`. Compatible with Python 3.14.5 on
  win32 — no build issues.

## Signatures

- `slugify(text: str) -> str`
- `render_to_format(markdown: str, spec: DocSpec, output_dir: Path,
  name_hint: str | None = None) -> Path`
- `prose.render_docx(markdown: str, spec: DocSpec, output_path: Path) -> Path`
- `slides.render_pptx(markdown: str, spec: DocSpec, output_path: Path) -> Path`
  (always raises `NotImplementedError`)

## Routing / behavior

- `render_to_format` builds the filename base from `name_hint` if given, else
  `spec.title`; slugifies it; appends the extension from `spec.format`
  (`docx`→`.docx`, `pptx`→`.pptx`); creates `output_dir` with `pathlib` if
  missing; routes `docx`→`prose.render_docx`, `pptx`→`slides.render_pptx`.
  `output_dir` is always the caller's — never hard-coded `data/output/`.

## Markdown subset handled (prose.py)

Small, line-oriented parser (not full CommonMark):

- `#`/`##`/`###` headings → `document.add_heading(text, level=1|2|3)`
  (matched by `^(#{1,3})\s+(.*)$`).
- `-`/`*` bullets → `add_paragraph(style="List Bullet")`
  (`^[-*]\s+(.*)$`; requires whitespace after the marker so `*italic*`
  inline is not mistaken for a bullet).
- `1.` numbered items → `add_paragraph(style="List Number")`
  (`^\d+\.\s+(.*)$`).
- Blank lines separate/skip; every other non-blank line → a plain paragraph.
- Inline `**bold**` / `*italic*` via `_add_inline()`: splits on
  `(\*\*.+?\*\*|\*.+?\*)` (bold alternative first so `**x**` isn't parsed as
  two italics), emits `run.bold=True` / `run.italic=True` runs, plain text
  otherwise. Applied to paragraphs, bullets and numbered items.

## slugify sanitization

`_NON_ALNUM_RE = [^a-z0-9]+` on the lowercased text → single hyphens, then
`.strip("-")`. Empty or fully non-alphanumeric input falls back to
`"document"` (non-empty guarantee). Examples asserted in tests:
`"Chapter 1: Intro!!! (draft)"`→`chapter-1-intro-draft`,
`"Hello___World"`→`hello-world`, `""`/`"***"`→`document`,
`"---already---"`→`already`.

## How the docx round-trip test asserts content

`test_render_to_format_docx_writes_file_reflecting_markdown` renders a
multi-element Markdown string, asserts the returned path exists, ends `.docx`,
lives under `tmp_path`, then reopens it with `docx.Document(path)` and asserts
concrete paragraph texts are present: the heading `"Main Heading"`, the
subsection heading `"Subsection"`, the intro paragraph with emphasis markers
stripped (`"This is an intro paragraph with bold text and italic text."`), and
bullet/numbered item text. A second test reopens the doc and asserts a
`**bold**` span produced a run with `run.bold` True and a `*italic*` span a
run with `run.italic` True. The `pptx` test asserts `NotImplementedError`.
No filesystem mocking — real `tmp_path`.

## Layering

`adapters/formats/` imports only `schemas.models` (for `DocSpec`), stdlib
(`re`, `pathlib`), and `docx`. No import of `core/`, `agents.py`, or
`entrypoints/`.

## Verification (pasted output)

1. `uv run ruff check .`
```
All checks passed!
```

2. `uv run ruff format --check .`
```
25 files already formatted
```

3. `OPENROUTER_API_KEY= uv run pytest tests -q -m "not integration"`
   (real `.env` not consulted; conftest injects a dummy key so no test depends
   on the real secret)
```
........................................................................ [ 85%]
............                                                             [100%]
84 passed in 5.37s
```

4. `bash init.sh`
```
[OK]   feature_list.json valid (10 features, 7 done, 1 in progress)
...
84 passed in 3.36s
[OK]   Unit tests passed (integration tests excluded; ...)
[OK]   Environment ready. You can start working.
EXIT=0
```

"""Format renderers + the ``render_to_format`` switch (architecture.md §8).

This package is the only place the pipeline turns finished Markdown into a
deliverable file. :func:`render_to_format` slugifies a filename and routes by
:attr:`DocSpec.format <thesis_agents.schemas.models.DocSpec.format>` to a
concrete renderer:

- ``"docx"`` → :func:`prose.render_docx` (implemented, ``python-docx``);
- ``"pptx"`` → :func:`slides.render_pptx` (a stub that raises).

The ``output_dir`` is supplied by the caller (the controller passes a path from
``config.py``); nothing here reads the environment or hard-codes ``data/output``.
"""

from __future__ import annotations

import re
from pathlib import Path

from thesis_agents.schemas.models import DocSpec

from . import prose, slides

#: Fallback slug when the source text has no slug-able characters at all.
_SLUG_FALLBACK = "document"
#: Any run of characters that are not ASCII alphanumerics becomes a separator.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

#: File extension per supported format.
_EXTENSIONS = {"docx": ".docx", "pptx": ".pptx"}


def slugify(text: str) -> str:
    """Return a filesystem-safe, lowercase, hyphen-separated slug.

    Non-alphanumeric runs collapse to single hyphens; leading/trailing hyphens
    are stripped. An empty or fully non-alphanumeric input yields
    :data:`_SLUG_FALLBACK` so the result is always a usable, non-empty name.
    """
    slug = _NON_ALNUM_RE.sub("-", text.lower()).strip("-")
    return slug or _SLUG_FALLBACK


def render_to_format(
    markdown: str,
    spec: DocSpec,
    output_dir: Path,
    name_hint: str | None = None,
) -> Path:
    """Render ``markdown`` to a file under ``output_dir``, routed by format.

    :param markdown: the finished document as Markdown (the Writer's subset).
    :param spec: the document spec; ``spec.format`` selects the renderer.
    :param output_dir: caller-provided directory for the artifact (created if
        missing). Never hard-coded here (architecture §3.1 / §9).
    :param name_hint: optional basis for the filename; defaults to the spec
        title.
    :returns: the path of the written file.
    :raises NotImplementedError: for ``pptx`` (the slides renderer is a stub).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base = name_hint if name_hint is not None else spec.title
    extension = _EXTENSIONS[spec.format]
    output_path = output_dir / f"{slugify(base)}{extension}"

    if spec.format == "docx":
        return prose.render_docx(markdown, spec, output_path)
    return slides.render_pptx(markdown, spec, output_path)

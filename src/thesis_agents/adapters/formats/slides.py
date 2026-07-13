"""``.pptx`` renderer — documented stub (architecture.md §8).

The slides renderer is deliberately unimplemented in this build: the only
supported output format is ``.docx`` (see :mod:`prose`). Adding ``.pptx``
support means implementing :func:`render_pptx` with ``python-pptx`` and wiring
it into the :func:`render_to_format` switch — until then this raises so a
``pptx`` :class:`~thesis_agents.schemas.models.DocSpec` fails loudly rather than
silently producing nothing.
"""

from __future__ import annotations

from pathlib import Path

from thesis_agents.schemas.models import DocSpec

_NOT_IMPLEMENTED_MSG = (
    "pptx rendering is not yet implemented; only 'docx' is supported in this "
    "build (architecture.md §8). Implement render_pptx with python-pptx to add "
    "it."
)


def render_pptx(markdown: str, spec: DocSpec, output_path: Path) -> Path:
    """Render Markdown to ``.pptx`` — not implemented.

    :raises NotImplementedError: always; the slides renderer is a stub.
    """
    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

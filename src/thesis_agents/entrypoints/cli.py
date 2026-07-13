"""CLI driver — the pipeline's composition root (architecture.md §4).

This is the **thin** entrypoint: it parses ``--spec`` / ``--mode`` / ``--input``,
loads ``.env`` into the environment, validates the :class:`DocSpec` at the
boundary (before any model call), builds the real :class:`OpenRouterClient`, and
dispatches to :func:`create_mode` / :func:`review_mode`. It holds **no routing
logic beyond mode selection** — the deterministic controller in ``core`` owns
every transition (architecture.md §2, §4). Mode selection is the pipeline's only
human interaction (architecture.md §6.2): if ``--mode`` is omitted the user is
asked once on stdin.

Layering: as the composition root this module may import ``config``, ``schemas``,
``core.controller`` and ``adapters.openrouter`` to wire the concrete client into
the controller. Nothing lower imports it.

Environment/secrets (architecture.md §9): ``.env`` is loaded **here** (a tiny
stdlib parser, no new dependency) so ``config.py`` remains the only module that
*reads* ``os.environ`` for application logic. Loading writes ``os.environ`` but
never overrides a value already present, and the secret value is never read or
logged. ``OPENROUTER_API_KEY`` is still resolved (and fail-loud validated) inside
``config.load_config()``, not here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from config import ROOT_DIR, AppConfig, ConfigError, load_config
from thesis_agents.adapters.openrouter import (
    OpenRouterClient,
    build_openrouter_client,
)
from thesis_agents.core.controller import create_mode, review_mode
from thesis_agents.schemas.models import DocSpec

logger = logging.getLogger(__name__)

#: Process exit codes.
EXIT_OK = 0
EXIT_USAGE = 2

#: Valid ``--mode`` values.
MODE_CREATE = "create"
MODE_REVIEW = "review"
VALID_MODES = (MODE_CREATE, MODE_REVIEW)


def _default_env_path() -> Path:
    """Repository ``.env`` path (overridable via ``--env-file``)."""
    return ROOT_DIR / ".env"


def load_env_file(path: Path) -> int:
    """Load ``KEY=VALUE`` lines from ``path`` into ``os.environ``.

    A minimal, dependency-free ``.env`` reader: blank lines and ``#`` comments
    are skipped, a leading ``export`` is tolerated, and surrounding single/double
    quotes are stripped. Existing environment values are **never overridden**, so
    a variable exported in the shell (or injected by the test harness) wins over
    the file. A missing file is not an error (returns 0). The secret value is
    never logged. Returns the number of variables newly set.
    """
    if not path.is_file():
        logger.info(json.dumps({"event": "env_load", "path": str(path), "found": 0}))
        return 0

    loaded = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or key in os.environ:
            continue
        os.environ[key] = value
        loaded += 1

    logger.info(json.dumps({"event": "env_load", "path": str(path), "loaded": loaded}))
    return loaded


def build_client(config: AppConfig) -> OpenRouterClient:
    """Construct the real :class:`OpenRouterClient` (mocked out in unit tests)."""
    return OpenRouterClient(config, build_openrouter_client(config))


def _load_spec(spec_path: Path) -> DocSpec:
    """Read and validate the ``DocSpec`` JSON at the CLI boundary.

    Raises :class:`ValueError` (with a clear message) on a missing file,
    malformed JSON, or a schema validation failure, so the caller can fail fast
    **before** constructing any client or calling the model.
    """
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read spec file {spec_path}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Spec file {spec_path} is not valid JSON: {exc}") from exc
    try:
        return DocSpec.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"Spec file {spec_path} is not a valid DocSpec:\n{exc}"
        ) from exc


def _resolve_mode(mode: str | None) -> str:
    """Return the run mode, prompting once on stdin if it was not given.

    This interactive prompt is the pipeline's only human interaction
    (architecture.md §6.2). Raises :class:`ValueError` on an unrecognized answer.
    """
    if mode is not None:
        return mode
    answer = input(f"Select mode {VALID_MODES}: ").strip().lower()
    if answer not in VALID_MODES:
        raise ValueError(f"Unknown mode {answer!r}; expected one of {VALID_MODES}.")
    return answer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thesis_agents",
        description=(
            "Generate a thesis chapter (create) or grade an existing document "
            "(review) from a DocSpec."
        ),
    )
    parser.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="Path to the DocSpec JSON file (validated before any model call).",
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default=None,
        help="Pipeline mode; asked interactively if omitted.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to the document to grade (required for --mode review).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to the .env file to load (default: repository .env).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse args, validate the spec, and dispatch to the controller.

    Returns ``0`` on success and a non-zero code on any boundary failure (bad
    args, unreadable/invalid spec, missing ``--input`` for review, missing
    secret). An invalid :class:`DocSpec` fails fast here — no client is built and
    the controller is never called.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse already printed the usage/error or help
        # --help exits 0; a bad argument exits 2. Preserve argparse's own code
        # (0 is falsy, so it must not be collapsed to EXIT_USAGE).
        return int(exc.code) if exc.code is not None else EXIT_USAGE

    env_path = args.env_file if args.env_file is not None else _default_env_path()
    load_env_file(env_path)

    # Boundary validation FIRST — before any client construction or model call.
    try:
        spec = _load_spec(args.spec)
    except ValueError as exc:
        print(f"error: {exc}")
        return EXIT_USAGE

    try:
        mode = _resolve_mode(args.mode)
    except ValueError as exc:
        print(f"error: {exc}")
        return EXIT_USAGE

    document: str | None = None
    if mode == MODE_REVIEW:
        if args.input is None:
            print("error: --input <file> is required for --mode review.")
            return EXIT_USAGE
        try:
            document = args.input.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read input document {args.input}: {exc}")
            return EXIT_USAGE

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"error: {exc}")
        return EXIT_USAGE

    client = build_client(config)

    if mode == MODE_CREATE:
        result = asyncio.run(create_mode(spec, client, config))
    else:
        assert document is not None
        result = asyncio.run(
            review_mode(document, spec, client, config, document_name=args.input.stem)
        )

    verdict = "APPROVED" if result.approved else "NOT APPROVED"
    print(f"{mode} complete: {verdict}")
    print(f"output: {result.output_path}")
    return EXIT_OK


__all__ = [
    "EXIT_OK",
    "EXIT_USAGE",
    "build_client",
    "load_env_file",
    "main",
]

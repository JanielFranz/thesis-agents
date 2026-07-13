"""Enable ``python -m thesis_agents`` — delegates to the CLI entrypoint."""

from __future__ import annotations

from thesis_agents.entrypoints.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

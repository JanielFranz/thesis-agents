"""Shared pytest fixtures for the thesis-agents-python suite.

Test isolation: unit tests must never read the real ``.env`` or reach a real
service. The autouse ``_isolate_env`` fixture strips any inherited
``OPENROUTER_API_KEY`` and injects a dummy one, so ``load_config()`` succeeds
deterministically without the real secret. Individual tests that need the
secret unset (error-path tests) can delete it via ``monkeypatch`` themselves.
"""

from __future__ import annotations

import pytest

DUMMY_API_KEY = "test-openrouter-key-not-a-real-secret"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a dummy API key so tests never depend on the real .env."""
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY_API_KEY)

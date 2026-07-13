"""Unit tests for the CLI composition root (feature 10).

Fully offline: the async controller entrypoints (``create_mode`` /
``review_mode``) and the client builder are monkeypatched, so no network, no
real model, and no real client is constructed. ``.env`` loading is pointed at a
nonexistent tmp path so the real repository ``.env`` is never consulted. The
dummy ``OPENROUTER_API_KEY`` comes from the autouse conftest fixture, so
``load_config()`` succeeds without the real secret.

Tests assert concrete results: the return code, which mode was dispatched (with
the parsed ``DocSpec`` / document text), that an invalid spec is rejected at the
boundary with **no** controller call, and that a missing ``--mode`` runs the
interactive prompt path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from thesis_agents.entrypoints import cli
from thesis_agents.schemas.models import DocSpec

VALID_SPEC = {
    "title": "Chapter One",
    "docType": "thesis-chapter",
    "format": "docx",
    "language": "en",
    "chapter": {"number": 1, "title": "Introduction"},
    "audience": "thesis committee",
    "targetWords": 3000,
    "citationStyle": "APA",
    "requirements": ["cover the research question"],
    "notes": "first chapter",
}


@dataclass
class _FakeResult:
    """Stand-in for CreateResult / ReviewResult (only what the CLI prints)."""

    approved: bool
    output_path: Path


def _write_spec(tmp_path: Path, payload: dict[str, object]) -> Path:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(payload), encoding="utf-8")
    return spec_path


def _missing_env(tmp_path: Path) -> Path:
    """A .env path that does not exist, so the real repo .env is never read."""
    return tmp_path / "does-not-exist.env"


class _Recorder:
    """Records the last call to an async controller stub."""

    def __init__(self, approved: bool = True) -> None:
        self.called = False
        self.args: tuple[object, ...] = ()
        self.kwargs: dict[str, object] = {}
        self._approved = approved

    async def __call__(self, *args: object, **kwargs: object) -> _FakeResult:
        self.called = True
        self.args = args
        self.kwargs = kwargs
        return _FakeResult(approved=self._approved, output_path=Path("out/doc.docx"))


@pytest.fixture
def stub_controllers(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_Recorder, _Recorder]:
    """Replace create_mode/review_mode and the client builder (no network)."""
    create = _Recorder(approved=True)
    review = _Recorder(approved=False)
    monkeypatch.setattr(cli, "create_mode", create)
    monkeypatch.setattr(cli, "review_mode", review)
    monkeypatch.setattr(cli, "build_client", lambda config: object())
    return create, review


def test_main_create_dispatches_create_mode_with_parsed_spec(
    tmp_path: Path, stub_controllers: tuple[_Recorder, _Recorder]
) -> None:
    create, review = stub_controllers
    spec_path = _write_spec(tmp_path, VALID_SPEC)

    rc = cli.main(
        [
            "--spec",
            str(spec_path),
            "--mode",
            "create",
            "--env-file",
            str(_missing_env(tmp_path)),
        ]
    )

    assert rc == cli.EXIT_OK
    assert create.called is True
    assert review.called is False
    spec_arg = create.args[0]
    assert isinstance(spec_arg, DocSpec)
    assert spec_arg.title == "Chapter One"
    assert spec_arg.chapter.number == 1


def test_main_review_dispatches_review_mode_with_document_text(
    tmp_path: Path, stub_controllers: tuple[_Recorder, _Recorder]
) -> None:
    create, review = stub_controllers
    spec_path = _write_spec(tmp_path, VALID_SPEC)
    doc_path = tmp_path / "submission.md"
    doc_path.write_text("# Submitted draft\n\nBody text.", encoding="utf-8")

    rc = cli.main(
        [
            "--spec",
            str(spec_path),
            "--mode",
            "review",
            "--input",
            str(doc_path),
            "--env-file",
            str(_missing_env(tmp_path)),
        ]
    )

    assert rc == cli.EXIT_OK
    assert review.called is True
    assert create.called is False
    # review_mode(document, spec, client, config, *, document_name=...)
    assert review.args[0] == "# Submitted draft\n\nBody text."
    assert isinstance(review.args[1], DocSpec)
    assert review.kwargs["document_name"] == "submission"


def test_main_review_without_input_errors_before_dispatch(
    tmp_path: Path, stub_controllers: tuple[_Recorder, _Recorder]
) -> None:
    create, review = stub_controllers
    spec_path = _write_spec(tmp_path, VALID_SPEC)

    rc = cli.main(
        [
            "--spec",
            str(spec_path),
            "--mode",
            "review",
            "--env-file",
            str(_missing_env(tmp_path)),
        ]
    )

    assert rc == cli.EXIT_USAGE
    assert review.called is False
    assert create.called is False


def test_main_invalid_spec_rejected_at_boundary_no_model_call(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    stub_controllers: tuple[_Recorder, _Recorder],
) -> None:
    create, review = stub_controllers
    bad = dict(VALID_SPEC)
    bad["format"] = "pdf"  # not a valid DocFormat enum value
    spec_path = _write_spec(tmp_path, bad)

    rc = cli.main(
        [
            "--spec",
            str(spec_path),
            "--mode",
            "create",
            "--env-file",
            str(_missing_env(tmp_path)),
        ]
    )

    assert rc == cli.EXIT_USAGE
    # Boundary validation happens BEFORE any model call.
    assert create.called is False
    assert review.called is False
    out = capsys.readouterr().out
    assert "error" in out.lower()
    assert "DocSpec" in out


def test_main_missing_required_field_rejected_at_boundary(
    tmp_path: Path, stub_controllers: tuple[_Recorder, _Recorder]
) -> None:
    create, review = stub_controllers
    bad = dict(VALID_SPEC)
    del bad["title"]
    spec_path = _write_spec(tmp_path, bad)

    rc = cli.main(
        [
            "--spec",
            str(spec_path),
            "--mode",
            "create",
            "--env-file",
            str(_missing_env(tmp_path)),
        ]
    )

    assert rc == cli.EXIT_USAGE
    assert create.called is False
    assert review.called is False


def test_main_missing_mode_triggers_interactive_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_controllers: tuple[_Recorder, _Recorder],
) -> None:
    create, review = stub_controllers
    spec_path = _write_spec(tmp_path, VALID_SPEC)
    prompts: list[str] = []

    def fake_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return "create"

    monkeypatch.setattr("builtins.input", fake_input)

    rc = cli.main(["--spec", str(spec_path), "--env-file", str(_missing_env(tmp_path))])

    assert rc == cli.EXIT_OK
    assert prompts, "interactive prompt was not shown"
    assert create.called is True
    assert review.called is False


def test_main_missing_spec_argument_returns_usage_code(
    tmp_path: Path, stub_controllers: tuple[_Recorder, _Recorder]
) -> None:
    create, review = stub_controllers
    rc = cli.main(["--mode", "create", "--env-file", str(_missing_env(tmp_path))])
    assert rc == cli.EXIT_USAGE
    assert create.called is False
    assert review.called is False


def test_main_help_returns_zero(
    capsys: pytest.CaptureFixture[str],
    stub_controllers: tuple[_Recorder, _Recorder],
) -> None:
    create, review = stub_controllers
    rc = cli.main(["--help"])
    assert rc == cli.EXIT_OK
    assert create.called is False
    assert review.called is False
    assert "usage" in capsys.readouterr().out.lower()


def test_load_env_file_sets_new_vars_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\nNEW_ONLY_VAR=fresh\nexport ALREADY_SET=fromfile\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NEW_ONLY_VAR", raising=False)
    monkeypatch.setenv("ALREADY_SET", "fromshell")

    loaded = cli.load_env_file(env_path)

    import os

    assert os.environ["NEW_ONLY_VAR"] == "fresh"
    # Existing shell value is never overridden.
    assert os.environ["ALREADY_SET"] == "fromshell"
    assert loaded == 1


def test_load_env_file_missing_file_is_noop(tmp_path: Path) -> None:
    assert cli.load_env_file(tmp_path / "nope.env") == 0

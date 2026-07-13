"""Unit tests for the root config module (feature 1 — project_skeleton)."""

from __future__ import annotations

from pathlib import Path

import pytest

import config
from config import (
    DEFAULT_MAX_JUDGE_RETRIES,
    DEFAULT_MAX_REVIEW_PASSES,
    DEFAULT_MODEL_FLASH,
    DEFAULT_MODEL_PRO,
    DEFAULT_OPENROUTER_BASE_URL,
    AppConfig,
    ConfigError,
    load_config,
)


def test_load_config_returns_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-key")
    cfg = load_config()

    assert isinstance(cfg, AppConfig)
    assert cfg.model_pro == DEFAULT_MODEL_PRO
    assert cfg.model_flash == DEFAULT_MODEL_FLASH
    assert cfg.openrouter_base_url == DEFAULT_OPENROUTER_BASE_URL
    assert cfg.openrouter_api_key == "sentinel-key"


def test_load_config_uses_fixed_loop_caps() -> None:
    cfg = load_config()

    assert cfg.max_review_passes == DEFAULT_MAX_REVIEW_PASSES == 2
    assert cfg.max_judge_retries == DEFAULT_MAX_JUDGE_RETRIES == 2


def test_load_config_data_paths_are_under_root() -> None:
    cfg = load_config()

    assert cfg.data_dir == cfg.root_dir / "data"
    assert cfg.source_of_truth_dir == cfg.data_dir / "source-of-truth"
    assert cfg.sources_dir == cfg.data_dir / "sources"
    assert cfg.input_dir == cfg.data_dir / "input"
    assert cfg.output_dir == cfg.data_dir / "output"
    assert cfg.drafts_dir == cfg.output_dir / "drafts"
    assert all(isinstance(p, Path) for p in (cfg.data_dir, cfg.drafts_dir))


def test_load_config_missing_secret_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        load_config()


def test_load_config_empty_secret_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with pytest.raises(ConfigError):
        load_config()


def test_load_config_env_overrides_model_and_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL_PRO", "vendor/custom-pro")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "custom-data"))
    monkeypatch.setenv("MAX_REVIEW_PASSES", "5")

    cfg = load_config()

    assert cfg.model_pro == "vendor/custom-pro"
    assert cfg.data_dir == tmp_path / "custom-data"
    assert cfg.max_review_passes == 5


def test_importing_config_does_not_read_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Import-safety: module-level constants exist without any secret present.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert config.DEFAULT_MODEL_PRO == DEFAULT_MODEL_PRO
    assert config.ROOT_DIR.is_dir()

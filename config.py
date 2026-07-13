"""Central configuration for thesis-agents-python.

This is the **only** module that reads ``os.environ``. Every path, model slug,
timeout and loop cap the rest of the codebase needs is resolved here and handed
out as a typed :class:`AppConfig` via :func:`load_config`.

Import safety: importing this module never touches the environment beyond
defaults and never raises. The single required secret (``OPENROUTER_API_KEY``)
is read and validated lazily inside :func:`load_config`, so the unit suite can
import and exercise everything with the secret unset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- Fixed defaults (env-overridable where noted) -------------------------

#: Repository root — the directory that contains this file.
ROOT_DIR = Path(__file__).resolve().parent

#: Model slugs. Authoritative values live in feature_list.json -> stack.models;
#: these mirror them and are overridable via env so nothing is inlined at call
#: sites.
DEFAULT_MODEL_PRO = "deepseek/deepseek-v4-pro"
DEFAULT_MODEL_FLASH = "deepseek/deepseek-v4-flash"
DEFAULT_MODEL_QWEN_PLUS = "qwen/qwen3.7-plus"

#: Per-tier pricing (USD per 1M tokens) used to derive per-stage cost from token
#: usage. Defaults are 0.0 because the deepseek-v4-* / qwen3.7-plus slugs are
#: unverified on OpenRouter at implementation time; override via env once the
#: slugs and their prices are confirmed. Cost derivation is still exercised by
#: the unit tests via explicit env overrides.
DEFAULT_PRICE_INPUT_PER_MTOK = 0.0
DEFAULT_PRICE_OUTPUT_PER_MTOK = 0.0

#: Tier names, mirroring feature_list.json -> stack.models keys.
TIER_PRO = "pro"
TIER_FLASH = "flash"
TIER_QWEN_PLUS = "qwen_plus"

#: OpenRouter's OpenAI-compatible gateway (stack.model_provider.base_url).
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: Deterministic loop caps (architecture.md §6.1). Integer counters, not
#: instructions to the model.
DEFAULT_MAX_REVIEW_PASSES = 2
DEFAULT_MAX_JUDGE_RETRIES = 2

#: Per-stage turn cap default (architecture.md §6.7); the Judge stage overrides
#: this to 3 in its own definition.
DEFAULT_MAX_TURNS = 6

#: HTTP request timeout for model calls, in seconds.
DEFAULT_REQUEST_TIMEOUT_S = 120.0

#: Name of the required secret. Read with NO default; the app fails loudly if
#: it is missing.
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"


class ConfigError(RuntimeError):
    """Raised when required configuration (a secret) is missing or empty."""


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-tier token pricing in USD per 1M tokens, for cost accounting."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Typed, immutable snapshot of the application's configuration."""

    root_dir: Path

    # data/ I/O contract (architecture.md §3.1)
    data_dir: Path
    source_of_truth_dir: Path
    sources_dir: Path
    input_dir: Path
    output_dir: Path
    drafts_dir: Path

    # model backend (architecture.md §5)
    openrouter_base_url: str
    openrouter_api_key: str
    model_pro: str
    model_flash: str
    model_qwen_plus: str
    model_prices: dict[str, ModelPrice]

    # timeouts / caps (architecture.md §6)
    request_timeout_s: float
    max_turns: int
    max_review_passes: int
    max_judge_retries: int

    def models_by_tier(self) -> dict[str, str]:
        """Map each configured tier name to its model slug (never inline slugs)."""
        return {
            TIER_PRO: self.model_pro,
            TIER_FLASH: self.model_flash,
            TIER_QWEN_PLUS: self.model_qwen_plus,
        }

    def model_for_tier(self, tier: str) -> str:
        """Resolve a tier name to its configured model slug.

        Raises :class:`ConfigError` for an unknown tier so a typo never
        silently reaches the model backend.
        """
        try:
            return self.models_by_tier()[tier]
        except KeyError as exc:
            known = ", ".join(sorted(self.models_by_tier()))
            raise ConfigError(
                f"Unknown model tier {tier!r}; known tiers: {known}."
            ) from exc

    def price_for_tier(self, tier: str) -> ModelPrice:
        """Resolve a tier name to its :class:`ModelPrice` (0.0 if unpriced)."""
        # model_for_tier validates the tier name first.
        self.model_for_tier(tier)
        return self.model_prices.get(
            tier,
            ModelPrice(DEFAULT_PRICE_INPUT_PER_MTOK, DEFAULT_PRICE_OUTPUT_PER_MTOK),
        )


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value is not None and value != "" else default


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {value!r}") from exc


def _env_price(prefix: str) -> ModelPrice:
    """Read ``<prefix>_INPUT`` / ``<prefix>_OUTPUT`` USD-per-1M-token prices."""
    return ModelPrice(
        input_usd_per_mtok=_env_float(f"{prefix}_INPUT", DEFAULT_PRICE_INPUT_PER_MTOK),
        output_usd_per_mtok=_env_float(
            f"{prefix}_OUTPUT", DEFAULT_PRICE_OUTPUT_PER_MTOK
        ),
    )


def _require_secret(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise ConfigError(
            f"Required secret {name} is not set. "
            f"Add it to your .env (see .env.example) — it has no default."
        )
    return value


def load_config() -> AppConfig:
    """Build the :class:`AppConfig` from the environment with safe defaults.

    Raises :class:`ConfigError` if the required ``OPENROUTER_API_KEY`` secret is
    missing or empty. All other values fall back to the documented defaults.
    """
    root_dir = _env_path("ROOT_DIR", ROOT_DIR)
    data_dir = _env_path("DATA_DIR", root_dir / "data")
    output_dir = _env_path("OUTPUT_DIR", data_dir / "output")

    model_prices = {
        TIER_PRO: _env_price("OPENROUTER_PRICE_PRO"),
        TIER_FLASH: _env_price("OPENROUTER_PRICE_FLASH"),
        TIER_QWEN_PLUS: _env_price("OPENROUTER_PRICE_QWEN_PLUS"),
    }

    return AppConfig(
        root_dir=root_dir,
        data_dir=data_dir,
        source_of_truth_dir=_env_path(
            "SOURCE_OF_TRUTH_DIR", data_dir / "source-of-truth"
        ),
        sources_dir=_env_path("SOURCES_DIR", data_dir / "sources"),
        input_dir=_env_path("INPUT_DIR", data_dir / "input"),
        output_dir=output_dir,
        drafts_dir=_env_path("DRAFTS_DIR", output_dir / "drafts"),
        openrouter_base_url=_env_str(
            "OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL
        ),
        openrouter_api_key=_require_secret(OPENROUTER_API_KEY_ENV),
        model_pro=_env_str("OPENROUTER_MODEL_PRO", DEFAULT_MODEL_PRO),
        model_flash=_env_str("OPENROUTER_MODEL_FLASH", DEFAULT_MODEL_FLASH),
        model_qwen_plus=_env_str("OPENROUTER_MODEL_QWEN_PLUS", DEFAULT_MODEL_QWEN_PLUS),
        model_prices=model_prices,
        request_timeout_s=_env_float("REQUEST_TIMEOUT_S", DEFAULT_REQUEST_TIMEOUT_S),
        max_turns=_env_int("MAX_TURNS", DEFAULT_MAX_TURNS),
        max_review_passes=_env_int("MAX_REVIEW_PASSES", DEFAULT_MAX_REVIEW_PASSES),
        max_judge_retries=_env_int("MAX_JUDGE_RETRIES", DEFAULT_MAX_JUDGE_RETRIES),
    )

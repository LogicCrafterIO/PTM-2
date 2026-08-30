from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tomllib
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
# override=True so the checked-in .env wins over any stale placeholder already
# exported in the shell (e.g. OLLAMA_API_KEY=YOUR_OLLAMA_API_KEY). Without it,
# load_dotenv leaves pre-existing env vars untouched and the real key is ignored.
load_dotenv(ROOT / ".env", override=True)

_data_root: Path | None = None
_ideas_root: Path | None = None


def set_roots(*, data: Path | None = None, ideas: Path | None = None) -> None:
    """Redirect data/ and ideas/ (used by tests). Pass None to restore defaults."""
    global _data_root, _ideas_root
    _data_root = data
    _ideas_root = ideas


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.1-8b-instruct"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com/v1"
    ollama_model: str = "kimi-k2.7-code"
    # Verdict/dive reasoning model. Was deepseek-v4-pro:0813 - arguably sharper,
    # but it burned the provider's usage window mid-run (~10 heavy calls per
    # candidate dive, x173 candidates) and left ideas unbookable. gpt-oss:20b
    # does the structured verdict work at a fraction of the usage; override with
    # OLLAMA_VERDICT_MODEL when running a small manual batch where quality
    # matters more than headroom.
    ollama_verdict_model: str = "gpt-oss:20b"
    ollama_max_tokens: int = 8192
    ollama_max_filing_chars: int = 24000
    deepsearch_max_queries: int = 12
    deepsearch_max_results: int = 8
    deepsearch_max_fetches: int = 8
    # How many days an idea-pipeline run will reuse a ticker's cached deep dive
    # before rerunning it. The viewer's on-demand dives keep any cache.
    deepsearch_cache_days: int = 2
    sec_user_agent: str = "PTM-Idea-Engine/0.1 (contact: ptm-research@example.com)"
    fred_api_key: str = ""


@lru_cache
def env() -> Settings:
    return Settings()


@lru_cache
def toml_settings() -> dict:
    path = ROOT / "config" / "settings.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)


def llm_limits() -> dict:
    """Return active-provider token and pack limits.

    Ollama Cloud models have much larger context/output windows than the legacy
    NVIDIA endpoints, so we widen both the research pack and the generation
    budget when the Ollama key is present. This is the main knob for reducing
    qualitative verdict errors caused by truncated JSON output.
    """
    settings = env()
    if settings.ollama_api_key:
        return {
            "max_filing_chars": settings.ollama_max_filing_chars,
            "max_tokens": settings.ollama_max_tokens,
        }
    cfg = toml_settings()["llm"]
    return {
        "max_filing_chars": int(cfg["max_filing_chars"]),
        "max_tokens": int(cfg["max_tokens"]),
    }


def data_dir(*parts: str) -> Path:
    root = _data_root if _data_root is not None else ROOT / "data"
    path = root.joinpath(*parts) if parts else root
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ideas_dir(*parts: str) -> Path:
    root = _ideas_root if _ideas_root is not None else ROOT / "ideas"
    path = root.joinpath(*parts) if parts else root
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

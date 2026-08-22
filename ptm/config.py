from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tomllib
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

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

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
    # Model for ptm_setups' group ranking. The verdict model above is sized for
    # the main pipeline's ~10 heavy calls PER NAME; the ranking spends one call
    # per industry plus one final — 14 for the current 13 industries — so it can
    # afford a far stronger model, and it needs one: on gpt-oss:20b a live pass
    # ranked a name first for its low P/E and called another "over-valued" while
    # its own PEG said otherwise, exactly the valuation bias the prompt forbids.
    # On gpt-oss:120b the same group came back ordered by revisions and beat
    # size, with the multiple cited only as the bar the print has to clear; on
    # glm-5.3-flash it did that AND read earnings quality out of the filings
    # (naming a one-off tariff claim inside a margin beat, and a beat size
    # decaying across four quarters), which is the judgement this pass exists
    # for. glm is a thinking model, so it REQUIRES the reasoning-effort setting
    # below: left to deliberate freely it spends the whole output budget on
    # reasoning and returns empty content. gpt-oss:120b is the fallback that
    # needs no such care. Override with OLLAMA_SETUPS_MODEL, or per run with
    # `rank --model`.
    ollama_setups_model: str = "glm-5.3-flash"
    # Thinking budget for the ranking call, when the chosen model is a reasoning
    # model. Reasoning tokens come out of the SAME allowance as the answer, so a
    # heavy thinker consumes the budget and answers with nothing.
    #
    # "low" is the measured choice, not a cautious one. At low, glm-5.3-flash
    # returned the sharpest output of anything tried — it named a one-off tariff
    # claim inflating a margin beat and a beat size decaying across four
    # quarters — in about 11 seconds a group. Raised to medium for more depth it
    # got slower (~85s a group) and less reliable: a five-name industry came
    # back with no ranking at all, having spent all 28k tokens thinking. More
    # deliberation did not buy better judgement here; it bought empty replies.
    # ptm_setups.rank retries an empty result at low, so medium degrades rather
    # than fails, but low is what to run. Blank leaves the model's own default.
    # Only low/medium/high are honoured ("none" made glm return its reasoning as
    # prose instead of JSON).
    ollama_setups_reasoning_effort: str = "low"
    ollama_max_tokens: int = 8192
    ollama_max_filing_chars: int = 24000
    deepsearch_max_queries: int = 12
    deepsearch_max_results: int = 8
    deepsearch_max_fetches: int = 8
    # How many days an idea-pipeline run will reuse a ticker's cached deep dive
    # before rerunning it. The viewer's on-demand dives keep any cache.
    deepsearch_cache_days: int = 2
    # Unix timestamp: caches written AFTER this moment count as fresh even in
    # a forced redo. A redo campaign that gets interrupted (e.g. the provider
    # usage window ran out) resumes with the same dd_force flag, and this floor
    # keeps the campaign's own completed dives instead of re-diving them — set
    # DEEPSEARCH_CACHE_FLOOR to the campaign's start time. Empty = no floor:
    # dd_force re-dives everything, as before.
    deepsearch_cache_floor: float | None = None
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

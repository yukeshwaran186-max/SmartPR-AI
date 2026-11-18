"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "checkpoints.sqlite")
LINTER_TIMEOUT_SECONDS = int(os.getenv("LINTER_TIMEOUT_SECONDS", "15"))


def get_github_token() -> str:
    """Return the GitHub token or raise an actionable configuration error."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to access GitHub.")
    return token


def get_openai_api_key() -> str:
    """Return the OpenAI API key or raise an actionable configuration error."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to generate refactors.")
    return api_key


def validate_config() -> None:
    """Validate credentials required for a live review."""
    missing = [
        name for name in ("GITHUB_TOKEN", "OPENAI_API_KEY") if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))

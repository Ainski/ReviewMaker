"""Central configuration for the Literature Review Agent Tool."""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Global configuration loaded from environment variables."""

    # API Keys
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    github_token: Optional[str] = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", None)
    )
    semantic_scholar_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", None)
    )

    # DeepSeek API settings
    deepseek_base_url: str = "https://api.deepseek.com"

    # Search defaults
    max_papers: int = 20
    year_range: int = 5  # look back N years
    prioritize_code: bool = True

    # Output directory
    output_dir: str = "output"

    # Model settings
    deepseek_model: str = "deepseek-chat"  # or "deepseek-reasoner" for reasoning tasks

    def ensure_api_keys(self) -> None:
        """Validate that required API keys are set."""
        if not self.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required. Set it in .env file or environment."
            )


# Singleton config instance
config = Config()

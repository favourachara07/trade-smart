"""
Central place for all configuration / environment variables.
Copy .env.example to .env and fill in your real keys before running.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    twelvedata_api_key: str = os.getenv("TWELVEDATA_API_KEY", "")

    # Gemini model names (override in .env if Google renames/updates these)
    gemini_vision_model: str = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")
    gemini_synthesis_model: str = os.getenv("GEMINI_SYNTHESIS_MODEL", "gemini-2.0-flash")

    # Risk defaults used only as a fallback if the model doesn't compute something usable
    default_risk_reward: float = float(os.getenv("DEFAULT_RISK_REWARD", "2.0"))


def get_settings() -> Settings:
    settings = Settings()
    missing = [
        name
        for name, val in [
            ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
            ("GEMINI_API_KEY", settings.gemini_api_key),
            ("TWELVEDATA_API_KEY", settings.twelvedata_api_key),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Check your .env file against .env.example."
        )
    return settings

"""
Configuration settings for RSSB Office Data Platform.
Phase 2.4 — Optional AI Query Planner.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root or backend dir if present
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.is_file():
    load_dotenv(_env_path)
else:
    load_dotenv()


class Settings:
    """Application settings with safe defaults."""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/office_data_platform",
    )

    # Optional AI Query Planner
    # IMPORTANT: Disabled by default. Platform requires NO external AI API to operate.
    AI_PLANNER_ENABLED: bool = os.getenv("AI_PLANNER_ENABLED", "false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "mock").strip().lower()
    AI_API_KEY: Optional[str] = os.getenv("AI_API_KEY", None)
    AI_MODEL: str = os.getenv("AI_MODEL", "gemini-1.5-flash")
    # Phase 2.5 — Authentication & Office Permissions
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "rssb-office-data-platform-dev-secret-key-change-in-production-2026",
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )
    AUTH_ENFORCED: bool = os.getenv("AUTH_ENFORCED", "false").strip().lower() in (
        "true",
        "1",
        "yes",
        "on",
    )


settings = Settings()

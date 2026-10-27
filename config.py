"""Environment-based configuration for local demos and MySQL deployments."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


class Config:
    SECRET_KEY_CONFIGURED = bool(os.getenv("FLASK_SECRET_KEY"))
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    SQLITE_PATH = os.getenv("SQLITE_PATH", "instance/electricity_demo.db")
    HIGH_USAGE_THRESHOLD_KWH = float(os.getenv("HIGH_USAGE_THRESHOLD_KWH", "120"))
    LARGE_JUMP_MULTIPLIER = float(os.getenv("LARGE_JUMP_MULTIPLIER", "3"))
    ENVIRONMENT = "production" if os.getenv("VERCEL") else os.getenv("APP_ENV", "development")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = None

    @classmethod
    def database_url(cls) -> str:
        """Use configured MySQL exactly; otherwise explicitly select local SQLite."""
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        if cls.ENVIRONMENT != "development":
            raise RuntimeError(
                "Set DATABASE_URL to a persistent database outside development mode. "
                "SQLite file storage is intended for local development only."
            )
        sqlite_path = Path(cls.SQLITE_PATH)
        if not sqlite_path.is_absolute():
            sqlite_path = ROOT_DIR / sqlite_path
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_path}"
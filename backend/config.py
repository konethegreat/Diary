"""Central settings, loaded from .env. All secrets live in env vars only."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    # Gatekeeper — the single permitted user
    ALLOWED_EMAIL: str = os.getenv("ALLOWED_EMAIL", "").strip().lower()

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    AUTH_MODE: str = os.getenv("AUTH_MODE", "oauth")  # "oauth" | "dev"

    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    DATABASE_PATH: Path = ROOT_DIR / os.getenv("DATABASE_PATH", "data/diary.db")

    BRIEF_HOUR: int = int(os.getenv("BRIEF_HOUR", "6"))

    # Phone push notifications via ntfy (optional). NTFY_TOPIC is the secret:
    # anyone who knows it can read the notifications — use a long random name.
    NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "")
    NTFY_SERVER: str = os.getenv("NTFY_SERVER", "https://ntfy.sh")
    # Public-ish base URL of the app (e.g. the Tailscale https://….ts.net
    # address) — used as the notification click-through target.
    APP_URL: str = os.getenv("APP_URL", "")

    # Free-API integrations (all optional, all keyless)
    LATITUDE: str = os.getenv("LATITUDE", "")        # for Open-Meteo weather
    LONGITUDE: str = os.getenv("LONGITUDE", "")
    COUNTRY_CODE: str = os.getenv("COUNTRY_CODE", "ZA")  # for Nager.Date holidays

    TEMPLATES_DIR: Path = ROOT_DIR / "frontend" / "templates"
    STATIC_DIR: Path = ROOT_DIR / "frontend" / "static"


settings = Settings()
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Fail fast on insecure configuration — never run half-locked.
if not settings.ALLOWED_EMAIL:
    raise RuntimeError("ALLOWED_EMAIL must be set in .env — the gatekeeper has no owner.")
if not settings.SECRET_KEY or settings.SECRET_KEY in ("change-me", "dev-insecure-change-me"):
    raise RuntimeError(
        "SECRET_KEY must be set to a random value in .env: "
        'python -c "import secrets; print(secrets.token_hex(32))"'
    )

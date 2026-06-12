"""Phone push notifications via ntfy (https://ntfy.sh) — free, no account.

The phone subscribes to a private random topic in the ntfy app; the server
POSTs messages to NTFY_SERVER/NTFY_TOPIC. The topic name is the only secret —
treat it like a password (it lives in .env). With no NTFY_TOPIC configured,
push() is a silent no-op. Sends are best-effort: a dead network must never
break the scheduler or a request.
"""
import re

import httpx

from ..config import settings


def _plain(markdown_text: str, limit: int = 300) -> str:
    """Markdown -> the plain text a notification body can show."""
    text = re.sub(r"[*_#`>]+", "", markdown_text or "")
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _ascii(text: str) -> str:
    """HTTP headers are latin-1; keep ntfy titles plain ASCII."""
    return text.encode("ascii", "ignore").decode("ascii").strip()


async def push(
    title: str,
    message: str,
    click_path: str = "/",
    priority: str = "default",
    tags: str = "",
) -> bool:
    """Send a phone notification. Returns False when unconfigured or failed."""
    if not settings.NTFY_TOPIC:
        return False
    headers = {
        "Title": _ascii(title),
        "Priority": priority,
    }
    if tags:  # ntfy renders known tag names as emoji, e.g. "sunny", "brain"
        headers["Tags"] = tags
    if settings.APP_URL:
        headers["Click"] = settings.APP_URL.rstrip("/") + click_path
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.NTFY_SERVER.rstrip('/')}/{settings.NTFY_TOPIC}",
                content=_plain(message).encode("utf-8"),
                headers=headers,
            )
            r.raise_for_status()
            return True
    except Exception:
        return False

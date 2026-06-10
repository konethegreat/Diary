"""AI provider abstraction.

Two providers behind one `complete()` call:
  - "anthropic": Claude API (use on mobile / away from desk)
  - "local":     Ollama at OLLAMA_BASE_URL (use at your desk, zero API cost)

The active provider is a Setting row ("ai_provider") toggled from the UI.
"""
import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting

PROVIDER_KEY = "ai_provider"
DEFAULT_PROVIDER = "anthropic"


def get_provider(db: Session) -> str:
    row = db.get(Setting, PROVIDER_KEY)
    return row.value if row else DEFAULT_PROVIDER


def set_provider(db: Session, provider: str) -> str:
    if provider not in ("anthropic", "local"):
        raise ValueError("provider must be 'anthropic' or 'local'")
    row = db.get(Setting, PROVIDER_KEY)
    if row:
        row.value = provider
    else:
        db.add(Setting(key=PROVIDER_KEY, value=provider))
    db.commit()
    return provider


async def complete(db: Session, system: str, prompt: str, max_tokens: int = 1500) -> str:
    """Route a completion to the active provider."""
    provider = get_provider(db)
    if provider == "local":
        return await _ollama_complete(system, prompt)
    return await _anthropic_complete(system, prompt, max_tokens)


async def _anthropic_complete(system: str, prompt: str, max_tokens: int) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — add it to .env or toggle to the local provider.")
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


async def _ollama_complete(system: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


# ---------------------------------------------------------------- prompts ---

POLISH_SYSTEM = """You are a precise writing assistant for a personal work diary.
The user brain-dumps messy, unformatted notes about their day. Rewrite them:
- Fix grammar and structure; keep the author's voice and first person.
- Summarize technical work concisely and accurately — do not invent details.
- Use short markdown: a bold one-line summary, then tight bullet points grouped
  by theme if there are several.
Return ONLY the polished text, no preamble."""


async def polish(db: Session, raw_text: str) -> str:
    return await complete(db, POLISH_SYSTEM, raw_text)


MOOD_SYSTEM = """Rate the overall mood of this diary entry on a scale of 1 to 5:
1 = rough day, 2 = below average, 3 = neutral, 4 = good, 5 = great.
Respond with ONLY the single digit, nothing else."""


async def mood_score(db: Session, text: str) -> int | None:
    """Best-effort 1–5 mood rating. Returns None on any failure."""
    try:
        raw = await complete(db, MOOD_SYSTEM, text, max_tokens=4)
        score = int(raw.strip()[0])
        return score if 1 <= score <= 5 else None
    except Exception:
        return None


REVIEW_SYSTEM = """You are a thoughtful personal coach reviewing someone's diary.
Given the past week's entries (with mood scores where available), write a short
markdown "weekly review": 1) a warm 2–3 sentence overview of the week,
2) **Wins** (bullets), 3) **Threads to pick up** — unfinished things worth
returning to, 4) one sharp, kind observation about patterns you notice.
Be specific; quote dates. Max ~250 words."""


async def weekly_review(db: Session, entries_text: str) -> str:
    return await complete(db, REVIEW_SYSTEM, entries_text, max_tokens=800)


CHAT_SYSTEM = """You are the user's personal diary assistant. Answer their question
using ONLY the diary excerpts provided as context. Quote dates when referencing
entries. If the context doesn't contain the answer, say so plainly."""


async def chat_with_context(db: Session, question: str, context_blocks: list[str]) -> str:
    ctx = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no relevant entries found)"
    prompt = f"Diary excerpts:\n\n{ctx}\n\n---\n\nQuestion: {question}"
    return await complete(db, CHAT_SYSTEM, prompt)

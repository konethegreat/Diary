# Backend — FastAPI

## Map

| File | Purpose |
|---|---|
| `main.py` | App assembly: middleware order, routers, PWA routes, brief scheduler |
| `config.py` | All settings from `.env`; the only place env vars are read |
| `auth.py` | Google OAuth + **GatekeeperMiddleware** (single-user 403 wall) |
| `database.py` | Engine, sessions, sqlite-vec loading, `init_db()` |
| `models.py` | Topic, Entry, Reminder, Setting, Brief |
| `routers/diary.py` | Pages + entry CRUD + polish (+ mood) + provider toggle |
| `routers/chat.py` | RAG chat endpoint |
| `routers/reminders.py` | Reminder CRUD |
| `routers/brief.py` | Morning brief endpoint |
| `routers/calendar_view.py` | Month calendar: entries, reminders, holidays, moods |
| `routers/review.py` | AI weekly review, cached per ISO week in Setting rows |
| `services/ai.py` | Provider abstraction (`complete()`), polish/chat/mood/review prompts |
| `services/embeddings.py` | Embed via Ollama, pack/unpack BLOBs, cosine search |
| `services/brief.py` | Morning brief agent (weather + holidays + reminders + yesterday) |
| `services/external.py` | Keyless APIs: Open-Meteo, Nager.Date, ZenQuotes — all best-effort |
| `services/calendar_stub.py` | Replace with Google Calendar / MS Graph |

## Rules

- **Middleware order in `main.py` is load-bearing**: SessionMiddleware is added
  last so it runs *before* GatekeeperMiddleware, which reads the session.
- New protected routes need nothing extra — the gatekeeper covers everything
  not in `auth.PUBLIC_PATHS` / `PUBLIC_PREFIXES`.
- Provider routing: never call Anthropic/Ollama directly from routers; go
  through `services/ai.complete()` so the UI toggle keeps working.
- Embeddings are best-effort: `embed_entry()` returns False when Ollama is
  down and the caller must continue. Don't make saving depend on it.
- DB sessions come from `Depends(get_db)`; background jobs create their own
  `SessionLocal()` and must close it.

## Extending

- **Real calendar:** implement `services/calendar_stub.todays_events()` —
  return `["09:00–09:30 Standup", ...]` strings and the brief + agenda UI
  pick it up unchanged.
- **External cron for the brief:** `GET /api/brief?force=true` (authenticated)
  regenerates; the in-process APScheduler job already runs at `BRIEF_HOUR`.

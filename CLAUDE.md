# Diary — AI-Augmented Personal Life Log

Single-user, open-source diary app. Python end-to-end (no JavaScript authored
by hand — only HTMX from CDN and a minimal service worker for PWA install).

## Features

- **Today** — brain-dump entries, AI polish + 1–5 mood scoring, topics,
  reminders, "on this day" memories, morning brief (weather/holidays/agenda)
- **Calendar** — month view with entry dots, reminders, holidays, mood emoji
- **Topics** — six presets + custom; AI summaries per topic per period,
  in-app and embedded in the topic PDF
- **Review** — AI weekly reflection with a 7-day mood chart
- **Coach** — monthly AI coaching that adapts to the month's mood data
  (comfort after rough months, push after strong ones), quotes the user's
  own entries, remembers who they are across months, follows up on its
  previous challenge
- **Ask** — RAG chat over all entries via embeddings
- **PDF export** — any day, any month, any topic (with its AI summary), or
  the complete archive, from `/export/`

## Stack

- **Backend:** FastAPI + SQLAlchemy 2.0, SQLite (+ sqlite-vec when available)
- **Frontend:** Jinja2 templates + HTMX, single CSS file, PWA
- **AI:** Anthropic Claude API ↔ local Ollama, toggled at runtime from the UI
- **Embeddings:** Ollama `nomic-embed-text`, stored as float32 BLOBs
- **PDF export:** fpdf2 with core fonts only — day/month/all/topic downloads
  under `/export/`, plus topic summaries and coach sessions rendered from
  the same markdown the web UI shows

## Run

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
# .env must exist with ALLOWED_EMAIL and a random SECRET_KEY —
# the app refuses to start without them (see backend/config.py)
python run.py --dev                               # http://localhost:8000
```

## Deployment (current)

Runs permanently on the owner's Windows laptop:

- **Windows scheduled task "Diary"** starts `.venv\Scripts\pythonw.exe run.py`
  at logon (no console; logs append to `data/server.log`). `--dev` enables
  uvicorn auto-reload for development; without it the server is headless.
- **Tailscale** provides phone access: `tailscale serve` fronts
  127.0.0.1:8000 with HTTPS at `https://diary.<tailnet>.ts.net` (device
  hostname "diary"; Let's Encrypt cert auto-renewed by tailscaled). The
  diary is never exposed to the public internet — serve is tailnet-only,
  Funnel is off and must stay off. Session cookies are Secure-flagged;
  HSTS is emitted (scheme arrives via X-Forwarded-Proto). NOTE: with
  TRUST_TAILNET=true + AUTH_MODE=dev every tailnet device is the owner —
  fine while the tailnet is single-person; switch to OAuth before family.
- **Push notifications** via ntfy.sh (`backend/services/notify.py`):
  morning brief at BRIEF_HOUR and a coach nudge at 18:00 on the last day of
  the month. `NTFY_TOPIC` in `.env` is the secret; `APP_URL` is the ts.net
  address used for notification click-through.

## Critical invariants — do not break

1. **Single-user gatekeeper.** The repo is public. Every request passes through
   `backend/auth.py:GatekeeperMiddleware`; only `ALLOWED_EMAIL` may hold a
   session, all others get 403. Never add a route that bypasses this without
   adding it to `PUBLIC_PATHS` deliberately.
2. **Secrets stay in `.env`** (gitignored). Never hardcode keys; never commit
   `.env` or `data/`. There is deliberately no `.env.example` — config.py
   documents every variable and fails fast on missing/insecure values.
3. **AUTH_MODE=dev** auto-logs-in the owner, and is honored ONLY for loopback
   connections — plus the owner's Tailscale ranges when `TRUST_TAILNET=true`
   (see `auth._is_local`; tailscale serve forwards the peer's tailnet IP via
   X-Forwarded-For, which uvicorn applies). All other clients always hit
   OAuth. TRUST_TAILNET is only sane while the tailnet is single-person —
   turn it off and switch to OAuth before inviting family.
4. **Security headers** (CSP, frame-deny, nosniff, HSTS-on-https) are attached
   by the gatekeeper middleware to every response, including public paths.
   htmx is the only external script, SRI-pinned to unpkg.

## Layout

- `backend/` — API, models, auth, AI services → see `backend/CLAUDE.md`
- `frontend/` — templates, CSS, PWA assets → see `frontend/CLAUDE.md`
- `run.py` — uvicorn entry point
- `data/diary.db` — SQLite database (created on first run, gitignored)

## Conventions

- HTMX endpoints return HTML partials from `frontend/templates/partials/`,
  not JSON. JSON is reserved for future programmatic API needs.
- AI failures must degrade gracefully: entries always save even if
  polish/embedding fails; errors render inline in the affected partial.
- AI output that should survive restarts (weekly reviews, topic summaries,
  coach sessions, the coach's profile memory) is cached in `Setting` rows —
  see the key namespaces in `backend/CLAUDE.md`. Regenerating overwrites.
- Topics: six presets (Work, Personal, Discovery, Growth, Failure, Struggle)
  are seeded at startup; users add custom ones from the new-entry form.
- Keep all code Python. Do not introduce Node, npm, or hand-written JS.

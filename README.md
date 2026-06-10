# ✦ Diary — AI-Augmented Personal Life Log

A single-user, installable (PWA) daily diary with AI superpowers. Built
entirely in Python (FastAPI + HTMX) — no JavaScript to maintain.

## Features

- **Smart diary** — brain-dump messy notes; one click and AI polishes them
  into clean, structured markdown. Entries organized by topics/projects.
- **Ask my diary (RAG)** — semantic search over every entry. "What bug did I
  fix in the routing logic last month?" gets a sourced answer.
- **Provider toggle** — switch between Claude API (on the go) and local
  Ollama (at your desk, free) with one click in the nav bar.
- **Morning brief** — a daily agent reads your calendar, open reminders, and
  yesterday's entries, then writes your priorities for the day.
- **Reminders** — lightweight task tracking attached to each day.
- **Single-user gatekeeper** — repo can be public; only your email can log in
  (Google OAuth, hard 403 for everyone else).

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env            # fill in values — see comments inside
python run.py                   # → http://localhost:8000
```

For local-only use, `AUTH_MODE=dev` in `.env` skips OAuth and signs you in
as `ALLOWED_EMAIL`. For anything internet-facing, set `AUTH_MODE=oauth` and
create Google OAuth credentials (redirect URI `https://your-host/auth/callback`).

### AI setup

- **Claude:** set `ANTHROPIC_API_KEY`.
- **Local:** install [Ollama](https://ollama.com), then
  `ollama pull llama3.1 && ollama pull nomic-embed-text`.
  Embeddings always use Ollama (free); chat/polish follow the UI toggle.

## Install as an app

Open the site in Chrome/Edge (desktop or Android) → "Install app", or Safari
on iOS → Share → "Add to Home Screen".

## Architecture

See `CLAUDE.md`, `backend/CLAUDE.md`, and `frontend/CLAUDE.md` for the full
map, invariants, and conventions.

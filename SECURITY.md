# Security Policy

Diary is a single-user, self-hosted application whose entire purpose is to keep
one person's private journal private. Security is a first-class concern, and the
codebase is built around a small set of hard invariants documented below.

## Reporting a vulnerability

Please report security issues **privately**. Do **not** open a public issue,
pull request, or discussion for anything potentially exploitable.

- **Preferred:** use GitHub's private vulnerability reporting on this
  repository — the **Security** tab → **Report a vulnerability**.
- If private reporting is not enabled, open a public issue containing only the
  text "security report — please enable private vulnerability reporting" with
  **no further detail**, and wait to be contacted before sharing specifics.

This is a personal, single-maintainer project, so there is no formal response
SLA — but legitimate reports are read and taken seriously. Please give a
reasonable amount of time for a fix before any public disclosure.

## Supported versions

Only the latest commit on the `main` branch is supported. Older states are not
maintained and fixes are not backported.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| anything older | ❌ |

## Security model

The application is designed so that a public source repository never implies a
public diary. Key invariants (see `CLAUDE.md` and `backend/CLAUDE.md`):

- **Single-user gatekeeper.** Every request passes through
  `backend/auth.py:GatekeeperMiddleware`. Only the configured `ALLOWED_EMAIL`
  may hold a session; everyone else receives a hard `403`. Routes are private
  by default — only paths explicitly placed in `PUBLIC_PATHS` /
  `PUBLIC_PREFIXES` are reachable unauthenticated.
- **Secrets live only in `.env`** (gitignored). There is deliberately no
  `.env.example`. `backend/config.py` is the single place env vars are read and
  it **fails fast** on startup if `ALLOWED_EMAIL` or a strong `SECRET_KEY` are
  missing or left at a placeholder value — the app refuses to run half-locked.
- **Security headers on every response**, including public paths: a strict
  Content-Security-Policy (no `'unsafe-eval'`, no inline scripts; htmx is the
  only external script and is Subresource-Integrity pinned to a fixed version),
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy`, `Permissions-Policy`, and HSTS when served over HTTPS.
- **Secure sessions.** Session cookies are `Secure`-flagged over HTTPS and
  signed with `SECRET_KEY`.
- **Private by default at the edge.** The reference deployment is fronted by
  Tailscale `serve` and is reachable only from the owner's own tailnet — it is
  never exposed to the public internet, and Tailscale Funnel is intentionally
  off.
- **`AUTH_MODE=dev` auto-login is restricted.** It is honored only for loopback
  connections, plus the owner's tailnet ranges when `TRUST_TAILNET=true`. All
  other clients always go through Google OAuth.
- **AI can stay fully local.** Chat/polish can be pointed at a local Ollama
  instance so diary content need never leave the machine. Push notifications via
  ntfy are private by default (a generic "ready" ping; including any diary
  content is strictly opt-in via `NTFY_SEND_CONTENT`).

## Operator responsibilities

If you run your own instance, you are responsible for:

- generating a strong random `SECRET_KEY`
  (`python -c "import secrets; print(secrets.token_hex(32))"`);
- keeping `.env`, `data/` (your database), and any TLS material out of version
  control (all are gitignored by default);
- using real Google OAuth (`AUTH_MODE=oauth`) for anything internet-facing, and
  treating `TRUST_TAILNET=true` as safe **only** while the tailnet contains no
  one else's devices;
- choosing a long, unguessable `NTFY_TOPIC` if you enable notifications.

## Out of scope

- Issues that require the owner's own authenticated session, device, or `.env`
  secrets to exploit.
- The deliberate `TRUST_TAILNET` single-person trade-off described above.
- Vulnerabilities in third-party services and dependencies (Anthropic, Ollama,
  ntfy.sh, Google, the htmx CDN) — though reports about how this project
  *integrates* them (e.g. a weakened CSP or unpinned dependency) are welcome.

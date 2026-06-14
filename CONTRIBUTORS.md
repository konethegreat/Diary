# Contributors

Diary is a personal project, built and maintained by its author with help from
an AI pair programmer.

## Maintainer & copyright holder

- **Kone Tshivhinda** ([@konethegreat](https://github.com/konethegreat)) —
  creator, author, and maintainer. Holds the copyright to this project
  (see [LICENSE.md](LICENSE.md)).

## Contributors

- **Claude** (Anthropic) — AI pair programmer, via Claude Code. Helped design
  and implement features (PDF export, preset + custom topics with AI summaries,
  the mood-aware monthly coach, RAG "Ask my diary"), harden security (strict
  CSP, CSP-safe service worker and htmx handlers, deployment hardening), and
  write documentation. All contributions were made under the maintainer's
  direction and review.

## Contributing

This is primarily a personal application rather than a community project, and it
is **source-available under a noncommercial license** (see
[LICENSE.md](LICENSE.md)) — you are welcome to fork it for your own
noncommercial use.

If you would like to propose a change:

1. Open an issue first to discuss it.
2. Keep changes consistent with the conventions and invariants in `CLAUDE.md`,
   `backend/CLAUDE.md`, and `frontend/CLAUDE.md`.
3. Never commit secrets or personal data (`.env`, `data/`, TLS material are
   gitignored — keep it that way).

By submitting a contribution, you agree that it is licensed under the same terms
as this project.

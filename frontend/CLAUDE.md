# Frontend — Jinja2 + HTMX (no hand-written JS)

## Map

- `templates/base.html` — shell: nav, fonts, htmx CDN, SW registration
- `templates/diary.html` — daily view: brief, new-entry form, entries, reminders sidebar
- `templates/chat.html` — RAG chat page
- `templates/login.html` — Google sign-in
- `templates/partials/` — HTMX swap targets (entry_card, chat_message, reminder_list, brief, provider_toggle, topic_options)
- `static/app.css` — entire design system (tokens at top in `:root`)
- `static/manifest.json`, `static/sw.js`, `static/icon.svg` — PWA

## Design language

Two themes via `<html data-theme>` (cookie-backed, toggled server-side):
**dark** = warm ink, **light** = warm paper. Ember-orange accent with a
fire-to-violet gradient (`--accent-grad`). Type: Fraunces (display serif,
headings/logo/quotes) + Inter (UI). Tokens live in `:root` /
`[data-theme="light"]` at the top of `app.css` — never hardcode colors.

Motion follows Emil Kowalski's design-engineering principles:

- transition **specific properties**, never `transition: all`
- custom curves: `--ease-out: cubic-bezier(0.23,1,0.32,1)`; UI under 300ms
- every pressable element gets `:active { transform: scale(0.97) }`
- entries animate in with translateY+opacity (never from `scale(0)`),
  staggered 40ms via `.stack > :nth-child()` delays
- hover effects gated behind `@media (hover:hover) and (pointer:fine)`
- `prefers-reduced-motion`: movement removed, fades kept

## Rules

- **All interactivity is HTMX attributes** (`hx-post`, `hx-target`,
  `hx-swap`). Do not add `<script>` blocks; the only JS is `static/init.js`
  (one-line SW registration — kept as a file so CSP stays strict) and
  `static/sw.js`. htmx is SRI-pinned; bumping its version means updating
  both the URL and integrity hash in base.html AND the CSP in auth.py.
- Theme toggle: POST `/api/theme` flips a cookie and returns `HX-Refresh` —
  no client-side theme logic exists or should exist.
- Server returns partials; a partial must render standalone with only the
  context its router provides.
- Loading states: put `btn-busy` on the button and
  `<span class="htmx-indicator spinner"></span>` inside it.
- New colors/spacing go in `:root` tokens first; never hardcode hex values
  mid-file.
- Mobile: the grid collapses at 860px; test new UI at narrow widths (this is
  an installable PWA used on phones).

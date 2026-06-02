# HotStream Web (Next.js)

The Next.js front + auth layer for HotStream. It owns **authentication** and all
**per-user persistence** (settings / drafts / history), and **proxies** the
stateless scraping/AI endpoints to the existing Python service.

This is milestone 1 of the migration to a Next.js + Docker delivery. The legacy
HTML pages (`legacy/index.html`, `legacy/editor.html`) are served behind auth for
now; they'll be rewritten as React pages in a later milestone.

## Architecture

```
Browser ──same-origin──▶ Next.js (this app, :3000)
   ├─ /login, /admin/users                          (React)
   ├─ /app, /editor                                 (legacy HTML, auth-gated)
   ├─ /api/auth/*, /api/users/*                      (auth + admin)
   ├─ /api/settings, /api/drafts, /api/history       (per-user, pg → PostgreSQL)
   └─ /api/hot-topics, /api/generate-copy,           (proxy → Python, injects
      /api/analyze-video, /api/prompts, /api/proxy-image    the user's API key)
                          │
                          ▼ PYTHON_API_BASE
                 Python scraper/AI service (:5173, stateless, no DB)
```

Key design points:
- **Sessions**: opaque random token in an httpOnly cookie; only its SHA-256 is
  stored in the `sessions` table. Validated against the DB on every request, so
  disabling a user / changing a password takes effect immediately.
- **Passwords**: `crypto.scrypt` (Node built-in, no native deps), parameterized
  hash format, timing-safe compare.
- **Per-user isolation**: every `settings`/`drafts`/`history` query is scoped by
  `user_id`. Users never see each other's data.
- **API keys never reach the browser**: stored server-side; `GET /api/settings`
  returns only a masked tail (`••••ABCD`). The generate/analyze proxies inject
  the user's key server-side.
- **Admin-only user management** (invite/admin-created, no open registration) at
  `/admin/users`, with guards against removing the last admin / self-lockout.
- **CSRF**: Origin-header check on all mutating + proxied-POST routes; `SameSite=Lax`.

## Local development

```bash
cd web
npm install
cp .env.example .env.local   # fill in DB_*, ADMIN_*
npm run migrate              # create/upgrade tables (idempotent)
npm run seed:admin           # create the first admin from ADMIN_USERNAME/PASSWORD
# In another terminal, start the Python service so proxied routes work:
#   (cd .. && uv run python main.py)   # http://127.0.0.1:5173
npm run dev                  # http://127.0.0.1:3000
```

Tests: `npm test` (vitest). Typecheck: `npx tsc --noEmit`.

## Docker (compose: web + scraper)

From the repo root:

```bash
cp .env.example .env         # fill in DB_*, ADMIN_PASSWORD
docker compose up --build    # web on :3000, scraper internal on :5173
```

The web container runs migrations + admin seed on startup (via bundled
`dist/migrate.js` / `dist/seed-admin.js`) before launching the standalone server.

Environment variables:

| Var | Purpose |
|---|---|
| `DB_HOST/PORT/NAME/USER/PASSWORD/SCHEMA` | PostgreSQL (schema-scoped to `wangyafei`) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | first admin, seeded on startup |
| `COOKIE_SECURE` | `true` only when served over HTTPS |
| `PYTHON_API_BASE` | scraper/AI service base URL |

## Notes / future milestones

- **Milestone 2**: rewrite `legacy/*.html` as React pages (port the canvas
  long-image export and drag-to-reorder blocks); drop `legacy/`.
- **Milestone 3**: port the Python scrapers/AI to TypeScript → a single Next.js
  Docker image (drop the Python service / compose).
- The legacy Python persistence routes (`/api/settings|drafts|history`) are now
  superseded by this app and are no longer hit by the frontend.

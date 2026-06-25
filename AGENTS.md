# AGENTS.md

Two deliverables in this repo: a **static landing page** (`index.html`) and an **untracked FastAPI registration backend** (`backend/`).

## Landing page — `index.html` (tracked)

Single-file static page for the **2026 兩岸無人機足球青年領袖研習營**. Open in a browser to preview; deploy by copying to any static host. No build system, framework, JS, or tests.

- **CSS**: `:root` custom properties only — never hardcode colors.
- **Layout**: mobile-first; breakpoints at `480px–500px`.
- **Section pattern**: `.section` > `.section-label` + `.section-title` + `<hr class="divider">`.
- **Page flow**: hero → organizers → event info → instructors → 6-day schedule → takeaways → career opportunities → costs → CTA → footer.
- **Content**: Traditional Chinese (`zh-TW`), FIDA / 世界盃 framing.
- **Placeholders**: `【待填：...】` markers — do not invent values.
- `index_remote.html` — untracked variant with `【待填】` placeholders. Do not edit.

## Backend — `backend/` (untracked)

FastAPI registration system with SQLAlchemy + PostgreSQL.

### Run

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary jinja2 python-multipart
uvicorn backend.main:app --reload
```

### Requirements

- PostgreSQL at `DATABASE_URL` (default: `postgresql://postgres:postgres@localhost:5432/drone_soccer`)
- Tables created automatically on startup (`Base.metadata.create_all`)

### Routes

| Path | Purpose |
|------|---------|
| `/` | Registration portal (Jinja2 template) |
| `/register/leader` | Leader creates a team, gets `DST-XXXX` code |
| `/register/member` | Member joins with team code |
| `/admin/login` | Admin auth (default password from `ADMIN_PASSWORD` env, fallback `admin123`) |
| `/admin` | Dashboard with registrations + stats |
| `/admin/export.csv` | CSV export with BOM |

## Working conventions

- No `.gitignore` exists — create one if needed.
- `.claude/` is git-ignored by default (contains local Claude Code settings only).
- No `requirements.txt` or dependency manifest — install packages directly.

# AkashiSovet Modernization Plan (v2)

## Priority Order
1. Refactoring & DRY
2. Dynamic JSON Template
3. Web Interface UI/UX
4. Authentication via Telegram
5. Security & Access Control

---

## 1. Refactoring & DRY Elimination
**Goal:** Remove all three pain points simultaneously — duplication, scattered models, logic in handlers.

**Proposed changes:**
- **`stdlib/models.py`** — centralize all Pydantic schemas: `Application`, `User`, `Template`, `Meeting`.
- **`stdlib/services/`** — extract business logic from handlers into dedicated services:
  - `application_service.py` — status changes, creation, finalization.
  - `file_service.py` — upload/download via S3.
  - `notification_service.py` — all Telegram message dispatching.
- **`stdlib/resources.py`** — single async resource manager for DB (asyncpg pool), Redis, and S3 client. Both `bot/` and `web/` import from here.
- **Rule:** `bot/handlers/` and `web/` contain only routing logic — no business logic directly inside them.

---

## 2. Unified Dynamic Template (JSON)
**Goal:** Make the request structure fully configurable without code changes.

**Proposed changes:**
- **DB:** New `settings` table (`key TEXT PRIMARY KEY`, `value JSONB`). The `app_template` key stores the full structure.
- **JSON schema example:**
```json
{
  "blocks": [
    {
      "id": 1,
      "title": "Тема вопроса",
      "question": "Укажите тему вопроса, выносимого на Правление...",
    },
    {
      "id": 2,
      "title": "Краткое описание и суть вопроса",
      "question": "Кратко опишите ситуацию...",
    }
  ]
}
```
- **Bot:** `filling.py` loads blocks dynamically from DB on each new application. No hardcoded questions.
- **PDF:** `pdf.py` renders sections by iterating over the same JSON — section titles and order driven by the template.
- **Web — Visual Template Editor:**
  - Dedicated `/settings/template` page (superuser only).
  - UI: list of blocks with fields for title, question text, AI assist toggle.
  - Add / remove / reorder blocks via HTMX without page reload.
  - Save writes the updated JSON back to the `settings` table.
  - Validation before save: check required fields are present.

---

## 3. Web Interface UI/UX
**Goal:** A convenient, fast dashboard for the approval workflow.

**Proposed changes:**
- **Dashboard widgets** (HTMX, auto-refresh):
  - Counters: Pending / Approved / Sent for Revision / Total.
  - Quick-filter buttons by status.
- **Archive:** Approved requests grouped by date — collapsible accordions, newest first.
- **Meeting Module ("Basket"):**
  - New `meetings` table: `id`, `scheduled_date`, `created_by`, `created_at`, `application_ids JSONB`.
  - UI flow: checkbox on each approved request → "Add to Meeting" button → pick date → save.
  - Two views: **Upcoming meetings** and **Past meetings**, each showing the date and list of included requests.
  - Each meeting page shows its requests with links to their detail pages and PDFs.
  - No automatic notifications — meetings are purely for record-keeping and planning.

---

## 4. Authentication via Telegram (Deep Linking)
**Goal:** Replace the ID + OTP + password flow with one-click login.

**Reason for choosing Deep Linking over Telegram Login Widget:** no public domain available; all supervisors already use the bot.

**Proposed changes:**
- **Bot:** Add `/web` command. On call — generate a one-time token (UUID, TTL 5 min), store in Redis as `auth_token:{token} → user_id`. Send the supervisor a message with the login link: `http://your-panel/auth?token=xyz`.
- **Web:** New `/auth` route — validate token from Redis, check `user_id` in `config.SUPERUSER_IDS`, set session cookie, redirect to dashboard. On invalid/expired token — redirect to login page with error.
- **Remove:** Old ID input, OTP via bot, permanent password — all deprecated.
- **Session:** Cookie-based, TTL configurable (e.g. 8 hours). On expiry — re-auth via `/web` in bot.

---

## 5. Security & Access Control
**Goal:** Prevent any unauthorized access to the web panel.

**Proposed changes:**
- **Superuser-only middleware:** FastAPI dependency injected on all routes except `/auth` and `/login`. Any request without a valid session → 403 or redirect to login.
- **SQL audit:** Review all `asyncpg` queries in `stdlib/db.py` — ensure 100% parameterized, zero f-strings in SQL.
- **Attachment protection:** `/files/` and `/pdf/` endpoints check active supervisor session before serving. No public S3 URLs.
- **Secrets:** Full audit — all tokens, passwords, S3 keys moved to `.env` / `pydantic-settings`. No hardcoded values anywhere in codebase.
- **Auth token security:** Deep Linking tokens are single-use — deleted from Redis immediately after first use.

---

## Implementation Order

| Phase | Sections | Outcome |
|-------|----------|---------|
| **1** | Refactoring + Models + Services | Clean foundation, no duplication |
| **2** | JSON Template + Visual Editor | Configurable requests end-to-end |
| **3** | Dashboard + Archive + Meetings | Full supervisor workflow |
| **4** | Deep Linking Auth | Seamless login |
| **5** | Security audit | Production-ready hardening |

---
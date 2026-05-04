---

# 🏗️ AKASHI Sovet — Request Management System

**AKASHI Sovet** is a comprehensive platform for automating the submission, processing, and approval of internal requests (Board agenda items) for **AKASHI Data Center PLC**.

The system combines a Telegram bot for end users and a web panel for administrators (supervisors).

---

## 🛠️ Tech Stack

- **Backend (Bot):** Python 3.12, [Aiogram 3.7+](https://docs.aiogram.dev/) (async Telegram framework).
- **Backend (Web):** [FastAPI](https://fastapi.tiangolo.com/) (high-performance web framework).
- **Database:** PostgreSQL (primary storage), Redis (FSM state storage and caching).
- **File Storage:** S3-compatible storage (MinIO/AWS S3) for attachments.
- **LLM Integration:** OpenAI API / Anthropic (to assist users in filling out request blocks).
- **Document Generation:** ReportLab (PDF report creation).
- **Scheduling & Tasks:** APScheduler (daily reports, notifications).

---

## 📂 Project Structure

### 📁 Root Directory
- `PROJECT.MD` — (this file) detailed description of the architecture and files.
- `Dockerfile` — instructions for building the application Docker image.
- `docker-compose.yaml` — configuration for running the full infrastructure (Bot, Web, DB, Redis, S3).
- `pyproject.toml` / `uv.lock` — dependency management via the `uv` package manager.
- `.env` / `env.example` — environment variables (tokens, database credentials).

---

### 🤖 `bot/` — Telegram Bot Logic
The primary interaction point for regular users.

- `bot.py` — **Main bot entry point.** Initializes Aiogram, routers, the task scheduler (APScheduler), and starts polling.
- `config.py` — Loads and validates settings from `.env` via `pydantic-settings`.
- `logger.py` — Logging configuration (Loguru) with file rotation and standard log interception.

---

### 🌐 `web/` — Admin Web Interface
A management panel for superusers to review and approve requests.

- `main.py` — **FastAPI entry point.** Handles dashboard routes, authentication (Cookie + OTP via bot), request viewing and export.
- `templates/` — Jinja2 templates for rendering the UI (HTMX is used for dynamic table row updates).

---

### 📚 `stdlib/` — Shared Library (Core Logic)
The central location for all business logic shared between the bot and the web components.

- `db.py` — Database access layer. Uses `asyncpg`. Contains all SQL queries, from user registration to statistics retrieval.
- `s3.py` — Object storage integration. File upload/download, bucket validation.
- `pdf.py` — Logic for generating a PDF document from request data. Uses complex ReportLab templates.
- `schemas.py` — Pydantic models and TypedDicts for strict data typing across the project.
- `keyboards.py` — Keyboard generator (Inline/Reply) for the Telegram bot.
- `redis_client.py` — Redis connection initialization and management.
- `template.py` / `templates/` — Templates (text or HTML) for various purposes.
- `llm/` — AI interaction module:
  - `client.py` — Wrapper over LLM provider APIs.
  - `prompts.py` — System prompts for processing request text.
  - `formatter.py` — Logic for formatting responses from the neural network.
  - `free_form.py` — Handling "free-form" user queries to the AI.
- `handlers/` — Bot command handlers (Aiogram routers):
  - `user/` — Logic for regular employees (creating a request via `/start`, filling blocks in `filling.py`, editing in `rework.py`, viewing own requests in `my_apps.py`).
  - `superuser/` — Admin commands (broadcasts, statistics).
  - `blocks.py` — Logic for processing specific informational blocks of a request.
  - `states.py` — FSM (Finite State Machine) state definitions.

---

### 🧪 Testing & Miscellaneous
- `test_pdf.py` — Script for local PDF generation testing.
- `graphify-out/` — Code dependency analysis results (if used).
- `trash/` — Temporary files or old drafts.

---

## 🔄 Workflow

1. **Submission:** The user launches the bot and fills in their profile (full name, position).
2. **Filling:** The bot guides the user through steps (request blocks). AI can be used to polish the text.
3. **Files:** If attachments are needed, the user sends them to the bot — they are uploaded to S3 and the links are saved to the database.
4. **Review:** Once finalized, the request appears in the Web panel.
5. **Decision:** The supervisor clicks "Approve", "Reject", or "Send for Revision" (with a comment).
6. **Notification:** The user instantly receives a Telegram message with the status of their request.
7. **Result:** An approved request is available as an auto-generated PDF report.

---
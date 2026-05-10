<div align="center">
  <!-- Place your logo or banner image here -->
  <img src="https://via.placeholder.com/800x200/000000/FFFFFF/?text=AkashiSovet+Banner" alt="AkashiSovet Banner" width="100%">

  # ✨ AkashiSovet

  <p><strong>A modern, scalable corporate ecosystem powered by AI.</strong></p>

  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.13+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI"></a>
    <a href="https://docs.aiogram.dev/"><img src="https://img.shields.io/badge/Aiogram-3.x-blue?style=for-the-badge&logo=telegram" alt="Aiogram"></a>
    <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"></a>
  </p>
</div>

<br/>

## 🎯 About The Project

**AkashiSovet** is a universal corporate platform unifying a powerful Telegram Bot and a web administrative dashboard. Initially designed for a secretariat, it is built with a scalable microservices-ready architecture that can support multiple company departments. 

The system leverages state-of-the-art AI models via LangChain, utilizing secure S3-compatible storage (MinIO) and high-performance databases (PostgreSQL, Redis).

<br/>

## 📸 Screenshots & Previews

> *Insert screenshots of your Web Dashboard, Telegram Bot, or Grafana analytics here!*

<div align="center">
  <table>
    <tr>
      <td align="center">
        <!-- Photo 1 Placeholder -->
        <img src="https://via.placeholder.com/400x250/1e1e1e/888888/?text=Web+Dashboard" alt="Web Dashboard" width="400"/>
        <br><i>Web Dashboard</i>
      </td>
      <td align="center">
        <!-- Photo 2 Placeholder -->
        <img src="https://via.placeholder.com/400x250/1e1e1e/888888/?text=Telegram+Bot" alt="Telegram Bot" width="400"/>
        <br><i>Telegram Bot Interface</i>
      </td>
    </tr>
    <tr>
      <td align="center">
        <!-- Photo 3 Placeholder -->
        <img src="https://via.placeholder.com/400x250/1e1e1e/888888/?text=Grafana+Analytics" alt="Grafana Analytics" width="400"/>
        <br><i>Grafana Analytics</i>
      </td>
      <td align="center">
        <!-- Photo 4 Placeholder -->
        <img src="https://via.placeholder.com/400x250/1e1e1e/888888/?text=System+Architecture" alt="Architecture" width="400"/>
        <br><i>System Architecture</i>
      </td>
    </tr>
  </table>
</div>

<br/>

## 🚀 Key Features

- 🤖 **AI Integration**: Powered by LangChain and OpenAI models for intelligent automation.
- 📱 **Telegram Bot**: Fully asynchronous bot built on `aiogram` for seamless user interactions.
- 🌐 **Web Dashboard**: High-performance REST API and dashboard powered by `FastAPI`.
- 🗄️ **Robust Storage**: Uses PostgreSQL (via `asyncpg`), Redis for caching, and MinIO for S3-compatible file storage.
- 📊 **Monitoring & Observability**: Integrated with Langfuse for LLM observability and Grafana for system metrics.
- 🐳 **Dockerized Setup**: Containerized using Docker and `docker-compose` for easy deployment and scaling.
- ⚡ **Modern Python**: Built with Python 3.13+ and modern dependency management using `uv`.

<br/>

## 💻 Tech Stack

| Category | Technologies |
| :--- | :--- |
| **Backend & Web** | `<img src="https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi" alt="FastAPI">` `<img src="https://img.shields.io/badge/Uvicorn-499848?style=flat-square&logo=uvicorn" alt="Uvicorn">` |
| **Telegram Bot** | `<img src="https://img.shields.io/badge/Aiogram-2CA5E0?style=flat-square&logo=telegram" alt="Aiogram">` |
| **Databases** | `<img src="https://img.shields.io/badge/PostgreSQL-316192?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">` `<img src="https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white" alt="Redis">` |
| **Storage** | `<img src="https://img.shields.io/badge/MinIO-C7202C?style=flat-square&logo=minio&logoColor=white" alt="MinIO">` |
| **AI / ML** | `<img src="https://img.shields.io/badge/LangChain-121212?style=flat-square&logo=langchain&logoColor=white" alt="LangChain">` `<img src="https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=openai&logoColor=white" alt="OpenAI">` |
| **DevOps & Tools**| `<img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">` `<img src="https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white" alt="Grafana">` `<img src="https://img.shields.io/badge/uv-000000?style=flat-square&logo=python&logoColor=white" alt="uv">` |

<br/>

## 🛠️ Getting Started

Follow these instructions to set up the project locally.

### Prerequisites

Ensure you have the following installed:
* [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
* [Python 3.13+](https://www.python.org/)
* [uv](https://github.com/astral-sh/uv) (Fast Python package installer)

### Installation & Running

1. **Clone the repository**
   ```sh
   git clone https://github.com/your-username/AkashiSovet.git
   cd AkashiSovet
   ```

2. **Environment Variables**
   Copy the example environment file and configure your credentials:
   ```sh
   cp env.example .env
   ```
   *Make sure to fill in your API keys (Telegram, OpenAI, etc.), database passwords, and MinIO credentials in the `.env` file.*

3. **Run with Docker Compose**
   The easiest way to start the entire ecosystem (Web app, Bot, DB, Redis, MinIO, Grafana) is via Docker:
   ```sh
   docker-compose up -d --build
   ```

4. **Apply Database Migrations**
   If this is the first time you are running the project, you will need to apply the database migrations:
   ```sh
   cat migrations/*.sql | docker exec -i akashi_db psql -U akashi -d akashi
   ```

5. **Access the Services**
   - **FastAPI Dashboard/API**: `http://localhost:8000` (or `http://localhost:8000/docs` for Swagger UI)
   - **MinIO Console**: `http://localhost:9001`
   - **Grafana**: `http://localhost:3000`

### Local Development (Without Docker)

If you wish to run the app or bot directly on your host machine for development:

```sh
# Sync dependencies using uv
uv sync

# Run the FastAPI Web Application
uv run uvicorn web.main:app --host 0.0.0.0 --port 8000

# Run the Telegram Bot
uv run python -m bot.bot
```
*(Note: You will still need the database, Redis, and MinIO running locally or via `docker-compose.yaml` without the bot/web services).*

<br/>

## 📂 Project Structure

```text
AkashiSovet/
├── bot/                # Telegram bot source code (aiogram)
├── web/                # FastAPI web dashboard and REST API
├── migrations/         # Database migration scripts
├── grafana/            # Grafana dashboards and provisioning
├── scripts/            # Helper bash/python scripts
├── docker-compose.yaml # Production/Main docker services setup
├── pyproject.toml      # Project dependencies managed by uv
└── README.md           # You are here!
```

---

<div align="center">
  <p>Built with ❤️ by <a href="https://github.com/your-username">Your Name/Team</a></p>
</div>

# Repository Guidelines

This document provides essential guidelines for contributing to the AKASHI Data Center PLC Telegram bot project.

## Project Structure

```
AkashiSovet/
├── bot/                 # Main bot package
│   ├── bot.py          # Entry point
│   ├── config.py       # Settings (pydantic)
│   └── logger.py       # Logging setup
├── stdlib/             # Shared modules
│   ├── handlers/       # Telegram command handlers
│   │   ├── user.py     # User commands
│   │   ├── superuser.py
│   │   └── blocks.py
│   ├── db.py          # SQLite database (aiosqlite)
│   ├── keyboards.py   # Inline keyboards
│   ├── llm.py         # LangChain LLM wrapper
│   └── pdf.py         # PDF generation
├── pyproject.toml     # Dependencies (uv)
└── .env               # Local configuration
```

## Development Commands

- **Run bot**: `python -m bot.bot` or `uv run python -m bot.bot`
- **Install dependencies**: `uv sync`
- **Add dependency**: `uv add <package>`

Configuration is managed via `.env` file. Copy `env.example` to `.env` and fill in required values.

## Coding Style

- **Python version**: 3.13+
- **Indentation**: 4 spaces (no tabs)
- **Line length**: Max 120 characters
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **Type hints**: Use full type annotations where practical
- **Async**: Prefer `async`/`await` for I/O operations (aiogram, aiosqlite)

Run `uv run ruff check .` to lint code (if ruff is added).

## Database

- Uses **SQLite** with `aiosqlite` (async driver)
- Schema defined in `stdlib/db.py`
- Database path configured via `DB_PATH` in `.env`

## Testing Guidelines

Currently, no test framework is configured. When adding tests:

- Place tests in a `tests/` directory at project root
- Use `pytest` with `pytest-asyncio` for async tests
- Naming: `test_<module>_<function>.py`
- Run with: `uv run pytest`

## Commit & Pull Request Guidelines

Use **Conventional Commits** format:

```
<type>(<scope>): <description>

[optional body]
```

Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`

Examples:
- `feat(handlers): add /status command`
- `fix(db): handle connection errors`
- `chore: update pyproject.toml`

**PR Requirements**:
- Clear description of changes
- Reference related issues (e.g., "Closes #12")
- Test locally before submitting

## Key Dependencies

- `aiogram>=3.27.0` — Telegram bot framework
- `langchain>=1.2.15` — LLM integration
- `pydantic-settings>=2.14.0` — Configuration
- `aiosqlite` — Async SQLite
- `loguru` — Logging (via logger.py)

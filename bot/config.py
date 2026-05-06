from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    SUPERUSER_IDS: list[int] = []

    DB_PATH: str = "./app.db"
    DATABASE_URL: str = ""
    # asyncpg: поднимайте max_size под ожидаемый параллелизм; max_connections в Postgres ≥ max + запас
    DB_POOL_MIN_SIZE: int = 2
    DB_POOL_MAX_SIZE: int = 30

    REDIS_URL: str = "redis://localhost:6379/0"

    # Веб-панель: базовый URL без завершающего «/» (для ссылок из бота /web)
    WEB_PUBLIC_URL: str = ""
    WEB_AUTH_TOKEN_TTL_SECONDS: int = 300
    ADMIN_SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 8
    # Секрет для подписи cookie admin_session (обязательно в проде; минимум 32 случайных символа)
    WEB_SESSION_SECRET: str = ""
    # Установите True за HTTPS reverse-proxy
    WEB_COOKIE_SECURE: bool = False
    # Лимит POST /login на IP (slowapi)
    WEB_LOGIN_RATE_LIMIT: str = "10/minute"

    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    # Logging
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"  # console level
    LOG_FILE_LEVEL: str = "INFO"
    LOG_ERROR_LEVEL: str = "ERROR"
    LOG_ROTATION_MB: int = 10
    LOG_RETENTION_DAYS: int = 7
    LOG_ERRORS_ROTATION_MB: int = 5
    LOG_ERRORS_RETENTION_DAYS: int = 30
    LOG_CLEAN_ON_START: bool = False
    LOG_MAX_TOTAL_MB: int = 1024

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("SUPERUSER_IDS", mode="before")
    @classmethod
    def parse_superuser_ids(cls, v: object) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, (int, float)):
            return [int(v)]
        return [int(x.strip()) for x in str(v).split(",") if x.strip()]

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)


config = Settings()

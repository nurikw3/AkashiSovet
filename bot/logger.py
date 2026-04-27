"""
Централизованная настройка Loguru.
Импортируй `logger` из этого модуля во всех файлах вместо стандартного logging.
"""
import sys
from loguru import logger


def setup_logging(level: str = "INFO") -> None:
    """Настроить форматы вывода. Вызвать один раз при старте бота."""
    logger.remove()  # убрать дефолтный handler

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )

    # stdout — все уровни >= level
    logger.add(sys.stdout, format=fmt, level=level, colorize=True)

    # файл — всё включая DEBUG, ротация 10 МБ, хранить 7 дней
    logger.add(
        "logs/bot.log",
        format=fmt,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        colorize=False,
    )

    # отдельный файл только для ошибок
    logger.add(
        "logs/errors.log",
        format=fmt,
        level="ERROR",
        rotation="5 MB",
        retention="30 days",
        encoding="utf-8",
        colorize=False,
    )


# Перехватываем стандартный logging (aiogram, aiosqlite и т.д.)
class InterceptHandler:
    """Перенаправляет записи stdlib logging → loguru."""

    def write(self, message):
        pass

    @staticmethod
    def install():
        import logging

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    level = logger.level(record.levelname).name
                except ValueError:
                    level = record.levelno
                frame, depth = sys._getframe(6), 6
                while frame and frame.f_code.co_filename == logging.__file__:
                    frame = frame.f_back
                    depth += 1
                logger.opt(depth=depth, exception=record.exc_info).log(
                    level, record.getMessage()
                )

        logging.basicConfig(handlers=[_Handler()], level=0, force=True)

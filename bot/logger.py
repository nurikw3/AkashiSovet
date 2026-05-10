from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from loguru import logger


def _iter_log_files(log_dir: str) -> list[Path]:
    p = Path(log_dir)
    if not p.exists():
        return []
    return [x for x in p.iterdir() if x.is_file()]


def prepare_log_storage(
    *,
    log_dir: str,
    clean_on_start: bool,
    max_total_mb: int,
) -> None:
    os.makedirs(log_dir, exist_ok=True)
    
    if clean_on_start:
        for fp in _iter_log_files(log_dir):
            try:
                fp.unlink(missing_ok=True)
            except Exception as e:
                print(f"Warning: Failed to delete {fp}: {e}", file=sys.stderr)

    max_bytes = max(0, int(max_total_mb)) * 1024 * 1024
    if max_bytes == 0:
        return
        
    files = _iter_log_files(log_dir)
    total = sum(f.stat().st_size for f in files)
    
    if total <= max_bytes:
        return

    files.sort(key=lambda f: f.stat().st_mtime)
    for fp in files:
        if total <= max_bytes:
            break
        try:
            size = fp.stat().st_size
            fp.unlink(missing_ok=True)
            total -= size
        except Exception as e:
            print(f"Warning: Failed to rotate {fp}: {e}", file=sys.stderr)


def setup_logging(
    *,
    level: str = "INFO",
    file_level: str = "INFO",
    error_level: str = "ERROR",
    log_dir: str = "logs",
    rotation_mb: int = 10,
    retention_days: int = 7,
    errors_rotation_mb: int = 5,
    errors_retention_days: int = 30,
) -> None:
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )

    logger.add(sys.stdout, format=fmt, level=level, colorize=True)

    app_log_path = Path(log_dir) / "bot.log"
    errors_log_path = Path(log_dir) / "errors.log"

    logger.add(
        app_log_path,
        format=fmt,
        level=file_level,
        rotation=f"{max(1, int(rotation_mb))} MB",
        retention=f"{max(1, int(retention_days))} days",
        encoding="utf-8",
        colorize=False,
        enqueue=True,
    )

    logger.add(
        errors_log_path,
        format=fmt,
        level=error_level,
        rotation=f"{max(1, int(errors_rotation_mb))} MB",
        retention=f"{max(1, int(errors_retention_days))} days",
        encoding="utf-8",
        colorize=False,
        enqueue=True,
    )

    InterceptHandler.install()


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

    @classmethod
    def install(cls) -> None:
        logging.basicConfig(handlers=[cls()], level=0, force=True)
        for name in logging.root.manager.loggerDict.keys():
            logging.getLogger(name).handlers = [cls()]
            logging.getLogger(name).propagate = False
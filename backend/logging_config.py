"""Настройка логирования: консоль + файлы с ротацией."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import settings

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_ERRORS_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 3


def setup_logging() -> None:
    """Идемпотентная настройка логгеров `jobpulse` и `jobpulse.parser`."""
    root = logging.getLogger("jobpulse")
    if getattr(root, "_jobpulse_configured", False):
        return

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root.setLevel(level)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    app_file = RotatingFileHandler(log_dir / "app.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
    app_file.setLevel(level)
    app_file.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(app_file)

    parser_logger = logging.getLogger("jobpulse.parser")
    errors_file = RotatingFileHandler(
        log_dir / "parsing_errors.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    errors_file.setLevel(logging.WARNING)
    errors_file.setFormatter(logging.Formatter(_ERRORS_FORMAT))
    parser_logger.addHandler(errors_file)

    root._jobpulse_configured = True  # type: ignore[attr-defined]

from __future__ import annotations

import logging
import logging.handlers

from backend.core.config import settings
from backend.core.run_context import get_current_run_id
from backend.core.workspace import REPOSITORY_ROOT

_FORMAT = "%(asctime)s | %(levelname)s | run=%(run_id)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LOG_DIR = REPOSITORY_ROOT / "logs"
LOG_FILE = LOG_DIR / "app.log"

_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


class _RunIdFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = get_current_run_id() or "-"

        return True


def setup_logging(level: str | None = None) -> None:
    root_logger = logging.getLogger()

    if root_logger.handlers:
        return

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)
    run_id_filter = _RunIdFilter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(run_id_filter)
    root_logger.addHandler(console_handler)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(run_id_filter)
    root_logger.addHandler(file_handler)

    root_logger.setLevel((level or settings.LOG_LEVEL or "INFO").upper())

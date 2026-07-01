import json
import logging
import os
from datetime import datetime, timezone


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "correlation_id"):
            log_entry["correlation_id"] = record.correlation_id
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging():
    """Setup logging configuration using environment variables."""
    log_level = os.getenv("HORDEFORGE_LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("HORDEFORGE_LOG_FORMAT", "text").lower()

    level = getattr(logging, log_level, logging.INFO)

    if log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJSONFormatter())
        logging.basicConfig(level=level, handlers=[handler])
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(name)s: %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name and configured level."""
    logger = logging.getLogger(name)
    log_level = os.getenv("HORDEFORGE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    logger.setLevel(level)
    return logger


# Setup logging when this module is imported
setup_logging()

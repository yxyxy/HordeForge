import logging
import os


def setup_logging():
    """Setup logging configuration using environment variables."""
    log_level = os.getenv("HORDEFORGE_LOG_LEVEL", "INFO").upper()

    # Convert string level to logging constant
    level = getattr(logging, log_level, logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s: %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # You can also configure specific loggers here if needed
    # For example, to set a different level for third-party libraries:
    # logging.getLogger('some_third_party_lib').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name and configured level."""
    logger = logging.getLogger(name)
    log_level = os.getenv("HORDEFORGE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    logger.setLevel(level)
    return logger


# Setup logging when this module is imported
setup_logging()

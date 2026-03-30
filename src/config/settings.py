"""Configuration settings for the application."""

import os
from typing import Optional


class Settings:
    """Application settings class.

    Attributes:
        app_name: Name of the application
        debug: Whether to run in debug mode
        database_url: URL for the database connection
        log_level: Level of logging
    """

    def __init__(self):
        self.app_name: str = os.getenv("APP_NAME", "HordeForge")
        self.debug: bool = os.getenv("DEBUG", "False").lower() == "true"
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./hordeforge.db")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
        self.container_registry: str = os.getenv(
            "CONTAINER_REGISTRY", "ghcr.io"
        )
        self.image_name: str = os.getenv(
            "IMAGE_NAME", f"{os.getenv('GITHUB_REPOSITORY', 'hordeforge')}"
        )


settings = Settings()

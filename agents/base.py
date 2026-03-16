"""Базовый класс для всех агентов в системе HordeForge."""

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """
    Абстрактный базовый класс для всех агентов.

    Все агенты должны наследоваться от этого класса и реализовывать метод run.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Основной метод выполнения агента.

        Args:
            context: Контекст выполнения агента

        Returns:
            Результат выполнения агента
        """
        pass

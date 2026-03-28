"""
Тесты для скрипта генерации документации по агентам.
"""

import os
import tempfile

from registry.agents import AgentRegistry, register_agents
from scripts.generate_agent_docs import generate_agent_docs


def test_generate_agent_docs():
    """Тестируем генерацию документации по агентам."""
    # Создаем реестр агентов и регистрируем агенты
    agent_registry = AgentRegistry()
    register_agents(agent_registry)

    # Создаем временный файл для тестирования
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as temp_file:
        temp_filename = temp_file.name

    try:
        # Вызываем функцию генерации документации
        generate_agent_docs(temp_filename)

        # Проверяем, что файл был создан
        assert os.path.exists(temp_filename)

        # Читаем содержимое файла
        with open(temp_filename, encoding="utf-8") as f:
            content = f.read()

        # Проверяем, что в документации есть заголовок
        assert "# Агенты HordeForge" in content

        # Проверяем, что в документации есть информация о каком-то агенте
        assert "dod_extractor" in content
        assert "Извлекает DoD (Definition of Done) из задач" in content

        # Проверяем, что в документации есть таблица с агентами
        assert (
            "| Название | Описание | Класс | Категория | Входной контракт | Выходной контракт |"
            in content
        )

    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


def test_generate_agent_docs_structure():
    """Тестируем структуру генерируемой документации."""
    # Создаем временный файл для тестирования
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as temp_file:
        temp_filename = temp_file.name

    try:
        # Вызываем функцию генерации документации
        generate_agent_docs(temp_filename)

        # Проверяем, что файл был создан
        assert os.path.exists(temp_filename)

        # Читаем содержимое файла
        with open(temp_filename, encoding="utf-8") as f:
            content = f.read()

        # Проверяем, что в документации есть заголовок
        assert "# Агенты HordeForge" in content

        # Проверяем, что в документации есть таблица с агентами
        assert (
            "| Название | Описание | Класс | Категория | Входной контракт | Выходной контракт |"
            in content
        )

        # Проверяем, что в документации есть хотя бы один агент
        assert "dod_extractor" in content

    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

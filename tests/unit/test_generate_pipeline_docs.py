"""
Тесты для скрипта генерации документации по пайплайнам.
"""

import os
import tempfile

from scripts.generate_pipeline_docs import generate_pipeline_docs


def test_generate_pipeline_docs_structure():
    """Тестируем структуру генерируемой документации."""
    # Создаем временный файл для тестирования
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as temp_file:
        temp_filename = temp_file.name

    try:
        # Вызываем функцию генерации документации
        generate_pipeline_docs(temp_filename)

        # Проверяем, что файл был создан
        assert os.path.exists(temp_filename)

        # Читаем содержимое файла
        with open(temp_filename, encoding="utf-8") as f:
            content = f.read()

        # Проверяем, что в документации есть заголовок
        assert "# Пайплайны HordeForge" in content

        # Проверяем, что в документации есть таблица с пайплайнами
        assert "| Название | Описание | Путь | Версия |" in content

        # Проверяем, что в документации есть хотя бы один пайплайн
        assert "init_pipeline" in content or "feature_pipeline" in content

        # Проверяем, что документация содержит новые секции
        assert "**Triggers**" in content
        assert "**Logging**" in content
        assert "**Loops**" in content

    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

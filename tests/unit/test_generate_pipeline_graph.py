"""
Тесты для скрипта генерации графа пайплайнов в формате Mermaid.
"""

import os
import tempfile

from scripts.generate_pipeline_graph import generate_pipeline_graph


def test_generate_pipeline_graph_structure():
    """Тестируем структуру генерируемого графа пайплайнов."""
    # Создаем временный файл для тестирования
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as temp_file:
        temp_filename = temp_file.name

    try:
        # Вызываем функцию генерации графа
        generate_pipeline_graph(temp_filename)

        # Проверяем, что файл был создан
        assert os.path.exists(temp_filename)

        # Читаем содержимое файла
        with open(temp_filename, encoding="utf-8") as f:
            content = f.read()

        # Проверяем, что в документации есть заголовок
        assert "# Графы пайплайнов" in content

        # Проверяем, что в документации есть начало диаграммы Mermaid
        assert "```mermaid" in content

        # Проверяем, что в документации есть диаграмма потока
        assert "graph" in content or "flowchart" in content

        # Проверяем, что в документации есть хотя бы один пайплайн
        assert "init_pipeline" in content or "feature_pipeline" in content

    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


def test_generate_pipeline_graph_has_diagrams():
    """Тестируем, что генерируются диаграммы для конкретных пайплайнов."""
    # Создаем временный файл для тестирования
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as temp_file:
        temp_filename = temp_file.name

    try:
        # Вызываем функцию генерации графа
        generate_pipeline_graph(temp_filename)

        # Проверяем, что файл был создан
        assert os.path.exists(temp_filename)

        # Читаем содержимое файла
        with open(temp_filename, encoding="utf-8") as f:
            content = f.read()

        # Проверяем, что в документации есть заголовок
        assert "# Графы пайплайнов" in content

        # Проверяем, что в документации есть Mermaid блоки
        assert content.count("```mermaid") >= 1

    finally:
        # Удаляем временный файл
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

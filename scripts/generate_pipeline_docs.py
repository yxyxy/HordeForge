#!/usr/bin/env python3
"""
Скрипт для генерации документации по пайплайнам в docs/pipelines.md.
"""

import os
import sys
from pathlib import Path

try:
    from orchestrator.loader import PipelineLoader
    from registry.bootstrap import init_registries
except ImportError:
    # Добавляем путь к корню проекта для правильного импорта
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    from orchestrator.loader import PipelineLoader
    from registry.bootstrap import init_registries


def _format_triggers(triggers: list[str]) -> str:
    if not triggers:
        return "Не указаны"
    return ", ".join(triggers)


def _format_logging(logging_config: dict) -> str:
    if not logging_config:
        return "Не указаны"
    parts = [f"{key}={logging_config[key]}" for key in sorted(logging_config.keys())]
    return ", ".join(parts)


def _format_loops(loops: list) -> str:
    if not loops:
        return "Не указаны"
    parts = []
    for loop in loops:
        steps = ", ".join(loop.steps)
        parts.append(f"{loop.condition} -> [{steps}]")
    return "; ".join(parts)


def generate_pipeline_docs(output_path: str = "docs/pipelines.md"):
    """
    Генерирует документацию по пайплайнам и сохраняет в указанный файл.

    Args:
        output_path: Путь к файлу, куда сохранить документацию
    """
    # Инициализируем реестры
    registries = init_registries()
    pipeline_registry = registries["pipeline_registry"]

    # Получаем список всех пайплайнов
    pipelines = pipeline_registry.list()

    # Формируем содержимое документации
    content = []
    content.append("# Пайплайны HordeForge\n")
    content.append(
        "Этот документ содержит информацию обо всех зарегистрированных пайплайнах системы.\n"
    )

    if pipelines:
        # Добавляем таблицу с пайплайнами
        content.append("## Список пайплайнов\n")
        content.append("| Название | Описание | Путь | Версия |")
        content.append("|----------|----------|------|--------|")

        # Сортируем пайплайны по имени для более читаемого вывода
        sorted_pipelines = sorted(pipelines, key=lambda x: x.name)

        for pipeline in sorted_pipelines:
            name = pipeline.name
            description = pipeline.description or "Описание отсутствует"
            path = pipeline.path
            version = pipeline.version or "Не указана"

            content.append(f"| {name} | {description} | {path} | {version} |")

        content.append("")  # Пустая строка после таблицы

        # Добавляем подробное описание для каждого пайплайна
        content.append("## Подробное описание пайплайнов\n")

        for pipeline in sorted_pipelines:
            pipeline_def = None
            if hasattr(pipeline_registry, "get_pipeline_definition"):
                pipeline_def = pipeline_registry.get_pipeline_definition(pipeline.name)
            if pipeline_def is None:
                try:
                    loader = PipelineLoader()
                    pipeline_def = loader.load(pipeline.path)
                except Exception:
                    pipeline_def = None

            triggers = pipeline_def.triggers if pipeline_def is not None else []
            logging_config = pipeline_def.logging if pipeline_def is not None else {}
            loops = pipeline_def.loops if pipeline_def is not None else []

            content.append(f"### {pipeline.name}\n")
            content.append(f"- **Описание**: {pipeline.description or 'Описание отсутствует'}\n")
            content.append(f"- **Путь**: `{pipeline.path}`\n")
            content.append(f"- **Версия**: {pipeline.version or 'Не указана'}\n")
            content.append(f"- **Triggers**: {_format_triggers(triggers)}\n")
            content.append(f"- **Logging**: {_format_logging(logging_config)}\n")
            content.append(f"- **Loops**: {_format_loops(loops)}\n")
            content.append("")
    else:
        content.append("## Нет зарегистрированных пайплайнов\n")
        content.append("В системе пока не зарегистрировано ни одного пайплайна.\n")

    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Записываем содержимое в файл
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    print(f"Документация по пайплайнам успешно сгенерирована: {output_path}")


def main():
    """Основная функция для запуска скрипта."""
    generate_pipeline_docs()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Скрипт для генерации визуального представления пайплайнов в формате Mermaid в docs/pipeline_graph.md.
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


def generate_pipeline_graph(output_path: str = "docs/pipeline_graph.md"):
    """
    Генерирует визуальное представление пайплайнов в формате Mermaid и сохраняет в указанный файл.

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
    content.append("# Графы пайплайнов\n")
    content.append(
        "Этот документ содержит визуальные представления пайплайнов в формате Mermaid.\n"
    )

    if pipelines:
        # Загружаем каждый пайплайн и создаем для него диаграмму
        loader = PipelineLoader()

        for pipeline_meta in pipelines:
            try:
                # Загружаем полное определение пайплайна
                pipeline_def = loader.load(pipeline_meta.path)

                content.append(f"## {pipeline_def.pipeline_name}\n")

                if pipeline_def.description:
                    content.append(f"*{pipeline_def.description}*\n")

                content.append("```mermaid")
                content.append("graph TD")

                # Добавляем узлы для каждого шага
                for step in pipeline_def.steps:
                    step_label = f"{step.name}({step.agent})"
                    content.append(f"    {step.name}[{step_label}]")

                # Добавляем связи между шагами
                has_dependencies = False
                for step in pipeline_def.steps:
                    for dep in step.depends_on:
                        content.append(f"    {dep} --> {step.name}")
                        has_dependencies = True

                # Если нет зависимостей, просто покажем последовательность шагов
                if not has_dependencies and len(pipeline_def.steps) > 1:
                    steps = [step.name for step in pipeline_def.steps]
                    for i in range(len(steps) - 1):
                        content.append(f"    {steps[i]} --> {steps[i + 1]}")

                content.append("```")
                content.append("")  # Пустая строка после диаграммы

            except Exception as e:
                # Если не удалось загрузить пайплайн, добавляем информацию об ошибке
                content.append(f"## {pipeline_meta.name}\n")
                content.append(f"⚠️ Ошибка загрузки пайплайна: {str(e)}\n")
                content.append("")

    else:
        content.append("## Нет зарегистрированных пайплайнов\n")
        content.append("В системе пока не зарегистрировано ни одного пайплайна.\n")

    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Записываем содержимое в файл
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    print(f"Графы пайплайнов успешно сгенерированы: {output_path}")


def main():
    """Основная функция для запуска скрипта."""
    generate_pipeline_graph()


if __name__ == "__main__":
    main()

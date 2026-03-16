#!/usr/bin/env python3
"""
Скрипт для генерации документации по агентам в docs/agents.md.
"""

import os
import sys
from pathlib import Path

try:
    from registry.bootstrap import init_registries
except ImportError:
    # Добавляем путь к корню проекта для правильного импорта
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    from registry.bootstrap import init_registries


def generate_agent_docs(output_path: str = "docs/agents.md"):
    """
    Генерирует документацию по агентам и сохраняет в указанный файл.

    Args:
        output_path: Путь к файлу, куда сохранить документацию
    """
    # Инициализируем реестры
    registries = init_registries()
    agent_registry = registries["agent_registry"]

    # Получаем список всех агентов
    agents = agent_registry.list()

    # Формируем содержимое документации
    content = []
    content.append("# Агенты HordeForge\n")
    content.append(
        "Этот документ содержит информацию обо всех зарегистрированных агентах системы.\n"
    )

    if agents:
        # Добавляем таблицу с агентами
        content.append("## Список агентов\n")
        content.append(
            "| Название | Описание | Класс | Категория | Входной контракт | Выходной контракт |"
        )
        content.append(
            "|----------|----------|-------|-----------|------------------|-------------------|"
        )

        # Сортируем агенты по имени для более читаемого вывода
        sorted_agents = sorted(agents, key=lambda x: x.name)

        for agent in sorted_agents:
            name = agent.name
            description = agent.description or "Описание отсутствует"
            agent_class = agent.agent_class
            category = agent.category or "Не указана"
            input_contract = agent.input_contract or "Не требуется"
            output_contract = agent.output_contract or "Не предусмотрен"

            content.append(
                f"| {name} | {description} | {agent_class} | {category} | {input_contract} | {output_contract} |"
            )

        content.append("")  # Пустая строка после таблицы

        # Добавляем подробное описание для каждого агента
        content.append("## Подробное описание агентов\n")

        for agent in sorted_agents:
            content.append(f"### {agent.name}\n")
            content.append(f"- **Описание**: {agent.description or 'Описание отсутствует'}\n")
            content.append(f"- **Класс**: `{agent.agent_class}`\n")
            content.append(f"- **Категория**: {agent.category or 'Не указана'}\n")
            content.append(f"- **Входной контракт**: {agent.input_contract or 'Не требуется'}\n")
            content.append(
                f"- **Выходной контракт**: {agent.output_contract or 'Не предусмотрен'}\n"
            )
            content.append(f"- **Версия**: {agent.version or 'Не указана'}\n")
            content.append(f"- **Автор**: {agent.author or 'Не указан'}\n")
            content.append("")
    else:
        content.append("## Нет зарегистрированных агентов\n")
        content.append("В системе пока не зарегистрировано ни одного агента.\n")

    # Создаем директорию, если она не существует
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Записываем содержимое в файл
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    print(f"Документация по агентам успешно сгенерирована: {output_path}")


def main():
    """Основная функция для запуска скрипта."""
    generate_agent_docs()


if __name__ == "__main__":
    main()

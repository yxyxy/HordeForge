#!/usr/bin/env python3
"""
Скрипт для автоматического обновления агентов, чтобы они наследовались от BaseAgent.
"""

import re
from pathlib import Path


def update_agent_file(filepath):
    """Обновляет файл агента, добавляя наследование от BaseAgent и импорт."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Проверяем, содержит ли файл класс агента (обычно имеет метод run и атрибут name)
    if "def run(self, context:" not in content:
        print(f"Пропускаем {filepath}, так как не содержит метода run")
        return False

    # Проверяем, уже ли наследуется от BaseAgent
    if (
        "(BaseAgent)" in content
        or "BaseAgent" in content
        and "from agents.base import BaseAgent" in content
    ):
        print(f"Пропускаем {filepath}, так как уже наследуется от BaseAgent")
        return False

    # Проверяем, есть ли уже импорт BaseAgent
    has_base_import = "from agents.base import BaseAgent" in content

    # Находим класс агента (обычно это класс с атрибутами name и методом run)
    class_pattern = r"class\s+(\w+)\s*:"  # Находит класс, который не наследуется ни от чего
    classes = re.findall(class_pattern, content)

    # Находим классы, которые могут быть агентами (имеют name и run)
    agent_classes = []
    for cls in classes:
        # Проверяем, есть ли у класса атрибут name и метод run
        class_pattern_with_name = rf"class\s+{cls}\s*:(.*?)(?=class\s+\w+\s*:|$)"
        class_match = re.search(class_pattern_with_name, content, re.DOTALL)
        if class_match:
            class_content = class_match.group(1)
            if (
                "name =" in class_content or ".name" in class_content
            ) and "def run(self, context:" in class_content:
                agent_classes.append(cls)

    if not agent_classes:
        print(f"Не найдены классы агентов в {filepath}")
        return False

    # Добавляем импорт BaseAgent, если его нет
    if not has_base_import:
        # Находим место после других импортов, но до определения классов
        import_end_pos = content.find("\nclass ")  # Находим начало первого класса
        if import_end_pos == -1:
            import_end_pos = content.find("\n@")  # Или декоратора
        if import_end_pos == -1:
            import_end_pos = len(content)  # Или конец файла

        # Вставляем импорт BaseAgent перед первым классом
        import_line = "\nfrom agents.base import BaseAgent\n"
        content = content[:import_end_pos] + import_line + content[import_end_pos:]

    # Обновляем каждый класс агента, добавляя наследование от BaseAgent
    for agent_class in agent_classes:
        old_class_decl = f"class {agent_class}:"
        new_class_decl = f"class {agent_class}(BaseAgent):"
        content = content.replace(old_class_decl, new_class_decl)
        print(f"Обновлен класс {agent_class} в {filepath}")

    # Сохраняем обновленный файл
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def main():
    agents_dir = Path("agents")
    updated_count = 0

    # Получаем все файлы агентов
    agent_files = [
        f for f in agents_dir.glob("*.py") if f.name != "base.py" and f.name != "__init__.py"
    ]

    for agent_file in agent_files:
        print(f"Обработка {agent_file}")
        if update_agent_file(agent_file):
            updated_count += 1

    print(f"\nОбновлено {updated_count} файлов агентов.")


if __name__ == "__main__":
    main()

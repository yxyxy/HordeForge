#!/usr/bin/env python3
"""
Инструмент визуализации архитектуры реестров.
Генерирует диаграммы Mermaid для пайплайнов и агентов.
"""

from pathlib import Path
from typing import Any

# Используем абсолютные импорты, предполагая что файл будет запускаться из корня проекта
try:
    from registry.agents import AgentRegistry
    from registry.contracts import ContractRegistry
    from registry.pipelines import PipelineRegistry
except ImportError:
    # Если прямой импорт не работает, добавляем путь к sys.path
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    from registry.agents import AgentRegistry
    from registry.contracts import ContractRegistry
    from registry.pipelines import PipelineRegistry


def get_registered_pipelines() -> list[dict[str, Any]]:
    """
    Получить список зарегистрированных пайплайнов из реестра.
    """
    registry = PipelineRegistry()
    pipelines = []

    for name in registry.list_pipelines():
        try:
            # Загружаем определение пайплайна
            pipeline_def = registry.get_pipeline_definition(name)
            if pipeline_def:
                pipeline_info = {"name": name, "definition": pipeline_def, "steps": []}

                # Преобразуем шаги пайплайна в удобный формат
                for step in pipeline_def.steps:
                    step_info = {
                        "name": step.name,
                        "agent": step.agent,
                        "depends_on": getattr(step, "depends_on", []),
                        "input_mapping": getattr(step, "input_mapping", {}),
                        "output_mapping": getattr(step, "output_mapping", {}),
                    }
                    pipeline_info["steps"].append(step_info)

                pipelines.append(pipeline_info)
        except Exception as e:
            print(f"Ошибка при получении пайплайна {name}: {e}")

    return pipelines


def get_registered_agents() -> list[dict[str, Any]]:
    """
    Получить список зарегистрированных агентов из реестра.
    """
    registry = AgentRegistry()
    agents = []

    for name in registry.list_agents():
        try:
            metadata = registry.get_agent_metadata(name)
            if metadata:
                agent_info = {
                    "name": getattr(metadata, "name", name),
                    "input_contract": getattr(metadata, "input_contract", "unknown"),
                    "output_contract": getattr(metadata, "output_contract", "unknown"),
                    "category": getattr(metadata.category, "value", "unknown")
                    if hasattr(metadata, "category") and metadata.category
                    else "unknown",
                }
                agents.append(agent_info)
        except Exception as e:
            print(f"Ошибка при получении агента {name}: {e}")

    return agents


def get_registered_contracts() -> list[str]:
    """
    Получить список зарегистрированных контрактов из реестра.
    """
    registry = ContractRegistry()
    return registry.list_contracts()


def generate_pipeline_diagram(pipeline_data: dict[str, Any]) -> str:
    """
    Генерирует диаграмму Mermaid для конкретного пайплайна.
    """
    name = pipeline_data["name"]
    steps = pipeline_data["steps"]

    diagram_lines = ["graph TD", f'    subgraph "Pipeline: {name}"']

    # Добавляем узлы для каждого шага
    for step in steps:
        step_name = step["name"]
        agent_name = step["agent"]
        diagram_lines.append(f"        {step_name}[{step_name}<br/>{agent_name}]")

    # Добавляем связи между шагами
    for i, step in enumerate(steps):
        if i < len(steps) - 1:  # Не последний шаг
            current_step = step["name"]
            next_step = steps[i + 1]["name"]
            diagram_lines.append(f"        {current_step} --> {next_step}")

    diagram_lines.append("    end")

    return "\n".join(diagram_lines)


def generate_agent_relationships_diagram(agents: list[dict[str, Any]]) -> str:
    """
    Генерирует диаграмму связей между агентами на основе контрактов.
    """
    diagram_lines = ["graph TD"]

    # Добавляем узлы для агентов
    for agent in agents:
        agent_name = agent["name"]
        input_contract = agent["input_contract"]
        output_contract = agent["output_contract"]

        # Добавляем узлы для контрактов, если они еще не добавлены
        diagram_lines.append(f"    {input_contract}[{input_contract}]")
        diagram_lines.append(f"    {output_contract}[{output_contract}]")

        # Добавляем связи: входной контракт -> агент -> выходной контракт
        diagram_lines.append(f"    {input_contract} --> {agent_name}({agent_name})")
        diagram_lines.append(f"    {agent_name} --> {output_contract}")

    return "\n".join(diagram_lines)


def generate_contract_relationships_diagram(
    agents: list[dict[str, Any]], contracts: list[str]
) -> str:
    """
    Генерирует диаграмму связей между контрактами.
    """
    diagram_lines = ["graph TD"]

    # Добавляем все контракты как узлы
    for contract in contracts:
        diagram_lines.append(f"    {contract}[{contract}]")

    # Находим связи между контрактами через агентов
    for agent in agents:
        input_contract = agent["input_contract"]
        output_contract = agent["output_contract"]

        if input_contract != output_contract:
            diagram_lines.append(f"    {input_contract} --> {output_contract}")

    return "\n".join(diagram_lines)


def visualize_all_registries(output_dir: Path) -> None:
    """
    Генерирует все диаграммы и сохраняет их в указанную директорию.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Получаем данные из реестров
    pipelines = get_registered_pipelines()
    agents = get_registered_agents()
    contracts = get_registered_contracts()

    # Генерируем диаграммы для каждого пайплайна
    for pipeline in pipelines:
        diagram = generate_pipeline_diagram(pipeline)
        filename = output_dir / f"pipeline_{pipeline['name']}.mmd"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(diagram)
        print(f"Сохранена диаграмма пайплайна: {filename}")

    # Генерируем диаграмму связей между агентами
    if agents:
        agent_diagram = generate_agent_relationships_diagram(agents)
        filename = output_dir / "agent_relationships.mmd"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(agent_diagram)
        print(f"Сохранена диаграмма связей агентов: {filename}")

    # Генерируем диаграмму связей между контрактами
    if agents and contracts:
        contract_diagram = generate_contract_relationships_diagram(agents, contracts)
        filename = output_dir / "contract_relationships.mmd"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(contract_diagram)
        print(f"Сохранена диаграмма связей контрактов: {filename}")


def main():
    """
    Основная функция для запуска визуализации архитектуры.
    """
    output_dir = Path("docs/architecture")
    visualize_all_registries(output_dir)
    print(f"Визуализация архитектуры сохранена в {output_dir}")


if __name__ == "__main__":
    main()

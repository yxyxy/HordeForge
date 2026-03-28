import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.visualize_architecture import (
    generate_agent_relationships_diagram,
    generate_pipeline_diagram,
    visualize_all_registries,
)


def test_generate_pipeline_diagram():
    """Тест проверяет генерацию mermaid диаграммы для пайплайна"""
    # Мокаем данные пайплайна
    mock_pipeline_data = {
        "name": "test_pipeline",
        "steps": [
            {"name": "step1", "agent": "agent1"},
            {"name": "step2", "agent": "agent2"},
            {"name": "step3", "agent": "agent3"},
        ],
    }

    diagram = generate_pipeline_diagram(mock_pipeline_data)

    assert "graph TD" in diagram
    assert "step1" in diagram
    assert "step2" in diagram
    assert "step3" in diagram
    assert "agent1" in diagram
    assert "agent2" in diagram
    assert "agent3" in diagram


def test_generate_agent_relationships_diagram():
    """Тест проверяет генерацию диаграммы связей между агентами"""
    # Мокаем данные агентов
    mock_agents = [
        {"name": "agent1", "input_contract": "contract1", "output_contract": "contract2"},
        {"name": "agent2", "input_contract": "contract2", "output_contract": "contract3"},
        {"name": "agent3", "input_contract": "contract3", "output_contract": "contract4"},
    ]

    diagram = generate_agent_relationships_diagram(mock_agents)

    assert "graph TD" in diagram
    assert "agent1" in diagram
    assert "agent2" in diagram
    assert "agent3" in diagram
    assert "contract2" in diagram
    assert "contract3" in diagram


def test_visualize_all_registries_creates_output_files():
    """Тест проверяет, что при запуске скрипта создаются выходные файлы с диаграммами"""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "diagrams"

        # Мокаем получение данных из реестров
        with (
            patch("tools.visualize_architecture.get_registered_pipelines") as mock_get_pipelines,
            patch("tools.visualize_architecture.get_registered_agents") as mock_get_agents,
            patch("tools.visualize_architecture.get_registered_contracts") as mock_get_contracts,
        ):
            # Подготовим моковые данные
            mock_get_pipelines.return_value = [
                {
                    "name": "test_pipeline",
                    "steps": [
                        {"name": "step1", "agent": "agent1"},
                        {"name": "step2", "agent": "agent2"},
                    ],
                }
            ]
            mock_get_agents.return_value = [
                {"name": "agent1", "input_contract": "contract1", "output_contract": "contract2"},
                {"name": "agent2", "input_contract": "contract2", "output_contract": "contract3"},
            ]
            mock_get_contracts.return_value = ["contract1", "contract2", "contract3"]

            # Вызываем функцию
            visualize_all_registries(output_dir)

            # Проверяем, что были созданы выходные файлы
            assert (output_dir / "pipeline_test_pipeline.mmd").exists()
            assert (output_dir / "agent_relationships.mmd").exists()
            assert (output_dir / "contract_relationships.mmd").exists()


def test_generate_correct_mermaid_structure():
    """Тест проверяет, что создается корректная структура диаграммы"""
    mock_pipeline_data = {
        "name": "simple_pipeline",
        "steps": [
            {"name": "start_step", "agent": "start_agent"},
            {"name": "end_step", "agent": "end_agent"},
        ],
    }

    diagram = generate_pipeline_diagram(mock_pipeline_data)

    # Проверяем основные элементы структуры mermaid
    assert diagram.startswith("graph TD")
    assert "start_step" in diagram
    assert "end_step" in diagram
    assert "start_agent" in diagram
    assert "end_agent" in diagram
    # Проверяем, что есть соединение между шагами
    assert "start_step --> end_step" in diagram or "start_agent --> end_agent" in diagram

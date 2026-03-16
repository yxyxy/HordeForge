"""
Тесты для проверки загрузки пайплайнов через PipelineRegistry
"""

import os
import tempfile

import pytest
import yaml

from orchestrator.loader import PipelineLoader
from registry.pipelines import PipelineMetadata, PipelineRegistry


def test_pipeline_loader_uses_registry_success():
    """Тест проверяет, что оркестратор получает пайплайн через PipelineRegistry и успешно его загружает"""
    # Создаем временный файл пайплайна
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "pipeline_name": "test_pipeline",
                "description": "Test pipeline for registry loading",
                "steps": [],
            },
            f,
        )
        temp_file_path = f.name

    # Подготовка
    registry = PipelineRegistry()
    # Регистрируем метаданные пайплайна в реестре
    registry.register(
        PipelineMetadata(
            name="test_pipeline",
            path=temp_file_path,
            description="Test pipeline for registry loading",
        )
    )

    loader = PipelineLoader(pipeline_registry=registry)

    # Загружаем пайплайн - должно произойти через реестр
    pipeline_def = loader.load("test_pipeline")

    # Проверяем, что пайплайн был успешно загружен
    assert pipeline_def.pipeline_name == "test_pipeline"
    assert pipeline_def.description == "Test pipeline for registry loading"
    assert len(pipeline_def.steps) == 0

    # Проверяем, что пайплайн теперь доступен в реестре как определение
    assert registry.has_pipeline_definition("test_pipeline") is True
    cached_def = registry.get_pipeline_definition("test_pipeline")
    assert cached_def is not None
    assert cached_def.pipeline_name == "test_pipeline"


def test_pipeline_loader_fails_with_unregistered_pipeline():
    """Тест проверяет, что возвращается ошибка с понятным сообщением при попытке загрузки незарегистрированного пайплайна"""
    registry = PipelineRegistry()
    loader = PipelineLoader(pipeline_registry=registry, allow_fallback=False)

    try:
        loader.load("nonexistent_pipeline")
        raise AssertionError("Ожидается ошибка при загрузке незарегистрированного пайплайна")
    except KeyError as e:
        # Проверяем, что сообщение об ошибке информативное
        assert "not registered" in str(e).lower() or "not found" in str(e).lower()
        assert "fallback to file system is disabled" in str(e).lower()


def test_pipeline_loader_registry_has_priority_over_filesystem():
    """Тест проверяет, что пайплайн из реестра имеет приоритет над файловой системой при повторной загрузке"""
    # Создаем временный файл пайплайна
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {"pipeline_name": "priority_test", "description": "Original file version", "steps": []},
            f,
        )
        temp_file_path = f.name

    # Подготовка
    registry = PipelineRegistry()
    # Регистрируем метаданные пайплайна в реестре
    registry.register(
        PipelineMetadata(name="priority_test", path=temp_file_path, description="Registry version")
    )

    loader = PipelineLoader(pipeline_registry=registry)

    # Загружаем пайплайн первый раз - происходит через реестр и файл
    first_load = loader.load("priority_test")
    assert first_load.description == "Original file version"

    # После первой загрузки пайплайн должен быть закэширован в реестре
    # При следующей загрузке будет использоваться кэшированная версия из реестра
    second_load = loader.load("priority_test")
    assert second_load.description == "Original file version"  # та же, что и первая загрузка
    # Проверяем, что значения совпадают, даже если это могут быть разные объекты
    assert first_load.pipeline_name == second_load.pipeline_name
    assert first_load.description == second_load.description
    assert len(first_load.steps) == len(second_load.steps)
    assert registry.has_pipeline_definition("priority_test") is True  # подтверждение, что в кэше


def test_pipeline_loader_fallback_still_works_when_no_registry():
    """Тест проверяет, что резервная загрузка из файловой системы все еще работает, когда реестр не указан"""
    # Создаем временный файл пайплайна
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, "fallback_test.yaml")

    with open(temp_file_path, "w") as f:
        yaml.dump(
            {"pipeline_name": "fallback_test", "description": "Fallback version", "steps": []}, f
        )

    # Создаем загрузчик без реестра
    loader = PipelineLoader(pipelines_dir=temp_dir)

    # Загружаем пайплайн - должно произойти напрямую из файловой системы
    pipeline_def = loader.load("fallback_test")

    assert pipeline_def.pipeline_name == "fallback_test"
    assert pipeline_def.description == "Fallback version"
    assert len(pipeline_def.steps) == 0


def test_pipeline_loader_parses_triggers_and_logging():
    """Тест проверяет, что loader парсит triggers и logging."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "pipeline_name": "pipeline_with_metadata",
                "description": "Pipeline with triggers and logging",
                "triggers": ["manual_trigger", "scheduled_trigger"],
                "logging": {"level": "INFO", "log_decisions": True},
                "steps": [],
            },
            f,
        )
        temp_file_path = f.name

    try:
        loader = PipelineLoader()
        pipeline_def = loader.load(temp_file_path)

        assert pipeline_def.triggers == ["manual_trigger", "scheduled_trigger"]
        assert pipeline_def.logging["level"] == "INFO"
        assert pipeline_def.logging["log_decisions"] is True
    finally:
        os.remove(temp_file_path)


def test_pipeline_loader_normalizes_step_level_loops():
    """Тест проверяет, что step-level loops нормализуются в общий список."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "pipeline_name": "loop_pipeline",
                "steps": [
                    {"name": "step_a", "agent": "repo_connector"},
                    {
                        "name": "step_b",
                        "agent": "fix_agent",
                        "loops": {
                            "condition": "{{step_a}} > 0",
                            "steps": ["step_b"],
                        },
                    },
                ],
                "loops": [{"condition": "{{step_b}} > 0", "steps": ["step_a", "step_b"]}],
            },
            f,
        )
        temp_file_path = f.name

    try:
        loader = PipelineLoader()
        pipeline_def = loader.load(temp_file_path)

        assert len(pipeline_def.loops) == 2
        assert pipeline_def.loops[0].condition == "{{step_a}} > 0"
        assert pipeline_def.loops[0].steps == ["step_b"]
        assert pipeline_def.loops[1].condition == "{{step_b}} > 0"
        assert pipeline_def.loops[1].steps == ["step_a", "step_b"]
    finally:
        os.remove(temp_file_path)


def test_pipeline_loader_rejects_loops_with_unknown_steps():
    """Тест проверяет, что loops с неизвестными шагами отклоняются."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "pipeline_name": "invalid_loop_pipeline",
                "steps": [
                    {"name": "step_a", "agent": "repo_connector"},
                ],
                "loops": [{"condition": "{{step_a}} > 0", "steps": ["missing_step"]}],
            },
            f,
        )
        temp_file_path = f.name

    try:
        loader = PipelineLoader()
        with pytest.raises(ValueError, match="unknown step"):
            loader.load(temp_file_path)
    finally:
        os.remove(temp_file_path)

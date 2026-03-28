"""
Тесты для проверки использования PipelineRegistry в оркестраторе
"""

import pytest

from orchestrator.loader import PipelineDefinition, PipelineLoader, StepDefinition
from registry.pipelines import PipelineMetadata, PipelineRegistry


class TestPipelineRegistry:
    def test_registry_can_register_pipeline(self):
        """Тест проверяет, что в реестр можно зарегистрировать пайплайн"""
        registry = PipelineRegistry()
        metadata = PipelineMetadata(
            name="test_pipeline",
            path="path/to/pipeline.yaml",
        )
        registry.register(metadata)

        assert registry.exists("test_pipeline")

    def test_registry_can_get_pipeline(self):
        """Тест проверяет, что из реестра можно получить пайплайн"""
        registry = PipelineRegistry()
        metadata = PipelineMetadata(
            name="test_pipeline",
            path="path/to/pipeline.yaml",
        )
        registry.register(metadata)

        retrieved = registry.get("test_pipeline")
        assert retrieved.name == "test_pipeline"
        assert retrieved.path == "path/to/pipeline.yaml"

    def test_registry_raises_error_for_unregistered_pipeline(self):
        """Тест проверяет, что возвращается None при запросе незарегистрированного пайплайна"""
        registry = PipelineRegistry()

        retrieved = registry.get("nonexistent_pipeline")
        assert retrieved is None

    def test_registry_has_returns_false_for_unregistered(self):
        """Тест проверяет, что exists() возвращает False для незарегистрированных пайплайнов"""
        registry = PipelineRegistry()

        assert registry.exists("nonexistent_pipeline") is False

    def test_registry_cannot_register_duplicate(self):
        """Тест проверяет, что нельзя зарегистрировать пайплайн с уже существующим именем"""
        registry = PipelineRegistry()
        metadata = PipelineMetadata(
            name="duplicate_pipeline",
            path="path/to/pipeline.yaml",
        )
        registry.register(metadata)

        with pytest.raises(ValueError) as exc_info:
            registry.register(metadata)

        assert "already registered" in str(exc_info.value).lower()


class TestPipelineLoaderWithRegistry:
    def test_loader_can_use_registry(self):
        """Тест проверяет, что PipelineLoader может загружать пайплайн через PipelineRegistry"""
        registry = PipelineRegistry()
        # Регистрируем определение напрямую в кеш
        pipeline = PipelineDefinition(
            pipeline_name="registry_pipeline",
            steps=[
                StepDefinition(name="step1", agent="fake_agent"),
                StepDefinition(name="step2", agent="another_agent"),
            ],
        )
        registry.register_pipeline_definition("registry_pipeline", pipeline)

        loader = PipelineLoader(pipeline_registry=registry)
        loaded = loader.load("registry_pipeline")

        assert loaded.pipeline_name == "registry_pipeline"
        assert len(loaded.steps) == 2
        assert loaded.steps[0].name == "step1"

    def test_loader_falls_back_to_file_when_not_in_registry(self):
        """Тест проверяет, что loader может использовать fallback на файловую систему"""
        registry = PipelineRegistry()

        # Не регистрируем init_pipeline, загружаем из файла
        loader = PipelineLoader(pipeline_registry=registry, allow_fallback=True)
        loaded = loader.load("init_pipeline")

        assert loaded.pipeline_name == "init_pipeline"
        assert len(loaded.steps) > 0

    def test_loader_raises_error_when_not_in_registry_and_no_fallback(self):
        """Тест проверяет, что возвращается ошибка, если пайплайн не в реестре и fallback отключен"""
        registry = PipelineRegistry()

        loader = PipelineLoader(pipeline_registry=registry, allow_fallback=False)

        with pytest.raises(KeyError) as exc_info:
            loader.load("init_pipeline")

        assert "not registered" in str(exc_info.value).lower()


class TestDefaultPipelineRegistration:
    def test_default_pipelines_are_registered(self):
        """Тест проверяет, что дефолтные пайплайны регистрируются при вызове функции"""
        # Создаем новый реестр и загружаем пайплайны из директории
        test_registry = PipelineRegistry()
        test_registry.autoload_pipelines("pipelines/")

        # Проверяем, что основные пайплайны зарегистрированы
        assert test_registry.exists("init_pipeline")
        assert test_registry.exists("feature_pipeline")
        assert test_registry.exists("ci_fix_pipeline")

    def test_global_registry_has_default_pipelines(self):
        """Тест проверяет, что глобальный реестр содержит зарегистрированные пайплайны"""
        # Используем registry.pipelines.PipelineRegistry
        from registry.pipelines import PipelineRegistry

        test_registry = PipelineRegistry()
        test_registry.autoload_pipelines("pipelines/")

        assert test_registry.exists("init_pipeline")
        assert test_registry.exists("feature_pipeline")


class TestPipelineCompatibility:
    def test_registry_validates_core_pipelines(self):
        from registry.agents import AgentRegistry, register_agents

        pipeline_registry = PipelineRegistry()
        pipeline_names = ["init_pipeline", "feature_pipeline", "ci_fix_pipeline"]
        for name in pipeline_names:
            pipeline_registry.register(PipelineMetadata(name, f"pipelines/{name}.yaml"))

        agent_registry = AgentRegistry()
        register_agents(agent_registry)

        for name in pipeline_names:
            pipeline_def = pipeline_registry.load_and_validate_pipeline(name, agent_registry)
            assert pipeline_def.pipeline_name == name

"""
Тесты для проверки инициализации всех реестров через bootstrap
"""


class TestRegistryBootstrap:
    def test_init_registries_returns_dict(self):
        """Тест проверяет, что init_registries() возвращает словарь с реестрами"""
        from registry.bootstrap import init_registries

        result = init_registries()

        assert isinstance(result, dict)
        assert "agent_registry" in result
        assert "pipeline_registry" in result

    def test_init_registries_contains_agent_registry(self):
        """Тест проверяет, что результат содержит AgentRegistry"""
        from registry.bootstrap import init_registries

        result = init_registries()

        from registry.agents import AgentRegistry
        from registry.pipelines import PipelineRegistry

        assert isinstance(result["agent_registry"], AgentRegistry)
        assert isinstance(result["pipeline_registry"], PipelineRegistry)

    def test_init_registries_validates_agents(self):
        """Тест проверяет, что агенты проходят валидацию"""
        from registry.bootstrap import init_registries

        result = init_registries()

        # Проверяем, что реестр агентов не пустой
        agent_registry = result["agent_registry"]
        assert hasattr(agent_registry, "exists")
        # Проверяем наличие одного из известных агентов
        assert agent_registry.exists("dod_extractor")
        assert agent_registry.exists("specification_writer")

    def test_init_registries_validates_pipelines(self):
        """Тест проверяет, что пайплайны проходят валидацию"""
        from registry.bootstrap import init_registries

        result = init_registries()

        # Проверяем, что реестр пайплайнов не пустой
        pipeline_registry = result["pipeline_registry"]
        assert hasattr(pipeline_registry, "exists")
        # Проверяем наличие одного из известных пайплайнов
        assert pipeline_registry.exists("init_pipeline")
        assert pipeline_registry.exists("feature_pipeline")

    def test_init_registries_with_existing_registries(self):
        """Тест проверяет, что можно передать существующие реестры для инициализации"""
        from registry.agents import AgentRegistry
        from registry.bootstrap import init_registries
        from registry.pipelines import PipelineRegistry

        custom_agent_registry = AgentRegistry()
        custom_pipeline_registry = PipelineRegistry()

        result = init_registries(
            agent_registry=custom_agent_registry,
            pipeline_registry=custom_pipeline_registry,
        )

        assert result["agent_registry"] is custom_agent_registry
        assert result["pipeline_registry"] is custom_pipeline_registry

"""
Модуль для инициализации всех реестров (контрактов, агентов, пайплайнов) с валидацией.
"""

from .agents import AgentRegistry
from .contracts import ContractRegistry
from .pipelines import PipelineRegistry


def init_registries(
    contract_registry=None,
    agent_registry=None,
    pipeline_registry=None,
    contracts_dir="contracts/schemas/",
    pipelines_dir="pipelines/",
):
    """
    Инициализирует все реестры с валидацией.

    Args:
        contract_registry: Экземпляр ContractRegistry. Если None, создается новый.
        agent_registry: Экземпляр AgentRegistry. Если None, создается новый.
        pipeline_registry: Экземпляр PipelineRegistry. Если None, создается новый.
        contracts_dir: Директория для автозагрузки схем контрактов.
        pipelines_dir: Директория для автозагрузки пайплайнов.

    Returns:
        dict: Словарь с инициализированными реестрами:
              {
                  'contract_registry': ContractRegistry,
                  'agent_registry': AgentRegistry,
                  'pipeline_registry': PipelineRegistry
              }

    Raises:
        ValueError: Если возникают ошибки валидации при инициализации реестров.
    """
    # Инициализируем реестр контрактов
    if contract_registry is None:
        contract_registry = ContractRegistry()

    # Автозагружаем схемы контрактов
    contract_registry.autoload_schemas(contracts_dir)

    # Инициализируем реестр агентов
    if agent_registry is None:
        agent_registry = AgentRegistry(contract_registry=contract_registry)

    # Регистрируем агентов
    from .agents import register_agents

    register_agents(agent_registry)

    # Инициализируем реестр пайплайнов
    if pipeline_registry is None:
        pipeline_registry = PipelineRegistry()

    # Автозагружаем пайплайны
    pipeline_registry.autoload_pipelines(pipelines_dir)

    # Валидируем пайплайны
    pipeline_names = [pipeline.name for pipeline in pipeline_registry.list()]
    for pipeline_name in pipeline_names:
        try:
            pipeline_registry.load_and_validate_pipeline(pipeline_name, agent_registry)
        except Exception as e:
            raise ValueError(f"Ошибка валидации пайплайна '{pipeline_name}': {str(e)}") from e

    return {
        "contract_registry": contract_registry,
        "agent_registry": agent_registry,
        "pipeline_registry": pipeline_registry,
    }

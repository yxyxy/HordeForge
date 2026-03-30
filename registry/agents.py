from dataclasses import dataclass
from typing import TYPE_CHECKING

from .agent_category import AgentCategory

if TYPE_CHECKING:
    from agents.base import BaseAgent


@dataclass(frozen=True)
class AgentMetadata:
    """
    Класс для хранения метаданных агентов в реестре.
    """

    name: str
    agent_class: type["BaseAgent"]  # Теперь хранит тип, а не строку
    description: str | None = None
    input_contract: str | None = None
    output_contract: str | None = None
    version: str | None = None
    author: str | None = None
    category: AgentCategory | str | None = None  # Обновляем тип для поддержки enum


class AgentRegistry:
    """
    Класс для управления реестром агентов с методами регистрации,
    получения, списка и проверки существования.
    """

    def __init__(self, contract_registry=None):
        self._agents: dict[str, AgentMetadata] = {}
        self.contract_registry = contract_registry

    def register(self, metadata: AgentMetadata) -> None:
        """
        Регистрирует новый агент в реестре.
        Если указан contract_registry, проверяет существование input_contract и output_contract.
        """
        # Проверяем, что агент с таким именем не зарегистрирован
        if metadata.name in self._agents:
            raise ValueError(f"Agent '{metadata.name}' уже зарегистрирован в реестре")

        # Проверяем, что agent_class является подклассом BaseAgent
        from agents.base import BaseAgent

        if not isinstance(metadata.agent_class, type) or not issubclass(
            metadata.agent_class, BaseAgent
        ):
            raise TypeError(
                f"agent_class должен быть подклассом BaseAgent, получен: {type(metadata.agent_class)}"
            )

        if self.contract_registry:
            if metadata.input_contract and not self.contract_registry.exists(
                metadata.input_contract
            ):
                raise ValueError(
                    f"Input contract '{metadata.input_contract}' не найден в реестре контрактов"
                )

            if metadata.output_contract and not self.contract_registry.exists(
                metadata.output_contract
            ):
                raise ValueError(
                    f"Output contract '{metadata.output_contract}' не найден в реестре контрактов"
                )

        self._agents[metadata.name] = metadata

    def get(self, name: str) -> AgentMetadata | None:
        """
        Возвращает метаданные агента по имени.
        """
        return self._agents.get(name)

    def list(self) -> list[AgentMetadata]:
        """
        Возвращает список всех зарегистрированных агентов.
        """
        return list(self._agents.values())

    def exists(self, name: str) -> bool:
        """
        Проверяет существование агента по имени.
        """
        return name in self._agents


def register_agents(agent_registry: AgentRegistry) -> None:
    """
    Регистрирует основные MVP агенты в AgentRegistry.
    """
    # Импортируем классы агентов
    from agents.architecture_evaluator import ArchitectureEvaluator
    from agents.architecture_planner import ArchitecturePlanner
    from agents.bdd_generator import BDDGenerator
    from agents.ci_failure_analyzer import CiFailureAnalyzer
    from agents.ci_incident_handoff import CiIncidentHandoff
    from agents.ci_monitor_agent.agent import CIMonitorAgent
    from agents.code_generator import CodeGenerator
    from agents.dependency_checker_agent.agent import DependencyCheckerAgent
    from agents.dod_extractor import DodExtractor
    from agents.fix_agent import FixAgent
    from agents.issue_closer import IssueCloser
    from agents.issue_pipeline_dispatcher import IssuePipelineDispatcher
    from agents.issue_scanner import IssueScanner
    from agents.memory_agent import MemoryAgent
    from agents.pipeline_initializer import PipelineInitializer
    from agents.pr_merge_agent import PrMergeAgent
    from agents.rag_initializer import RagInitializer
    from agents.repo_connector import RepoConnector
    from agents.review_agent import ReviewAgent
    from agents.specification_writer import SpecificationWriter
    from agents.task_decomposer import TaskDecomposer
    from agents.test_analyzer import TestAnalyzer
    from agents.test_generator import TestGenerator
    from agents.test_runner import TestRunner

    agents = [
        AgentMetadata(
            name="dod_extractor",
            agent_class=DodExtractor,
            description="Извлекает DoD (Definition of Done) из задач",
            input_contract="context.dod.v1",
            output_contract="context.dod.v1",
        ),
        AgentMetadata(
            name="architecture_planner",
            agent_class=ArchitecturePlanner,
            description="Планирует архитектуру решения",
            input_contract="context.dod.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="specification_writer",
            agent_class=SpecificationWriter,
            description="Генерирует техническую спецификацию",
            input_contract="context.dod.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="task_decomposer",
            agent_class=TaskDecomposer,
            description="Декомпозирует задачи на подзадачи",
            input_contract="context.dod.v1",
            output_contract="context.dod.v1",
        ),
        AgentMetadata(
            name="bdd_generator",
            agent_class=BDDGenerator,
            description="Генерирует BDD сценарии",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="test_generator",
            agent_class=TestGenerator,
            description="Генерирует тесты",
            input_contract="context.spec.v1",
            output_contract="context.tests.v1",
        ),
        AgentMetadata(
            name="code_generator",
            agent_class=CodeGenerator,
            description="Генерирует код",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="fix_agent",
            agent_class=FixAgent,
            description="Исправляет ошибки в коде",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="review_agent",
            agent_class=ReviewAgent,
            description="Проверяет код на соответствие стандартам",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="ci_failure_analyzer",
            agent_class=CiFailureAnalyzer,
            description="Анализирует ошибки CI",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="ci_incident_handoff",
            agent_class=CiIncidentHandoff,
            description="Creates CI handoff issue with agent:ready label",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="test_runner",
            agent_class=TestRunner,
            description="Запускает тесты",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="pr_merge_agent",
            agent_class=PrMergeAgent,
            description="Объединяет pull request",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="issue_closer",
            agent_class=IssueCloser,
            description="Закрывает задачи",
            input_contract="context.spec.v1",
            output_contract="context.spec.v1",
        ),
        AgentMetadata(
            name="architecture_evaluator",
            agent_class=ArchitectureEvaluator,
            description="Оценивает архитектуру",
            input_contract=None,
            output_contract=None,
        ),
        AgentMetadata(
            name="test_analyzer",
            agent_class=TestAnalyzer,
            description="Анализирует тесты",
            input_contract=None,
            output_contract=None,
        ),
        # Новые агенты (ревизия) - без валидации контрактов
        AgentMetadata(
            name="repo_connector",
            agent_class=RepoConnector,
            description="Подключается к репозиторию и получает метаданные",
            input_contract=None,
            output_contract=None,
            category="infrastructure",
        ),
        AgentMetadata(
            name="rag_initializer",
            agent_class=RagInitializer,
            description="Создаёт RAG индекс из документации",
            input_contract=None,
            output_contract=None,
            category="infrastructure",
        ),
        AgentMetadata(
            name="memory_agent",
            agent_class=MemoryAgent,
            description="Создаёт начальное состояние памяти для downstream агентов",
            input_contract=None,
            output_contract=None,
            category="infrastructure",
        ),
        AgentMetadata(
            name="pipeline_initializer",
            agent_class=PipelineInitializer,
            description="Инициализирует и конфигурирует pipeline на основе типа задачи",
            input_contract=None,
            output_contract=None,
            category="orchestration",
        ),
        AgentMetadata(
            name="issue_scanner",
            agent_class=IssueScanner,
            description="Сканирует и классифицирует GitHub issues",
            input_contract=None,
            output_contract=None,
            category="scanning",
        ),
        AgentMetadata(
            name="issue_pipeline_dispatcher",
            agent_class=IssuePipelineDispatcher,
            description="Запускает downstream pipeline для agent:ready issues",
            input_contract=None,
            output_contract=None,
            category="orchestration",
        ),
        AgentMetadata(
            name="ci_monitor_agent",
            agent_class=CIMonitorAgent,
            description="Мониторит CI/CD процессы и реагирует на изменения статусов",
            input_contract=None,
            output_contract=None,
            category="monitoring",
        ),
        AgentMetadata(
            name="dependency_checker_agent",
            agent_class=DependencyCheckerAgent,
            description="Проверяет зависимости проекта на уязвимости и устаревшие компоненты",
            input_contract=None,
            output_contract=None,
            category="security",
        ),
    ]

    for agent in agents:
        agent_registry.register(agent)

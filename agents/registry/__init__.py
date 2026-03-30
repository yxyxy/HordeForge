from __future__ import annotations

from typing import Any


class AgentRegistry:
    def __init__(self) -> None:
        self._mapping: dict[str, type[Any]] = {}

    def register(self, agent_name: str, agent_class: type[Any]) -> None:
        if not agent_name or not isinstance(agent_name, str):
            raise ValueError("agent_name must be a non-empty string")
        if agent_name in self._mapping:
            raise ValueError(f"Agent '{agent_name}' is already registered")
        self._mapping[agent_name] = agent_class

    def get(self, agent_name: str) -> type[Any]:
        if agent_name not in self._mapping:
            raise KeyError(f"Agent '{agent_name}' is not registered")
        return self._mapping[agent_name]

    def has(self, agent_name: str) -> bool:
        return agent_name in self._mapping

    def create(self, agent_name: str) -> Any:
        agent_class = self.get(agent_name)
        return agent_class()

    def items(self) -> dict[str, type[Any]]:
        return dict(self._mapping)


AGENT_REGISTRY = AgentRegistry()


def register_default_agents(registry: AgentRegistry | None = None) -> AgentRegistry:
    target = registry or AGENT_REGISTRY
    if target.items():
        return target

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

    default_mapping: dict[str, type[Any]] = {
        "architecture_evaluator": ArchitectureEvaluator,
        "architecture_planner": ArchitecturePlanner,
        "bdd_generator": BDDGenerator,
        "ci_failure_analyzer": CiFailureAnalyzer,
        "ci_incident_handoff": CiIncidentHandoff,
        "code_generator": CodeGenerator,
        "dod_extractor": DodExtractor,
        "fix_agent": FixAgent,
        "issue_closer": IssueCloser,
        "issue_pipeline_dispatcher": IssuePipelineDispatcher,
        "issue_scanner": IssueScanner,
        "memory_agent": MemoryAgent,
        "pipeline_initializer": PipelineInitializer,
        "pr_merge_agent": PrMergeAgent,
        "rag_initializer": RagInitializer,
        "repo_connector": RepoConnector,
        "review_agent": ReviewAgent,
        "specification_writer": SpecificationWriter,
        "ci_monitor_agent": CIMonitorAgent,
        "dependency_checker_agent": DependencyCheckerAgent,
        "task_decomposer": TaskDecomposer,
        "test_analyzer": TestAnalyzer,
        "test_generator": TestGenerator,
        "test_runner": TestRunner,
    }

    for name, agent_class in default_mapping.items():
        target.register(name, agent_class)
    return target


register_default_agents()


class PipelineRegistry:
    """Реестр для хранения и управления пайплайнами."""

    def __init__(self) -> None:
        self._mapping: dict[str, Any] = {}

    def register(self, pipeline_name: str, pipeline: Any) -> None:
        """Регистрирует пайплайн в реестре."""
        if not pipeline_name or not isinstance(pipeline_name, str):
            raise ValueError("pipeline_name must be a non-empty string")
        if pipeline_name in self._mapping:
            raise ValueError(f"Pipeline '{pipeline_name}' is already registered")
        self._mapping[pipeline_name] = pipeline

    def get(self, pipeline_name: str) -> Any:
        """Получает пайплайн по имени."""
        if pipeline_name not in self._mapping:
            raise KeyError(f"Pipeline '{pipeline_name}' is not registered")
        return self._mapping[pipeline_name]

    def has(self, pipeline_name: str) -> bool:
        """Проверяет, зарегистрирован ли пайплайн."""
        return pipeline_name in self._mapping

    def items(self) -> dict[str, Any]:
        """Возвращает все зарегистрированные пайплайны."""
        return dict(self._mapping)

    def list_all(self) -> list[str]:
        """Возвращает список имен всех зарегистрированных пайплайнов."""
        return list(self._mapping.keys())


PIPELINE_REGISTRY = PipelineRegistry()


def register_default_pipelines(registry: PipelineRegistry | None = None) -> PipelineRegistry:
    """Регистрирует дефолтные пайплайны из папки pipelines/."""
    target = registry or PIPELINE_REGISTRY
    if target.list_all():
        return target

    # Импортируем здесь, чтобы избежать циклических зависимостей
    from orchestrator.loader import PipelineLoader

    # Загружаем все пайплайны из папки
    loader = PipelineLoader(pipelines_dir="pipelines")

    default_pipeline_names = [
        "init_pipeline",
        "feature_pipeline",
        "ci_fix_pipeline",
        "issue_scanner_pipeline",
        "ci_monitoring_pipeline",
        "dependency_check_pipeline",
    ]

    for pipeline_name in default_pipeline_names:
        try:
            pipeline = loader.load(pipeline_name)
            target.register(pipeline_name, pipeline)
        except FileNotFoundError:
            # Пропускаем пайплайны, которые не найдены
            pass

    return target


# Инициализируем глобальный реестр пайплайнов
register_default_pipelines()

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
    from agents.bdd_generator import BddGenerator
    from agents.ci_failure_analyzer import CiFailureAnalyzer
    from agents.code_generator import CodeGenerator
    from agents.dod_extractor import DodExtractor
    from agents.fix_agent import FixAgent
    from agents.issue_closer import IssueCloser
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
        "bdd_generator": BddGenerator,
        "ci_failure_analyzer": CiFailureAnalyzer,
        "code_generator": CodeGenerator,
        "dod_extractor": DodExtractor,
        "fix_agent": FixAgent,
        "issue_closer": IssueCloser,
        "memory_agent": MemoryAgent,
        "pipeline_initializer": PipelineInitializer,
        "pr_merge_agent": PrMergeAgent,
        "rag_initializer": RagInitializer,
        "repo_connector": RepoConnector,
        "review_agent": ReviewAgent,
        "specification_writer": SpecificationWriter,
        "task_decomposer": TaskDecomposer,
        "test_analyzer": TestAnalyzer,
        "test_generator": TestGenerator,
        "test_runner": TestRunner,
    }

    for name, agent_class in default_mapping.items():
        target.register(name, agent_class)
    return target


register_default_agents()

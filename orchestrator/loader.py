from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class StepDefinition:
    name: str
    agent: str
    description: str | None = None
    on_failure: str = "stop_pipeline"
    depends_on: list[str] = field(default_factory=list)
    depends_on_explicit: bool = False
    resource_locks: list[str] = field(default_factory=list)
    input_mapping: dict[str, Any] = field(default_factory=dict)
    output_mapping: Any = None
    retry_limit: int | None = None
    timeout_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["input"] = data.pop("input_mapping")
        data["output"] = data.pop("output_mapping")
        return data


@dataclass(slots=True)
class LoopDefinition:
    condition: str
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineDefinition:
    pipeline_name: str
    description: str = ""
    steps: list[StepDefinition] = field(default_factory=list)
    loops: list[LoopDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "loops": [loop.to_dict() for loop in self.loops],
        }


class PipelineLoader:
    def __init__(self, pipelines_dir: str = "pipelines"):
        self.pipelines_dir = Path(pipelines_dir)

    def load(self, pipeline_name_or_path: str) -> PipelineDefinition:
        path = self._resolve_pipeline_path(pipeline_name_or_path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        return self._parse_pipeline(payload, path)

    def _resolve_pipeline_path(self, pipeline_name_or_path: str) -> Path:
        path = Path(pipeline_name_or_path)
        if path.suffix == ".yaml":
            return path
        return self.pipelines_dir / f"{pipeline_name_or_path}.yaml"

    @staticmethod
    def _parse_pipeline(payload: dict[str, Any], path: Path) -> PipelineDefinition:
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid pipeline format in {path}: payload must be an object")

        pipeline_name = payload.get("pipeline_name")
        steps_raw = payload.get("steps")
        if not isinstance(pipeline_name, str) or not pipeline_name.strip():
            raise ValueError(f"Invalid pipeline format in {path}: missing pipeline_name")
        if not isinstance(steps_raw, list):
            raise ValueError(f"Invalid pipeline format in {path}: missing steps[]")

        steps: list[StepDefinition] = []
        for index, step in enumerate(steps_raw, start=1):
            if not isinstance(step, dict):
                raise ValueError(
                    f"Invalid pipeline format in {path}: step #{index} must be an object"
                )
            name = step.get("name")
            agent = step.get("agent")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Invalid pipeline format in {path}: step #{index} missing name")
            if not isinstance(agent, str) or not agent.strip():
                raise ValueError(f"Invalid pipeline format in {path}: step '{name}' missing agent")
            timeout = step.get("timeout_seconds")
            timeout_value = float(timeout) if timeout is not None else None
            depends_on_explicit = "depends_on" in step
            depends_on_raw = step.get("depends_on", [])
            if depends_on_raw is None:
                depends_on_raw = []
            if not isinstance(depends_on_raw, list) or not all(
                isinstance(item, str) and item.strip() for item in depends_on_raw
            ):
                raise ValueError(
                    f"Invalid pipeline format in {path}: step '{name}' depends_on must be list[str]"
                )
            resource_locks_raw = step.get("resource_locks", [])
            if resource_locks_raw is None:
                resource_locks_raw = []
            if not isinstance(resource_locks_raw, list) or not all(
                isinstance(item, str) and item.strip() for item in resource_locks_raw
            ):
                raise ValueError(
                    f"Invalid pipeline format in {path}: step '{name}' resource_locks must be list[str]"
                )

            steps.append(
                StepDefinition(
                    name=name,
                    agent=agent,
                    description=step.get("description"),
                    on_failure=step.get("on_failure", "stop_pipeline"),
                    depends_on=list(depends_on_raw),
                    depends_on_explicit=depends_on_explicit,
                    resource_locks=list(resource_locks_raw),
                    input_mapping=step.get("input", {}),
                    output_mapping=step.get("output"),
                    retry_limit=step.get("retry_limit"),
                    timeout_seconds=timeout_value,
                )
            )

        loops_raw = payload.get("loops", [])
        loops: list[LoopDefinition] = []
        if loops_raw is not None:
            if not isinstance(loops_raw, list):
                raise ValueError(f"Invalid pipeline format in {path}: loops must be a list")
            for loop in loops_raw:
                if not isinstance(loop, dict):
                    raise ValueError(
                        f"Invalid pipeline format in {path}: loop item must be an object"
                    )
                condition = loop.get("condition")
                loop_steps = loop.get("steps")
                if not isinstance(condition, str) or not condition.strip():
                    raise ValueError(f"Invalid pipeline format in {path}: loop missing condition")
                if not isinstance(loop_steps, list) or not all(
                    isinstance(item, str) and item.strip() for item in loop_steps
                ):
                    raise ValueError(f"Invalid pipeline format in {path}: loop missing steps[]")
                loops.append(LoopDefinition(condition=condition, steps=loop_steps))

        return PipelineDefinition(
            pipeline_name=pipeline_name,
            description=payload.get("description", ""),
            steps=steps,
            loops=loops,
        )

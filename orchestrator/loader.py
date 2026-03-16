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
    triggers: list[str] = field(default_factory=list)
    logging: dict[str, Any] = field(default_factory=dict)
    steps: list[StepDefinition] = field(default_factory=list)
    loops: list[LoopDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "description": self.description,
            "triggers": self.triggers,
            "logging": self.logging,
            "steps": [step.to_dict() for step in self.steps],
            "loops": [loop.to_dict() for loop in self.loops],
        }


class PipelineLoader:
    def __init__(
        self,
        pipelines_dir: str = "pipelines",
        pipeline_registry: Any | None = None,
        allow_fallback: bool = True,
    ):
        self.pipelines_dir = Path(pipelines_dir)
        self.pipeline_registry = pipeline_registry
        self.allow_fallback = allow_fallback

    def load(self, pipeline_name_or_path: str) -> PipelineDefinition:
        # Пробуем сначала загрузить из реестра
        if self.pipeline_registry is not None:
            # Если передан registry, пытаемся загрузить из него
            # Проверяем, что это не полный путь к файлу
            path = Path(pipeline_name_or_path)
            if not path.suffix == ".yaml" and not path.is_absolute():
                # Это имя пайплайна, пробуем получить из него
                # Проверяем, есть ли уже загруженное определение
                if hasattr(
                    self.pipeline_registry, "has_pipeline_definition"
                ) and self.pipeline_registry.has_pipeline_definition(pipeline_name_or_path):
                    return self.pipeline_registry.get_pipeline_definition(pipeline_name_or_path)

                # Также проверяем наличие в реестре (метаданные)
                if hasattr(self.pipeline_registry, "exists") and self.pipeline_registry.exists(
                    pipeline_name_or_path
                ):
                    # Получаем метаданные и загружаем пайплайн
                    metadata = self.pipeline_registry.get_metadata(pipeline_name_or_path)
                    if metadata:
                        # Загружаем из файла, указанного в метаданных
                        with open(metadata.path, encoding="utf-8") as handle:
                            payload = yaml.safe_load(handle) or {}
                        pipeline_def = self._parse_pipeline(payload, Path(metadata.path))

                        # Регистрируем загруженное определение в реестре для последующего использования
                        self.pipeline_registry.register_pipeline_definition(
                            pipeline_name_or_path, pipeline_def
                        )
                        return pipeline_def

                # Если не в реестре и fallback запрещен - ошибка
                if not self.allow_fallback:
                    raise KeyError(
                        f"Pipeline '{pipeline_name_or_path}' is not registered "
                        "and fallback to file system is disabled"
                    )

        # Fallback на загрузку из файла
        path = self._resolve_pipeline_path(pipeline_name_or_path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        pipeline_def = self._parse_pipeline(payload, path)

        # Если у нас есть реестр, регистрируем загруженное определение для последующего использования
        if self.pipeline_registry is not None and hasattr(
            self.pipeline_registry, "register_pipeline_definition"
        ):
            # Проверяем, что путь не является абсолютным файлом, а представляет имя пайплайна
            if not Path(pipeline_name_or_path).is_absolute() or path.suffix == ".yaml":
                # Извлекаем имя пайплайна из пути
                pipeline_name = path.stem
                self.pipeline_registry.register_pipeline_definition(pipeline_name, pipeline_def)

        return pipeline_def

    def _resolve_pipeline_path(self, pipeline_name_or_path: str) -> Path:
        path = Path(pipeline_name_or_path)
        if path.suffix == ".yaml":
            return path
        return self.pipelines_dir / f"{pipeline_name_or_path}.yaml"

    @staticmethod
    def _ensure_list_of_strings(
        value: Any,
        field_name: str,
        *,
        allow_scalar: bool = False,
    ) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str) and allow_scalar:
            value = [value]
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"Invalid pipeline format in {field_name}: expected list[str]")
        return [item.strip() for item in value]

    @staticmethod
    def _ensure_dict(value: Any, field_name: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"Invalid pipeline format in {field_name}: expected object")
        return value

    @classmethod
    def _parse_loop_item(cls, loop: Any, context: str) -> LoopDefinition:
        if not isinstance(loop, dict):
            raise ValueError(f"Invalid pipeline format in {context}: loop must be an object")
        condition = loop.get("condition")
        if not isinstance(condition, str) or not condition.strip():
            raise ValueError(f"Invalid pipeline format in {context}: loop missing condition")
        steps = cls._ensure_list_of_strings(loop.get("steps"), f"{context}.steps")
        if not steps:
            raise ValueError(f"Invalid pipeline format in {context}: loop missing steps[]")
        return LoopDefinition(condition=condition, steps=steps)

    @classmethod
    def _parse_loops_container(cls, raw: Any, context: str) -> list[LoopDefinition]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            items = [raw]
        elif isinstance(raw, list):
            items = raw
        else:
            raise ValueError(f"Invalid pipeline format in {context}: loops must be a list")

        loops: list[LoopDefinition] = []
        for index, item in enumerate(items, start=1):
            loops.append(cls._parse_loop_item(item, f"{context}[{index}]"))
        return loops

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

        triggers = PipelineLoader._ensure_list_of_strings(
            payload.get("triggers"),
            f"{path}: triggers",
            allow_scalar=True,
        )
        logging_config = PipelineLoader._ensure_dict(
            payload.get("logging"),
            f"{path}: logging",
        )

        steps: list[StepDefinition] = []
        loops: list[LoopDefinition] = []
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
            depends_on_raw = step.get("depends_on")
            depends_on = PipelineLoader._ensure_list_of_strings(
                depends_on_raw,
                f"{path}: step '{name}' depends_on",
            )
            resource_locks_raw = step.get("resource_locks")
            resource_locks = PipelineLoader._ensure_list_of_strings(
                resource_locks_raw,
                f"{path}: step '{name}' resource_locks",
            )
            input_mapping = step.get("input", {})
            if input_mapping is None:
                input_mapping = {}
            if not isinstance(input_mapping, dict):
                raise ValueError(
                    f"Invalid pipeline format in {path}: step '{name}' input must be an object"
                )

            steps.append(
                StepDefinition(
                    name=name,
                    agent=agent,
                    description=step.get("description"),
                    on_failure=step.get("on_failure", "stop_pipeline"),
                    depends_on=list(depends_on),
                    depends_on_explicit=depends_on_explicit,
                    resource_locks=list(resource_locks),
                    input_mapping=input_mapping,
                    output_mapping=step.get("output"),
                    retry_limit=step.get("retry_limit"),
                    timeout_seconds=timeout_value,
                )
            )

            step_loops = PipelineLoader._parse_loops_container(
                step.get("loops"),
                f"{path}: step '{name}' loops",
            )
            loops.extend(step_loops)

        top_level_loops = PipelineLoader._parse_loops_container(
            payload.get("loops"),
            f"{path}: loops",
        )
        loops.extend(top_level_loops)

        step_names = {step.name for step in steps}
        for loop in loops:
            for step_name in loop.steps:
                if step_name not in step_names:
                    raise ValueError(
                        f"Invalid pipeline format in {path}: loop references unknown step '{step_name}'"
                    )

        return PipelineDefinition(
            pipeline_name=pipeline_name,
            description=payload.get("description", ""),
            triggers=triggers,
            logging=logging_config,
            steps=steps,
            loops=loops,
        )

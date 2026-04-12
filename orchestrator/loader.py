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
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["input"] = data.pop("input_mapping")
        data["output"] = data.pop("output_mapping")
        return data


@dataclass(slots=True)
class LoopDefinition:
    condition: str
    steps: list[str] = field(default_factory=list)
    no_progress_threshold: int | None = None
    progress_signature_path: str | None = None

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
        # РџСЂРѕР±СѓРµРј СЃРЅР°С‡Р°Р»Р° Р·Р°РіСЂСѓР·РёС‚СЊ РёР· СЂРµРµСЃС‚СЂР°
        if self.pipeline_registry is not None:
            # Р•СЃР»Рё РїРµСЂРµРґР°РЅ registry, РїС‹С‚Р°РµРјСЃСЏ Р·Р°РіСЂСѓР·РёС‚СЊ РёР· РЅРµРіРѕ
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ СЌС‚Рѕ РЅРµ РїРѕР»РЅС‹Р№ РїСѓС‚СЊ Рє С„Р°Р№Р»Сѓ
            path = Path(pipeline_name_or_path)
            if not path.suffix == ".yaml" and not path.is_absolute():
                # Р­С‚Рѕ РёРјСЏ РїР°Р№РїР»Р°Р№РЅР°, РїСЂРѕР±СѓРµРј РїРѕР»СѓС‡РёС‚СЊ РёР· РЅРµРіРѕ
                # РџСЂРѕРІРµСЂСЏРµРј, РµСЃС‚СЊ Р»Рё СѓР¶Рµ Р·Р°РіСЂСѓР¶РµРЅРЅРѕРµ РѕРїСЂРµРґРµР»РµРЅРёРµ
                if hasattr(
                    self.pipeline_registry, "has_pipeline_definition"
                ) and self.pipeline_registry.has_pipeline_definition(pipeline_name_or_path):
                    return self.pipeline_registry.get_pipeline_definition(pipeline_name_or_path)

                # РўР°РєР¶Рµ РїСЂРѕРІРµСЂСЏРµРј РЅР°Р»РёС‡РёРµ РІ СЂРµРµСЃС‚СЂРµ (РјРµС‚Р°РґР°РЅРЅС‹Рµ)
                if hasattr(self.pipeline_registry, "exists") and self.pipeline_registry.exists(
                    pipeline_name_or_path
                ):
                    # РџРѕР»СѓС‡Р°РµРј РјРµС‚Р°РґР°РЅРЅС‹Рµ Рё Р·Р°РіСЂСѓР¶Р°РµРј РїР°Р№РїР»Р°Р№РЅ
                    metadata = self.pipeline_registry.get_metadata(pipeline_name_or_path)
                    if metadata:
                        # Р—Р°РіСЂСѓР¶Р°РµРј РёР· С„Р°Р№Р»Р°, СѓРєР°Р·Р°РЅРЅРѕРіРѕ РІ РјРµС‚Р°РґР°РЅРЅС‹С…
                        with open(metadata.path, encoding="utf-8") as handle:
                            payload = yaml.safe_load(handle) or {}
                        pipeline_def = self._parse_pipeline(payload, Path(metadata.path))

                        # Р РµРіРёСЃС‚СЂРёСЂСѓРµРј Р·Р°РіСЂСѓР¶РµРЅРЅРѕРµ РѕРїСЂРµРґРµР»РµРЅРёРµ РІ СЂРµРµСЃС‚СЂРµ РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµРіРѕ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ
                        self.pipeline_registry.register_pipeline_definition(
                            pipeline_name_or_path, pipeline_def
                        )
                        return pipeline_def

                # Р•СЃР»Рё РЅРµ РІ СЂРµРµСЃС‚СЂРµ Рё fallback Р·Р°РїСЂРµС‰РµРЅ - РѕС€РёР±РєР°
                if not self.allow_fallback:
                    raise KeyError(
                        f"Pipeline '{pipeline_name_or_path}' is not registered "
                        "and fallback to file system is disabled"
                    )

        # Fallback РЅР° Р·Р°РіСЂСѓР·РєСѓ РёР· С„Р°Р№Р»Р°
        path = self._resolve_pipeline_path(pipeline_name_or_path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

        pipeline_def = self._parse_pipeline(payload, path)

        # Р•СЃР»Рё Сѓ РЅР°СЃ РµСЃС‚СЊ СЂРµРµСЃС‚СЂ, СЂРµРіРёСЃС‚СЂРёСЂСѓРµРј Р·Р°РіСЂСѓР¶РµРЅРЅРѕРµ РѕРїСЂРµРґРµР»РµРЅРёРµ РґР»СЏ РїРѕСЃР»РµРґСѓСЋС‰РµРіРѕ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ
        if self.pipeline_registry is not None and hasattr(
            self.pipeline_registry, "register_pipeline_definition"
        ):
            # РџСЂРѕРІРµСЂСЏРµРј, С‡С‚Рѕ РїСѓС‚СЊ РЅРµ СЏРІР»СЏРµС‚СЃСЏ Р°Р±СЃРѕР»СЋС‚РЅС‹Рј С„Р°Р№Р»РѕРј, Р° РїСЂРµРґСЃС‚Р°РІР»СЏРµС‚ РёРјСЏ РїР°Р№РїР»Р°Р№РЅР°
            if not Path(pipeline_name_or_path).is_absolute() or path.suffix == ".yaml":
                # РР·РІР»РµРєР°РµРј РёРјСЏ РїР°Р№РїР»Р°Р№РЅР° РёР· РїСѓС‚Рё
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
        no_progress_threshold_raw = loop.get("no_progress_threshold")
        no_progress_threshold: int | None = None
        if no_progress_threshold_raw is not None:
            try:
                no_progress_threshold = int(no_progress_threshold_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid pipeline format in {context}: no_progress_threshold must be int"
                ) from exc
            if no_progress_threshold <= 0:
                raise ValueError(
                    f"Invalid pipeline format in {context}: no_progress_threshold must be > 0"
                )

        signature_path_raw = loop.get("progress_signature_path")
        progress_signature_path: str | None = None
        if signature_path_raw is not None:
            if not isinstance(signature_path_raw, str) or not signature_path_raw.strip():
                raise ValueError(
                    f"Invalid pipeline format in {context}: progress_signature_path must be string"
                )
            progress_signature_path = signature_path_raw.strip()

        return LoopDefinition(
            condition=condition,
            steps=steps,
            no_progress_threshold=no_progress_threshold,
            progress_signature_path=progress_signature_path,
        )

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
            condition = step.get("condition")
            if condition is not None and not isinstance(condition, str):
                raise ValueError(
                    f"Invalid pipeline format in {path}: step '{name}' condition must be a string"
                )
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
                    condition=condition.strip()
                    if isinstance(condition, str) and condition.strip()
                    else None,
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

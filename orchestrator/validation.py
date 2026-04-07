from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _matches_type(instance: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(instance, dict)
    if expected_type == "array":
        return isinstance(instance, list)
    if expected_type == "string":
        return isinstance(instance, str)
    if expected_type == "number":
        return _is_number(instance)
    if expected_type == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected_type == "boolean":
        return isinstance(instance, bool)
    if expected_type == "null":
        return instance is None
    return True


def _validate_against_schema(
    instance: Any,
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = [expected_type] if isinstance(expected_type, str) else list(expected_type)
        if expected_types and not any(_matches_type(instance, item) for item in expected_types):
            errors.append(
                f"{path}: expected type {expected_type!r}, got {type(instance).__name__!r}"
            )
            return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} is not in enum {schema['enum']!r}")
        return

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
        return

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}.{key}: required property is missing")

        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                _validate_against_schema(
                    value, properties[key], path=f"{path}.{key}", errors=errors
                )
                continue

            if additional is False:
                errors.append(f"{path}.{key}: additional property is not allowed")
            elif isinstance(additional, dict):
                _validate_against_schema(value, additional, path=f"{path}.{key}", errors=errors)
        return

    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < int(min_items):
            errors.append(f"{path}: expected at least {min_items} items, got {len(instance)}")

        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                _validate_against_schema(item, item_schema, path=f"{path}[{index}]", errors=errors)
        return

    if isinstance(instance, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < int(min_length):
            errors.append(f"{path}: expected minimum length {min_length}, got {len(instance)}")
        return

    if _is_number(instance):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: expected value >= {minimum}, got {instance}")
        if maximum is not None and instance > maximum:
            errors.append(f"{path}: expected value <= {maximum}, got {instance}")


class RuntimeSchemaValidator:
    AGENT_RESULT_SCHEMA_NAME = "agent_result.v1.schema.json"
    PIPELINE_STATE_SCHEMA_NAME = "pipeline_state.v1.schema.json"

    CONTEXT_SCHEMA_BY_ARTIFACT: dict[str, str] = {
        "dod": "context.dod.v1.schema.json",
        "spec": "context.spec.v1.schema.json",
        "tests": "context.tests.v1.schema.json",
        "code_patch": "context.code_patch.v1.schema.json",
    }

    def __init__(self, schema_dir: str = "contracts/schemas", strict_mode: bool = True) -> None:
        self.schema_dir = Path(schema_dir)
        self.strict_mode = strict_mode
        self._schemas = self._load_schemas()

    def _load_schemas(self) -> dict[str, dict[str, Any]]:
        if not self.schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {self.schema_dir}")

        schemas: dict[str, dict[str, Any]] = {}
        for file_path in self.schema_dir.glob("*.json"):
            with file_path.open("r", encoding="utf-8-sig") as handle:
                schemas[file_path.name] = json.load(handle)
        if self.AGENT_RESULT_SCHEMA_NAME not in schemas:
            raise FileNotFoundError(
                f"Required schema not found: {self.schema_dir / self.AGENT_RESULT_SCHEMA_NAME}"
            )
        return schemas

    def _validate_schema(
        self,
        schema_name: str,
        instance: Any,
        *,
        path: str,
    ) -> list[str]:
        schema = self._schemas.get(schema_name)
        if schema is None:
            return [f"{path}: schema is not configured ({schema_name})"]

        errors: list[str] = []
        _validate_against_schema(instance, schema, path=path, errors=errors)
        return errors

    def validate_step_output(self, step_name: str, output: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        errors.extend(
            self._validate_schema(
                self.AGENT_RESULT_SCHEMA_NAME,
                output,
                path=f"step[{step_name}]",
            )
        )

        artifacts = output.get("artifacts", [])
        if isinstance(artifacts, list):
            for index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    continue
                artifact_type = artifact.get("type")
                if not isinstance(artifact_type, str):
                    continue
                schema_name = self.CONTEXT_SCHEMA_BY_ARTIFACT.get(artifact_type)
                if not schema_name:
                    continue
                errors.extend(
                    self._validate_schema(
                        schema_name,
                        artifact.get("content"),
                        path=f"step[{step_name}].artifacts[{index}].content",
                    )
                )

        if errors and self.strict_mode:
            raise SchemaValidationError(f"Schema validation failed: {'; '.join(errors)}")
        return errors

    def validate_pipeline_state(self, payload: dict[str, Any]) -> list[str]:
        errors = self._validate_schema(
            self.PIPELINE_STATE_SCHEMA_NAME,
            payload,
            path="pipeline_state",
        )
        if errors and self.strict_mode:
            raise SchemaValidationError(f"Schema validation failed: {'; '.join(errors)}")
        return errors

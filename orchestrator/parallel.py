from __future__ import annotations

import re
from typing import Any

from orchestrator.loader import StepDefinition

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _extract_placeholders(value: Any) -> list[str]:
    if isinstance(value, str):
        return _PLACEHOLDER_PATTERN.findall(value)
    if isinstance(value, dict):
        refs: list[str] = []
        for item in value.values():
            refs.extend(_extract_placeholders(item))
        return refs
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(_extract_placeholders(item))
        return refs
    return []


def _root_key(path: str) -> str:
    return str(path).strip().split(".", maxsplit=1)[0]


def _extract_output_aliases(output_mapping: Any) -> set[str]:
    aliases: set[str] = set()
    for placeholder in _extract_placeholders(output_mapping):
        key = _root_key(placeholder)
        if key:
            aliases.add(key)
    return aliases


def build_step_dependency_graph(steps: list[StepDefinition]) -> dict[str, set[str]]:
    dependencies: dict[str, set[str]] = {step.name: set() for step in steps}
    producer_by_key: dict[str, str] = {}

    for step in steps:
        producer_by_key.setdefault(step.name, step.name)
        for alias in _extract_output_aliases(step.output_mapping):
            existing = producer_by_key.get(alias)
            if existing is not None and existing != step.name:
                raise ValueError(
                    f"Ambiguous output alias '{alias}' produced by both '{existing}' and '{step.name}'"
                )
            producer_by_key[alias] = step.name

    step_names = set(dependencies.keys())
    previous_step_name: str | None = None
    for step in steps:
        if previous_step_name is not None and not step.depends_on_explicit:
            dependencies[step.name].add(previous_step_name)

        for dep_name in step.depends_on:
            if dep_name not in step_names:
                raise ValueError(f"Step '{step.name}' depends on unknown step '{dep_name}'")
            if dep_name != step.name:
                dependencies[step.name].add(dep_name)

        for placeholder in _extract_placeholders(step.input_mapping):
            key = _root_key(placeholder)
            if not key:
                continue
            producer = producer_by_key.get(key)
            if producer is None or producer == step.name:
                continue
            dependencies[step.name].add(producer)
        previous_step_name = step.name

    return dependencies


def select_lock_aware_batch(ready_steps: list[StepDefinition]) -> list[StepDefinition]:
    selected: list[StepDefinition] = []
    held_locks: set[str] = set()
    for step in ready_steps:
        locks = {item for item in step.resource_locks if item}
        if locks.intersection(held_locks):
            continue
        selected.append(step)
        held_locks.update(locks)
    if selected:
        return selected
    return [ready_steps[0]] if ready_steps else []

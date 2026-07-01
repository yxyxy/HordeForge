from __future__ import annotations

import json
import logging
import re
from typing import Any

from hordeforge_utils import resolve_path
from orchestrator.loader import StepDefinition

logger = logging.getLogger(__name__)


def try_parse_json(value: str) -> Any:
    """Try to parse a string as JSON. Return original string if not valid JSON."""
    value = value.strip()
    if (value.startswith("{") and value.endswith("}")) or (
        value.startswith("[") and value.endswith("]")
    ):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
    return value


def apply_input_mapping(step: StepDefinition, context_state: dict[str, Any]) -> dict[str, Any]:
    """
    Apply input_mapping from step definition to context state.

    Handles Jinja2 template variables like {{key}}, {{key.subkey}}, {{key|default(value)}}
    Resolves them from context_state and builds step-specific payload.

    Args:
        step: Step definition with input_mapping
        context_state: Current execution context state

    Returns:
        Merged payload for the agent
    """
    try:
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError:
        return apply_input_mapping_simple(step, context_state)

    env = SandboxedEnvironment()

    # Start with context state as base
    payload = dict(context_state)

    # If no input_mapping, return full context
    if not step.input_mapping:
        return payload

    scalar_template_pattern = re.compile(r"^\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}$")

    def resolve_value(raw_value: Any) -> Any:
        if not isinstance(raw_value, str):
            return raw_value

        match = scalar_template_pattern.fullmatch(raw_value.strip())
        if match:
            resolved = resolve_path(context_state, match.group(1))
            if resolved is not None:
                return resolved

        try:
            template = env.from_string(raw_value)
            rendered = template.render(**context_state)
            return try_parse_json(rendered)
        except Exception as e:
            logger.debug("Jinja2 template resolution failed for %r: %s", raw_value, e)
            return raw_value

    # Apply each mapping from input_mapping
    for target_key, source_value in step.input_mapping.items():
        if isinstance(source_value, str):
            payload[target_key] = resolve_value(source_value)
        elif isinstance(source_value, dict):
            resolved_dict = {k: resolve_value(v) for k, v in source_value.items()}
            payload[target_key] = resolved_dict
        elif isinstance(source_value, list):
            payload[target_key] = [resolve_value(item) for item in source_value]
        else:
            payload[target_key] = source_value

    return payload


def apply_input_mapping_simple(
    step: StepDefinition, context_state: dict[str, Any]
) -> dict[str, Any]:
    """Fallback simple input_mapping without Jinja2."""
    # Start with context state as base
    payload = dict(context_state)

    # If no input_mapping, return full context
    if not step.input_mapping:
        return payload

    # Pattern to match template variables: {{key}} or {{key.subkey}}
    template_pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}")

    def resolve_template(template_str: str) -> Any:
        """Resolve a template string like {{key.subkey}} from context_state."""
        # Find all template variables in the string
        matches = template_pattern.findall(template_str)

        if not matches:
            # No template variables, return as-is
            return template_str

        # If entire string is a single template variable, resolve it directly
        if len(matches) == 1 and template_str.strip() == f"{{{{{matches[0]}}}}}":
            return resolve_path(context_state, matches[0])

        # Otherwise, replace each template variable in the string
        result = template_str
        for match in matches:
            value = resolve_path(context_state, match)
            if value is not None:
                # Replace the template with the resolved value
                result = result.replace(f"{{{{{match}}}}}", str(value))
            else:
                # Keep the template if not resolved
                pass
        return result

    # Apply each mapping from input_mapping
    for target_key, source_value in step.input_mapping.items():
        if isinstance(source_value, str):
            # Try to resolve as template first
            resolved = resolve_template(source_value)
            payload[target_key] = resolved
        elif isinstance(source_value, dict):
            # For dict values, resolve each value
            resolved_dict = {}
            for k, v in source_value.items():
                if isinstance(v, str):
                    resolved_dict[k] = resolve_template(v)
                else:
                    resolved_dict[k] = v
            payload[target_key] = resolved_dict
        elif isinstance(source_value, list):
            # For list values, resolve each element
            resolved_list = []
            for item in source_value:
                if isinstance(item, str):
                    resolved_list.append(resolve_template(item))
                else:
                    resolved_list.append(item)
            payload[target_key] = resolved_list
        else:
            # For non-string values, use as-is
            payload[target_key] = source_value

    return payload

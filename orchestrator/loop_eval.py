from __future__ import annotations

import logging
import re
from typing import Any

from hordeforge_utils import resolve_path

logger = logging.getLogger(__name__)


def evaluate_loop_condition(condition: str, state: dict[str, Any]) -> bool:
    """Evaluate loop condition with Jinja2 support.

    Supports:
    - {{path.to.value}} > 0
    - {{path.to.value}} >= 1
    - {{path.to.value}} == 0
    - {{path.to.value}} != 0
    - Boolean expressions like {{value}}
    """
    try:
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string(condition)
        rendered = template.render(**state)
        rendered = rendered.strip()
    except Exception as e:
        logger.debug("Jinja2 loop condition evaluation failed, falling back to simple: %s", e)
        return evaluate_loop_condition_simple(condition, state)

    if rendered.lower() in ("true", "false"):
        return rendered.lower() == "true"

    pattern = r"^(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+)$"
    match = re.match(pattern, rendered)
    if match:
        left_str, operator, right_str = match.groups()

        left_value = resolve_path(state, left_str.strip())
        if left_value is None:
            try:
                left_value = float(left_str.strip())
            except (ValueError, TypeError):
                left_value = bool(left_str.strip())

        right_value: Any
        try:
            right_value = float(right_str.strip())
        except ValueError:
            right_str_lower = right_str.strip().lower()
            if right_str_lower == "true":
                right_value = True
            elif right_str_lower == "false":
                right_value = False
            else:
                right_value = right_str.strip()

        if operator == "==":
            return left_value == right_value
        if operator == "!=":
            return left_value != right_value
        if operator == ">":
            try:
                return float(left_value) > float(right_value)
            except (TypeError, ValueError):
                return False
        if operator == "<":
            try:
                return float(left_value) < float(right_value)
            except (TypeError, ValueError):
                return False
        if operator == ">=":
            try:
                return float(left_value) >= float(right_value)
            except (TypeError, ValueError):
                return False
        if operator == "<=":
            try:
                return float(left_value) <= float(right_value)
            except (TypeError, ValueError):
                return False

    return bool(rendered)


def evaluate_loop_condition_simple(condition: str, state: dict[str, Any]) -> bool:
    """Fallback simple loop condition evaluation without Jinja2."""
    pattern = r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}\s*(==|!=|>=|<=|>|<)\s*(-?\d+)"
    match = re.fullmatch(pattern, condition.strip())
    if not match:
        return False

    path, operator, right_value_raw = match.groups()
    left = resolve_path(state, path)
    if left is None:
        return False
    try:
        left_value = float(left)
        right_value = float(right_value_raw)
    except (TypeError, ValueError):
        return False

    if operator == "==":
        return left_value == right_value
    if operator == "!=":
        return left_value != right_value
    if operator == ">":
        return left_value > right_value
    if operator == "<":
        return left_value < right_value
    if operator == ">=":
        return left_value >= right_value
    return left_value <= right_value

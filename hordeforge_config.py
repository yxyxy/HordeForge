from __future__ import annotations

import json
import os
from dataclasses import dataclass


def _get_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _get_int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _get_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    parts = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not parts:
        return default
    # Preserve declaration order while deduplicating values.
    return tuple(dict.fromkeys(parts))


def _get_json_mapping_env(name: str) -> dict[str, tuple[str, ...]]:
    raw = os.getenv(name)
    if raw is None:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    mapping: dict[str, tuple[str, ...]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            values = tuple(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str):
            values = tuple(part.strip() for part in value.split(",") if part.strip())
        else:
            continue
        if values:
            mapping[key.strip().lower()] = values
    return mapping


@dataclass(frozen=True, slots=True)
class RunConfig:
    gateway_url: str
    pipelines_dir: str
    rules_dir: str
    rule_set_version: str
    request_timeout_seconds: float
    status_timeout_seconds: float
    health_timeout_seconds: float
    max_parallel_workers: int
    strict_schema_validation: bool
    enable_dynamic_fallback: bool
    webhook_secret: str
    storage_dir: str
    idempotency_ttl_seconds: int
    operator_api_key: str
    operator_allowed_roles: tuple[str, ...]
    manual_command_allowed_sources: tuple[str, ...]
    default_tenant_id: str
    tenant_repository_map: dict[str, tuple[str, ...]]
    enforce_tenant_boundaries: bool
    retention_runs_days: int
    retention_logs_days: int
    retention_artifacts_days: int
    retention_audit_days: int

    @classmethod
    def from_env(cls) -> RunConfig:
        gateway_url = os.getenv("HORDEFORGE_GATEWAY_URL", "http://localhost:8000").rstrip("/")
        pipelines_dir = os.getenv("HORDEFORGE_PIPELINES_DIR", "pipelines")
        rules_dir = os.getenv("HORDEFORGE_RULES_DIR", "rules")
        rule_set_version = os.getenv("HORDEFORGE_RULE_SET_VERSION", "1.0")
        request_timeout = _get_float_env("HORDEFORGE_REQUEST_TIMEOUT_SECONDS", 30.0)
        status_timeout = _get_float_env("HORDEFORGE_STATUS_TIMEOUT_SECONDS", 15.0)
        health_timeout = _get_float_env("HORDEFORGE_HEALTH_TIMEOUT_SECONDS", 10.0)
        max_parallel_workers = _get_int_env("HORDEFORGE_MAX_PARALLEL_WORKERS", 4, minimum=1)
        strict_schema_validation = _get_bool_env("HORDEFORGE_STRICT_SCHEMA_VALIDATION", True)
        enable_dynamic_fallback = _get_bool_env("HORDEFORGE_ENABLE_DYNAMIC_FALLBACK", True)
        webhook_secret = os.getenv("HORDEFORGE_WEBHOOK_SECRET", "local-dev-secret")
        storage_dir = os.getenv("HORDEFORGE_STORAGE_DIR", ".hordeforge_data")
        idempotency_ttl_raw = os.getenv("HORDEFORGE_IDEMPOTENCY_TTL_SECONDS", "3600")
        operator_api_key = os.getenv("HORDEFORGE_OPERATOR_API_KEY", "local-operator-key")
        operator_allowed_roles = _get_csv_env("HORDEFORGE_OPERATOR_ALLOWED_ROLES", ("operator",))
        manual_command_allowed_sources = _get_csv_env(
            "HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES",
            ("api",),
        )
        default_tenant_id = (
            os.getenv("HORDEFORGE_DEFAULT_TENANT_ID", "default").strip().lower() or "default"
        )
        tenant_repository_map = _get_json_mapping_env("HORDEFORGE_TENANT_REPOSITORY_MAP")
        enforce_tenant_boundaries = _get_bool_env("HORDEFORGE_ENFORCE_TENANT_BOUNDARIES", False)
        retention_runs_days = _get_int_env("HORDEFORGE_RETENTION_RUNS_DAYS", 90, minimum=1)
        retention_logs_days = _get_int_env("HORDEFORGE_RETENTION_LOGS_DAYS", 30, minimum=1)
        retention_artifacts_days = _get_int_env("HORDEFORGE_RETENTION_ARTIFACTS_DAYS", 7, minimum=1)
        retention_audit_days = _get_int_env("HORDEFORGE_RETENTION_AUDIT_DAYS", 365, minimum=1)
        try:
            idempotency_ttl_seconds = max(1, int(idempotency_ttl_raw))
        except ValueError:
            idempotency_ttl_seconds = 3600

        return cls(
            gateway_url=gateway_url,
            pipelines_dir=pipelines_dir,
            rules_dir=rules_dir,
            rule_set_version=rule_set_version,
            request_timeout_seconds=request_timeout,
            status_timeout_seconds=status_timeout,
            health_timeout_seconds=health_timeout,
            max_parallel_workers=max_parallel_workers,
            strict_schema_validation=strict_schema_validation,
            enable_dynamic_fallback=enable_dynamic_fallback,
            webhook_secret=webhook_secret,
            storage_dir=storage_dir,
            idempotency_ttl_seconds=idempotency_ttl_seconds,
            operator_api_key=operator_api_key,
            operator_allowed_roles=operator_allowed_roles,
            manual_command_allowed_sources=manual_command_allowed_sources,
            default_tenant_id=default_tenant_id,
            tenant_repository_map=tenant_repository_map,
            enforce_tenant_boundaries=enforce_tenant_boundaries,
            retention_runs_days=retention_runs_days,
            retention_logs_days=retention_logs_days,
            retention_artifacts_days=retention_artifacts_days,
            retention_audit_days=retention_audit_days,
        )

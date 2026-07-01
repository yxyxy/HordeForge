from __future__ import annotations

import json
import os
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


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


class RunConfig(BaseModel):
    model_config = {"frozen": True}

    gateway_url: str = "http://localhost:8000"
    pipelines_dir: str = "pipelines"
    rules_dir: str = "rules"
    rule_set_version: str = "1.0"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    request_timeout_seconds: Annotated[float, Field(ge=0.1)] = 30.0
    status_timeout_seconds: Annotated[float, Field(ge=0.1)] = 15.0
    health_timeout_seconds: Annotated[float, Field(ge=0.1)] = 10.0
    max_parallel_workers: Annotated[int, Field(ge=1)] = 4
    strict_schema_validation: bool = True
    enable_dynamic_fallback: bool = True
    webhook_secret: str = ""
    storage_dir: str = ".hordeforge_data"
    queue_backend: str = "memory"
    idempotency_ttl_seconds: Annotated[int, Field(ge=1)] = 3600
    operator_api_key: str = ""
    operator_allowed_roles: tuple[str, ...] = ("operator",)
    manual_command_allowed_sources: tuple[str, ...] = ("api",)
    default_tenant_id: str = "default"
    tenant_repository_map: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    enforce_tenant_boundaries: bool = False
    retention_runs_days: Annotated[int, Field(ge=1)] = 90
    retention_logs_days: Annotated[int, Field(ge=1)] = 30
    retention_artifacts_days: Annotated[int, Field(ge=1)] = 7
    retention_audit_days: Annotated[int, Field(ge=1)] = 365
    auth_enabled: bool = False
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    session_ttl_seconds: Annotated[int, Field(ge=60)] = 3600
    auth_public_paths: tuple[str, ...] = (
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    metrics_exporter: str = ""
    metrics_export_interval_seconds: Annotated[int, Field(ge=10)] = 60
    prometheus_pushgateway_url: str = "http://localhost:9091"
    datadog_api_key: str = ""
    datadog_app_key: str = ""
    datadog_site: str = "datadoghq.com"
    audit_log_dir: str = ".hordeforge_data/audit"

    @field_validator("gateway_url", mode="before")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/") if isinstance(v, str) else v

    @field_validator("queue_backend", mode="before")
    @classmethod
    def _normalize_queue_backend(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("default_tenant_id", mode="before")
    @classmethod
    def _normalize_tenant_id(cls, v: str) -> str:
        return (v.strip().lower() or "default") if isinstance(v, str) else v

    @classmethod
    def from_env(cls, *, testing: bool | None = None) -> RunConfig:
        if testing is None:
            testing = _get_bool_env("HORDEFORGE_TESTING", False)

        webhook_secret = _get_env("HORDEFORGE_WEBHOOK_SECRET")
        if not webhook_secret and not testing:
            raise ValueError(
                "HORDEFORGE_WEBHOOK_SECRET is required. "
                "Set it via environment variable or .env file."
            )

        operator_api_key = _get_env("HORDEFORGE_OPERATOR_API_KEY")
        if not operator_api_key and not testing:
            raise ValueError(
                "HORDEFORGE_OPERATOR_API_KEY is required. "
                "Set it via environment variable or .env file."
            )

        jwt_secret_key = _get_env("HORDEFORGE_JWT_SECRET_KEY")
        if not jwt_secret_key and not testing:
            raise ValueError(
                "HORDEFORGE_JWT_SECRET_KEY is required. "
                "Set it via environment variable or .env file."
            )

        idempotency_ttl_raw = _get_env("HORDEFORGE_IDEMPOTENCY_TTL_SECONDS", "3600")
        try:
            idempotency_ttl_seconds = max(1, int(idempotency_ttl_raw))
        except ValueError:
            idempotency_ttl_seconds = 3600

        return cls(
            gateway_url=_get_env("HORDEFORGE_GATEWAY_URL", "http://localhost:8000"),
            pipelines_dir=_get_env("HORDEFORGE_PIPELINES_DIR", "pipelines"),
            rules_dir=_get_env("HORDEFORGE_RULES_DIR", "rules"),
            rule_set_version=_get_env("HORDEFORGE_RULE_SET_VERSION", "1.0"),
            embedding_model=_get_env(
                "HORDEFORGE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            request_timeout_seconds=_get_float_env("HORDEFORGE_REQUEST_TIMEOUT_SECONDS", 30.0),
            status_timeout_seconds=_get_float_env("HORDEFORGE_STATUS_TIMEOUT_SECONDS", 15.0),
            health_timeout_seconds=_get_float_env("HORDEFORGE_HEALTH_TIMEOUT_SECONDS", 10.0),
            max_parallel_workers=_get_int_env("HORDEFORGE_MAX_PARALLEL_WORKERS", 4, minimum=1),
            strict_schema_validation=_get_bool_env("HORDEFORGE_STRICT_SCHEMA_VALIDATION", True),
            enable_dynamic_fallback=_get_bool_env("HORDEFORGE_ENABLE_DYNAMIC_FALLBACK", True),
            webhook_secret=webhook_secret,
            storage_dir=_get_env("HORDEFORGE_STORAGE_DIR", ".hordeforge_data"),
            queue_backend=_get_env("HORDEFORGE_QUEUE_BACKEND", "memory"),
            idempotency_ttl_seconds=idempotency_ttl_seconds,
            operator_api_key=operator_api_key,
            operator_allowed_roles=_get_csv_env("HORDEFORGE_OPERATOR_ALLOWED_ROLES", ("operator",)),
            manual_command_allowed_sources=_get_csv_env(
                "HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES",
                ("api",),
            ),
            default_tenant_id=_get_env("HORDEFORGE_DEFAULT_TENANT_ID", "default"),
            tenant_repository_map=_get_json_mapping_env("HORDEFORGE_TENANT_REPOSITORY_MAP"),
            enforce_tenant_boundaries=_get_bool_env("HORDEFORGE_ENFORCE_TENANT_BOUNDARIES", False),
            retention_runs_days=_get_int_env("HORDEFORGE_RETENTION_RUNS_DAYS", 90, minimum=1),
            retention_logs_days=_get_int_env("HORDEFORGE_RETENTION_LOGS_DAYS", 30, minimum=1),
            retention_artifacts_days=_get_int_env(
                "HORDEFORGE_RETENTION_ARTIFACTS_DAYS", 7, minimum=1
            ),
            retention_audit_days=_get_int_env("HORDEFORGE_RETENTION_AUDIT_DAYS", 365, minimum=1),
            auth_enabled=_get_bool_env("HORDEFORGE_AUTH_ENABLED", False),
            jwt_secret_key=jwt_secret_key,
            jwt_algorithm=_get_env("HORDEFORGE_JWT_ALGORITHM", "HS256"),
            jwt_issuer=os.getenv("HORDEFORGE_JWT_ISSUER"),
            jwt_audience=os.getenv("HORDEFORGE_JWT_AUDIENCE"),
            session_ttl_seconds=_get_int_env("HORDEFORGE_SESSION_TTL_SECONDS", 3600, minimum=60),
            auth_public_paths=_get_csv_env(
                "HORDEFORGE_AUTH_PUBLIC_PATHS",
                ("/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"),
            ),
            metrics_exporter=_get_env("HORDEFORGE_METRICS_EXPORTER"),
            metrics_export_interval_seconds=_get_int_env(
                "HORDEFORGE_METRICS_EXPORT_INTERVAL_SECONDS", 60, minimum=10
            ),
            prometheus_pushgateway_url=_get_env(
                "HORDEFORGE_PROMETHEUS_PUSHGATEWAY_URL", "http://localhost:9091"
            ),
            datadog_api_key=_get_env("HORDEFORGE_DATADOG_API_KEY"),
            datadog_app_key=_get_env("HORDEFORGE_DATADOG_APP_KEY"),
            datadog_site=_get_env("HORDEFORGE_DATADOG_SITE", "datadoghq.com"),
            audit_log_dir=_get_env("HORDEFORGE_AUDIT_LOG_DIR", ".hordeforge_data/audit"),
        )

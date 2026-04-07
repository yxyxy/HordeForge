import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from cli.repo_store import (
    add_or_update_llm_profile,
    get_llm_profile,
    get_secret_value,
    list_llm_profiles,
    list_secret_keys,
    remove_llm_profile,
    remove_secret_value,
    set_default_llm_profile,
    set_secret_value,
)
from hordeforge_config import RunConfig
from logging_utils import redact_mapping, redact_sensitive_data
from observability.alerts import AlertDispatcher
from observability.metrics import RuntimeMetrics
from orchestrator import OrchestratorEngine
from orchestrator.override import RUN_OVERRIDE_REGISTRY
from scheduler.auth.jwt_validator import JWTValidator
from scheduler.auth.middleware import AuthMiddleware
from scheduler.auth.rbac import Permission, RBACUser, Role, has_role_permission
from scheduler.cron_dispatcher import CronDispatcher
from scheduler.cron_runtime import build_default_cron_dispatcher
from scheduler.idempotency import IdempotencyStore, build_idempotency_key
from scheduler.queue_backends import get_task_queue_backend

# Rate limiting imports
from scheduler.rate_limiter import (
    get_default_api_limiter,
)
from scheduler.task_queue import InMemoryTaskQueue, QueueTaskRequest
from scheduler.tenant_registry import (
    TenantRepositoryRegistry,
    extract_repository_full_name,
    normalize_tenant_id,
)
from storage.backends import archive_and_prune_rotated_logs, rotate_current_log_files
from storage.models import ArtifactRecord, RunRecord, StepLogRecord
from storage.repositories.artifact_repository import ArtifactRepository
from storage.repositories.run_repository import RunRepository
from storage.repositories.step_log_repository import StepLogRepository

try:
    from scheduler.rate_limiter_middleware import RateLimitMiddleware

    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    RateLimitMiddleware = None

app = FastAPI(title="HordeForge Scheduler Gateway", version="0.1.0")

logger = logging.getLogger("hordeforge.gateway")

config = RunConfig.from_env()
CONTAINER_STARTED_AT = datetime.now(timezone.utc)

# Initialize JWT validator if auth is enabled
JWT_VALIDATOR: JWTValidator | None = None
if config.auth_enabled:
    JWT_VALIDATOR = JWTValidator(
        secret_key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
        issuer=config.jwt_issuer,
        audience=config.jwt_audience,
    )
    # Add auth middleware
    app.add_middleware(
        AuthMiddleware,
        jwt_validator=JWT_VALIDATOR,
        public_paths=list(config.auth_public_paths),
    )
    logger.info("JWT authentication enabled")

# Add rate limiting middleware if available
if RATE_LIMITER_AVAILABLE and RateLimitMiddleware is not None:
    rate_limiter = get_default_api_limiter()
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

engine = OrchestratorEngine(
    pipelines_dir=config.pipelines_dir,
    rules_dir=config.rules_dir,
    rule_set_version=config.rule_set_version,
    max_parallel_workers=config.max_parallel_workers,
    strict_schema_validation=config.strict_schema_validation,
    enable_dynamic_fallback=config.enable_dynamic_fallback,
)
RUNS: dict[str, dict[str, Any]] = {}
RUN_REPOSITORY = RunRepository(storage_dir=config.storage_dir)
STEP_LOG_REPOSITORY = StepLogRepository(storage_dir=config.storage_dir)
ARTIFACT_REPOSITORY = ArtifactRepository(storage_dir=config.storage_dir)
IDEMPOTENCY_STORE = IdempotencyStore(ttl_seconds=config.idempotency_ttl_seconds)
RUN_RUNTIME_INPUTS: dict[str, dict[str, Any]] = {}
METRICS = RuntimeMetrics()
ALERT_DISPATCHER = AlertDispatcher(throttle_seconds=60)
logger = logging.getLogger("hordeforge.gateway")
CRON_DISPATCHER: CronDispatcher | None = None
QUEUE_BACKEND_REQUESTED = config.queue_backend
QUEUE_BACKEND_ACTIVE: str | None = None
QUEUE_BACKEND_ERROR: str | None = None
QUEUE_AUTODRAIN_THREAD: threading.Thread | None = None
QUEUE_AUTODRAIN_STOP = threading.Event()


def _init_task_queue():
    global QUEUE_BACKEND_ACTIVE, QUEUE_BACKEND_ERROR
    backend_type = QUEUE_BACKEND_REQUESTED or "memory"
    try:
        queue = get_task_queue_backend(backend_type)
        QUEUE_BACKEND_ACTIVE = backend_type
        return queue
    except Exception as exc:  # noqa: BLE001
        QUEUE_BACKEND_ACTIVE = "memory"
        QUEUE_BACKEND_ERROR = str(exc)
        logger.warning(
            "Queue backend '%s' failed to initialize: %s. Falling back to memory.",
            backend_type,
            exc,
        )
        return InMemoryTaskQueue()


TASK_QUEUE = _init_task_queue()
TENANT_REGISTRY = TenantRepositoryRegistry(
    mapping=config.tenant_repository_map,
    default_tenant_id=config.default_tenant_id,
    enforce_boundaries=config.enforce_tenant_boundaries,
)
STORAGE_BACKEND_REQUESTED = os.getenv("HORDEFORGE_STORAGE_BACKEND", "json")
STORAGE_BACKEND_ERROR: str | None = None


def _validate_backends_on_startup() -> None:
    global STORAGE_BACKEND_ERROR, QUEUE_BACKEND_ERROR
    if STORAGE_BACKEND_REQUESTED == "postgres":
        try:
            store = RUN_REPOSITORY.store
            if hasattr(store, "health_check"):
                health = store.health_check()
                if isinstance(health, dict) and not health.get("healthy", True):
                    STORAGE_BACKEND_ERROR = str(health.get("error", "unhealthy"))
                    logger.warning(
                        "Postgres storage health check failed: %s",
                        STORAGE_BACKEND_ERROR,
                    )
            else:
                store.read_all()
        except Exception as exc:  # noqa: BLE001
            STORAGE_BACKEND_ERROR = str(exc)
            logger.warning("Postgres storage health check failed: %s", exc)

    if QUEUE_BACKEND_REQUESTED == "redis":
        if QUEUE_BACKEND_ERROR:
            logger.warning(
                "Redis queue backend failed to initialize: %s",
                QUEUE_BACKEND_ERROR,
            )
            return
        if hasattr(TASK_QUEUE, "health_check"):
            try:
                health = TASK_QUEUE.health_check()
                if isinstance(health, dict) and not health.get("healthy", True):
                    QUEUE_BACKEND_ERROR = str(health.get("error", "unhealthy"))
                    logger.warning("Redis queue health check failed: %s", QUEUE_BACKEND_ERROR)
            except Exception as exc:  # noqa: BLE001
                QUEUE_BACKEND_ERROR = str(exc)
                logger.warning("Redis queue health check failed: %s", exc)


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

_validate_backends_on_startup()


class PipelineRequest(BaseModel):
    pipeline_name: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="api", min_length=1)
    tenant_id: str | None = None
    repository_full_name: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    async_mode: bool = False


class OverrideCommand(BaseModel):
    action: str = Field(..., min_length=1)
    reason: str = Field(default="")


class CronManualTriggerRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class QueueDrainRequest(BaseModel):
    max_items: int = Field(default=10, ge=1, le=200)


class LlmProfileUpsertRequest(BaseModel):
    profile_name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    base_url: str | None = None
    api_key_ref: str | None = None
    set_default: bool = False


class SecretUpsertRequest(BaseModel):
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    role: str
    source: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(level: int, run_id: str, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    correlation_id = safe_fields.pop("correlation_id", None)
    step = safe_fields.pop("step", safe_fields.pop("step_name", None))
    payload = {
        "timestamp": _utc_now_iso(),
        "level": logging.getLevelName(level),
        "component": "gateway",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "step": step,
        "event": event,
        **safe_fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False))


def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    *,
    run_id: str | None = None,
    correlation_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "run_id": run_id,
                "correlation_id": correlation_id,
                "timestamp": _utc_now_iso(),
            }
        },
    )


def _sanitize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive_data(inputs) if isinstance(inputs, dict) else {}


def _sanitize_run_result(result: dict[str, Any] | None) -> dict[str, Any]:
    return redact_sensitive_data(result) if isinstance(result, dict) else {}


def _remember_runtime_inputs(run_id: str, inputs: dict[str, Any]) -> None:
    RUN_RUNTIME_INPUTS[run_id] = dict(inputs if isinstance(inputs, dict) else {})


def _resolve_runtime_inputs(record: RunRecord) -> dict[str, Any]:
    runtime_inputs = RUN_RUNTIME_INPUTS.get(record.run_id)
    if isinstance(runtime_inputs, dict):
        return dict(runtime_inputs)
    return dict(record.inputs) if isinstance(record.inputs, dict) else {}


def _resolve_tenant_repository(
    request: PipelineRequest,
) -> tuple[str, str | None, str | None]:
    repository_full_name = extract_repository_full_name(
        inputs=request.inputs,
        explicit=request.repository_full_name,
    )
    decision = TENANT_REGISTRY.validate_boundary(
        tenant_id=request.tenant_id,
        repository_full_name=repository_full_name,
    )
    if not decision.allowed:
        return decision.tenant_id, decision.repository_full_name, decision.reason
    return decision.tenant_id, decision.repository_full_name, None


def _build_run_id(*, tenant_id: str) -> str:
    return f"{tenant_id}:{uuid4()}"


def _scope_idempotency_key(*, tenant_id: str, key: str) -> str:
    return f"{tenant_id}:{key}"


def _normalize_access_field(value: str | None) -> str:
    return str(value or "").strip().lower()


def _get_user_from_request(request: Any) -> RBACUser | None:
    """Extract user from request state (set by JWT middleware)."""
    if not hasattr(request, "state") or not hasattr(request.state, "user"):
        return None
    user_data = request.state.user
    if not isinstance(user_data, dict):
        return None
    try:
        role = Role(user_data.get("role", "viewer"))
    except ValueError:
        role = Role.VIEWER
    return RBACUser(
        user_id=user_data.get("user_id", ""),
        role=role,
        email=user_data.get("email"),
    )


def _authorize_jwt_request(
    request: Any,
    required_permission: Permission,
) -> tuple[bool, str | None, RBACUser | None]:
    """Authorize request using JWT user info from request.state.

    Returns:
        tuple of (authorized, denial_reason, user)
    """
    # If auth is not enabled, allow all requests
    if not config.auth_enabled:
        return True, None, None

    user = _get_user_from_request(request)
    if user is None:
        return False, "unauthenticated", None

    if not user.has_permission(required_permission):
        return False, "permission_denied", user

    return True, None, user


def _audit_jwt_request(
    *,
    run_id: str,
    action: str,
    endpoint: str,
    authorized: bool,
    user: RBACUser | None,
    reason: str | None = None,
    outcome: str | None = None,
) -> None:
    """Audit log for JWT-based requests."""
    _log_event(
        logging.INFO if authorized else logging.WARNING,
        run_id,
        "jwt_auth_audit",
        action=action,
        endpoint=endpoint,
        authorized=authorized,
        user_id=user.user_id if user else None,
        user_role=user.role.value if user else None,
        reason=reason,
        outcome=outcome,
    )


def _authorize_manual_command(
    operator_key: str | None,
    operator_role: str | None,
    command_source: str | None,
    required_permission: Permission | None = None,
) -> tuple[bool, str | None, OperatorIdentity | None]:
    if not operator_key or operator_key != config.operator_api_key:
        return False, "invalid_operator_key", None

    role = _normalize_access_field(operator_role)
    source = _normalize_access_field(command_source)
    if not role:
        return False, "missing_operator_role", None
    if not source:
        return False, "missing_command_source", None
    if role not in set(config.operator_allowed_roles):
        return False, "operator_role_not_allowed", OperatorIdentity(role=role, source=source)
    if source not in set(config.manual_command_allowed_sources):
        return False, "command_source_not_allowed", OperatorIdentity(role=role, source=source)

    # Check RBAC permission if required
    if required_permission is not None:
        try:
            rbac_role = Role(role)
        except ValueError:
            return False, "invalid_role_for_rbac", OperatorIdentity(role=role, source=source)
        if not has_role_permission(rbac_role, required_permission):
            return False, "permission_denied", OperatorIdentity(role=role, source=source)

    return True, None, OperatorIdentity(role=role, source=source)


def _audit_manual_command(
    *,
    run_id: str,
    action: str,
    endpoint: str,
    authorized: bool,
    principal: OperatorIdentity | None,
    reason: str | None = None,
    outcome: str | None = None,
) -> None:
    _log_event(
        logging.INFO if authorized else logging.WARNING,
        run_id,
        "manual_command_audit",
        action=action,
        endpoint=endpoint,
        authorized=authorized,
        operator_role=principal.role if principal else None,
        command_source=principal.source if principal else None,
        reason=reason,
        outcome=outcome,
    )


def _decode_json_response(response: JSONResponse) -> dict[str, Any]:
    try:
        body = response.body.decode("utf-8")
    except UnicodeDecodeError:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _queue_autodrain_enabled() -> bool:
    value = str(os.getenv("HORDEFORGE_QUEUE_AUTODRAIN_ENABLED", "true")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _queue_autodrain_interval_seconds() -> float:
    raw_value = os.getenv("HORDEFORGE_QUEUE_AUTODRAIN_INTERVAL_SECONDS", "1.0")
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        parsed = 1.0
    return max(0.1, parsed)


def _queue_autodrain_batch_size() -> int:
    raw_value = os.getenv("HORDEFORGE_QUEUE_AUTODRAIN_BATCH_SIZE", "10")
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(200, parsed))


def _queue_autodrain_shutdown_timeout_seconds() -> float:
    raw_value = os.getenv("HORDEFORGE_QUEUE_AUTODRAIN_SHUTDOWN_TIMEOUT_SECONDS", "15")
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        parsed = 15.0
    return max(1.0, min(300.0, parsed))


def _drain_queue_once(*, max_items: int) -> list[dict[str, Any]]:
    claimed = TASK_QUEUE.claim_next(max_items=max_items)
    records: list[dict[str, Any]] = []
    for task in claimed:
        try:
            response = run_pipeline(
                PipelineRequest(
                    pipeline_name=task.pipeline_name,
                    inputs=task.inputs,
                    source=task.source,
                    correlation_id=task.correlation_id,
                    idempotency_key=task.idempotency_key,
                    tenant_id=task.tenant_id,
                    repository_full_name=task.repository_full_name,
                    async_mode=False,
                )
            )
            if isinstance(response, JSONResponse):
                payload = _decode_json_response(response)
                message = str(payload.get("error", {}).get("message", "Queue task failed"))
                completed = TASK_QUEUE.mark_failed(task.task_id, message)
            else:
                completed = TASK_QUEUE.mark_succeeded(task.task_id, response)
        except Exception as exc:  # noqa: BLE001
            completed = TASK_QUEUE.mark_failed(task.task_id, str(exc))
        records.append(completed.to_dict())
    return records


def _queue_autodrain_worker() -> None:
    interval = _queue_autodrain_interval_seconds()
    batch_size = _queue_autodrain_batch_size()
    logger.info(
        "Queue autodrain worker started interval_seconds=%s batch_size=%s",
        interval,
        batch_size,
    )
    while not QUEUE_AUTODRAIN_STOP.is_set():
        try:
            records = _drain_queue_once(max_items=batch_size)
            if records:
                logger.info("Queue autodrain processed %s task(s).", len(records))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Queue autodrain worker error: %s", str(exc)[:300])
        QUEUE_AUTODRAIN_STOP.wait(interval)
    logger.info("Queue autodrain worker stopped.")


@app.on_event("startup")
def startup_queue_autodrain_worker() -> None:
    global QUEUE_AUTODRAIN_THREAD
    if STORAGE_BACKEND_REQUESTED == "json":
        archive_and_prune_rotated_logs(
            storage_dir=config.storage_dir,
            archive_after_days=7,
            retention_days=7,
        )
    if not _queue_autodrain_enabled():
        logger.info("Queue autodrain worker disabled by HORDEFORGE_QUEUE_AUTODRAIN_ENABLED.")
        return
    if QUEUE_AUTODRAIN_THREAD is not None and QUEUE_AUTODRAIN_THREAD.is_alive():
        return
    QUEUE_AUTODRAIN_STOP.clear()
    QUEUE_AUTODRAIN_THREAD = threading.Thread(
        target=_queue_autodrain_worker,
        name="hordeforge-queue-autodrain",
        daemon=False,
    )
    QUEUE_AUTODRAIN_THREAD.start()


@app.on_event("shutdown")
def shutdown_queue_autodrain_worker() -> None:
    global QUEUE_AUTODRAIN_THREAD
    if QUEUE_AUTODRAIN_THREAD is not None:
        QUEUE_AUTODRAIN_STOP.set()
        shutdown_timeout = _queue_autodrain_shutdown_timeout_seconds()
        QUEUE_AUTODRAIN_THREAD.join(timeout=shutdown_timeout)
        if QUEUE_AUTODRAIN_THREAD.is_alive():
            logger.warning(
                "Queue autodrain worker did not stop within %ss.",
                shutdown_timeout,
            )
        QUEUE_AUTODRAIN_THREAD = None

    if STORAGE_BACKEND_REQUESTED == "json":
        rotate_current_log_files(
            storage_dir=config.storage_dir,
            container_started_at=CONTAINER_STARTED_AT,
        )
        archive_and_prune_rotated_logs(
            storage_dir=config.storage_dir,
            archive_after_days=7,
            retention_days=7,
        )


@app.post("/llm/profiles")
def upsert_llm_profile(request: LlmProfileUpsertRequest) -> dict[str, Any]:
    add_or_update_llm_profile(
        profile_name=request.profile_name,
        provider=request.provider,
        model=request.model,
        base_url=request.base_url,
        api_key_ref=request.api_key_ref,
        set_default=request.set_default,
    )
    profile = get_llm_profile(request.profile_name)
    return {"status": "ok", "profile": profile}


@app.get("/llm/profiles")
def get_llm_profiles(profile_name: str | None = None) -> dict[str, Any]:
    if isinstance(profile_name, str) and profile_name.strip():
        profile = get_llm_profile(profile_name.strip())
        if profile is None:
            raise HTTPException(status_code=404, detail="LLM profile not found")
        return {"profile": profile}
    return {"profiles": list_llm_profiles()}


@app.post("/llm/profiles/{profile_name}/default")
def set_default_profile(profile_name: str) -> dict[str, Any]:
    if not set_default_llm_profile(profile_name):
        raise HTTPException(status_code=404, detail="LLM profile not found")
    return {"status": "ok", "default_profile": profile_name}


@app.delete("/llm/profiles/{profile_name}")
def delete_llm_profile(profile_name: str, delete_secret: bool = False) -> dict[str, Any]:
    api_key_ref = remove_llm_profile(profile_name)
    if api_key_ref is None:
        raise HTTPException(status_code=404, detail="LLM profile not found")
    if delete_secret and api_key_ref:
        remove_secret_value(api_key_ref)
    return {"status": "ok", "profile_name": profile_name, "api_key_ref": api_key_ref}


@app.post("/secrets")
def upsert_secret(request: SecretUpsertRequest) -> dict[str, Any]:
    set_secret_value(request.name, request.value)
    return {"status": "ok", "name": request.name}


@app.get("/secrets")
def get_secrets(name: str | None = None) -> dict[str, Any]:
    if isinstance(name, str) and name.strip():
        value = get_secret_value(name.strip())
        if value is None:
            raise HTTPException(status_code=404, detail="Secret not found")
        return {"name": name.strip(), "value": value}
    return {"keys": list_secret_keys()}


@app.delete("/secrets/{name}")
def delete_secret(name: str) -> dict[str, Any]:
    removed = remove_secret_value(name)
    if not removed:
        raise HTTPException(status_code=404, detail="Secret not found")
    return {"status": "ok", "name": name}


def _trigger_pipeline_from_cron(
    pipeline_name: str,
    inputs: dict[str, Any],
    source: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(None, default_tenant_id=config.default_tenant_id)
    response = run_pipeline(
        PipelineRequest(
            pipeline_name=pipeline_name,
            inputs=inputs,
            source=source,
            tenant_id=tenant_id,
            correlation_id=str(uuid4()),
            idempotency_key=idempotency_key,
        )
    )
    if isinstance(response, JSONResponse):
        payload = _decode_json_response(response)
        return {
            "status": "error",
            "status_code": response.status_code,
            "error": payload.get("error", payload),
        }
    return response


def _get_cron_dispatcher() -> CronDispatcher:
    global CRON_DISPATCHER
    if CRON_DISPATCHER is None:
        CRON_DISPATCHER = build_default_cron_dispatcher(_trigger_pipeline_from_cron)
    return CRON_DISPATCHER


def _build_step_summary(step_logs: list[StepLogRecord]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    failed_steps: list[str] = []
    retry_sum = 0
    for item in step_logs:
        status = str(item.status).upper()
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in {"FAILED", "BLOCKED"}:
            failed_steps.append(item.step_name)
        retry_sum += max(0, int(item.retry_count))

    return {
        "step_count": len(step_logs),
        "status_counts": status_counts,
        "failed_steps": failed_steps,
        "retry_count_sum": retry_sum,
    }


def _to_payload(record: RunRecord) -> dict[str, Any]:
    payload = record.to_dict()
    payload["inputs"] = _sanitize_inputs(payload.get("inputs", {}))
    payload["result"] = _sanitize_run_result(payload.get("result"))
    step_logs = STEP_LOG_REPOSITORY.list_by_run(record.run_id, tenant_id=record.tenant_id)
    payload["step_logs"] = [item.to_dict() for item in step_logs]
    payload["artifacts"] = [
        redact_sensitive_data(item.to_dict())
        for item in ARTIFACT_REPOSITORY.list_by_run(record.run_id, tenant_id=record.tenant_id)
    ]
    payload["step_summary"] = _build_step_summary(step_logs)
    return payload


def _persist_step_and_artifact_logs(run_record: RunRecord) -> None:
    result = run_record.result
    if not isinstance(result, dict):
        return
    steps = result.get("steps", {})
    if not isinstance(steps, dict):
        return
    run_state = result.get("run_state", {})
    run_state_steps: dict[str, Any] = {}
    if isinstance(run_state, dict) and isinstance(run_state.get("steps"), list):
        for item in run_state["steps"]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                run_state_steps[item["name"]] = item

    step_logs: list[StepLogRecord] = []
    artifacts: list[ArtifactRecord] = []
    for step_name, step_result in steps.items():
        if not isinstance(step_result, dict):
            continue
        step_state = run_state_steps.get(step_name, {})
        status = str(step_result.get("status", "UNKNOWN"))
        error_message = None
        logs = step_result.get("logs")
        if isinstance(logs, list) and logs:
            error_message = str(logs[0])

        artifact_ids: list[str] = []
        raw_artifacts = step_result.get("artifacts", [])
        if isinstance(raw_artifacts, list):
            for raw_artifact in raw_artifacts:
                if not isinstance(raw_artifact, dict):
                    continue
                metadata = raw_artifact.get("metadata")
                if isinstance(metadata, dict) and isinstance(metadata.get("artifact_id"), str):
                    artifact_ids.append(str(metadata.get("artifact_id")))

        step_logs.append(
            StepLogRecord(
                run_id=run_record.run_id,
                step_name=step_name,
                status=status,
                tenant_id=run_record.tenant_id,
                started_at=step_state.get("started_at", run_record.started_at),
                finished_at=step_state.get("finished_at", run_record.finished_at),
                error=step_state.get("error")
                or (error_message if status in {"FAILED", "BLOCKED"} else None),
                retry_count=max(0, int(step_state.get("attempts", 1)) - 1),
                step_input_hash=(
                    str(step_state.get("input_hash")).strip()
                    if step_state.get("input_hash") is not None
                    else None
                ),
                artifact_ids=artifact_ids,
            )
        )

        if not isinstance(raw_artifacts, list):
            continue
        for raw_artifact in raw_artifacts:
            if not isinstance(raw_artifact, dict):
                continue
            artifact_type = str(raw_artifact.get("type", "unknown")).strip() or "unknown"
            content = raw_artifact.get("content")
            if not isinstance(content, dict):
                continue
            artifacts.append(
                ArtifactRecord(
                    run_id=run_record.run_id,
                    step_name=step_name,
                    artifact_type=artifact_type,
                    content=content,
                    size_bytes=0,
                    tenant_id=run_record.tenant_id,
                )
            )

    STEP_LOG_REPOSITORY.replace_for_run(
        run_record.run_id,
        step_logs,
        tenant_id=run_record.tenant_id,
    )
    ARTIFACT_REPOSITORY.replace_for_run(
        run_record.run_id,
        artifacts,
        tenant_id=run_record.tenant_id,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/redis")
def redis_health() -> dict[str, Any]:
    """Health check for Redis connection."""
    if QUEUE_BACKEND_REQUESTED != "redis":
        return {"status": "not_configured", "backend": QUEUE_BACKEND_REQUESTED}
    if QUEUE_BACKEND_ERROR:
        return {
            "status": "unhealthy",
            "backend": QUEUE_BACKEND_ACTIVE or "redis",
            "error": QUEUE_BACKEND_ERROR,
        }
    if hasattr(TASK_QUEUE, "health_check"):
        health = TASK_QUEUE.health_check()
        if isinstance(health, dict):
            health.setdefault(
                "status",
                "healthy" if health.get("healthy", False) else "unhealthy",
            )
            health.setdefault("backend", QUEUE_BACKEND_ACTIVE or "redis")
            return health
    return {"status": "no_health_check", "backend": QUEUE_BACKEND_ACTIVE or "redis"}


@app.get("/health/postgres")
def postgres_health() -> dict[str, Any]:
    """Health check for Postgres storage backend."""
    if STORAGE_BACKEND_REQUESTED != "postgres":
        return {"status": "not_configured", "backend": STORAGE_BACKEND_REQUESTED}
    if STORAGE_BACKEND_ERROR:
        return {
            "status": "unhealthy",
            "backend": STORAGE_BACKEND_REQUESTED,
            "error": STORAGE_BACKEND_ERROR,
        }
    store = RUN_REPOSITORY.store
    if hasattr(store, "health_check"):
        health = store.health_check()
        if isinstance(health, dict):
            health.setdefault(
                "status",
                "healthy" if health.get("healthy", False) else "unhealthy",
            )
            return health
    try:
        store.read_all()
        return {"status": "healthy", "backend": "postgres"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unhealthy", "backend": "postgres", "error": str(exc)}


@app.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.post("/run-pipeline")
def run_pipeline(request: PipelineRequest) -> dict[str, Any]:
    correlation_id = request.correlation_id or str(uuid4())
    tenant_id, repository_full_name, boundary_error = _resolve_tenant_repository(request)
    if boundary_error is not None:
        _log_event(
            logging.WARNING,
            f"tenant:{tenant_id}",
            "tenant_boundary_rejected",
            pipeline_name=request.pipeline_name,
            source=request.source,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
            reason=boundary_error,
        )
        return _error_response(
            403,
            "TENANT_BOUNDARY_VIOLATION",
            f"Tenant boundary rejected: {boundary_error}",
            correlation_id=correlation_id,
        )

    if request.async_mode:
        queued = TASK_QUEUE.enqueue(
            QueueTaskRequest(
                pipeline_name=request.pipeline_name,
                inputs=dict(request.inputs),
                source=request.source,
                correlation_id=correlation_id,
                tenant_id=tenant_id,
                repository_full_name=repository_full_name,
                idempotency_key=request.idempotency_key,
            )
        )
        _log_event(
            logging.INFO,
            queued.task_id,
            "pipeline_request_enqueued",
            pipeline_name=request.pipeline_name,
            source=request.source,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
            queue_task_id=queued.task_id,
        )
        return {
            "status": "queued",
            "task_id": queued.task_id,
            "pipeline": request.pipeline_name,
            "source": request.source,
            "correlation_id": correlation_id,
            "idempotency_key": request.idempotency_key,
            "tenant_id": tenant_id,
            "repository_full_name": repository_full_name,
        }

    idempotency_key = request.idempotency_key or build_idempotency_key(
        source=request.source,
        pipeline_name=request.pipeline_name,
        payload={
            "tenant_id": tenant_id,
            "repository_full_name": repository_full_name,
            "inputs": request.inputs,
        },
    )
    scoped_idempotency_key = _scope_idempotency_key(tenant_id=tenant_id, key=idempotency_key)
    existing = IDEMPOTENCY_STORE.get(scoped_idempotency_key)
    if existing is not None:
        existing_record = RUN_REPOSITORY.get(existing["run_id"], tenant_id=tenant_id)
        if existing_record is not None:
            existing_record.result = _sanitize_run_result(existing_record.result)
            RUNS[existing_record.run_id] = existing_record.to_dict()
            _log_event(
                logging.INFO,
                existing_record.run_id,
                "idempotency_duplicate_suppressed",
                pipeline_name=existing_record.pipeline_name,
                source=existing_record.source,
                correlation_id=existing_record.correlation_id,
                tenant_id=tenant_id,
                repository_full_name=existing_record.repository_full_name,
                idempotency_key=idempotency_key,
            )
            return {
                "status": "duplicate",
                "run_id": existing_record.run_id,
                "pipeline": existing_record.pipeline_name,
                "source": existing_record.source,
                "correlation_id": existing_record.correlation_id,
                "idempotency_key": idempotency_key,
                "tenant_id": tenant_id,
                "repository_full_name": existing_record.repository_full_name,
                "result": existing_record.result,
            }

    run_id = _build_run_id(tenant_id=tenant_id)
    runtime_inputs = dict(request.inputs) if isinstance(request.inputs, dict) else {}
    runtime_inputs.setdefault("tenant_id", tenant_id)
    if repository_full_name and "repository_full_name" not in runtime_inputs:
        runtime_inputs["repository_full_name"] = repository_full_name
    _remember_runtime_inputs(run_id, runtime_inputs)
    METRICS.mark_run_started()
    _log_event(
        logging.INFO,
        run_id,
        "pipeline_request_received",
        pipeline_name=request.pipeline_name,
        source=request.source,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        repository_full_name=repository_full_name,
    )

    run_record = RunRecord(
        run_id=run_id,
        pipeline_name=request.pipeline_name,
        source=request.source,
        correlation_id=correlation_id,
        started_at=_utc_now_iso(),
        status="RUNNING",
        tenant_id=tenant_id,
        repository_full_name=repository_full_name,
        result=None,
        error=None,
        inputs=_sanitize_inputs(request.inputs),
        idempotency_key=idempotency_key,
    )
    RUN_REPOSITORY.create(run_record)
    RUNS[run_id] = run_record.to_dict()

    def _on_checkpoint(payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        run_record.result = _sanitize_run_result(payload)
        checkpoint = payload.get("checkpoint")
        run_record.checkpoint_state = checkpoint if isinstance(checkpoint, dict) else None
        run_record.status = str(payload.get("status") or "RUNNING")
        RUN_REPOSITORY.upsert(run_record)
        _persist_step_and_artifact_logs(run_record)

    try:
        result = engine.run(
            request.pipeline_name,
            runtime_inputs,
            run_id=run_id,
            metadata={
                "source": request.source,
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "repository_full_name": repository_full_name,
                "__checkpoint_callback": _on_checkpoint,
            },
        )
        run_record.result = _sanitize_run_result(result)
        run_record.status = run_record.result.get("status", "UNKNOWN")
        run_record.finished_at = _utc_now_iso()
        RUN_REPOSITORY.upsert(run_record)
        _persist_step_and_artifact_logs(run_record)
        METRICS.observe_run_result(run_record.result)
        if run_record.status not in {"FAILED", "BLOCKED"}:
            RUN_RUNTIME_INPUTS.pop(run_id, None)
        if run_record.status in {"FAILED", "BLOCKED"}:
            ALERT_DISPATCHER.alert_run_failure(
                run_id=run_record.run_id,
                pipeline_name=run_record.pipeline_name,
                status=run_record.status,
                correlation_id=run_record.correlation_id,
                error=run_record.error,
            )
        _log_event(
            logging.INFO,
            run_id,
            "pipeline_request_completed",
            status=run_record.status,
            pipeline_name=request.pipeline_name,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
        )
    except FileNotFoundError as exc:
        RUN_RUNTIME_INPUTS.pop(run_id, None)
        run_record.status = "FAILED"
        run_record.error = str(exc)
        run_record.finished_at = _utc_now_iso()
        RUN_REPOSITORY.upsert(run_record)
        METRICS.observe_run_result({"status": "FAILED", "summary": {}})
        ALERT_DISPATCHER.alert_run_failure(
            run_id=run_record.run_id,
            pipeline_name=run_record.pipeline_name,
            status=run_record.status,
            correlation_id=run_record.correlation_id,
            error=run_record.error,
        )
        _log_event(
            logging.ERROR,
            run_id,
            "pipeline_request_failed",
            error=str(exc),
            status_code=404,
            pipeline_name=request.pipeline_name,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
        )
        return _error_response(
            404,
            "PIPELINE_NOT_FOUND",
            str(exc),
            run_id=run_id,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        RUN_RUNTIME_INPUTS.pop(run_id, None)
        run_record.status = "FAILED"
        run_record.error = str(exc)
        run_record.finished_at = _utc_now_iso()
        RUN_REPOSITORY.upsert(run_record)
        METRICS.observe_run_result({"status": "FAILED", "summary": {}})
        ALERT_DISPATCHER.alert_run_failure(
            run_id=run_record.run_id,
            pipeline_name=run_record.pipeline_name,
            status=run_record.status,
            correlation_id=run_record.correlation_id,
            error=run_record.error,
        )
        _log_event(
            logging.ERROR,
            run_id,
            "pipeline_request_failed",
            error=str(exc),
            status_code=400,
            pipeline_name=request.pipeline_name,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
        )
        return _error_response(
            400,
            "INVALID_PIPELINE_PAYLOAD",
            str(exc),
            run_id=run_id,
            correlation_id=correlation_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        RUN_RUNTIME_INPUTS.pop(run_id, None)
        run_record.status = "FAILED"
        run_record.error = str(exc)
        run_record.finished_at = _utc_now_iso()
        RUN_REPOSITORY.upsert(run_record)
        METRICS.observe_run_result({"status": "FAILED", "summary": {}})
        ALERT_DISPATCHER.alert_run_failure(
            run_id=run_record.run_id,
            pipeline_name=run_record.pipeline_name,
            status=run_record.status,
            correlation_id=run_record.correlation_id,
            error=run_record.error,
        )
        _log_event(
            logging.ERROR,
            run_id,
            "pipeline_request_failed",
            error=str(exc),
            status_code=500,
            pipeline_name=request.pipeline_name,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            repository_full_name=repository_full_name,
        )
        return _error_response(
            500,
            "PIPELINE_EXECUTION_FAILED",
            "Pipeline execution failed",
            run_id=run_id,
            correlation_id=correlation_id,
        )

    IDEMPOTENCY_STORE.remember(scoped_idempotency_key, run_id, run_record.result or {})
    RUNS[run_id] = run_record.to_dict()
    return {
        "status": "started",
        "run_id": run_id,
        "pipeline": request.pipeline_name,
        "source": request.source,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "tenant_id": tenant_id,
        "repository_full_name": repository_full_name,
        "result": run_record.result,
    }


@app.get("/queue/tasks/{task_id}", response_model=None)
def get_queue_task(task_id: str):
    task = TASK_QUEUE.get(task_id)
    if task is None:
        return _error_response(404, "QUEUE_TASK_NOT_FOUND", f"Queue task not found: {task_id}")
    return task.to_dict()


@app.post("/queue/drain", response_model=None)
def drain_queue(
    http_request: Request,
    request: QueueDrainRequest,
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_command_source: str | None = Header(default=None, alias="X-Command-Source"),
):
    # Try JWT authorization first if auth is enabled
    if config.auth_enabled:
        authorized, denial_reason, jwt_user = _authorize_jwt_request(
            http_request,
            Permission.QUEUE_DRAIN,
        )
        if not authorized:
            _audit_jwt_request(
                run_id="system",
                action="queue_drain",
                endpoint="/queue/drain",
                authorized=False,
                user=jwt_user,
                reason=denial_reason,
                outcome="denied",
            )
            return _error_response(403, "FORBIDDEN", "Permission denied")

    authorized, denial_reason, principal = _authorize_manual_command(
        x_operator_key,
        x_operator_role,
        x_command_source,
        required_permission=Permission.QUEUE_DRAIN,
    )
    if not authorized:
        _audit_manual_command(
            run_id="system",
            action="queue_drain",
            endpoint="/queue/drain",
            authorized=False,
            principal=principal,
            reason=denial_reason,
            outcome="denied",
        )
        return _error_response(403, "FORBIDDEN", "Operator permission denied")

    records = _drain_queue_once(max_items=request.max_items)

    _audit_manual_command(
        run_id="system",
        action="queue_drain",
        endpoint="/queue/drain",
        authorized=True,
        principal=principal,
        outcome=f"processed:{len(records)}",
    )
    return {"status": "ok", "processed_count": len(records), "records": records}


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(content=METRICS.render_prometheus())


@app.post("/metrics/export", response_model=None)
def export_metrics(
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_command_source: str | None = Header(default=None, alias="X-Command-Source"),
) -> dict[str, Any]:
    """Manually trigger metrics export to configured exporter."""
    # This endpoint requires admin or operator role
    authorized, denial_reason, principal = _authorize_manual_command(
        x_operator_key,
        x_operator_role,
        x_command_source,
        required_permission=Permission.ADMIN_ACCESS,
    )
    if not authorized:
        # Fall back to checking if it's at least operator
        authorized, denial_reason, principal = _authorize_manual_command(
            x_operator_key,
            x_operator_role,
            x_command_source,
            required_permission=Permission.METRICS_READ,
        )
    if not authorized:
        _audit_manual_command(
            run_id="system",
            action="metrics_export",
            endpoint="/metrics/export",
            authorized=False,
            principal=principal,
            reason=denial_reason,
            outcome="denied",
        )
        return _error_response(403, "FORBIDDEN", "Operator permission denied")

    # Import here to avoid circular imports
    try:
        from scheduler.jobs.metrics_exporter import trigger_metrics_export

        result = trigger_metrics_export()
        _audit_manual_command(
            run_id="system",
            action="metrics_export",
            endpoint="/metrics/export",
            authorized=True,
            principal=principal,
            outcome=result.get("status"),
        )
        return result
    except ImportError:
        return {"status": "error", "message": "Metrics exporter not available"}


@app.get("/cron/jobs")
def list_cron_jobs() -> dict[str, Any]:
    dispatcher = _get_cron_dispatcher()
    items = [
        {
            "name": job.name,
            "interval_seconds": job.interval_seconds,
            "enabled": job.enabled,
            "default_payload": job.default_payload,
            "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        }
        for job in dispatcher.jobs.values()
    ]
    return {"items": items, "count": len(items)}


@app.post("/cron/run-due", response_model=None)
def run_due_cron_jobs(
    http_request: Request,
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_command_source: str | None = Header(default=None, alias="X-Command-Source"),
) -> Any:
    # Try JWT authorization first if auth is enabled
    if config.auth_enabled:
        authorized, denial_reason, jwt_user = _authorize_jwt_request(
            http_request,
            Permission.CRON_TRIGGER,
        )
        if not authorized:
            _audit_jwt_request(
                run_id="system",
                action="cron_run_due",
                endpoint="/cron/run-due",
                authorized=False,
                user=jwt_user,
                reason=denial_reason,
                outcome="denied",
            )
            return _error_response(403, "FORBIDDEN", "Permission denied")

    authorized, denial_reason, principal = _authorize_manual_command(
        x_operator_key,
        x_operator_role,
        x_command_source,
        required_permission=Permission.CRON_TRIGGER,
    )
    if not authorized:
        _audit_manual_command(
            run_id="system",
            action="cron_run_due",
            endpoint="/cron/run-due",
            authorized=False,
            principal=principal,
            reason=denial_reason,
            outcome="denied",
        )
        return _error_response(403, "FORBIDDEN", "Operator permission denied")

    records = _get_cron_dispatcher().run_due_jobs()
    _audit_manual_command(
        run_id="system",
        action="cron_run_due",
        endpoint="/cron/run-due",
        authorized=True,
        principal=principal,
        outcome="executed",
    )
    return {"status": "ok", "triggered_count": len(records), "records": records}


@app.post("/cron/jobs/{job_name}/trigger", response_model=None)
def trigger_cron_job(
    http_request: Request,
    job_name: str,
    request: CronManualTriggerRequest,
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_command_source: str | None = Header(default=None, alias="X-Command-Source"),
) -> Any:
    # Try JWT authorization first if auth is enabled
    if config.auth_enabled:
        authorized, denial_reason, jwt_user = _authorize_jwt_request(
            http_request,
            Permission.CRON_TRIGGER,
        )
        if not authorized:
            _audit_jwt_request(
                run_id=f"cron:{job_name}",
                action="cron_trigger_job",
                endpoint=f"/cron/jobs/{job_name}/trigger",
                authorized=False,
                user=jwt_user,
                reason=denial_reason,
                outcome="denied",
            )
            return _error_response(403, "FORBIDDEN", "Permission denied")

    authorized, denial_reason, principal = _authorize_manual_command(
        x_operator_key,
        x_operator_role,
        x_command_source,
        required_permission=Permission.CRON_TRIGGER,
    )
    if not authorized:
        _audit_manual_command(
            run_id=f"cron:{job_name}",
            action="cron_trigger_job",
            endpoint=f"/cron/jobs/{job_name}/trigger",
            authorized=False,
            principal=principal,
            reason=denial_reason,
            outcome="denied",
        )
        return _error_response(403, "FORBIDDEN", "Operator permission denied")

    try:
        record = _get_cron_dispatcher().trigger_job(job_name, payload=request.payload)
    except KeyError:
        _audit_manual_command(
            run_id=f"cron:{job_name}",
            action="cron_trigger_job",
            endpoint=f"/cron/jobs/{job_name}/trigger",
            authorized=True,
            principal=principal,
            outcome="job_not_found",
        )
        return _error_response(404, "CRON_JOB_NOT_FOUND", f"Unknown cron job: {job_name}")
    _audit_manual_command(
        run_id=f"cron:{job_name}",
        action="cron_trigger_job",
        endpoint=f"/cron/jobs/{job_name}/trigger",
        authorized=True,
        principal=principal,
        outcome=record.get("status"),
    )
    return {"status": "triggered", "record": record}


@app.get("/runs")
def list_runs(
    run_id: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    pipeline_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    normalized_tenant_id = (
        normalize_tenant_id(
            tenant_id,
            default_tenant_id=config.default_tenant_id,
        )
        if tenant_id is not None
        else None
    )
    runs = RUN_REPOSITORY.list(
        run_id=run_id,
        tenant_id=normalized_tenant_id,
        pipeline_name=pipeline_name,
        status=status,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    return {
        "items": [_to_payload(item) for item in runs],
        "offset": offset,
        "limit": limit,
        "count": len(runs),
    }


@app.get("/runs/{run_id}", response_model=None)
def get_run(run_id: str, tenant_id: str | None = Query(default=None)):
    normalized_tenant_id = (
        normalize_tenant_id(
            tenant_id,
            default_tenant_id=config.default_tenant_id,
        )
        if tenant_id is not None
        else None
    )
    run_record = RUN_REPOSITORY.get(run_id, tenant_id=normalized_tenant_id)
    if run_record is not None:
        payload = _to_payload(run_record)
        RUNS[run_id] = payload
        return payload

    run_record_legacy = RUNS.get(run_id)
    if run_record_legacy:
        if normalized_tenant_id is not None:
            legacy_tenant = normalize_tenant_id(
                run_record_legacy.get("tenant_id"),
                default_tenant_id=config.default_tenant_id,
            )
            if legacy_tenant != normalized_tenant_id:
                return _error_response(
                    404,
                    "RUN_NOT_FOUND",
                    f"Run not found: {run_id}",
                    run_id=run_id,
                )
        return redact_sensitive_data(run_record_legacy)
    return _error_response(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", run_id=run_id)


@app.post("/runs/{run_id}/override")
def override_run(
    http_request: Request,
    run_id: str,
    command: OverrideCommand,
    x_operator_key: str | None = Header(default=None, alias="X-Operator-Key"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
    x_command_source: str | None = Header(default=None, alias="X-Command-Source"),
):
    action = command.action.strip().lower()
    reason = command.reason.strip()

    # Try JWT authorization first if auth is enabled
    if config.auth_enabled:
        authorized, denial_reason, jwt_user = _authorize_jwt_request(
            http_request,
            Permission.OVERRIDE_EXECUTE,
        )
        if not authorized:
            _audit_jwt_request(
                run_id=run_id,
                action=action or "unknown",
                endpoint=f"/runs/{run_id}/override",
                authorized=False,
                user=jwt_user,
                reason=denial_reason,
                outcome="denied",
            )
            return _error_response(403, "FORBIDDEN", "Permission denied", run_id=run_id)

    authorized, denial_reason, principal = _authorize_manual_command(
        x_operator_key,
        x_operator_role,
        x_command_source,
        required_permission=Permission.OVERRIDE_EXECUTE,
    )
    if not authorized:
        _audit_manual_command(
            run_id=run_id,
            action=action or "unknown",
            endpoint=f"/runs/{run_id}/override",
            authorized=False,
            principal=principal,
            reason=denial_reason,
            outcome="denied",
        )
        return _error_response(403, "FORBIDDEN", "Operator permission denied", run_id=run_id)

    record = RUN_REPOSITORY.get(run_id)
    if record is None:
        _audit_manual_command(
            run_id=run_id,
            action=action or "unknown",
            endpoint=f"/runs/{run_id}/override",
            authorized=True,
            principal=principal,
            outcome="run_not_found",
        )
        return _error_response(404, "RUN_NOT_FOUND", f"Run not found: {run_id}", run_id=run_id)

    _log_event(
        logging.INFO,
        run_id,
        "override_requested",
        action=action,
        reason=reason,
        operator_authorized=True,
        operator_role=principal.role if principal else None,
        command_source=principal.source if principal else None,
    )

    if action == "explain":
        _audit_manual_command(
            run_id=run_id,
            action=action,
            endpoint=f"/runs/{run_id}/override",
            authorized=True,
            principal=principal,
            outcome="explained",
        )
        return {
            "run_id": run_id,
            "status": record.status,
            "override_state": record.override_state,
            "allowed_actions": ["stop", "retry", "resume", "explain"],
            "summary": record.result.get("summary") if isinstance(record.result, dict) else None,
        }

    if action == "stop":
        if record.status != "RUNNING":
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                outcome="invalid_state",
            )
            return _error_response(
                409,
                "INVALID_OVERRIDE_STATE",
                "Stop is allowed only for RUNNING runs.",
                run_id=run_id,
            )
        RUN_OVERRIDE_REGISTRY.set(run_id, "stop", reason)
        record.override_state = "STOPPED"
        record.status = "BLOCKED"
        record.error = reason or "Stopped by operator."
        record.finished_at = _utc_now_iso()
        RUN_REPOSITORY.upsert(record)
        RUNS[run_id] = record.to_dict()
        _audit_manual_command(
            run_id=run_id,
            action=action,
            endpoint=f"/runs/{run_id}/override",
            authorized=True,
            principal=principal,
            outcome="stopped",
        )
        return {
            "status": "accepted",
            "run_id": run_id,
            "action": action,
            "override_state": record.override_state,
        }

    if action in {"retry", "resume"}:
        if action == "retry" and record.status not in {"FAILED", "BLOCKED"}:
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                outcome="invalid_state",
            )
            return _error_response(
                400,
                "INVALID_OVERRIDE_STATE",
                "Retry is allowed only for FAILED/BLOCKED runs.",
                run_id=run_id,
            )
        if action == "resume" and record.status != "BLOCKED":
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                outcome="invalid_state",
            )
            return _error_response(
                400,
                "INVALID_OVERRIDE_STATE",
                "Resume is allowed only for BLOCKED runs.",
                run_id=run_id,
            )

        result_payload = record.result if isinstance(record.result, dict) else {}
        resume_run_state = result_payload.get("run_state")
        resume_step_results = result_payload.get("steps")
        if not isinstance(resume_run_state, dict) or not isinstance(resume_step_results, dict):
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                outcome="resume_context_missing",
            )
            return _error_response(
                409,
                "INVALID_OVERRIDE_STATE",
                "Run cannot be resumed/retried because persisted step state is unavailable.",
                run_id=run_id,
            )

        RUN_OVERRIDE_REGISTRY.clear(run_id)
        record.override_state = "RESUMED" if action == "resume" else "RETRYING"
        record.status = "RUNNING"
        record.error = None
        record.finished_at = None
        RUN_REPOSITORY.upsert(record)
        runtime_inputs = _resolve_runtime_inputs(record)
        correlation_id = str(uuid4())
        record.correlation_id = correlation_id
        METRICS.mark_run_started()
        _log_event(
            logging.INFO,
            run_id,
            "override_execution_started",
            action=action,
            correlation_id=correlation_id,
            override_state=record.override_state,
        )

        def _on_override_checkpoint(payload: dict[str, Any]) -> None:
            if not isinstance(payload, dict):
                return
            record.result = _sanitize_run_result(payload)
            checkpoint = payload.get("checkpoint")
            record.checkpoint_state = checkpoint if isinstance(checkpoint, dict) else None
            record.status = str(payload.get("status") or "RUNNING")
            RUN_REPOSITORY.upsert(record)
            _persist_step_and_artifact_logs(record)

        try:
            result = engine.run(
                record.pipeline_name,
                runtime_inputs,
                run_id=record.run_id,
                metadata={
                    "source": "override",
                    "correlation_id": correlation_id,
                    "tenant_id": record.tenant_id,
                    "repository_full_name": record.repository_full_name,
                    "__checkpoint_callback": _on_override_checkpoint,
                },
                resume_run_state=resume_run_state,
                resume_step_results=resume_step_results,
            )
            record.result = _sanitize_run_result(result)
            record.status = record.result.get("status", "UNKNOWN")
            record.finished_at = _utc_now_iso()
            RUN_REPOSITORY.upsert(record)
            _persist_step_and_artifact_logs(record)
            METRICS.observe_run_result(record.result)
            if record.status not in {"FAILED", "BLOCKED"}:
                RUN_RUNTIME_INPUTS.pop(run_id, None)
            if record.status in {"FAILED", "BLOCKED"}:
                ALERT_DISPATCHER.alert_run_failure(
                    run_id=record.run_id,
                    pipeline_name=record.pipeline_name,
                    status=record.status,
                    correlation_id=record.correlation_id,
                    error=record.error,
                )
        except ValueError as exc:
            record.status = "FAILED"
            record.error = str(exc)
            record.finished_at = _utc_now_iso()
            RUN_REPOSITORY.upsert(record)
            METRICS.observe_run_result({"status": "FAILED", "summary": {}})
            ALERT_DISPATCHER.alert_run_failure(
                run_id=record.run_id,
                pipeline_name=record.pipeline_name,
                status=record.status,
                correlation_id=record.correlation_id,
                error=record.error,
            )
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                reason=str(exc),
                outcome="failed",
            )
            return _error_response(
                400,
                "INVALID_OVERRIDE_STATE",
                str(exc),
                run_id=run_id,
            )
        except Exception as exc:  # noqa: BLE001
            record.status = "FAILED"
            record.error = str(exc)
            record.finished_at = _utc_now_iso()
            RUN_REPOSITORY.upsert(record)
            METRICS.observe_run_result({"status": "FAILED", "summary": {}})
            ALERT_DISPATCHER.alert_run_failure(
                run_id=record.run_id,
                pipeline_name=record.pipeline_name,
                status=record.status,
                correlation_id=record.correlation_id,
                error=record.error,
            )
            _audit_manual_command(
                run_id=run_id,
                action=action,
                endpoint=f"/runs/{run_id}/override",
                authorized=True,
                principal=principal,
                reason=str(exc),
                outcome="failed",
            )
            return _error_response(
                500,
                "PIPELINE_EXECUTION_FAILED",
                "Pipeline execution failed",
                run_id=run_id,
            )

        RUNS[run_id] = record.to_dict()
        _audit_manual_command(
            run_id=run_id,
            action=action,
            endpoint=f"/runs/{run_id}/override",
            authorized=True,
            principal=principal,
            outcome=f"completed:{record.status}",
        )
        return {
            "status": "accepted",
            "run_id": run_id,
            "action": action,
            "override_state": record.override_state,
            "final_status": record.status,
            "result": record.result,
        }

    _audit_manual_command(
        run_id=run_id,
        action=action or "unknown",
        endpoint=f"/runs/{run_id}/override",
        authorized=True,
        principal=principal,
        outcome="unsupported_action",
    )
    return _error_response(
        400, "INVALID_OVERRIDE_ACTION", f"Unsupported action: {action}", run_id=run_id
    )

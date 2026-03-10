from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from api.event_router import route_github_event
from api.security import verify_github_signature
from hordeforge_config import RunConfig
from logging_utils import redact_mapping
from scheduler.gateway import PipelineRequest, run_pipeline
from scheduler.idempotency import build_idempotency_key

app = FastAPI(title="HordeForge Webhook API", version="0.1.0")
config = RunConfig.from_env()
logger = logging.getLogger("hordeforge.webhook_api")

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(level: int, event: str, **fields: Any) -> None:
    safe_fields = redact_mapping(fields)
    run_id = safe_fields.pop("run_id", None)
    correlation_id = safe_fields.pop("correlation_id", None)
    step = safe_fields.pop("step", safe_fields.pop("step_name", None))
    payload = {
        "timestamp": _utc_now_iso(),
        "level": logging.getLevelName(level),
        "component": "webhook_api",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "step": step,
        "event": event,
        **safe_fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/github", response_model=None)
async def github_webhook(request: Request) -> Any:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    correlation_id = request.headers.get("X-GitHub-Delivery") or str(uuid4())

    if not verify_github_signature(config.webhook_secret, signature, raw_body):
        _log_event(
            logging.WARNING,
            "webhook_signature_rejected",
            event_type=event_type,
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook JSON body must be an object")

    decision = route_github_event(event_type, payload)
    if decision.ignored:
        _log_event(
            logging.INFO,
            "webhook_event_ignored",
            event_type=event_type,
            correlation_id=correlation_id,
            reason=decision.reason,
        )
        return {
            "status": "ignored",
            "event_type": event_type,
            "correlation_id": correlation_id,
            "reason": decision.reason,
        }

    trigger_request = PipelineRequest(
        pipeline_name=str(decision.pipeline_name),
        inputs=decision.inputs,
        source="webhook",
        correlation_id=correlation_id,
        idempotency_key=build_idempotency_key(
            source=f"webhook:{event_type}:{correlation_id}",
            pipeline_name=str(decision.pipeline_name),
            payload=decision.inputs,
        ),
    )
    trigger_result = run_pipeline(trigger_request)
    if isinstance(trigger_result, JSONResponse):
        return trigger_result

    _log_event(
        logging.INFO,
        "webhook_event_accepted",
        event_type=event_type,
        correlation_id=correlation_id,
        pipeline_name=decision.pipeline_name,
        run_id=trigger_result.get("run_id"),
    )
    return {
        "status": "accepted",
        "event_type": event_type,
        "pipeline_name": decision.pipeline_name,
        "correlation_id": correlation_id,
        "trigger_result": trigger_result,
    }

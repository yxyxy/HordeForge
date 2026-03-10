from __future__ import annotations

import argparse
import json
from typing import Any

from hordeforge_config import HordeForgeConfig
from scheduler.cron_runtime import build_job_registry
from scheduler.schedule_registry import build_schedule_registry


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger a scheduler job manually.")
    parser.add_argument("--job", required=True, help="Job name (cron scheduler).")
    parser.add_argument(
        "--payload",
        help="JSON payload for the job inputs",
        default="{}",
    )
    return parser.parse_args()


def _load_payload(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge_defaults(job_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    schedule_registry = build_schedule_registry()
    spec = schedule_registry.get(job_name)
    defaults = spec.default_inputs if spec else {}
    merged = dict(defaults)
    merged.update(payload)
    return merged


def main() -> int:
    args = _parse_args()
    config = HordeForgeConfig.load()
    job_registry = build_job_registry(config)
    handler = job_registry.get(args.job)
    if handler is None:
        raise SystemExit(f"Unknown job: {args.job}")
    payload = _merge_defaults(args.job, _load_payload(args.payload))
    result = handler(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from typing import Any


def _version_to_tuple(value: str) -> tuple[int, ...]:
    raw_parts = [part for part in value.replace("-", ".").split(".") if part]
    parsed: list[int] = []
    for part in raw_parts:
        digits = "".join(ch for ch in part if ch.isdigit())
        parsed.append(int(digits) if digits else 0)
    return tuple(parsed or [0])


class DependencyCheckerJob:
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        deps = payload.get("dependencies", [])
        critical_only = bool(payload.get("critical_only", False))
        if not isinstance(deps, list):
            deps = []

        findings: list[dict[str, Any]] = []
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            name = str(dep.get("name", "")).strip()
            current = str(dep.get("current_version", "")).strip()
            latest = str(dep.get("latest_version", "")).strip()
            severity = str(dep.get("severity", "medium")).lower()
            if not name or not current or not latest:
                continue
            if _version_to_tuple(latest) <= _version_to_tuple(current):
                continue
            if critical_only and severity not in {"critical", "high"}:
                continue
            findings.append(
                {
                    "name": name,
                    "current_version": current,
                    "latest_version": latest,
                    "severity": severity,
                    "risk_score": 3 if severity == "critical" else 2 if severity == "high" else 1,
                }
            )

        triggers = [
            {
                "pipeline_name": "dependency_check_pipeline",
                "inputs": {"dependency": finding},
                "idempotency_key": f"dependency_checker:{finding['name']}:{finding['latest_version']}",
            }
            for finding in findings
        ]

        return {
            "status": "SUCCESS",
            "checked": len(deps),
            "findings_count": len(findings),
            "findings": findings,
            "triggers": triggers,
        }

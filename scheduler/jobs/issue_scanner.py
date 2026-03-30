from __future__ import annotations

from typing import Any


class IssueScannerJob:
    def __init__(self) -> None:
        self._processed_issue_ids: set[int] = set()

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        labels_filter = set(
            payload.get(
                "labels",
                ["agent:opened", "agent:planning", "agent:ready", "agent:fixed"],
            )
        )
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            issues = []

        triggers: list[dict[str, Any]] = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_id = issue.get("id")
            if not isinstance(issue_id, int) or issue_id in self._processed_issue_ids:
                continue
            labels = issue.get("labels", [])
            label_names = {
                str(item.get("name")).strip()
                for item in labels
                if isinstance(item, dict) and item.get("name")
            }
            if labels_filter and label_names.isdisjoint(labels_filter):
                continue

            self._processed_issue_ids.add(issue_id)
            triggers.append(
                {
                    "pipeline_name": "issue_scanner_pipeline",
                    "inputs": {"issue": issue},
                    "idempotency_key": f"issue_scanner:{issue_id}",
                }
            )

        return {
            "status": "SUCCESS",
            "scanned": len(issues),
            "trigger_count": len(triggers),
            "triggers": triggers,
        }

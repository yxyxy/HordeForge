from __future__ import annotations

import json
from typing import Any

from orchestrator.status import StepStatus


def normalize_agent_output(output: dict[str, Any]) -> dict[str, Any]:
    """Normalize agent output to ensure required keys are present with correct types."""
    allowed_keys = {
        "status",
        "artifacts",
        "decisions",
        "logs",
        "next_actions",
        "validation_errors",
        "test_results",
        "schema_version",
    }

    normalized = {}
    for key in allowed_keys:
        if key in output:
            normalized[key] = output[key]

    if "status" not in normalized:
        normalized["status"] = output.get("status", "FAILED")

    if "artifacts" not in normalized:
        normalized["artifacts"] = output.get("artifacts", [])

    if "decisions" not in normalized:
        normalized["decisions"] = output.get("decisions", [])

    if "logs" not in normalized:
        normalized["logs"] = output.get("logs", [])

    if "next_actions" not in normalized:
        normalized["next_actions"] = output.get("next_actions", [])

    return normalized


def coerce_decisions_for_validation(decisions: Any) -> Any:
    """Coerce decisions into a normalized list format for schema validation."""
    if not isinstance(decisions, list):
        return decisions

    normalized_decisions: list[dict[str, Any]] = []
    for item in decisions:
        if isinstance(item, dict):
            reason = item.get("reason")
            confidence = item.get("confidence")
            if not isinstance(reason, str) or not reason.strip():
                reason = str(reason) if reason is not None else str(item)
            if not isinstance(confidence, (int, float)):
                confidence = 0.5
            confidence = max(0.0, min(float(confidence), 1.0))
            normalized_decisions.append({"reason": reason, "confidence": confidence})
            continue

        if isinstance(item, str):
            normalized_decisions.append({"reason": item, "confidence": 0.5})
            continue

        normalized_decisions.append({"reason": str(item), "confidence": 0.5})

    return normalized_decisions


def coerce_code_patch_content_for_validation(content: Any) -> dict[str, Any]:
    """Coerce code patch content into a normalized dict for schema validation."""
    content_dict = content if isinstance(content, dict) else {}

    def _normalize_file_entries(raw_files: Any) -> list[dict[str, Any]]:
        normalized_entries: list[dict[str, Any]] = []
        if not isinstance(raw_files, list):
            return normalized_entries

        for item in raw_files:
            if not isinstance(item, dict):
                normalized_entries.append({"path": "unknown_path", "diff": "# modify"})
                continue

            path_value = item.get("path")
            path = str(path_value).strip() if path_value else "unknown_path"
            content_value = item.get("content")
            change_type = str(item.get("change_type") or "modify").strip().lower() or "modify"
            diff = item.get("diff")

            normalized_file: dict[str, Any] = {
                "path": path,
                "change_type": change_type,
            }

            if isinstance(content_value, str):
                normalized_file["content"] = content_value

            if isinstance(diff, str) and diff.strip():
                normalized_file["diff"] = diff
                normalized_entries.append(normalized_file)
                continue

            if isinstance(content_value, str) and content_value.strip():
                generated_diff = f"# {change_type}\n{content_value}"
            elif content_value is None:
                generated_diff = f"# {change_type}"
            else:
                generated_diff = f"# {change_type}\n{json.dumps(content_value, ensure_ascii=False)}"

            normalized_file["diff"] = generated_diff or "# modify"
            normalized_entries.append(normalized_file)

        return normalized_entries

    schema_version = str(content_dict.get("schema_version", "1.0")).strip()
    if schema_version not in {"1.0", "2.0"}:
        schema_version = "1.0"

    normalized_files = _normalize_file_entries(content_dict.get("files"))
    normalized_test_changes = _normalize_file_entries(content_dict.get("test_changes"))
    has_runtime_patch_fields = (
        bool(str(content_dict.get("patch_text", "") or "").strip())
        or (
            isinstance(content_dict.get("operations"), list)
            and bool(content_dict.get("operations"))
        )
        or (
            isinstance(content_dict.get("test_operations"), list)
            and bool(content_dict.get("test_operations"))
        )
        or bool(normalized_test_changes)
    )

    if not normalized_files and not has_runtime_patch_fields:
        normalized_files = [{"path": "unknown_path", "diff": "# modify"}]

    normalized_content: dict[str, Any] = {
        "schema_version": schema_version,
    }
    if normalized_files:
        normalized_content["files"] = normalized_files
    if normalized_test_changes:
        normalized_content["test_changes"] = normalized_test_changes

    patch_text = content_dict.get("patch_text")
    if isinstance(patch_text, str) and patch_text.strip():
        normalized_content["patch_text"] = patch_text

    operations = content_dict.get("operations")
    if isinstance(operations, list):
        normalized_content["operations"] = operations

    test_operations = content_dict.get("test_operations")
    if isinstance(test_operations, list):
        normalized_content["test_operations"] = test_operations

    decisions = content_dict.get("decisions")
    if isinstance(decisions, list):
        normalized_content["decisions"] = [str(item) for item in decisions]

    dry_run = content_dict.get("dry_run")
    if isinstance(dry_run, bool):
        normalized_content["dry_run"] = dry_run

    for key in ("expected_failures", "fix_iteration", "remaining_failures"):
        value = content_dict.get(key)
        if isinstance(value, int):
            normalized_content[key] = value
        elif value is not None:
            try:
                normalized_content[key] = int(value)
            except (TypeError, ValueError):
                continue

    pr_number = content_dict.get("pr_number")
    if isinstance(pr_number, int):
        normalized_content["pr_number"] = pr_number

    for key in ("pr_url", "branch_name", "apply_error"):
        value = content_dict.get(key)
        if isinstance(value, str) and value.strip():
            normalized_content[key] = value

    for key in ("applied_to_github", "rollback_performed", "llm_enhanced"):
        value = content_dict.get(key)
        if isinstance(value, bool):
            normalized_content[key] = value

    notes = content_dict.get("notes")
    if isinstance(notes, list):
        normalized_content["notes"] = [str(item) for item in notes]

    return normalized_content


def coerce_spec_content_for_validation(content: Any) -> dict[str, Any]:
    """Coerce spec content into a normalized dict for schema validation."""
    if not isinstance(content, dict):
        summary = str(content).strip() if content is not None else ""
        if not summary:
            summary = "Generated specification"
        return {
            "schema_version": "1.0",
            "summary": summary,
            "requirements": ["Define implementation details"],
        }

    summary_candidates = [
        content.get("summary"),
        content.get("feature_description"),
        content.get("title"),
        content.get("user_story"),
    ]
    summary = next(
        (
            str(candidate).strip()
            for candidate in summary_candidates
            if isinstance(candidate, str) and candidate.strip()
        ),
        "Generated specification",
    )

    requirements: list[str] = []
    raw_requirements = content.get("requirements")
    if isinstance(raw_requirements, list):
        for item in raw_requirements:
            if isinstance(item, str) and item.strip():
                requirements.append(item.strip())
            elif isinstance(item, dict):
                for key in ("description", "title", "name"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        requirements.append(value.strip())
                        break

    if not requirements:
        acceptance_criteria = content.get("acceptance_criteria")
        if isinstance(acceptance_criteria, list):
            for item in acceptance_criteria:
                if isinstance(item, str) and item.strip():
                    requirements.append(item.strip())

    if not requirements:
        technical_spec = content.get("technical_specification")
        if isinstance(technical_spec, dict):
            for key in ("components", "implementation_notes", "dependencies"):
                values = technical_spec.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, str) and item.strip():
                            requirements.append(item.strip())

    if not requirements:
        requirements = ["Define implementation details"]

    notes: list[str] = []
    raw_notes = content.get("notes")
    if isinstance(raw_notes, list):
        for item in raw_notes:
            if isinstance(item, str) and item.strip():
                notes.append(item.strip())

    normalized_content: dict[str, Any] = {
        "schema_version": "1.0",
        "summary": summary,
        "requirements": requirements,
    }
    if notes:
        normalized_content["notes"] = notes

    return normalized_content


def coerce_tests_content_for_validation(content: Any) -> dict[str, Any]:
    """Coerce tests content into a normalized dict for schema validation."""
    content_dict = content if isinstance(content, dict) else {}

    normalized_cases: list[dict[str, str]] = []
    raw_cases = content_dict.get("test_cases")
    if isinstance(raw_cases, list):
        for index, case in enumerate(raw_cases, start=1):
            if isinstance(case, dict):
                name = str(case.get("name") or f"test_case_{index}").strip()
                test_type = str(case.get("type") or "unit").strip()
                expected_result = str(case.get("expected_result") or "pass").strip()
            else:
                name = f"test_case_{index}"
                test_type = "unit"
                expected_result = "pass"

            normalized_cases.append(
                {
                    "name": name or f"test_case_{index}",
                    "type": test_type or "unit",
                    "expected_result": expected_result or "pass",
                }
            )

    if not normalized_cases:
        normalized_cases.append(
            {
                "name": "test_feature_baseline",
                "type": "unit",
                "expected_result": "pass",
            }
        )

    schema_version = str(content_dict.get("schema_version", "1.0")).strip()
    if schema_version not in {"1.0", "2.0"}:
        schema_version = "1.0"

    normalized_content: dict[str, Any] = {
        "schema_version": schema_version,
        "test_cases": normalized_cases,
    }

    language = content_dict.get("language")
    if isinstance(language, str):
        normalized_content["language"] = language

    framework = content_dict.get("framework")
    if isinstance(framework, str) or framework is None:
        normalized_content["framework"] = framework

    test_template = content_dict.get("test_template")
    if isinstance(test_template, str) or test_template is None:
        normalized_content["test_template"] = test_template

    test_patterns = content_dict.get("test_patterns")
    if isinstance(test_patterns, dict):
        normalized_content["test_patterns"] = test_patterns

    return normalized_content


def coerce_test_results_for_validation(test_results: Any) -> Any:
    """Coerce test results into a normalized dict for schema validation."""
    if not isinstance(test_results, dict):
        return test_results

    passed_raw = test_results.get("passed")
    failed_raw = test_results.get("failed")
    total_raw = test_results.get("total")

    try:
        passed = int(passed_raw) if passed_raw is not None else 0
    except (TypeError, ValueError):
        passed = 0

    try:
        failed = int(failed_raw) if failed_raw is not None else 0
    except (TypeError, ValueError):
        failed = 0

    if total_raw is None:
        total = max(0, passed + failed)
    else:
        try:
            total = int(total_raw)
        except (TypeError, ValueError):
            total = max(0, passed + failed)

    normalized = {
        "total": max(0, total),
        "passed": max(0, passed),
        "failed": max(0, failed),
    }

    exit_code_raw = test_results.get("exit_code")
    if exit_code_raw is not None:
        try:
            normalized["exit_code"] = int(exit_code_raw)
        except (TypeError, ValueError):
            pass

    failure_signature = test_results.get("failure_signature")
    if isinstance(failure_signature, str) and failure_signature.strip():
        normalized["failure_signature"] = failure_signature.strip()

    mode = test_results.get("mode")
    if isinstance(mode, str) and mode.strip():
        normalized["mode"] = mode

    return normalized


def normalize_step_status(raw_status: str | None) -> StepStatus:
    """Normalize a raw status string to a StepStatus enum value."""
    if raw_status == StepStatus.PARTIAL_SUCCESS.value:
        return StepStatus.PARTIAL_SUCCESS
    if raw_status == StepStatus.SUCCESS.value:
        return StepStatus.SUCCESS
    if raw_status in {item.value for item in StepStatus}:
        return StepStatus(raw_status)
    return StepStatus.FAILED


def error_result(message: str) -> dict[str, Any]:
    """Create a standardized error result dict with FAILED status."""
    return {
        "status": "FAILED",
        "artifacts": [],
        "decisions": [],
        "logs": [message],
        "next_actions": [],
    }

"""Specification Writer Agent - Generates structured specifications with user stories,
acceptance criteria, and technical specs.

Stage-1 improvements:
- stricter prepared-plan validation mode for feature pipeline fail-fast
- stronger DoD usage via normalized input resolution
- quality signals on produced specification artifacts
- consistent build_agent_result usage on all paths
- backward-compatible passthrough / LLM / deterministic modes
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result
from agents.llm_wrapper import build_spec_prompt, get_llm_wrapper, parse_spec_output
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_spec_prompt,
    legacy_parse_spec_output,
)


class SpecificationType(Enum):
    """Types of specifications that can be generated."""

    USER_STORY = "user_story"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    TECHNICAL_SPEC = "technical_spec"
    FILE_CHANGE_PLAN = "file_change_plan"


@dataclass
class UserStory:
    """Represents a user story in the specification."""

    as_a: str
    i_want_to: str
    so_that: str
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class TechnicalSpec:
    """Represents technical specifications."""

    components: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    schemas: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    implementation_notes: list[str] = field(default_factory=list)


@dataclass
class FileChangePlan:
    """Represents a plan for file changes."""

    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_to_delete: list[str] = field(default_factory=list)


REQUIRED_PREPARED_PLAN_FIELDS = (
    "dod",
    "spec",
    "subtasks",
    "bdd_specification",
    "tests",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_str_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _extract_label_names(labels: Any) -> list[str]:
    if not isinstance(labels, list):
        return []

    names: list[str] = []
    for label in labels:
        if isinstance(label, dict):
            name = _normalize_text(label.get("name"))
        else:
            name = _normalize_text(label)
        if name:
            names.append(name)
    return names


def _extract_step_artifact_content(step_result: Any, artifact_type: str) -> dict[str, Any]:
    if not isinstance(step_result, dict):
        return {}

    artifact_content = step_result.get("artifact_content")
    if isinstance(artifact_content, dict) and artifact_content:
        return artifact_content

    artifacts = step_result.get("artifacts", [])
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if artifact.get("type") == artifact_type and isinstance(artifact.get("content"), dict):
                return artifact["content"]

    return {}


def _resolve_context_payload(
    context: dict[str, Any], key: str, step_names: list[str]
) -> dict[str, Any]:
    direct = context.get(key)
    if isinstance(direct, dict) and direct:
        return direct

    for step_name in step_names:
        candidate = _extract_step_artifact_content(context.get(step_name), key)
        if candidate:
            return candidate

    return {}


def _has_meaningful_test_payload(tests: dict[str, Any]) -> bool:
    if not isinstance(tests, dict) or not tests:
        return False

    test_cases = tests.get("test_cases")
    if isinstance(test_cases, list) and test_cases:
        return True

    items = tests.get("items")
    if isinstance(items, list) and items:
        return True

    return bool(
        _normalize_text(tests.get("test_strategy")) or _normalize_text(tests.get("summary"))
    )


def _has_meaningful_subtasks_payload(subtasks: dict[str, Any]) -> bool:
    if not isinstance(subtasks, dict) or not subtasks:
        return False

    items = subtasks.get("items")
    if isinstance(items, list) and items:
        return True

    legacy_subtasks = subtasks.get("subtasks")
    return isinstance(legacy_subtasks, list) and legacy_subtasks


def _has_meaningful_bdd_payload(bdd_specification: dict[str, Any]) -> bool:
    if not isinstance(bdd_specification, dict) or not bdd_specification:
        return False

    if _normalize_text(bdd_specification.get("gherkin_feature")):
        return True

    scenarios = bdd_specification.get("scenarios")
    return isinstance(scenarios, dict) and bool(scenarios)


def _has_meaningful_spec_payload(spec: dict[str, Any]) -> bool:
    if not isinstance(spec, dict) or not spec:
        return False

    return any(
        (
            _normalize_text(spec.get("summary")),
            _normalize_text(spec.get("feature_description")),
            _normalize_text(spec.get("user_story")),
            bool(_coerce_str_list(spec.get("acceptance_criteria"))),
        )
    )


def _has_meaningful_dod_payload(dod: dict[str, Any]) -> bool:
    if not isinstance(dod, dict) or not dod:
        return False

    return any(
        (
            _normalize_text(dod.get("title")),
            _normalize_text(dod.get("feature_description")),
            bool(_coerce_str_list(dod.get("acceptance_criteria"))),
        )
    )


def _detect_spec_mode(issue: dict[str, Any], dod: dict[str, Any], labels: list[str]) -> str:
    title = _normalize_text(issue.get("title"))
    body = _normalize_text(issue.get("body"))
    dod_text = " ".join(
        [
            _normalize_text(dod.get("title")),
            _normalize_text(dod.get("feature_description")),
            " ".join(_coerce_str_list(dod.get("acceptance_criteria"))),
        ]
    )
    combined = f"{title} {body} {dod_text} {' '.join(labels)}".lower()

    if (
        "ci incident" in combined
        or "kind:ci-incident" in combined
        or "source:ci_scanner_pipeline" in combined
    ):
        return "ci_incident"
    if any(token in combined for token in ["bug", "fix", "regression", "failure", "error"]):
        return "bugfix"
    if any(
        token in combined
        for token in ["infra", "config", "deployment", "docker", "pipeline", "workflow"]
    ):
        return "infra"
    if any(token in combined for token in ["docs", "documentation", "readme", "guide"]):
        return "docs"
    return "feature"


def _resolve_spec_input(context: dict[str, Any]) -> dict[str, Any]:
    issue = context.get("issue", {}) if isinstance(context.get("issue"), dict) else {}
    dod = _resolve_context_payload(context, "dod", ["dod_extractor"])
    labels = _extract_label_names(issue.get("labels", []))

    issue_title = _normalize_text(issue.get("title"))
    issue_body = _normalize_text(issue.get("body") or issue.get("description"))
    dod_title = _normalize_text(dod.get("title"))
    dod_feature_description = _normalize_text(dod.get("feature_description"))
    acceptance_criteria = _coerce_str_list(dod.get("acceptance_criteria"))

    feature_description = (
        issue_title
        or issue_body
        or _normalize_text(context.get("feature_description"))
        or dod_title
        or dod_feature_description
        or (acceptance_criteria[0] if acceptance_criteria else "")
    )

    return {
        "issue": issue,
        "dod": dod,
        "labels": labels,
        "issue_title": issue_title,
        "issue_body": issue_body,
        "dod_title": dod_title,
        "acceptance_criteria": acceptance_criteria,
        "feature_description": feature_description,
        "source_text": "\n\n".join(
            part
            for part in [
                issue_title,
                issue_body,
                dod_title,
                dod_feature_description,
                "\n".join(acceptance_criteria),
            ]
            if part
        ),
        "spec_mode": _detect_spec_mode(issue, dod, labels),
    }


def generate_user_story(issue_description: str, spec_mode: str = "feature") -> str | None:
    """Generate a user story from issue description when appropriate."""
    if spec_mode != "feature":
        return None

    issue_lower = issue_description.lower()
    user_context_keywords = [
        "user",
        "customer",
        "admin",
        "manager",
        "employee",
        "client",
        "visitor",
        "member",
        "account",
        "profile",
        "login",
        "register",
    ]
    if not any(keyword in issue_lower for keyword in user_context_keywords):
        return None

    action_indicators = ["add", "implement", "create", "update", "fix", "improve", "enable"]
    action = next(
        (
            word.lower().strip(".,!?")
            for word in issue_description.split()
            if word.lower().strip(".,!?") in action_indicators
        ),
        "implement",
    )

    feature = issue_description
    for verb in ["Add", "Implement", "Create", "Fix", "Update", "Improve"]:
        feature = feature.replace(verb, "")
    feature = feature.split(".")[0].strip() or issue_description

    return f"As a user,\nI want to {action} {feature},\nSo that I can achieve my goals"


def generate_acceptance_criteria(
    user_story: str | None,
    issue_description: str = "",
    seed_criteria: list[str] | None = None,
) -> list[str]:
    """Generate acceptance criteria, preferring upstream DoD criteria."""
    criteria = _coerce_str_list(seed_criteria or [])
    issue_lower = issue_description.lower()

    if not criteria:
        criteria.extend(
            [
                "Feature works as described in the specification",
                "Feature passes all relevant tests",
                "Feature is documented appropriately",
            ]
        )

    if any(word in issue_lower for word in ["api", "endpoint", "service"]):
        criteria.extend(
            [
                "API endpoint returns correct response format",
                "API endpoint handles error cases appropriately",
                "API endpoint validates input parameters",
            ]
        )

    if any(word in issue_lower for word in ["ui", "interface", "form", "page"]):
        criteria.extend(
            [
                "UI renders correctly across supported browsers",
                "UI is responsive and accessible",
                "Form validation works as expected",
            ]
        )

    if any(word in issue_lower for word in ["security", "auth", "authentication", "permission"]):
        criteria.extend(
            [
                "Security measures are properly implemented",
                "Access controls are enforced",
                "Sensitive data is protected",
            ]
        )

    if any(word in issue_lower for word in ["performance", "speed", "load", "scale"]):
        criteria.extend(
            [
                "Performance benchmarks are met",
                "Feature scales appropriately under load",
            ]
        )

    return _coerce_str_list(criteria)


def generate_technical_spec(feature_description: str, spec_mode: str = "feature") -> TechnicalSpec:
    """Generate technical specification for a feature."""
    feature_lower = feature_description.lower()
    components: list[str] = []
    endpoints: list[str] = []
    schemas: list[dict[str, Any]] = []
    dependencies: list[str] = []
    implementation_notes: list[str] = []

    if spec_mode == "ci_incident":
        return TechnicalSpec(
            components=["CI workflow", "Failing job triage", "Targeted fix", "Verification step"],
            dependencies=["ci_provider", "test_runner"],
            implementation_notes=[
                "Focus on reproducing the failure deterministically",
                "Prefer targeted fixes over broad refactors",
                "Rerun only affected checks first",
            ],
        )

    if spec_mode == "bugfix":
        implementation_notes.append("Preserve existing behaviour outside the failing path")
        implementation_notes.append("Add or update regression coverage")

    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        entity = _extract_entity_name(feature_description)
        components.extend(["Controller", "Service Layer", "Data Access Layer"])
        endpoints.append(f"/api/v1/{entity}")
        schemas.append({"name": f"{entity}_request", "fields": ["id", "name", "description"]})
        dependencies.extend(["database", "authentication"])
        implementation_notes.append("Follow RESTful API principles")

    if any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
        components.extend(["UI Component", "State Management", "Styling"])
        dependencies.extend(["frontend_framework", "api_client"])
        implementation_notes.append("Ensure responsive design")

    if any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
        components.extend(["Auth Service", "Token Manager", "Permission Checker"])
        dependencies.extend(["jwt_library", "password_hashing"])
        implementation_notes.extend(
            [
                "Implement secure password hashing",
                "Use proper token expiration",
                "Validate all inputs",
            ]
        )

    if any(word in feature_lower for word in ["test", "testing"]):
        components.extend(["Unit Tests", "Integration Tests", "Test Utilities"])
        dependencies.extend(["testing_framework", "mocking_library"])
        implementation_notes.append("Prefer targeted coverage before broader expansion")

    return TechnicalSpec(
        components=_coerce_str_list(components),
        endpoints=_coerce_str_list(endpoints),
        schemas=schemas,
        dependencies=_coerce_str_list(dependencies),
        implementation_notes=_coerce_str_list(implementation_notes),
    )


def generate_file_change_plan(
    feature_description: str,
    project_structure: dict[str, Any] | None = None,
    spec_mode: str = "feature",
) -> FileChangePlan:
    """Generate a file change plan for the feature."""
    feature_lower = feature_description.lower()
    files_to_create: list[str] = []
    files_to_modify: list[str] = []
    files_to_delete: list[str] = []

    if spec_mode == "ci_incident":
        files_to_modify.extend([".github/workflows/", "tests/", "src/"])
        return FileChangePlan(
            files_to_create=[], files_to_modify=files_to_modify, files_to_delete=[]
        )

    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.extend(
            [
                f"api/v1/{entity_name}.py",
                f"api/v1/schemas/{entity_name}.py",
                f"tests/api/v1/test_{entity_name}.py",
            ]
        )
        files_to_modify.append("api/v1/routes.py")

    if any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.extend(
            [f"ui/components/{entity_name}_form.jsx", f"ui/styles/{entity_name}_form.css"]
        )
        files_to_modify.append("ui/components/index.js")

    if any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
        files_to_create.extend(
            ["auth/service.py", "auth/schemas.py", "auth/utils.py", "tests/auth/test_service.py"]
        )
        files_to_modify.extend(["auth/__init__.py", "config/settings.py"])

    if any(word in feature_lower for word in ["test", "testing"]):
        entity_name = _extract_entity_name(feature_description)
        files_to_create.append(f"tests/unit/test_{entity_name}.py")

    if project_structure and isinstance(project_structure, dict):
        existing_files = set(project_structure.get("files", []))
        final_create: list[str] = []
        final_modify: list[str] = []

        for file_path in files_to_create:
            if file_path in existing_files:
                final_modify.append(file_path)
            else:
                final_create.append(file_path)

        for file_path in files_to_modify:
            if file_path in existing_files:
                final_modify.append(file_path)
            else:
                final_create.append(file_path)

        files_to_create = final_create
        files_to_modify = final_modify

    return FileChangePlan(
        files_to_create=_coerce_str_list(files_to_create),
        files_to_modify=_coerce_str_list(files_to_modify),
        files_to_delete=_coerce_str_list(files_to_delete),
    )


def _extract_entity_name(feature_description: str) -> str:
    """Extract entity name from feature description for file naming."""
    words = feature_description.lower().split()
    verbs = ["add", "implement", "create", "update", "modify", "delete", "manage", "fix"]

    for index, word in enumerate(words):
        if word in verbs and index + 1 < len(words):
            entity = re.sub(
                r"(feature|functionality|module|system|service|endpoint|api)$",
                "",
                words[index + 1],
            ).strip()
            if entity:
                return re.sub(r"[^\w]", "_", entity)

    for word in words:
        if word not in verbs and len(word) > 2:
            return re.sub(r"[^\w]", "_", word)

    return "feature"


def _build_quality_signals(spec_content: dict[str, Any]) -> dict[str, Any]:
    acceptance_criteria = _coerce_str_list(spec_content.get("acceptance_criteria"))
    technical_specification = spec_content.get("technical_specification", {})
    file_change_plan = spec_content.get("file_change_plan", {})

    has_technical_spec = isinstance(technical_specification, dict) and any(
        technical_specification.get(key)
        for key in ["components", "endpoints", "schemas", "dependencies"]
    )
    has_file_change_plan = isinstance(file_change_plan, dict) and any(
        file_change_plan.get(key)
        for key in ["files_to_create", "files_to_modify", "files_to_delete"]
    )

    completeness_score = 0
    if _normalize_text(spec_content.get("feature_description")):
        completeness_score += 1
    if _normalize_text(spec_content.get("user_story")):
        completeness_score += 1
    if acceptance_criteria:
        completeness_score += 1
    if has_technical_spec:
        completeness_score += 1
    if has_file_change_plan:
        completeness_score += 1

    completeness = "low"
    if completeness_score >= 4:
        completeness = "high"
    elif completeness_score >= 2:
        completeness = "medium"

    return {
        "has_user_story": bool(_normalize_text(spec_content.get("user_story"))),
        "acceptance_criteria_count": len(acceptance_criteria),
        "has_technical_spec": has_technical_spec,
        "has_file_change_plan": has_file_change_plan,
        "spec_completeness": completeness,
    }


class SpecificationWriter(BaseAgent):
    """Generates structured specifications with user stories, acceptance criteria, and technical specs."""

    name = "specification_writer"
    description = "Generates structured specifications with user stories, acceptance criteria, and technical specs."

    def _validate_prepared_plan(self, context: dict[str, Any]) -> dict:
        dod = _resolve_context_payload(context, "dod", ["dod_extractor"])
        spec = _resolve_context_payload(context, "spec", ["specification_writer"])
        subtasks = _resolve_context_payload(context, "subtasks", ["task_decomposer"])
        bdd_specification = _resolve_context_payload(
            context, "bdd_specification", ["bdd_generator"]
        )
        tests = _resolve_context_payload(context, "tests", ["test_generator"])

        missing_fields: list[str] = []
        invalid_fields: list[str] = []

        field_values = {
            "dod": dod,
            "spec": spec,
            "subtasks": subtasks,
            "bdd_specification": bdd_specification,
            "tests": tests,
        }

        validators = {
            "dod": _has_meaningful_dod_payload,
            "spec": _has_meaningful_spec_payload,
            "subtasks": _has_meaningful_subtasks_payload,
            "bdd_specification": _has_meaningful_bdd_payload,
            "tests": _has_meaningful_test_payload,
        }

        for field_name in REQUIRED_PREPARED_PLAN_FIELDS:
            value = field_values[field_name]
            if not isinstance(value, dict) or not value:
                missing_fields.append(field_name)
                continue
            if not validators[field_name](value):
                invalid_fields.append(field_name)

        blocked_reasons: list[str] = []
        if missing_fields:
            blocked_reasons.append(f"missing fields: {', '.join(missing_fields)}")
        if invalid_fields:
            blocked_reasons.append(f"incomplete fields: {', '.join(invalid_fields)}")

        artifact_content = {
            "schema_version": "1.0",
            "planning_artifacts_present": not missing_fields,
            "plan_complete": not missing_fields and not invalid_fields,
            "plan_source": context.get("plan_source", "prepared_plan"),
            "dispatch_blocked_reason": "; ".join(blocked_reasons),
            "validated_fields": {
                field_name: field_name not in missing_fields and field_name not in invalid_fields
                for field_name in REQUIRED_PREPARED_PLAN_FIELDS
            },
            "missing_fields": missing_fields,
            "invalid_fields": invalid_fields,
        }

        if artifact_content["plan_complete"]:
            return build_agent_result(
                status="SUCCESS",
                artifact_type="prepared_plan_validation",
                artifact_content=artifact_content,
                reason="Prepared plan validation passed.",
                confidence=0.98,
                logs=[
                    "Prepared plan validator: all required artifacts are present.",
                    f"plan_source={artifact_content['plan_source']}",
                    "plan_complete=true",
                ],
                next_actions=[
                    "specification_passthrough",
                    "subtasks_passthrough",
                    "bdd_passthrough",
                    "tests_passthrough",
                ],
            )

        return build_agent_result(
            status="BLOCKED",
            artifact_type="prepared_plan_validation",
            artifact_content=artifact_content,
            reason="Prepared plan validation failed.",
            confidence=0.99,
            logs=[
                "Prepared plan validator blocked execution.",
                f"plan_source={artifact_content['plan_source']}",
                f"dispatch_blocked_reason={artifact_content['dispatch_blocked_reason']}",
            ],
            next_actions=["regenerate_planning_artifacts", "request_human_input"],
        )

    def run(self, context: dict) -> dict:
        if context.get("validate_prepared_plan"):
            return self._validate_prepared_plan(context)

        existing_spec = context.get("spec")
        if isinstance(existing_spec, dict) and _has_meaningful_spec_payload(existing_spec):
            passthrough_content = dict(existing_spec)
            passthrough_content.setdefault(
                "quality_signals", _build_quality_signals(passthrough_content)
            )
            passthrough_content.setdefault(
                "plan_provenance",
                {
                    "source": context.get("plan_source", "upstream_pipeline"),
                    "passthrough": True,
                    "rebuilt": False,
                },
            )
            return build_agent_result(
                status="SUCCESS",
                artifact_type="spec",
                artifact_content=passthrough_content,
                reason="Specification passed through from upstream pipeline.",
                confidence=0.95,
                logs=[
                    "Specification reused from upstream pipeline (passthrough mode).",
                    f"spec_completeness={passthrough_content['quality_signals']['spec_completeness']}",
                ],
                next_actions=["task_decomposer", "bdd_generator", "test_generator"],
            )

        resolved = _resolve_spec_input(context)
        feature_description = resolved["feature_description"]
        if not feature_description:
            return build_agent_result(
                status="FAILED",
                artifact_type="spec",
                artifact_content={},
                reason="No feature description provided in context.",
                confidence=1.0,
                logs=["No feature description found in issue, DoD, or upstream artifacts."],
                next_actions=["dod_extractor", "request_human_input"],
            )

        use_llm = context.get("use_llm", True)
        require_llm = bool(context.get("require_llm", False))
        llm_spec: dict[str, Any] | None = None
        llm_error: str | None = None

        if use_llm:
            try:
                llm = get_llm_wrapper() or get_legacy_llm_wrapper()
                if llm is not None:
                    repo_context = {
                        "feature_description": feature_description,
                        "issue_labels": resolved["labels"],
                        "existing_files": context.get("existing_files", []),
                        "dod_acceptance_criteria": resolved["acceptance_criteria"],
                        "spec_mode": resolved["spec_mode"],
                    }
                    try:
                        prompt = build_spec_prompt(feature_description, [], repo_context)
                    except AttributeError:
                        prompt = legacy_build_spec_prompt(feature_description, [], repo_context)

                    response = llm.complete(prompt)
                    llm.close()
                    try:
                        llm_spec = parse_spec_output(response)
                    except AttributeError:
                        llm_spec = legacy_parse_spec_output(response)
            except Exception as exc:  # pragma: no cover - defensive compatibility path
                llm_error = str(exc)

        if use_llm and require_llm and not llm_spec:
            fallback_draft = self._build_deterministic_spec(context, resolved, llm_error)
            return build_agent_result(
                status="FAILED",
                artifact_type="spec",
                artifact_content={
                    "schema_version": "1.0",
                    "llm_required": True,
                    "llm_error": llm_error,
                    "spec_fallback_draft": fallback_draft,
                },
                reason=(
                    f"LLM required but unavailable: {llm_error[:160]}"
                    if llm_error
                    else "LLM required but no valid specification was produced."
                ),
                confidence=0.98,
                logs=[
                    "LLM strict mode enabled (require_llm=true).",
                    f"LLM error: {llm_error or 'missing_or_invalid_spec_output'}",
                    "Deterministic fallback draft generated for diagnosis.",
                ],
                next_actions=["retry_with_llm", "request_human_input"],
            )

        if llm_spec and isinstance(llm_spec, dict):
            result_content = self._normalize_llm_spec(llm_spec, resolved, context, llm_error)
            reason = "Specification generated successfully using LLM."
            confidence = 0.93
        else:
            result_content = self._build_deterministic_spec(context, resolved, llm_error)
            reason = (
                "Deterministic specification generated (LLM unavailable)."
                if llm_error
                else "Specification generated from normalized issue/DoD input."
            )
            confidence = 0.86

        rules = context.get("rules", {})
        if isinstance(rules, dict) and rules:
            rule_sources = rules.get("sources", [])
            if isinstance(rule_sources, list) and rule_sources:
                result_content.setdefault("requirements", [])
                result_content["requirements"].extend(rule_sources)
            rules_version = _normalize_text(rules.get("version"))
            if rules_version:
                result_content.setdefault("notes", [])
                result_content["notes"].append(f"rules_version={rules_version}")

        result_content["quality_signals"] = _build_quality_signals(result_content)

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="spec",
            artifact_content=result_content,
            reason=reason,
            confidence=confidence,
            logs=[
                f"Generated specification for: {feature_description[:80]}",
                f"spec_mode={resolved['spec_mode']}",
                f"acceptance_criteria={result_content['quality_signals']['acceptance_criteria_count']}",
                f"spec_completeness={result_content['quality_signals']['spec_completeness']}",
            ],
            next_actions=["task_decomposer", "bdd_generator", "test_generator"],
        )
        result["artifact_type"] = "spec"
        result["artifact_content"] = result_content
        return result

    def _build_deterministic_spec(
        self,
        context: dict[str, Any],
        resolved: dict[str, Any],
        llm_error: str | None,
    ) -> dict[str, Any]:
        feature_description = resolved["feature_description"]
        spec_mode = resolved["spec_mode"]
        user_story_text = generate_user_story(feature_description, spec_mode=spec_mode)
        acceptance_criteria = generate_acceptance_criteria(
            user_story_text,
            issue_description=resolved["source_text"],
            seed_criteria=resolved["acceptance_criteria"],
        )
        tech_spec = generate_technical_spec(feature_description, spec_mode=spec_mode)
        project_structure = context.get("project_structure", {})
        file_plan = generate_file_change_plan(
            feature_description,
            project_structure=project_structure if isinstance(project_structure, dict) else {},
            spec_mode=spec_mode,
        )

        result_content = {
            "schema_version": "1.0",
            "summary": resolved["issue_title"] or feature_description,
            "feature_description": feature_description,
            "user_story": user_story_text,
            "acceptance_criteria": acceptance_criteria,
            "technical_specification": {
                "components": tech_spec.components,
                "endpoints": tech_spec.endpoints,
                "schemas": tech_spec.schemas,
                "dependencies": tech_spec.dependencies,
                "implementation_notes": tech_spec.implementation_notes,
            },
            "file_change_plan": {
                "files_to_create": file_plan.files_to_create,
                "files_to_modify": file_plan.files_to_modify,
                "files_to_delete": file_plan.files_to_delete,
            },
            "generation_context": {
                "spec_mode": spec_mode,
                "has_user_context": user_story_text is not None,
                "complexity_estimate": max(1, len(feature_description.split()) // 10 + 1),
                "input_sources": {
                    "issue_title": bool(resolved["issue_title"]),
                    "issue_body": bool(resolved["issue_body"]),
                    "dod": bool(resolved["dod"]),
                    "acceptance_criteria_seed_count": len(resolved["acceptance_criteria"]),
                },
            },
            "plan_provenance": {
                "source": context.get("plan_source", "generated"),
                "passthrough": False,
                "rebuilt": False,
            },
        }

        if spec_mode in {"bugfix", "ci_incident", "infra", "docs"}:
            result_content["problem_statement"] = resolved["source_text"] or feature_description
            result_content["target_outcome"] = (
                "Restore the expected system behaviour with minimal-risk changes."
                if spec_mode in {"bugfix", "ci_incident"}
                else "Implement the requested change safely and predictably."
            )
            result_content["constraints"] = [
                "Prefer minimal, targeted changes",
                "Preserve backward compatibility where possible",
            ]

        if llm_error:
            result_content.setdefault("notes", [])
            result_content["notes"].append(f"llm_error={llm_error[:120]}")

        return result_content

    def _normalize_llm_spec(
        self,
        llm_spec: dict[str, Any],
        resolved: dict[str, Any],
        context: dict[str, Any],
        llm_error: str | None,
    ) -> dict[str, Any]:
        acceptance_criteria = generate_acceptance_criteria(
            llm_spec.get("user_story"),
            issue_description=resolved["source_text"],
            seed_criteria=llm_spec.get("acceptance_criteria") or resolved["acceptance_criteria"],
        )
        technical_specification = llm_spec.get("technical_specification")
        if not isinstance(technical_specification, dict):
            technical_specification = llm_spec.get("technical_spec", {})
        if not isinstance(technical_specification, dict):
            technical_specification = {}

        file_change_plan = llm_spec.get("file_change_plan")
        if not isinstance(file_change_plan, dict):
            deterministic = self._build_deterministic_spec(context, resolved, llm_error)
            file_change_plan = deterministic.get("file_change_plan", {})

        result_content = {
            "schema_version": "1.0",
            "summary": _normalize_text(llm_spec.get("summary"))
            or resolved["issue_title"]
            or resolved["feature_description"],
            "feature_description": _normalize_text(llm_spec.get("feature_description"))
            or resolved["feature_description"],
            "user_story": _normalize_text(llm_spec.get("user_story"))
            or generate_user_story(
                resolved["feature_description"],
                spec_mode=resolved["spec_mode"],
            ),
            "acceptance_criteria": acceptance_criteria,
            "technical_specification": {
                "components": _coerce_str_list(technical_specification.get("components")),
                "endpoints": _coerce_str_list(technical_specification.get("endpoints")),
                "schemas": technical_specification.get("schemas", [])
                if isinstance(technical_specification.get("schemas", []), list)
                else [],
                "dependencies": _coerce_str_list(technical_specification.get("dependencies")),
                "implementation_notes": _coerce_str_list(
                    technical_specification.get("implementation_notes")
                ),
            },
            "file_change_plan": {
                "files_to_create": _coerce_str_list(file_change_plan.get("files_to_create")),
                "files_to_modify": _coerce_str_list(file_change_plan.get("files_to_modify")),
                "files_to_delete": _coerce_str_list(file_change_plan.get("files_to_delete")),
            },
            "generation_context": {
                "spec_mode": resolved["spec_mode"],
                "llm_enhanced": True,
                "complexity_estimate": max(
                    1, len(resolved["feature_description"].split()) // 10 + 1
                ),
            },
            "plan_provenance": {
                "source": context.get("plan_source", "generated"),
                "passthrough": False,
                "rebuilt": False,
            },
        }

        notes = llm_spec.get("notes")
        if isinstance(notes, list) and notes:
            result_content["notes"] = [
                _normalize_text(note) for note in notes if _normalize_text(note)
            ]
        if llm_error:
            result_content.setdefault("notes", []).append(f"llm_error={llm_error[:120]}")

        return result_content


SpecWriter = SpecificationWriter
EnhancedSpecificationWriter = SpecificationWriter

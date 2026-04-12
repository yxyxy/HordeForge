from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from logging_utils import redact_mapping
from orchestrator.context import ExecutionContext
from orchestrator.loader import StepDefinition
from orchestrator.state import PipelineRunState
from orchestrator.status import StepStatus
from orchestrator.validation import RuntimeSchemaValidator
from registry.agents import AgentMetadata, AgentRegistry
from registry.bootstrap import init_registries
from registry.runtime_adapter import RuntimeRegistryAdapter


class StepExecutor:
    def __init__(
        self,
        *,
        agent_registry: RuntimeRegistryAdapter | AgentRegistry | None = None,
        agent_factory: Callable[[str], Any] | None = None,
        schema_validator: RuntimeSchemaValidator | None = None,
        strict_schema_validation: bool = True,
        schema_dir: str = "contracts/schemas",
    ):
        if agent_registry is not None:
            if isinstance(agent_registry, RuntimeRegistryAdapter):
                self.agent_registry = agent_registry
            elif isinstance(agent_registry, AgentRegistry):
                self.agent_registry = RuntimeRegistryAdapter(agent_registry)
            else:
                self.agent_registry = agent_registry
        elif agent_factory is not None:
            base_registry = RuntimeRegistryAdapter(AgentRegistry())
            self.agent_registry = self._create_registry_from_factory(base_registry, agent_factory)
        else:
            registries = init_registries(contracts_dir=schema_dir)
            self.agent_registry = RuntimeRegistryAdapter(registries["agent_registry"])

        self.strict_schema_validation = strict_schema_validation
        self.schema_validator = schema_validator or RuntimeSchemaValidator(
            schema_dir=schema_dir,
            strict_mode=strict_schema_validation,
        )
        self.logger = logging.getLogger("hordeforge.orchestrator.step_executor")

    def _create_registry_from_factory(self, base_registry, factory):
        """Р РЋР С•Р В·Р Т‘Р В°Р ВµРЎвЂљ Р С•Р В±Р ВµРЎР‚РЎвЂљР С”РЎС“ РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚Р В°, Р С”Р С•РЎвЂљР С•РЎР‚РЎвЂ№Р в„– Р С‘РЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р ВµРЎвЂљ РЎвЂћР В°Р В±РЎР‚Р С‘Р С”РЎС“ Р Т‘Р В»РЎРЏ РЎРѓР С•Р В·Р Т‘Р В°Р Р…Р С‘РЎРЏ Р В°Р С–Р ВµР Р…РЎвЂљР С•Р Р†."""

        # Р РЋР С•Р В·Р Т‘Р В°Р ВµР С Р С•Р В±Р ВµРЎР‚РЎвЂљР С”РЎС“ Р Р†Р С•Р С”РЎР‚РЎС“Р С– Р В±Р В°Р В·Р С•Р Р†Р С•Р С–Р С• РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚Р В°, Р С”Р С•РЎвЂљР С•РЎР‚Р В°РЎРЏ Р СР С•Р В¶Р ВµРЎвЂљ Р Т‘Р С‘Р Р…Р В°Р СР С‘РЎвЂЎР ВµРЎРѓР С”Р С‘ РЎР‚Р ВµР С–Р С‘РЎРѓРЎвЂљРЎР‚Р С‘РЎР‚Р С•Р Р†Р В°РЎвЂљРЎРЉ Р В°Р С–Р ВµР Р…РЎвЂљР С•Р Р†
        class DynamicRegistryWrapper:
            def __init__(self, base_reg, factory_func):
                self.base_registry = base_reg
                self.factory = factory_func
                self.dynamic_agents = {}

            def has(self, agent_name: str) -> bool:
                # Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЏР ВµР С РЎРѓР Р…Р В°РЎвЂЎР В°Р В»Р В° Р Р† Р В±Р В°Р В·Р С•Р Р†Р С•Р С РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚Р Вµ, Р В·Р В°РЎвЂљР ВµР С Р С—РЎР‚Р С•Р В±РЎС“Р ВµР С РЎвЂћР В°Р В±РЎР‚Р С‘Р С”РЎС“
                if self.base_registry.has(agent_name):
                    return True

                # Р СџРЎР‚Р С•Р В±РЎС“Р ВµР С РЎРѓР С•Р В·Р Т‘Р В°РЎвЂљРЎРЉ Р В°Р С–Р ВµР Р…РЎвЂљ РЎвЂЎР ВµРЎР‚Р ВµР В· РЎвЂћР В°Р В±РЎР‚Р С‘Р С”РЎС“, РЎвЂЎРЎвЂљР С•Р В±РЎвЂ№ Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚Р С‘РЎвЂљРЎРЉ Р ВµР С–Р С• Р Р…Р В°Р В»Р С‘РЎвЂЎР С‘Р Вµ
                try:
                    agent = self.factory(agent_name)
                    # Р РЋР С•РЎвЂ¦РЎР‚Р В°Р Р…РЎРЏР ВµР С Р В°Р С–Р ВµР Р…РЎвЂљ Р Р†Р С• Р Р†РЎР‚Р ВµР СР ВµР Р…Р Р…РЎвЂ№Р в„– Р С”РЎРЊРЎв‚¬
                    self.dynamic_agents[agent_name] = agent.__class__
                    return True
                except Exception:
                    return False

            def create(self, agent_name: str) -> Any:
                # Р вЂўРЎРѓР В»Р С‘ Р В°Р С–Р ВµР Р…РЎвЂљ Р Р† Р В±Р В°Р В·Р С•Р Р†Р С•Р С РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚Р Вµ - Р С‘РЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р ВµР С Р ВµР С–Р С•
                if self.base_registry.has(agent_name):
                    return self.base_registry.create(agent_name)

                # Р ВР Р…Р В°РЎвЂЎР Вµ РЎРѓР С•Р В·Р Т‘Р В°Р ВµР С РЎвЂЎР ВµРЎР‚Р ВµР В· РЎвЂћР В°Р В±РЎР‚Р С‘Р С”РЎС“ Р С”Р В°Р В¶Р Т‘РЎвЂ№Р в„– РЎР‚Р В°Р В·, РЎвЂЎРЎвЂљР С•Р В±РЎвЂ№ Р С‘Р В·Р В±Р ВµР В¶Р В°РЎвЂљРЎРЉ Р С—РЎР‚Р С•Р В±Р В»Р ВµР С РЎРѓ РЎРѓР С•РЎРѓРЎвЂљР С•РЎРЏР Р…Р С‘Р ВµР С
                agent = self.factory(agent_name)
                return agent

            def get(self, agent_name: str):
                # Р вЂќР В»РЎРЏ РЎРѓР С•Р Р†Р СР ВµРЎРѓРЎвЂљР С‘Р СР С•РЎРѓРЎвЂљР С‘ РЎРѓ Р С‘Р Р…РЎвЂљР ВµРЎР‚РЎвЂћР ВµР в„–РЎРѓР С•Р С AgentRegistry
                if self.base_registry.has(agent_name):
                    item = self.base_registry.get(agent_name)
                    if isinstance(item, AgentMetadata):
                        return item.agent_class
                    return item

                if agent_name in self.dynamic_agents:
                    # Р вЂ™Р С•Р В·Р Р†РЎР‚Р В°РЎвЂ°Р В°Р ВµР С Р С”Р В»Р В°РЎРѓРЎРѓ Р В°Р С–Р ВµР Р…РЎвЂљР В°, Р В° Р Р…Р Вµ РЎРЊР С”Р В·Р ВµР СР С—Р В»РЎРЏРЎР‚
                    return self.dynamic_agents[agent_name]

                # Р вЂўРЎРѓР В»Р С‘ Р В°Р С–Р ВµР Р…РЎвЂљ Р Р…Р Вµ РЎРѓРЎС“РЎвЂ°Р ВµРЎРѓРЎвЂљР Р†РЎС“Р ВµРЎвЂљ, Р С—РЎР‚Р С•Р В±РЎС“Р ВµР С РЎРѓР С•Р В·Р Т‘Р В°РЎвЂљРЎРЉ РЎвЂЎР ВµРЎР‚Р ВµР В· РЎвЂћР В°Р В±РЎР‚Р С‘Р С”РЎС“
                try:
                    agent = self.factory(agent_name)
                    self.dynamic_agents[agent_name] = agent.__class__
                    return agent.__class__
                except Exception:
                    # Р вЂўРЎРѓР В»Р С‘ Р В°Р С–Р ВµР Р…РЎвЂљ Р Р…Р Вµ РЎРѓРЎС“РЎвЂ°Р ВµРЎРѓРЎвЂљР Р†РЎС“Р ВµРЎвЂљ, Р Р†РЎвЂ№Р В·РЎвЂ№Р Р†Р В°Р ВµР С Р С‘РЎРѓР С”Р В»РЎР‹РЎвЂЎР ВµР Р…Р С‘Р Вµ Р С”Р В°Р С” Р Р† Р С•РЎР‚Р С‘Р С–Р С‘Р Р…Р В°Р В»РЎРЉР Р…Р С•Р С Р СР ВµРЎвЂљР С•Р Т‘Р Вµ
                    raise KeyError(f"Agent '{agent_name}' is not registered") from None

        return DynamicRegistryWrapper(base_registry, factory)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _stable_hash(payload: dict[str, Any]) -> str:
        normalized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(normalized.encode("utf-8")).hexdigest()

    def calculate_step_input_hash(self, step: StepDefinition, context_state: dict[str, Any]) -> str:
        payload = self._apply_input_mapping(step, context_state)
        if not isinstance(payload, dict):
            payload = {"_payload": payload}
        return self._stable_hash(payload)

    def _log_event(self, level: int, run_id: str, event: str, **fields: Any) -> None:
        safe_fields = redact_mapping(fields)
        correlation_id = safe_fields.pop("correlation_id", None)
        step = safe_fields.pop("step", safe_fields.pop("step_name", None))
        payload = {
            "timestamp": self._now_iso(),
            "level": logging.getLevelName(level),
            "component": "step_executor",
            "run_id": run_id,
            "correlation_id": correlation_id,
            "step": step,
            "event": event,
            **safe_fields,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _resolve_step_end_log_level(step_status: StepStatus) -> int:
        if step_status == StepStatus.SUCCESS:
            return logging.INFO
        if step_status == StepStatus.PARTIAL_SUCCESS:
            return logging.WARNING
        if step_status == StepStatus.SKIPPED:
            return logging.INFO
        return logging.ERROR

    @staticmethod
    def _extract_primary_reason(output: dict[str, Any]) -> str | None:
        decisions = output.get("decisions")
        if isinstance(decisions, list):
            for item in decisions:
                if not isinstance(item, dict):
                    continue
                reason = item.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return reason.strip()
        logs = output.get("logs")
        if isinstance(logs, list):
            for item in logs:
                if isinstance(item, str) and item.strip():
                    return item.strip()[:300]
        return None

    def _get_agent_from_registry(self, agent_name: str, run_id: str) -> Any:
        """Р СџР С•Р В»РЎС“РЎвЂЎР С‘РЎвЂљРЎРЉ Р В°Р С–Р ВµР Р…РЎвЂљ Р С‘Р В· РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚Р В°, РЎРѓ Р С•Р В±РЎР‚Р В°Р В±Р С•РЎвЂљР С”Р С•Р в„– Р С•РЎв‚¬Р С‘Р В±Р С•Р С” Р Т‘Р В»РЎРЏ Р Р…Р ВµР В·Р В°РЎР‚Р ВµР С–Р С‘РЎРѓРЎвЂљРЎР‚Р С‘РЎР‚Р С•Р Р†Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р В°Р С–Р ВµР Р…РЎвЂљР С•Р Р†."""
        if not self.agent_registry.has(agent_name):
            error_msg = f"Agent '{agent_name}' is not registered in AgentRegistry"
            self._log_event(
                logging.ERROR,
                run_id,
                "agent_not_found_in_registry",
                agent=agent_name,
                error=error_msg,
            )
            raise LookupError(error_msg)

        return self.agent_registry.create(agent_name)

    @staticmethod
    def _normalize_agent_output(output: dict[str, Any]) -> dict[str, Any]:
        """
        Р СњР С•РЎР‚Р СР В°Р В»Р С‘Р В·РЎС“Р ВµРЎвЂљ РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљ Р В°Р С–Р ВµР Р…РЎвЂљР В°, РЎвЂЎРЎвЂљР С•Р В±РЎвЂ№ Р С•Р Р… РЎРѓР С•Р С•РЎвЂљР Р†Р ВµРЎвЂљРЎРѓРЎвЂљР Р†Р С•Р Р†Р В°Р В» РЎРѓРЎвЂ¦Р ВµР СР Вµ.
        Р Р€Р Т‘Р В°Р В»РЎРЏР ВµРЎвЂљ Р Т‘Р С•Р С—Р С•Р В»Р Р…Р С‘РЎвЂљР ВµР В»РЎРЉР Р…РЎвЂ№Р Вµ Р С—Р С•Р В»РЎРЏ, Р С”Р С•РЎвЂљР С•РЎР‚РЎвЂ№Р Вµ Р Р…Р Вµ Р С—РЎР‚Р ВµР Т‘РЎС“РЎРѓР СР С•РЎвЂљРЎР‚Р ВµР Р…РЎвЂ№ РЎРѓРЎвЂ¦Р ВµР СР С•Р в„–.
        """
        # Р С›Р С—РЎР‚Р ВµР Т‘Р ВµР В»РЎРЏР ВµР С Р Т‘Р С•Р С—РЎС“РЎРѓРЎвЂљР С‘Р СРЎвЂ№Р Вµ Р С—Р С•Р В»РЎРЏ Р Р† РЎРѓР С•Р С•РЎвЂљР Р†Р ВµРЎвЂљРЎРѓРЎвЂљР Р†Р С‘Р С‘ РЎРѓР С• РЎРѓРЎвЂ¦Р ВµР СР С•Р в„–
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

        # Р РЋР С•Р В·Р Т‘Р В°Р ВµР С Р Р…Р С•Р Р†РЎвЂ№Р в„– РЎРѓР В»Р С•Р Р†Р В°РЎР‚РЎРЉ РЎвЂљР С•Р В»РЎРЉР С”Р С• РЎРѓ РЎР‚Р В°Р В·РЎР‚Р ВµРЎв‚¬Р ВµР Р…Р Р…РЎвЂ№Р СР С‘ Р С”Р В»РЎР‹РЎвЂЎР В°Р СР С‘
        normalized = {}
        for key in allowed_keys:
            if key in output:
                normalized[key] = output[key]

        # Р вЂўРЎРѓР В»Р С‘ Р С•Р В±РЎРЏР В·Р В°РЎвЂљР ВµР В»РЎРЉР Р…РЎвЂ№Р Вµ Р С—Р С•Р В»РЎРЏ Р С•РЎвЂљРЎРѓРЎС“РЎвЂљРЎРѓРЎвЂљР Р†РЎС“РЎР‹РЎвЂљ, Р Т‘Р С•Р В±Р В°Р Р†Р В»РЎРЏР ВµР С Р С‘РЎвЂ¦ РЎРѓР С• Р В·Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘РЎРЏР СР С‘ Р С—Р С• РЎС“Р СР С•Р В»РЎвЂЎР В°Р Р…Р С‘РЎР‹
        if "status" not in normalized:
            normalized["status"] = output.get("status", "FAILED")

        if "artifacts" not in normalized:
            normalized["artifacts"] = output.get("artifacts", [])

        if "decisions" not in normalized:
            normalized["decisions"] = output.get("decisions", [])

        if "logs" not in normalized:
            normalized["logs"] = output.get("logs", ["Normalized by StepExecutor"])

        if "next_actions" not in normalized:
            normalized["next_actions"] = output.get("next_actions", [])

        return normalized

    @staticmethod
    def _coerce_decisions_for_validation(decisions: Any) -> Any:
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

    @staticmethod
    def _coerce_code_patch_content_for_validation(content: Any) -> dict[str, Any]:
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
                    generated_diff = (
                        f"# {change_type}\n{json.dumps(content_value, ensure_ascii=False)}"
                    )

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

        # Preserve GitHub patch workflow metadata so downstream agents (e.g. pr_merge_agent)
        # can consume PR details from code_patch artifacts.
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

    @staticmethod
    def _coerce_spec_content_for_validation(content: Any) -> dict[str, Any]:
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

    @staticmethod
    def _coerce_tests_content_for_validation(content: Any) -> dict[str, Any]:
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

    @staticmethod
    def _coerce_test_results_for_validation(test_results: Any) -> Any:
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

    def _sanitize_output_for_validation(self, output: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "schema_version",
            "status",
            "artifacts",
            "decisions",
            "logs",
            "next_actions",
            "validation_errors",
            "test_results",
        }
        sanitized = {key: value for key, value in output.items() if key in allowed_keys}

        raw_status = sanitized.get("status")
        if isinstance(raw_status, str):
            status_upper = raw_status.strip().upper()
            if status_upper in {"FAILURE", "ERROR", "FAIL"}:
                status_upper = "FAILED"  # Normalize to consistent FAILED status
            if status_upper:
                sanitized["status"] = status_upper

        if "decisions" not in sanitized:
            reason = output.get("reason")
            if isinstance(reason, str) and reason.strip():
                confidence = output.get("confidence")
                if not isinstance(confidence, (int, float)):
                    confidence = 0.5
                confidence = max(0.0, min(float(confidence), 1.0))
                sanitized["decisions"] = [{"reason": reason.strip(), "confidence": confidence}]

        if "decisions" in sanitized:
            sanitized["decisions"] = self._coerce_decisions_for_validation(
                sanitized.get("decisions")
            )

        if "test_results" in sanitized:
            sanitized["test_results"] = self._coerce_test_results_for_validation(
                sanitized.get("test_results")
            )

        artifacts = sanitized.get("artifacts")
        if isinstance(artifacts, list):
            normalized_artifacts = []
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    normalized_artifacts.append(artifact)
                    continue

                normalized_artifact = {
                    key: artifact[key]
                    for key in ("type", "path", "content", "metadata")
                    if key in artifact
                }
                artifact_type = artifact.get("type")
                if artifact_type == "code_patch":
                    normalized_artifact["content"] = self._coerce_code_patch_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "spec":
                    normalized_artifact["content"] = self._coerce_spec_content_for_validation(
                        artifact.get("content")
                    )
                elif artifact_type == "tests":
                    normalized_artifact["content"] = self._coerce_tests_content_for_validation(
                        artifact.get("content")
                    )

                normalized_artifacts.append(normalized_artifact)
            sanitized["artifacts"] = normalized_artifacts

        return sanitized

    @staticmethod
    def _extract_output_aliases(output_mapping: Any) -> set[str]:
        aliases: set[str] = set()

        if isinstance(output_mapping, str):
            stripped = output_mapping.strip()
            if stripped and "{{" not in stripped and "}}" not in stripped:
                aliases.add(stripped)
            for match in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", output_mapping):
                if match:
                    aliases.add(match)
            return aliases

        if isinstance(output_mapping, dict):
            for value in output_mapping.values():
                aliases.update(StepExecutor._extract_output_aliases(value))
            return aliases

        if isinstance(output_mapping, list):
            for value in output_mapping:
                aliases.update(StepExecutor._extract_output_aliases(value))

        return aliases

    @staticmethod
    def _extract_output_payload(output: dict[str, Any]) -> Any:
        artifacts = output.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if isinstance(artifact, dict) and "content" in artifact:
                    return artifact.get("content")

        if "test_results" in output:
            return output.get("test_results")

        return output

    def _apply_output_mapping(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        output: dict[str, Any],
    ) -> None:
        aliases = self._extract_output_aliases(step.output_mapping)
        if not aliases:
            return

        mapped_value = self._extract_output_payload(output)

        for alias in aliases:
            if not alias:
                continue
            parts = alias.split(".")
            if len(parts) == 1:
                context.set_state_value(alias, mapped_value)
                continue

            root = parts[0]
            nested = context.state.get(root)
            if not isinstance(nested, dict):
                nested = {}

            cursor = nested
            for part in parts[1:-1]:
                value = cursor.get(part)
                if not isinstance(value, dict):
                    value = {}
                    cursor[part] = value
                cursor = value

            cursor[parts[-1]] = mapped_value
            context.set_state_value(root, nested)

    @staticmethod
    def _normalize_step_status(raw_status: str | None) -> StepStatus:
        # PARTIAL_SUCCESS should remain as PARTIAL_SUCCESS, not normalized to SUCCESS
        if raw_status == StepStatus.PARTIAL_SUCCESS.value:
            return StepStatus.PARTIAL_SUCCESS
        if raw_status == StepStatus.SUCCESS.value:
            return StepStatus.SUCCESS
        if raw_status in {item.value for item in StepStatus}:
            return StepStatus(raw_status)
        return StepStatus.FAILED

    @staticmethod
    def _error_result(message: str) -> dict[str, Any]:
        return {
            "status": "FAILED",
            "artifacts": [],
            "decisions": [],
            "logs": [message],
            "next_actions": [],
        }

    @staticmethod
    def _invoke_agent_run(agent: Any, payload: Any) -> Any:
        import inspect

        run_callable = agent.run
        bound_signature = inspect.signature(run_callable)
        positional_params = [
            parameter
            for parameter in bound_signature.parameters.values()
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]

        # Compatibility mode:
        # Some tests/agents define `def run(context)` on a class (without `self`),
        # which becomes a bound method with zero positional params.
        if not positional_params:
            raw_function = getattr(run_callable, "__func__", None)
            if raw_function is not None:
                raw_signature = inspect.signature(raw_function)
                raw_positional = [
                    parameter
                    for parameter in raw_signature.parameters.values()
                    if parameter.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                if len(raw_positional) == 1 and raw_positional[0].name not in {"self", "cls"}:
                    return raw_function(payload)
            return run_callable()

        return run_callable(payload)

    @staticmethod
    def _run_agent(agent: Any, payload: Any, timeout_seconds: float | None) -> dict[str, Any]:
        import asyncio
        import inspect

        def invoke_with_await_support() -> dict[str, Any]:
            result = StepExecutor._invoke_agent_run(agent, payload)
            if inspect.isawaitable(result):
                return asyncio.run(result)
            return result

        if timeout_seconds is None:
            return invoke_with_await_support()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(invoke_with_await_support)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeoutError as exc:
                raise TimeoutError(f"Step timed out after {timeout_seconds} seconds") from exc

    def _apply_input_mapping(
        self, step: StepDefinition, context_state: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Apply input_mapping from step definition to context state.

        Handles Jinja2 template variables like {{key}}, {{key.subkey}}, {{key|default(value)}}
        Resolves them from context_state and builds step-specific payload.

        Args:
            step: Step definition with input_mapping
            context_state: Current execution context state

        Returns:
            Merged payload for the agent
        """
        try:
            from jinja2 import Template
        except ImportError:
            # Fallback to simple regex-based resolution if Jinja2 not available
            return self._apply_input_mapping_simple(step, context_state)

        # Start with context state as base
        payload = dict(context_state)

        # If no input_mapping, return full context
        if not step.input_mapping:
            return payload

        scalar_template_pattern = re.compile(r"^\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}$")

        def resolve_value(raw_value: Any) -> Any:
            if not isinstance(raw_value, str):
                return raw_value

            match = scalar_template_pattern.fullmatch(raw_value.strip())
            if match:
                resolved_value = self._resolve_path(context_state, match.group(1))
                if resolved_value is not None:
                    return resolved_value

            try:
                template = Template(raw_value)
                rendered = template.render(**context_state)
                return self._try_parse_json(rendered)
            except Exception:
                return raw_value

        # Apply each mapping from input_mapping
        for target_key, source_value in step.input_mapping.items():
            if isinstance(source_value, str):
                payload[target_key] = resolve_value(source_value)
            elif isinstance(source_value, dict):
                resolved_dict = {k: resolve_value(v) for k, v in source_value.items()}
                payload[target_key] = resolved_dict
            elif isinstance(source_value, list):
                payload[target_key] = [resolve_value(item) for item in source_value]
            else:
                payload[target_key] = source_value

        return payload

    def _try_parse_json(self, value: str) -> Any:
        """Try to parse a string as JSON. Return original string if not valid JSON."""
        import json

        value = value.strip()
        if (value.startswith("{") and value.endswith("}")) or (
            value.startswith("[") and value.endswith("]")
        ):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass
        return value

    def _apply_input_mapping_simple(
        self, step: StepDefinition, context_state: dict[str, Any]
    ) -> dict[str, Any]:
        """Fallback simple input_mapping without Jinja2."""

        import re

        # Start with context state as base
        payload = dict(context_state)

        # If no input_mapping, return full context
        if not step.input_mapping:
            return payload

        # Pattern to match template variables: {{key}} or {{key.subkey}}
        template_pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]]+)\s*\}\}")

        def resolve_template(template_str: str) -> Any:
            """Resolve a template string like {{key.subkey}} from context_state."""
            # Find all template variables in the string
            matches = template_pattern.findall(template_str)

            if not matches:
                # No template variables, return as-is
                return template_str

            # If entire string is a single template variable, resolve it directly
            if len(matches) == 1 and template_str.strip() == f"{{{{{matches[0]}}}}}":
                return self._resolve_path(context_state, matches[0])

            # Otherwise, replace each template variable in the string
            result = template_str
            for match in matches:
                value = self._resolve_path(context_state, match)
                if value is not None:
                    # Replace the template with the resolved value
                    result = result.replace(f"{{{{{match}}}}}", str(value))
                else:
                    # Keep the template if not resolved
                    pass
            return result

        # Apply each mapping from input_mapping
        for target_key, source_value in step.input_mapping.items():
            if isinstance(source_value, str):
                # Try to resolve as template first
                resolved = resolve_template(source_value)
                payload[target_key] = resolved
            elif isinstance(source_value, dict):
                # For dict values, resolve each value
                resolved_dict = {}
                for k, v in source_value.items():
                    if isinstance(v, str):
                        resolved_dict[k] = resolve_template(v)
                    else:
                        resolved_dict[k] = v
                payload[target_key] = resolved_dict
            elif isinstance(source_value, list):
                # For list values, resolve each element
                resolved_list = []
                for item in source_value:
                    if isinstance(item, str):
                        resolved_list.append(resolve_template(item))
                    else:
                        resolved_list.append(item)
                payload[target_key] = resolved_list
            else:
                # For non-string values, use as-is
                payload[target_key] = source_value

        return payload

    @staticmethod
    def _resolve_path(source: dict[str, Any], dotted_path: str) -> Any:
        """Resolve a dotted path like 'key.subkey.array[0].field' from source dict."""
        current = source
        parts = dotted_path.split(".")

        for part in parts:
            if not isinstance(current, dict) or part not in current:
                # Try to handle array access like items[0]
                if "[" in part and "]" in part:
                    key, idx_str = part.split("[")
                    idx = int(idx_str.rstrip("]"))
                    if isinstance(current, dict) and key in current:
                        arr = current[key]
                        if isinstance(arr, list) and 0 <= idx < len(arr):
                            current = arr[idx]
                            continue
                return None
            current = current[part]

        return current

    @staticmethod
    def _attach_artifact_ids(
        output: dict[str, Any],
        *,
        step_name: str,
        step_input_hash: str,
    ) -> list[str]:
        artifact_ids: list[str] = []
        artifacts = output.get("artifacts")
        if not isinstance(artifacts, list):
            return artifact_ids

        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            artifact_type = str(artifact.get("type") or "unknown").strip() or "unknown"
            digest_seed = f"{step_name}:{step_input_hash}:{artifact_type}:{index}"
            artifact_id = sha256(digest_seed.encode("utf-8")).hexdigest()[:20]
            metadata = artifact.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.setdefault("artifact_id", artifact_id)
            metadata.setdefault("step_input_hash", step_input_hash)
            artifact["metadata"] = metadata
            artifact_ids.append(str(metadata["artifact_id"]))

        return artifact_ids

    def execute_step(
        self,
        step: StepDefinition,
        context: ExecutionContext,
        run_state: PipelineRunState,
    ) -> dict[str, Any]:
        run_id = context.run_id
        correlation_id = str(context.metadata.get("correlation_id", "")).strip() or None
        trace_id = str(context.metadata.get("trace_id", "")).strip() or None
        parent_span_id = str(context.metadata.get("root_span_id", "")).strip() or None
        span_id = uuid4().hex[:16]
        started_at = self._now_iso()
        step_payload_for_hash = self._apply_input_mapping(step, context.state)
        if not isinstance(step_payload_for_hash, dict):
            step_payload_for_hash = {"_payload": step_payload_for_hash}
        step_input_hash = self._stable_hash(step_payload_for_hash)
        run_state.mark_step_status(
            step.name,
            StepStatus.RUNNING,
            started_at=started_at,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
        )
        self._log_event(
            logging.INFO,
            run_id,
            "step_start",
            step_name=step.name,
            agent=step.agent,
            pipeline_name=context.pipeline_name,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
        )

        error_message: str | None = None
        try:
            # Р вЂ™РЎРѓР ВµР С–Р Т‘Р В° Р С—Р С•Р В»РЎС“РЎвЂЎР В°Р ВµР С Р В°Р С–Р ВµР Р…РЎвЂљ РЎвЂЎР ВµРЎР‚Р ВµР В· РЎР‚Р ВµР ВµРЎРѓРЎвЂљРЎР‚, Р В±Р ВµР В· Р Р†Р С•Р В·Р СР С•Р В¶Р Р…Р С•РЎРѓРЎвЂљР С‘ Р С—РЎР‚РЎРЏР СР С•Р С–Р С• РЎРѓР С•Р В·Р Т‘Р В°Р Р…Р С‘РЎРЏ
            agent = self._get_agent_from_registry(step.agent, run_id)

            # Apply input_mapping from step definition to context.state
            step_payload = dict(step_payload_for_hash)

            # Р вЂєР С•Р С–Р С‘РЎР‚РЎС“Р ВµР С Р С‘Р Р…РЎвЂћР С•РЎР‚Р СР В°РЎвЂ Р С‘РЎР‹ Р С• Р Р†РЎвЂ№Р В·Р С•Р Р†Р Вµ Р В°Р С–Р ВµР Р…РЎвЂљР В°
            self._log_event(
                logging.DEBUG,
                run_id,
                "about_to_run_agent",
                step_name=step.name,
                agent=step.agent,
                payload_keys=list(step_payload.keys())
                if isinstance(step_payload, dict)
                else type(step_payload).__name__,
            )

            # Р РЋР С•Р В·Р Т‘Р В°Р ВµР С Р С”Р С•Р Р…РЎвЂљР ВµР С”РЎРѓРЎвЂљ Р Р†РЎвЂ№Р С—Р С•Р В»Р Р…Р ВµР Р…Р С‘РЎРЏ Р Т‘Р В»РЎРЏ Р В°Р С–Р ВµР Р…РЎвЂљР В°, Р С”Р С•РЎвЂљР С•РЎР‚РЎвЂ№Р в„– Р Р†Р С”Р В»РЎР‹РЎвЂЎР В°Р ВµРЎвЂљ Р Р† РЎРѓР ВµР В±РЎРЏ state Р С‘ Р СР ВµРЎвЂљР С•Р Т‘РЎвЂ№ Р Т‘Р С•РЎРѓРЎвЂљРЎС“Р С—Р В° Р С” Р Р…Р ВµР СРЎС“
            # Р ВРЎРѓР С—Р С•Р В»РЎРЉР В·РЎС“Р ВµР С Р С•Р В±РЎР‰Р ВµР С”РЎвЂљ, Р С”Р С•РЎвЂљР С•РЎР‚РЎвЂ№Р в„– Р С—РЎР‚Р ВµР Т‘Р С•РЎРѓРЎвЂљР В°Р Р†Р В»РЎРЏР ВµРЎвЂљ Р Т‘Р С•РЎРѓРЎвЂљРЎС“Р С— Р С” РЎРѓР С•РЎРѓРЎвЂљР С•РЎРЏР Р…Р С‘РЎР‹ Р С”Р В°Р С” РЎвЂЎР ВµРЎР‚Р ВµР В· Р В°РЎвЂљРЎР‚Р С‘Р В±РЎС“РЎвЂљ state, РЎвЂљР В°Р С” Р С‘ РЎвЂЎР ВµРЎР‚Р ВµР В· Р СР ВµРЎвЂљР С•Р Т‘ get

            mapped_overrides: dict[str, Any] = {}
            if step.input_mapping and isinstance(step_payload, dict):
                mapped_overrides = {
                    key: step_payload[key] for key in step.input_mapping if key in step_payload
                }

            class _StepStateView:
                def __init__(self, shared_state: dict[str, Any], overrides: dict[str, Any]):
                    self._shared_state = shared_state
                    self._overrides = dict(overrides)

                def get(self, key: str, default: Any = None) -> Any:
                    if key in self._overrides:
                        return self._overrides[key]
                    return self._shared_state.get(key, default)

                def __getitem__(self, key: str) -> Any:
                    if key in self._overrides:
                        return self._overrides[key]
                    return self._shared_state[key]

                def __setitem__(self, key: str, value: Any) -> None:
                    self._shared_state[key] = value
                    self._overrides[key] = value

                def __contains__(self, key: str) -> bool:
                    return key in self._overrides or key in self._shared_state

                def update(self, updates: dict[str, Any]) -> None:
                    self._shared_state.update(updates)
                    self._overrides.update(updates)

                def copy(self) -> dict[str, Any]:
                    merged = dict(self._shared_state)
                    merged.update(self._overrides)
                    return merged

                def keys(self):
                    return self.copy().keys()

                def items(self):
                    return self.copy().items()

                def values(self):
                    return self.copy().values()

                def __iter__(self):
                    return iter(self.copy())

                def __len__(self) -> int:
                    return len(self.copy())

                def setdefault(self, key: str, default: Any = None) -> Any:
                    if key in self:
                        return self[key]
                    self[key] = default
                    return default

            class AgentContext:
                def __init__(
                    self,
                    execution_context: ExecutionContext,
                    step_specific_overrides: dict[str, Any],
                ):
                    self.execution_context = execution_context
                    self.state = _StepStateView(execution_context.state, step_specific_overrides)

                def get(self, key: str, default: Any = None) -> Any:
                    return self.state.get(key, default)

                def keys(self):
                    return self.state.keys()

                def items(self):
                    return self.state.items()

                def values(self):
                    return self.state.values()

                def copy(self) -> dict[str, Any]:
                    return self.state.copy()

                def __getitem__(self, key: str) -> Any:
                    return self.state[key]

                def __contains__(self, key: str) -> bool:
                    return key in self.state

                def __iter__(self):
                    return iter(self.state)

                def __len__(self) -> int:
                    return len(self.state)

                def update(self, updates: dict[str, Any]) -> None:
                    self.state.update(updates)

                def update_state(self, updates: dict[str, Any]) -> None:
                    self.state.update(updates)

                def set_state_value(self, key: str, value: Any) -> None:
                    self.state[key] = value

            agent_context = AgentContext(context, mapped_overrides)

            output = self._run_agent(agent, agent_context, step.timeout_seconds)
            if not isinstance(output, dict):
                raise TypeError("Agent output must be a dict")

            # Р вЂєР С•Р С–Р С‘РЎР‚РЎС“Р ВµР С РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљ Р Р†РЎвЂ№Р С—Р С•Р В»Р Р…Р ВµР Р…Р С‘РЎРЏ Р В°Р С–Р ВµР Р…РЎвЂљР В°
            self._log_event(
                logging.DEBUG,
                run_id,
                "agent_execution_completed",
                step_name=step.name,
                agent=step.agent,
                output_status=output.get("status", "unknown"),
            )

            # Р РЋР Р…Р В°РЎвЂЎР В°Р В»Р В° Р С—РЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЏР ВµР С РЎРѓРЎвЂ¦Р ВµР СРЎС“ РЎРѓ Р С•РЎР‚Р С‘Р С–Р С‘Р Р…Р В°Р В»РЎРЉР Р…РЎвЂ№Р С РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљР С•Р С
            validation_payload = self._sanitize_output_for_validation(output)

            validation_errors = self.schema_validator.validate_step_output(
                step.name, validation_payload
            )
            if validation_errors:
                # Р вЂўРЎРѓР В»Р С‘ Р ВµРЎРѓРЎвЂљРЎРЉ Р С•РЎв‚¬Р С‘Р В±Р С”Р С‘ Р Р†Р В°Р В»Р С‘Р Т‘Р В°РЎвЂ Р С‘Р С‘, Р Р…Р С•РЎР‚Р СР В°Р В»Р С‘Р В·РЎС“Р ВµР С РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљ Р С‘ Р Т‘Р С•Р В±Р В°Р Р†Р В»РЎРЏР ВµР С Р С•РЎв‚¬Р С‘Р В±Р С”Р С‘
                normalized_output = self._normalize_agent_output(validation_payload)
                existing_errors = normalized_output.get("validation_errors", [])
                normalized_errors = (
                    list(existing_errors) if isinstance(existing_errors, list) else []
                )
                normalized_errors.extend(validation_errors)
                normalized_output["validation_errors"] = normalized_errors
                output = normalized_output
                if self.strict_schema_validation:
                    # Р вЂ™ РЎРѓРЎвЂљРЎР‚Р С•Р С–Р С•Р С РЎР‚Р ВµР В¶Р С‘Р СР Вµ Р Р†Р В°Р В»Р С‘Р Т‘Р В°РЎвЂ Р С‘Р С‘ Р Р†Р С•Р В·Р Р†РЎР‚Р В°РЎвЂ°Р В°Р ВµР С Р С•РЎв‚¬Р С‘Р В±Р С”РЎС“
                    error_message = "; ".join(validation_errors)
                    self._log_event(
                        logging.WARNING,
                        run_id,
                        "step_validation_error",
                        step_name=step.name,
                        agent=step.agent,
                        validation_error_count=len(validation_errors),
                        strict_mode=self.strict_schema_validation,
                    )
                    output = self._error_result(f"Schema validation failed: {error_message}")
                else:
                    # Р вЂ™ Р Р…Р ВµРЎРѓРЎвЂљРЎР‚Р С•Р С–Р С•Р С РЎР‚Р ВµР В¶Р С‘Р СР Вµ Р С—РЎР‚Р С•Р Т‘Р С•Р В»Р В¶Р В°Р ВµР С РЎРѓ Р Р…Р С•РЎР‚Р СР В°Р В»Р С‘Р В·Р С•Р Р†Р В°Р Р…Р Р…РЎвЂ№Р С РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљР С•Р С
                    error_message = "; ".join(validation_errors)
                    self._log_event(
                        logging.WARNING,
                        run_id,
                        "step_validation_warning",
                        step_name=step.name,
                        agent=step.agent,
                        validation_error_count=len(validation_errors),
                        strict_mode=self.strict_schema_validation,
                    )
            else:
                # Р вЂўРЎРѓР В»Р С‘ Р С•РЎв‚¬Р С‘Р В±Р С•Р С” Р Р†Р В°Р В»Р С‘Р Т‘Р В°РЎвЂ Р С‘Р С‘ Р Р…Р ВµРЎвЂљ, Р Р…Р С•РЎР‚Р СР В°Р В»Р С‘Р В·РЎС“Р ВµР С РЎР‚Р ВµР В·РЎС“Р В»РЎРЉРЎвЂљР В°РЎвЂљ Р Т‘Р В»РЎРЏ РЎРѓР С•Р С–Р В»Р В°РЎРѓР С•Р Р†Р В°Р Р…Р Р…Р С•РЎРѓРЎвЂљР С‘
                output = self._normalize_agent_output(validation_payload)

            step_status = self._normalize_step_status(output.get("status"))
        except Exception as exc:  # pylint: disable=broad-except
            error_message = str(exc)
            self._log_event(
                logging.ERROR,
                run_id,
                "agent_execution_failed",
                step_name=step.name,
                agent=step.agent,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            output = self._error_result(f"Agent '{step.agent}' failed: {exc}")
            step_status = StepStatus.FAILED

        if step_status in {StepStatus.SUCCESS, StepStatus.PARTIAL_SUCCESS, StepStatus.BLOCKED}:
            try:
                self._apply_output_mapping(step, context, output)
            except Exception as exc:  # pylint: disable=broad-except
                self._log_event(
                    logging.WARNING,
                    run_id,
                    "output_mapping_failed",
                    step_name=step.name,
                    agent=step.agent,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        _ = self._attach_artifact_ids(output, step_name=step.name, step_input_hash=step_input_hash)
        context.record_step_result(step.name, output)
        finished_at = self._now_iso()
        run_state.mark_step_status(
            step.name,
            step_status,
            finished_at=finished_at,
            error=error_message,
            output=output,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
        )
        self._log_event(
            self._resolve_step_end_log_level(step_status),
            run_id,
            "step_end",
            step_name=step.name,
            agent=step.agent,
            pipeline_name=context.pipeline_name,
            status=step_status.value,
            reason=self._extract_primary_reason(output),
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            input_hash=step_input_hash,
        )
        return output

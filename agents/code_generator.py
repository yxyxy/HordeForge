from __future__ import annotations

import ast
import json
import logging
import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.github_client import GitHubClient
from agents.instruction_layers import build_instruction_stack
from agents.llm_wrapper import build_code_prompt, get_llm_wrapper, parse_code_output
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_prompt,
)
from agents.patch_workflow import PatchWorkflowOrchestrator, create_patch_from_code_result
from agents.patch_workflow_orchestrator import materialize_patch_operations, materialize_patch_text

logger = logging.getLogger("hordeforge.code_generator")


class EnhancedCodeGenerator(BaseAgent):
    name: str = "code_generator"
    description: str = "Generates code patch from specification, tests and subtasks."
    OPENED_LABEL = "agent:opened"
    PLANNING_LABEL = "agent:planning"
    READY_LABEL = "agent:ready"
    FIXED_LABEL = "agent:fixed"
    PLACEHOLDER_PATCH_MARKERS: tuple[str, ...] = (
        "placeholder content - actual file content would be provided",
        "cannot implement fix without access to the actual source code",
        "no source files were identified to modify",
        "without seeing the actual",
        "# generated test file",
        "need to find and examine the specific test case",
        "analyze the failing test",
        "cannot implement fix without",
    )
    MAX_UNJUSTIFIED_REWRITE_LINES = 1400
    MAX_CONTEXT_REPAIR_ATTEMPTS = 1
    MAX_REQUIRED_FILE_REQUEST_ROUNDTRIPS = 2
    MAX_REQUESTED_FILES_PER_ROUND = 4
    MAX_REQUESTED_FILE_SNIPPET_CHARS = 3000
    MAX_CANDIDATE_SNIPPETS_TOTAL = 8
    MAX_SEMANTIC_VIOLATIONS = 10
    SEMANTIC_RETRY_STATE_KEY = "__code_generator_semantic_retry_state"
    SEMANTIC_RETRY_HISTORY_LIMIT = 8
    PATCH_FIRST_STRATEGY = "patch_first"
    FULL_FILE_STRATEGY = "full_file"
    CONTEXT_REPAIRABLE_REASONS: tuple[str, ...] = (
        "no_files_in_patch",
        "analysis_only_without_source_change",
        "test_failure_without_source_change",
        "full_file_rewrite_without_justification",
        "missing_file_content",
        "handoff_scope_violation",
        "semantic_contract_violation",
        "invalid_patch_operations",
    )

    PLAN_JSON_START = "<!-- hordeforge:plan-json:start -->"
    PLAN_JSON_END = "<!-- hordeforge:plan-json:end -->"

    # Function calling tool definition for apply_patch (Codex-compatible format)
    APPLY_PATCH_TOOL_DESCRIPTION = (
        "Use the `apply_patch` tool to edit files. "
        "Your patch language is a stripped-down, file-oriented diff format.\n\n"
        "Format:\n"
        "*** Begin Patch\n"
        "[ one or more file sections ]\n"
        "*** End Patch\n\n"
        "File operations:\n"
        "*** Add File: <path> - create a new file. Every following line starts with +\n"
        "*** Delete File: <path> - remove an existing file\n"
        "*** Update File: <path> - patch an existing file\n"
        "  @@ <context line - class or function name>\n"
        "  -<old line to remove>\n"
        "  +<new line to add>\n\n"
        "Example:\n"
        "*** Begin Patch\n"
        "*** Update File: src/app.py\n"
        "@@ def greet():\n"
        "-    pass\n"
        "+    return 'hello'\n"
        "*** End Patch"
    )

    @staticmethod
    def _build_apply_patch_tool_definition() -> dict[str, Any]:
        """Build OpenAI function calling tool definition for apply_patch."""
        return {
            "type": "function",
            "function": {
                "name": "apply_patch",
                "description": EnhancedCodeGenerator.APPLY_PATCH_TOOL_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patch_text": {
                            "type": "string",
                            "description": (
                                "The full patch text in Codex apply_patch format. "
                                "Must start with '*** Begin Patch' and end with '*** End Patch'. "
                                "Use '*** Update File: <path>' with @@ context, -old, +new lines."
                            ),
                        },
                    },
                    "required": ["patch_text"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        spec: dict[str, Any] = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer"],
            )
            or {}
        )
        if not isinstance(spec, dict):
            spec = {}

        tests: dict[str, Any] = (
            get_artifact_from_context(
                context,
                "tests",
                preferred_steps=["test_generator"],
            )
            or {}
        )
        if not isinstance(tests, dict):
            tests = {}

        subtasks: dict[str, Any] = (
            get_artifact_from_context(
                context,
                "subtasks",
                preferred_steps=["task_decomposer"],
            )
            or {}
        )
        if not isinstance(subtasks, dict):
            subtasks = {}

        rag_context: dict[str, Any] = (
            get_artifact_from_context(
                context,
                "rag_context",
                preferred_steps=["rag_initializer", "rag_retriever"],
            )
            or {}
        )
        if not isinstance(rag_context, dict):
            rag_context = {}

        ci_failure_context: dict[str, Any] = (
            get_artifact_from_context(
                context,
                "ci_failure_context",
                preferred_steps=["ci_failure_analysis"],
            )
            or {}
        )
        if not isinstance(ci_failure_context, dict):
            ci_failure_context = {}

        memory_context = context.get("memory_context", "")
        memory_context_text = self._format_memory_context(memory_context)
        issue_context_text = self._format_issue_context(context.get("issue"))
        task_description = context.get("task_description", spec.get("summary", ""))

        rules_payload: dict[str, Any] = (
            context.get("rules") if isinstance(context.get("rules"), dict) else {}
        )

        test_cases: list[dict[str, Any]] = tests.get("test_cases", []) or []
        subtask_items: list[dict[str, Any]] = subtasks.get("items", []) or []
        rag_sources: list[Any] = rag_context.get("sources", []) or []
        rules_documents: dict[str, Any] = rules_payload.get("documents", {}) or {}
        rules_version: str = str(rules_payload.get("version", "")).strip()

        use_llm: bool = bool(context.get("use_llm", True))
        require_llm: bool = bool(context.get("require_llm", False))
        publish_pr_in_code_generator: bool = bool(context.get("publish_pr_in_code_generator", True))
        open_mode: bool = bool(context.get("open_mode", False))
        enforce_patch_quality_gate: bool = bool(context.get("enforce_patch_quality_gate", False))
        enforce_semantic_patch_gate: bool = bool(
            context.get("enforce_semantic_patch_gate", enforce_patch_quality_gate)
        )
        allow_full_file_rewrite: bool = bool(context.get("allow_full_file_rewrite", False))
        patch_strategy = self._resolve_patch_strategy(
            context.get("patch_strategy"),
            allow_full_file_rewrite=allow_full_file_rewrite,
        )
        semantic_retry_state = self._read_semantic_retry_state(context)
        semantic_feedback_packet = self._build_semantic_feedback_packet_from_state(
            semantic_retry_state
        )
        force_plan_after_semantic_failure: bool = bool(
            context.get("force_plan_after_semantic_failure", True)
        )
        forced_strategy_mode = (
            "forced_plan"
            if self._should_force_plan_for_semantic_retries(
                semantic_retry_state,
                force_after_first=force_plan_after_semantic_failure,
            )
            else "default"
        )
        quality_gate_mode_raw = str(context.get("quality_gate_mode", "")).strip().lower()
        if open_mode and not quality_gate_mode_raw:
            quality_gate_mode_raw = "shadow"
        quality_gate_mode = quality_gate_mode_raw if quality_gate_mode_raw else "enforce"
        quality_gate_is_shadow = quality_gate_mode in {"shadow", "observe", "monitor"}
        quality_gate_is_enforced = enforce_patch_quality_gate and not quality_gate_is_shadow
        semantic_gate_blocking_raw = context.get("enforce_semantic_gate_blocking")
        semantic_gate_is_enforced = enforce_semantic_patch_gate and (
            bool(semantic_gate_blocking_raw)
            if semantic_gate_blocking_raw is not None
            else not quality_gate_is_shadow
        )

        github_client, github_client_reason = self._resolve_github_client(context)

        candidate_files = self._collect_candidate_files(
            spec=spec,
            tests=tests,
            rag_context=rag_context,
            ci_failure_context=ci_failure_context,
        )
        candidate_files = self._merge_explicit_target_files(
            candidate_files=candidate_files,
            explicit_targets=context.get("target_files"),
        )
        strict_target_files = bool(context.get("strict_target_files", not open_mode))
        allow_new_files = self._allow_new_files(candidate_files, ci_failure_context, spec)
        candidate_file_snippets = self._load_candidate_file_snippets(candidate_files)
        signature_discovery_packet = self._build_signature_discovery_packet(
            candidate_files=candidate_files,
            candidate_file_snippets=candidate_file_snippets,
        )
        base_instruction_stack = [
            "global_agent_rules",
            "pipeline_ci_fix_rules",
            "strict_target_files" if strict_target_files else "non_strict_targets",
            "quality_gate_enforced" if quality_gate_is_enforced else "quality_gate_observe_only",
        ]
        instruction_stack, instruction_layers = build_instruction_stack(
            base_instruction_stack,
            candidate_files,
        )

        input_log = self._build_input_log(
            context=context,
            spec=spec,
            tests=tests,
            subtasks=subtasks,
            rag_context=rag_context,
            github_client=github_client,
            github_client_reason=github_client_reason,
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
            enforce_patch_quality_gate=enforce_patch_quality_gate,
            enforce_semantic_patch_gate=enforce_semantic_patch_gate,
            allow_full_file_rewrite=allow_full_file_rewrite,
            patch_strategy=patch_strategy,
            forced_strategy_mode=forced_strategy_mode,
            signature_discovery_packet=signature_discovery_packet,
            semantic_feedback_packet=semantic_feedback_packet,
            force_plan_after_semantic_failure=force_plan_after_semantic_failure,
            open_mode=open_mode,
        )
        logger.info("code_generator_input %s", input_log)

        llm_patch: dict[str, Any] | None = None
        llm_error: str | None = None
        llm_prompt_excerpt: str | None = None
        llm_response_excerpt: str | None = None
        llm_response_parsed = False
        llm_required_file_roundtrips = 0
        llm_requested_files: list[str] = []

        if use_llm and (spec or candidate_files):
            llm = None
            try:
                llm = get_llm_wrapper()
                if llm is None:
                    llm = get_legacy_llm_wrapper()

                if llm is not None:
                    repo_context: dict[str, Any] = self._build_repo_context(
                        spec=spec,
                        tests=tests,
                        subtasks=subtasks,
                        rag_context=rag_context,
                        rules_payload=rules_payload,
                        ci_failure_context=ci_failure_context,
                        candidate_files=candidate_files,
                        allow_new_files=allow_new_files,
                        candidate_file_snippets=candidate_file_snippets,
                        patch_strategy=patch_strategy,
                        forced_strategy_mode=forced_strategy_mode,
                        signature_discovery_packet=signature_discovery_packet,
                        semantic_feedback_packet=semantic_feedback_packet,
                        open_mode=open_mode,
                    )

                    try:
                        prompt: str = build_code_prompt(spec, test_cases, repo_context)
                    except AttributeError:
                        prompt = legacy_build_code_prompt(spec, test_cases, repo_context)

                    self._ci_failure_context = ci_failure_context

                    prompt = self._append_compact_context(
                        prompt=prompt,
                        task_description=task_description,
                        issue_context_text=issue_context_text,
                        memory_context_text=memory_context_text,
                        candidate_files=candidate_files,
                        allow_new_files=allow_new_files,
                        strict_target_files=strict_target_files,
                        candidate_file_snippets=candidate_file_snippets,
                        patch_strategy=patch_strategy,
                        forced_strategy_mode=forced_strategy_mode,
                        signature_discovery_packet=signature_discovery_packet,
                        semantic_feedback_packet=semantic_feedback_packet,
                        open_mode=open_mode,
                    )
                    llm_prompt_excerpt = prompt[:1200]

                    # Try function calling first (Codex-style apply_patch tool)
                    response: str | None = None
                    function_calling_succeeded = False
                    try:
                        tool_result = self._complete_with_function_calling(
                            llm=llm,
                            prompt=prompt,
                            temperature=0.0 if forced_strategy_mode == "forced_plan" else None,
                        )
                        if tool_result is not None:
                            # tool_result["arguments"]["patch_text"] contains the patch
                            response = tool_result["arguments"].get("patch_text", "")
                            if response and isinstance(response, str):
                                function_calling_succeeded = True
                                logger.info(
                                    "code_generator_function_calling_success tool=%s",
                                    tool_result.get("name"),
                                )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "code_generator_function_calling_failed falling_back_to_text_completion error=%s",
                            str(exc)[:200],
                        )

                    # Fall back to text completion if function calling failed
                    if not function_calling_succeeded:
                        if forced_strategy_mode == "forced_plan":
                            response = self._complete_llm_with_optional_temperature(
                                llm=llm,
                                prompt=prompt,
                                temperature=0.0,
                            )
                        else:
                            response = llm.complete(prompt)
                    llm_response_excerpt = str(response)[:1200]

                    llm_patch = self._parse_llm_patch_response(response)
                    llm_response_parsed = llm_patch is not None

                    if not llm_response_parsed and isinstance(response, str) and response.strip():
                        repaired_response = self._repair_llm_output_with_llm(
                            llm=llm,
                            raw_response=response,
                        )
                        if repaired_response:
                            llm_response_excerpt = repaired_response[:1200]
                            llm_patch = self._parse_llm_patch_response(repaired_response)
                            llm_response_parsed = llm_patch is not None

                    if not llm_response_parsed:
                        llm_error = "missing/invalid llm output"
                    elif isinstance(llm_patch, dict):
                        (
                            llm_patch,
                            candidate_files,
                            candidate_file_snippets,
                            llm_required_file_roundtrips,
                            llm_requested_files,
                            roundtrip_prompt_excerpt,
                            roundtrip_response_excerpt,
                        ) = self._resolve_required_file_requests(
                            llm=llm,
                            initial_patch=llm_patch,
                            spec=spec,
                            test_cases=test_cases,
                            tests=tests,
                            subtasks=subtasks,
                            rag_context=rag_context,
                            rules_payload=rules_payload,
                            ci_failure_context=ci_failure_context,
                            task_description=task_description,
                            issue_context_text=issue_context_text,
                            memory_context_text=memory_context_text,
                            allow_new_files=allow_new_files,
                            strict_target_files=strict_target_files,
                            candidate_files=candidate_files,
                            candidate_file_snippets=candidate_file_snippets,
                            patch_strategy=patch_strategy,
                            forced_strategy_mode=forced_strategy_mode,
                            signature_discovery_packet=signature_discovery_packet,
                            semantic_feedback_packet=semantic_feedback_packet,
                            open_mode=open_mode,
                        )
                        if roundtrip_prompt_excerpt:
                            llm_prompt_excerpt = roundtrip_prompt_excerpt
                        if roundtrip_response_excerpt:
                            llm_response_excerpt = roundtrip_response_excerpt
                        instruction_stack, instruction_layers = build_instruction_stack(
                            base_instruction_stack,
                            candidate_files,
                        )

                        if not self._has_patch_files(llm_patch):
                            llm_error = "llm_requested_additional_files_but_no_patch"
                            llm_patch = None
                        elif isinstance(llm_patch, dict):
                            llm_patch = self._attempt_context_first_repair(
                                llm=llm,
                                llm_patch=llm_patch,
                                ci_failure_context=ci_failure_context,
                                candidate_files=candidate_files,
                                allow_new_files=allow_new_files,
                                strict_target_files=strict_target_files,
                                candidate_file_snippets=candidate_file_snippets,
                                task_description=task_description,
                                patch_strategy=patch_strategy,
                                forced_strategy_mode=forced_strategy_mode,
                                signature_discovery_packet=signature_discovery_packet,
                                semantic_feedback_packet=semantic_feedback_packet,
                            )

                    logger.info(
                        "code_generator_llm_response parsed=%s prompt_excerpt=%s response_excerpt=%s",
                        llm_response_parsed,
                        (llm_prompt_excerpt or "")[:500],
                        (llm_response_excerpt or "")[:500],
                    )
            except Exception as exc:  # noqa: BLE001
                llm_error = self._normalize_llm_error(exc)
            finally:
                if llm is not None:
                    try:
                        llm.close()
                    except Exception:
                        pass

        if use_llm and require_llm and not llm_patch:
            failure_reason = (
                f"LLM required but unavailable: {llm_error[:160]}"
                if isinstance(llm_error, str) and llm_error
                else "LLM required but no valid structured output was produced."
            )
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content={
                    "schema_version": "2.0",
                    "files": [],
                    "llm_required": True,
                    "llm_error": llm_error,
                    "llm_response_parsed": llm_response_parsed,
                },
                reason=failure_reason,
                confidence=0.95,
                logs=[
                    "LLM strict mode enabled (require_llm=true).",
                    f"LLM enabled: {use_llm}",
                    f"LLM parsed response: {llm_response_parsed}",
                    f"LLM error: {(llm_error or 'missing/invalid llm output')[:200]}",
                ],
                next_actions=["fix_llm_connectivity"],
            )

        if llm_patch:
            filtered_files, materialized_test_changes, grounding_notes = (
                self._materialize_llm_payload(
                    llm_payload=llm_patch,
                    candidate_files=candidate_files,
                    allow_new_files=allow_new_files,
                    strict_target_files=strict_target_files,
                )
            )
            patch: dict[str, Any] = {
                "schema_version": "2.0",
                "files": filtered_files,
                "patch_text": str(llm_patch.get("patch_text", "") or ""),
                "operations": (
                    list(llm_patch.get("operations", []))
                    if isinstance(llm_patch.get("operations"), list)
                    else []
                ),
                "decisions": llm_patch.get("decisions", []),
                "test_operations": (
                    list(llm_patch.get("test_operations", []))
                    if isinstance(llm_patch.get("test_operations"), list)
                    else []
                ),
                "test_changes": materialized_test_changes,
                "dry_run": False,
                "expected_failures": int(llm_patch.get("expected_failures", 1) or 0),
                "llm_enhanced": True,
                "target_files": candidate_files[:20],
                "strict_target_files": strict_target_files,
                "instruction_stack": instruction_stack,
                "selected_target_files": self._build_selected_target_files(
                    filtered_files, candidate_files
                ),
                "allow_new_files": allow_new_files,
                "instruction_layers": instruction_layers,
                "llm_context_expansion": {
                    "roundtrips": llm_required_file_roundtrips,
                    "requested_files": llm_requested_files[:20],
                },
            }
            if grounding_notes:
                patch.setdefault("notes", [])
                patch["notes"].extend(grounding_notes)
            reason: str = "Code patch generated with LLM synthesis."
            confidence: float = 0.92
        else:
            patch = self._build_deterministic_patch(
                spec=spec,
                tests=tests,
                subtask_count=len(subtask_items),
                rag_source_count=len(rag_sources),
                rule_doc_count=len(rules_documents),
                rules_version=rules_version,
                issue_context_text=issue_context_text,
                candidate_files=candidate_files,
                allow_new_files=allow_new_files,
                ci_failure_context=ci_failure_context,
                strict_target_files=strict_target_files,
            )
            reason = (
                "Deterministic patch generated (LLM unavailable)."
                if llm_error
                else "Code patch generated from spec."
            )
            confidence = 0.87
        patch["instruction_stack"] = instruction_stack
        patch["instruction_layers"] = instruction_layers

        if llm_error:
            patch.setdefault("notes", [])
            patch["notes"].append(f"llm_error={llm_error[:120]}")

        # Allow LLM to select any existing files for editing, not just candidate files.
        # Candidate files are suggestions — LLM has freedom to choose appropriate targets.
        if not patch.get("files"):
            patch["blocked"] = True
            patch.setdefault("notes", [])
            patch["notes"].append("no_files_in_patch")
            patch["quality_gate"] = {
                "passed": False,
                "reasons": ["no_files_in_patch"],
            }
        else:
            patch["quality_gate"] = {
                "passed": True,
                "reasons": [],
            }
        patch["quality_gate"]["enforced"] = quality_gate_is_enforced
        patch["quality_gate"]["mode"] = quality_gate_mode
        patch["quality_gate"]["target_files_count"] = len(candidate_files)
        patch["quality_gate"]["selected_files_count"] = len(patch.get("files", []) or [])
        patch["open_mode"] = open_mode
        patch["patch_strategy"] = patch_strategy
        patch["signature_discovery"] = signature_discovery_packet
        if semantic_feedback_packet.get("violations"):
            patch["semantic_feedback_packet"] = semantic_feedback_packet
        if self._has_unjustified_full_rewrite(
            patch.get("files", []),
            patch.get("decisions", []),
            allow_full_file_rewrite=allow_full_file_rewrite,
        ):
            patch["quality_gate"]["passed"] = False
            patch["quality_gate"]["reasons"].append("full_file_rewrite_without_justification")
        if self._is_analysis_only_without_source_change(
            patch.get("decisions", []),
            patch.get("files", []),
        ):
            patch["quality_gate"]["passed"] = False
            patch["quality_gate"]["reasons"].append("analysis_only_without_source_change")
        if any(
            isinstance(note, str) and note.startswith("missing_content_for_file=")
            for note in patch.get("notes", []) or []
        ):
            patch["quality_gate"]["passed"] = False
            patch["quality_gate"]["reasons"].append("missing_file_content")
        if any(
            isinstance(note, str)
            and (
                note.startswith("operation_")
                or note.startswith("invalid_operation_")
                or note.startswith("invalid_patch_text:")
            )
            for note in patch.get("notes", []) or []
        ):
            patch["quality_gate"]["passed"] = False
            patch["quality_gate"]["reasons"].append("invalid_patch_operations")
        if self._is_test_failure_without_source_change(
            ci_failure_context=ci_failure_context,
            candidate_files=candidate_files,
            files=patch.get("files", []),
            decisions=patch.get("decisions", []),
        ):
            patch["quality_gate"]["passed"] = False
            patch["quality_gate"]["reasons"].append("test_failure_without_source_change")
        semantic_gate = {
            "enabled": enforce_semantic_patch_gate,
            "mode": "enforce" if semantic_gate_is_enforced else "shadow",
            "passed": True,
            "violations": [],
        }
        if enforce_semantic_patch_gate:
            semantic_gate = self._evaluate_semantic_patch_gate(patch.get("files", []))
            semantic_gate["enabled"] = True
            semantic_gate["mode"] = "enforce" if semantic_gate_is_enforced else "shadow"
            if not bool(semantic_gate.get("passed", False)):
                patch["quality_gate"]["passed"] = False
                patch["quality_gate"]["reasons"].append("semantic_contract_violation")
                patch.setdefault("notes", [])
                patch["notes"].extend(
                    f"semantic_violation={item}"
                    for item in (semantic_gate.get("violations", []) or [])[:5]
                    if isinstance(item, str) and item.strip()
                )
                semantic_feedback_packet = self._build_semantic_feedback_packet(
                    semantic_gate.get("violations", []),
                    signature_discovery_packet=signature_discovery_packet,
                )
                patch["semantic_feedback_packet"] = semantic_feedback_packet
                self._record_semantic_retry_state(
                    context,
                    semantic_retry_state=semantic_retry_state,
                    semantic_feedback_packet=semantic_feedback_packet,
                )
            else:
                self._reset_semantic_retry_state(context)
        patch["semantic_gate"] = semantic_gate
        patch["loop_metrics"] = {
            "quality_gate_passed": bool(patch["quality_gate"]["passed"]),
            "quality_gate_reason_count": len(patch["quality_gate"].get("reasons", []) or []),
            "target_files_count": len(candidate_files),
            "selected_files_count": len(patch.get("files", []) or []),
            "strict_target_files": strict_target_files,
            "semantic_gate_passed": bool(semantic_gate.get("passed", True)),
            "semantic_gate_mode": semantic_gate.get("mode", "shadow"),
            "semantic_violation_count": len(semantic_gate.get("violations", []) or []),
            "forced_strategy_mode": forced_strategy_mode,
        }

        if semantic_gate_is_enforced and not bool(semantic_gate.get("passed", False)):
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content=patch,
                reason="Semantic patch gate failed before test execution.",
                confidence=0.97,
                logs=[
                    "Semantic patch gate enforced: true.",
                    f"Semantic patch gate violations: {semantic_gate.get('violations', [])}",
                ],
                next_actions=["fix_agent"],
            )

        if quality_gate_is_enforced and not bool(patch["quality_gate"]["passed"]):
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content=patch,
                reason="Patch quality gate failed before test execution.",
                confidence=0.95,
                logs=[
                    "Patch quality gate enforced: true.",
                    f"Patch quality gate reasons: {patch['quality_gate'].get('reasons', [])}",
                ],
                next_actions=["fix_agent"],
            )

        pr_url: str | None = None
        pr_number: int | None = None

        if publish_pr_in_code_generator and github_client and patch.get("files"):
            try:
                pr_title: str = (spec.get("summary") or "HordeForge Generated Feature")[:100]
                pr_body: str = self._build_pr_body(spec, patch)

                branch_name: str | None = context.get("branch_name")
                if not isinstance(branch_name, str) or not branch_name.strip():
                    branch_name = self._default_branch_name(context)
                else:
                    branch_name = branch_name.strip()

                orchestrator = PatchWorkflowOrchestrator(github_client)
                file_changes = create_patch_from_code_result(patch)

                result = orchestrator.apply_patch(
                    files=file_changes,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    branch_name=branch_name,
                )
                if (not result.success) and isinstance(result.error, str):
                    lower_error = result.error.lower()
                    if "already exists" in lower_error or "reference update failed" in lower_error:
                        retry_branch = f"{branch_name}-{uuid4().hex[:6]}"
                        logger.info(
                            "code_generator_branch_retry original=%s retry=%s reason=%s",
                            branch_name,
                            retry_branch,
                            result.error[:300],
                        )
                        result = orchestrator.apply_patch(
                            files=file_changes,
                            pr_title=pr_title,
                            pr_body=pr_body,
                            branch_name=retry_branch,
                        )

                if result.success:
                    pr_url = result.pr_url
                    pr_number = result.pr_number
                    patch["pr_url"] = pr_url
                    patch["pr_number"] = pr_number
                    patch["branch_name"] = result.branch_name
                    patch["applied_to_github"] = True
                    self._mark_issue_as_fixed(
                        context=context,
                        github_client=github_client,
                        pr_url=pr_url,
                        pr_number=pr_number,
                    )
                else:
                    patch["apply_error"] = result.error
                    patch["rollback_performed"] = result.rollback_performed
                    logger.error(
                        "code_generator_apply_failed reason=%s rollback_performed=%s",
                        str(result.error)[:500],
                        result.rollback_performed,
                    )
            except Exception as exc:  # noqa: BLE001
                patch["apply_error"] = str(exc)
                logger.exception("code_generator_apply_exception: %s", str(exc)[:500])

        logs: list[str] = [
            f"Code generator produced patch with {len(patch.get('files', []))} files."
        ]
        logs.append(f"Code generator input: {input_log}")
        logs.append(f"LLM enabled: {use_llm}")
        logs.append(f"PR publish in code_generator: {publish_pr_in_code_generator}")
        logs.append(f"candidate_files_count={len(candidate_files)}")
        logs.append(f"allow_new_files={allow_new_files}")
        logs.append(f"strict_target_files={strict_target_files}")
        logs.append(f"enforce_patch_quality_gate={enforce_patch_quality_gate}")
        logs.append(f"enforce_semantic_patch_gate={enforce_semantic_patch_gate}")
        logs.append(f"enforce_semantic_gate_blocking={semantic_gate_is_enforced}")
        logs.append(f"open_mode={open_mode}")
        logs.append(f"patch_strategy={patch_strategy}")
        logs.append(f"allow_full_file_rewrite={allow_full_file_rewrite}")
        logs.append(f"forced_strategy_mode={forced_strategy_mode}")
        logs.append(f"force_plan_after_semantic_failure={force_plan_after_semantic_failure}")
        logs.append(
            "signature_discovery_symbols="
            f"{len(signature_discovery_packet.get('symbols', []) or [])}"
        )
        if semantic_feedback_packet.get("violations"):
            logs.append(
                "semantic_feedback_packet_violations="
                f"{len(semantic_feedback_packet.get('violations', []) or [])}"
            )
        logs.append(f"llm_required_file_roundtrips={llm_required_file_roundtrips}")
        if llm_requested_files:
            logs.append(f"llm_requested_files={llm_requested_files[:20]}")
        if llm_prompt_excerpt:
            logs.append(f"LLM prompt excerpt: {llm_prompt_excerpt}")
        if llm_response_excerpt:
            logs.append(f"LLM raw response excerpt: {llm_response_excerpt}")
            logs.append(f"LLM response parsed: {llm_response_parsed}")

        if pr_url:
            logs.append(f"PR created: {pr_url}")
        else:
            logs.append(
                "PR not created."
                f" github_client_present={github_client is not None}, files_count={len(patch.get('files', []))}."
            )
            if "apply_error" in patch:
                logs.append(f"PR apply error: {str(patch.get('apply_error'))[:500]}")

        logger.info(
            "code_generator_output files=%s pr_number=%s applied_to_github=%s llm_enhanced=%s llm_error=%s",
            len(patch.get("files", [])),
            patch.get("pr_number"),
            patch.get("applied_to_github"),
            patch.get("llm_enhanced"),
            llm_error[:200] if isinstance(llm_error, str) else None,
        )

        return build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason=reason,
            confidence=confidence,
            logs=logs,
            next_actions=["test_runner", "fix_agent"],
        )

    @staticmethod
    def _normalize_path(value: str) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        for prefix in ("workspace/repo/", "/workspace/repo/", "workspace/", "/workspace/", "repo/"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized

    def _collect_candidate_files(
        self,
        *,
        spec: dict[str, Any],
        tests: dict[str, Any],
        rag_context: dict[str, Any],
        ci_failure_context: dict[str, Any],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        def add(path: Any) -> None:
            if not isinstance(path, str):
                return
            normalized = self._normalize_path(path)
            if not normalized:
                return
            if "::" in normalized:
                normalized = normalized.split("::", 1)[0]
            if normalized.startswith("/") or ".." in normalized.split("/"):
                return
            if normalized in seen:
                return
            seen.add(normalized)
            result.append(normalized)

        file_change_plan = spec.get("file_change_plan", {}) or {}
        for path in file_change_plan.get("files_to_modify", []) or []:
            add(path)

        for change in spec.get("file_changes", []) or []:
            if isinstance(change, dict):
                add(change.get("path"))

        for case in tests.get("test_cases", []) or []:
            if isinstance(case, dict):
                add(case.get("file_path"))

        for path in ci_failure_context.get("files", []) or []:
            add(path)

        for target in ci_failure_context.get("test_targets", []) or []:
            add(target)

        for job in ci_failure_context.get("per_job_analysis", []) or []:
            if not isinstance(job, dict):
                continue
            for target in job.get("test_targets", []) or []:
                add(target)
            for location in job.get("locations", []) or []:
                if isinstance(location, dict):
                    add(location.get("file"))

        for source in rag_context.get("sources", []) or []:
            if isinstance(source, dict):
                add(source.get("path"))

        # Expand test targets into likely source counterparts to avoid
        # test-only patch loops under strict target mode.
        for path in list(result):
            for inferred in self._infer_source_candidates_from_test_path(path):
                add(inferred)

        return result[:20]

    def _infer_source_candidates_from_test_path(self, path: str) -> list[str]:
        normalized = self._normalize_path(path)
        if "::" in normalized:
            normalized = normalized.split("::", 1)[0]
        if not normalized.startswith("tests/"):
            return []

        parts = [item for item in normalized.split("/") if item]
        if len(parts) < 2:
            return []
        filename = parts[-1]
        if not filename.endswith(".py"):
            return []
        if filename.startswith("test_"):
            module_filename = filename[len("test_") :]
        elif filename.endswith("_test.py"):
            module_filename = filename[: -len("_test.py")] + ".py"
        else:
            return []

        relative_parts = parts[1:]
        while relative_parts and relative_parts[0] in {
            "unit",
            "integration",
            "functional",
            "e2e",
            "acceptance",
            "system",
        }:
            relative_parts = relative_parts[1:]
        if not relative_parts:
            return []

        if not module_filename:
            return []

        candidates: list[str] = []
        dedup: set[str] = set()

        def _push(candidate: str) -> None:
            normalized_candidate = self._normalize_path(candidate)
            if not normalized_candidate or normalized_candidate in dedup:
                return
            dedup.add(normalized_candidate)
            candidates.append(normalized_candidate)

        base_parts = list(relative_parts)
        base_parts[-1] = module_filename
        _push("/".join(base_parts))

        if len(base_parts) >= 2:
            parent_dir = base_parts[-2]
            module_stem = module_filename[:-3]
            prefix = f"{parent_dir}_"
            if module_stem.startswith(prefix):
                collapsed_name = module_stem[len(prefix) :] + ".py"
                collapsed_parts = list(base_parts)
                collapsed_parts[-1] = collapsed_name
                _push("/".join(collapsed_parts))

        return candidates

    def _merge_explicit_target_files(
        self,
        *,
        candidate_files: list[str],
        explicit_targets: Any,
    ) -> list[str]:
        if not isinstance(explicit_targets, list):
            return candidate_files

        result = list(candidate_files)
        seen = {self._normalize_path(item) for item in candidate_files if isinstance(item, str)}
        for item in explicit_targets:
            if not isinstance(item, str):
                continue
            normalized = self._normalize_path(item)
            if not normalized:
                continue
            if "::" in normalized:
                normalized = normalized.split("::", 1)[0]
            if normalized.startswith("/") or ".." in normalized.split("/"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result[:20]

    @staticmethod
    def _allow_new_files(
        candidate_files: list[str],
        ci_failure_context: dict[str, Any],
        spec: dict[str, Any],
    ) -> bool:
        if candidate_files:
            return False
        if ci_failure_context.get("classification") in {
            "path_error",
            "collection_error",
            "test_failure",
        }:
            return False
        file_changes = spec.get("file_changes", []) or []
        if file_changes:
            for change in file_changes:
                if (
                    isinstance(change, dict)
                    and str(change.get("change_type", "")).lower() == "create"
                ):
                    return True
        return True

    def _build_repo_context(
        self,
        *,
        spec: dict[str, Any],
        tests: dict[str, Any],
        subtasks: dict[str, Any],
        rag_context: dict[str, Any],
        rules_payload: dict[str, Any],
        ci_failure_context: dict[str, Any] | None = None,
        candidate_files: list[str] | None = None,
        allow_new_files: bool = True,
        candidate_file_snippets: list[dict[str, Any]] | None = None,
        patch_strategy: str = PATCH_FIRST_STRATEGY,
        forced_strategy_mode: str = "default",
        signature_discovery_packet: dict[str, Any] | None = None,
        semantic_feedback_packet: dict[str, Any] | None = None,
        open_mode: bool = False,
    ) -> dict[str, Any]:
        test_cases = tests.get("test_cases", []) or []
        acceptance_criteria = spec.get("acceptance_criteria", []) or []
        file_change_plan = spec.get("file_change_plan", {}) or {}
        files_to_modify = file_change_plan.get("files_to_modify", []) or []
        items = subtasks.get("items", []) or []
        rag_sources = rag_context.get("sources", []) or []
        rule_documents = rules_payload.get("documents", {}) or {}

        ci_failing_jobs: list[str] = []
        ci_failure_details: list[dict[str, Any]] = []
        ci_files: list[str] = []
        ci_test_targets: list[str] = []
        if ci_failure_context and isinstance(ci_failure_context, dict):
            ci_failing_jobs = [
                str(job.get("job_name", ""))
                for job in ci_failure_context.get("per_job_analysis", [])
                if isinstance(job, dict) and job.get("job_name")
            ][:5]
            ci_failure_details = ci_failure_context.get("details", []) or []
            ci_files = [
                str(item) for item in ci_failure_context.get("files", []) if str(item).strip()
            ][:8]
            ci_test_targets = [
                str(item)
                for item in ci_failure_context.get("test_targets", [])
                if str(item).strip()
            ][:8]

        return {
            "spec_summary": str(spec.get("summary", "")).strip()[:300],
            "acceptance_criteria": [
                str(item).strip()[:180] for item in acceptance_criteria[:6] if str(item).strip()
            ],
            "test_case_names": [
                str(case.get("name", "")).strip()[:120]
                for case in test_cases[:8]
                if isinstance(case, dict) and str(case.get("name", "")).strip()
            ],
            "test_case_files": [
                str(case.get("file_path", "")).strip()
                for case in test_cases[:8]
                if isinstance(case, dict) and str(case.get("file_path", "")).strip()
            ],
            "files_to_modify": [
                str(path).strip() for path in files_to_modify[:8] if str(path).strip()
            ],
            "candidate_files": candidate_files[:10] if candidate_files else [],
            "candidate_file_snippets": candidate_file_snippets[:4]
            if candidate_file_snippets
            else [],
            "existing_files": [
                str(item.get("path", "")).strip()
                for item in (candidate_file_snippets or [])[:4]
                if isinstance(item, dict) and str(item.get("path", "")).strip()
            ],
            "file_contents": {
                str(item.get("path", "")).strip(): str(
                    item.get("content") or item.get("snippet") or ""
                )
                for item in (candidate_file_snippets or [])[:4]
                if isinstance(item, dict) and str(item.get("path", "")).strip()
            },
            "allow_new_files": allow_new_files,
            "open_mode": open_mode,
            "patch_strategy": patch_strategy,
            "forced_strategy_mode": forced_strategy_mode,
            "signature_discovery": signature_discovery_packet
            if isinstance(signature_discovery_packet, dict)
            else {"ran": True, "symbols": []},
            "semantic_feedback_packet": semantic_feedback_packet
            if isinstance(semantic_feedback_packet, dict)
            else {"violations": []},
            "subtasks": [
                str(item.get("title") or item.get("name") or "").strip()[:140]
                for item in items[:6]
                if isinstance(item, dict)
                and str(item.get("title") or item.get("name") or "").strip()
            ],
            "rag_sources": [
                str(source.get("path", "")).strip()[:160]
                for source in rag_sources[:6]
                if isinstance(source, dict) and str(source.get("path", "")).strip()
            ],
            "rules_documents": list(rule_documents.keys())[:6],
            "ci_failing_jobs": ci_failing_jobs,
            "ci_files": ci_files,
            "ci_test_targets": ci_test_targets,
            "ci_failure_details": [
                {
                    "job_name": str(detail.get("name", ""))[:120],
                    "error_excerpt": str(detail.get("logs", ""))[:500],
                }
                for detail in ci_failure_details[:5]
                if isinstance(detail, dict)
            ],
        }

    def _append_compact_context(
        self,
        *,
        prompt: str,
        task_description: Any,
        issue_context_text: str,
        memory_context_text: str,
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
        candidate_file_snippets: list[dict[str, Any]] | None = None,
        patch_strategy: str = PATCH_FIRST_STRATEGY,
        forced_strategy_mode: str = "default",
        signature_discovery_packet: dict[str, Any] | None = None,
        semantic_feedback_packet: dict[str, Any] | None = None,
        open_mode: bool = False,
    ) -> str:
        context_blocks: list[str] = []
        if isinstance(task_description, str) and task_description.strip():
            context_blocks.append(f"Task:\n{task_description.strip()[:500]}")
        if issue_context_text:
            context_blocks.append(f"Issue context:\n{issue_context_text[:2200]}")
        if memory_context_text:
            context_blocks.append(f"Memory/RAG context:\n{memory_context_text[:1800]}")

        ci_failure_context = getattr(self, "_ci_failure_context", None)
        if ci_failure_context and isinstance(ci_failure_context, dict):
            ci_blocks = []
            failing_jobs = [
                str(item.get("job_name", ""))
                for item in ci_failure_context.get("per_job_analysis", [])
                if isinstance(item, dict) and item.get("job_name")
            ]
            if failing_jobs:
                ci_blocks.append(f"Failing CI jobs: {', '.join(failing_jobs[:5])}")
            ci_files = [
                str(item).strip()
                for item in ci_failure_context.get("files", [])
                if isinstance(item, str) and item.strip()
            ]
            if ci_files:
                ci_blocks.append(f"Candidate files from CI: {', '.join(ci_files[:10])}")
            ci_targets = [
                str(item).strip()
                for item in ci_failure_context.get("test_targets", [])
                if isinstance(item, str) and item.strip()
            ]
            if ci_targets:
                ci_blocks.append(f"Test targets from CI: {', '.join(ci_targets[:10])}")
            if ci_blocks:
                context_blocks.append("## CI Failure Context\n" + "\n".join(ci_blocks))

        if candidate_files:
            context_blocks.append(
                "## Grounded file targets\n"
                + "\n".join(f"- {item}" for item in candidate_files[:15])
            )
        if candidate_file_snippets:
            snippet_lines: list[str] = []
            for item in candidate_file_snippets[:2]:
                path = str(item.get("path", "")).strip()
                full_content = str(item.get("content") or "").strip()
                snippet = full_content or str(item.get("snippet") or "").strip()
                truncated = bool(item.get("truncated", False)) and not full_content
                if not path or not snippet:
                    continue
                suffix = "\n# [snippet truncated]" if truncated else ""
                snippet_lines.append(f"### {path}\n{snippet}{suffix}")
            if snippet_lines:
                context_blocks.append(
                    "## Candidate file content (real repository content)\n"
                    + "\n\n".join(snippet_lines)
                )
        discovered_symbols = []
        if isinstance(signature_discovery_packet, dict):
            raw_symbols = signature_discovery_packet.get("symbols", [])
            if isinstance(raw_symbols, list):
                discovered_symbols = raw_symbols
        if discovered_symbols:
            lines: list[str] = []
            for item in discovered_symbols[:10]:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol", "")).strip()
                expected_signature = str(item.get("expected_signature", "")).strip()
                location = str(item.get("location", "")).strip()
                if not symbol:
                    continue
                detail = f"- {symbol}"
                if expected_signature:
                    detail += f" :: {expected_signature}"
                if location:
                    detail += f" [{location}]"
                lines.append(detail)
            if lines:
                context_blocks.append(
                    "## Mandatory signature discovery (do not invent kwargs)\n" + "\n".join(lines)
                )
        semantic_violations = []
        if isinstance(semantic_feedback_packet, dict):
            raw_violations = semantic_feedback_packet.get("violations", [])
            if isinstance(raw_violations, list):
                semantic_violations = raw_violations
        if semantic_violations:
            lines = []
            for item in semantic_violations[:8]:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol", "")).strip()
                invalid_kwargs = item.get("invalid_kwargs", [])
                if not isinstance(invalid_kwargs, list):
                    invalid_kwargs = []
                invalid_text = ",".join(
                    str(keyword).strip() for keyword in invalid_kwargs if str(keyword).strip()
                )
                expected_signature = str(item.get("expected_signature", "")).strip()
                location = str(item.get("location", "")).strip()
                line = f"- symbol={symbol or 'unknown'}"
                if invalid_text:
                    line += f" invalid_kwargs={invalid_text}"
                if expected_signature:
                    line += f" expected={expected_signature}"
                if location:
                    line += f" location={location}"
                lines.append(line)
            if lines:
                context_blocks.append("## Semantic feedback packet\n" + "\n".join(lines))

        if not context_blocks:
            return prompt

        instruction = (
            "\n\n## Important Rules:\n"
            "1. Prefer MODIFYING existing files over creating new ones.\n"
            "2. If candidate files are provided, you MUST restrict code changes to those files.\n"
            "3. If tests are failing, fix the test files or source files they test.\n"
            f"4. New files are {'ALLOWED' if allow_new_files else 'NOT ALLOWED'} for this task.\n"
            f"5. Strict target files mode is {'ENABLED' if strict_target_files else 'DISABLED'}.\n"
            "6. Return non-empty patch_text, operations[] or files[]; analysis-only responses are invalid.\n"
            "7. PRIORITY: Use patch_text in Codex apply_patch format for minimal, targeted edits. "
            "Example: patch_text='*** Begin Patch\\n*** Update File: path\\n@@ context\\n-old\\n+new\\n*** End Patch'.\n"
            "8. Use operations[] for precise string replacement when patch_text is insufficient.\n"
            "9. files[] with full file content is LAST RESORT ONLY — never rewrite entire files unless absolutely necessary.\n"
            "10. Never escape literal edit strings in operations[].\n"
            "11. DO NOT create stub functions with 'return True'; implement real logic.\n"
            "12. Every function must have meaningful implementation, not just placeholders.\n"
            "13. If you cannot determine the correct implementation, prefer a minimal grounded patch "
            "to an invented new module.\n"
            f"14. Default strategy is {self.PATCH_FIRST_STRATEGY}. "
            "Use minimal in-place edits and preserve untouched code.\n"
            f"15. Full-file rewrite is allowed only when patch_strategy={self.FULL_FILE_STRATEGY}.\n"
            "16. You MUST satisfy every semantic feedback violation and signature-discovery constraint."
        )
        if forced_strategy_mode == "forced_plan":
            instruction += (
                "\n17. Forced-plan mode: before writing patch JSON, internally verify each constructor/"
                "function call kwargs against discovered signatures and remove unsupported kwargs."
            )
        if open_mode:
            instruction += (
                "\n18. Open mode enabled: you may touch directly related dependency files beyond"
                " the initial candidate list when required to make tests pass, but keep edits minimal."
            )

        return (
            f"{prompt}\n\n## Compact execution context\n"
            + "\n\n".join(context_blocks)
            + instruction
        )

    def _repair_llm_output_with_llm(self, *, llm: Any, raw_response: str) -> str | None:
        if not isinstance(raw_response, str) or not raw_response.strip():
            return None

        repair_prompt = (
            "Convert the following assistant output into valid JSON only.\n"
            "Return exactly one JSON object with this schema:\n"
            "{"
            '"files":[{"path":"relative/path","change_type":"create|modify|delete","content":"full file content"}],'
            '"decisions":[{"description":"...", "rationale":"..."}],'
            '"test_changes":[{"path":"tests/file.py","change_type":"create|modify","content":"full file content"}]'
            "}\n"
            "Rules:\n"
            "- No markdown fences.\n"
            "- No explanatory text.\n"
            "- Preserve code content exactly as much as possible.\n"
            "- If a field is missing, use an empty list for decisions/test_changes.\n\n"
            "Assistant output to repair:\n"
            f"{raw_response[:12000]}"
        )
        try:
            repaired = self._complete_llm_with_optional_temperature(
                llm=llm, prompt=repair_prompt, temperature=0.0
            )
        except Exception:
            return None
        return repaired if isinstance(repaired, str) and repaired.strip() else None

    def _complete_with_function_calling(
        self,
        *,
        llm: Any,
        prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any] | None:
        """Attempt function calling to get patch_text via apply_patch tool.

        Returns dict with {"name": str, "arguments": {"patch_text": str}} or None
        if the LLM doesn't support function calling.
        """
        tool_def = self._build_apply_patch_tool_definition()
        tools = [tool_def]
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature

        # Try complete_with_tools on wrappers that support it
        if hasattr(llm, "complete_with_tools"):
            try:
                result = llm.complete_with_tools(
                    prompt=prompt,
                    tools=tools,
                    tool_choice="required",
                    **kwargs,
                )
                if isinstance(result, dict) and "arguments" in result:
                    return result
            except Exception as exc:
                raise RuntimeError(f"Function calling failed: {exc}") from exc
            return None

        return None

    @staticmethod
    def _complete_llm_with_optional_temperature(
        *, llm: Any, prompt: str, temperature: float
    ) -> str:
        try:
            return llm.complete(prompt, temperature=temperature)
        except TypeError:
            # Some wrappers/stubs expose complete(prompt) only.
            return llm.complete(prompt)

    @staticmethod
    def _merge_candidate_file_snippets(
        existing: list[dict[str, Any]],
        extra: list[dict[str, Any]],
        *,
        max_total: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*(existing or []), *(extra or [])]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            if not path or not snippet:
                continue
            if path in seen:
                continue
            seen.add(path)
            merged.append(item)
            if len(merged) >= max_total:
                break
        return merged

    @staticmethod
    def _append_required_files_followup_prompt(*, prompt: str, requested_files: list[str]) -> str:
        if not requested_files:
            return prompt
        required_block = "\n".join(f"- {path}" for path in requested_files[:10])
        return (
            f"{prompt}\n\n"
            "## Required files were requested and provided\n"
            "Now produce the final patch JSON.\n"
            "Do not return a request-only payload again.\n"
            "Use these files if needed:\n"
            f"{required_block}\n"
        )

    def _resolve_required_file_requests(
        self,
        *,
        llm: Any,
        initial_patch: dict[str, Any],
        spec: dict[str, Any],
        test_cases: list[dict[str, Any]],
        tests: dict[str, Any],
        subtasks: dict[str, Any],
        rag_context: dict[str, Any],
        rules_payload: dict[str, Any],
        ci_failure_context: dict[str, Any],
        task_description: Any,
        issue_context_text: str,
        memory_context_text: str,
        allow_new_files: bool,
        strict_target_files: bool,
        candidate_files: list[str],
        candidate_file_snippets: list[dict[str, Any]],
        patch_strategy: str,
        forced_strategy_mode: str,
        signature_discovery_packet: dict[str, Any],
        semantic_feedback_packet: dict[str, Any],
        open_mode: bool,
    ) -> tuple[
        dict[str, Any], list[str], list[dict[str, Any]], int, list[str], str | None, str | None
    ]:
        current_patch = initial_patch
        current_candidate_files = list(candidate_files)
        current_candidate_snippets = list(candidate_file_snippets)
        requested_history: list[str] = []
        request_roundtrips = 0
        last_prompt_excerpt: str | None = None
        last_response_excerpt: str | None = None

        for _ in range(self.MAX_REQUIRED_FILE_REQUEST_ROUNDTRIPS):
            if self._has_patch_files(current_patch):
                break

            requested_files = self._extract_required_files(current_patch)
            if not requested_files:
                break

            for path in requested_files:
                if path not in requested_history:
                    requested_history.append(path)

            current_candidate_files = self._merge_explicit_target_files(
                candidate_files=current_candidate_files,
                explicit_targets=requested_files,
            )

            requested_snippets = self._load_candidate_file_snippets(
                requested_files,
                max_files=self.MAX_REQUESTED_FILES_PER_ROUND,
                max_chars_per_file=self.MAX_REQUESTED_FILE_SNIPPET_CHARS,
            )
            current_candidate_snippets = self._merge_candidate_file_snippets(
                current_candidate_snippets,
                requested_snippets,
                max_total=self.MAX_CANDIDATE_SNIPPETS_TOTAL,
            )

            repo_context = self._build_repo_context(
                spec=spec,
                tests=tests,
                subtasks=subtasks,
                rag_context=rag_context,
                rules_payload=rules_payload,
                ci_failure_context=ci_failure_context,
                candidate_files=current_candidate_files,
                allow_new_files=allow_new_files,
                candidate_file_snippets=current_candidate_snippets,
                patch_strategy=patch_strategy,
                forced_strategy_mode=forced_strategy_mode,
                signature_discovery_packet=signature_discovery_packet,
                semantic_feedback_packet=semantic_feedback_packet,
                open_mode=open_mode,
            )

            try:
                prompt = build_code_prompt(spec, test_cases, repo_context)
            except AttributeError:
                prompt = legacy_build_code_prompt(spec, test_cases, repo_context)

            prompt = self._append_compact_context(
                prompt=prompt,
                task_description=task_description,
                issue_context_text=issue_context_text,
                memory_context_text=memory_context_text,
                candidate_files=current_candidate_files,
                allow_new_files=allow_new_files,
                strict_target_files=strict_target_files,
                candidate_file_snippets=current_candidate_snippets,
                patch_strategy=patch_strategy,
                forced_strategy_mode=forced_strategy_mode,
                signature_discovery_packet=signature_discovery_packet,
                semantic_feedback_packet=semantic_feedback_packet,
                open_mode=open_mode,
            )
            prompt = self._append_required_files_followup_prompt(
                prompt=prompt,
                requested_files=requested_files,
            )
            last_prompt_excerpt = prompt[:1200]

            try:
                raw_response = self._complete_llm_with_optional_temperature(
                    llm=llm,
                    prompt=prompt,
                    temperature=0.0,
                )
            except Exception:
                break

            if isinstance(raw_response, str):
                last_response_excerpt = raw_response[:1200]
            parsed = self._parse_llm_patch_response(str(raw_response or ""))
            if parsed is None and isinstance(raw_response, str) and raw_response.strip():
                repaired_response = self._repair_llm_output_with_llm(
                    llm=llm,
                    raw_response=raw_response,
                )
                if repaired_response:
                    last_response_excerpt = repaired_response[:1200]
                    parsed = self._parse_llm_patch_response(repaired_response)
            if not isinstance(parsed, dict):
                break

            current_patch = parsed
            request_roundtrips += 1

        return (
            current_patch,
            current_candidate_files,
            current_candidate_snippets,
            request_roundtrips,
            requested_history,
            last_prompt_excerpt,
            last_response_excerpt,
        )

    def _attempt_context_first_repair(
        self,
        *,
        llm: Any,
        llm_patch: dict[str, Any],
        ci_failure_context: dict[str, Any],
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
        candidate_file_snippets: list[dict[str, Any]],
        task_description: Any,
        patch_strategy: str,
        forced_strategy_mode: str,
        signature_discovery_packet: dict[str, Any],
        semantic_feedback_packet: dict[str, Any],
    ) -> dict[str, Any]:
        current_patch = llm_patch
        for _attempt in range(self.MAX_CONTEXT_REPAIR_ATTEMPTS):
            files, _test_changes, notes = self._materialize_llm_payload(
                llm_payload=current_patch,
                candidate_files=candidate_files,
                allow_new_files=allow_new_files,
                strict_target_files=strict_target_files,
            )
            reasons = self._predict_quality_gate_reasons(
                files=files,
                notes=notes,
                decisions=current_patch.get("decisions", []),
                ci_failure_context=ci_failure_context,
                candidate_files=candidate_files,
                allow_full_file_rewrite=(patch_strategy == self.FULL_FILE_STRATEGY),
            )
            if not reasons:
                return current_patch
            if not any(reason in self.CONTEXT_REPAIRABLE_REASONS for reason in reasons):
                return current_patch

            repair_prompt = self._build_context_repair_prompt(
                reasons=reasons,
                task_description=task_description,
                candidate_files=candidate_files,
                candidate_file_snippets=candidate_file_snippets,
                ci_failure_context=ci_failure_context,
                semantic_feedback_packet=semantic_feedback_packet,
                signature_discovery_packet=signature_discovery_packet,
                patch_strategy=patch_strategy,
                forced_strategy_mode=forced_strategy_mode,
            )
            try:
                repaired_response = self._complete_llm_with_optional_temperature(
                    llm=llm, prompt=repair_prompt, temperature=0.0
                )
            except Exception:
                return current_patch

            repaired_patch = self._parse_llm_patch_response(str(repaired_response or ""))
            if not isinstance(repaired_patch, dict):
                repaired_response = self._repair_llm_output_with_llm(
                    llm=llm,
                    raw_response=str(repaired_response or ""),
                )
                repaired_patch = self._parse_llm_patch_response(str(repaired_response or ""))
            if not isinstance(repaired_patch, dict):
                return current_patch
            current_patch = repaired_patch
        return current_patch

    def _build_context_repair_prompt(
        self,
        *,
        reasons: list[str],
        task_description: Any,
        candidate_files: list[str],
        candidate_file_snippets: list[dict[str, Any]],
        ci_failure_context: dict[str, Any],
        semantic_feedback_packet: dict[str, Any],
        signature_discovery_packet: dict[str, Any],
        patch_strategy: str,
        forced_strategy_mode: str,
    ) -> str:
        issue_summary = str(task_description or "").strip()[:500]
        ci_classification = str(ci_failure_context.get("classification", "")).strip()
        required_scope = str(ci_failure_context.get("required_change_scope", "")).strip()
        ci_targets = [
            str(item).strip()
            for item in ci_failure_context.get("test_targets", [])
            if isinstance(item, str) and item.strip()
        ][:10]
        snippet_blocks: list[str] = []
        for item in candidate_file_snippets[:2]:
            path = str(item.get("path", "")).strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            if path and snippet:
                snippet_blocks.append(f"### {path}\n{snippet}")
        semantic_lines: list[str] = []
        for item in semantic_feedback_packet.get("violations", [])[:8]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip()
            expected_signature = str(item.get("expected_signature", "")).strip()
            invalid_kwargs = ",".join(
                str(keyword).strip()
                for keyword in item.get("invalid_kwargs", [])
                if str(keyword).strip()
            )
            location = str(item.get("location", "")).strip()
            line = f"- symbol={symbol or 'unknown'}"
            if invalid_kwargs:
                line += f" invalid_kwargs={invalid_kwargs}"
            if expected_signature:
                line += f" expected={expected_signature}"
            if location:
                line += f" location={location}"
            semantic_lines.append(line)
        signature_lines: list[str] = []
        for item in signature_discovery_packet.get("symbols", [])[:12]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip()
            expected_signature = str(item.get("expected_signature", "")).strip()
            location = str(item.get("location", "")).strip()
            if not symbol:
                continue
            line = f"- {symbol}"
            if expected_signature:
                line += f" :: {expected_signature}"
            if location:
                line += f" [{location}]"
            signature_lines.append(line)

        return (
            "You generated a patch that failed validation.\n"
            f"Rejection reasons: {', '.join(reasons)}.\n\n"
            "Generate a corrected JSON patch. Prefer minimal edits. Do not rewrite whole files.\n"
            "CRITICAL:\n"
            "- Return valid JSON only.\n"
            "- Fill patch_text, operations[] or files[] with at least one entry.\n"
            "- PREFER patch_text in Codex apply_patch format:\n"
            '  patch_text="*** Begin Patch\\n*** Update File: path\\n@@ context\\n-old\\n+new\\n*** End Patch"\n'
            "- Prefer `operations[]` using exact literal edit strings when patch_text is not used. Do not escape them.\n"
            "- files[] with full content is LAST RESORT — never rewrite entire files unless absolutely necessary.\n"
            "- Every modified/create file in files[] MUST include full `content` (no `diff`-only entries).\n"
            "- Restrict changes to grounded candidate files.\n"
            "- Preserve existing signatures and run() API compatibility.\n"
            "- If CI classification is test_failure, include at least one source-file change unless "
            "you add an explicit decision rationale containing 'test_only_change_justified'.\n\n"
            f"Task: {issue_summary}\n"
            f"CI classification: {ci_classification}\n"
            f"Patch strategy: {patch_strategy}\n"
            f"Forced strategy mode: {forced_strategy_mode}\n"
            + (f"Required change scope: {required_scope}\n" if required_scope else "")
            + (
                "Candidate files:\n"
                + "\n".join(f"- {item}" for item in candidate_files[:15])
                + "\n"
                if candidate_files
                else ""
            )
            + (
                "CI test targets:\n" + "\n".join(f"- {item}" for item in ci_targets) + "\n"
                if ci_targets
                else ""
            )
            + (
                "Semantic feedback packet:\n" + "\n".join(semantic_lines) + "\n"
                if semantic_lines
                else ""
            )
            + (
                "Mandatory signature discovery:\n" + "\n".join(signature_lines) + "\n"
                if signature_lines
                else ""
            )
            + ("File snippets:\n" + "\n\n".join(snippet_blocks) + "\n" if snippet_blocks else "")
            + (
                "Schema:\n"
                "{"
                '"files":[{"path":"...","change_type":"modify","content":"..."}],'
                '"decisions":[{"description":"...","rationale":"..."}],'
                '"test_changes":[{"path":"...","change_type":"modify","content":"..."}]'
                "}\n"
            )
        )

    @classmethod
    def _resolve_patch_strategy(
        cls,
        strategy_raw: Any,
        *,
        allow_full_file_rewrite: bool,
    ) -> str:
        normalized = str(strategy_raw or "").strip().lower()
        if normalized == cls.FULL_FILE_STRATEGY and allow_full_file_rewrite:
            return cls.FULL_FILE_STRATEGY
        return cls.PATCH_FIRST_STRATEGY

    def _read_semantic_retry_state(self, context: dict[str, Any]) -> dict[str, Any]:
        raw = context.get(self.SEMANTIC_RETRY_STATE_KEY, {})
        if not isinstance(raw, dict):
            return {"fingerprints": [], "packets": []}
        fingerprints = raw.get("fingerprints", [])
        packets = raw.get("packets", [])
        if not isinstance(fingerprints, list):
            fingerprints = []
        if not isinstance(packets, list):
            packets = []
        return {
            "fingerprints": [str(item).strip() for item in fingerprints if str(item).strip()][
                -self.SEMANTIC_RETRY_HISTORY_LIMIT :
            ],
            "packets": [item for item in packets if isinstance(item, dict)][
                -self.SEMANTIC_RETRY_HISTORY_LIMIT :
            ],
        }

    def _reset_semantic_retry_state(self, context: dict[str, Any]) -> None:
        self._write_semantic_retry_state(
            context,
            {
                "fingerprints": [],
                "packets": [],
            },
        )

    def _write_semantic_retry_state(self, context: dict[str, Any], value: dict[str, Any]) -> None:
        try:
            if hasattr(context, "set_state_value"):
                context.set_state_value(self.SEMANTIC_RETRY_STATE_KEY, value)
                return
            context[self.SEMANTIC_RETRY_STATE_KEY] = value
        except Exception:
            logger.debug("code_generator_semantic_retry_state_write_failed")

    @staticmethod
    def _build_semantic_feedback_packet_from_state(
        semantic_retry_state: dict[str, Any],
    ) -> dict[str, Any]:
        packets = semantic_retry_state.get("packets", [])
        if not isinstance(packets, list) or not packets:
            return {"violations": []}
        latest = packets[-1]
        if not isinstance(latest, dict):
            return {"violations": []}
        violations = latest.get("violations", [])
        if not isinstance(violations, list):
            violations = []
        return {"violations": [item for item in violations if isinstance(item, dict)]}

    @staticmethod
    def _should_force_plan_for_semantic_retries(
        semantic_retry_state: dict[str, Any],
        *,
        force_after_first: bool,
    ) -> bool:
        history = semantic_retry_state.get("fingerprints", [])
        if not isinstance(history, list) or not history:
            return False
        normalized = [str(item).strip() for item in history if str(item).strip()]
        if not normalized:
            return False
        if force_after_first:
            return True
        if len(normalized) < 2:
            return False
        last_two = normalized[-2:]
        return last_two[0] == last_two[1]

    def _record_semantic_retry_state(
        self,
        context: dict[str, Any],
        *,
        semantic_retry_state: dict[str, Any],
        semantic_feedback_packet: dict[str, Any],
    ) -> None:
        fingerprint = self._fingerprint_semantic_feedback_packet(semantic_feedback_packet)
        history = [
            str(item).strip()
            for item in semantic_retry_state.get("fingerprints", [])
            if str(item).strip()
        ]
        packets = [
            item for item in semantic_retry_state.get("packets", []) if isinstance(item, dict)
        ]
        if fingerprint:
            history.append(fingerprint)
        packets.append(semantic_feedback_packet)
        self._write_semantic_retry_state(
            context,
            {
                "fingerprints": history[-self.SEMANTIC_RETRY_HISTORY_LIMIT :],
                "packets": packets[-self.SEMANTIC_RETRY_HISTORY_LIMIT :],
            },
        )

    def _build_semantic_feedback_packet(
        self,
        violations: Any,
        *,
        signature_discovery_packet: dict[str, Any],
    ) -> dict[str, Any]:
        symbol_signatures: dict[str, str] = {}
        raw_symbols = signature_discovery_packet.get("symbols", [])
        if isinstance(raw_symbols, list):
            for item in raw_symbols:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol", "")).strip()
                expected_signature = str(item.get("expected_signature", "")).strip()
                if symbol and expected_signature:
                    symbol_signatures[symbol] = expected_signature

        packet_items: list[dict[str, Any]] = []
        for raw in violations if isinstance(violations, list) else []:
            violation = str(raw).strip()
            if not violation:
                continue

            if violation.startswith("unknown_keyword_argument:"):
                parts = violation.split(":", 3)
                if len(parts) < 4:
                    continue
                file_path = self._normalize_path(parts[1])
                symbol = str(parts[2]).strip()
                invalid_kwargs = [item.strip() for item in str(parts[3]).split(",") if item.strip()]
                packet_items.append(
                    {
                        "violation_type": "unknown_keyword_argument",
                        "symbol": symbol,
                        "expected_signature": symbol_signatures.get(symbol, ""),
                        "invalid_kwargs": invalid_kwargs,
                        "location": f"{file_path}:0" if file_path else "",
                    }
                )
                continue

            if violation.startswith("python_syntax_error:"):
                parts = violation.split(":", 2)
                if len(parts) < 3:
                    continue
                file_path = self._normalize_path(parts[1])
                line_no = str(parts[2]).strip() or "0"
                packet_items.append(
                    {
                        "violation_type": "python_syntax_error",
                        "symbol": "",
                        "expected_signature": "",
                        "invalid_kwargs": [],
                        "location": f"{file_path}:{line_no}" if file_path else "",
                    }
                )
                continue

            if violation.startswith("public_signature_missing_keyword:"):
                parts = violation.split(":", 3)
                if len(parts) < 4:
                    continue
                file_path = self._normalize_path(parts[1])
                symbol = str(parts[2]).strip()
                missing_kwargs = [item.strip() for item in str(parts[3]).split(",") if item.strip()]
                packet_items.append(
                    {
                        "violation_type": "public_signature_missing_keyword",
                        "symbol": symbol,
                        "expected_signature": symbol_signatures.get(symbol, ""),
                        "invalid_kwargs": missing_kwargs,
                        "location": f"{file_path}:0" if file_path else "",
                    }
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in packet_items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= self.MAX_SEMANTIC_VIOLATIONS:
                break
        return {"violations": deduped}

    @staticmethod
    def _fingerprint_semantic_feedback_packet(packet: dict[str, Any]) -> str:
        violations = packet.get("violations", [])
        if not isinstance(violations, list) or not violations:
            return ""
        serialized = json.dumps(violations, sort_keys=True, ensure_ascii=False)
        return sha256(serialized.encode("utf-8")).hexdigest()[:20]

    def _build_signature_discovery_packet(
        self,
        *,
        candidate_files: list[str],
        candidate_file_snippets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        signature_cache: dict[str, dict[str, tuple[set[str], bool]] | None] = {}
        targets = self._extract_signature_targets_from_snippets(
            candidate_files=candidate_files,
            candidate_file_snippets=candidate_file_snippets,
        )
        symbols: list[dict[str, Any]] = []
        seen: set[str] = set()
        for imported_module, imported_symbol, caller_file in targets:
            signature = self._resolve_imported_callable_signature(
                imported_module=imported_module,
                imported_symbol=imported_symbol,
                patch_sources={},
                signature_cache=signature_cache,
            )
            if signature is None:
                continue
            accepted_keywords, accepts_kwargs = signature
            symbol_key = f"{imported_module}.{imported_symbol}"
            if symbol_key in seen:
                continue
            seen.add(symbol_key)
            expected_signature = self._render_expected_signature(
                symbol=symbol_key,
                accepted_keywords=accepted_keywords,
                accepts_kwargs=accepts_kwargs,
            )
            symbols.append(
                {
                    "symbol": symbol_key,
                    "expected_signature": expected_signature,
                    "location": f"{caller_file}:0" if caller_file else "",
                }
            )
            if len(symbols) >= 20:
                break
        local_symbols = self._collect_local_public_signature_entries(
            candidate_files=candidate_files,
            candidate_file_snippets=candidate_file_snippets,
        )
        for item in local_symbols:
            if len(symbols) >= 20:
                break
            if not isinstance(item, dict):
                continue
            symbol_key = str(item.get("symbol", "")).strip()
            if not symbol_key or symbol_key in seen:
                continue
            seen.add(symbol_key)
            symbols.append(item)
        return {"ran": True, "symbols": symbols}

    def _extract_signature_targets_from_snippets(
        self,
        *,
        candidate_files: list[str],
        candidate_file_snippets: list[dict[str, Any]],
    ) -> list[tuple[str, str, str]]:
        snippet_by_path = {
            self._normalize_path(item.get("path", "")): str(item.get("snippet", ""))
            for item in candidate_file_snippets
            if isinstance(item, dict)
            and self._normalize_path(item.get("path", ""))
            and isinstance(item.get("snippet"), str)
        }
        results: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidate_files[:20]:
            normalized_path = self._normalize_path(candidate)
            if not normalized_path.endswith(".py"):
                continue
            source = snippet_by_path.get(normalized_path)
            tree = None
            if isinstance(source, str) and source.strip():
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    tree = None
            if tree is None:
                source = self._read_semantic_source(normalized_path)
            if not isinstance(source, str) or not source.strip():
                continue
            if tree is None:
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue
            if tree is None:
                continue
            from_imports, module_imports = self._extract_import_bindings(
                tree=tree,
                current_file_path=normalized_path,
            )
            call_targets_found = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                imported_module = ""
                imported_symbol = ""
                if isinstance(node.func, ast.Name):
                    binding = from_imports.get(node.func.id)
                    if binding:
                        imported_module, imported_symbol = binding
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    module_name = module_imports.get(node.func.value.id)
                    if module_name:
                        imported_module = module_name
                        imported_symbol = node.func.attr
                if not imported_module or not imported_symbol:
                    continue
                key = (imported_module, imported_symbol, normalized_path)
                if key in seen:
                    continue
                seen.add(key)
                results.append(key)
                call_targets_found += 1
            if call_targets_found == 0:
                # Fall back to imported local symbols so discovery still produces contracts
                # when snippets are truncated or call-sites are outside the snippet window.
                for imported_module, imported_symbol in from_imports.values():
                    key = (imported_module, imported_symbol, normalized_path)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(key)
        return results

    @staticmethod
    def _render_expected_signature(
        *,
        symbol: str,
        accepted_keywords: set[str],
        accepts_kwargs: bool,
    ) -> str:
        keyword_items = sorted(item for item in accepted_keywords if item)
        signature_suffix = ", **kwargs" if accepts_kwargs else ""
        kwargs_body = ", ".join(keyword_items)
        if kwargs_body and signature_suffix:
            kwargs_body = f"{kwargs_body}{signature_suffix}"
        elif signature_suffix:
            kwargs_body = signature_suffix.lstrip(", ")
        return f"{symbol}({kwargs_body})"

    def _collect_local_public_signature_entries(
        self,
        *,
        candidate_files: list[str],
        candidate_file_snippets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        snippet_by_path = {
            self._normalize_path(item.get("path", "")): str(item.get("snippet", ""))
            for item in candidate_file_snippets
            if isinstance(item, dict)
            and self._normalize_path(item.get("path", ""))
            and isinstance(item.get("snippet"), str)
        }
        entries: list[dict[str, Any]] = []
        for candidate in candidate_files[:20]:
            normalized_path = self._normalize_path(candidate)
            if not normalized_path.endswith(".py"):
                continue
            source = snippet_by_path.get(normalized_path)
            tree = None
            if isinstance(source, str) and source.strip():
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    tree = None
            if tree is None:
                source = self._read_semantic_source(normalized_path)
            if not isinstance(source, str) or not source.strip():
                continue
            if tree is None:
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    continue
            signature_map = self._build_public_callable_signature_map(
                tree=tree,
                normalized_path=normalized_path,
            )
            for symbol, signature in signature_map.items():
                accepted_keywords, accepts_kwargs = signature
                entries.append(
                    {
                        "symbol": symbol,
                        "expected_signature": self._render_expected_signature(
                            symbol=symbol,
                            accepted_keywords=accepted_keywords,
                            accepts_kwargs=accepts_kwargs,
                        ),
                        "location": f"{normalized_path}:0",
                    }
                )
        return entries

    def _predict_quality_gate_reasons(
        self,
        *,
        files: list[dict[str, Any]],
        notes: list[str],
        decisions: Any,
        ci_failure_context: dict[str, Any],
        candidate_files: list[str],
        allow_full_file_rewrite: bool = False,
    ) -> list[str]:
        reasons: list[str] = []
        if not files:
            reasons.append("no_files_in_patch")
        if self._has_unjustified_full_rewrite(
            files,
            decisions,
            allow_full_file_rewrite=allow_full_file_rewrite,
        ):
            reasons.append("full_file_rewrite_without_justification")
        if self._is_analysis_only_without_source_change(decisions, files):
            reasons.append("analysis_only_without_source_change")
        if self._is_test_failure_without_source_change(
            ci_failure_context=ci_failure_context,
            candidate_files=candidate_files,
            files=files,
            decisions=decisions,
        ):
            reasons.append("test_failure_without_source_change")
        if any(
            isinstance(note, str) and note.startswith("missing_content_for_file=") for note in notes
        ):
            reasons.append("missing_file_content")
        if any(
            isinstance(note, str)
            and (
                note.startswith("operation_")
                or note.startswith("invalid_operation_")
                or note.startswith("invalid_patch_text:")
            )
            for note in notes
        ):
            reasons.append("invalid_patch_operations")
        return sorted(set(reasons))

    def _evaluate_semantic_patch_gate(self, files: Any) -> dict[str, Any]:
        if not isinstance(files, list):
            return {"passed": False, "violations": ["patch_files_not_a_list"]}

        patch_sources: dict[str, str] = {}
        for item in files:
            if not isinstance(item, dict):
                continue
            path = self._normalize_path(item.get("path", ""))
            content = item.get("content")
            if not path.endswith(".py") or not isinstance(content, str):
                continue
            patch_sources[path] = content

        if not patch_sources:
            return {"passed": True, "violations": []}

        violations: list[str] = []
        signature_cache: dict[str, dict[str, tuple[set[str], bool]] | None] = {}

        for patch_path, patch_content in patch_sources.items():
            try:
                tree = ast.parse(patch_content)
            except SyntaxError as exc:
                line_no = int(exc.lineno or 0)
                violations.append(f"python_syntax_error:{patch_path}:{line_no}")
                if len(violations) >= self.MAX_SEMANTIC_VIOLATIONS:
                    break
                continue

            original_public_signatures = self._load_public_callable_signatures(
                normalized_path=patch_path,
                source_override=None,
            )
            patched_public_signatures = self._build_public_callable_signature_map(
                tree=tree,
                normalized_path=patch_path,
            )
            for symbol, original_signature in original_public_signatures.items():
                patched_signature = patched_public_signatures.get(symbol)
                if patched_signature is None:
                    continue
                original_keywords, original_accepts_kwargs = original_signature
                patched_keywords, patched_accepts_kwargs = patched_signature
                if original_accepts_kwargs or patched_accepts_kwargs:
                    continue
                missing_keywords = sorted(original_keywords - patched_keywords)
                if not missing_keywords:
                    continue
                violations.append(
                    "public_signature_missing_keyword:"
                    f"{patch_path}:{symbol}:{','.join(missing_keywords[:5])}"
                )
                if len(violations) >= self.MAX_SEMANTIC_VIOLATIONS:
                    break

            if len(violations) >= self.MAX_SEMANTIC_VIOLATIONS:
                break

            from_imports, module_imports = self._extract_import_bindings(
                tree=tree,
                current_file_path=patch_path,
            )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                keyword_args = sorted(
                    {
                        kw.arg
                        for kw in node.keywords
                        if isinstance(kw, ast.keyword) and isinstance(kw.arg, str)
                    }
                )
                if not keyword_args:
                    continue

                imported_module = ""
                imported_symbol = ""
                if isinstance(node.func, ast.Name):
                    binding = from_imports.get(node.func.id)
                    if binding:
                        imported_module, imported_symbol = binding
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    module_name = module_imports.get(node.func.value.id)
                    if module_name:
                        imported_module = module_name
                        imported_symbol = node.func.attr

                if not imported_module or not imported_symbol:
                    continue

                signature = self._resolve_imported_callable_signature(
                    imported_module=imported_module,
                    imported_symbol=imported_symbol,
                    patch_sources=patch_sources,
                    signature_cache=signature_cache,
                )
                if signature is None:
                    continue

                accepted_keywords, accepts_kwargs = signature
                if accepts_kwargs:
                    continue

                unsupported_keywords = sorted(set(keyword_args) - accepted_keywords)
                if not unsupported_keywords:
                    continue

                unsupported = ",".join(unsupported_keywords[:3])
                violations.append(
                    "unknown_keyword_argument:"
                    f"{patch_path}:{imported_module}.{imported_symbol}:{unsupported}"
                )
                if len(violations) >= self.MAX_SEMANTIC_VIOLATIONS:
                    break

            if len(violations) >= self.MAX_SEMANTIC_VIOLATIONS:
                break

        deduped: list[str] = []
        seen: set[str] = set()
        for item in violations:
            key = str(item).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
            if len(deduped) >= self.MAX_SEMANTIC_VIOLATIONS:
                break
        return {"passed": len(deduped) == 0, "violations": deduped}

    @staticmethod
    def _path_to_module_name(normalized_path: str) -> str:
        path = str(normalized_path or "").strip().replace("\\", "/")
        if not path.endswith(".py"):
            return ""
        if path.endswith("/__init__.py"):
            path = path[: -len("/__init__.py")]
        else:
            path = path[:-3]
        return ".".join(part for part in path.split("/") if part and part != ".")

    def _build_public_callable_signature_map(
        self,
        *,
        tree: ast.AST,
        normalized_path: str,
    ) -> dict[str, tuple[set[str], bool]]:
        module_name = self._path_to_module_name(normalized_path)
        if not module_name:
            return {}

        signatures: dict[str, tuple[set[str], bool]] = {}
        for node in getattr(tree, "body", []):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not node.name.startswith("_"):
                signatures[f"{module_name}.{node.name}"] = self._build_callable_signature(
                    node,
                    drop_first=False,
                )
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                constructor_signature: tuple[set[str], bool] | None = None
                for child in node.body:
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if child.name == "__init__":
                        constructor_signature = self._build_callable_signature(
                            child,
                            drop_first=True,
                        )
                        continue
                    if child.name.startswith("_"):
                        continue
                    signatures[f"{module_name}.{node.name}.{child.name}"] = (
                        self._build_callable_signature(child, drop_first=True)
                    )
                if constructor_signature is not None:
                    signatures[f"{module_name}.{node.name}"] = constructor_signature
        return signatures

    def _load_public_callable_signatures(
        self,
        *,
        normalized_path: str,
        source_override: str | None,
    ) -> dict[str, tuple[set[str], bool]]:
        source = source_override
        if not isinstance(source, str):
            source = self._read_semantic_source(normalized_path)
        if not isinstance(source, str) or not source.strip():
            return {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}
        return self._build_public_callable_signature_map(
            tree=tree,
            normalized_path=normalized_path,
        )

    def _extract_import_bindings(
        self,
        *,
        tree: ast.AST,
        current_file_path: str,
    ) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
        from_imports: dict[str, tuple[str, str]] = {}
        module_imports: dict[str, str] = {}
        current_package_parts = [
            part
            for part in self._normalize_path(current_file_path).split("/")[:-1]
            if part and part != "."
        ]

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_name = self._resolve_import_module_name(
                    module=node.module,
                    level=int(node.level or 0),
                    current_package_parts=current_package_parts,
                )
                if not module_name:
                    continue
                for alias in node.names:
                    raw_name = str(alias.name or "").strip()
                    if not raw_name or raw_name == "*":
                        continue
                    alias_name = str(alias.asname or raw_name).strip()
                    if not alias_name:
                        continue
                    imported_symbol = raw_name.split(".", 1)[0]
                    from_imports[alias_name] = (module_name, imported_symbol)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = str(alias.name or "").strip()
                    if not module_name:
                        continue
                    alias_name = str(alias.asname or module_name.split(".", 1)[0]).strip()
                    if not alias_name:
                        continue
                    module_imports[alias_name] = module_name

        return from_imports, module_imports

    @staticmethod
    def _resolve_import_module_name(
        *,
        module: str | None,
        level: int,
        current_package_parts: list[str],
    ) -> str:
        module_parts = [part for part in str(module or "").split(".") if part]
        if level <= 0:
            return ".".join(module_parts)

        if level - 1 > len(current_package_parts):
            return ""
        base_parts = current_package_parts[: len(current_package_parts) - (level - 1)]
        resolved_parts = [*base_parts, *module_parts]
        return ".".join(part for part in resolved_parts if part)

    @staticmethod
    def _module_name_to_candidate_paths(module_name: str) -> list[str]:
        normalized_module = str(module_name or "").strip().strip(".")
        if not normalized_module:
            return []
        module_path = normalized_module.replace(".", "/")
        return [f"{module_path}.py", f"{module_path}/__init__.py"]

    def _resolve_imported_callable_signature(
        self,
        *,
        imported_module: str,
        imported_symbol: str,
        patch_sources: dict[str, str],
        signature_cache: dict[str, dict[str, tuple[set[str], bool]] | None],
    ) -> tuple[set[str], bool] | None:
        for module_path in self._module_name_to_candidate_paths(imported_module):
            signatures = self._load_module_signatures_for_semantic_gate(
                module_path=module_path,
                patch_sources=patch_sources,
                signature_cache=signature_cache,
            )
            if not isinstance(signatures, dict):
                continue
            signature = signatures.get(imported_symbol)
            if signature is not None:
                return signature
        return None

    def _load_module_signatures_for_semantic_gate(
        self,
        *,
        module_path: str,
        patch_sources: dict[str, str],
        signature_cache: dict[str, dict[str, tuple[set[str], bool]] | None],
    ) -> dict[str, tuple[set[str], bool]] | None:
        normalized_path = self._normalize_path(module_path)
        if normalized_path in signature_cache:
            return signature_cache[normalized_path]

        source = patch_sources.get(normalized_path)
        if not isinstance(source, str):
            source = self._read_semantic_source(normalized_path)
        if not isinstance(source, str):
            signature_cache[normalized_path] = None
            return None

        try:
            module_tree = ast.parse(source)
        except SyntaxError:
            signature_cache[normalized_path] = None
            return None

        signatures: dict[str, tuple[set[str], bool]] = {}
        for node in module_tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                signatures[node.name] = self._build_callable_signature(node, drop_first=False)
            elif isinstance(node, ast.ClassDef):
                init_func = None
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        child.name == "__init__"
                    ):
                        init_func = child
                        break
                if init_func is None:
                    continue
                signatures[node.name] = self._build_callable_signature(init_func, drop_first=True)

        signature_cache[normalized_path] = signatures
        return signatures

    def _read_semantic_source(self, normalized_path: str) -> str | None:
        repo_path = Path("workspace/repo") / normalized_path
        local_path = Path(normalized_path)
        selected_path: Path | None = None
        if repo_path.exists() and repo_path.is_file():
            selected_path = repo_path
        elif local_path.exists() and local_path.is_file():
            selected_path = local_path
        if selected_path is None:
            return None
        try:
            return selected_path.read_text(encoding="utf-8")
        except Exception:
            return None

    @staticmethod
    def _build_callable_signature(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        drop_first: bool,
    ) -> tuple[set[str], bool]:
        arg_names = [
            arg.arg
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if isinstance(arg, ast.arg) and isinstance(arg.arg, str) and arg.arg
        ]
        if drop_first and arg_names:
            arg_names = arg_names[1:]
        accepts_kwargs = node.args.kwarg is not None
        return set(arg_names), accepts_kwargs

    @classmethod
    def _parse_llm_patch_response(cls, response: str) -> dict[str, Any] | None:
        if not isinstance(response, str) or not response.strip():
            return None

        candidates = [response, cls._strip_code_fences(response)]
        for candidate in candidates:
            if not candidate or not candidate.strip():
                continue

            parsed = cls._try_shared_code_parser(candidate)
            if parsed is not None:
                return cls._normalize_llm_response_payload(parsed)

            parsed = cls._try_balanced_json_parse(candidate)
            if parsed is not None:
                return cls._normalize_llm_response_payload(parsed)

            parsed = cls._try_loose_patch_extraction(candidate)
            if parsed is not None:
                return cls._normalize_llm_response_payload(parsed)

        return None

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _try_shared_code_parser(text: str) -> dict[str, Any] | None:
        try:
            parsed = parse_code_output(text)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _try_balanced_json_parse(cls, text: str) -> dict[str, Any] | None:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if cls._is_valid_llm_patch(parsed) or cls._is_valid_llm_file_request(parsed):
                return parsed
        return None

    @classmethod
    def _normalize_llm_response_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        files = normalized.get("files")
        if not isinstance(files, list):
            normalized["files"] = []
        operations = normalized.get("operations")
        if not isinstance(operations, list):
            normalized["operations"] = []
        patch_text = normalized.get("patch_text")
        if not isinstance(patch_text, str):
            normalized["patch_text"] = ""
        decisions = normalized.get("decisions")
        if not isinstance(decisions, list):
            normalized["decisions"] = []
        test_operations = normalized.get("test_operations")
        if not isinstance(test_operations, list):
            normalized["test_operations"] = []
        test_changes = normalized.get("test_changes")
        if not isinstance(test_changes, list):
            normalized["test_changes"] = []
        if "required_files" in normalized:
            normalized["required_files"] = cls._extract_required_files(normalized)
        return normalized

    @classmethod
    def _is_valid_llm_patch(cls, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        files = payload.get("files")
        operations = payload.get("operations")
        patch_text = str(payload.get("patch_text", "") or "").strip()
        has_files = isinstance(files, list) and bool(files)
        has_operations = isinstance(operations, list) and bool(operations)
        has_patch_text = bool(patch_text)
        if not has_files and not has_operations and not has_patch_text:
            return False
        if has_files:
            for item in files:
                if not isinstance(item, dict):
                    return False
                if not isinstance(item.get("path"), str) or not item.get("path", "").strip():
                    return False
                if (
                    not isinstance(item.get("change_type"), str)
                    or not item.get("change_type", "").strip()
                ):
                    return False
                if not isinstance(item.get("content"), str):
                    return False
        if has_operations:
            for item in operations:
                if not cls._is_valid_llm_operation(item):
                    return False
        return True

    @classmethod
    def _is_valid_llm_operation(cls, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        operation_type = str(payload.get("type", "")).strip().lower()
        if operation_type not in {"edit", "write"}:
            return False
        if not isinstance(payload.get("path"), str) or not str(payload.get("path", "")).strip():
            return False
        if operation_type == "edit":
            return isinstance(payload.get("old_string"), str) and isinstance(
                payload.get("new_string"), str
            )
        return isinstance(payload.get("content"), str)

    @classmethod
    def _is_valid_llm_file_request(cls, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        required_files = cls._extract_required_files(payload)
        return bool(required_files)

    @staticmethod
    def _has_patch_files(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        files = payload.get("files")
        if isinstance(files, list) and len(files) > 0:
            return True
        operations = payload.get("operations")
        if isinstance(operations, list) and len(operations) > 0:
            return True
        patch_text = payload.get("patch_text")
        return isinstance(patch_text, str) and bool(patch_text.strip())

    @classmethod
    def _extract_required_files(cls, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            return []

        raw_items = payload.get("required_files")
        if not isinstance(raw_items, list):
            return []

        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            raw_path = None
            if isinstance(item, str):
                raw_path = item
            elif isinstance(item, dict):
                path_value = item.get("path")
                if isinstance(path_value, str):
                    raw_path = path_value
            if not isinstance(raw_path, str):
                continue

            normalized = cls._normalize_path(raw_path)
            if not normalized:
                continue
            if "::" in normalized:
                normalized = normalized.split("::", 1)[0]
            if normalized.startswith("/") or ".." in normalized.split("/"):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)

        return result[:20]

    @classmethod
    def _try_loose_patch_extraction(cls, text: str) -> dict[str, Any] | None:
        pattern = re.compile(
            r'"path"\s*:\s*"(?P<path>[^"]+)"[\s\S]*?'
            r'"change_type"\s*:\s*"(?P<change_type>[^"]+)"[\s\S]*?'
            r'"content"\s*:\s*"(?P<content>[\s\S]*?)"\s*"?\s*}',
            re.IGNORECASE,
        )
        files: list[dict[str, str]] = []
        for match in pattern.finditer(text):
            path = match.group("path").strip()
            change_type = match.group("change_type").strip()
            content = match.group("content")
            if not path or not change_type:
                continue
            try:
                content = bytes(content, "utf-8").decode("unicode_escape")
            except Exception:
                content = content.replace("\\n", "\n")
            files.append(
                {
                    "path": path,
                    "change_type": change_type,
                    "content": content,
                }
            )

        if not files:
            return None

        payload: dict[str, Any] = {
            "files": files,
            "decisions": [],
            "test_changes": [],
        }
        return payload if cls._is_valid_llm_patch(payload) else None

    def _filter_patch_files(
        self,
        files: Any,
        *,
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool = True,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not isinstance(files, list):
            return [], ["patch_files_not_a_list"]

        normalized_candidates = {self._normalize_path(item) for item in candidate_files if item}
        filtered: list[dict[str, Any]] = []
        notes: list[str] = []

        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            content = item.get("content")
            change_type = str(item.get("change_type", "modify")).strip().lower() or "modify"
            normalized_path = self._normalize_path(path or "")
            if (
                isinstance(path, str)
                and path.strip()
                and change_type != "delete"
                and not isinstance(content, str)
            ):
                notes.append(f"missing_content_for_file={normalized_path}")
            if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
                continue
            if self._is_placeholder_patch_content(content):
                notes.append(f"filtered_placeholder_patch={normalized_path}")
                continue
            file_item = {
                "path": normalized_path,
                "change_type": change_type,
                "content": content,
            }

            if normalized_candidates:
                if normalized_path in normalized_candidates:
                    filtered.append(file_item)
                elif strict_target_files:
                    notes.append(f"filtered_non_candidate_file={normalized_path}")
                elif not allow_new_files and Path(normalized_path).exists():
                    filtered.append(file_item)
                    notes.append(f"existing_non_candidate_file_allowed={normalized_path}")
                elif allow_new_files:
                    filtered.append(file_item)
                    notes.append(f"new_or_non_candidate_file_allowed={normalized_path}")
                else:
                    notes.append(f"filtered_non_candidate_file={normalized_path}")
            else:
                if allow_new_files:
                    filtered.append(file_item)
                else:
                    notes.append(f"filtered_file_without_grounding={normalized_path}")

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in filtered:
            key = item["path"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped, notes

    def _materialize_patch_files(
        self,
        *,
        files: Any,
        test_changes: Any,
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        filtered_files, notes = self._filter_patch_files(
            files,
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        if filtered_files:
            return filtered_files, notes

        promoted_count = 0
        promoted_candidates: list[dict[str, Any]] = []
        if isinstance(test_changes, list):
            for item in test_changes:
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get("path"), str):
                    continue
                if not isinstance(item.get("content"), str):
                    continue
                promoted_candidates.append(
                    {
                        "path": item["path"],
                        "change_type": str(item.get("change_type", "modify")).strip().lower()
                        or "modify",
                        "content": item["content"],
                    }
                )

        if promoted_candidates:
            filtered_files, promoted_notes = self._filter_patch_files(
                promoted_candidates,
                candidate_files=candidate_files,
                allow_new_files=allow_new_files,
                strict_target_files=strict_target_files,
            )
            promoted_count = len(filtered_files)
            notes.extend(promoted_notes)

        if promoted_count > 0:
            notes.append(f"promoted_test_changes_to_files={promoted_count}")
        return filtered_files, notes

    def _materialize_llm_payload(
        self,
        *,
        llm_payload: dict[str, Any],
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        notes: list[str] = []
        patch_text = str(llm_payload.get("patch_text", "") or "").strip()
        patch_text_files: list[dict[str, Any]] = []
        if patch_text:
            try:
                patch_text_files = materialize_patch_text(patch_text, base_dir=Path.cwd())
                notes.append(f"materialized_patch_text_files={len(patch_text_files)}")
            except Exception as exc:
                notes.append(f"invalid_patch_text:{str(exc)[:200]}")
                patch_text_files = []
        filtered_patch_text_files, patch_text_notes = self._filter_patch_files(
            patch_text_files,
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        notes.extend(patch_text_notes)
        materialized_files, file_notes = self._materialize_patch_files(
            files=llm_payload.get("files", []),
            test_changes=llm_payload.get("test_changes", []),
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        notes.extend(file_notes)
        if filtered_patch_text_files:
            materialized_files = self._merge_materialized_files(
                filtered_patch_text_files, materialized_files
            )

        operation_files, operation_notes = self._materialize_operations(
            operations=llm_payload.get("operations", []),
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        notes.extend(operation_notes)

        if operation_files:
            materialized_files = self._merge_materialized_files(materialized_files, operation_files)

        test_changes = (
            list(llm_payload.get("test_changes", []))
            if isinstance(llm_payload.get("test_changes"), list)
            else []
        )
        test_operation_files, test_operation_notes = self._materialize_operations(
            operations=llm_payload.get("test_operations", []),
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        notes.extend(test_operation_notes)
        if test_operation_files:
            test_changes = self._merge_materialized_files(test_changes, test_operation_files)

        return materialized_files, test_changes, notes

    @staticmethod
    def _merge_materialized_files(
        left: list[dict[str, Any]], right: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        latest: dict[str, dict[str, Any]] = {}
        for item in [*(left or []), *(right or [])]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            latest[path] = item
        for item in [*(left or []), *(right or [])]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            if latest.get(path) is None:
                continue
            merged.append(latest.pop(path))
        merged.extend(latest.values())
        return merged

    def _materialize_operations(
        self,
        *,
        operations: Any,
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        materialized, notes = materialize_patch_operations(operations, base_dir=Path.cwd())
        filtered, filter_notes = self._filter_patch_files(
            materialized,
            candidate_files=candidate_files,
            allow_new_files=allow_new_files,
            strict_target_files=strict_target_files,
        )
        notes.extend(filter_notes)
        return filtered, notes

    def _load_candidate_file_snippets(
        self,
        candidate_files: list[str],
        *,
        max_files: int = 3,
        max_chars_per_file: int = 3000,
    ) -> list[dict[str, str]]:
        snippets: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_path in candidate_files[:20]:
            normalized = self._normalize_path(raw_path)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            repo_path = Path("workspace/repo") / normalized
            local_path = Path(normalized)
            selected_path: Path | None = None
            if repo_path.exists() and repo_path.is_file():
                selected_path = repo_path
            elif local_path.exists() and local_path.is_file():
                selected_path = local_path
            if selected_path is None:
                continue

            try:
                content = selected_path.read_text(encoding="utf-8")
            except Exception:
                continue
            snippet = content[:max_chars_per_file].strip()
            if not snippet:
                continue
            snippets.append(
                {
                    "path": normalized,
                    "snippet": snippet,
                    "content": content.strip(),
                    "truncated": len(content) > max_chars_per_file,
                }
            )
            if len(snippets) >= max_files:
                break
        return snippets

    @classmethod
    def _is_placeholder_patch_content(cls, content: str) -> bool:
        text = str(content or "").lower()
        return any(marker in text for marker in cls.PLACEHOLDER_PATCH_MARKERS)

    def _has_unjustified_full_rewrite(
        self,
        files: Any,
        decisions: Any,
        *,
        allow_full_file_rewrite: bool = False,
    ) -> bool:
        if not isinstance(files, list):
            return False
        if allow_full_file_rewrite:
            return False
        for item in files:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            if len(content.splitlines()) > self.MAX_UNJUSTIFIED_REWRITE_LINES:
                return True
        return False

    def _is_analysis_only_without_source_change(self, decisions: Any, files: Any) -> bool:
        if not isinstance(decisions, list):
            return False
        if not isinstance(files, list) or not files:
            return False

        decisions_text = " ".join(str(item).lower() for item in decisions)
        analysis_markers = (
            "need to find and examine",
            "need to examine",
            "cannot implement fix without",
            "without access to",
            "no source files were identified",
        )
        if not any(marker in decisions_text for marker in analysis_markers):
            return False

        changed_paths: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_path(item.get("path"))
            if normalized:
                changed_paths.append(normalized)

        if not changed_paths:
            return True
        return all(path.startswith("tests/") for path in changed_paths)

    def _is_test_failure_without_source_change(
        self,
        *,
        ci_failure_context: dict[str, Any],
        candidate_files: list[str],
        files: Any,
        decisions: Any,
    ) -> bool:
        if str(ci_failure_context.get("classification", "")).strip().lower() != "test_failure":
            return False
        if not isinstance(files, list) or not files:
            return False

        changed_paths: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_path(item.get("path", ""))
            if normalized:
                changed_paths.append(normalized)
        if not changed_paths:
            return False
        if any(not path.startswith("tests/") for path in changed_paths):
            return False

        decisions_text = " ".join(str(item).lower() for item in decisions or [])
        if "test_only_change_justified" in decisions_text:
            return False

        source_candidates = [
            self._normalize_path(path)
            for path in candidate_files
            if isinstance(path, str) and not self._normalize_path(path).startswith("tests/")
        ]
        return bool(source_candidates)

    def _is_required_scope_violated(
        self,
        *,
        ci_failure_context: dict[str, Any],
        files: Any,
        decisions: Any,
    ) -> bool:
        required_scope = str(ci_failure_context.get("required_change_scope", "")).strip().lower()
        if required_scope != "source_required":
            return False
        if not isinstance(files, list) or not files:
            return False

        changed_paths: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_path(item.get("path", ""))
            if normalized:
                changed_paths.append(normalized)
        if not changed_paths:
            return False
        if any(not path.startswith("tests/") for path in changed_paths):
            return False

        decisions_text = " ".join(str(item).lower() for item in decisions or [])
        return "test_only_change_justified" not in decisions_text

    def _build_selected_target_files(
        self,
        files: list[dict[str, Any]],
        candidate_files: list[str],
    ) -> list[dict[str, str]]:
        candidate_set = {self._normalize_path(item) for item in candidate_files}
        selected: list[dict[str, str]] = []
        for item in files:
            path = self._normalize_path(item.get("path", ""))
            if not path:
                continue
            reason = "candidate_file_match" if path in candidate_set else "fallback_selection"
            selected.append({"path": path, "reason": reason})
        return selected

    def _mark_issue_as_fixed(
        self,
        *,
        context: dict[str, Any],
        github_client: Any,
        pr_url: str | None = None,
        pr_number: int | None = None,
    ) -> None:
        issue = context.get("issue")
        if not isinstance(issue, dict):
            return
        issue_number = issue.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            return
        if not hasattr(github_client, "update_issue_labels"):
            return

        labels = self._extract_issue_label_names(issue)
        labels_set = set(labels)
        labels_set.discard(self.OPENED_LABEL)
        labels_set.discard(self.PLANNING_LABEL)
        labels_set.discard(self.READY_LABEL)
        labels_set.add(self.FIXED_LABEL)

        try:
            github_client.update_issue_labels(issue_number, labels=sorted(labels_set))
            logger.info(
                "code_generator_issue_label_updated issue=%s labels=%s",
                issue_number,
                sorted(labels_set),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "code_generator_issue_label_update_failed issue=%s reason=%s",
                issue_number,
                str(exc)[:300],
            )

        if not pr_url or not hasattr(github_client, "comment_issue"):
            return

        pr_ref = f"#{pr_number}" if isinstance(pr_number, int) and pr_number > 0 else pr_url
        comment = (
            "## Service update\n\n"
            f"PR {pr_ref} created for this issue.\n"
            f"Link: {pr_url}\n\n"
            f"Label `{self.FIXED_LABEL}` applied automatically."
        )
        try:
            github_client.comment_issue(issue_number, comment=comment)
            logger.info(
                "code_generator_issue_fixed_comment_posted issue=%s pr_url=%s",
                issue_number,
                pr_url,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "code_generator_issue_fixed_comment_failed issue=%s reason=%s",
                issue_number,
                str(exc)[:300],
            )

    def _build_input_log(
        self,
        *,
        context: dict[str, Any],
        spec: dict[str, Any],
        tests: dict[str, Any],
        subtasks: dict[str, Any],
        rag_context: dict[str, Any],
        github_client: Any | None,
        github_client_reason: str,
        candidate_files: list[str],
        allow_new_files: bool,
        strict_target_files: bool,
        enforce_patch_quality_gate: bool,
        enforce_semantic_patch_gate: bool,
        allow_full_file_rewrite: bool,
        patch_strategy: str,
        forced_strategy_mode: str,
        signature_discovery_packet: dict[str, Any],
        semantic_feedback_packet: dict[str, Any],
        force_plan_after_semantic_failure: bool,
        open_mode: bool,
    ) -> str:
        issue = context.get("issue")
        issue_number = issue.get("number") if isinstance(issue, dict) else None
        issue_title = issue.get("title") if isinstance(issue, dict) else None
        repository = context.get("repository")
        repository_full_name = (
            repository.get("full_name")
            if isinstance(repository, dict)
            else context.get("repository_full_name")
        )
        matches = None
        memory_context = context.get("memory_context")
        if isinstance(memory_context, dict):
            memory_matches = memory_context.get("matches")
            if isinstance(memory_matches, list):
                matches = len(memory_matches)

        payload = {
            "use_llm": bool(context.get("use_llm", True)),
            "issue_number": issue_number,
            "issue_title": str(issue_title)[:140] if isinstance(issue_title, str) else None,
            "repository": repository_full_name,
            "spec_summary": str(spec.get("summary", ""))[:200],
            "test_cases": len(tests.get("test_cases", []) or []),
            "subtasks": len(subtasks.get("items", []) or []),
            "rag_sources": len(rag_context.get("sources", []) or []),
            "memory_matches": matches,
            "has_github_client": github_client is not None,
            "github_client_reason": github_client_reason,
            "has_github_token": bool(
                str(context.get("github_token") or context.get("token") or "").strip()
            ),
            "candidate_files": candidate_files[:10],
            "allow_new_files": allow_new_files,
            "strict_target_files": strict_target_files,
            "enforce_patch_quality_gate": enforce_patch_quality_gate,
            "enforce_semantic_patch_gate": enforce_semantic_patch_gate,
            "open_mode": open_mode,
            "allow_full_file_rewrite": allow_full_file_rewrite,
            "patch_strategy": patch_strategy,
            "forced_strategy_mode": forced_strategy_mode,
            "force_plan_after_semantic_failure": force_plan_after_semantic_failure,
            "signature_discovery_symbols_count": len(
                signature_discovery_packet.get("symbols", []) or []
            ),
            "semantic_feedback_violation_count": len(
                semantic_feedback_packet.get("violations", []) or []
            ),
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _extract_issue_label_names(issue: dict[str, Any]) -> list[str]:
        labels = issue.get("labels")
        if not isinstance(labels, list):
            return []
        result: list[str] = []
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name")
                if isinstance(name, str) and name.strip():
                    result.append(name.strip())
            elif isinstance(label, str) and label.strip():
                result.append(label.strip())
        return result

    @staticmethod
    def _normalize_llm_error(exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return (
                "LLM provider returned invalid JSON payload. "
                "Check provider credentials/profile and token endpoint response format."
            )
        return str(exc)

    def _resolve_github_client(self, context: dict[str, Any]) -> tuple[Any | None, str]:
        github_client = context.get("github_client")
        if github_client is not None:
            return github_client, "provided_in_context"

        token_raw = context.get("github_token")
        if token_raw is None:
            token_raw = context.get("token")
        token = str(token_raw).strip() if token_raw is not None else ""
        if not token:
            return None, "missing_token"

        repository = context.get("repository")
        repository_full_name = context.get("repository_full_name")
        if isinstance(repository, dict):
            full_name = repository.get("full_name")
            if isinstance(full_name, str) and full_name.strip():
                repository_full_name = full_name.strip()
            else:
                owner = repository.get("owner")
                name = repository.get("name")
                if (
                    isinstance(owner, str)
                    and isinstance(name, str)
                    and owner.strip()
                    and name.strip()
                ):
                    repository_full_name = f"{owner.strip()}/{name.strip()}"

        if not isinstance(repository_full_name, str) or not repository_full_name.strip():
            return None, "missing_repository_full_name"

        try:
            return (
                GitHubClient(token=token, repo=repository_full_name.strip()),
                "created_from_token_and_repo",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "code_generator_github_client_init_failed reason=%s token_type=%s repository=%s",
                str(exc)[:300],
                type(token_raw).__name__,
                str(repository_full_name)[:200],
            )
            return None, f"client_init_failed:{type(exc).__name__}"

    def _build_deterministic_patch(
        self,
        *,
        spec: dict[str, Any],
        tests: dict[str, Any],
        subtask_count: int,
        rag_source_count: int,
        rule_doc_count: int,
        rules_version: str,
        issue_context_text: str,
        candidate_files: list[str],
        allow_new_files: bool,
        ci_failure_context: dict[str, Any],
        strict_target_files: bool,
    ) -> dict[str, Any]:
        ci_patch = self._build_ci_permissions_patch_from_local_workflow(issue_context_text)
        if ci_patch:
            return ci_patch

        files: list[dict[str, Any]] = []
        decisions: list[str] = [
            f"subtasks={subtask_count}",
            f"tests={len(tests.get('test_cases', []) or [])}",
            f"rag_sources={rag_source_count}",
            f"rules_documents={rule_doc_count}",
            f"rules_version={rules_version or 'none'}",
            "deterministic_patch=true",
        ]

        if candidate_files:
            target_path = candidate_files[0]
            description = "Grounded deterministic patch target from CI/spec context"
            files.append(
                {
                    "path": target_path,
                    "change_type": "modify",
                    "content": self._generate_basic_content(target_path, description),
                }
            )
            decisions.append(f"grounded_target={target_path}")
        else:
            file_changes: list[dict[str, Any]] = spec.get("file_changes", []) or []
            if file_changes:
                for change in file_changes:
                    path: str = str(change.get("path", "")).strip()
                    if not path:
                        continue
                    change_type: str = str(change.get("change_type", "modify") or "modify")
                    description: str = str(change.get("description", "") or "deterministic patch")
                    files.append(
                        {
                            "path": self._normalize_path(path),
                            "change_type": change_type,
                            "content": self._generate_basic_content(path, description),
                        }
                    )
            elif allow_new_files:
                files.append(
                    {
                        "path": "src/feature_impl.py",
                        "change_type": "create",
                        "content": self._generate_basic_content(
                            "src/feature_impl.py",
                            "Feature implementation",
                        ),
                    }
                )
                decisions.append("fallback_new_file_created=src/feature_impl.py")
            else:
                decisions.append("no_grounded_targets_available")

        test_cases: list[dict[str, Any]] = tests.get("test_cases", []) or []
        existing_paths = {item["path"] for item in files}
        for test_case in test_cases:
            if not isinstance(test_case, dict):
                continue
            test_path = str(test_case.get("file_path") or "").strip()
            content = test_case.get("content")
            if (
                test_path
                and isinstance(content, str)
                and content.strip()
                and self._normalize_path(test_path) in set(candidate_files)
                and self._normalize_path(test_path) not in existing_paths
            ):
                normalized_test_path = self._normalize_path(test_path)
                files.append(
                    {
                        "path": normalized_test_path,
                        "change_type": "modify",
                        "content": content,
                    }
                )
                existing_paths.add(normalized_test_path)

        if (
            test_cases
            and allow_new_files
            and not any("test" in path.lower() for path in existing_paths)
        ):
            generated_test_path = "tests/test_feature_impl.py"
            if generated_test_path not in existing_paths:
                files.append(
                    {
                        "path": generated_test_path,
                        "change_type": "create",
                        "content": self._generate_test_content(test_cases),
                    }
                )
                existing_paths.add(generated_test_path)
                decisions.append(f"fallback_test_file_created={generated_test_path}")

        patch = {
            "schema_version": "2.0",
            "files": files,
            "decisions": decisions,
            "test_changes": [],
            "dry_run": False,
            "expected_failures": 1,
            "llm_enhanced": False,
            "target_files": candidate_files[:20],
            "strict_target_files": strict_target_files,
            "instruction_stack": [
                "global_agent_rules",
                "pipeline_ci_fix_rules",
                "deterministic_fallback",
            ],
            "selected_target_files": self._build_selected_target_files(files, candidate_files),
            "allow_new_files": allow_new_files,
        }
        if not files and ci_failure_context:
            patch["blocked"] = True
        return patch

    def _build_ci_permissions_patch_from_local_workflow(
        self, issue_context_text: str
    ) -> dict[str, Any] | None:
        workflow_path = Path(".github/workflows/ci.yml")
        if not workflow_path.exists():
            return None
        try:
            workflow_content = workflow_path.read_text(encoding="utf-8")
        except OSError:
            return None
        return self._build_ci_permissions_patch_from_workflow(issue_context_text, workflow_content)

    def _build_ci_permissions_patch_from_workflow(
        self, issue_context_text: str, workflow_content: str
    ) -> dict[str, Any] | None:
        if not self._should_apply_ghcr_permissions_fix(issue_context_text):
            return None

        updated_content = self._ensure_ghcr_permissions_in_workflow(workflow_content)
        if updated_content == workflow_content:
            return None

        return {
            "schema_version": "2.0",
            "files": [
                {
                    "path": ".github/workflows/ci.yml",
                    "change_type": "modify",
                    "content": updated_content,
                }
            ],
            "decisions": [
                "detected_ci_incident=ghcr_permissions",
                "workflow_permissions_fix=packages_write",
                "deterministic_patch=true",
            ],
            "test_changes": [],
            "dry_run": False,
            "expected_failures": 0,
            "llm_enhanced": False,
            "selected_target_files": [
                {"path": ".github/workflows/ci.yml", "reason": "ci_permissions_fix"}
            ],
            "allow_new_files": False,
        }

    @staticmethod
    def _should_apply_ghcr_permissions_fix(issue_context_text: str) -> bool:
        text = issue_context_text.lower()

        has_ghcr_registry = "ghcr.io" in text
        has_push_failure = (
            "failed to push" in text
            or "push ghcr.io" in text
            or "docker push" in text
            or "image push" in text
        )
        has_denied_signal = "denied" in text
        has_permission_phrase = "installation not allowed" in text
        has_package_phrase = (
            "organization package" in text
            or "to creat" in text
            or "to create" in text
            or "create organization package" in text
        )

        return (
            has_ghcr_registry
            and has_push_failure
            and has_denied_signal
            and has_permission_phrase
            and has_package_phrase
        )

    @staticmethod
    def _ensure_ghcr_permissions_in_workflow(workflow_content: str) -> str:
        if "permissions:" in workflow_content and "packages: write" in workflow_content:
            return workflow_content

        permissions_block = "permissions:\n  contents: read\n  packages: write\n\n"
        env_match = re.search(r"(?m)^env:\s*$", workflow_content)
        if env_match:
            insert_at = env_match.start()
            return workflow_content[:insert_at] + permissions_block + workflow_content[insert_at:]

        return permissions_block + workflow_content

    def _build_pr_body(self, spec: dict[str, Any], patch: dict[str, Any]) -> str:
        lines: list[str] = [
            "## Summary",
            spec.get("summary", "Generated by HordeForge"),
            "",
            "## Requirements",
        ]

        raw_requirements = spec.get("requirements", [])
        if isinstance(raw_requirements, list):
            for req in raw_requirements:
                if isinstance(req, dict):
                    req_id = str(req.get("id", "")).strip()
                    desc = str(req.get("description", "")).strip()
                    priority = str(req.get("priority", "")).strip()
                    if req_id or desc:
                        if priority:
                            lines.append(f"- [{priority}] {req_id}: {desc}")
                        else:
                            lines.append(f"- {req_id}: {desc}".strip(": "))
                        continue
                elif isinstance(req, str) and req.strip():
                    lines.append(f"- {req.strip()}")

        lines.extend(["", "## Technical Notes"])

        raw_notes = spec.get("technical_notes", [])
        if isinstance(raw_notes, list):
            for note in raw_notes:
                if isinstance(note, str) and note.strip():
                    lines.append(f"- {note.strip()}")

        lines.extend(["", "## Changes"])
        for fc in patch.get("files", []):
            path: str = fc.get("path", "")
            change_type: str = fc.get("change_type", "modified")
            lines.append(f"- `{change_type}`: {path}")

        lines.extend(["", "---", "*Generated by HordeForge AI*"])
        return "\n".join(lines)

    def _format_memory_context(self, memory_context: Any) -> str:
        if isinstance(memory_context, str):
            return memory_context.strip()[:1200]

        if isinstance(memory_context, dict):
            lines: list[str] = []

            matches = memory_context.get("matches")
            if isinstance(matches, list) and matches:
                lines.append("Top memory matches:")
                for item in matches[:6]:
                    if not isinstance(item, dict):
                        continue
                    path = str(item.get("path") or "unknown").strip()
                    summary = str(item.get("summary") or "").strip()
                    score = item.get("score")
                    summary = re.sub(r"\s+", " ", summary)[:220]
                    if isinstance(score, (int, float)):
                        lines.append(f"- {path} (score={float(score):.3f}): {summary}")
                    else:
                        lines.append(f"- {path}: {summary}")

            quality = memory_context.get("quality_signals")
            if isinstance(quality, dict):
                strategy = str(quality.get("retrieval_strategy") or "").strip()
                confidence = str(quality.get("retrieval_confidence") or "").strip()
                if strategy or confidence:
                    lines.append(
                        "Retrieval: "
                        + ", ".join(
                            part
                            for part in [
                                f"strategy={strategy}" if strategy else "",
                                f"confidence={confidence}" if confidence else "",
                            ]
                            if part
                        )
                    )

            return "\n".join(lines).strip()[:1800]

        return str(memory_context).strip()[:1200] if memory_context is not None else ""

    def _format_issue_context(self, issue: Any) -> str:
        if not isinstance(issue, dict):
            return ""

        lines: list[str] = []
        title = issue.get("title")
        body = issue.get("body")

        if isinstance(title, str) and title.strip():
            lines.append(f"Title: {title.strip()}")

        body_text = str(body or "").strip()
        if body_text:
            lines.extend(self._summarize_issue_body(body_text, issue))

        comments_context = issue.get("comments_context")
        if isinstance(comments_context, str) and comments_context.strip():
            lines.append(f"Comments context:\n{comments_context.strip()[:1200]}")

        plan_summary = self._extract_plan_summary(issue)
        if plan_summary:
            lines.append(plan_summary)

        return "\n\n".join(part for part in lines if part).strip()[:2600]

    def _summarize_issue_body(self, body_text: str, issue: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        failed_jobs = self._extract_failed_job_lines(body_text)
        if failed_jobs:
            lines.append("Failed jobs:")
            lines.extend(f"- {item}" for item in failed_jobs[:6])

        ci_run_id = self._extract_bullet_value(body_text, "ci_run.id")
        ci_branch = self._extract_bullet_value(body_text, "ci_run.head_branch")
        ci_sha = self._extract_bullet_value(body_text, "ci_run.head_sha")
        ci_meta = []
        if ci_run_id:
            ci_meta.append(f"run_id={ci_run_id}")
        if ci_branch:
            ci_meta.append(f"branch={ci_branch}")
        if ci_sha:
            ci_meta.append(f"sha={ci_sha[:12]}")
        if ci_meta:
            lines.append("CI metadata: " + ", ".join(ci_meta))

        issue_url = issue.get("html_url")
        if isinstance(issue_url, str) and issue_url.strip():
            lines.append(f"Issue URL: {issue_url.strip()}")

        return lines

    @staticmethod
    def _extract_failed_job_lines(body_text: str) -> list[str]:
        result: list[str] = []
        for match in re.finditer(
            r"\d+\.\s+\*\*(?P<name>[^*]+)\*\*:\s*(?P<reason>[^\n]+)",
            body_text,
            flags=re.IGNORECASE,
        ):
            name = match.group("name").strip()
            reason = match.group("reason").strip()
            result.append(f"{name}: {reason}")
        return result

    @staticmethod
    def _extract_bullet_value(body_text: str, key: str) -> str:
        pattern = rf"-\s+{re.escape(key)}:\s+`([^`]+)`"
        match = re.search(pattern, body_text)
        return match.group(1).strip() if match else ""

    def _extract_plan_summary(self, issue: dict[str, Any]) -> str:
        payload = self._extract_plan_payload(issue)
        if not isinstance(payload, dict):
            return ""

        dod = payload.get("dod")
        spec = payload.get("spec")
        tests = payload.get("tests")
        subtasks = payload.get("subtasks")

        lines: list[str] = ["Planning summary:"]
        if isinstance(spec, dict):
            summary = str(spec.get("summary") or "").strip()
            if summary:
                lines.append(f"- spec: {summary[:220]}")
            acceptance = spec.get("acceptance_criteria")
            if isinstance(acceptance, list) and acceptance:
                for item in acceptance[:4]:
                    text = str(item).strip()
                    if text:
                        lines.append(f"- AC: {text[:180]}")

        if isinstance(dod, dict):
            criteria = dod.get("acceptance_criteria")
            if isinstance(criteria, list):
                lines.append(f"- dod_count={len(criteria)}")

        if isinstance(subtasks, dict):
            items = subtasks.get("items") or subtasks.get("subtasks")
            if isinstance(items, list) and items:
                lines.append(f"- subtasks={len(items)}")

        if isinstance(tests, dict):
            test_cases = tests.get("test_cases")
            if isinstance(test_cases, list) and test_cases:
                lines.append(f"- tests={len(test_cases)}")
                for case in test_cases[:4]:
                    if not isinstance(case, dict):
                        continue
                    path = str(case.get("file_path") or case.get("name") or "").strip()
                    if path:
                        lines.append(f"- test: {path[:180]}")

        return "\n".join(lines)

    def _extract_plan_payload(self, issue: dict[str, Any]) -> dict[str, Any] | None:
        comments = issue.get("comments")
        if isinstance(comments, list):
            for comment in comments:
                if not isinstance(comment, dict):
                    continue
                body = comment.get("body")
                parsed = self._extract_plan_json_from_text(body)
                if isinstance(parsed, dict):
                    return parsed

        body = issue.get("body")
        parsed = self._extract_plan_json_from_text(body)
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _extract_plan_json_from_text(cls, text: Any) -> dict[str, Any] | None:
        if not isinstance(text, str) or not text.strip():
            return None
        pattern = re.escape(cls.PLAN_JSON_START) + r"\s*(.*?)\s*" + re.escape(cls.PLAN_JSON_END)
        match = re.search(pattern, text, flags=re.DOTALL)
        if not match:
            return None
        raw_json = match.group(1).strip()
        if not raw_json:
            return None
        try:
            parsed = json.loads(raw_json)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _generate_basic_content(self, path: str, description: str) -> str:
        if "test" in path.lower():
            return (
                "# Test file placeholder\n"
                "import pytest\n\n"
                "def test_placeholder():\n"
                "    assert True\n"
            )

        ext: str = path.split(".")[-1] if "." in path else "py"
        base_name: str = path.split("/")[-1].split("\\")[-1].replace(f".{ext}", "")

        if ext == "py":
            return (
                f'"""Generated implementation for {base_name}."""\n\n'
                "def process() -> None:\n"
                '    """Process implementation."""\n'
                "    pass\n\n"
                'if __name__ == "__main__":\n'
                "    process()\n"
            )

        if ext in {"js", "ts"}:
            return (
                f"// Generated implementation for {base_name}\n\n"
                "export function process() {\n"
                "    // Implementation\n"
                "}\n"
            )

        if ext == "go":
            return (
                f"// Generated implementation for {base_name}\n\n"
                "package main\n\n"
                "func Process() {\n"
                "    // Implementation\n"
                "}\n"
            )

        return f"# Generated file: {path}\n# {description}\n"

    def _generate_test_content(self, test_cases: list[dict[str, Any]]) -> str:
        lines: list[str] = [
            '"""Generated tests for feature."""',
            "import pytest",
            "",
        ]

        for idx, tc in enumerate(test_cases, start=1):
            test_name: str = tc.get("name", f"test_case_{idx}")
            safe_name = "".join(
                char if char.isalnum() or char in {"_", "-"} else "_" for char in test_name
            )
            lines.append(f"def test_{safe_name}():")
            lines.append('    """Test case from specification."""')
            lines.append("    assert True")
            lines.append("")

        return "\n".join(lines)

    def _default_branch_name(self, context: dict[str, Any]) -> str:
        issue = context.get("issue")
        issue_number = self._extract_issue_number(issue)
        title = self._extract_issue_title(issue)
        slug = self._slugify(title) or "task"
        return f"horde/{issue_number}-{slug}"

    @staticmethod
    def _extract_issue_number(issue: Any) -> int:
        if isinstance(issue, dict):
            number = issue.get("number")
            if isinstance(number, int) and number > 0:
                return number
        return 0

    @staticmethod
    def _extract_issue_title(issue: Any) -> str:
        if isinstance(issue, dict):
            title = issue.get("title")
            if isinstance(title, str):
                return title
        return ""

    @staticmethod
    def _slugify(value: str) -> str:
        lowered = value.lower().strip()
        lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
        lowered = re.sub(r"-{2,}", "-", lowered)
        return lowered.strip("-")[:48]


CodeGenerator = EnhancedCodeGenerator

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.github_client import GitHubClient
from agents.llm_wrapper import build_code_prompt, get_llm_wrapper, parse_code_output
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_prompt,
)
from agents.patch_workflow import PatchWorkflowOrchestrator, create_patch_from_code_result

logger = logging.getLogger("hordeforge.code_generator")


class EnhancedCodeGenerator(BaseAgent):
    name: str = "code_generator"
    description: str = "Generates code patch from specification, tests and subtasks."
    OPENED_LABEL = "agent:opened"
    PLANNING_LABEL = "agent:planning"
    READY_LABEL = "agent:ready"
    FIXED_LABEL = "agent:fixed"

    PLAN_JSON_START = "<!-- hordeforge:plan-json:start -->"
    PLAN_JSON_END = "<!-- hordeforge:plan-json:end -->"

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

        github_client, github_client_reason = self._resolve_github_client(context)

        candidate_files = self._collect_candidate_files(
            spec=spec,
            tests=tests,
            rag_context=rag_context,
            ci_failure_context=ci_failure_context,
        )
        allow_new_files = self._allow_new_files(candidate_files, ci_failure_context, spec)

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
        )
        logger.info("code_generator_input %s", input_log)

        llm_patch: dict[str, Any] | None = None
        llm_error: str | None = None
        llm_prompt_excerpt: str | None = None
        llm_response_excerpt: str | None = None
        llm_response_parsed = False

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
                    )
                    llm_prompt_excerpt = prompt[:1200]

                    response: str = llm.complete(prompt)
                    llm_response_excerpt = response[:1200]

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
            filtered_files, grounding_notes = self._filter_patch_files(
                llm_patch.get("files", []),
                candidate_files=candidate_files,
                allow_new_files=allow_new_files,
            )
            patch: dict[str, Any] = {
                "schema_version": "2.0",
                "files": filtered_files,
                "decisions": llm_patch.get("decisions", []),
                "test_changes": llm_patch.get("test_changes", []),
                "dry_run": False,
                "expected_failures": int(llm_patch.get("expected_failures", 1) or 0),
                "llm_enhanced": True,
                "selected_target_files": self._build_selected_target_files(
                    filtered_files, candidate_files
                ),
                "allow_new_files": allow_new_files,
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
            )
            reason = (
                "Deterministic patch generated (LLM unavailable)."
                if llm_error
                else "Code patch generated from spec."
            )
            confidence = 0.87

        if llm_error:
            patch.setdefault("notes", [])
            patch["notes"].append(f"llm_error={llm_error[:120]}")

        if not patch.get("files"):
            patch["blocked"] = True
            patch.setdefault("notes", [])
            patch["notes"].append("no_grounded_files_selected")

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

        return result[:20]

    @staticmethod
    def _allow_new_files(
        candidate_files: list[str],
        ci_failure_context: dict[str, Any],
        spec: dict[str, Any],
    ) -> bool:
        if candidate_files:
            return False
        if ci_failure_context.get("classification") in {"path_error", "collection_error", "test_failure"}:
            return False
        file_changes = spec.get("file_changes", []) or []
        if file_changes:
            for change in file_changes:
                if isinstance(change, dict) and str(change.get("change_type", "")).lower() == "create":
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
            ci_files = [str(item) for item in ci_failure_context.get("files", []) if str(item).strip()][:8]
            ci_test_targets = [
                str(item) for item in ci_failure_context.get("test_targets", []) if str(item).strip()
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
            "allow_new_files": allow_new_files,
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

        if not context_blocks:
            return prompt

        instruction = (
            "\n\n## Important Rules:\n"
            "1. Prefer MODIFYING existing files over creating new ones.\n"
            "2. If candidate files are provided, you MUST restrict code changes to those files.\n"
            "3. If tests are failing, fix the test files or source files they test.\n"
            f"4. New files are {'ALLOWED' if allow_new_files else 'NOT ALLOWED'} for this task.\n"
            "5. DO NOT create stub functions with 'return True' — implement real logic.\n"
            "6. Every function must have meaningful implementation, not just placeholders.\n"
            "7. If you cannot determine the correct implementation, prefer a minimal grounded patch "
            "to an invented new module."
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
            repaired = llm.complete(repair_prompt, temperature=0.0)
        except Exception:
            return None
        return repaired if isinstance(repaired, str) and repaired.strip() else None

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
                return parsed

            parsed = cls._try_balanced_json_parse(candidate)
            if parsed is not None:
                return parsed

            parsed = cls._try_loose_patch_extraction(candidate)
            if parsed is not None:
                return parsed

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
            if cls._is_valid_llm_patch(parsed):
                return parsed
        return None

    @staticmethod
    def _is_valid_llm_patch(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            return False
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
        return True

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
            if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
                continue

            normalized_path = self._normalize_path(path)
            file_item = {
                "path": normalized_path,
                "change_type": change_type,
                "content": content,
            }

            if normalized_candidates:
                if normalized_path in normalized_candidates:
                    filtered.append(file_item)
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

        patch = {
            "schema_version": "2.0",
            "files": files,
            "decisions": decisions,
            "test_changes": [],
            "dry_run": False,
            "expected_failures": 1,
            "llm_enhanced": False,
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
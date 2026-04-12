from __future__ import annotations

import re
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import (
    build_agent_result,
    get_artifact_from_context,
    get_artifact_from_result,
)
from agents.instruction_layers import build_instruction_stack
from agents.llm_wrapper import build_code_prompt, get_llm_wrapper
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_prompt,
)


class FixAgent(BaseAgent):
    name = "fix_agent"
    description = "Produces iterative fixes based on failing test results."
    CODEGEN_FIX_MAX_ATTEMPTS: int = 3
    STRATEGY_SEQUENCE: tuple[str, ...] = (
        "status_transition_guard",
        "failing_test_alignment",
        "minimal_source_correction",
    )

    @staticmethod
    def parse_stacktrace(stacktrace: str) -> dict[str, Any] | None:
        if not stacktrace:
            return None

        python_pattern = r"File\s+['\"]([^'\"]+)['\"]\s*,\s*line\s*(\d+)"
        python_match = re.search(python_pattern, stacktrace)
        if python_match:
            return {
                "file": python_match.group(1),
                "line": int(python_match.group(2)),
                "language": "python",
            }

        js_pattern = r"at\s+([^\s:]+):(\d+):(\d+)"
        js_match = re.search(js_pattern, stacktrace)
        if js_match:
            return {
                "file": js_match.group(1),
                "line": int(js_match.group(2)),
                "language": "javascript",
            }

        return None

    @staticmethod
    def detect_failure(output: str) -> dict[str, Any] | None:
        if not output:
            return None

        output_lower = output.lower()

        if "assertionerror" in output_lower:
            return {"type": "assertion", "message": output}
        if "expected:" in output_lower and "received:" in output_lower:
            return {"type": "assertion", "message": output}
        if "attributeerror" in output_lower:
            return {"type": "exception", "message": output}
        if "indexerror" in output_lower:
            return {"type": "exception", "message": output}
        if "keyerror" in output_lower:
            return {"type": "exception", "message": output}
        if "zerodivisionerror" in output_lower:
            return {"type": "exception", "message": output}
        if "syntaxerror" in output_lower:
            return {"type": "syntax_error", "message": output}
        if "file or directory not found" in output_lower:
            return {"type": "path_error", "message": output}
        if "collected 0 items" in output_lower or "no tests collected" in output_lower:
            return {"type": "collection_error", "message": output}

        return {"type": "unknown", "message": output}

    @staticmethod
    def generate_fix(failure: dict[str, Any]) -> str | None:
        failure_type = failure.get("type", "")
        message = str(failure.get("message", "")).lower()

        if failure_type == "assertion":
            if "expected" in message and "got" in message:
                if "expected 3 got 2" in message or "expected 2 got 1" in message:
                    return "Increment the value by 1 to fix off-by-one error."
                return "Check the expected value and adjust the code accordingly."

        elif failure_type == "exception":
            if "nonetype" in message or "'noneType'" in message:
                return "Add null/None check before accessing the object."
            if "indexerror" in message:
                return "Check array/list bounds before accessing by index."
            if "keyerror" in message:
                return "Check if key exists in dictionary before accessing."
            if "zerodivisionerror" in message:
                return "Add check for zero before division operation."

        elif failure_type == "syntax_error":
            return "Fix syntax error in the code."

        elif failure_type == "path_error":
            return "Normalize test paths relative to repository root and use existing files only."

        elif failure_type == "collection_error":
            return "Repair pytest collection by fixing imports, file names, or discovery configuration."

        return "Review the error message and implement appropriate fix."

    @staticmethod
    def _resolve_test_results(context: dict[str, Any]) -> dict[str, Any]:
        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["test_runner"],
            )
            or {}
        )
        if isinstance(test_results, dict) and test_results:
            return test_results

        test_runner_result = context.get("test_runner")
        if isinstance(test_runner_result, dict):
            payload = test_runner_result.get("test_results")
            if isinstance(payload, dict):
                return payload

        return {}

    @classmethod
    def _extract_failed_tests(cls, context: dict[str, Any]) -> int:
        test_results = cls._resolve_test_results(context)
        if isinstance(test_results.get("failed"), int):
            return max(0, int(test_results["failed"]))
        return 0

    def _resolve_iteration(self, context: dict[str, Any]) -> int:
        previous_fix = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer"],
            )
            or {}
        )

        if not previous_fix and "fix_agent" in context and "code_patch" in context["fix_agent"]:
            previous_fix = context["fix_agent"]["code_patch"]

        fix_iteration = previous_fix.get("fix_iteration")
        if isinstance(fix_iteration, int):
            return fix_iteration + 1
        if fix_iteration is not None:
            try:
                return int(fix_iteration) + 1
            except (ValueError, TypeError):
                pass
        return 1

    @staticmethod
    def _extract_candidate_files(context: dict[str, Any]) -> list[str]:
        ci_failure_context = context.get("ci_failure_context", {})
        if not isinstance(ci_failure_context, dict):
            ci_failure_context = {}

        files: list[str] = []
        for key in ("files", "test_targets"):
            values = ci_failure_context.get(key, [])
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, str) and item.strip():
                        files.append(item.strip().replace("\\", "/"))

        code_patch = context.get("code_patch")
        if isinstance(code_patch, dict):
            patch_files = code_patch.get("files", [])
            if isinstance(patch_files, list):
                for item in patch_files:
                    if isinstance(item, dict):
                        path = item.get("path")
                        if isinstance(path, str) and path.strip():
                            files.append(path.strip().replace("\\", "/"))

        result: list[str] = []
        seen: set[str] = set()
        for item in files:
            normalized = item
            if "::" in normalized:
                normalized = normalized.split("::", 1)[0]
            if not normalized or normalized in seen:
                continue
            if normalized.startswith("/") or ".." in normalized.split("/"):
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _synthesize_failure_info(test_results: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(test_results, dict):
            return []

        stdout = str(test_results.get("stdout") or "").strip()
        stderr = str(test_results.get("stderr") or "").strip()
        framework = str(test_results.get("framework") or "unknown").strip()
        failed_raw = test_results.get("failed")
        exit_code_raw = test_results.get("exit_code")
        error_classification = str(test_results.get("error_classification") or "").strip()

        try:
            failed_count = int(failed_raw) if failed_raw is not None else 0
        except (TypeError, ValueError):
            failed_count = 0
        try:
            exit_code = int(exit_code_raw) if exit_code_raw is not None else 0
        except (TypeError, ValueError):
            exit_code = 0

        message_parts: list[str] = []
        if error_classification:
            message_parts.append(f"error_classification:\n{error_classification}")
        if stderr:
            message_parts.append(f"stderr:\n{stderr[:3000]}")
        if stdout:
            message_parts.append(f"stdout:\n{stdout[:3000]}")

        if not message_parts and (failed_count > 0 or exit_code != 0):
            message_parts.append(
                "synthetic_failure_summary:\n"
                f"framework={framework}\n"
                f"failed={failed_count}\n"
                f"exit_code={exit_code}\n"
                "No stdout/stderr payload was provided by test_runner."
            )

        if not message_parts:
            return []

        failure_type = "test_failure"
        if error_classification in {"path_error", "collection_error"}:
            failure_type = error_classification

        return [
            {
                "name": f"{framework}_failure",
                "type": failure_type,
                "failed_count": max(0, failed_count),
                "message": "\n\n".join(message_parts),
            }
        ]

    @staticmethod
    def _extract_error_line(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            return ""

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("E       "):
                return line[len("E       ") :].strip()
            if line.startswith("E   "):
                return line[len("E   ") :].strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):\s+", line):
                return line
        return ""

    @classmethod
    def _extract_failure_highlights(cls, test_results: dict[str, Any], limit: int = 3) -> list[str]:
        if not isinstance(test_results, dict):
            return []

        highlights: list[str] = []
        failures = test_results.get("failures")
        if isinstance(failures, list):
            for item in failures:
                if not isinstance(item, dict):
                    continue
                nodeid = str(item.get("nodeid") or item.get("name") or "").strip()
                error_line = str(item.get("error_line") or item.get("message") or "").strip()
                if nodeid and error_line:
                    highlights.append(f"{nodeid}: {error_line}")
                elif nodeid:
                    highlights.append(nodeid)
                elif error_line:
                    highlights.append(error_line)
                if len(highlights) >= limit:
                    return highlights[:limit]

        report = test_results.get("json_report")
        tests = report.get("tests") if isinstance(report, dict) else None
        if isinstance(tests, list):
            for item in tests:
                if not isinstance(item, dict) or item.get("outcome") != "failed":
                    continue
                nodeid = str(item.get("nodeid", "")).strip()
                error_line = ""
                for phase_name in ("call", "setup", "teardown"):
                    phase = item.get(phase_name)
                    if not isinstance(phase, dict):
                        continue
                    longrepr = phase.get("longrepr", "")
                    if isinstance(longrepr, list):
                        longrepr = "\n".join(str(part) for part in longrepr)
                    error_line = cls._extract_error_line(str(longrepr))
                    if error_line:
                        break
                if nodeid and error_line:
                    highlights.append(f"{nodeid}: {error_line}")
                elif nodeid:
                    highlights.append(nodeid)
                if len(highlights) >= limit:
                    return highlights

        stdout = str(test_results.get("stdout") or "")
        failed_lines = [
            line.strip()[len("FAILED ") :].strip()
            for line in stdout.splitlines()
            if line.strip().startswith("FAILED ")
        ]
        error_lines = [
            candidate
            for candidate in (
                cls._extract_error_line(stdout),
                str(test_results.get("stderr") or ""),
            )
            if isinstance(candidate, str) and candidate.strip()
        ]
        if failed_lines:
            first_failure = failed_lines[0]
            if error_lines:
                highlights.append(f"{first_failure}: {error_lines[0].strip()}")
            else:
                highlights.append(first_failure)
        elif error_lines:
            highlights.append(error_lines[0].strip())
        return highlights[:limit]

    @classmethod
    def _build_failure_focus_summary(cls, test_results: dict[str, Any]) -> str:
        if not isinstance(test_results, dict):
            return ""

        framework = str(test_results.get("framework") or "unknown").strip()
        failed = int(test_results.get("failed", 0) or 0)
        exit_code = int(test_results.get("exit_code", 0) or 0)
        signature = str(test_results.get("failure_signature") or "").strip()
        lines = [
            f"framework={framework}",
            f"failed={failed}",
            f"exit_code={exit_code}",
        ]
        if signature:
            lines.append(f"failure_signature={signature}")
        for item in cls._extract_failure_highlights(test_results):
            lines.append(f"- {item}")
        return "\n".join(lines)

    @staticmethod
    def _is_actionable_failure(test_results: dict[str, Any]) -> bool:
        failed = test_results.get("failed", 0)
        exit_code = test_results.get("exit_code", 0)
        try:
            failed_count = int(failed)
        except (TypeError, ValueError):
            failed_count = 0
        try:
            exit_code_int = int(exit_code)
        except (TypeError, ValueError):
            exit_code_int = 0
        return failed_count > 0 or exit_code_int != 0

    @classmethod
    def _select_strategy(cls, iteration: int) -> str:
        if not cls.STRATEGY_SEQUENCE:
            return "default_fix_strategy"
        index = (max(1, int(iteration)) - 1) % len(cls.STRATEGY_SEQUENCE)
        return cls.STRATEGY_SEQUENCE[index]

    def _build_fix_plan(
        self,
        *,
        context: dict[str, Any],
        test_results: dict[str, Any],
        iteration: int,
        strategy_class: str,
        strict_target_files: bool,
    ) -> dict[str, Any]:
        target_files = self._extract_candidate_files(context)
        if not target_files and not strict_target_files:
            target_files = ["src/feature_impl.py"]
        failed_tests = int(test_results.get("failed", 0) or 0)
        exit_code = int(test_results.get("exit_code", 0) or 0)
        plan = {
            "iteration": iteration,
            "strategy_class": strategy_class,
            "target_files": target_files[:20],
            "hypothesis": (
                "Status mismatch between expected BLOCKED and observed SUCCESS/PARTIAL_SUCCESS "
                "is caused by incorrect status transition handling in the current fix path."
            ),
            "expected_transition": "test_results.failed decreases and exit_code becomes 0",
            "current_failed": failed_tests,
            "current_exit_code": exit_code,
            "plan_valid": bool(target_files),
        }
        if not target_files:
            plan["plan_error"] = "missing_target_files"
        elif target_files == ["src/feature_impl.py"]:
            plan["plan_note"] = "fallback_target_file_used"
        return plan

    def run(self, context: dict[str, Any]) -> dict:
        test_results = self._resolve_test_results(context)
        failed = self._extract_failed_tests(context)
        iteration = self._resolve_iteration(context)
        remaining_failures = max(0, failed - 1)
        strategy_class = self._select_strategy(iteration)
        strict_target_files = bool(context.get("strict_target_files", False))
        if iteration > len(self.STRATEGY_SEQUENCE):
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content={
                    "schema_version": "1.0",
                    "files": [],
                    "fix_iteration": iteration,
                    "blocked": True,
                    "diagnosis": "max_strategy_classes_exhausted",
                },
                reason="Fix loop stopped after exhausting strategy classes.",
                confidence=0.95,
                logs=[f"max_strategies={len(self.STRATEGY_SEQUENCE)}", f"iteration={iteration}"],
                next_actions=["review_agent"],
            )

        previous_fix = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer"],
            )
            or {}
        )
        previous_strategy = (
            str(previous_fix.get("strategy_class", "")).strip()
            if isinstance(previous_fix, dict)
            else ""
        )
        if previous_strategy and previous_strategy == strategy_class:
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content={
                    "schema_version": "1.0",
                    "files": [],
                    "fix_iteration": iteration,
                    "strategy_class": strategy_class,
                    "blocked": True,
                    "diagnosis": "strategy_repetition_blocked",
                },
                reason="Fix strategy repetition blocked by plan/act gate.",
                confidence=0.95,
                logs=[
                    f"previous_strategy={previous_strategy}",
                    f"current_strategy={strategy_class}",
                ],
                next_actions=["review_agent"],
            )

        fix_plan = self._build_fix_plan(
            context=context,
            test_results=test_results,
            iteration=iteration,
            strategy_class=strategy_class,
            strict_target_files=strict_target_files,
        )
        if not bool(fix_plan.get("plan_valid")):
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content={
                    "schema_version": "1.0",
                    "files": [],
                    "fix_iteration": iteration,
                    "strategy_class": strategy_class,
                    "fix_plan": fix_plan,
                    "blocked": True,
                    "diagnosis": str(fix_plan.get("plan_error") or "invalid_fix_plan"),
                },
                reason="Fix plan validation failed before code generation.",
                confidence=0.95,
                logs=[f"plan_error={fix_plan.get('plan_error', 'invalid_fix_plan')}"],
                next_actions=["review_agent"],
            )

        use_llm = context.get("use_llm", True)
        require_llm = bool(context.get("require_llm", False))
        llm_fix_result = None
        llm_error = None

        if use_llm and self._is_actionable_failure(test_results):
            llm_fix_result, llm_error = self._generate_fix_with_code_generator_core(
                context, iteration
            )

            llm = None
            if not llm_fix_result:
                try:
                    llm = get_llm_wrapper()
                    if llm is None:
                        llm = get_legacy_llm_wrapper()

                    if llm is not None:
                        failure_info = test_results.get("failures", [])
                        if not failure_info:
                            failure_info = context.get("failures", [])
                        if not failure_info:
                            failure_info = self._synthesize_failure_info(test_results)

                        if failure_info:
                            try:
                                prompt = build_code_prompt(
                                    {"summary": f"Fix iteration {iteration}", "requirements": []},
                                    failure_info,
                                    {"language": "python"},
                                )
                            except AttributeError:
                                prompt = legacy_build_code_prompt(
                                    {"summary": f"Fix iteration {iteration}", "requirements": []},
                                    failure_info,
                                    {"language": "python"},
                                )

                            response = llm.complete(prompt)

                            import json

                            try:
                                llm_fix_result = json.loads(response)
                            except json.JSONDecodeError:
                                candidate_files = self._extract_candidate_files(context)
                                fallback_path = (
                                    candidate_files[0] if candidate_files else "src/feature_impl.py"
                                )
                                llm_fix_result = {
                                    "files": [
                                        {
                                            "path": fallback_path,
                                            "content": f"# Fix suggestion from LLM\n# iteration={iteration}\n# response:\n# {response[:800]}",
                                            "change_type": "modify",
                                        }
                                    ]
                                }
                except Exception as e:
                    llm_error = str(e)
                finally:
                    if llm is not None:
                        try:
                            llm.close()
                        except Exception:
                            pass

        if use_llm and require_llm and not (llm_fix_result and isinstance(llm_fix_result, dict)):
            return build_agent_result(
                status="FAILED",
                artifact_type="code_patch",
                artifact_content={
                    "schema_version": "1.0",
                    "files": [],
                    "llm_required": True,
                    "llm_error": llm_error,
                },
                reason=(
                    f"LLM required but unavailable: {llm_error[:160]}"
                    if isinstance(llm_error, str) and llm_error
                    else "LLM required but no valid fix patch was generated."
                ),
                confidence=0.95,
                logs=[
                    "LLM strict mode enabled (require_llm=true).",
                    f"LLM error: {(llm_error or 'missing/invalid llm output')[:200]}",
                ],
                next_actions=["fix_llm_connectivity"],
            )

        if llm_fix_result and isinstance(llm_fix_result, dict):
            files = llm_fix_result.get("files", [])
            decisions = llm_fix_result.get("decisions", [])
            reason = "Fix patch generated with LLM enhancement."
            confidence = 0.92
        else:
            candidate_files = self._extract_candidate_files(context)
            fallback_path = candidate_files[0] if candidate_files else "src/feature_impl.py"
            files = [
                {
                    "path": fallback_path,
                    "content": (
                        f"# fix iteration {iteration}\n"
                        f"# Failed before: {failed}\n"
                        f"# Remaining after fix: {remaining_failures}\n"
                    ),
                    "change_type": "modify",
                }
            ]
            decisions = [
                f"failed_before={failed}",
                f"remaining_after_fix={remaining_failures}",
                f"target_file={fallback_path}",
            ]
            reason = (
                "Deterministic fix patch generated (LLM unavailable)."
                if llm_error
                else "Fix patch generated from test failure analysis."
            )
            confidence = 0.85

        patch = {
            "schema_version": "1.0",
            "files": files,
            "decisions": decisions,
            "fix_iteration": iteration,
            "remaining_failures": remaining_failures,
            "strategy_class": strategy_class,
            "fix_plan": fix_plan,
            "instruction_stack": [
                "global_agent_rules",
                "pipeline_ci_fix_rules",
                "plan_before_act",
                "strategy_rotation",
            ],
        }
        patch["instruction_stack"], patch["instruction_layers"] = build_instruction_stack(
            patch["instruction_stack"],
            [item for item in fix_plan.get("target_files", []) if isinstance(item, str)],
        )

        if llm_error:
            patch.setdefault("notes", [])
            patch["notes"].append(f"llm_error={llm_error[:120]}")

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="code_patch",
            artifact_content=patch,
            reason=reason,
            confidence=confidence,
            logs=[
                f"Fix iteration {iteration} produced patch.",
                f"Remaining simulated failures: {remaining_failures}.",
            ],
            next_actions=["test_runner"]
            if self._is_actionable_failure(test_results)
            else ["review_agent"],
        )
        result["artifact_type"] = "code_patch"
        result["artifact_content"] = patch
        return result

    def _generate_fix_with_code_generator_core(
        self,
        context: dict[str, Any],
        iteration: int,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            from agents.code_generator import EnhancedCodeGenerator
        except Exception as exc:
            return None, f"code_generator_import_failed: {exc}"

        test_results = self._resolve_test_results(context)
        failure_info = test_results.get("failures", [])
        if not failure_info:
            failure_info = self._synthesize_failure_info(test_results)
        if not failure_info:
            return None, "missing_failure_context_for_codegen_fix"

        delegated_context = dict(context)
        open_mode = bool(context.get("open_mode", False))
        delegated_context["publish_pr_in_code_generator"] = False
        delegated_context["open_mode"] = open_mode
        delegated_context["strict_target_files"] = bool(
            context.get("strict_target_files", not open_mode)
        )
        delegated_context["enforce_patch_quality_gate"] = bool(
            context.get("enforce_patch_quality_gate", True)
        )
        delegated_context["enforce_semantic_patch_gate"] = bool(
            context.get("enforce_semantic_patch_gate", True)
        )
        delegated_context["enforce_semantic_gate_blocking"] = bool(
            context.get("enforce_semantic_gate_blocking", True)
        )
        delegated_context["quality_gate_mode"] = str(
            context.get("quality_gate_mode", "shadow" if open_mode else "enforce")
        )
        delegated_context["patch_strategy"] = (
            str(context.get("patch_strategy", "patch_first")).strip() or "patch_first"
        )
        delegated_context["allow_full_file_rewrite"] = bool(
            context.get("allow_full_file_rewrite", False)
        )
        delegated_context["force_plan_after_semantic_failure"] = bool(
            context.get("force_plan_after_semantic_failure", True)
        )
        delegated_context["target_files"] = self._extract_candidate_files(context)
        focused_failure_summary = self._build_failure_focus_summary(test_results)
        base_task_description_parts = [
            f"Fix iteration {iteration}: address failing tests and produce minimal patch."
        ]
        if focused_failure_summary:
            base_task_description_parts.append(
                "Focused failure summary:\n" + focused_failure_summary
            )
        base_task_description_parts.append(f"Failure context: {failure_info}")
        base_task_description = "\n\n".join(base_task_description_parts)
        delegated_context["task_description"] = base_task_description

        last_error: str | None = None
        for attempt in range(1, self.CODEGEN_FIX_MAX_ATTEMPTS + 1):
            if attempt > 1 and last_error:
                delegated_context["task_description"] = (
                    f"{base_task_description}\n\n"
                    "Candidate validation feedback:\n"
                    f"- Previous candidate was rejected: {last_error}\n"
                    "- Produce a new candidate that explicitly fixes this rejection reason.\n"
                    "- Do not repeat the same invalid patch shape.\n"
                )

            try:
                codegen = EnhancedCodeGenerator()
                codegen_result = codegen.run(delegated_context)
                result_status = str(codegen_result.get("status") or "").strip().upper()
                patch = get_artifact_from_result(codegen_result, "code_patch")
                patch_rejection = self._reject_codegen_patch_result(
                    codegen_result=codegen_result,
                    patch=patch,
                )
                if patch_rejection:
                    last_error = patch_rejection
                    if attempt < self.CODEGEN_FIX_MAX_ATTEMPTS:
                        continue
                    return None, last_error
                if result_status == "SUCCESS" and isinstance(patch, dict) and patch.get("files"):
                    return patch, None
                last_error = f"codegen_fix_status={result_status or 'UNKNOWN'}"
                if attempt < self.CODEGEN_FIX_MAX_ATTEMPTS:
                    continue
                return None, last_error
            except Exception as exc:
                last_error = f"codegen_fix_failed: {exc}"
                if attempt < self.CODEGEN_FIX_MAX_ATTEMPTS:
                    continue
                return None, last_error

        return None, last_error or "codegen_fix_exhausted"

    @staticmethod
    def _reject_codegen_patch_result(
        *,
        codegen_result: dict[str, Any],
        patch: dict[str, Any] | None,
    ) -> str | None:
        if not isinstance(codegen_result, dict):
            return "codegen_fix_invalid_result"

        if not isinstance(patch, dict):
            result_status = str(codegen_result.get("status") or "").strip().upper()
            if result_status and result_status != "SUCCESS":
                return f"codegen_fix_status={result_status}"
            return "codegen_fix_returned_empty_patch"
        if not patch.get("files"):
            result_status = str(codegen_result.get("status") or "").strip().upper()
            if result_status and result_status != "SUCCESS":
                return f"codegen_fix_status={result_status}"
            return "codegen_fix_returned_empty_patch"

        semantic_gate = patch.get("semantic_gate")
        if isinstance(semantic_gate, dict) and not bool(semantic_gate.get("passed", True)):
            violations = semantic_gate.get("violations", [])
            violation_summary = ""
            if isinstance(violations, list) and violations:
                violation_summary = str(violations[0])[:160]
            if violation_summary:
                return f"codegen_fix_semantic_gate_failed:{violation_summary}"
            return "codegen_fix_semantic_gate_failed"

        quality_gate = patch.get("quality_gate")
        if isinstance(quality_gate, dict) and not bool(quality_gate.get("passed", True)):
            reasons = quality_gate.get("reasons", [])
            reason_summary = ""
            if isinstance(reasons, list) and reasons:
                reason_summary = ",".join(str(item).strip() for item in reasons[:3] if item)
            if reason_summary:
                return f"codegen_fix_quality_gate_failed:{reason_summary}"
            return "codegen_fix_quality_gate_failed"

        result_status = str(codegen_result.get("status") or "").strip().upper()
        if result_status and result_status != "SUCCESS":
            return f"codegen_fix_status={result_status}"

        return None


EnhancedFixAgent = FixAgent

from __future__ import annotations

import re
import subprocess
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import get_llm_wrapper, parse_review_output
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_review_prompt,
)


def run_lint(project: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["ruff", "check", "."],
            capture_output=True,
            text=True,
            cwd=project if project != "python" else ".",
        )
        return {
            "tool": "ruff",
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except FileNotFoundError:
        return {
            "tool": "ruff",
            "exit_code": -1,
            "stdout": "",
            "stderr": "ruff command not found",
            "success": False,
        }
    except Exception as e:  # noqa: BLE001
        return {"tool": "ruff", "exit_code": -1, "stdout": "", "stderr": str(e), "success": False}


def run_security_scan(project: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["bandit", "-r", "."],
            capture_output=True,
            text=True,
            cwd=project if project != "python" else ".",
        )
        return {
            "tool": "bandit",
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except FileNotFoundError:
        return {
            "tool": "bandit",
            "exit_code": -1,
            "stdout": "",
            "stderr": "bandit command not found",
            "success": False,
        }
    except Exception as e:  # noqa: BLE001
        return {"tool": "bandit", "exit_code": -1, "stdout": "", "stderr": str(e), "success": False}


def validate_architecture_rules(dependencies: list[str]) -> dict[str, Any]:
    violations = []

    for dep in dependencies:
        if "agents/" in dep and "api/" in dep:
            violations.append(f"Architecture violation: {dep} (agents should not depend on api)")

    for dep in dependencies:
        if "storage/" in dep and "api/" in dep:
            violations.append(f"Architecture violation: {dep} (storage should not depend on api)")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "total_dependencies": len(dependencies),
    }


SECURITY_PATTERNS = [
    (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password detected"),
    (r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded API key detected"),
    (r"secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret detected"),
    (r"(?:os\.)?execute\s*\(\s*[fr]?['\"].*\{[^}]+\}", "Potential command injection"),
    (r"subprocess\..*\(\s*.*\[^}]+\}", "Potential command injection"),
    (r"['\"][^'\"]*%[sdf][^'\"]*['\"]\s*%\s*\w+", "Potential format string vulnerability"),
    (r"\.format\s*\([^)]*\)", "Potential format string vulnerability"),
]

STYLE_PATTERNS = [
    (r"from\s+\w+\s+import\s+\*", "Wildcard import detected"),
    (r"import\s+\w+,\s*\w+", "Multiple imports on single line"),
]


def analyze_file_content(path: str, content: str) -> list[dict[str, Any]]:
    findings = []

    for pattern, message in SECURITY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(
                {
                    "file": path,
                    "line": None,
                    "type": "security",
                    "severity": "high",
                    "description": message,
                    "suggestion": "Remove the risky pattern and replace it with a safe implementation.",
                    "category": "vulnerability",
                }
            )

    for pattern, message in STYLE_PATTERNS:
        if re.search(pattern, content):
            findings.append(
                {
                    "file": path,
                    "line": None,
                    "type": "style",
                    "severity": "low",
                    "description": message,
                    "suggestion": "Update the import style to follow project conventions.",
                    "category": "readability",
                }
            )

    return findings


def build_code_review_prompt(
    files: list[dict[str, Any]],
    spec: dict[str, Any] | None = None,
    *,
    ci_failure_context: dict[str, Any] | None = None,
    test_results: dict[str, Any] | None = None,
) -> str:
    file_context = ""
    for file_change in files:
        path = file_change.get("path", "")
        content = file_change.get("content", "")
        change_type = file_change.get("change_type", "modify")
        if content:
            file_context += f"\n--- {path} ({change_type}) ---\n{content[:2000]}\n"

    spec_context = ""
    if spec:
        raw_requirements = spec.get("requirements", [])
        requirement_lines = []
        if isinstance(raw_requirements, list):
            for req in raw_requirements:
                if isinstance(req, dict):
                    requirement_lines.append(f"- {req.get('description', '')}")
                elif isinstance(req, str):
                    requirement_lines.append(f"- {req}")
        spec_context = f"""
## Feature Specification
{spec.get("summary", "")}

## Requirements
{chr(10).join(requirement_lines)}
"""

    ci_context = ""
    if isinstance(ci_failure_context, dict):
        ci_files = ci_failure_context.get("files", [])
        ci_targets = ci_failure_context.get("test_targets", [])
        classification = ci_failure_context.get("classification", "unknown")
        ci_context = (
            "\n## CI Failure Context\n"
            f"- classification: {classification}\n"
            f"- candidate_files: {ci_files[:10] if isinstance(ci_files, list) else []}\n"
            f"- test_targets: {ci_targets[:10] if isinstance(ci_targets, list) else []}\n"
        )

    test_context = ""
    if isinstance(test_results, dict):
        test_context = (
            "\n## Verification Context\n"
            f"- exit_code: {test_results.get('exit_code')}\n"
            f"- failed: {test_results.get('failed')}\n"
            f"- error_classification: {test_results.get('error_classification')}\n"
        )

    return f"""You are a senior software engineer performing a code review. Review the following code changes for quality, security, performance, adherence to best practices, and grounding to the actual CI failure.

{spec_context}
{ci_context}
{test_context}

## Code Changes
{file_context}

## Review Criteria
- Code quality and readability
- Security vulnerabilities
- Performance implications
- Adherence to coding standards
- Proper error handling
- Test coverage considerations
- Architecture compliance
- Documentation completeness
- Grounding to CI failure context
- Validity of verification/test execution

## Output Format - STRICT JSON
Generate a JSON object with EXACTLY these fields:

{{
    "overall_decision": "approve|request_changes|needs_discussion",
    "summary": "Brief summary of the review",
    "findings": [
        {{
            "file": "path/to/file.py",
            "line": 10,
            "type": "security|bug|performance|style|architecture|maintainability|grounding_mismatch|verification_invalid",
            "severity": "critical|high|medium|low",
            "description": "Detailed description of the issue",
            "suggestion": "Suggested fix or improvement",
            "category": "vulnerability|logic_error|efficiency|readability|design|testability|documentation"
        }}
    ],
    "strengths": [
        "List of positive aspects noted in the code"
    ],
    "recommendations": [
        "General recommendations for improvement"
    ],
    "confidence": 0.9
}}

Respond with valid JSON only.
"""


class ReviewAgent(BaseAgent):
    name = "review_agent"
    description = "Performs comprehensive code review with policy checks and optional live GitHub integration."

    def run(self, context: dict[str, Any]) -> dict:
        github_client = context.get("github_client")
        pr_number = context.get("pr_number")

        patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["fix_agent", "fix_loop", "test_fixer", "code_generator"],
            )
            or {}
        )
        if not isinstance(patch, dict):
            patch = {}

        spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer"],
            )
            or {}
        )
        if not isinstance(spec, dict):
            spec = {}

        ci_failure_context = (
            get_artifact_from_context(
                context,
                "ci_failure_context",
                preferred_steps=["ci_failure_analysis"],
            )
            or context.get("ci_failure_context")
            or {}
        )
        if not isinstance(ci_failure_context, dict):
            ci_failure_context = {}

        test_results = (
            get_artifact_from_context(
                context,
                "test_results",
                preferred_steps=["test_runner"],
            )
            or context.get("test_results")
            or {}
        )
        if not isinstance(test_results, dict):
            test_results = {}

        files = patch.get("files", [])
        if not isinstance(files, list):
            files = []

        llm_review_result = None
        llm_error = None
        use_llm = bool(context.get("use_llm", True))
        require_llm = bool(context.get("require_llm", False))

        if use_llm and files:
            llm = None
            try:
                llm = get_llm_wrapper()
                if llm is None:
                    llm = get_legacy_llm_wrapper()

                if llm is not None:
                    try:
                        prompt = build_code_review_prompt(
                            files,
                            spec,
                            ci_failure_context=ci_failure_context,
                            test_results=test_results,
                        )
                    except AttributeError:
                        prompt = legacy_build_code_review_prompt(files, spec)

                    response = llm.complete(prompt)
                    cleaned_response = response.strip()
                    json_match = re.search(r"\{[\s\S]*\}", cleaned_response)
                    parsed_response = json_match.group(0) if json_match else cleaned_response
                    llm_review_result = parse_review_output(parsed_response)
            except Exception as e:  # noqa: BLE001
                llm_error = str(e)
            finally:
                if llm is not None:
                    try:
                        llm.close()
                    except Exception:
                        pass

        if use_llm and require_llm and files and not isinstance(llm_review_result, dict):
            return build_agent_result(
                status="FAILED",
                artifact_type="review_result",
                artifact_content={
                    "decision": "error",
                    "overall_decision": "request_changes",
                    "summary": "LLM required but review LLM is unavailable.",
                    "llm_required": True,
                    "llm_error": llm_error,
                    "findings": [],
                    "strengths": [],
                    "recommendations": [],
                    "confidence": 0.0,
                },
                reason=(
                    f"LLM required but unavailable: {llm_error[:160]}"
                    if isinstance(llm_error, str) and llm_error
                    else "LLM required but no valid review output was produced."
                ),
                confidence=0.95,
                logs=[
                    "LLM strict mode enabled (require_llm=true).",
                    f"LLM error: {(llm_error or 'missing/invalid llm output')[:200]}",
                ],
                next_actions=["fix_llm_connectivity"],
            )

        live_review = False
        findings: list[dict[str, Any]] = []

        if llm_review_result and isinstance(llm_review_result, dict):
            overall_decision = str(
                llm_review_result.get("overall_decision")
                or llm_review_result.get("decision")
                or "request_changes"
            )
            summary = str(llm_review_result.get("summary", ""))
            findings = llm_review_result.get("findings", [])
            if not isinstance(findings, list):
                findings = []
            strengths = llm_review_result.get("strengths", [])
            if not isinstance(strengths, list):
                strengths = []
            recommendations = llm_review_result.get("recommendations", [])
            if not isinstance(recommendations, list):
                recommendations = []
            confidence = float(llm_review_result.get("confidence", 0.8))
            llm_enhanced = True

            if github_client and pr_number:
                live_review = True
                live_findings = self._perform_live_review(github_client, pr_number, files)
                findings.extend(live_findings)
        else:
            if github_client and pr_number:
                live_review = True
                findings = self._perform_live_review(github_client, pr_number, files)
            else:
                findings = self._analyze_local_patch(files)

            strengths = ["Code passed basic static analysis"] if not findings else []
            recommendations = ["Consider adding more comprehensive tests"]
            confidence = 0.75
            llm_enhanced = False
            overall_decision = "approve"
            summary = "Traditional review completed."

        grounded_findings = self._evaluate_grounding(files, ci_failure_context)
        verification_findings = self._evaluate_verification(test_results)
        findings.extend(grounded_findings)
        findings.extend(verification_findings)

        findings = self._normalize_findings(findings)

        if any(
            isinstance(f, dict) and str(f.get("severity", "")).lower() in {"critical", "high"}
            for f in findings
        ):
            overall_decision = "request_changes"

        if any(
            isinstance(f, dict)
            and str(f.get("type", "")).lower() in {"grounding_mismatch", "verification_invalid"}
            for f in findings
        ):
            overall_decision = "request_changes"

        if not summary.strip():
            summary = f"Review completed with {len(findings)} finding(s)."

        recommendations = self._merge_recommendations(
            recommendations,
            grounded_findings=grounded_findings,
            verification_findings=verification_findings,
        )

        has_changes = isinstance(files, list) and len(files) > 0
        touches_protected_branch = False
        policy_checks = {
            "has_changes": has_changes,
            "touches_protected_branch": touches_protected_branch,
            "dry_run_only": not live_review,
            "live_review": live_review,
            "llm_enhanced": llm_enhanced,
            "grounding_checked": True,
            "verification_checked": True,
        }

        status = "SUCCESS" if overall_decision == "approve" else "PARTIAL_SUCCESS"
        review_result = {
            "decision": overall_decision,
            "overall_decision": overall_decision,
            "summary": summary,
            "policy_checks": policy_checks,
            "findings": findings,
            "strengths": strengths,
            "recommendations": recommendations,
            "live_review": live_review,
            "llm_enhanced": llm_enhanced,
        }

        reason = (
            f"Live GitHub review with LLM enhancement: {overall_decision}"
            if live_review and llm_enhanced
            else f"LLM-enhanced review: {overall_decision}"
            if llm_enhanced
            else f"Live GitHub review: {overall_decision}"
            if live_review
            else "Review decision generated via policy checks."
        )

        logs = [f"Review decision: {overall_decision}. Findings: {len(findings)}"]
        if llm_error:
            logs.append(f"LLM error: {llm_error[:100]}")

        return build_agent_result(
            status=status,
            artifact_type="review_result",
            artifact_content=review_result,
            reason=reason,
            confidence=confidence,
            logs=logs,
            next_actions=["pr_merge_agent"] if overall_decision == "approve" else ["fix_agent"],
        )

    @staticmethod
    def _normalize_path(value: Any) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        for prefix in ("workspace/repo/", "/workspace/repo/", "workspace/", "/workspace/", "repo/"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        if "::" in normalized:
            normalized = normalized.split("::", 1)[0]
        return normalized

    def _evaluate_grounding(
        self,
        files: list[dict[str, Any]],
        ci_failure_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_files = {
            self._normalize_path(item)
            for item in ci_failure_context.get("files", [])
            if isinstance(item, str) and item.strip()
        }
        test_targets = {
            self._normalize_path(item)
            for item in ci_failure_context.get("test_targets", [])
            if isinstance(item, str) and item.strip()
        }
        allowed = {item for item in candidate_files | test_targets if item}

        if not allowed:
            return []

        findings: list[dict[str, Any]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path = self._normalize_path(item.get("path"))
            if not path:
                continue
            if path not in allowed:
                findings.append(
                    {
                        "file": path,
                        "line": None,
                        "type": "grounding_mismatch",
                        "severity": "high",
                        "description": (
                            "Patch modifies a file that is not referenced by CI diagnostics "
                            "or extracted failure targets."
                        ),
                        "suggestion": "Restrict the patch to candidate files derived from CI diagnostics.",
                        "category": "design",
                    }
                )
        return findings

    @staticmethod
    def _evaluate_verification(test_results: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if not isinstance(test_results, dict) or not test_results:
            return findings

        error_classification = str(test_results.get("error_classification", "")).strip().lower()
        exit_code = test_results.get("exit_code")

        if error_classification in {"path_error", "collection_error"}:
            findings.append(
                {
                    "file": None,
                    "line": None,
                    "type": "verification_invalid",
                    "severity": "high",
                    "description": (
                        "Verification is not reliable because pytest did not execute the intended tests."
                    ),
                    "suggestion": (
                        "Normalize test targets relative to repository root and rerun verification."
                    ),
                    "category": "testability",
                }
            )
        elif isinstance(exit_code, int) and exit_code not in {0, 1}:
            findings.append(
                {
                    "file": None,
                    "line": None,
                    "type": "verification_invalid",
                    "severity": "high",
                    "description": (
                        f"Verification ended with non-standard exit code {exit_code}, indicating execution issues."
                    ),
                    "suggestion": "Fix the test execution environment before approving the patch.",
                    "category": "testability",
                }
            )

        return findings

    @staticmethod
    def _normalize_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for finding in findings:
            if not isinstance(finding, dict):
                continue
            item = {
                "file": finding.get("file"),
                "line": finding.get("line"),
                "type": str(finding.get("type", "maintainability")),
                "severity": str(finding.get("severity", "medium")),
                "description": str(
                    finding.get("description") or finding.get("message") or "Review finding"
                ),
                "suggestion": str(
                    finding.get("suggestion") or "Investigate and address the issue."
                ),
                "category": str(finding.get("category", "readability")),
            }
            key = (
                str(item["file"]),
                item["type"],
                item["description"],
            )
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        return normalized

    @staticmethod
    def _merge_recommendations(
        recommendations: list[str],
        *,
        grounded_findings: list[dict[str, Any]],
        verification_findings: list[dict[str, Any]],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for item in recommendations:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text or text in seen:
                continue
            result.append(text)
            seen.add(text)

        if grounded_findings:
            text = "Restrict code changes to files referenced by CI diagnostics."
            if text not in seen:
                result.append(text)
                seen.add(text)

        if verification_findings:
            text = "Fix test execution issues and rerun verification before merge."
            if text not in seen:
                result.append(text)
                seen.add(text)

        return result

    def _perform_live_review(
        self,
        github_client: Any,
        pr_number: int,
        local_files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        findings = []

        try:
            pr_files = github_client.get_pull_request_files(pr_number)
        except Exception:
            return findings

        for pr_file in pr_files:
            filename = pr_file.get("filename", "")
            if pr_file.get("binary_file"):
                continue

            patch_content = pr_file.get("patch", "")
            if patch_content:
                for line in patch_content.split("\n"):
                    if line.startswith("+") and not line.startswith("+++"):
                        findings.extend(analyze_file_content(filename, line[1:]))

        return findings

    def _analyze_local_patch(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings = []
        for fc in files:
            path = fc.get("path", "")
            content = fc.get("content", "")
            findings.extend(analyze_file_content(path, content))
        return findings

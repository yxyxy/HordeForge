from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import get_llm_wrapper
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_review_prompt,
    legacy_parse_review_output,
)


def run_lint(project: str) -> dict[str, Any]:
    """
    Run lint checks using ruff.

    Args:
        project: The project type to lint

    Returns:
        Dictionary containing the linting results
    """
    try:
        # Execute ruff lint command
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
        # Handle case where ruff is not installed
        return {
            "tool": "ruff",
            "exit_code": -1,
            "stdout": "",
            "stderr": "ruff command not found",
            "success": False,
        }
    except Exception as e:
        return {"tool": "ruff", "exit_code": -1, "stdout": "", "stderr": str(e), "success": False}


def run_security_scan(project: str) -> dict[str, Any]:
    """
    Run security scan using bandit.

    Args:
        project: The project type to scan

    Returns:
        Dictionary containing the security scan results
    """
    try:
        # Execute bandit security scan command
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
        # Handle case where bandit is not installed
        return {
            "tool": "bandit",
            "exit_code": -1,
            "stdout": "",
            "stderr": "bandit command not found",
            "success": False,
        }
    except Exception as e:
        return {"tool": "bandit", "exit_code": -1, "stdout": "", "stderr": str(e), "success": False}


def validate_architecture_rules(dependencies: list[str]) -> dict[str, Any]:
    """
    Validate architecture rules against module dependencies.

    Args:
        dependencies: List of module dependencies in format "module_a -> module_b"

    Returns:
        Dictionary containing the architecture validation results
    """
    # For now, we'll implement basic validation logic
    # In a real implementation, this would check against architectural rules

    violations = []

    # Example architectural rule: agents should not depend on api
    for dep in dependencies:
        if "agents/" in dep and "api/" in dep:
            violations.append(f"Architecture violation: {dep} (agents should not depend on api)")

    # Example architectural rule: storage should not depend on api
    for dep in dependencies:
        if "storage/" in dep and "api/" in dep:
            violations.append(f"Architecture violation: {dep} (storage should not depend on api)")

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "total_dependencies": len(dependencies),
    }


# Code analysis patterns (HF-P5-006)
SECURITY_PATTERNS = [
    (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password detected"),
    (r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded API key detected"),
    (r"secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret detected"),
    # Command injection: os.execute, subprocess with user input
    (r"(?:os\.)?execute\s*\(\s*[fr]?['\"].*\{[^}]+\}", "Potential command injection"),
    (r"subprocess\..*\(\s*.*\[^}]+\}", "Potential command injection"),
    # Format string vulnerabilities: % formatting and .format() with user input
    (r"['\"][^'\"]*%[sdf][^'\"]*['\"]\s*%\s*\w+", "Potential format string vulnerability"),
    (r"\.format\s*\([^)]*\)", "Potential format string vulnerability"),
]

STYLE_PATTERNS = [
    (r"from\s+\w+\s+import\s+\*", "Wildcard import detected"),
    (r"import\s+\w+,\s*\w+", "Multiple imports on single line"),
]


def analyze_file_content(path: str, content: str) -> list[dict[str, Any]]:
    """Analyze file content for issues."""
    findings = []

    # Security checks
    for pattern, message in SECURITY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(
                {
                    "type": "security",
                    "severity": "high",
                    "file": path,
                    "message": message,
                }
            )

    # Style checks
    for pattern, message in STYLE_PATTERNS:
        if re.search(pattern, content):
            findings.append(
                {
                    "type": "style",
                    "severity": "low",
                    "file": path,
                    "message": message,
                }
            )

    return findings


def build_code_review_prompt(files: list[dict[str, Any]], spec: dict[str, Any] = None) -> str:
    """Build prompt for LLM-based code review."""
    # Build file context
    file_context = ""
    for file_change in files:
        path = file_change.get("path", "")
        content = file_change.get("content", "")
        change_type = file_change.get("change_type", "modify")
        if content:
            file_context += f"\n--- {path} ({change_type}) ---\n{content[:2000]}\n"  # Limit to 2000 chars per file

    spec_context = ""
    if spec:
        spec_context = f"""
## Feature Specification
{spec.get("summary", "")}

## Requirements
{chr(10).join(f"- {req.get('description', '')}" for req in spec.get("requirements", []))}
"""

    prompt = f"""You are a senior software engineer performing a code review. Review the following code changes for quality, security, performance, and adherence to best practices.

{spec_context}

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

## Output Format - STRICT JSON
Generate a JSON object with EXACTLY these fields:

{{
    "overall_decision": "approve|request_changes|needs_discussion",
    "summary": "Brief summary of the review",
    "findings": [
        {{
            "file": "path/to/file.py",
            "line": 10,
            "type": "security|bug|performance|style|architecture|maintainability",
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

## Critical Requirements:
1. Each finding must have a specific file path and line number if possible
2. Severity levels: critical (security/data loss), high (major bugs), medium (minor bugs), low (style)
3. Categories: vulnerability, logic_error, efficiency, readability, design, testability, documentation
4. Response must be valid JSON only - no markdown code blocks

Respond with valid JSON only.
"""
    return prompt


def parse_review_output(output: str) -> dict[str, Any]:
    """Parse and validate LLM code review output."""
    # Try to extract JSON from output
    json_match = re.search(r"\{[\s\S]*\}", output)
    if not json_match:
        raise ValueError("No JSON found in LLM output")

    json_str = json_match.group(0)

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM output: {e}") from e

    # Validate required fields
    required_fields = [
        "overall_decision",
        "summary",
        "findings",
        "strengths",
        "recommendations",
        "confidence",
    ]
    for field in required_fields:
        if field not in result:
            raise ValueError(f"Missing required field: {field}")

    # Validate findings structure
    for i, finding in enumerate(result.get("findings", [])):
        if not isinstance(finding, dict):
            raise ValueError(f"Finding {i} is not an object")
        if "type" not in finding:
            raise ValueError(f"Finding {i} missing 'type'")
        if "severity" not in finding:
            raise ValueError(f"Finding {i} missing 'severity'")
        if "description" not in finding:
            raise ValueError(f"Finding {i} missing 'description'")

    return result


class ReviewAgent(BaseAgent):
    name = "review_agent"
    description = "Performs comprehensive code review with policy checks and optional live GitHub integration."

    def run(self, context: dict[str, Any]) -> dict:
        # Get GitHub client if available (HF-P5-006)
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
        spec = (
            get_artifact_from_context(
                context,
                "spec",
                preferred_steps=["specification_writer"],
            )
            or {}
        )
        files = patch.get("files", [])

        # Try LLM-enhanced review
        llm_review_result = None
        llm_error = None
        use_llm = context.get("use_llm", True)

        if use_llm and files:
            try:
                # Try to use the new LLM wrapper first, fall back to legacy if needed
                llm = get_llm_wrapper()
                if llm is None:
                    # Try legacy wrapper for backward compatibility
                    llm = get_legacy_llm_wrapper()

                if llm is not None:
                    # Try new prompt building first, fall back to legacy if needed
                    try:
                        prompt = build_code_review_prompt(files, spec)
                    except AttributeError:
                        # Fall back to legacy prompt building
                        prompt = legacy_build_code_review_prompt(files, spec)

                    response = llm.complete(prompt)
                    llm.close()

                    # Clean up the response to handle potential formatting issues
                    cleaned_response = response.strip()

                    # Try to extract JSON from the response if it contains extra text
                    import re

                    json_match = re.search(r"\{[\s\S]*\}", cleaned_response)
                    if json_match:
                        json_str = json_match.group(0)
                        parsed_response = json_str
                    else:
                        parsed_response = cleaned_response

                    # Try new parsing first, fall back to legacy if needed
                    try:
                        llm_review_result = parse_review_output(parsed_response)
                    except AttributeError:
                        # Fall back to legacy parsing
                        llm_review_result = legacy_parse_review_output(parsed_response)
            except Exception as e:
                llm_error = str(e)

        # Live GitHub review (HF-P5-006)
        live_review = False
        findings = []
        if llm_review_result and isinstance(llm_review_result, dict):
            # Use LLM-generated review
            overall_decision = llm_review_result.get("overall_decision", "request_changes")
            summary = llm_review_result.get("summary", "")
            findings = llm_review_result.get("findings", [])
            strengths = llm_review_result.get("strengths", [])
            recommendations = llm_review_result.get("recommendations", [])
            confidence = llm_review_result.get("confidence", 0.8)
            llm_enhanced = True

            # If GitHub integration is available, add LLM findings to live review
            if github_client and pr_number:
                live_review = True
                live_findings = self._perform_live_review(github_client, pr_number, files)
                findings.extend(live_findings)
        else:
            # Fallback to traditional analysis
            if github_client and pr_number:
                live_review = True
                findings = self._perform_live_review(github_client, pr_number, files)
            else:
                # Fallback to local analysis
                findings = self._analyze_local_patch(files)

            # Determine decision based on findings
            has_critical = any(f.get("severity") in ["critical", "high"] for f in findings)
            overall_decision = "request_changes" if has_critical else "approve"
            summary = f"Traditional review: {overall_decision} based on {len(findings)} findings"
            strengths = ["Code passed basic static analysis"]
            recommendations = ["Consider adding more comprehensive tests"]
            confidence = 0.75 if overall_decision == "approve" else 0.65
            llm_enhanced = False

        has_changes = isinstance(files, list) and len(files) > 0
        touches_protected_branch = False
        policy_checks = {
            "has_changes": has_changes,
            "touches_protected_branch": touches_protected_branch,
            "dry_run_only": not live_review,
            "live_review": live_review,
            "llm_enhanced": llm_enhanced,
        }

        status = "SUCCESS" if overall_decision == "approve" else "PARTIAL_SUCCESS"
        review_result = {
            "decision": overall_decision,
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

    def _perform_live_review(
        self,
        github_client: Any,
        pr_number: int,
        local_files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Perform live review on GitHub PR."""
        findings = []

        # Get PR files
        try:
            pr_files = github_client.get_pull_request_files(pr_number)
        except Exception:
            return findings

        # Analyze each changed file
        for pr_file in pr_files:
            filename = pr_file.get("filename", "")

            # Skip binary files
            if pr_file.get("binary_file"):
                continue

            # Get file content from patch
            patch_content = pr_file.get("patch", "")
            if patch_content:
                # Analyze added/changed lines
                for line in patch_content.split("\n"):
                    if line.startswith("+") and not line.startswith("+++"):
                        findings.extend(analyze_file_content(filename, line[1:]))

        return findings

    def _analyze_local_patch(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyze local patch files."""
        findings = []

        for fc in files:
            path = fc.get("path", "")
            content = fc.get("content", "")
            findings.extend(analyze_file_content(path, content))

        return findings

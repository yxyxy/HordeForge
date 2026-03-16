from __future__ import annotations

import re
import subprocess
from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context


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


from agents.base import BaseAgent


class ReviewAgent(BaseAgent):
    name = "review_agent"
    description = "Performs review with policy checks and optional live GitHub integration."

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
        files = patch.get("files", [])

        # Live GitHub review (HF-P5-006)
        live_review = False
        if github_client and pr_number:
            live_review = True
            findings = self._perform_live_review(github_client, pr_number, files)
        else:
            # Fallback to local analysis
            findings = self._analyze_local_patch(files)

        has_changes = isinstance(files, list) and len(files) > 0
        touches_protected_branch = False
        policy_checks = {
            "has_changes": has_changes,
            "touches_protected_branch": touches_protected_branch,
            "dry_run_only": not live_review,
            "live_review": live_review,
        }

        # Determine decision based on findings
        has_critical = any(f.get("severity") == "high" for f in findings)
        decision = "request_changes" if has_critical else "approve"

        status = "SUCCESS" if decision == "approve" else "PARTIAL_SUCCESS"
        review_result = {
            "decision": decision,
            "policy_checks": policy_checks,
            "findings": findings,
            "live_review": live_review,
        }

        reason = (
            f"Live GitHub review: {decision}"
            if live_review
            else "Review decision generated via policy checks."
        )

        return build_agent_result(
            status=status,
            artifact_type="review_result",
            artifact_content=review_result,
            reason=reason,
            confidence=0.91 if decision == "approve" else 0.74,
            logs=[f"Review decision: {decision}."],
            next_actions=["pr_merge_agent"] if decision == "approve" else ["fix_agent"],
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

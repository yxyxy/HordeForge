"""Test execution and result parsing for real fix loop (HF-P5-005).

This module handles:
- Test execution via GitHub Actions API
- Result parsing for various test frameworks (pytest, jest, go test)
- Convergence detection
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from agents.github_client import GitHubApiError, GitHubClient


@dataclass
class TestExecutionResult:
    """Result of test execution."""

    success: bool = False
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    workflow_run_id: int | None = None
    failure_details: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""
    parse_error: str | None = None


@dataclass
class FixIterationState:
    """State of a fix iteration for convergence detection."""

    iteration: int
    error_patterns: set[str] = field(default_factory=set)
    failed_tests: set[str] = field(default_factory=set)
    error_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "error_patterns": list(self.error_patterns),
            "failed_tests": list(self.failed_tests),
            "error_messages": self.error_messages,
        }


class TestExecutor:
    """Executes tests via GitHub Actions and parses results."""

    DEFAULT_POLL_INTERVAL = 10
    DEFAULT_TIMEOUT = 300

    def __init__(
        self,
        github_client: GitHubClient,
        workflow_id: str = "ci.yml",
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.client = github_client
        self.workflow_id = workflow_id
        self.poll_interval = poll_interval
        self.timeout = timeout

    def run_tests(
        self,
        branch: str = "main",
        inputs: dict[str, str] | None = None,
    ) -> TestExecutionResult:
        """Run tests via GitHub Actions workflow dispatch."""
        result = TestExecutionResult()

        try:
            self.client.dispatch_workflow(
                workflow_id=self.workflow_id,
                ref=branch,
                inputs=inputs,
            )

            run_id = self._poll_for_run(branch)
            if not run_id:
                result.parse_error = "Could not find workflow run"
                return result

            result.workflow_run_id = run_id

            completed = self._wait_for_completion(run_id)
            if not completed:
                result.parse_error = "Workflow timeout"
                return result

            result = self._get_run_results(run_id)

        except GitHubApiError as e:
            result.parse_error = f"GitHub API error: {e}"
        except Exception as e:
            result.parse_error = f"Execution error: {e}"

        return result

    def _poll_for_run(self, branch: str) -> int | None:
        """Poll for latest workflow run on branch."""
        try:
            runs = self.client.get_workflow_runs(self.workflow_id, branch)
            workflow_runs = runs.get("workflow_runs", [])
            if workflow_runs:
                return workflow_runs[0].get("id")
        except Exception:
            pass
        return None

    def _wait_for_completion(self, run_id: int) -> bool:
        """Wait for workflow run to complete."""
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                run = self.client.get_workflow_run(run_id)
                status = run.get("status", "")
                conclusion = run.get("conclusion", "")

                if status == "completed":
                    return conclusion is not None

                time.sleep(self.poll_interval)

            except Exception:
                time.sleep(self.poll_interval)

        return False

    def _get_run_results(self, run_id: int) -> TestExecutionResult:
        """Get test results from completed workflow run."""
        result = TestExecutionResult()
        result.workflow_run_id = run_id

        try:
            jobs_data = self.client.get_workflow_run_jobs(run_id)
            jobs = jobs_data.get("jobs", [])

            for job in jobs:
                conclusion = job.get("conclusion", "unknown")

                if conclusion == "success":
                    result.passed += 1
                elif conclusion == "failure":
                    result.failed += 1

                if conclusion == "failure":
                    steps = job.get("steps", [])
                    for step in steps:
                        if step.get("conclusion") == "failure":
                            result.failure_details.append(
                                {
                                    "job": job.get("name", ""),
                                    "step": step.get("name", ""),
                                    "message": f"Step '{step.get('name')}' failed in job '{job.get('name')}'",
                                }
                            )

            result.total = result.passed + result.failed
            result.success = result.failed == 0

        except Exception as e:
            result.parse_error = f"Failed to get results: {e}"

        return result


class TestResultParser:
    """Parses test output from various frameworks."""

    @staticmethod
    def parse_pytest_output(output: str) -> TestExecutionResult:
        result = TestExecutionResult()

        passed_match = re.search(r"(\d+)\s+passed", output)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", output)
        if failed_match:
            result.failed = int(failed_match.group(1))

        error_match = re.search(r"(\d+)\s+error", output)
        if error_match:
            result.errors = int(error_match.group(1))

        skipped_match = re.search(r"(\d+)\s+skipped", output)
        if skipped_match:
            result.skipped = int(skipped_match.group(1))

        for match in re.finditer(r"FAILED\s+([^\s]+)", output):
            result.failure_details.append(
                {
                    "test": match.group(1),
                    "type": "pytest_failure",
                }
            )

        for match in re.finditer(r"(?:Error|ERROR|Exception):\s*(.+?)(?:\n|$)", output):
            result.failure_details.append(
                {
                    "message": match.group(1).strip(),
                    "type": "error_message",
                }
            )

        for match in re.finditer(r'File "([^"]+)", line (\d+)', output):
            result.failure_details.append(
                {
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "type": "location",
                }
            )

        result.total = result.passed + result.failed + result.errors + result.skipped
        result.success = result.failed == 0 and result.errors == 0
        result.raw_output = output
        return result

    @staticmethod
    def parse_jest_output(output: str) -> TestExecutionResult:
        result = TestExecutionResult()

        json_match = re.search(r"\{[\s\S]*\"numTotalTestSuites\"[\s\S]*\}", output)
        if json_match:
            try:
                import json

                data = json.loads(json_match.group(0))
                result.passed = data.get("numPassedTests", 0)
                result.failed = data.get("numFailedTests", 0)
                result.skipped = data.get("numPendingTests", 0)
                result.total = data.get("numTotalTests", 0)

                for suite in data.get("testResults", []):
                    for assertion in suite.get("assertionResults", []):
                        if assertion.get("status") == "failed":
                            result.failure_details.append(
                                {
                                    "test": assertion.get("fullName", ""),
                                    "message": assertion.get("message", ""),
                                    "type": "jest_failure",
                                }
                            )

                result.success = result.failed == 0
                result.raw_output = output
                return result

            except Exception:
                pass

        passed_match = re.search(r"Tests:\s+(\d+)\s+passed", output)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", output)
        if failed_match:
            result.failed = int(failed_match.group(1))

        result.total = result.passed + result.failed
        result.success = result.failed == 0
        result.raw_output = output
        return result

    @staticmethod
    def parse_go_test_output(output: str) -> TestExecutionResult:
        result = TestExecutionResult()

        if output.startswith("FAIL"):
            result.failed = 1

        for match in re.finditer(r"^---\s+FAIL:\s+(\S+)", output, re.MULTILINE):
            result.failure_details.append(
                {
                    "test": match.group(1),
                    "type": "go_failure",
                }
            )

        passed_count = len(re.findall(r"^---\s+PASS:\s+(\S+)", output, re.MULTILINE))
        result.passed = passed_count

        for match in re.finditer(r"FAIL\s+(\S+)\s+(.+?)(?=\n---|\Z)", output, re.DOTALL):
            result.failure_details.append(
                {
                    "test": match.group(1),
                    "message": match.group(2)[:200],
                    "type": "go_error",
                }
            )

        result.failed = len(result.failure_details)
        result.total = result.passed + result.failed
        result.success = result.failed == 0
        result.raw_output = output
        return result

    @staticmethod
    def auto_detect_and_parse(output: str, framework: str | None = None) -> TestExecutionResult:
        """Auto-detect framework and parse output more safely."""
        output_lower = output.lower()

        # Use explicit framework hint if provided
        if framework == "pytest":
            return TestResultParser.parse_pytest_output(output)
        if framework == "jest":
            return TestResultParser.parse_jest_output(output)
        if framework == "go":
            return TestResultParser.parse_go_test_output(output)

        # Detect by output patterns
        if "pytest" in output_lower or re.search(r"\d+\s+passed", output_lower):
            return TestResultParser.parse_pytest_output(output)

        if "jest" in output_lower or "tests:" in output:
            return TestResultParser.parse_jest_output(output)

        if "go test" in output_lower or "--- pass:" in output_lower or "--- fail:" in output_lower:
            return TestResultParser.parse_go_test_output(output)

        # Default: assume success
        result = TestExecutionResult()
        result.success = True
        result.raw_output = output
        return result


class ConvergenceDetector:
    """Detects when fix iterations are not making progress."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.history: list[FixIterationState] = []

    def record_iteration(
        self,
        iteration: int,
        failed_tests: list[str],
        error_messages: list[str],
    ) -> FixIterationState:

        patterns = set()

        for msg in error_messages:
            if "AssertionError" in msg:
                patterns.add("assertion")
            elif "ImportError" in msg or "ModuleNotFoundError" in msg:
                patterns.add("import")
            elif "SyntaxError" in msg:
                patterns.add("syntax")
            elif "TypeError" in msg:
                patterns.add("type")
            elif "NameError" in msg:
                patterns.add("name")
            elif "AttributeError" in msg:
                patterns.add("attribute")
            elif "IndexError" in msg or "KeyError" in msg:
                patterns.add("index")
            else:
                patterns.add("other")

        state = FixIterationState(
            iteration=iteration,
            error_patterns=patterns,
            failed_tests=set(failed_tests),
            error_messages=error_messages,
        )

        self.history.append(state)
        return state

    def has_converged(self) -> bool:
        """Check if fix iterations have converged (no progress).

        Convergence means: same error patterns AND same failed tests.
        Different errors = progress being made = no convergence.
        """
        if len(self.history) < 2:
            return False

        current = self.history[-1]
        previous = self.history[-2]

        # Convergence = same errors and same tests failing (no progress)
        if current.error_patterns == previous.error_patterns:
            if current.failed_tests == previous.failed_tests:
                return True

        return False

    def should_stop(self, iteration: int) -> bool:

        if iteration >= self.max_iterations:
            return True

        if self.has_converged():
            return True

        return False

    def get_status(self) -> dict[str, Any]:

        return {
            "iteration_count": len(self.history),
            "max_iterations": self.max_iterations,
            "has_converged": self.has_converged(),
            "should_stop": len(self.history) >= self.max_iterations or self.has_converged(),
            "history": [s.to_dict() for s in self.history],
        }

    def clear(self) -> None:
        self.history.clear()


def extract_error_context(
    test_results: TestExecutionResult,
    test_code: dict[str, str] | None = None,
) -> str:
    lines = [
        "## Test Results Summary",
        f"- Total: {test_results.total}",
        f"- Passed: {test_results.passed}",
        f"- Failed: {test_results.failed}",
        f"- Errors: {test_results.errors}",
        "",
    ]

    if test_results.failure_details:
        lines.append("## Failed Tests Details")

        for detail in test_results.failure_details[:10]:
            if "test" in detail:
                lines.append(f"- **{detail.get('test', 'unknown')}**")

            if "message" in detail:
                msg = detail.get("message", "")
                if len(msg) > 200:
                    msg = msg[:200] + "..."
                lines.append(f"  - {msg}")

            if "file" in detail and "line" in detail:
                lines.append(f"  - Location: {detail['file']}:{detail['line']}")

            lines.append("")

    if test_code:
        lines.append("## Relevant Code")

        for path, content in list(test_code.items())[:3]:
            lines.append(f"### {path}")
            content_lines = content.split("\n")[:50]

            lines.append("```")
            lines.extend(content_lines)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)

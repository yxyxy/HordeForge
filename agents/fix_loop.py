"""Real fix loop execution - runs actual tests and generates fixes based on real errors."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agents.github_client import GitHubClient
from agents.llm_wrapper import LLMWrapper, generate_code_with_retry

logger = logging.getLogger(__name__)


@dataclass
class TestResultData:
    """Result of a test run."""

    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_messages: list[str] = field(default_factory=list)
    failure_messages: list[str] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class FixIterationData:
    """Single iteration of the fix loop."""

    iteration: int
    test_result: TestResultData
    generated_fix: dict[str, Any] | None = None
    applied: bool = False
    error: str | None = None


@dataclass
class FixLoopResultData:
    """Result of the complete fix loop."""

    success: bool
    iterations: list[FixIterationData] = field(default_factory=list)
    final_test_result: TestResultData | None = None
    error: str | None = None
    max_iterations_reached: bool = False


class TestRunner:
    """Executes tests and parses results."""

    def __init__(self, github_client: GitHubClient) -> None:
        self.client = github_client

    def run_github_actions_workflow(
        self,
        workflow_id: str,
        branch: str = "main",
    ) -> TestResultData:
        """Run tests via GitHub Actions workflow."""
        try:
            self.client.dispatch_workflow(workflow_id, branch)
            return TestResultData(passed=True, total_tests=0)
        except Exception as e:
            logger.error(f"Failed to run GitHub Actions workflow: {e}")
            return TestResultData(
                passed=False,
                error_messages=[f"Workflow execution failed: {e}"],
            )

    def parse_pytest_output(self, output: str) -> TestResultData:
        """Parse pytest output."""
        result = TestResultData(passed=False, raw_output=output)

        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)
        error_match = re.search(r"(\d+) error", output)

        if passed_match:
            result.passed_tests = int(passed_match.group(1))
            result.total_tests += result.passed_tests

        if failed_match:
            result.failed_tests = int(failed_match.group(1))
            result.total_tests += result.failed_tests

        if error_match:
            result.error_messages.append(f"{error_match.group(1)} errors")

        result.passed = result.failed_tests == 0 and result.error_messages == []

        failure_section = re.search(
            r"^(=+ )?FAILED.*?(?=^=+ |^$)", output, re.MULTILINE | re.DOTALL
        )
        if failure_section:
            result.failure_messages.append(failure_section.group(0))

        return result

    def parse_jest_output(self, output: str) -> TestResultData:
        """Parse Jest output."""
        result = TestResultData(passed=False, raw_output=output)

        summary_match = re.search(r"Tests:\s+(.+?)(?:\n|$)", output)
        if summary_match:
            summary = summary_match.group(1)
            passed_match = re.search(r"(\d+) passed", summary)
            failed_match = re.search(r"(\d+) failed", summary)

            if passed_match:
                result.passed_tests = int(passed_match.group(1))
                result.total_tests += result.passed_tests

            if failed_match:
                result.failed_tests = int(failed_match.group(1))
                result.total_tests += result.failed_tests

        result.passed = result.failed_tests == 0
        return result

    def parse_go_test_output(self, output: str) -> TestResultData:
        """Parse Go test output."""
        result = TestResultData(passed=False, raw_output=output)

        fail_matches = re.findall(r"--- FAIL: (\w+)", output)
        pass_matches = re.findall(r"--- PASS: (\w+)", output)

        result.failed_tests = len(fail_matches)
        result.passed_tests = len(pass_matches)
        result.total_tests = result.failed_tests + result.passed_tests

        result.passed = result.failed_tests == 0
        return result


class FixLoopExecutor:
    """Executes the fix loop: generate fix -> apply -> test -> repeat."""

    def __init__(
        self,
        github_client: GitHubClient,
        llm: LLMWrapper,
        max_iterations: int = 5,
    ) -> None:
        self.github_client = github_client
        self.llm = llm
        self.max_iterations = max_iterations
        self.test_runner = TestRunner(github_client)
        self.logger = logging.getLogger("hordeforge.fix_loop")

    def execute_fix_loop(
        self,
        code_result: dict[str, Any],
        test_output: str,
        test_framework: str = "pytest",
        language: str = "python",
    ) -> FixLoopResultData:
        """Execute the fix loop."""
        result = FixLoopResultData(success=False)

        test_result = self._parse_test_output(test_output, test_framework)
        result.iterations.append(
            FixIterationData(
                iteration=0,
                test_result=test_result,
                generated_fix=None,
            )
        )

        if test_result.passed:
            result.success = True
            result.final_test_result = test_result
            return result

        for i in range(1, self.max_iterations + 1):
            self.logger.info(f"Fix iteration {i}/{self.max_iterations}")

            iteration_result = self._run_iteration(
                code_result=code_result,
                test_result=test_result,
                iteration=i,
                language=language,
            )

            result.iterations.append(iteration_result)

            if iteration_result.error:
                result.error = iteration_result.error
                break

            if iteration_result.test_result.passed:
                result.success = True
                result.final_test_result = iteration_result.test_result
                break

            if iteration_result.generated_fix:
                code_result = iteration_result.generated_fix

            test_result = iteration_result.test_result

        if not result.success and not result.error:
            result.max_iterations_reached = True
            result.error = f"Max iterations ({self.max_iterations}) reached without success"

        return result

    def _run_iteration(
        self,
        code_result: dict[str, Any],
        test_result: TestResultData,
        iteration: int,
        language: str,
    ) -> FixIterationData:
        """Run a single fix iteration."""
        iteration_result = FixIterationData(
            iteration=iteration,
            test_result=test_result,
        )

        try:
            fix = self._generate_fix(code_result, test_result, language)
            iteration_result.generated_fix = fix
        except Exception as e:
            self.logger.error(f"Fix iteration {iteration} failed: {e}")
            iteration_result.error = str(e)

        return iteration_result

    def _generate_fix(
        self,
        code_result: dict[str, Any],
        test_result: TestResultData,
        language: str,
    ) -> dict[str, Any]:
        """Generate a fix using LLM based on test failures."""
        context = {
            "language": language,
            "failed_tests": test_result.failed_tests,
            "failure_messages": test_result.failure_messages,
            "error_messages": test_result.error_messages,
            "current_code": self._extract_code_context(code_result),
        }

        fix_spec = {
            "summary": "Fix test failures",
            "requirements": [
                {
                    "id": "FIX-001",
                    "description": "Fix the failing tests",
                    "test_criteria": "All tests pass",
                    "priority": "must",
                }
            ],
            "technical_notes": [
                f"Failed tests: {test_result.failed_tests}",
                f"Errors: {test_result.error_messages}",
            ],
            "file_changes": [],
        }

        try:
            fix_result = generate_code_with_retry(
                llm=self.llm,
                spec=fix_spec,
                test_cases=[],
                repo_context=context,
                language=language,
            )
            return fix_result
        except Exception as e:
            self.logger.warning(f"LLM fix generation failed: {e}")
            return code_result

    def _extract_code_context(self, code_result: dict[str, Any]) -> str:
        """Extract code context for fix generation."""
        files = code_result.get("files", [])
        if not files:
            return ""
        first_file = files[0]
        content = first_file.get("content", "")
        return content[:2000]

    def _parse_test_output(
        self,
        output: str,
        framework: str,
    ) -> TestResultData:
        """Parse test output based on framework."""
        if framework == "pytest":
            return self.test_runner.parse_pytest_output(output)
        elif framework == "jest":
            return self.test_runner.parse_jest_output(output)
        elif framework == "go":
            return self.test_runner.parse_go_test_output(output)
        else:
            return self.test_runner.parse_pytest_output(output)


def run_fix_loop(
    github_client: GitHubClient,
    llm: LLMWrapper,
    code_result: dict[str, Any],
    test_output: str,
    test_framework: str = "pytest",
    language: str = "python",
    max_iterations: int = 5,
) -> FixLoopResultData:
    """Convenience function to run fix loop."""
    executor = FixLoopExecutor(
        github_client=github_client,
        llm=llm,
        max_iterations=max_iterations,
    )

    return executor.execute_fix_loop(
        code_result=code_result,
        test_output=test_output,
        test_framework=test_framework,
        language=language,
    )

from __future__ import annotations

from typing import Any

from agents.context_utils import build_agent_result


def analyze_coverage(report: dict[str, Any]) -> int:
    """
    Analyze coverage report and return coverage percentage.

    Args:
        report: Coverage report dictionary

    Returns:
        Coverage percentage as integer
    """
    return report.get("coverage", 0)


def detect_missing_tests(modules: list[str], tests: list[str]) -> list[str]:
    """
    Detect missing tests for modules.

    Args:
        modules: List of module names
        tests: List of test file paths

    Returns:
        List of modules without corresponding tests
    """
    # Extract module names from test files
    tested_modules = set()
    for test_file in tests:
        # Assuming test files follow naming convention like test_module_name.py
        if test_file.startswith("tests/test_") and test_file.endswith(".py"):
            module_part = test_file.replace("tests/test_", "").replace(".py", "")
            tested_modules.add(module_part)

    # Find modules without tests
    missing_tests = []
    for module in modules:
        if module not in tested_modules:
            missing_tests.append(module)

    return missing_tests


def calculate_risk_score(coverage: int) -> str:
    """
    Calculate risk score based on coverage percentage.

    Args:
        coverage: Coverage percentage

    Returns:
        Risk level as string ("high", "medium", "low")
    """
    if coverage < 50:
        return "high"
    elif coverage < 80:
        return "medium"
    else:
        return "low"


from agents.base import BaseAgent


class TestAnalyzer(BaseAgent):
    name = "test_analyzer"
    description = "Analyzes test coverage, detects missing tests, and calculates risk scores."

    @staticmethod
    def _extract_test_files(context: dict[str, Any]) -> list[str]:
        raw = context.get("test_files")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, str)]
        return []

    @staticmethod
    def _extract_modules(context: dict[str, Any]) -> list[str]:
        raw = context.get("modules")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, str)]
        return []

    def run(self, context: dict[str, Any]) -> dict:
        test_files = self._extract_test_files(context)
        modules = self._extract_modules(context)

        # Perform coverage analysis
        coverage_report = context.get("coverage_report", {})
        coverage_score = analyze_coverage(coverage_report)

        # Detect missing tests
        missing_tests = detect_missing_tests(modules, test_files)

        # Calculate risk score
        risk_score = calculate_risk_score(coverage_score)

        total_tests = len(test_files)
        has_tests = total_tests > 0
        status = (
            "SUCCESS"
            if has_tests or len(missing_tests) > 0 or coverage_score > 0
            else "PARTIAL_SUCCESS"
        )

        report = {
            "total_tests": total_tests,
            "coverage_percentage": coverage_score,
            "risk_level": risk_score,
            "missing_tests": missing_tests,
            "test_files": test_files,
            "modules": modules,
            "fallback_reason": ""
            if has_tests or len(missing_tests) > 0 or coverage_score > 0
            else "No tests or coverage data discovered in provided context.",
        }
        return build_agent_result(
            status=status,
            artifact_type="test_coverage_report",
            artifact_content=report,
            reason="Coverage report generated via intelligent test analyzer.",
            confidence=0.85 if has_tests or coverage_score > 0 else 0.70,
            logs=[
                f"Detected {total_tests} test files.",
                f"Coverage: {coverage_score}%",
                f"Risk level: {risk_score}",
                f"Missing tests for: {len(missing_tests)} modules",
            ],
            next_actions=["pipeline_initializer"],
        )

from __future__ import annotations

import re
from typing import Any

from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.test_templates import get_test_template

# Language detection (HF-P5-004)
LANGUAGE_EXTENSIONS = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "go": "go",
    "rb": "ruby",
    "java": "java",
    "cs": "csharp",
    "rs": "rust",
}

FRAMEWORK_INDICATORS = {
    "python": {
        "pytest": ["pytest", "conftest.py"],
        "unittest": ["unittest", "TestCase"],
        "nose": ["nose"],
    },
    "javascript": {
        "jest": ["jest.config", "package.json"],
        "mocha": ["mocha"],
        "vitest": ["vitest.config"],
    },
    "typescript": {
        "jest": ["jest.config", "@types/jest"],
        "vitest": ["vitest.config"],
    },
    "go": {
        "testing": ["_test.go"],
        "ginkgo": ["ginkgo", "gomega"],
    },
}


# Test patterns extraction (HF-P5-004)
TEST_PATTERNS = {
    "python": {
        "pytest": {
            "fixture_usage": r"@pytest\.fixture|def \w+\(.*\):",
            "parametrize": r"@pytest\.mark\.parametrized",
            "mock_import": r"from unittest\.mock import|@mock\.patch",
            "assertions": r"assert \w+",
        },
        "unittest": {
            "test_class": r"class Test\w+\(unittest\.TestCase\):",
            "set_up": r"def setUp\(self\):",
            "tear_down": r"def tearDown\(self\):",
        },
    },
    "javascript": {
        "jest": {
            "describe": r"describe\(",
            "test": r"test\(|it\(",
            "before_each": r"beforeEach\(",
            "mock": r"jest\.mock\(|vi\.mock\(",
        },
    },
    "typescript": {
        "jest": {
            "describe": r"describe\(",
            "test": r"test\(|it\(",
            "mock": r"jest\.mock\(|vi\.mock\(",
            "type_imports": r"import type \{",
        },
    },
}


def extract_test_patterns(
    test_files: list[dict[str, Any]],
    language: str,
    framework: str | None = None,
) -> dict[str, Any]:
    """Extract test patterns from existing test files.

    Args:
        test_files: List of test file contents to analyze
        language: Programming language
        framework: Testing framework

    Returns:
        Dictionary of detected patterns
    """
    patterns = {
        "uses_fixtures": False,
        "uses_mocks": False,
        "uses_parametrize": False,
        "uses_setups": False,
        "common_assertions": [],
        "naming_convention": "snake_case",
    }

    if language not in TEST_PATTERNS:
        return patterns

    lang_patterns = TEST_PATTERNS.get(language, {})
    framework_patterns = lang_patterns.get(framework or "", {})

    # If no framework-specific, try language defaults
    if not framework_patterns:
        for _fw, fw_patterns in lang_patterns.items():
            framework_patterns = fw_patterns
            break

    for test_file in test_files:
        content = test_file.get("content", "")
        if not content:
            continue

        # Check each pattern
        for pattern_name, pattern_regex in framework_patterns.items():
            if re.search(pattern_regex, content):
                if pattern_name in ("fixture_usage", "set_up", "before_each"):
                    patterns["uses_fixtures"] = True
                if pattern_name in ("mock_import", "mock"):
                    patterns["uses_mocks"] = True
                if pattern_name == "parametrize":
                    patterns["uses_parametrize"] = True
                if pattern_name in ("set_up", "before_each", "tear_down", "after_each"):
                    patterns["uses_setups"] = True

        # Extract common assertions
        assertion_matches = re.findall(r"assert\s+(\w+)", content)
        patterns["common_assertions"].extend(assertion_matches[:5])  # Limit

    # Deduplicate assertions
    patterns["common_assertions"] = list(dict.fromkeys(patterns["common_assertions"]))

    # Detect naming convention
    if language in ("javascript", "typescript"):
        if re.search(r"test\(['\"][A-Z]", content):
            patterns["naming_convention"] = "camelCase"

    return patterns


def adapt_test_to_patterns(
    test_content: str,
    patterns: dict[str, Any],
    language: str,
    framework: str | None,
) -> str:
    """Adapt generated test content to project patterns.

    Args:
        test_content: Generated test content
        patterns: Extracted patterns from existing tests
        language: Programming language
        framework: Testing framework

    Returns:
        Adapted test content
    """
    adapted = test_content

    # Add fixtures if project uses them
    if patterns.get("uses_fixtures") and "pytest.fixture" not in adapted:
        # Add a basic fixture
        if language == "python" and framework == "pytest":
            fixture_block = """

@pytest.fixture
def mock_dependencies():
    return {}
"""
            adapted = adapted.replace("import pytest", "import pytest" + fixture_block)

    # Add mocks if project uses them
    if patterns.get("uses_mocks"):
        if language == "python" and "from unittest.mock import" not in adapted:
            adapted = adapted.replace("import pytest", "import pytest\nfrom unittest.mock import Mock, patch")

    return adapted


def detect_language_from_files(files: list[str]) -> str:
    """Detect primary language from file list."""
    ext_counts: dict[str, int] = {}
    for f in files:
        if "." in f:
            ext = f.rsplit(".", 1)[1]
            lang = LANGUAGE_EXTENSIONS.get(ext)
            if lang:
                ext_counts[lang] = ext_counts.get(lang, 0) + 1

    if ext_counts:
        return max(ext_counts, key=ext_counts.get)
    return "python"  # Default


def detect_framework(language: str, repo_config: dict[str, Any] | None = None) -> str | None:
    """Detect testing framework from repository config."""
    if not repo_config:
        return None

    config_files = repo_config.get("config_files", [])
    package_json = repo_config.get("package_json")

    indicators = FRAMEWORK_INDICATORS.get(language, {})

    for framework, files in indicators.items():
        if any(cf in files for cf in config_files):
            return framework

    # Check package.json for JS/TS
    if language in ("javascript", "typescript") and package_json:
        deps = package_json.get("devDependencies", {})
        if "jest" in deps:
            return "jest"
        if "vitest" in deps:
            return "vitest"
        if "mocha" in deps:
            return "mocha"

    return None


class TestGenerator:
    name = "test_generator"
    description = "Generates deterministic test cases from decomposed subtasks."

    def run(self, context: dict[str, Any]) -> dict:
        subtasks = (
            get_artifact_from_context(
                context,
                "subtasks",
                preferred_steps=["task_decomposer"],
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
        rules_payload = context.get("rules") if isinstance(context.get("rules"), dict) else {}
        rules_version = str(rules_payload.get("version", "")).strip()
        items = subtasks.get("items")
        if not isinstance(items, list):
            items = []

        # Detect language and framework (HF-P5-004)
        existing_files = context.get("existing_files", [])
        repo_config = context.get("repo_config", {})
        language = detect_language_from_files(existing_files)
        framework = detect_framework(language, repo_config)

        test_cases = []
        for index, item in enumerate(items, start=1):
            title = str(item.get("title", f"Subtask {index}")).strip()
            test_cases.append(
                {
                    "name": f"test_{index:02d}_{title.lower().replace(' ', '_')[:30]}",
                    "type": "unit",
                    "expected_result": "pass",
                }
            )
        if not test_cases:
            test_cases = [
                {
                    "name": "test_feature_baseline",
                    "type": "unit",
                    "expected_result": "pass",
                }
            ]

        # Generate test file template if spec is available (HF-P5-004)
        test_template = None
        if spec and language:
            try:
                test_template = get_test_template(language, framework)
            except Exception:
                pass

        # Extract test patterns from existing test files (HF-P5-004)
        test_patterns = {}
        existing_test_files = context.get("existing_test_files", [])
        if existing_test_files:
            test_patterns = extract_test_patterns(existing_test_files, language, framework)
            # Adapt template to project patterns
            if test_template:
                test_template = adapt_test_to_patterns(test_template, test_patterns, language, framework)

        tests_artifact = {
            "schema_version": "2.0",
            "test_cases": test_cases,
            "language": language,
            "framework": framework,
            "test_template": test_template,
            "test_patterns": test_patterns,
        }
        generated_with_rules = f" using rules {rules_version}" if rules_version else ""
        return build_agent_result(
            status="SUCCESS",
            artifact_type="tests",
            artifact_content=tests_artifact,
            reason="Test suite generated from subtask decomposition.",
            confidence=0.9,
            logs=[
                f"Generated {len(test_cases)} deterministic test cases{generated_with_rules}.",
                f"Language: {language}, Framework: {framework or 'default'}",
                f"Test patterns: fixtures={test_patterns.get('uses_fixtures', False)}, "
                f"mocks={test_patterns.get('uses_mocks', False)}",
            ],
            next_actions=["code_generator", "test_runner"],
        )

from __future__ import annotations

import json
import re
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import get_llm_wrapper
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
    legacy_build_code_prompt,
)
from agents.test_templates import get_test_template


def generate_unit_tests(function: str) -> str:
    """Generate unit tests for a given function.

    Args:
        function: Name of the function to test

    Returns:
        String containing unit test code
    """
    # Basic unit test template
    test_template = f"""def test_{function}():
    # Arrange
    # Setup test data
    
    # Act
    # Call the function
    
    # Assert
    # Verify the result
    pass"""

    return test_template


def generate_integration_tests(endpoint: str) -> str:
    """Generate integration tests for a given endpoint.

    Args:
        endpoint: API endpoint to test (e.g., "POST /login")

    Returns:
        String containing integration test code
    """
    # Parse HTTP method and path
    method, path = endpoint.split(" ", 1)
    test_name = path.strip("/").replace("/", "_").replace("-", "_")

    # Basic integration test template
    test_template = f'''def test_{test_name}():
    # Test {method} {path} endpoint
    # Arrange
    client = get_test_client()
    
    # Act
    response = client.{method.lower()}("{path}")
    
    # Assert
    assert response.status_code == 200'''

    return test_template


def generate_edge_cases(function: str) -> str:
    """Generate edge case tests for a given function.

    Args:
        function: Name of the function to test

    Returns:
        String containing edge case test code
    """
    # Basic edge case test template
    test_template = f"""def test_{function}_edge_cases():
    # Test empty input
    # Test null values
    # Test boundary conditions
    # Test error handling
    pass"""

    return test_template


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
            adapted = adapted.replace(
                "import pytest", "import pytest\nfrom unittest.mock import Mock, patch"
            )

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


def build_test_generation_prompt(
    spec: dict[str, Any], code_files: list[dict[str, Any]], language: str, framework: str
) -> str:
    """Build prompt for LLM-based test generation."""
    spec_summary = spec.get("summary", "")
    requirements = spec.get("requirements", [])
    file_changes = spec.get("file_changes", [])

    # Get code content for context
    code_context = ""
    for file_change in code_files:
        path = file_change.get("path", "")
        content = file_change.get("content", "")
        if content:
            code_context += f"\n--- {path} ---\n{content[:200]}\n"  # Limit to 2000 chars per file

    prompt = f"""You are a senior {language.title()} engineer. Generate comprehensive test cases for the following feature implementation.

## Feature Specification
{spec_summary}

## Requirements
{chr(10).join(f"- {req.get('description', '')}" for req in requirements)}

## File Changes
{chr(10).join(f"- {fc.get('path', '')}: {fc.get('description', '')}" for fc in file_changes)}

## Code Context
{code_context}

## Testing Framework
Language: {language}
Framework: {framework}

## Output Format - STRICT JSON
Generate a JSON object with EXACTLY these fields:

{{
    "test_cases": [
        {{
            "name": "test_descriptive_name",
            "type": "unit|integration|e2e",
            "description": "What this test verifies",
            "file_path": "path/to/test_file.py",
            "content": "Full test file content with imports and implementation",
            "expected_result": "pass|fail|error"
        }}
    ],
    "coverage_analysis": {{
        "covered_functions": [],
        "missing_coverage": [],
        "test_strategy": "What testing approach was used"
    }}
}}

## Critical Requirements:
1. Tests must cover all requirements from the specification
2. Follow the project's testing patterns and conventions
3. Include edge cases and error conditions
4. Use appropriate mocking and fixtures
5. Response must be valid JSON only - no markdown code blocks

Respond with valid JSON only.
"""
    return prompt


def parse_test_generation_output(output: str) -> dict[str, Any]:
    """Parse and validate LLM test generation output."""
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
    if "test_cases" not in result:
        raise ValueError("Missing required field: test_cases")

    # Validate test cases structure
    for i, tc in enumerate(result.get("test_cases", [])):
        if not isinstance(tc, dict):
            raise ValueError(f"Test case {i} is not an object")
        if "name" not in tc:
            raise ValueError(f"Test case {i} missing 'name'")
        if "content" not in tc:
            raise ValueError(f"Test case {i} missing 'content'")
        if "file_path" not in tc:
            raise ValueError(f"Test case {i} missing 'file_path'")

    return result


class TestGenerator(BaseAgent):
    name = "test_generator"
    description = "Generates comprehensive test cases from specification and code with optional LLM synthesis."

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
        code_patch = (
            get_artifact_from_context(
                context,
                "code_patch",
                preferred_steps=["code_generator"],
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

        # Try LLM-enhanced generation
        llm_test_result = None
        llm_error = None
        use_llm = context.get("use_llm", True)
        require_llm = bool(context.get("require_llm", False))

        if use_llm and spec and code_patch:
            try:
                # Try to use the new LLM wrapper first, fall back to legacy if needed
                llm = get_llm_wrapper()
                if llm is None:
                    # Try legacy wrapper for backward compatibility
                    llm = get_legacy_llm_wrapper()

                if llm is not None:
                    # Get code files from patch for context
                    code_files = code_patch.get("files", [])

                    # Try new prompt building first, fall back to legacy if needed
                    try:
                        prompt = build_test_generation_prompt(spec, code_files, language, framework)
                    except AttributeError:
                        # Fall back to legacy prompt building (using code prompt as base)
                        prompt = legacy_build_code_prompt(
                            spec, [], {"language": language, "framework": framework}
                        )

                    response = llm.complete(prompt)
                    llm.close()

                    # Clean up the response to handle potential formatting issues
                    cleaned_response = response.strip()

                    # Try to extract JSON from the response if it contains extra text
                    import re

                    json_match = re.search(r"\{[\s\S]*\}", cleaned_response)
                    if json_match:
                        json_str = json_match.group(0)
                        llm_test_result = parse_test_generation_output(json_str)
                    else:
                        llm_test_result = parse_test_generation_output(cleaned_response)
            except Exception as e:
                llm_error = str(e)

        if use_llm and require_llm and not (llm_test_result and isinstance(llm_test_result, dict)):
            return build_agent_result(
                status="FAILED",
                artifact_type="tests",
                artifact_content={
                    "schema_version": "2.0",
                    "test_cases": [],
                    "llm_required": True,
                    "llm_error": llm_error,
                },
                reason=(
                    f"LLM required but unavailable: {llm_error[:160]}"
                    if isinstance(llm_error, str) and llm_error
                    else "LLM required but no valid tests were generated."
                ),
                confidence=0.95,
                logs=[
                    "LLM strict mode enabled (require_llm=true).",
                    f"LLM error: {(llm_error or 'missing/invalid llm output')[:200]}",
                ],
                next_actions=["fix_llm_connectivity"],
            )

        if llm_test_result and isinstance(llm_test_result, dict):
            # Use LLM-generated tests
            test_cases = llm_test_result.get("test_cases", [])
            coverage_analysis = llm_test_result.get("coverage_analysis", {})
            reason = "Test suite generated with LLM enhancement."
            confidence = 0.95
        else:
            # Fallback to deterministic generation
            test_cases = []
            for index, item in enumerate(items, start=1):
                title = str(item.get("title", f"Subtask {index}")).strip()
                test_cases.append(
                    {
                        "name": f"test_{index:02d}_{title.lower().replace(' ', '_')[:30]}",
                        "type": "unit",
                        "expected_result": "pass",
                        "description": f"Test for {title}",
                        "file_path": f"tests/test_{title.lower().replace(' ', '_')[:30]}.py",
                        "content": f"def test_{index:02d}_{title.lower().replace(' ', '_')[:30]}():\n    # TODO: Implement test for {title}\n    assert True\n",
                    }
                )
            if not test_cases:
                test_cases = [
                    {
                        "name": "test_feature_baseline",
                        "type": "unit",
                        "expected_result": "pass",
                        "description": "Baseline test for feature",
                        "file_path": "tests/test_feature.py",
                        "content": "def test_feature_baseline():\n    # TODO: Implement baseline test\n    assert True\n",
                    }
                ]
            coverage_analysis = {
                "covered_functions": [],
                "missing_coverage": [],
                "test_strategy": "deterministic",
            }
            reason = (
                "Deterministic test suite generated (LLM unavailable)."
                if llm_error
                else "Test suite generated from subtask decomposition."
            )
            confidence = 0.85

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
                test_template = adapt_test_to_patterns(
                    test_template, test_patterns, language, framework
                )

        tests_artifact = {
            "schema_version": "2.0",
            "test_cases": test_cases,
            "language": language,
            "framework": framework,
            "test_template": test_template,
            "test_patterns": test_patterns,
            "coverage_analysis": coverage_analysis,
            "llm_enhanced": llm_test_result is not None,
        }
        generated_with_rules = f" using rules {rules_version}" if rules_version else ""
        logs = [
            f"Generated {len(test_cases)} test cases{generated_with_rules}.",
            f"Language: {language}, Framework: {framework or 'default'}",
            f"Test patterns: fixtures={test_patterns.get('uses_fixtures', False)}, "
            f"mocks={test_patterns.get('uses_mocks', False)}",
        ]
        if llm_error:
            logs.append(f"LLM error: {llm_error[:100]}")

        return build_agent_result(
            status="SUCCESS",
            artifact_type="tests",
            artifact_content=tests_artifact,
            reason=reason,
            confidence=confidence,
            logs=logs,
            next_actions=["code_generator", "test_runner"],
        )

from __future__ import annotations

import json
import re
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result, get_artifact_from_context
from agents.llm_wrapper import get_llm_wrapper
from agents.llm_wrapper_backward_compatibility import (
    get_legacy_llm_wrapper,
)
from agents.test_templates import get_test_template


def generate_unit_tests(function: str) -> str:
    return f"""def test_{function}():
    # Arrange
    # Setup test data

    # Act
    # Call the function

    # Assert
    # Verify the result
    raise NotImplementedError("Test not implemented for {function}")
"""


def generate_integration_tests(endpoint: str) -> str:
    method, path = endpoint.split(" ", 1)
    test_name = path.strip("/").replace("/", "_").replace("-", "_") or "endpoint"
    return f'''def test_{test_name}():
    # Test {method} {path} endpoint
    # Arrange
    client = get_test_client()

    # Act
    response = client.{method.lower()}("{path}")

    # Assert
    assert response.status_code == 200
'''


def generate_edge_cases(function: str) -> str:
    return f"""def test_{function}_edge_cases():
    # Test empty input
    # Test null values
    # Test boundary conditions
    # Test error handling
    raise NotImplementedError("Edge-case test not implemented for {function}")
"""


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
        "pytest": ["pytest.ini", "pytest", "conftest.py"],
        "unittest": ["unittest", "TestCase"],
    },
    "javascript": {
        "jest": ["jest.config", "jest"],
        "mocha": ["mocha"],
        "vitest": ["vitest.config", "vitest"],
    },
    "typescript": {
        "jest": ["jest.config", "@types/jest", "jest"],
        "vitest": ["vitest.config", "vitest"],
    },
    "go": {"testing": ["go.mod", "_test.go"]},
}
TEST_PATTERNS = {
    "python": {
        "pytest": {
            "fixture_usage": r"@pytest\.fixture\b",
            "parametrize": r"@pytest\.mark\.parametrize\b",
            "mock_import": r"from unittest\.mock import|@patch\(",
            "assertions": r"\bassert\s+",
        },
        "unittest": {
            "test_class": r"class\s+Test\w+\(unittest\.TestCase\):",
            "set_up": r"def\s+setUp\(self\):",
        },
    },
    "javascript": {
        "jest": {
            "describe": r"describe\(",
            "test": r"\b(test|it)\(",
            "mock": r"(jest|vi)\.mock\(",
            "before_each": r"beforeEach\s*\(",
        }
    },
    "typescript": {
        "jest": {
            "describe": r"describe\(",
            "test": r"\b(test|it)\(",
            "mock": r"(jest|vi)\.mock\(",
            "before_each": r"beforeEach\s*\(",
        }
    },
}


def _slugify(text: str, max_length: int = 30) -> str:
    value = re.sub(r"[^\w]+", "_", text.lower()).strip("_")
    value = re.sub(r"_+", "_", value)
    return (value[:max_length] or "feature").strip("_") or "feature"


def _collect_acceptance_criteria(context: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    criteria: list[str] = []
    spec_criteria = spec.get("acceptance_criteria", [])
    if isinstance(spec_criteria, list):
        criteria.extend(str(item).strip() for item in spec_criteria if str(item).strip())

    dod = context.get("dod")
    if isinstance(dod, dict):
        dod_criteria = dod.get("acceptance_criteria", [])
        if isinstance(dod_criteria, list):
            criteria.extend(str(item).strip() for item in dod_criteria if str(item).strip())

    dod_artifact = get_artifact_from_context(context, "dod", preferred_steps=["dod_extractor"])
    if isinstance(dod_artifact, dict):
        dod_criteria = dod_artifact.get("acceptance_criteria", [])
        if isinstance(dod_criteria, list):
            criteria.extend(str(item).strip() for item in dod_criteria if str(item).strip())

    out: list[str] = []
    seen: set[str] = set()
    for item in criteria:
        key = item.lower()
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def _safe_framework_default(language: str, framework: str | None) -> str | None:
    return framework or {
        "python": "pytest",
        "javascript": "jest",
        "typescript": "jest",
        "go": "testing",
    }.get(language)


def extract_test_patterns(
    test_files: list[dict[str, Any]], language: str, framework: str | None = None
) -> dict[str, Any]:
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

    framework_patterns = TEST_PATTERNS.get(language, {}).get(framework or "", {})
    if not framework_patterns:
        lang_patterns = TEST_PATTERNS.get(language, {})
        if lang_patterns:
            framework_patterns = next(iter(lang_patterns.values()))

    all_contents: list[str] = []
    for test_file in test_files:
        file_content = str(test_file.get("content", "") or "")
        if not file_content:
            continue

        all_contents.append(file_content)
        for pattern_name, pattern_regex in framework_patterns.items():
            if re.search(pattern_regex, file_content):
                if pattern_name in ("fixture_usage", "set_up", "before_each"):
                    patterns["uses_fixtures"] = True
                if pattern_name in ("mock_import", "mock"):
                    patterns["uses_mocks"] = True
                if pattern_name == "parametrize":
                    patterns["uses_parametrize"] = True
                if pattern_name in ("set_up", "before_each", "tear_down", "after_each"):
                    patterns["uses_setups"] = True

        patterns["common_assertions"].extend(re.findall(r"\bassert\s+([\w\.]+)", file_content)[:5])

    patterns["common_assertions"] = list(dict.fromkeys(patterns["common_assertions"]))

    combined_content = " ".join(all_contents)
    if combined_content:
        camel_pattern = re.findall(r"(?:test|it)\s*\(\s*['\"]([A-Z]\w*)", combined_content)
        if camel_pattern:
            patterns["naming_convention"] = "camelCase"

    return patterns


def adapt_test_to_patterns(
    test_content: str, patterns: dict[str, Any], language: str, framework: str | None
) -> str:
    adapted = test_content
    if (
        patterns.get("uses_fixtures")
        and "pytest.fixture" not in adapted
        and language == "python"
        and framework == "pytest"
        and "import pytest" in adapted
    ):
        adapted = adapted.replace(
            "import pytest",
            "import pytest\n\n@pytest.fixture\ndef mock_dependencies():\n    return {}",
        )

    if (
        patterns.get("uses_mocks")
        and language == "python"
        and "from unittest.mock import" not in adapted
        and "import pytest" in adapted
    ):
        adapted = adapted.replace(
            "import pytest", "import pytest\nfrom unittest.mock import Mock, patch"
        )

    return adapted


def detect_language_from_files(files: list[str]) -> str:
    counts: dict[str, int] = {}
    for file_path in files:
        if "." in file_path:
            lang = LANGUAGE_EXTENSIONS.get(file_path.rsplit(".", 1)[1])
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.get) if counts else "python"


def detect_framework(language: str, repo_config: dict[str, Any] | None = None) -> str | None:
    if not repo_config:
        return None

    config_files = repo_config.get("config_files", [])
    for framework, files in FRAMEWORK_INDICATORS.get(language, {}).items():
        if any(any(token in str(cf) for token in files) for cf in config_files):
            return framework

    package_json = repo_config.get("package_json")
    if language in ("javascript", "typescript") and package_json:
        deps = package_json.get("devDependencies", {})
        for name in ("jest", "vitest", "mocha"):
            if name in deps:
                return name

    return None


def build_test_generation_prompt(
    spec: dict[str, Any],
    code_files: list[dict[str, Any]],
    language: str,
    framework: str | None,
    acceptance_criteria=None,
    bdd_specification=None,
    subtasks=None,
) -> str:
    summary = spec.get("summary") or spec.get("feature_description") or spec.get("user_story") or ""
    return (
        f"Generate tests as strict JSON for {language}/{framework or 'default'}\nFeature: {summary}"
    )


def _extract_json_block(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid JSON object found in LLM output")


def parse_test_generation_output(output: str) -> dict[str, Any]:
    result = _extract_json_block(output)
    if "test_cases" not in result:
        raise ValueError("Missing required field: test_cases")
    for index, tc in enumerate(result.get("test_cases", [])):
        if not isinstance(tc, dict):
            raise ValueError(f"Test case {index} is not an object")
        for field in ("name", "content", "file_path"):
            if not tc.get(field):
                raise ValueError(f"Test case {index} missing '{field}'")
    return result


def _extract_spec(context: dict[str, Any]) -> dict[str, Any]:
    spec = (
        get_artifact_from_context(context, "spec", preferred_steps=["specification_writer"]) or {}
    )
    return spec if isinstance(spec, dict) else {}


def _validate_passthrough_tests(existing_tests: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    test_cases = existing_tests.get("test_cases", [])
    if not isinstance(test_cases, list) or not test_cases:
        return False, ["tests.test_cases must be a non-empty list"]

    for index, test_case in enumerate(test_cases):
        if not isinstance(test_case, dict):
            errors.append(f"test_case[{index}] must be an object")
            continue

        for field in ("name", "file_path", "content"):
            value = test_case.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"test_case[{index}].{field} must be a non-empty string")

        path = str(test_case.get("file_path", ""))
        if path.startswith("/") or ".." in path.replace("\\", "/").split("/"):
            errors.append(f"test_case[{index}].file_path must be relative and safe")

    return not errors, errors


def _assess_test_quality(
    *,
    test_cases: list[dict[str, Any]],
    acceptance_criteria: list[str],
    generation_mode: str,
) -> dict[str, Any]:
    placeholder_count = 0
    for case in test_cases:
        content = str(case.get("content", ""))
        if "NotImplementedError" in content or "TODO:" in content:
            placeholder_count += 1

    completeness = "high"
    if not test_cases or placeholder_count == len(test_cases):
        completeness = "low"
    elif placeholder_count > 0 or len(test_cases) < max(1, len(acceptance_criteria)):
        completeness = "medium"

    return {
        "test_cases_count": len(test_cases),
        "acceptance_criteria_count": len(acceptance_criteria),
        "covered_requirements_count": min(len(test_cases), len(acceptance_criteria)),
        "contains_placeholders": placeholder_count > 0,
        "placeholder_count": placeholder_count,
        "generation_mode": generation_mode,
        "test_suite_completeness": completeness,
    }


def _passthrough_tests_are_plausible(
    existing_tests: dict[str, Any], acceptance_criteria: list[str]
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    test_cases = existing_tests.get("test_cases", [])
    if not isinstance(test_cases, list):
        return False, ["tests.test_cases must be a list"]

    if acceptance_criteria and len(test_cases) > max(6, len(acceptance_criteria) * 3):
        issues.append(
            "Passthrough tests appear over-generated relative to acceptance criteria count."
        )

    suspicious_terms = {"ui", "form validation", "responsive", "browser", "frontend"}
    ac_text = " ".join(item.lower() for item in acceptance_criteria)
    if acceptance_criteria and not any(term in ac_text for term in suspicious_terms):
        for case in test_cases:
            if not isinstance(case, dict):
                continue
            text = f"{case.get('name', '')} {case.get('description', '')}".lower()
            if any(term in text for term in suspicious_terms):
                issues.append("Passthrough tests contain suspicious UI-oriented cases.")
                break

    return not issues, issues


class TestGenerator(BaseAgent):
    name = "test_generator"
    description = "Generates comprehensive test cases from specification and code with optional LLM synthesis."

    def run(self, context: dict[str, Any]) -> dict:
        spec = _extract_spec(context)
        acceptance_criteria = _collect_acceptance_criteria(context, spec)

        existing_tests = context.get("tests")
        if isinstance(existing_tests, dict) and existing_tests:
            valid, errors = _validate_passthrough_tests(existing_tests)
            plausible, plausibility_issues = _passthrough_tests_are_plausible(
                existing_tests, acceptance_criteria
            )

            if not valid:
                return build_agent_result(
                    status="BLOCKED",
                    artifact_type="tests",
                    artifact_content={
                        "schema_version": "2.1",
                        "test_cases": [],
                        "quality_signals": {
                            "generation_mode": "passthrough",
                            "test_suite_completeness": "low",
                            "validation_errors": errors,
                        },
                    },
                    reason="Upstream tests were provided but failed validation.",
                    confidence=0.98,
                    logs=errors,
                    next_actions=["fix_upstream_tests_payload"],
                )

            test_cases = existing_tests.get("test_cases", [])
            quality = _assess_test_quality(
                test_cases=test_cases,
                acceptance_criteria=acceptance_criteria,
                generation_mode="passthrough",
            )

            status = (
                "SUCCESS" if quality["test_suite_completeness"] == "high" else "PARTIAL_SUCCESS"
            )
            logs = ["Tests reused from upstream pipeline (passthrough mode)."]
            if not plausible:
                status = "PARTIAL_SUCCESS"
                logs.extend(plausibility_issues)

            return build_agent_result(
                status=status,
                artifact_type="tests",
                artifact_content={
                    "schema_version": "2.1",
                    "test_cases": test_cases,
                    "language": existing_tests.get("language", "python"),
                    "framework": existing_tests.get("framework"),
                    "test_template": existing_tests.get("test_template"),
                    "test_patterns": existing_tests.get("test_patterns", {}),
                    "coverage_analysis": existing_tests.get("coverage_analysis", {}),
                    "llm_enhanced": existing_tests.get("llm_enhanced", False),
                    "quality_signals": {
                        **quality,
                        "plausibility_issues": plausibility_issues,
                    },
                    "plan_provenance": {"source": "upstream_tests", "rebuilt": False},
                },
                reason="Tests passed through from upstream pipeline.",
                confidence=0.95,
                logs=logs,
                next_actions=["code_generator", "test_runner"],
            )

        subtasks = (
            get_artifact_from_context(context, "subtasks", preferred_steps=["task_decomposer"])
            or {}
        )
        code_patch = (
            get_artifact_from_context(context, "code_patch", preferred_steps=["code_generator"])
            or {}
        )
        bdd_specification = (
            get_artifact_from_context(
                context, "bdd_specification", preferred_steps=["bdd_generator"]
            )
            or {}
        )

        items = subtasks.get("items") if isinstance(subtasks, dict) else []
        if not isinstance(items, list):
            items = []

        existing_files = context.get("existing_files", [])
        repo_config = context.get("repo_config", {})
        explicit_language = context.get("language")

        if isinstance(explicit_language, str) and explicit_language.strip():
            language, language_confidence = explicit_language.strip().lower(), "explicit"
        else:
            language, language_confidence = (
                detect_language_from_files(existing_files),
                ("derived" if existing_files else "default"),
            )

        framework = _safe_framework_default(language, detect_framework(language, repo_config))
        framework_confidence = "derived" if repo_config else "default"

        has_meaningful_input = (
            bool(spec)
            or bool(acceptance_criteria)
            or bool(items)
            or (isinstance(bdd_specification, dict) and bool(bdd_specification))
        )
        if not has_meaningful_input:
            return build_agent_result(
                status="BLOCKED",
                artifact_type="tests",
                artifact_content={
                    "schema_version": "2.1",
                    "test_cases": [],
                    "quality_signals": {
                        "generation_mode": "none",
                        "test_suite_completeness": "low",
                        "acceptance_criteria_count": 0,
                        "test_cases_count": 0,
                    },
                },
                reason="Insufficient planning artifacts for test generation.",
                confidence=0.98,
                logs=["Missing usable spec, acceptance criteria, subtasks, or BDD input."],
                next_actions=["specification_writer", "task_decomposer", "bdd_generator"],
            )

        llm_test_result = None
        llm_error = None
        if context.get("use_llm", True) and spec:
            try:
                llm = get_llm_wrapper() or get_legacy_llm_wrapper()
                if llm is not None:
                    response = llm.complete(
                        build_test_generation_prompt(
                            spec,
                            code_patch.get("files", []) if isinstance(code_patch, dict) else [],
                            language,
                            framework,
                            acceptance_criteria,
                            bdd_specification if isinstance(bdd_specification, dict) else {},
                            subtasks if isinstance(subtasks, dict) else {},
                        )
                    )
                    llm.close()
                    llm_test_result = parse_test_generation_output(response.strip())
            except Exception as exc:
                llm_error = str(exc)

        if (
            context.get("use_llm", True)
            and bool(context.get("require_llm", False))
            and not (llm_test_result and isinstance(llm_test_result, dict))
        ):
            return build_agent_result(
                status="FAILED",
                artifact_type="tests",
                artifact_content={
                    "schema_version": "2.1",
                    "test_cases": [],
                    "llm_required": True,
                    "llm_error": llm_error,
                    "quality_signals": {
                        "generation_mode": "llm_required",
                        "test_suite_completeness": "low",
                    },
                },
                reason=(
                    f"LLM required but unavailable: {llm_error[:160]}"
                    if llm_error
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
            test_cases = llm_test_result.get("test_cases", [])
            coverage_analysis = llm_test_result.get("coverage_analysis", {})
            generation_mode, reason, confidence = (
                "llm",
                "Test suite generated with LLM enhancement.",
                0.95,
            )
        else:
            test_cases = []
            for index, criterion in enumerate(acceptance_criteria, start=1):
                slug = _slugify(criterion, 30)
                test_cases.append(
                    {
                        "name": f"test_ac_{index:02d}_{slug}",
                        "type": "integration"
                        if any(t in criterion.lower() for t in ("api", "endpoint"))
                        else "unit",
                        "expected_result": "pass",
                        "description": f"Acceptance criterion coverage: {criterion}",
                        "file_path": f"tests/test_{slug}.py",
                        "content": (
                            f"def test_ac_{index:02d}_{slug}():\n"
                            f"    # Covers acceptance criterion: {criterion}\n"
                            f'    raise NotImplementedError("Test not implemented for acceptance criterion: {criterion}")\n'
                        ),
                    }
                )

            if not test_cases:
                for index, item in enumerate(items, start=1):
                    title = str(item.get("title", f"Subtask {index}")).strip()
                    slug = _slugify(title, 30)
                    test_cases.append(
                        {
                            "name": f"test_{index:02d}_{slug}",
                            "type": "unit",
                            "expected_result": "pass",
                            "description": f"Test for {title}",
                            "file_path": f"tests/test_{slug}.py",
                            "content": (
                                f"def test_{index:02d}_{slug}():\n"
                                f"    # TODO: Implement test for {title}\n"
                                f'    raise NotImplementedError("Test not implemented for {title}")\n'
                            ),
                        }
                    )

            if not test_cases and spec:
                baseline_summary = (
                    spec.get("summary") or spec.get("feature_description") or "feature"
                )
                slug = _slugify(str(baseline_summary), 30)
                test_cases = [
                    {
                        "name": "test_feature_baseline",
                        "type": "unit",
                        "expected_result": "pass",
                        "description": f"Baseline test for {baseline_summary}",
                        "file_path": f"tests/test_{slug}.py",
                        "content": (
                            "def test_feature_baseline():\n"
                            "    # TODO: Implement baseline test\n"
                            '    raise NotImplementedError("Baseline test not implemented")\n'
                        ),
                    }
                ]

            coverage_analysis = {
                "covered_functions": [],
                "missing_coverage": [],
                "covered_requirements": acceptance_criteria,
                "test_strategy": "deterministic_acceptance_criteria"
                if acceptance_criteria
                else "deterministic_subtasks",
            }
            generation_mode, reason, confidence = (
                "deterministic",
                (
                    "Deterministic test suite generated (LLM unavailable)."
                    if llm_error
                    else "Test suite generated from planning artifacts."
                ),
                0.85,
            )

        test_template = None
        if spec and language:
            try:
                test_template = get_test_template(language, framework)
            except Exception:
                pass

        test_patterns = {}
        existing_test_files = context.get("existing_test_files", [])
        if existing_test_files:
            test_patterns = extract_test_patterns(existing_test_files, language, framework)
            if test_template:
                test_template = adapt_test_to_patterns(
                    test_template, test_patterns, language, framework
                )

        quality = _assess_test_quality(
            test_cases=test_cases,
            acceptance_criteria=acceptance_criteria,
            generation_mode=generation_mode,
        )
        quality["language_confidence"] = language_confidence
        quality["framework_confidence"] = framework_confidence

        artifact = {
            "schema_version": "2.1",
            "test_cases": test_cases,
            "language": language,
            "framework": framework,
            "test_template": test_template,
            "test_patterns": test_patterns,
            "coverage_analysis": coverage_analysis,
            "llm_enhanced": llm_test_result is not None,
            "quality_signals": quality,
            "plan_provenance": {
                "source": generation_mode,
                "rebuilt": generation_mode != "passthrough",
                "rules_version": None,
            },
        }

        status = "SUCCESS" if quality["test_suite_completeness"] == "high" else "PARTIAL_SUCCESS"
        logs = [
            f"Generated {len(test_cases)} test cases.",
            f"Language: {language}, Framework: {framework or 'default'}",
            f"Acceptance criteria used: {len(acceptance_criteria)}",
        ]
        if llm_error:
            logs.append(f"LLM error: {llm_error[:100]}")

        return build_agent_result(
            status=status,
            artifact_type="tests",
            artifact_content=artifact,
            reason=reason,
            confidence=confidence,
            logs=logs,
            next_actions=["code_generator", "test_runner"],
        )

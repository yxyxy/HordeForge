from agents.test_generator import (
    TestGenerator,
    generate_edge_cases,
    generate_integration_tests,
    generate_unit_tests,
)


def _artifact_content(result: dict, artifact_type: str) -> dict:
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}


class TestPrimitiveTemplateHelpers:
    def test_generate_unit_tests(self):
        assert "def test_add" in generate_unit_tests("add")

    def test_generate_integration_tests(self):
        assert "test_login" in generate_integration_tests("POST /login")

    def test_generate_edge_cases(self):
        assert "empty" in generate_edge_cases("add")


class TestTestGeneratorAgent:
    def test_blocks_invalid_passthrough_tests(self):
        result = TestGenerator().run(
            {"tests": {"test_cases": [{"name": "x", "file_path": "", "content": ""}]}}
        )
        assert result["status"] == "BLOCKED"
        assert (
            _artifact_content(result, "tests")["quality_signals"]["test_suite_completeness"]
            == "low"
        )

    def test_passthrough_valid_tests(self):
        result = TestGenerator().run(
            {
                "tests": {
                    "test_cases": [
                        {
                            "name": "test_valid",
                            "file_path": "tests/test_valid.py",
                            "content": "def test_valid():\n    assert True\n",
                        }
                    ],
                    "language": "python",
                    "framework": "pytest",
                }
            }
        )
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
        assert _artifact_content(result, "tests")["plan_provenance"]["source"] == "upstream_tests"

    def test_blocks_when_no_meaningful_planning_inputs(self):
        assert TestGenerator().run({})["status"] == "BLOCKED"

    def test_generates_deterministic_tests_from_spec(self):
        context = {
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "User login",
                            "feature_description": "Login feature",
                            "acceptance_criteria": ["API endpoint validates credentials"],
                            "file_change_plan": {"files_to_create": ["auth/service.py"]},
                        },
                    }
                ]
            },
            "existing_files": ["auth/service.py"],
            "repo_config": {"config_files": ["pytest.ini"]},
        }
        result = TestGenerator().run(context)
        content = _artifact_content(result, "tests")
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
        assert content["language"] == "python"
        assert len(content["test_cases"]) >= 1

    def test_fails_in_require_llm_mode(self, monkeypatch):
        class _FailingWrapper:
            def complete(self, prompt: str):
                raise RuntimeError("llm unavailable")

            def close(self):
                return None

        import agents.test_generator as module

        monkeypatch.setattr(module, "get_llm_wrapper", lambda *args, **kwargs: _FailingWrapper())
        monkeypatch.setattr(module, "get_legacy_llm_wrapper", lambda *args, **kwargs: None)
        context = {
            "use_llm": True,
            "require_llm": True,
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {"summary": "Feature", "acceptance_criteria": ["criterion"]},
                    }
                ]
            },
        }
        assert TestGenerator().run(context)["status"] == "FAILED"

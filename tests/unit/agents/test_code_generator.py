"""TDD: Test-Driven Development для Code Generator Agent"""

import json

import agents.code_generator as code_generator_module
from agents.code_generator import CodeGenerator


class TestCodeGeneratorAgent:
    """TDD: Code Generator Agent Integration Tests"""

    def test_run_with_valid_feature(self):
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        generator = CodeGenerator()

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        assert len(result["artifacts"]) > 0
        artifact = result["artifacts"][0]
        assert artifact["type"] == "code_patch"
        assert "files" in artifact["content"]

    def test_run_handles_empty_feature(self):
        context = {"issue": {"title": "", "body": ""}}
        generator = CodeGenerator()

        result = generator.run(context)

        assert result["status"] == "SUCCESS"

    def test_run_handles_missing_issue(self):
        context = {}
        generator = CodeGenerator()

        result = generator.run(context)

        assert result["status"] == "SUCCESS"

    def test_run_generates_all_required_fields(self):
        context = {
            "issue": {"title": "Test feature implementation", "body": "Implement test feature"}
        }
        generator = CodeGenerator()

        result = generator.run(context)

        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]

        assert "schema_version" in content
        assert "files" in content
        assert "decisions" in content
        assert "dry_run" in content
        assert "selected_target_files" in content
        assert "allow_new_files" in content

        if content["files"]:
            file_patch = content["files"][0]
            assert "path" in file_patch
            assert "change_type" in file_patch
            assert "content" in file_patch

    def test_run_with_spec_and_tests(self):
        context = {
            "spec": {
                "summary": "Test feature",
                "file_changes": [{"path": "test.py", "description": "test file"}],
            },
            "tests": {
                "test_cases": [
                    {
                        "name": "test_func",
                        "content": "def test_func(): pass",
                        "file_path": "tests/test_func.py",
                    }
                ]
            },
            "subtasks": {"items": [{"title": "subtask1"}]},
        }
        generator = CodeGenerator()

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]
        assert "files" in content

    def test_backward_compatibility_alias(self):
        from agents.code_generator import CodeGenerator as AliasCodeGenerator

        assert CodeGenerator == AliasCodeGenerator

    def test_default_branch_name_format(self):
        generator = CodeGenerator()
        branch = generator._default_branch_name(  # noqa: SLF001
            {"issue": {"number": 42, "title": "Fix Bandit B608 and B310 now"}}
        )

        assert branch == "horde/42-fix-bandit-b608-and-b310-now"

    def test_detects_ci_incident_ghcr_permission_pattern(self):
        generator = CodeGenerator()
        issue_context = (
            "ERROR: failed to push ghcr.io/org/repo:main: denied: installation not allowed "
            "to Create organization package"
        )

        assert generator._should_apply_ghcr_permissions_fix(issue_context) is True  # noqa: SLF001

    def test_detects_ci_incident_ghcr_permission_pattern_when_message_truncated(self):
        generator = CodeGenerator()
        issue_context = "failed to push ghcr.io/x/y:main: denied: installation not allowed to Creat"

        assert generator._should_apply_ghcr_permissions_fix(issue_context) is True  # noqa: SLF001

    def test_builds_ci_patch_from_workflow_for_ghcr_permission_issue(self):
        generator = CodeGenerator()
        issue_context = (
            "failed to push ghcr.io/x/y:main: denied: installation not allowed "
            "to Create organization package"
        )
        workflow = (
            "name: CI\n\non:\n  push:\n    branches: [main]\n\nenv:\n  DOCKER_REGISTRY: ghcr.io\n"
        )

        patch = generator._build_ci_permissions_patch_from_workflow(  # noqa: SLF001
            issue_context, workflow
        )

        assert patch is not None
        assert patch["files"][0]["path"] == ".github/workflows/ci.yml"
        content = patch["files"][0]["content"]
        assert "permissions:" in content
        assert "packages: write" in content
        assert patch["allow_new_files"] is False

    def test_normalize_llm_error_for_json_decode(self):
        generator = CodeGenerator()
        exc = json.JSONDecodeError("Expecting value", "", 0)

        normalized = generator._normalize_llm_error(exc)  # noqa: SLF001

        assert "invalid JSON payload" in normalized
        assert "credentials/profile" in normalized

    def test_marks_issue_as_fixed_when_pr_created(self, monkeypatch):
        updated_labels: list[tuple[int, list[str]]] = []
        issue_comments: list[tuple[int, str]] = []

        class _FakeGitHubClient:
            def update_issue_labels(self, issue_number: int, labels: list[str]):
                updated_labels.append((issue_number, labels))
                return {"number": issue_number, "labels": labels}

            def comment_issue(self, issue_number: int, comment: str):
                issue_comments.append((issue_number, comment))
                return {"issue_number": issue_number, "body": comment}

        class _FakePatchResult:
            success = True
            pr_url = "https://github.com/acme/hordeforge/pull/1"
            pr_number = 1
            branch_name = "horde/3-fix"
            error = None
            rollback_performed = False

        class _FakePatchWorkflow:
            def __init__(self, github_client):
                self.github_client = github_client

            def apply_patch(self, files, pr_title, pr_body, branch_name):
                return _FakePatchResult()

        generator = CodeGenerator()
        fake_client = _FakeGitHubClient()
        monkeypatch.setattr(
            generator,
            "_resolve_github_client",
            lambda context: (fake_client, "provided_in_context"),
        )
        monkeypatch.setattr(
            code_generator_module,
            "PatchWorkflowOrchestrator",
            _FakePatchWorkflow,
        )

        context = {
            "use_llm": False,
            "github_token": "ghs_test",
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {
                "number": 3,
                "title": "Fix CI",
                "labels": [{"name": "agent:planning"}, {"name": "kind:ci-incident"}],
            },
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "Fix CI",
                            "file_changes": [{"path": "src/feature_impl.py"}],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        artifact = result["artifacts"][0]["content"]
        assert artifact["applied_to_github"] is True
        assert artifact["pr_number"] == 1
        assert updated_labels
        assert updated_labels[0][0] == 3
        assert "agent:fixed" in updated_labels[0][1]
        assert "agent:planning" not in updated_labels[0][1]
        assert issue_comments
        assert issue_comments[0][0] == 3
        assert "https://github.com/acme/hordeforge/pull/1" in issue_comments[0][1]

    def test_fails_when_llm_required_and_llm_unavailable(self, monkeypatch):
        class _FailingWrapper:
            def complete(self, prompt: str):
                raise RuntimeError("llm unavailable")

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _FailingWrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "issue": {"number": 7, "title": "Critical fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Critical fix", "file_changes": []}}
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "FAILED"
        assert result["artifacts"][0]["type"] == "code_patch"

    def test_skips_pr_publish_when_disabled(self, monkeypatch):
        class _UnexpectedPatchWorkflow:
            def __init__(self, github_client):
                raise AssertionError("Patch workflow should not be initialized")

        monkeypatch.setattr(
            code_generator_module,
            "PatchWorkflowOrchestrator",
            _UnexpectedPatchWorkflow,
        )

        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "github_token": "ghs_test",
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 5, "title": "Prepare code only"},
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "Prepare code only",
                            "file_changes": [{"path": "src/feature_impl.py"}],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch.get("applied_to_github") is not True
        assert patch.get("pr_number") is None

    def test_parses_llm_response_wrapped_in_markdown_fences(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return """```json
{
  "files": [
    {
      "path": "src/example.py",
      "change_type": "create",
      "content": "def run() -> str:\\n    return \\"ok\\"\\n"
    }
  ],
  "decisions": [],
  "test_changes": []
}
```"""

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "Generate simple file",
                            "file_changes": [{"path": "src/example.py"}],
                        },
                    }
                ]
            },
            "test_generator": {
                "artifacts": [
                    {
                        "type": "tests",
                        "content": {
                            "test_cases": [
                                {
                                    "name": "test_run",
                                    "file_path": "tests/test_example.py",
                                    "content": "def test_run(): assert True",
                                }
                            ]
                        },
                    }
                ]
            },
            "task_decomposer": {
                "artifacts": [{"type": "subtasks", "content": {"items": [{"title": "impl"}]}}]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["llm_enhanced"] is True
        assert patch["files"][0]["path"] == "src/example.py"
        assert patch["files"][0]["change_type"] == "create"

    def test_parse_llm_patch_response_uses_balanced_json_fallback(self):
        generator = CodeGenerator()
        response = (
            "prefix text "
            '{"files":[{"path":"src/example.py","change_type":"create","content":"x"}],'
            '"decisions":[],"test_changes":[]}'
            " trailing text"
        )

        parsed = generator._parse_llm_patch_response(response)  # noqa: SLF001

        assert parsed is not None
        assert parsed["files"][0]["path"] == "src/example.py"

    def test_collect_candidate_files_from_ci_context(self):
        generator = CodeGenerator()
        context = {
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "files": ["workspace/repo/orchestrator/loader.py"],
                            "test_targets": ["workspace/repo/tests/unit/test_loader.py::test_ok"],
                        },
                    }
                ]
            }
        }
        candidate_files = generator._collect_candidate_files(  # noqa: SLF001
            spec={},
            tests={},
            rag_context={},
            ci_failure_context={
                "files": ["workspace/repo/orchestrator/loader.py"],
                "test_targets": ["workspace/repo/tests/unit/test_loader.py::test_ok"],
            },
        )

        assert "orchestrator/loader.py" in candidate_files
        assert "tests/unit/test_loader.py" in candidate_files

    def test_filters_llm_patch_to_grounded_candidates(self):
        generator = CodeGenerator()
        files, notes = generator._filter_patch_files(  # noqa: SLF001
            [
                {"path": "src/fake.py", "change_type": "create", "content": "x"},
                {"path": "orchestrator/loader.py", "change_type": "modify", "content": "y"},
            ],
            candidate_files=["orchestrator/loader.py"],
            allow_new_files=False,
        )

        assert len(files) == 1
        assert files[0]["path"] == "orchestrator/loader.py"
        assert any("filtered_non_candidate_file=src/fake.py" in item for item in notes)

    def test_deterministic_patch_prefers_candidate_file(self):
        generator = CodeGenerator()
        patch = generator._build_deterministic_patch(  # noqa: SLF001
            spec={},
            tests={},
            subtask_count=0,
            rag_source_count=0,
            rule_doc_count=0,
            rules_version="",
            issue_context_text="",
            candidate_files=["orchestrator/loader.py"],
            allow_new_files=False,
            ci_failure_context={"classification": "test_failure"},
        )

        assert patch["files"][0]["path"] == "orchestrator/loader.py"
        assert patch["allow_new_files"] is False
        assert patch["selected_target_files"][0]["path"] == "orchestrator/loader.py"

    def test_deterministic_patch_does_not_create_synthetic_file_when_grounding_required(self):
        generator = CodeGenerator()
        patch = generator._build_deterministic_patch(  # noqa: SLF001
            spec={},
            tests={},
            subtask_count=0,
            rag_source_count=0,
            rule_doc_count=0,
            rules_version="",
            issue_context_text="",
            candidate_files=[],
            allow_new_files=False,
            ci_failure_context={"classification": "path_error"},
        )

        assert patch["files"] == []
        assert patch["blocked"] is True

    def test_run_uses_ci_candidate_files_in_output(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "specification_writer": {
                "artifacts": [{"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": ["workspace/repo/orchestrator/loader.py"],
                            "test_targets": ["workspace/repo/tests/unit/test_loader.py::test_ok"],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["files"][0]["path"] == "orchestrator/loader.py"
        assert patch["allow_new_files"] is False
        assert patch["selected_target_files"][0]["path"] == "orchestrator/loader.py"
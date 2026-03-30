"""TDD: Test-Driven Development для Code Generator Agent"""

import json

import agents.code_generator as code_generator_module
from agents.code_generator import CodeGenerator


class TestCodeGeneratorAgent:
    """TDD: Code Generator Agent Integration Tests"""

    def test_run_with_valid_feature(self):
        """TDD: Code generator runs with valid feature data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        assert len(result["artifacts"]) > 0
        artifact = result["artifacts"][0]
        assert artifact["type"] == "code_patch"
        assert "files" in artifact["content"]

    def test_run_handles_empty_feature(self):
        """TDD: Code generator handles empty feature description"""
        # Arrange
        context = {"issue": {"title": "", "body": ""}}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"  # Should succeed with default values

    def test_run_handles_missing_issue(self):
        """TDD: Code generator handles missing issue data"""
        # Arrange
        context = {}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"  # Should succeed with default values

    def test_run_generates_all_required_fields(self):
        """TDD: Code generator generates all required fields"""
        # Arrange
        context = {
            "issue": {"title": "Test feature implementation", "body": "Implement test feature"}
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]

        # Check required fields
        assert "schema_version" in content
        assert "files" in content
        assert "decisions" in content
        assert "dry_run" in content

        # Check file structure
        file_patch = content["files"][0]
        assert "path" in file_patch
        assert "change_type" in file_patch
        assert "content" in file_patch

    def test_run_with_spec_and_tests(self):
        """TDD: Code generator works with spec and tests from context"""
        # Arrange
        context = {
            "spec": {
                "summary": "Test feature",
                "file_changes": [{"path": "test.py", "description": "test file"}],
            },
            "tests": {"test_cases": [{"name": "test_func", "content": "def test_func(): pass"}]},
            "subtasks": {"items": [{"title": "subtask1"}]},
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert "artifacts" in result
        artifact = result["artifacts"][0]
        content = artifact["content"]
        assert "files" in content
        assert len(content["files"]) > 0

    def test_backward_compatibility_alias(self):
        """TDD: Backward compatibility alias works"""
        # Arrange
        from agents.code_generator import CodeGenerator as AliasCodeGenerator

        # Assert
        assert CodeGenerator == AliasCodeGenerator

    def test_default_branch_name_format(self):
        """Default branch name follows horde/<issue-number>-<slug>."""
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
        issue_context = "failed to push ghcr.io/x/y:main: denied: installation not allowed to Create organization package"
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

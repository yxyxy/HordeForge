from __future__ import annotations

from agents.code_generator import EnhancedCodeGenerator
from agents.specification_writer import EnhancedSpecificationWriter


def _get_content(result: dict, artifact_type: str) -> dict:
    """Extract content from agent result."""
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}


def test_enhanced_specification_writer_basic():
    """Test enhanced spec writer with basic context."""
    writer = EnhancedSpecificationWriter()
    context = {
        "use_llm": False,  # Skip LLM to test deterministic path
        "feature_description": "Implement OAuth2 login flow",
    }
    result = writer.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "spec")
    assert "schema_version" in content
    assert "acceptance_criteria" in content
    assert "technical_specification" in content


def test_enhanced_specification_writer_with_dod():
    """Test spec writer with DoD artifact."""
    writer = EnhancedSpecificationWriter()
    context = {
        "use_llm": False,
        "dod_extractor": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "dod",
                    "content": {
                        "acceptance_criteria": ["Implement OAuth2 login", "Add session management"],
                    },
                }
            ],
        },
    }
    result = writer.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "spec")
    assert len(content["acceptance_criteria"]) >= 1


def test_enhanced_code_generator_basic():
    """Test enhanced code generator with basic context."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert "schema_version" in content
    assert "files" in content
    assert content["llm_enhanced"] is False


def test_enhanced_code_generator_with_spec():
    """Test code generator with spec artifact."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "specification_writer": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "spec",
                    "content": {
                        "summary": "API feature",
                        "file_changes": [
                            {
                                "path": "src/api.py",
                                "change_type": "create",
                                "description": "API module",
                            }
                        ],
                    },
                }
            ],
        },
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert len(content["files"]) > 0


def test_enhanced_code_generator_with_test_cases():
    """Test code generator includes test file when test cases exist."""
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "test_generator": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "tests",
                    "content": {
                        "test_cases": [
                            {"name": "test_success", "input": "x", "expected": "y"},
                            {"name": "test_failure", "input": "z", "expected": "w"},
                        ]
                    },
                }
            ],
        },
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    # Should have feature file + test file
    paths = [f["path"] for f in content["files"]]
    assert any("test" in p.lower() for p in paths)


def test_enhanced_code_generator_reads_rag_context_from_rag_initializer():
    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "rag_initializer": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "rag_context",
                    "content": {"sources": [{"path": "README.md"}]},
                }
            ],
        },
    }
    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert "rag_sources=1" in content["decisions"]


def test_enhanced_spec_name():
    """Test agent name and description."""
    writer = EnhancedSpecificationWriter()
    assert writer.name == "specification_writer"
    assert "spec" in writer.description.lower()


def test_enhanced_code_generator_name():
    """Test agent name and description."""
    generator = EnhancedCodeGenerator()
    assert generator.name == "code_generator"
    assert "code" in generator.description.lower()


def test_enhanced_code_generator_includes_issue_and_memory_context_in_llm_prompt(monkeypatch):
    captured = {"prompt": ""}

    class _FakeLlm:
        def complete(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"files":[{"path":"src/a.py","change_type":"modify","content":"print(1)"}],"decisions":[],"test_changes":[],"expected_failures":0}'

        def close(self) -> None:
            return

    monkeypatch.setattr("agents.code_generator.get_llm_wrapper", lambda: _FakeLlm())

    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": True,
        "issue": {
            "title": "Fix docker publish permissions",
            "body": "Build and push fails for ghcr publish",
            "comments_context": "Comment: denied create organization package",
        },
        "memory_context": {
            "query": "ghcr publish denied",
            "matches": [{"path": ".github/workflows/ci.yml", "summary": "build and push"}],
        },
        "specification_writer": {
            "status": "SUCCESS",
            "artifacts": [{"type": "spec", "content": {"summary": "Fix CI publish flow"}}],
        },
    }

    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    assert "Fix docker publish permissions" in captured["prompt"]
    assert "denied create organization package" in captured["prompt"]
    assert ".github/workflows/ci.yml" in captured["prompt"]


def test_enhanced_code_generator_creates_pr_with_token_and_repository(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeGitHubClient:
        def __init__(self, token: str, repo: str):
            captured["token"] = token
            captured["repo"] = repo

    class _FakeWorkflow:
        def __init__(self, github_client):
            captured["workflow_client"] = github_client

        def apply_patch(self, *, files, pr_title, pr_body, branch_name):
            captured["files"] = files
            captured["pr_title"] = pr_title
            captured["branch_name"] = branch_name
            from types import SimpleNamespace

            return SimpleNamespace(
                success=True,
                pr_url="https://github.com/acme/hordeforge/pull/77",
                pr_number=77,
                branch_name=branch_name,
                error=None,
                rollback_performed=False,
            )

    monkeypatch.setattr("agents.code_generator.GitHubClient", _FakeGitHubClient)
    monkeypatch.setattr("agents.code_generator.PatchWorkflowOrchestrator", _FakeWorkflow)

    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "github_token": "ghs_test",
        "repository": {"full_name": "acme/hordeforge"},
        "issue": {"number": 3, "title": "Fix CI push"},
        "specification_writer": {
            "status": "SUCCESS",
            "artifacts": [{"type": "spec", "content": {"summary": "Fix CI push issue"}}],
        },
    }

    result = generator.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["applied_to_github"] is True
    assert content["pr_number"] == 77
    assert str(content["branch_name"]).startswith("horde/3-")
    assert captured["repo"] == "acme/hordeforge"


def test_enhanced_code_generator_builds_pr_body_with_string_requirements(monkeypatch):
    class _FakeGitHubClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

    class _FakeWorkflow:
        def __init__(self, github_client):
            self.github_client = github_client

        def apply_patch(self, *, files, pr_title, pr_body, branch_name):
            from types import SimpleNamespace

            # Regression guard: PR body generation must not crash on string requirements.
            assert "rules/coding_rules.md" in pr_body
            return SimpleNamespace(
                success=True,
                pr_url="https://github.com/acme/hordeforge/pull/88",
                pr_number=88,
                branch_name=branch_name,
                error=None,
                rollback_performed=False,
            )

    monkeypatch.setattr("agents.code_generator.GitHubClient", _FakeGitHubClient)
    monkeypatch.setattr("agents.code_generator.PatchWorkflowOrchestrator", _FakeWorkflow)

    generator = EnhancedCodeGenerator()
    context = {
        "use_llm": False,
        "github_token": "ghs_test",
        "repository": {"full_name": "acme/hordeforge"},
        "issue": {"number": 9, "title": "Handle string requirements"},
        "specification_writer": {
            "status": "SUCCESS",
            "artifacts": [
                {
                    "type": "spec",
                    "content": {
                        "summary": "String requirements",
                        "requirements": ["rules/coding_rules.md", "rules/testing_rules.md"],
                    },
                }
            ],
        },
    }

    result = generator.run(context)
    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["pr_number"] == 88

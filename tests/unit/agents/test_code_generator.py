"""TDD: Test-Driven Development РґР»СЏ Code Generator Agent"""

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

        assert result["status"] == "SUCCESS", result
        assert "artifacts" in result
        assert len(result["artifacts"]) > 0
        artifact = result["artifacts"][0]
        assert artifact["type"] == "code_patch"
        assert "files" in artifact["content"]

    def test_run_handles_empty_feature(self):
        context = {"issue": {"title": "", "body": ""}}
        generator = CodeGenerator()

        result = generator.run(context)

        assert result["status"] == "SUCCESS", result

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

    def test_parse_llm_patch_response_accepts_required_files_request_payload(self):
        generator = CodeGenerator()
        response = (
            '{"files":[],"required_files":["orchestrator/pipeline_validator.py"],'
            '"decisions":[],"test_changes":[]}'
        )

        parsed = generator._parse_llm_patch_response(response)  # noqa: SLF001

        assert parsed is not None
        assert parsed["files"] == []
        assert parsed["required_files"] == ["orchestrator/pipeline_validator.py"]

    def test_extract_required_files_filters_unsafe_paths(self):
        generator = CodeGenerator()
        requested = generator._extract_required_files(  # noqa: SLF001
            {
                "required_files": [
                    "../secrets.env",
                    "/etc/passwd",
                    "orchestrator/loader.py",
                    {"path": "tests/unit/orchestrator/test_orchestrator_engine.py"},
                    {"path": "workspace/repo/orchestrator/summary.py"},
                ]
            }
        )

        assert "orchestrator/loader.py" in requested
        assert "tests/unit/orchestrator/test_orchestrator_engine.py" in requested
        assert "orchestrator/summary.py" in requested
        assert "../secrets.env" not in requested
        assert "/etc/passwd" not in requested

    def test_collect_candidate_files_from_ci_context(self):
        generator = CodeGenerator()
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

    def test_collect_candidate_files_inferrs_source_counterpart_from_test_path(self):
        generator = CodeGenerator()
        candidate_files = generator._collect_candidate_files(  # noqa: SLF001
            spec={},
            tests={},
            rag_context={},
            ci_failure_context={
                "files": ["workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py"],
                "test_targets": [],
            },
        )

        assert "tests/unit/orchestrator/test_orchestrator_engine.py" in candidate_files
        assert "orchestrator/engine.py" in candidate_files

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

    def test_filter_patch_files_allows_existing_non_candidate_when_new_files_disallowed(self):
        generator = CodeGenerator()
        files, notes = generator._filter_patch_files(  # noqa: SLF001
            [
                {"path": "src/feature_impl.py", "change_type": "modify", "content": "x"},
                {
                    "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                    "change_type": "modify",
                    "content": "y",
                },
            ],
            candidate_files=["tests/unit/orchestrator/test_orchestrator_engine.py"],
            allow_new_files=False,
            strict_target_files=False,
        )

        paths = [item["path"] for item in files]
        assert "tests/unit/orchestrator/test_orchestrator_engine.py" in paths
        assert "src/feature_impl.py" in paths
        assert any(
            "existing_non_candidate_file_allowed=src/feature_impl.py" in item for item in notes
        )

    def test_filter_patch_files_strict_target_files_rejects_non_candidate(self):
        generator = CodeGenerator()
        files, notes = generator._filter_patch_files(  # noqa: SLF001
            [
                {"path": "src/feature_impl.py", "change_type": "modify", "content": "x"},
                {
                    "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                    "change_type": "modify",
                    "content": "y",
                },
            ],
            candidate_files=["tests/unit/orchestrator/test_orchestrator_engine.py"],
            allow_new_files=False,
            strict_target_files=True,
        )

        assert len(files) == 1
        assert files[0]["path"] == "tests/unit/orchestrator/test_orchestrator_engine.py"
        assert any("filtered_non_candidate_file=src/feature_impl.py" in item for item in notes)

    def test_filter_patch_files_rejects_placeholder_content(self):
        generator = CodeGenerator()
        files, notes = generator._filter_patch_files(  # noqa: SLF001
            [
                {
                    "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                    "change_type": "modify",
                    "content": (
                        "# Placeholder content - actual file content would be provided "
                        "based on the failing test"
                    ),
                }
            ],
            candidate_files=["tests/unit/orchestrator/test_orchestrator_engine.py"],
            allow_new_files=False,
            strict_target_files=False,
        )

        assert files == []
        assert any(
            "filtered_placeholder_patch=tests/unit/orchestrator/test_orchestrator_engine.py" in item
            for item in notes
        )

    def test_load_candidate_file_snippets_reads_workspace_repo_file(self, tmp_path, monkeypatch):
        generator = CodeGenerator()
        fake_repo_root = tmp_path / "workspace" / "repo"
        target = fake_repo_root / "tests" / "unit" / "orchestrator" / "test_orchestrator_engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def test_sample() -> None:\n    assert True\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)

        snippets = generator._load_candidate_file_snippets(  # noqa: SLF001
            ["tests/unit/orchestrator/test_orchestrator_engine.py"]
        )

        assert len(snippets) == 1
        assert snippets[0]["path"] == "tests/unit/orchestrator/test_orchestrator_engine.py"
        assert "def test_sample() -> None" in snippets[0]["snippet"]

    def test_build_repo_context_includes_existing_file_contents(self):
        generator = CodeGenerator()

        repo_context = generator._build_repo_context(  # noqa: SLF001
            spec={"summary": "Fix CI", "file_changes": []},
            tests={},
            subtasks={},
            rag_context={},
            rules_payload={},
            ci_failure_context={"classification": "test_failure"},
            candidate_files=["orchestrator/engine.py"],
            allow_new_files=False,
            candidate_file_snippets=[
                {
                    "path": "orchestrator/engine.py",
                    "snippet": "class OrchestratorEngine:\n    pass\n",
                    "content": "class OrchestratorEngine:\n    def run(self) -> dict[str, object]:\n        return {}\n",
                    "truncated": False,
                }
            ],
            patch_strategy="patch_first",
            forced_strategy_mode="default",
            signature_discovery_packet={"ran": True, "symbols": []},
            semantic_feedback_packet={"violations": []},
            open_mode=True,
        )

        assert repo_context["existing_files"] == ["orchestrator/engine.py"]
        assert "orchestrator/engine.py" in repo_context["file_contents"]
        assert "def run(self)" in repo_context["file_contents"]["orchestrator/engine.py"]

    def test_append_compact_context_prefers_full_candidate_file_content(self):
        generator = CodeGenerator()

        prompt = generator._append_compact_context(  # noqa: SLF001
            prompt="base prompt",
            task_description="Fix CI",
            issue_context_text="",
            memory_context_text="",
            candidate_files=["orchestrator/engine.py"],
            allow_new_files=False,
            strict_target_files=False,
            candidate_file_snippets=[
                {
                    "path": "orchestrator/engine.py",
                    "snippet": "class OrchestratorEngine:\n    ...",
                    "content": (
                        "class OrchestratorEngine:\n"
                        "    def run(self) -> dict[str, object]:\n"
                        "        return {}\n"
                    ),
                    "truncated": False,
                }
            ],
            patch_strategy="patch_first",
            forced_strategy_mode="default",
            signature_discovery_packet={"ran": True, "symbols": []},
            semantic_feedback_packet={"violations": []},
            open_mode=True,
        )

        assert "## Candidate file content (real repository content)" in prompt
        assert "def run(self) -> dict[str, object]" in prompt

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
            strict_target_files=True,
        )

        assert patch["files"][0]["path"] == "orchestrator/loader.py"
        assert patch["allow_new_files"] is False
        assert patch["selected_target_files"][0]["path"] == "orchestrator/loader.py"

    def test_promotes_test_changes_into_patch_files_when_files_missing(self):
        generator = CodeGenerator()
        patch_files, notes = generator._materialize_patch_files(  # noqa: SLF001
            files=[],
            test_changes=[
                {
                    "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                    "change_type": "modify",
                    "content": "def test_ok() -> None:\n    assert True\n",
                }
            ],
            candidate_files=["tests/unit/orchestrator/test_orchestrator_engine.py"],
            allow_new_files=False,
            strict_target_files=True,
        )

        assert len(patch_files) == 1
        assert patch_files[0]["path"] == "tests/unit/orchestrator/test_orchestrator_engine.py"
        assert any("promoted_test_changes_to_files=1" in item for item in notes)

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
            strict_target_files=True,
        )

        assert patch["files"] == []
        assert patch["blocked"] is True

    def test_run_uses_ci_candidate_files_in_output(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
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
        assert patch["quality_gate"]["passed"] is True
        assert patch["loop_metrics"]["quality_gate_passed"] is True
        assert "instruction_stack" in patch
        assert "instruction_layers" in patch

    def test_run_uses_explicit_target_files_from_context(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "target_files": ["src/custom_module.py"],
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["files"][0]["path"] == "src/custom_module.py"
        assert patch["target_files"][0] == "src/custom_module.py"

    def test_run_fails_when_quality_gate_is_enforced_and_no_grounded_files(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "FAILED"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is False
        assert "no_files_in_patch" in patch["quality_gate"]["reasons"]

    def test_run_blocks_analysis_only_llm_patch_without_source_change(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                                "change_type": "modify",
                                "content": "def test_blocked() -> None:\n    assert True\n",
                            }
                        ],
                        "decisions": [
                            {
                                "description": "Analyze failing test first",
                                "rationale": "Need to examine source file before implementing fix.",
                            }
                        ],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 33, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py",
                                "workspace/repo/orchestrator/engine.py",
                            ],
                            "test_targets": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py::test_engine_feature_pipeline_completes_fix_loop_and_stabilizes_tests"
                            ],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "FAILED"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is False
        assert "analysis_only_without_source_change" in patch["quality_gate"]["reasons"]

    def test_run_blocks_test_only_patch_when_source_candidates_exist(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                                "change_type": "modify",
                                "content": "def test_only_change() -> None:\n    assert True\n",
                            }
                        ],
                        "decisions": ["Apply minimal change."],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 33, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py",
                                "workspace/repo/orchestrator/engine.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "FAILED"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is False
        assert "test_failure_without_source_change" in patch["quality_gate"]["reasons"]

    def test_run_blocks_patch_with_semantic_unknown_keyword_violation(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/engine.py",
                                "change_type": "modify",
                                "content": (
                                    "from orchestrator.loader import PipelineLoader\n\n"
                                    "def build_loader() -> PipelineLoader:\n"
                                    '    return PipelineLoader(pipelines_dir="pipelines", agent_registry={})\n'
                                ),
                            }
                        ],
                        "decisions": ["Apply source-level fix for loader wiring."],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "enforce_semantic_patch_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 57, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/orchestrator/engine.py",
                                "workspace/repo/orchestrator/loader.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "FAILED"
        patch = result["artifacts"][0]["content"]
        assert patch["semantic_gate"]["passed"] is False
        assert "semantic_contract_violation" in patch["quality_gate"]["reasons"]
        assert any("agent_registry" in item for item in patch["semantic_gate"]["violations"])
        assert "semantic_feedback_packet" in patch
        feedback = patch["semantic_feedback_packet"]["violations"][0]
        assert feedback["violation_type"] == "unknown_keyword_argument"
        assert feedback["symbol"] == "orchestrator.loader.PipelineLoader"
        assert "agent_registry" in feedback["invalid_kwargs"]
        assert "location" in feedback

    def test_run_allows_patch_when_semantic_gate_passes(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/engine.py",
                                "change_type": "modify",
                                "content": (
                                    "from orchestrator.loader import PipelineLoader\n\n"
                                    "def build_loader() -> PipelineLoader:\n"
                                    '    return PipelineLoader(pipelines_dir="pipelines")\n'
                                ),
                            }
                        ],
                        "decisions": ["Apply source-level fix for loader wiring."],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "enforce_semantic_patch_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 58, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/orchestrator/engine.py",
                                "workspace/repo/orchestrator/loader.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["semantic_gate"]["passed"] is True
        assert patch["semantic_gate"]["violations"] == []
        assert patch["signature_discovery"]["ran"] is True
        assert isinstance(patch["signature_discovery"]["symbols"], list)

    def test_run_allows_test_only_patch_with_explicit_justification(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                                "change_type": "modify",
                                "content": "def test_only_change() -> None:\n    assert True\n",
                            }
                        ],
                        "decisions": [
                            "test_only_change_justified: flaky assertion due to timing variance"
                        ],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 33, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py",
                                "workspace/repo/orchestrator/engine.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is True
        assert "test_failure_without_source_change" not in patch["quality_gate"]["reasons"]

    def test_run_quality_gate_shadow_mode_does_not_block_execution(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "quality_gate_mode": "shadow",
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is False
        assert patch["quality_gate"]["mode"] == "shadow"

    def test_run_open_mode_defaults_to_shadow_and_non_strict_scope(self):
        generator = CodeGenerator()
        context = {
            "use_llm": False,
            "publish_pr_in_code_generator": False,
            "open_mode": True,
            "enforce_patch_quality_gate": True,
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = generator.run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["open_mode"] is True
        assert patch["quality_gate"]["mode"] == "shadow"
        assert patch["loop_metrics"]["strict_target_files"] is False

    def test_run_semantic_gate_can_block_even_in_shadow_mode(self, monkeypatch):
        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/engine.py",
                                "change_type": "modify",
                                "content": (
                                    "from orchestrator.loader import PipelineLoader\n\n"
                                    "def build_loader() -> PipelineLoader:\n"
                                    "    return PipelineLoader(agent_registry={})\n"
                                ),
                            }
                        ],
                        "decisions": ["Apply source-level fix for loader wiring."],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "quality_gate_mode": "shadow",
            "enforce_semantic_patch_gate": True,
            "enforce_semantic_gate_blocking": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 59, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/orchestrator/engine.py",
                                "workspace/repo/orchestrator/loader.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "FAILED"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["mode"] == "shadow"
        assert patch["semantic_gate"]["passed"] is False
        assert patch["semantic_gate"]["mode"] == "enforce"

    def test_detects_unjustified_full_file_rewrite(self):
        generator = CodeGenerator()
        long_content = "\n".join("line" for _ in range(450))
        assert (
            generator._has_unjustified_full_rewrite(  # noqa: SLF001
                [
                    {
                        "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                        "content": long_content,
                    }
                ],
                [],
            )
            is True
        )
        assert (
            generator._has_unjustified_full_rewrite(  # noqa: SLF001
                [
                    {
                        "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                        "content": long_content,
                    }
                ],
                ["full_file_rewrite_approved"],
                allow_full_file_rewrite=False,
            )
            is True
        )
        assert (
            generator._has_unjustified_full_rewrite(  # noqa: SLF001
                [
                    {
                        "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                        "content": long_content,
                    }
                ],
                ["full_file_rewrite_approved"],
                allow_full_file_rewrite=True,
            )
            is False
        )

    def test_forced_plan_mode_activates_after_repeated_semantic_failures(self, monkeypatch):
        prompts: list[str] = []

        class _Wrapper:
            def complete(self, prompt: str, temperature=None):
                prompts.append(prompt)
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/engine.py",
                                "change_type": "modify",
                                "content": (
                                    "from orchestrator.loader import PipelineLoader\n\n"
                                    "def build_loader() -> PipelineLoader:\n"
                                    '    return PipelineLoader(pipelines_dir="pipelines", agent_registry={})\n'
                                ),
                            }
                        ],
                        "decisions": ["Apply source-level fix for loader wiring."],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "enforce_semantic_patch_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 77, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/orchestrator/engine.py",
                                "workspace/repo/orchestrator/loader.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        first = CodeGenerator().run(context)
        second = CodeGenerator().run(context)
        third = CodeGenerator().run(context)

        assert first["status"] == "FAILED"
        assert second["status"] == "FAILED"
        assert third["status"] == "FAILED"
        assert len(prompts) >= 3
        assert "Forced-plan mode" in prompts[1]
        assert "Forced-plan mode" in prompts[2]
        assert "Semantic feedback packet" in prompts[2]

    def test_build_signature_discovery_packet_collects_callable_signatures(self):
        generator = CodeGenerator()
        packet = generator._build_signature_discovery_packet(  # noqa: SLF001
            candidate_files=["orchestrator/engine.py", "orchestrator/loader.py"],
            candidate_file_snippets=[
                {
                    "path": "orchestrator/engine.py",
                    "snippet": (
                        "from orchestrator.loader import PipelineLoader\n\n"
                        "def build_loader() -> PipelineLoader:\n"
                        '    return PipelineLoader(pipelines_dir="pipelines")\n'
                    ),
                }
            ],
        )

        assert packet["ran"] is True
        assert any(
            item.get("symbol") == "orchestrator.loader.PipelineLoader"
            for item in packet.get("symbols", [])
        )

    def test_build_signature_discovery_falls_back_to_full_file_on_truncated_snippet(
        self, tmp_path, monkeypatch
    ):
        generator = CodeGenerator()
        target = tmp_path / "orchestrator" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        loader = tmp_path / "orchestrator" / "loader.py"
        target.write_text(
            (
                "from orchestrator.loader import PipelineLoader\n\n"
                "def build_loader() -> PipelineLoader:\n"
                '    return PipelineLoader(pipelines_dir="pipelines")\n'
            ),
            encoding="utf-8",
        )
        loader.write_text(
            (
                "class PipelineLoader:\n"
                '    def __init__(self, *, pipelines_dir: str = "pipelines"):\n'
                "        self.pipelines_dir = pipelines_dir\n"
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        packet = generator._build_signature_discovery_packet(  # noqa: SLF001
            candidate_files=["orchestrator/engine.py"],
            candidate_file_snippets=[
                {
                    "path": "orchestrator/engine.py",
                    "snippet": "from orchestrator.loader import PipelineLoader\n\n"
                    "def build_loader(",
                }
            ],
        )

        assert packet["ran"] is True
        assert any(
            item.get("symbol") == "orchestrator.loader.PipelineLoader"
            for item in packet.get("symbols", [])
        )

    def test_build_signature_discovery_packet_collects_local_public_methods(self):
        generator = CodeGenerator()
        packet = generator._build_signature_discovery_packet(  # noqa: SLF001
            candidate_files=["orchestrator/engine.py"],
            candidate_file_snippets=[
                {
                    "path": "orchestrator/engine.py",
                    "snippet": (
                        "class OrchestratorEngine:\n"
                        "    def run(\n"
                        "        self,\n"
                        "        pipeline_name: str,\n"
                        "        inputs: dict[str, object] | None = None,\n"
                        "        *,\n"
                        "        run_id: str,\n"
                        "        metadata: dict[str, object] | None = None,\n"
                        "    ) -> dict[str, object]:\n"
                        "        return {}\n"
                    ),
                }
            ],
        )

        assert packet["ran"] is True
        assert any(
            item.get("symbol") == "orchestrator.engine.OrchestratorEngine.run"
            for item in packet.get("symbols", [])
        )

    def test_semantic_gate_rejects_public_signature_keyword_removal(self, tmp_path, monkeypatch):
        generator = CodeGenerator()
        target = tmp_path / "orchestrator" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (
                "class OrchestratorEngine:\n"
                "    def run(\n"
                "        self,\n"
                "        pipeline_name: str,\n"
                "        inputs: dict[str, object] | None = None,\n"
                "        *,\n"
                "        run_id: str,\n"
                "        metadata: dict[str, object] | None = None,\n"
                "    ) -> dict[str, object]:\n"
                "        return {}\n"
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = generator._evaluate_semantic_patch_gate(  # noqa: SLF001
            [
                {
                    "path": "orchestrator/engine.py",
                    "change_type": "modify",
                    "content": (
                        "class OrchestratorEngine:\n"
                        "    def run(self, pipeline_name: str, context: dict[str, object]) -> dict[str, object]:\n"
                        "        return {}\n"
                    ),
                }
            ]
        )

        assert result["passed"] is False
        assert any(
            "public_signature_missing_keyword:orchestrator/engine.py:orchestrator.engine.OrchestratorEngine.run"
            in item
            for item in result["violations"]
        )

    def test_context_first_repair_retries_invalid_test_only_patch(self, monkeypatch):
        class _Wrapper:
            def __init__(self):
                self.calls = 0

            def complete(self, prompt: str):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps(
                        {
                            "files": [
                                {
                                    "path": "tests/unit/orchestrator/test_orchestrator_engine.py",
                                    "change_type": "modify",
                                    "content": "def test_only_change() -> None:\n    assert True\n",
                                }
                            ],
                            "decisions": ["Need to inspect source first"],
                            "test_changes": [],
                        }
                    )
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/engine.py",
                                "change_type": "modify",
                                "content": "from __future__ import annotations\n",
                            }
                        ],
                        "decisions": [
                            {
                                "description": "Apply grounded source fix",
                                "rationale": "Update source behavior for CI regression",
                            }
                        ],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        wrapper = _Wrapper()
        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: wrapper
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 33, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py",
                                "workspace/repo/orchestrator/engine.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["quality_gate"]["passed"] is True
        assert patch["files"][0]["path"] == "orchestrator/engine.py"
        assert wrapper.calls == 2

    def test_run_reprompts_when_llm_requests_additional_files(self, monkeypatch):
        class _Wrapper:
            def __init__(self):
                self.calls = 0

            def complete(self, prompt: str):
                self.calls += 1
                if self.calls == 1:
                    return json.dumps(
                        {
                            "files": [],
                            "required_files": ["orchestrator/pipeline_validator.py"],
                            "decisions": [
                                {
                                    "description": "Need dependency context",
                                    "rationale": "Request related module before patch generation",
                                }
                            ],
                            "test_changes": [],
                        }
                    )
                return json.dumps(
                    {
                        "files": [
                            {
                                "path": "orchestrator/pipeline_validator.py",
                                "change_type": "modify",
                                "content": "def validate() -> bool:\n    return True\n",
                            }
                        ],
                        "decisions": [
                            {
                                "description": "Patch with expanded context",
                                "rationale": "Applied targeted fix after loading requested file",
                            }
                        ],
                        "test_changes": [],
                    }
                )

            def close(self):
                return None

        wrapper = _Wrapper()
        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: wrapper
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "repository": {"full_name": "acme/hordeforge"},
            "issue": {"number": 39, "title": "CI fix"},
            "specification_writer": {
                "artifacts": [
                    {"type": "spec", "content": {"summary": "Fix CI", "file_changes": []}}
                ]
            },
            "ci_failure_analysis": {
                "artifacts": [
                    {
                        "type": "ci_failure_context",
                        "content": {
                            "classification": "test_failure",
                            "files": [
                                "workspace/repo/tests/unit/orchestrator/test_orchestrator_engine.py",
                            ],
                            "test_targets": [],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["files"][0]["path"] == "orchestrator/pipeline_validator.py"
        assert "orchestrator/pipeline_validator.py" in patch["target_files"]
        assert patch["llm_context_expansion"]["roundtrips"] == 1
        assert (
            "orchestrator/pipeline_validator.py"
            in patch["llm_context_expansion"]["requested_files"]
        )
        assert wrapper.calls == 2

    def test_run_materializes_edit_operations_into_files(self, monkeypatch, tmp_path):
        target = tmp_path / "orchestrator" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (
                "class OrchestratorEngine:\n"
                "    def run(self) -> dict[str, object]:\n"
                "        return {'status': 'old'}\n"
            ),
            encoding="utf-8",
        )

        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "operations": [
                            {
                                "type": "edit",
                                "path": "orchestrator/engine.py",
                                "old_string": "        return {'status': 'old'}\n",
                                "new_string": "        return {'status': 'new'}\n",
                            }
                        ],
                        "decisions": [
                            {
                                "description": "Use exact edit operation",
                                "rationale": "Preserve untouched file regions",
                            }
                        ],
                        "test_operations": [],
                    }
                )

            def close(self):
                return None

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "issue": {"number": 77, "title": "Fix runtime regression"},
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "Fix runtime regression",
                            "file_changes": [{"path": "orchestrator/engine.py"}],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["operations"][0]["type"] == "edit"
        assert patch["files"][0]["path"] == "orchestrator/engine.py"
        assert "status': 'new'" in patch["files"][0]["content"]
        assert patch["quality_gate"]["passed"] is True

    def test_run_materializes_patch_text_into_files(self, monkeypatch, tmp_path):
        target = tmp_path / "orchestrator" / "engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (
                "class OrchestratorEngine:\n"
                "    def run(self) -> dict[str, object]:\n"
                "        return {'status': 'old'}\n"
            ),
            encoding="utf-8",
        )

        class _Wrapper:
            def complete(self, prompt: str):
                return json.dumps(
                    {
                        "patch_text": (
                            "*** Begin Patch\n"
                            "*** Update File: orchestrator/engine.py\n"
                            "@@\n"
                            " class OrchestratorEngine:\n"
                            "     def run(self) -> dict[str, object]:\n"
                            "-        return {'status': 'old'}\n"
                            "+        return {'status': 'patched'}\n"
                            "*** End Patch\n"
                        ),
                        "decisions": [
                            {
                                "description": "Use patch-text mutation path",
                                "rationale": "Let runtime materialize the final file content",
                            }
                        ],
                    }
                )

            def close(self):
                return None

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            code_generator_module, "get_llm_wrapper", lambda *args, **kwargs: _Wrapper()
        )

        context = {
            "use_llm": True,
            "require_llm": True,
            "publish_pr_in_code_generator": False,
            "enforce_patch_quality_gate": True,
            "issue": {"number": 78, "title": "Fix runtime regression"},
            "specification_writer": {
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "summary": "Fix runtime regression",
                            "file_changes": [{"path": "orchestrator/engine.py"}],
                        },
                    }
                ]
            },
        }

        result = CodeGenerator().run(context)

        assert result["status"] == "SUCCESS"
        patch = result["artifacts"][0]["content"]
        assert patch["patch_text"].startswith("*** Begin Patch")
        assert patch["files"][0]["path"] == "orchestrator/engine.py"
        assert "status': 'patched'" in patch["files"][0]["content"]
        assert patch["quality_gate"]["passed"] is True

    def test_predict_quality_gate_reasons_marks_missing_content(self):
        generator = CodeGenerator()
        reasons = generator._predict_quality_gate_reasons(  # noqa: SLF001
            files=[],
            notes=["missing_content_for_file=orchestrator/engine.py"],
            decisions=[],
            ci_failure_context={"classification": "test_failure"},
            candidate_files=["orchestrator/engine.py"],
        )

        assert "missing_file_content" in reasons

    def test_predict_quality_gate_reasons_marks_invalid_operations(self):
        generator = CodeGenerator()
        reasons = generator._predict_quality_gate_reasons(  # noqa: SLF001
            files=[],
            notes=["operation_old_string_not_found:orchestrator/engine.py"],
            decisions=[],
            ci_failure_context={"classification": "test_failure"},
            candidate_files=["orchestrator/engine.py"],
        )

        assert "invalid_patch_operations" in reasons

from __future__ import annotations

from agents.issue_pipeline_dispatcher import IssuePipelineDispatcher


def _step_result(artifact_type: str, content: dict) -> dict:
    return {
        "status": "SUCCESS",
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def test_dispatcher_starts_feature_pipeline_for_classified_issue(monkeypatch):
    calls: list[dict] = []

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        calls.append(
            {
                "pipeline_name": pipeline_name,
                "inputs": inputs,
                "source": source,
                "idempotency_key": idempotency_key,
                "async_mode": async_mode,
            }
        )
        return {"status": "queued", "task_id": "task-1"}

    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {
            "status": "ok",
            "dod": {"acceptance_criteria": ["ac-1"]},
            "spec": {"summary": "spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: Test"},
            "tests": {"test_cases": [{"file_path": "tests/test_x.py"}]},
            "comment_posted": True,
        },
    )

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 101,
                        "number": 101,
                        "title": "Fix build",
                        "body": "Pipeline failed",
                        "labels": [{"name": "agent:opened"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 101, "number": 101, "title": "Fix build"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(calls) == 1
    assert calls[0]["pipeline_name"] == "feature_pipeline"
    assert calls[0]["inputs"]["issue"]["number"] == 101
    assert calls[0]["inputs"]["repository"]["full_name"] == "acme/hordeforge"
    assert calls[0]["source"] == "issue_scanner_dispatcher"
    assert calls[0]["async_mode"] is True
    assert calls[0]["inputs"]["tests"]["test_cases"][0]["file_path"] == "tests/test_x.py"


def test_dispatcher_fails_without_token():
    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 101, "number": 101, "title": "Fix build"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "FAILED"
    artifact = result["artifacts"][0]["content"]
    assert artifact["reason"] == "missing_github_token"


def test_dispatcher_resolves_token_from_secrets_case_insensitive_repo_key(monkeypatch):
    def fake_build_repo_token_ref(repo_id: str) -> str:
        return f"repo.{repo_id.replace('/', '_')}.github_token"

    def fake_list_secret_keys() -> list[str]:
        return ["repo.yxyxy_HordeForge.github_token"]

    def fake_get_secret_value(key: str) -> str | None:
        if key == "repo.yxyxy_HordeForge.github_token":
            return "ghs_from_secret"
        return None

    monkeypatch.setattr("cli.repo_store.build_repo_token_ref", fake_build_repo_token_ref)
    monkeypatch.setattr("cli.repo_store.list_secret_keys", fake_list_secret_keys)
    monkeypatch.setattr("cli.repo_store.get_secret_value", fake_get_secret_value)
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {
            "status": "ok",
            "dod": {"acceptance_criteria": []},
            "spec": {"summary": "spec"},
            "subtasks": {"items": []},
            "bdd_specification": {},
            "tests": {"test_cases": []},
            "comment_posted": False,
        },
    )
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_update_issue_stage_label",
        lambda self, **kwargs: True,
    )
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_enrich_issue_payload_with_comments",
        staticmethod(lambda **kwargs: kwargs["issue_payload"]),
    )

    captured_inputs: list[dict] = []

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        captured_inputs.append(inputs)
        return {"status": "queued", "task_id": "task-1"}

    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )

    context = {
        "repository": {"full_name": "yxyxy/hordeforge"},
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 3,
                        "number": 3,
                        "title": "Fix build",
                        "body": "Pipeline failed",
                        "labels": [{"name": "agent:opened"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 3, "number": 3, "title": "Fix build"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(captured_inputs) == 1
    assert captured_inputs[0]["github_token"] == "ghs_from_secret"


def test_dispatcher_reports_planning_failure(monkeypatch):
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {"status": "failed", "error": "dod_generation_failed"},
    )

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 101,
                        "number": 101,
                        "title": "Fix build",
                        "body": "Pipeline failed",
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 101, "number": 101, "title": "Fix build"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "PARTIAL_SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["dispatched_count"] == 0
    assert artifact["failed_count"] == 1
    assert artifact["failed"][0]["stage"] == "planning"


def test_post_planning_comment_updates_existing_marker_comment(monkeypatch):
    calls: dict[str, list] = {"create": [], "update": []}

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, *, per_page: int = 100):
            return [
                {"id": 10, "body": "regular comment"},
                {
                    "id": 77,
                    "body": "<!-- hordeforge:planning-update -->\nold planning",
                },
            ]

        def update_issue_comment(self, comment_id: int, comment: str):
            calls["update"].append((comment_id, comment))
            return {"id": comment_id}

        def comment_issue(self, issue_number: int, comment: str):
            calls["create"].append((issue_number, comment))
            return {"id": 999}

    monkeypatch.setattr(
        "agents.issue_pipeline_dispatcher.GitHubClient",
        _FakeClient,
    )

    ok = IssuePipelineDispatcher._post_planning_comment(
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        issue={"number": 123},
        dod={"acceptance_criteria": ["ac-1"]},
        bdd_specification={"gherkin_feature": "Feature: X"},
        tests={"test_cases": [{"file_path": "tests/test_x.py", "description": "desc"}]},
    )

    assert ok is True
    assert len(calls["update"]) == 1
    assert calls["update"][0][0] == 77
    assert len(calls["create"]) == 0


def test_build_idempotency_key_ignores_updated_at_noise():
    issue_payload_a = {
        "title": "Fix CI GHCR push",
        "body": "Detailed issue body",
        "labels": [{"name": "agent:ready"}],
        "updated_at": "2026-03-29T11:00:00Z",
    }
    issue_payload_b = {
        "title": "Fix CI GHCR push",
        "body": "Detailed issue body",
        "labels": [{"name": "agent:ready"}],
        "updated_at": "2026-03-29T12:00:00Z",
    }

    key_a = IssuePipelineDispatcher._build_idempotency_key(
        repository_full_name="acme/hordeforge",
        issue_number=123,
        issue_payload=issue_payload_a,
    )
    key_b = IssuePipelineDispatcher._build_idempotency_key(
        repository_full_name="acme/hordeforge",
        issue_number=123,
        issue_payload=issue_payload_b,
    )

    assert key_a == key_b


def test_dispatcher_enriches_issue_with_comments_before_dispatch(monkeypatch):
    calls: list[dict] = []

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, per_page: int = 50):
            assert issue_number == 11
            return [
                {"id": 1, "body": "first diagnostic note"},
                {"id": 2, "body": "second diagnostic note"},
            ]

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        calls.append({"pipeline_name": pipeline_name, "inputs": inputs})
        return {"status": "started", "run_id": "default:r-2"}

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {
            "status": "ok",
            "dod": {"acceptance_criteria": []},
            "spec": {"summary": "spec"},
            "subtasks": {"items": []},
            "bdd_specification": {},
            "tests": {"test_cases": []},
            "comment_posted": False,
        },
    )
    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 11,
                        "number": 11,
                        "title": "Investigate CI failure",
                        "body": "Base description",
                        "labels": [{"name": "agent:ready"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 11, "number": 11, "title": "Investigate CI failure"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(calls) == 1
    dispatched_issue = calls[0]["inputs"]["issue"]
    assert len(dispatched_issue["comments"]) == 2
    assert "first diagnostic note" in dispatched_issue["comments_context"]


def test_dispatcher_updates_issue_stage_labels(monkeypatch):
    label_calls: list[tuple[int, list[str]]] = []

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, per_page: int = 50):
            return []

        def update_issue_labels(self, issue_number: int, labels: list[str]):
            label_calls.append((issue_number, labels))
            return {"number": issue_number, "labels": labels}

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        return {"status": "queued", "task_id": "task-42"}

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {
            "status": "ok",
            "dod": {"acceptance_criteria": []},
            "spec": {"summary": "spec"},
            "subtasks": {"items": []},
            "bdd_specification": {},
            "tests": {"test_cases": []},
            "comment_posted": False,
        },
    )

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 11,
                        "number": 11,
                        "title": "Investigate CI failure",
                        "body": "Base description",
                        "labels": [
                            {"name": "agent:opened"},
                            {"name": "kind:ci-incident"},
                        ],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 11, "number": 11, "title": "Investigate CI failure"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(label_calls) == 2
    assert label_calls[0][0] == 11
    assert "agent:planning" in label_calls[0][1]
    assert "agent:ready" in label_calls[1][1]


def test_dispatcher_skips_planning_for_agent_ready_issue(monkeypatch):
    calls: list[dict] = []

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        calls.append({"pipeline_name": pipeline_name, "inputs": inputs})
        return {"status": "queued", "task_id": "task-99"}

    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )

    def fail_if_called(self, **kwargs):
        raise AssertionError("planning must be skipped")

    monkeypatch.setattr(IssuePipelineDispatcher, "_build_issue_plan", fail_if_called)

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 44,
                        "number": 44,
                        "title": "Resume generation",
                        "body": "Resume from ready stage",
                        "labels": [{"name": "agent:ready"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 44, "number": 44, "title": "Resume generation"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(calls) == 1
    artifact = result["artifacts"][0]["content"]
    assert artifact["dispatched_count"] == 1
    assert artifact["dispatched"][0]["started_from_ready"] is True
    assert artifact["dispatched"][0]["planning_comment_posted"] is False


def test_dispatcher_closes_fixed_issue_with_related_merged_pr(monkeypatch):
    closed_issues: list[int] = []

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def list_pull_requests(self, state: str = "closed", page: int = 1, per_page: int = 100):
            return [
                {
                    "number": 77,
                    "state": "closed",
                    "merged": True,
                    "title": "Fix ci",
                    "body": "Closes #55",
                    "head": {"ref": "horde/55-fix-ci"},
                }
            ]

        def close_issue(self, issue_number: int):
            closed_issues.append(issue_number)
            return {"number": issue_number, "state": "closed"}

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 55,
                        "number": 55,
                        "title": "Incident resolved",
                        "body": "PR created",
                        "labels": [{"name": "agent:fixed"}],
                        "state": "open",
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 55, "number": 55, "title": "Incident resolved"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["fixed_processed_count"] == 1
    assert artifact["fixed_processed"][0]["closed"] is True
    assert artifact["fixed_processed"][0]["pr_number"] == 77
    assert closed_issues == [55]


def test_dispatcher_does_not_fail_when_fixed_issue_has_no_merged_pr(monkeypatch):
    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def list_pull_requests(self, state: str = "closed", page: int = 1, per_page: int = 100):
            return []

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 56,
                        "number": 56,
                        "title": "Incident maybe resolved",
                        "body": "Waiting for merge",
                        "labels": [{"name": "agent:fixed"}],
                        "state": "open",
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 56, "number": 56, "title": "Incident maybe resolved"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["fixed_processed_count"] == 1
    assert artifact["failed_count"] == 0
    assert artifact["fixed_processed"][0]["closed"] is False
    assert artifact["fixed_processed"][0]["reason"] == "related_merged_pr_not_found"


def test_build_issue_plan_disables_strict_llm_for_tests_step(monkeypatch):
    class _FakeDodExtractor:
        def run(self, context):
            return _step_result("dod", {"acceptance_criteria": ["ac-1"]})

    class _FakeSpecificationWriter:
        def run(self, context):
            return _step_result("spec", {"summary": "spec"})

    class _FakeTaskDecomposer:
        def run(self, context):
            return _step_result("subtasks", {"items": [{"id": "S1"}]})

    class _FakeBDDGenerator:
        def run(self, context):
            return _step_result("bdd_specification", {"gherkin_feature": "Feature: X"})

    class _FakeTestGenerator:
        def run(self, context):
            if bool(context.get("require_llm")):
                return {"status": "FAILED", "artifacts": []}
            return _step_result("tests", {"test_cases": [{"file_path": "tests/test_x.py"}]})

    monkeypatch.setattr("agents.dod_extractor.DodExtractor", _FakeDodExtractor)
    monkeypatch.setattr("agents.specification_writer.SpecificationWriter", _FakeSpecificationWriter)
    monkeypatch.setattr("agents.task_decomposer.TaskDecomposer", _FakeTaskDecomposer)
    monkeypatch.setattr("agents.bdd_generator.BDDGenerator", _FakeBDDGenerator)
    monkeypatch.setattr("agents.test_generator.TestGenerator", _FakeTestGenerator)
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_post_planning_comment",
        staticmethod(lambda **kwargs: True),
    )

    result = IssuePipelineDispatcher()._build_issue_plan(  # noqa: SLF001
        issue={"number": 23, "title": "Test"},
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        use_llm=True,
        require_llm=True,
        mock_mode=False,
        rules=None,
    )

    assert result["status"] == "ok"
    assert isinstance(result["tests"], dict)
    assert len(result["tests"].get("test_cases", [])) == 1

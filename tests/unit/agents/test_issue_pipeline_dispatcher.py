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
        "target_pipeline": "feature_pipeline",
        "ci_incident_pipeline": "ci_fix_pipeline",
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
            {
                "classified_issues": [
                    {
                        "id": 101,
                        "number": 101,
                        "title": "Fix build",
                        "labels": ["agent:opened"],
                    }
                ]
            },
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


def test_dispatcher_starts_ci_fix_pipeline_for_ci_incident_issue(monkeypatch):
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
        return {"status": "queued", "task_id": "task-ci-1"}

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
            "spec": {"summary": "ci incident spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: Repair failing CI"},
            "tests": {"test_cases": [{"file_path": "tests/test_ci_repair.py"}]},
            "comment_posted": True,
        },
    )

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "target_pipeline": "feature_pipeline",
        "ci_incident_pipeline": "ci_fix_pipeline",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 202,
                        "number": 202,
                        "title": "CI incident: failed unit tests",
                        "body": "Pipeline failed in unit tests",
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
            {
                "classified_issues": [
                    {
                        "id": 202,
                        "number": 202,
                        "title": "CI incident: failed unit tests",
                        "labels": ["agent:opened", "kind:ci-incident"],
                    }
                ]
            },
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(calls) == 1
    assert calls[0]["pipeline_name"] == "ci_fix_pipeline"
    assert calls[0]["inputs"]["issue"]["number"] == 202
    assert calls[0]["inputs"]["repository"]["full_name"] == "acme/hordeforge"
    assert calls[0]["source"] == "issue_scanner_dispatcher"
    assert calls[0]["async_mode"] is True
    assert calls[0]["inputs"]["ci_mode"] is True
    assert calls[0]["inputs"]["planning_scope"] == "ci_incident"

    artifact = result["artifacts"][0]["content"]
    assert artifact["dispatched_count"] == 1
    assert artifact["dispatched"][0]["pipeline"] == "ci_fix_pipeline"


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
            "dod": {"acceptance_criteria": ["ac-1"]},
            "spec": {"summary": "spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: X"},
            "tests": {"test_cases": [{"name": "t"}]},
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
        lambda self, **kwargs: {
            "status": "failed",
            "error": "dod_generation_failed",
            "error_details": {"phase": "dod", "reason": "missing_input"},
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
    assert artifact["failed"][0]["error_details"]["phase"] == "dod"


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
        spec={"summary": "spec"},
        subtasks={"items": [{"id": "S1"}]},
        bdd_specification={"gherkin_feature": "Feature: X"},
        tests={"test_cases": [{"file_path": "tests/test_x.py", "description": "desc"}]},
    )

    assert ok is True
    assert len(calls["update"]) == 1
    assert calls["update"][0][0] == 77
    assert len(calls["create"]) == 0
    updated_body = calls["update"][0][1]
    assert IssuePipelineDispatcher.PLAN_JSON_START in updated_body
    assert IssuePipelineDispatcher.PLAN_JSON_END in updated_body


def test_post_planning_comment_backward_compatible_without_spec_and_subtasks(monkeypatch):
    calls: dict[str, list] = {"create": [], "update": []}

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, *, per_page: int = 100):
            return []

        def update_issue_comment(self, comment_id: int, comment: str):
            calls["update"].append((comment_id, comment))
            return {"id": comment_id}

        def comment_issue(self, issue_number: int, comment: str):
            calls["create"].append((issue_number, comment))
            return {"id": 999}

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)

    ok = IssuePipelineDispatcher._post_planning_comment(
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        issue={"number": 321},
        dod={"acceptance_criteria": ["ac-1"]},
        bdd_specification={"gherkin_feature": "Feature: X"},
        tests={"test_cases": [{"file_path": "tests/test_x.py", "description": "desc"}]},
    )

    assert ok is True
    assert len(calls["create"]) == 1
    body = calls["create"][0][1]
    assert IssuePipelineDispatcher.PLAN_JSON_START in body
    assert IssuePipelineDispatcher.PLAN_JSON_END in body


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
            "dod": {"acceptance_criteria": ["ac-1"]},
            "spec": {"summary": "spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: X"},
            "tests": {"test_cases": [{"name": "t"}]},
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
                        "labels": [{"name": "agent:opened"}],
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
            "dod": {"acceptance_criteria": ["ac-1"]},
            "spec": {"summary": "spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: X"},
            "tests": {"test_cases": [{"name": "t"}]},
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


def test_dispatcher_uses_plan_from_issue_for_agent_ready_issue(monkeypatch):
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
        raise AssertionError("planning rebuild must not happen when plan exists in issue")

    monkeypatch.setattr(IssuePipelineDispatcher, "_build_issue_plan", fail_if_called)

    comment_body = IssuePipelineDispatcher._build_planning_comment_body(
        acceptance_criteria=["A"],
        gherkin_feature="Feature: Resume generation",
        test_cases=[{"file_path": "tests/test_resume.py", "description": "resume test"}],
        plan_payload={
            "dod": {"acceptance_criteria": ["A"]},
            "spec": {"summary": "Loaded from issue"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: Resume generation"},
            "tests": {"test_cases": [{"file_path": "tests/test_resume.py"}]},
        },
    )

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, per_page: int = 50):
            return [{"id": 77, "body": comment_body}]

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)

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
    assert artifact["dispatched"][0]["plan_source"] == "issue"
    assert calls[0]["inputs"]["spec"]["summary"] == "Loaded from issue"


def test_dispatcher_rebuilds_plan_for_agent_ready_issue_when_legacy_comment_only(monkeypatch):
    calls: list[dict] = []
    build_calls: list[dict] = []

    def fake_dispatch_pipeline(*, pipeline_name, inputs, source, idempotency_key, async_mode):
        calls.append({"pipeline_name": pipeline_name, "inputs": inputs})
        return {"status": "queued", "task_id": "task-100"}

    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fake_dispatch_pipeline),
    )

    def fake_build_issue_plan(self, **kwargs):
        build_calls.append(kwargs)
        return {
            "status": "ok",
            "dod": {"acceptance_criteria": ["rebuilt"]},
            "spec": {"summary": "rebuilt spec"},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: rebuilt"},
            "tests": {"test_cases": [{"name": "test_rebuilt"}]},
            "comment_posted": True,
        }

    monkeypatch.setattr(IssuePipelineDispatcher, "_build_issue_plan", fake_build_issue_plan)

    legacy_body = "\n".join(
        [
            IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
            "## HordeForge Planning Update",
            "",
            "### DoD (Acceptance Criteria)",
            "- Old human-readable comment",
        ]
    )

    class _FakeClient:
        def __init__(self, token: str, repo: str):
            self.token = token
            self.repo = repo

        def get_issue_comments(self, issue_number: int, per_page: int = 50):
            return [{"id": 78, "body": legacy_body}]

    monkeypatch.setattr("agents.issue_pipeline_dispatcher.GitHubClient", _FakeClient)

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 45,
                        "number": 45,
                        "title": "Resume generation from legacy comment",
                        "body": "Resume from ready stage",
                        "labels": [{"name": "agent:ready"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {
                "classified_issues": [
                    {"id": 45, "number": 45, "title": "Resume generation from legacy comment"}
                ]
            },
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "SUCCESS"
    assert len(build_calls) == 1
    assert len(calls) == 1
    artifact = result["artifacts"][0]["content"]
    assert artifact["dispatched"][0]["started_from_ready"] is True
    assert artifact["dispatched"][0]["plan_source"] == "regenerated"
    assert artifact["dispatched"][0]["rebuilt_plan"] is True
    assert calls[0]["inputs"]["spec"]["summary"] == "rebuilt spec"


def test_dispatcher_blocks_dispatch_when_plan_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_build_issue_plan",
        lambda self, **kwargs: {
            "status": "ok",
            "dod": {"acceptance_criteria": ["A"]},
            "spec": {},
            "subtasks": {"items": [{"id": "S1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: X"},
            "tests": {"test_cases": [{"name": "t"}]},
            "comment_posted": False,
        },
    )

    def fail_dispatch(**kwargs):
        raise AssertionError("dispatch must not be called with incomplete plan")

    monkeypatch.setattr(
        IssuePipelineDispatcher,
        "_dispatch_pipeline",
        staticmethod(fail_dispatch),
    )

    context = {
        "repository": {"full_name": "acme/hordeforge"},
        "github_token": "ghs_test",
        "repo_connector": _step_result(
            "repository_data",
            {
                "issues": [
                    {
                        "id": 46,
                        "number": 46,
                        "title": "Incomplete plan issue",
                        "body": "Should fail precheck",
                        "labels": [{"name": "agent:opened"}],
                    }
                ]
            },
        ),
        "issue_classification": _step_result(
            "issue_scan",
            {"classified_issues": [{"id": 46, "number": 46, "title": "Incomplete plan issue"}]},
        ),
    }

    result = IssuePipelineDispatcher().run(context)

    assert result["status"] == "PARTIAL_SUCCESS"
    artifact = result["artifacts"][0]["content"]
    assert artifact["dispatched_count"] == 0
    assert artifact["failed_count"] == 1
    assert artifact["failed"][0]["stage"] == "dispatch_precheck"
    assert "missing_plan_artifacts:spec" in artifact["failed"][0]["error"]


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


def test_build_issue_plan_retries_spec_with_relaxed_llm(monkeypatch):
    class _FakeDodExtractor:
        def run(self, context):
            return _step_result("dod", {"acceptance_criteria": ["ac-1"]})

    class _FakeSpecificationWriter:
        calls = 0

        def run(self, context):
            _FakeSpecificationWriter.calls += 1
            if bool(context.get("require_llm")):
                return {
                    "status": "FAILED",
                    "artifacts": [
                        {
                            "type": "spec",
                            "content": {
                                "llm_required": True,
                                "llm_error": "Qwen Code API call failed: timeout after 30s",
                            },
                        }
                    ],
                }
            return _step_result("spec", {"summary": "spec"})

    class _FakeTaskDecomposer:
        def run(self, context):
            return _step_result("subtasks", {"items": [{"id": "S1"}]})

    class _FakeBDDGenerator:
        def run(self, context):
            return _step_result("bdd_specification", {"gherkin_feature": "Feature: X"})

    class _FakeTestGenerator:
        def run(self, context):
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
        issue={"number": 28, "title": "CI incident"},
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        use_llm=True,
        require_llm=True,
        mock_mode=False,
        rules=None,
    )

    assert result["status"] == "ok"
    assert _FakeSpecificationWriter.calls == 2
    assert result["spec"]["summary"] == "spec"


def test_build_issue_plan_does_not_retry_spec_on_non_transient_failure(monkeypatch):
    class _FakeDodExtractor:
        def run(self, context):
            return _step_result("dod", {"acceptance_criteria": ["ac-1"]})

    class _FakeSpecificationWriter:
        calls = 0

        def run(self, context):
            _FakeSpecificationWriter.calls += 1
            return {
                "status": "FAILED",
                "artifacts": [
                    {
                        "type": "spec",
                        "content": {
                            "llm_required": True,
                            "llm_error": "missing_or_invalid_spec_output",
                        },
                    }
                ],
                "logs": ["LLM error: missing_or_invalid_spec_output"],
            }

    monkeypatch.setattr("agents.dod_extractor.DodExtractor", _FakeDodExtractor)
    monkeypatch.setattr("agents.specification_writer.SpecificationWriter", _FakeSpecificationWriter)

    result = IssuePipelineDispatcher()._build_issue_plan(  # noqa: SLF001
        issue={"number": 28, "title": "CI incident"},
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        use_llm=True,
        require_llm=True,
        mock_mode=False,
        rules=None,
    )

    assert result["status"] == "failed"
    assert result["error"] == "spec_step_failed"
    assert _FakeSpecificationWriter.calls == 1
    assert result["error_details"]["fallback_allowed"] is False
    assert result["error_details"]["fallback_attempted"] is False


def test_build_planning_comment_body_keeps_human_readable_and_embeds_json():
    body = IssuePipelineDispatcher._build_planning_comment_body(
        acceptance_criteria=["A", "B"],
        gherkin_feature="Feature: Example",
        test_cases=[{"file_path": "tests/test_x.py", "description": "Example test"}],
        plan_payload={
            "dod": {"acceptance_criteria": ["A", "B"]},
            "spec": {"summary": "Spec summary"},
            "subtasks": {"items": [{"id": "1"}]},
            "bdd_specification": {"gherkin_feature": "Feature: Example"},
            "tests": {"test_cases": [{"name": "test_x"}]},
        },
    )

    assert IssuePipelineDispatcher.PLANNING_COMMENT_MARKER in body
    assert "## HordeForge Planning Update" in body
    assert "### DoD (Acceptance Criteria)" in body
    assert "### BDD Scenarios" in body
    assert "### TDD Test Plan" in body
    assert IssuePipelineDispatcher.PLAN_JSON_START in body
    assert IssuePipelineDispatcher.PLAN_JSON_END in body


def test_extract_plan_json_from_comment_returns_payload():
    body = "\n".join(
        [
            IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
            "## HordeForge Planning Update",
            "",
            IssuePipelineDispatcher.PLAN_JSON_START,
            '{"dod":{"acceptance_criteria":["A"]},"spec":{"summary":"S"},"subtasks":{"items":[{"id":"1"}]},"bdd_specification":{"gherkin_feature":"Feature: A"},"tests":{"test_cases":[{"name":"t"}]}}',
            IssuePipelineDispatcher.PLAN_JSON_END,
        ]
    )

    payload = IssuePipelineDispatcher._extract_plan_json_from_comment(body)

    assert isinstance(payload, dict)
    assert payload["dod"]["acceptance_criteria"] == ["A"]
    assert payload["spec"]["summary"] == "S"


def test_extract_plan_json_from_comment_returns_none_for_legacy_comment():
    body = "\n".join(
        [
            IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
            "## HordeForge Planning Update",
            "",
            "### DoD (Acceptance Criteria)",
            "- Human readable only",
        ]
    )

    payload = IssuePipelineDispatcher._extract_plan_json_from_comment(body)
    assert payload is None


def test_load_plan_from_issue_returns_plan_for_new_comment():
    issue_payload = {
        "comments": [
            {
                "id": 1,
                "body": "\n".join(
                    [
                        IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
                        "## HordeForge Planning Update",
                        IssuePipelineDispatcher.PLAN_JSON_START,
                        '{"dod":{"acceptance_criteria":["A"]},"spec":{"summary":"S"},"subtasks":{"items":[{"id":"1"}]},"bdd_specification":{"gherkin_feature":"Feature: A"},"tests":{"test_cases":[{"name":"t"}]}}',
                        IssuePipelineDispatcher.PLAN_JSON_END,
                    ]
                ),
            }
        ]
    }

    plan = IssuePipelineDispatcher._load_plan_from_issue(issue_payload)

    assert plan["status"] == "ok"
    assert plan["dod"]["acceptance_criteria"] == ["A"]
    assert plan["spec"]["summary"] == "S"
    assert plan["comment_posted"] is True


def test_load_plan_from_issue_fails_for_legacy_comment_without_json():
    issue_payload = {
        "comments": [
            {
                "id": 1,
                "body": "\n".join(
                    [
                        IssuePipelineDispatcher.PLANNING_COMMENT_MARKER,
                        "## HordeForge Planning Update",
                        "",
                        "### DoD (Acceptance Criteria)",
                        "- Human readable only",
                    ]
                ),
            }
        ]
    }

    plan = IssuePipelineDispatcher._load_plan_from_issue(issue_payload)

    assert plan["status"] == "failed"
    assert plan["error"] == "plan_json_missing_or_invalid"


def test_missing_plan_keys_detects_empty_dicts():
    plan_bundle = {
        "status": "ok",
        "dod": {},
        "spec": {"summary": "x"},
        "subtasks": {},
        "bdd_specification": {"gherkin_feature": "Feature: X"},
        "tests": {"test_cases": [{"name": "t"}]},
    }

    missing = IssuePipelineDispatcher._missing_plan_keys(plan_bundle)

    assert "dod" in missing
    assert "subtasks" in missing
    assert "spec" not in missing
    assert "tests" not in missing


def test_plan_bundle_is_complete_true_for_filled_bundle():
    plan_bundle = {
        "status": "ok",
        "dod": {"acceptance_criteria": ["A"]},
        "spec": {"summary": "Spec"},
        "subtasks": {"items": [{"id": "1"}]},
        "bdd_specification": {"gherkin_feature": "Feature: X"},
        "tests": {"test_cases": [{"name": "t"}]},
    }

    assert IssuePipelineDispatcher._plan_bundle_is_complete(plan_bundle) is True


def test_plan_bundle_is_complete_false_for_partial_bundle():
    plan_bundle = {
        "status": "ok",
        "dod": {"acceptance_criteria": ["A"]},
        "spec": {},
        "subtasks": {"items": [{"id": "1"}]},
        "bdd_specification": {"gherkin_feature": "Feature: X"},
        "tests": {"test_cases": [{"name": "t"}]},
    }

    assert IssuePipelineDispatcher._plan_bundle_is_complete(plan_bundle) is False


def test_build_issue_plan_passes_ci_mode_to_steps(monkeypatch):
    seen_contexts: list[dict] = []

    class _FakeDodExtractor:
        def run(self, context):
            seen_contexts.append(dict(context))
            return _step_result("dod", {"acceptance_criteria": ["ac-1"]})

    class _FakeSpecificationWriter:
        def run(self, context):
            seen_contexts.append(dict(context))
            return _step_result(
                "spec",
                {
                    "summary": "ci spec",
                    "acceptance_criteria": [
                        "Unit pytest failures are reproducible and fixed",
                        "UI renders correctly across supported browsers",
                    ],
                },
            )

    class _FakeTaskDecomposer:
        def run(self, context):
            seen_contexts.append(dict(context))
            return _step_result("subtasks", {"items": [{"id": "S1"}]})

    class _FakeBDDGenerator:
        def run(self, context):
            seen_contexts.append(dict(context))
            return _step_result(
                "bdd_specification",
                {
                    "gherkin_feature": (
                        "Feature: Repair CI\n"
                        "  Scenario: fix unit tests\n"
                        "  Scenario: UI is responsive across browsers"
                    )
                },
            )

    class _FakeTestGenerator:
        def run(self, context):
            seen_contexts.append(dict(context))
            return _step_result(
                "tests",
                {
                    "test_cases": [
                        {"file_path": "tests/test_ci.py", "description": "CI test"},
                        {"file_path": "tests/test_ui.py", "description": "UI browser test"},
                    ]
                },
            )

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
        issue={"number": 202, "title": "CI incident"},
        repository_full_name="acme/hordeforge",
        token="ghs_test",
        use_llm=True,
        require_llm=True,
        mock_mode=False,
        rules=None,
        ci_mode=True,
    )

    assert result["status"] == "ok"
    assert all(ctx.get("ci_mode") is True for ctx in seen_contexts)
    assert (
        "UI renders correctly across supported browsers"
        not in result["spec"]["acceptance_criteria"]
    )
    assert "browser" not in result["bdd_specification"]["gherkin_feature"].lower()
    descriptions = [str(x.get("description", "")).lower() for x in result["tests"]["test_cases"]]
    assert all("browser" not in item for item in descriptions)

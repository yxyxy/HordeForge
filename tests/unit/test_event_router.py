from __future__ import annotations

from api.event_router import route_github_event


def test_route_github_event_maps_issues_to_feature_pipeline():
    payload = {
        "action": "opened",
        "issue": {"id": 1, "title": "Implement feature"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    decision = route_github_event("issues", payload)

    assert decision.ignored is False
    assert decision.pipeline_name == "feature_pipeline"
    assert decision.inputs["issue"]["id"] == 1


def test_route_github_event_maps_failed_workflow_run_to_ci_fix_pipeline():
    payload = {
        "workflow_run": {"id": 99, "status": "completed", "conclusion": "failure"},
        "repository": {"full_name": "acme/hordeforge"},
    }

    decision = route_github_event("workflow_run", payload)

    assert decision.ignored is False
    assert decision.pipeline_name == "ci_fix_pipeline"
    assert decision.inputs["ci_run"]["id"] == 99


def test_route_github_event_ignores_unsupported_events():
    decision = route_github_event("ping", {"zen": "keep it logically awesome"})

    assert decision.ignored is True
    assert decision.pipeline_name is None
    assert decision.reason.startswith("unsupported_event_type")

from __future__ import annotations

import pytest

from orchestrator.loader import StepDefinition
from orchestrator.parallel import build_step_dependency_graph, select_lock_aware_batch


def test_build_step_dependency_graph_resolves_input_output_references():
    steps = [
        StepDefinition(name="step_a", agent="repo_connector", output_mapping="{{artifact_a}}"),
        StepDefinition(
            name="step_b",
            agent="rag_initializer",
            input_mapping={"artifact": "{{artifact_a}}"},
        ),
        StepDefinition(
            name="step_c",
            agent="memory_agent",
            depends_on=["step_b"],
        ),
    ]

    graph = build_step_dependency_graph(steps)

    assert graph["step_a"] == set()
    assert graph["step_b"] == {"step_a"}
    assert graph["step_c"] == {"step_b"}


def test_build_step_dependency_graph_rejects_ambiguous_alias():
    steps = [
        StepDefinition(name="step_a", agent="repo_connector", output_mapping="{{artifact}}"),
        StepDefinition(name="step_b", agent="rag_initializer", output_mapping="{{artifact}}"),
    ]

    with pytest.raises(ValueError, match="Ambiguous output alias"):
        build_step_dependency_graph(steps)


def test_select_lock_aware_batch_skips_conflicting_steps():
    ready = [
        StepDefinition(name="step_a", agent="a", resource_locks=["repo"]),
        StepDefinition(name="step_b", agent="b", resource_locks=["repo"]),
        StepDefinition(name="step_c", agent="c", resource_locks=["docs"]),
    ]

    batch = select_lock_aware_batch(ready)

    assert [item.name for item in batch] == ["step_a", "step_c"]


def test_build_step_dependency_graph_allows_external_completed_dependencies():
    steps = [
        StepDefinition(
            name="review_agent",
            agent="review_agent",
            depends_on=["test_runner", "fix_agent"],
            depends_on_explicit=True,
        )
    ]

    graph = build_step_dependency_graph(
        steps,
        externally_satisfied_dependencies={"test_runner", "fix_agent"},
    )

    assert graph["review_agent"] == set()

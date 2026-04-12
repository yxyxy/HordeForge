from __future__ import annotations

import agents.code_generator as code_generator_module
import agents.fix_agent as fix_agent_module
from agents.fix_agent import FixAgent


def _step_result(status: str, artifact_type: str, content: dict) -> dict:
    return {
        "status": status,
        "artifacts": [{"type": artifact_type, "content": content}],
        "decisions": [],
        "logs": [],
        "next_actions": [],
    }


def _get_content(result: dict, artifact_type: str) -> dict:
    """Extract content from agent result."""
    for artifact in result.get("artifacts", []):
        if artifact.get("type") == artifact_type:
            return artifact.get("content", {})
    return {}


def test_fix_agent_no_failures():
    """Test fix agent when no tests are failing."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "SUCCESS",
            "test_results",
            {"total": 5, "passed": 5, "failed": 0},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["remaining_failures"] == 0
    assert content["fix_iteration"] == 1


def test_fix_agent_first_iteration():
    """Test fix agent on first iteration with failures."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 3, "failed": 2},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["fix_iteration"] == 1
    assert content["remaining_failures"] == 1  # 2 - 1 = 1
    assert content["strategy_class"] == "status_transition_guard"
    assert content["fix_plan"]["plan_valid"] is True
    assert content["fix_plan"]["target_files"]
    assert "plan_before_act" in content["instruction_stack"]


def test_fix_agent_subsequent_iteration():
    """Test fix agent increments iteration correctly."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": 2, "remaining_failures": 1},
        ),
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 4, "failed": 1},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["fix_iteration"] == 3  # Previous 2 + 1
    assert content["strategy_class"] == "minimal_source_correction"


def test_fix_agent_iteration_from_string():
    """Test fix agent handles string iteration value from previous patch."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": "5", "remaining_failures": 1},
        ),
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 4, "failed": 1},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "FAILED"
    content = _get_content(result, "code_patch")
    assert content["diagnosis"] == "max_strategy_classes_exhausted"


def test_fix_agent_produces_patch_files():
    """Test fix agent always emits at least one file change for failures."""
    agent = FixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 3, "passed": 1, "failed": 2},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    paths = [f["path"] for f in content.get("files", [])]
    assert "src/feature_impl.py" in paths


def test_fix_agent_blocks_when_plan_has_no_target_files():
    agent = FixAgent()
    context = {
        "use_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 2, "passed": 0, "failed": 2},
        ),
        "strict_target_files": True,
        "ci_failure_context": {"files": [], "test_targets": []},
    }

    result = agent.run(context)

    assert result["status"] == "FAILED"
    content = _get_content(result, "code_patch")
    assert content["blocked"] is True
    assert content["diagnosis"] == "missing_target_files"


def test_fix_agent_stops_after_strategy_classes_exhausted():
    agent = FixAgent()
    context = {
        "use_llm": False,
        "fix_agent": _step_result(
            "SUCCESS",
            "code_patch",
            {"fix_iteration": len(agent.STRATEGY_SEQUENCE), "remaining_failures": 1},
        ),
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 5, "passed": 2, "failed": 3},
        ),
    }

    result = agent.run(context)

    assert result["status"] == "FAILED"
    content = _get_content(result, "code_patch")
    assert content["diagnosis"] == "max_strategy_classes_exhausted"


def test_fix_agent_name():
    """Test agent name."""
    agent = FixAgent()
    assert agent.name == "fix_agent"
    assert "fix" in agent.description.lower()


def test_fix_agent_static_helpers_exist():
    """Test static helper methods remain available."""
    assert callable(FixAgent.parse_stacktrace)
    assert callable(FixAgent.detect_failure)
    assert callable(FixAgent.generate_fix)


def test_fix_agent_prefers_full_test_results_artifact_over_summary():
    """Full test_runner artifact should be preferred over compact step summary."""
    full_artifact = {
        "framework": "pytest",
        "failed": 1,
        "passed": 0,
        "total": 1,
        "exit_code": 1,
        "stdout": "FAILED tests/unit/orchestrator/test_orchestrator_engine.py::test_x",
        "stderr": "TypeError: OrchestratorEngine.run() got an unexpected keyword argument 'run_id'",
        "failure_signature": "abc123",
    }
    context = {
        "test_runner": {
            "status": "PARTIAL_SUCCESS",
            "test_results": {
                "failed": 1,
                "passed": 0,
                "total": 1,
                "exit_code": 1,
                "failure_signature": "abc123",
            },
            "artifacts": [{"type": "test_results", "content": full_artifact}],
        }
    }

    resolved = FixAgent._resolve_test_results(context)
    assert resolved == full_artifact
    assert "unexpected keyword argument" in resolved.get("stderr", "")


def test_fix_agent_prefers_code_generator_core_when_available(monkeypatch):
    """Fix agent should reuse code generator core patch when it succeeds."""
    agent = FixAgent()

    def _fake_codegen_core(self, context, iteration):
        return (
            {
                "schema_version": "1.0",
                "files": [
                    {
                        "path": "tests/test_example.py",
                        "change_type": "modify",
                        "content": "assert True\n",
                    }
                ],
                "decisions": ["use_codegen_core"],
            },
            None,
        )

    monkeypatch.setattr(
        fix_agent_module.FixAgent,
        "_generate_fix_with_code_generator_core",
        _fake_codegen_core,
    )

    context = {
        "use_llm": True,
        "require_llm": False,
        "test_runner": _step_result(
            "PARTIAL_SUCCESS",
            "test_results",
            {"total": 2, "passed": 1, "failed": 1},
        ),
    }
    result = agent.run(context)

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["files"][0]["path"] == "tests/test_example.py"
    assert "use_codegen_core" in content.get("decisions", [])


def test_fix_agent_require_llm_handles_missing_stdout_stderr(monkeypatch):
    """Require-LLM mode should remain actionable even when runner omits stdout/stderr."""
    agent = FixAgent()

    monkeypatch.setattr(
        fix_agent_module.FixAgent,
        "_generate_fix_with_code_generator_core",
        lambda *_args, **_kwargs: (
            None,
            "codegen_fix_returned_empty_patch",
        ),
    )

    class _StubLLM:
        def complete(self, _prompt):
            return '{"files":[{"path":"src/feature_impl.py","change_type":"modify","content":"# fix"}]}'

        def close(self):
            return

    monkeypatch.setattr(fix_agent_module, "get_llm_wrapper", lambda *args, **kwargs: _StubLLM())
    monkeypatch.setattr(fix_agent_module, "get_legacy_llm_wrapper", lambda *args, **kwargs: None)

    result = agent.run(
        {
            "use_llm": True,
            "require_llm": True,
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {
                    "framework": "pytest",
                    "failed": 1,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "",
                },
            ),
        }
    )

    assert result["status"] == "SUCCESS"
    content = _get_content(result, "code_patch")
    assert content["files"]


def test_fix_agent_codegen_core_propagates_quality_gate_flags(monkeypatch):
    captured_context: dict = {}

    class _StubEnhancedCodeGenerator:
        def run(self, context: dict) -> dict:
            captured_context.update(context)
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ]
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "strict_target_files": True,
            "enforce_patch_quality_gate": True,
            "quality_gate_mode": "shadow",
            "ci_failure_context": {
                "files": ["tests/unit/orchestrator/test_orchestrator_engine.py"],
                "test_targets": [],
            },
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=2,
    )

    assert error is None
    assert patch is not None
    assert captured_context["publish_pr_in_code_generator"] is False
    assert captured_context["strict_target_files"] is True
    assert captured_context["enforce_patch_quality_gate"] is True
    assert captured_context["enforce_semantic_patch_gate"] is True
    assert captured_context["enforce_semantic_gate_blocking"] is True
    assert captured_context["quality_gate_mode"] == "shadow"
    assert captured_context["patch_strategy"] == "patch_first"
    assert captured_context["allow_full_file_rewrite"] is False


def test_fix_agent_codegen_core_open_mode_relaxes_target_scope(monkeypatch):
    captured_context: dict = {}

    class _StubEnhancedCodeGenerator:
        def run(self, context: dict) -> dict:
            captured_context.update(context)
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ]
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "open_mode": True,
            "enforce_patch_quality_gate": True,
            "ci_failure_context": {
                "files": ["tests/unit/orchestrator/test_orchestrator_engine.py"],
                "test_targets": [],
            },
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=2,
    )

    assert error is None
    assert patch is not None
    assert captured_context["open_mode"] is True
    assert captured_context["strict_target_files"] is False
    assert captured_context["quality_gate_mode"] == "shadow"


def test_fix_agent_codegen_core_rejects_failed_codegen_result(monkeypatch):
    class _StubEnhancedCodeGenerator:
        def run(self, _context: dict) -> dict:
            return {
                "status": "FAILED",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ]
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=1,
    )

    assert patch is None
    assert error == "codegen_fix_status=FAILED"


def test_fix_agent_codegen_core_rejects_gate_failed_patch(monkeypatch):
    class _StubEnhancedCodeGenerator:
        def run(self, _context: dict) -> dict:
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ],
                            "semantic_gate": {
                                "enabled": True,
                                "mode": "enforce",
                                "passed": False,
                                "violations": ["python_syntax_error:orchestrator/engine.py:222"],
                            },
                            "quality_gate": {
                                "passed": False,
                                "reasons": ["semantic_contract_violation"],
                            },
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=1,
    )

    assert patch is None
    assert (
        error == "codegen_fix_semantic_gate_failed:python_syntax_error:orchestrator/engine.py:222"
    )


def test_fix_agent_codegen_core_retries_after_invalid_candidate(monkeypatch):
    seen_task_descriptions: list[str] = []

    class _StubEnhancedCodeGenerator:
        call_count = 0

        def run(self, context: dict) -> dict:
            self.__class__.call_count += 1
            seen_task_descriptions.append(str(context.get("task_description") or ""))
            if self.__class__.call_count == 1:
                return {
                    "status": "FAILED",
                    "artifacts": [
                        {
                            "type": "code_patch",
                            "content": {
                                "files": [
                                    {
                                        "path": "orchestrator/engine.py",
                                        "change_type": "modify",
                                        "content": "def broken(:\n",
                                    }
                                ],
                                "semantic_gate": {
                                    "enabled": True,
                                    "mode": "enforce",
                                    "passed": False,
                                    "violations": ["python_syntax_error:orchestrator/engine.py:1"],
                                },
                                "quality_gate": {
                                    "passed": False,
                                    "reasons": ["semantic_contract_violation"],
                                },
                            },
                        }
                    ],
                }
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "def repaired() -> None:\n    return None\n",
                                }
                            ],
                            "semantic_gate": {
                                "enabled": True,
                                "mode": "enforce",
                                "passed": True,
                                "violations": [],
                            },
                            "quality_gate": {"passed": True, "reasons": []},
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=1,
    )

    assert error is None
    assert patch is not None
    assert patch["files"][0]["content"] == "def repaired() -> None:\n    return None\n"
    assert len(seen_task_descriptions) == 2
    assert "Previous candidate was rejected" in seen_task_descriptions[1]
    assert "python_syntax_error:orchestrator/engine.py:1" in seen_task_descriptions[1]


def test_fix_agent_codegen_core_stops_after_local_candidate_budget(monkeypatch):
    seen_task_descriptions: list[str] = []

    class _StubEnhancedCodeGenerator:
        def run(self, context: dict) -> dict:
            seen_task_descriptions.append(str(context.get("task_description") or ""))
            return {
                "status": "FAILED",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "def broken(:\n",
                                }
                            ],
                            "semantic_gate": {
                                "enabled": True,
                                "mode": "enforce",
                                "passed": False,
                                "violations": ["python_syntax_error:orchestrator/engine.py:1"],
                            },
                            "quality_gate": {
                                "passed": False,
                                "reasons": ["semantic_contract_violation"],
                            },
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "test_runner": _step_result(
                "PARTIAL_SUCCESS",
                "test_results",
                {"failed": 1, "exit_code": 1, "stdout": "AssertionError: boom"},
            ),
        },
        iteration=1,
    )

    assert patch is None
    assert error == "codegen_fix_semantic_gate_failed:python_syntax_error:orchestrator/engine.py:1"
    assert len(seen_task_descriptions) == agent.CODEGEN_FIX_MAX_ATTEMPTS
    assert "Previous candidate was rejected" in seen_task_descriptions[-1]


def test_fix_agent_codegen_core_includes_compact_failure_summary(monkeypatch):
    captured_context: dict = {}

    class _StubEnhancedCodeGenerator:
        def run(self, context: dict) -> dict:
            captured_context.update(context)
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ]
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "open_mode": True,
            "test_runner": {
                "status": "PARTIAL_SUCCESS",
                "test_results": {
                    "failed": 23,
                    "exit_code": 1,
                    "failure_signature": "abc123",
                },
                "artifacts": [
                    {
                        "type": "test_results",
                        "content": {
                            "framework": "pytest",
                            "failed": 23,
                            "exit_code": 1,
                            "failure_signature": "abc123",
                            "json_report": {
                                "tests": [
                                    {
                                        "nodeid": "tests/unit/orchestrator/test_orchestrator_engine.py::test_engine_returns_summary_for_init_pipeline",
                                        "outcome": "failed",
                                        "call": {
                                            "longrepr": (
                                                "x\n"
                                                "E       TypeError: OrchestratorEngine.run() got an unexpected keyword argument 'run_id'\n"
                                            )
                                        },
                                    }
                                ]
                            },
                        },
                    }
                ],
            },
            "ci_failure_context": {
                "files": ["tests/unit/orchestrator/test_orchestrator_engine.py"],
                "test_targets": [],
            },
        },
        iteration=2,
    )

    assert error is None
    assert patch is not None
    assert "Focused failure summary" in captured_context["task_description"]
    assert "unexpected keyword argument 'run_id'" in captured_context["task_description"]
    assert "test_engine_returns_summary_for_init_pipeline" in captured_context["task_description"]


def test_fix_agent_failure_summary_prefers_structured_failures_packet(monkeypatch):
    captured_context: dict = {}

    class _StubEnhancedCodeGenerator:
        def run(self, context: dict) -> dict:
            captured_context.update(context)
            return {
                "status": "SUCCESS",
                "artifacts": [
                    {
                        "type": "code_patch",
                        "content": {
                            "files": [
                                {
                                    "path": "orchestrator/engine.py",
                                    "change_type": "modify",
                                    "content": "pass\n",
                                }
                            ]
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        code_generator_module,
        "EnhancedCodeGenerator",
        _StubEnhancedCodeGenerator,
    )

    agent = FixAgent()
    patch, error = agent._generate_fix_with_code_generator_core(  # noqa: SLF001
        context={
            "open_mode": True,
            "test_runner": {
                "status": "PARTIAL_SUCCESS",
                "artifacts": [
                    {
                        "type": "test_results",
                        "content": {
                            "framework": "pytest",
                            "failed": 23,
                            "exit_code": 1,
                            "failure_signature": "abc123",
                            "stdout": "truncated summary only",
                            "failures": [
                                {
                                    "nodeid": (
                                        "tests/unit/orchestrator/test_orchestrator_engine.py::"
                                        "test_engine_returns_summary_for_init_pipeline"
                                    ),
                                    "type": "test_failure",
                                    "error_line": (
                                        "TypeError: OrchestratorEngine.run() got an "
                                        "unexpected keyword argument 'run_id'"
                                    ),
                                    "message": "TypeError: OrchestratorEngine.run() ...",
                                }
                            ],
                        },
                    }
                ],
            },
            "ci_failure_context": {
                "files": ["tests/unit/orchestrator/test_orchestrator_engine.py"],
                "test_targets": [],
            },
        },
        iteration=2,
    )

    assert error is None
    assert patch is not None
    assert "unexpected keyword argument 'run_id'" in captured_context["task_description"]
    assert "test_engine_returns_summary_for_init_pipeline" in captured_context["task_description"]

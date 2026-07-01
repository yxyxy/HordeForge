from __future__ import annotations

import pytest
from jinja2.exceptions import SecurityError as JinjaSecurityError
from pydantic import ValidationError

from hordeforge_config import RunConfig


class TestJinja2Sandbox:
    def test_sandboxed_env_blocks_mro_access(self):
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string("{{ ''.__class__.__mro__ }}")

        with pytest.raises(JinjaSecurityError):
            template.render()

    def test_sandboxed_env_blocks_subclass_access(self):
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string("{{ ''.__class__.__subclasses__() }}")

        with pytest.raises(JinjaSecurityError):
            template.render()

    def test_sandboxed_env_blocks_chained_class_mro(self):
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string("{{ config.__class__.__mro__ }}")

        with pytest.raises(JinjaSecurityError):
            template.render(config={})

    def test_sandboxed_env_blocks_chained_class_subclasses(self):
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string("{{ config.__class__.__subclasses__() }}")

        with pytest.raises(JinjaSecurityError):
            template.render(config={})

    def test_sandboxed_env_blocks_init_globals(self):
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment()
        template = env.from_string("{{ cycler.__init__.__globals__ }}")

        with pytest.raises(JinjaSecurityError):
            template.render()

    def test_loop_eval_blocks_template_injection(self):
        from orchestrator.loop_eval import evaluate_loop_condition

        result = evaluate_loop_condition(
            "{{ ''.__class__.__mro__[1].__subclasses__() }}",
            {},
        )
        assert result is False

    def test_loop_eval_safe_template_works(self):
        from orchestrator.loop_eval import evaluate_loop_condition

        result = evaluate_loop_condition("{{ count }}", {"count": 5})
        assert result is True


class TestPathTraversal:
    def test_patch_apply_rejects_dotdot_paths(self, tmp_path):
        from agents.patch_apply_agent import PatchApplyAgent

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "safe.txt").write_text("ok")

        files = [{"path": "../../etc/passwd", "content": "stolen"}]
        applied = PatchApplyAgent._apply_materialized_files(str(workspace), files)
        assert applied == 0
        assert not (workspace / ".." / "etc" / "passwd").exists()

    def test_patch_apply_rejects_absolute_paths(self, tmp_path):
        from agents.patch_apply_agent import PatchApplyAgent

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        files = [{"path": "/etc/passwd", "content": "stolen"}]
        applied = PatchApplyAgent._apply_materialized_files(str(workspace), files)
        assert applied == 0

    def test_patch_apply_accepts_safe_relative_paths(self, tmp_path):
        from agents.patch_apply_agent import PatchApplyAgent

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        files = [{"path": "src/app.py", "content": "print('hello')"}]
        applied = PatchApplyAgent._apply_materialized_files(str(workspace), files)
        assert applied == 1
        assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "print('hello')"

    def test_code_generator_filters_dotdot_paths(self):
        from agents.code_generator import CodeGenerator

        payload = {
            "required_files": [
                "../secrets.env",
                "/etc/passwd",
                "src/main.py",
                {"path": "../../escape.py"},
            ]
        }
        result = CodeGenerator._extract_required_files(payload)
        assert "../secrets.env" not in result
        assert "/etc/passwd" not in result
        assert "../../escape.py" not in result
        assert "src/main.py" in result

    def test_instruction_layers_rejects_outside_workspace(self, tmp_path):
        from agents.instruction_layers import _within_workspace

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        inside = workspace / "src" / "app.py"
        outside = tmp_path / ".." / "secret.txt"

        assert _within_workspace(inside, workspace) is True
        assert _within_workspace(outside, workspace) is False

    def test_patch_apply_rejects_windows_backslash_escape(self, tmp_path):
        from agents.patch_apply_agent import PatchApplyAgent

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        files = [{"path": "..\\..\\etc\\passwd", "content": "stolen"}]
        applied = PatchApplyAgent._apply_materialized_files(str(workspace), files)
        assert applied == 0


class TestConfigValidation:
    def test_from_env_raises_without_webhook_secret(self):
        import os
        import sys

        is_test_original = "pytest" in sys.modules
        if is_test_original:
            sys.modules.pop("pytest", None)

        old_val = os.environ.pop("HORDEFORGE_WEBHOOK_SECRET", None)
        try:
            with pytest.raises(ValueError, match="HORDEFORGE_WEBHOOK_SECRET"):
                RunConfig.from_env()
        finally:
            if old_val is not None:
                os.environ["HORDEFORGE_WEBHOOK_SECRET"] = old_val
            if is_test_original:
                sys.modules["pytest"] = pytest

    def test_from_env_skips_secrets_in_test_mode(self):
        config = RunConfig.from_env()
        assert isinstance(config, RunConfig)

    def test_invalid_timeout_rejected_by_pydantic(self):
        with pytest.raises(ValidationError):
            RunConfig(request_timeout_seconds=-1)

    def test_invalid_max_workers_rejected_by_pydantic(self):
        with pytest.raises(ValidationError):
            RunConfig(max_parallel_workers=0)

    def test_gateway_url_trailing_slash_stripped(self):
        config = RunConfig(gateway_url="http://localhost:8000/")
        assert config.gateway_url == "http://localhost:8000"

    def test_queue_backend_normalized(self):
        config = RunConfig(queue_backend="  MEMORY  ")
        assert config.queue_backend == "memory"

    def test_default_tenant_id_normalized(self):
        config = RunConfig(default_tenant_id="  DefaultTenant  ")
        assert config.default_tenant_id == "defaulttenant"

    def test_config_is_frozen(self):
        config = RunConfig()
        with pytest.raises(ValidationError):
            config.gateway_url = "http://changed.com"

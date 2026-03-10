from hordeforge_config import RunConfig


def test_run_config_uses_defaults_when_env_is_missing(monkeypatch):
    monkeypatch.delenv("HORDEFORGE_GATEWAY_URL", raising=False)
    monkeypatch.delenv("HORDEFORGE_PIPELINES_DIR", raising=False)
    monkeypatch.delenv("HORDEFORGE_RULES_DIR", raising=False)
    monkeypatch.delenv("HORDEFORGE_RULE_SET_VERSION", raising=False)
    monkeypatch.delenv("HORDEFORGE_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("HORDEFORGE_STATUS_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("HORDEFORGE_HEALTH_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("HORDEFORGE_MAX_PARALLEL_WORKERS", raising=False)
    monkeypatch.delenv("HORDEFORGE_STRICT_SCHEMA_VALIDATION", raising=False)
    monkeypatch.delenv("HORDEFORGE_ENABLE_DYNAMIC_FALLBACK", raising=False)
    monkeypatch.delenv("HORDEFORGE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("HORDEFORGE_STORAGE_DIR", raising=False)
    monkeypatch.delenv("HORDEFORGE_IDEMPOTENCY_TTL_SECONDS", raising=False)
    monkeypatch.delenv("HORDEFORGE_OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("HORDEFORGE_OPERATOR_ALLOWED_ROLES", raising=False)
    monkeypatch.delenv("HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES", raising=False)
    monkeypatch.delenv("HORDEFORGE_DEFAULT_TENANT_ID", raising=False)
    monkeypatch.delenv("HORDEFORGE_TENANT_REPOSITORY_MAP", raising=False)
    monkeypatch.delenv("HORDEFORGE_ENFORCE_TENANT_BOUNDARIES", raising=False)

    config = RunConfig.from_env()

    assert config.gateway_url == "http://localhost:8000"
    assert config.pipelines_dir == "pipelines"
    assert config.rules_dir == "rules"
    assert config.rule_set_version == "1.0"
    assert config.request_timeout_seconds == 30.0
    assert config.status_timeout_seconds == 15.0
    assert config.health_timeout_seconds == 10.0
    assert config.max_parallel_workers == 4
    assert config.strict_schema_validation is True
    assert config.enable_dynamic_fallback is True
    assert config.webhook_secret == "local-dev-secret"
    assert config.storage_dir == ".hordeforge_data"
    assert config.idempotency_ttl_seconds == 3600
    assert config.operator_api_key == "local-operator-key"
    assert config.operator_allowed_roles == ("operator",)
    assert config.manual_command_allowed_sources == ("api",)
    assert config.default_tenant_id == "default"
    assert config.tenant_repository_map == {}
    assert config.enforce_tenant_boundaries is False


def test_run_config_reads_values_from_env(monkeypatch):
    monkeypatch.setenv("HORDEFORGE_GATEWAY_URL", "http://gateway:9000/")
    monkeypatch.setenv("HORDEFORGE_PIPELINES_DIR", "custom_pipelines")
    monkeypatch.setenv("HORDEFORGE_RULES_DIR", "custom_rules")
    monkeypatch.setenv("HORDEFORGE_RULE_SET_VERSION", "2.1.0")
    monkeypatch.setenv("HORDEFORGE_REQUEST_TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("HORDEFORGE_STATUS_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("HORDEFORGE_HEALTH_TIMEOUT_SECONDS", "13")
    monkeypatch.setenv("HORDEFORGE_MAX_PARALLEL_WORKERS", "9")
    monkeypatch.setenv("HORDEFORGE_STRICT_SCHEMA_VALIDATION", "false")
    monkeypatch.setenv("HORDEFORGE_ENABLE_DYNAMIC_FALLBACK", "0")
    monkeypatch.setenv("HORDEFORGE_WEBHOOK_SECRET", "top-secret")
    monkeypatch.setenv("HORDEFORGE_STORAGE_DIR", ".tmp-hf-storage")
    monkeypatch.setenv("HORDEFORGE_IDEMPOTENCY_TTL_SECONDS", "120")
    monkeypatch.setenv("HORDEFORGE_OPERATOR_API_KEY", "operator-secret")
    monkeypatch.setenv("HORDEFORGE_OPERATOR_ALLOWED_ROLES", "operator,admin,operator")
    monkeypatch.setenv("HORDEFORGE_MANUAL_COMMAND_ALLOWED_SOURCES", "api,runbook")
    monkeypatch.setenv("HORDEFORGE_DEFAULT_TENANT_ID", "Acme")
    monkeypatch.setenv(
        "HORDEFORGE_TENANT_REPOSITORY_MAP",
        '{"acme": ["acme/repo"], "beta": "beta/repo"}',
    )
    monkeypatch.setenv("HORDEFORGE_ENFORCE_TENANT_BOUNDARIES", "true")

    config = RunConfig.from_env()

    assert config.gateway_url == "http://gateway:9000"
    assert config.pipelines_dir == "custom_pipelines"
    assert config.rules_dir == "custom_rules"
    assert config.rule_set_version == "2.1.0"
    assert config.request_timeout_seconds == 11.0
    assert config.status_timeout_seconds == 12.0
    assert config.health_timeout_seconds == 13.0
    assert config.max_parallel_workers == 9
    assert config.strict_schema_validation is False
    assert config.enable_dynamic_fallback is False
    assert config.webhook_secret == "top-secret"
    assert config.storage_dir == ".tmp-hf-storage"
    assert config.idempotency_ttl_seconds == 120
    assert config.operator_api_key == "operator-secret"
    assert config.operator_allowed_roles == ("operator", "admin")
    assert config.manual_command_allowed_sources == ("api", "runbook")
    assert config.default_tenant_id == "acme"
    assert config.tenant_repository_map == {"acme": ("acme/repo",), "beta": ("beta/repo",)}
    assert config.enforce_tenant_boundaries is True

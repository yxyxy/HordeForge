from __future__ import annotations

from scheduler.tenant_registry import (
    TenantRepositoryRegistry,
    extract_repository_full_name,
    normalize_repository_full_name,
    normalize_tenant_id,
)


def test_normalize_tenant_id_default_fallback():
    assert normalize_tenant_id(None) == "default"
    assert normalize_tenant_id("") == "default"
    assert normalize_tenant_id(" ACME ") == "acme"


def test_normalize_repository_full_name_requires_owner_repo_format():
    assert normalize_repository_full_name("Acme/Repo") == "acme/repo"
    assert normalize_repository_full_name("invalid") is None


def test_extract_repository_full_name_from_inputs():
    assert (
        extract_repository_full_name(
            inputs={"repo_url": "https://github.com/yxyxy/hordeforge.git"},
            explicit=None,
        )
        == "acme/hordeforge"
    )
    assert (
        extract_repository_full_name(
            inputs={"repository": {"full_name": "Acme/Repo"}},
            explicit=None,
        )
        == "acme/repo"
    )


def test_tenant_registry_validation_allows_wildcard_and_enforces_boundaries():
    registry = TenantRepositoryRegistry(
        mapping={"acme": ("acme/repo", "*")},
        enforce_boundaries=True,
    )

    allowed = registry.validate_boundary(tenant_id="acme", repository_full_name="acme/other")
    assert allowed.allowed is True
    assert allowed.reason == "tenant_wildcard_allowed"


def test_tenant_registry_rejects_unknown_tenant_when_enforced():
    registry = TenantRepositoryRegistry(
        mapping={"acme": ("acme/repo",)},
        enforce_boundaries=True,
    )

    decision = registry.validate_boundary(tenant_id="beta", repository_full_name="beta/repo")
    assert decision.allowed is False
    assert decision.reason == "unknown_tenant"


def test_tenant_registry_requires_repo_when_restricted():
    registry = TenantRepositoryRegistry(
        mapping={"acme": ("acme/repo",)},
        enforce_boundaries=True,
    )

    decision = registry.validate_boundary(tenant_id="acme", repository_full_name=None)
    assert decision.allowed is False
    assert decision.reason == "repository_full_name_required"

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_REPO_NAME_PATTERN = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$")
_REPO_FROM_URL_PATTERN = re.compile(
    r"(?:https?://|git@)github\.com[:/](?P<full>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:\.git)?/?$",
    re.IGNORECASE,
)


def normalize_tenant_id(value: str | None, *, default_tenant_id: str = "default") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        normalized = str(default_tenant_id).strip().lower() or "default"
    return normalized


def normalize_repository_full_name(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower().removesuffix(".git")
    if not normalized:
        return None
    if _REPO_NAME_PATTERN.fullmatch(normalized):
        return normalized
    return None


def extract_repository_full_name(
    *, inputs: dict[str, Any], explicit: str | None = None
) -> str | None:
    candidates: list[str | None] = [explicit]
    repository = inputs.get("repository")
    if isinstance(repository, dict):
        candidates.append(str(repository.get("full_name", "")).strip())
    candidates.append(str(inputs.get("repository_full_name", "")).strip())
    repo_url = str(inputs.get("repo_url", "")).strip()
    if repo_url:
        match = _REPO_FROM_URL_PATTERN.search(repo_url)
        if match:
            candidates.append(match.group("full"))

    for candidate in candidates:
        normalized = normalize_repository_full_name(candidate)
        if normalized is not None:
            return normalized
    return None


@dataclass(frozen=True, slots=True)
class TenantBoundaryDecision:
    allowed: bool
    reason: str
    tenant_id: str
    repository_full_name: str | None


class TenantRepositoryRegistry:
    def __init__(
        self,
        *,
        mapping: dict[str, tuple[str, ...]] | None = None,
        default_tenant_id: str = "default",
        enforce_boundaries: bool = False,
    ) -> None:
        self.default_tenant_id = normalize_tenant_id(default_tenant_id, default_tenant_id="default")
        self.enforce_boundaries = bool(enforce_boundaries)
        self._mapping: dict[str, set[str]] = {}
        for tenant_id, repositories in (mapping or {}).items():
            normalized_tenant = normalize_tenant_id(
                tenant_id, default_tenant_id=self.default_tenant_id
            )
            values = {
                item
                for item in (
                    normalize_repository_full_name(value) if value != "*" else "*"
                    for value in repositories
                )
                if item is not None
            }
            if values:
                self._mapping[normalized_tenant] = values

    @property
    def has_mapping(self) -> bool:
        return bool(self._mapping)

    @classmethod
    def from_json(
        cls,
        raw_mapping: str | None,
        *,
        default_tenant_id: str = "default",
        enforce_boundaries: bool = False,
    ) -> TenantRepositoryRegistry:
        if not raw_mapping:
            return cls(
                mapping={},
                default_tenant_id=default_tenant_id,
                enforce_boundaries=enforce_boundaries,
            )
        try:
            payload = json.loads(raw_mapping)
        except json.JSONDecodeError:
            payload = {}
        mapping: dict[str, tuple[str, ...]] = {}
        if isinstance(payload, dict):
            for tenant_id, repositories in payload.items():
                if not isinstance(tenant_id, str):
                    continue
                if isinstance(repositories, list):
                    values = tuple(str(item).strip() for item in repositories if str(item).strip())
                elif isinstance(repositories, str):
                    values = tuple(item.strip() for item in repositories.split(",") if item.strip())
                else:
                    continue
                if values:
                    mapping[tenant_id] = values
        return cls(
            mapping=mapping,
            default_tenant_id=default_tenant_id,
            enforce_boundaries=enforce_boundaries,
        )

    def list_repositories(self, tenant_id: str | None) -> tuple[str, ...]:
        normalized_tenant = normalize_tenant_id(
            tenant_id,
            default_tenant_id=self.default_tenant_id,
        )
        values = sorted(self._mapping.get(normalized_tenant, set()))
        return tuple(values)

    def validate_boundary(
        self,
        *,
        tenant_id: str | None,
        repository_full_name: str | None,
    ) -> TenantBoundaryDecision:
        normalized_tenant = normalize_tenant_id(
            tenant_id,
            default_tenant_id=self.default_tenant_id,
        )
        normalized_repository = normalize_repository_full_name(repository_full_name)

        if not self.enforce_boundaries and not self.has_mapping:
            return TenantBoundaryDecision(
                allowed=True,
                reason="boundary_check_disabled",
                tenant_id=normalized_tenant,
                repository_full_name=normalized_repository,
            )

        allowed_repositories = self._mapping.get(normalized_tenant)
        if allowed_repositories is None:
            return TenantBoundaryDecision(
                allowed=False,
                reason="unknown_tenant",
                tenant_id=normalized_tenant,
                repository_full_name=normalized_repository,
            )
        if "*" in allowed_repositories:
            return TenantBoundaryDecision(
                allowed=True,
                reason="tenant_wildcard_allowed",
                tenant_id=normalized_tenant,
                repository_full_name=normalized_repository,
            )
        if normalized_repository is None:
            return TenantBoundaryDecision(
                allowed=False,
                reason="repository_full_name_required",
                tenant_id=normalized_tenant,
                repository_full_name=None,
            )
        if normalized_repository in allowed_repositories:
            return TenantBoundaryDecision(
                allowed=True,
                reason="repository_allowed",
                tenant_id=normalized_tenant,
                repository_full_name=normalized_repository,
            )
        return TenantBoundaryDecision(
            allowed=False,
            reason="repository_not_allowed",
            tenant_id=normalized_tenant,
            repository_full_name=normalized_repository,
        )

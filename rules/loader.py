from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

RULE_FILE_MAP: tuple[tuple[str, str], ...] = (
    ("coding", "coding_rules.md"),
    ("testing", "testing_rules.md"),
    ("security", "security_rules.md"),
)
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
DEFAULT_RULE_SET_VERSION = "1.0"


class RulePackValidationError(ValueError):
    """Raised when a rule pack does not satisfy minimum structure requirements."""


@dataclass(frozen=True, slots=True)
class RuleDocument:
    name: str
    source_path: str
    content: str
    line_count: int
    bullet_count: int
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "content": self.content,
            "line_count": self.line_count,
            "bullet_count": self.bullet_count,
            "checksum": self.checksum,
        }


class RulePackLoader:
    def __init__(
        self,
        *,
        rules_dir: str = "rules",
        rule_set_version: str = DEFAULT_RULE_SET_VERSION,
    ) -> None:
        self.rules_dir = Path(rules_dir)
        self.rule_set_version = rule_set_version

    @staticmethod
    def _validate_version(version: str) -> str:
        normalized = version.strip()
        if not normalized or not _SEMVER_PATTERN.fullmatch(normalized):
            raise RulePackValidationError(
                f"Invalid rule set version '{version}'. Expected format: <major>.<minor>[.<patch>]."
            )
        return normalized

    @staticmethod
    def _count_bullets(lines: list[str]) -> int:
        return sum(1 for line in lines if _BULLET_PATTERN.match(line))

    @staticmethod
    def _contains_heading(lines: list[str]) -> bool:
        return any(line.strip().startswith("#") for line in lines)

    def _read_document(self, rule_name: str, filename: str) -> RuleDocument:
        path = self.rules_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {path}")

        content = path.read_text(encoding="utf-8").strip()
        lines = content.splitlines()
        if not content:
            raise RulePackValidationError(f"Rule file is empty: {path}")
        if not self._contains_heading(lines):
            raise RulePackValidationError(f"Rule file must contain a markdown heading: {path}")

        bullet_count = self._count_bullets(lines)
        if bullet_count == 0:
            raise RulePackValidationError(
                f"Rule file must contain at least one rule bullet: {path}"
            )

        return RuleDocument(
            name=rule_name,
            source_path=path.as_posix(),
            content=content,
            line_count=len(lines),
            bullet_count=bullet_count,
            checksum=sha256(content.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _validate_pack(payload: dict[str, Any]) -> None:
        documents = payload.get("documents")
        if not isinstance(documents, dict):
            raise RulePackValidationError("Rule pack payload must contain documents mapping.")

        expected_rule_names = {item[0] for item in RULE_FILE_MAP}
        provided_names = set(documents.keys())
        if provided_names != expected_rule_names:
            missing = sorted(expected_rule_names - provided_names)
            extra = sorted(provided_names - expected_rule_names)
            raise RulePackValidationError(
                f"Rule pack documents mismatch. missing={missing}, extra={extra}"
            )

        for name, document in documents.items():
            if not isinstance(document, dict):
                raise RulePackValidationError(f"Rule document '{name}' must be an object.")
            content = document.get("content")
            if not isinstance(content, str) or not content.strip():
                raise RulePackValidationError(
                    f"Rule document '{name}' must contain non-empty content."
                )

        combined = payload.get("combined")
        if not isinstance(combined, str) or not combined.strip():
            raise RulePackValidationError("Rule pack combined content must be non-empty.")

    def load(self) -> dict[str, Any]:
        version = self._validate_version(self.rule_set_version)
        documents: dict[str, dict[str, Any]] = {}
        combined_blocks: list[str] = []
        sources: list[str] = []
        for rule_name, filename in RULE_FILE_MAP:
            document = self._read_document(rule_name, filename)
            payload = document.to_dict()
            documents[rule_name] = payload
            combined_blocks.append(f"# {rule_name}\n{document.content}")
            sources.append(document.source_path)

        combined = "\n\n".join(combined_blocks).strip()
        payload = {
            "version": version,
            "documents": documents,
            "sources": sources,
            "combined": combined,
            "checksum": sha256(combined.encode("utf-8")).hexdigest(),
        }
        self._validate_pack(payload)
        return payload

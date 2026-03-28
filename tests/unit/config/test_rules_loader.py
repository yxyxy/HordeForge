from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rules.loader import RulePackLoader, RulePackValidationError


def _write_rule(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip(), encoding="utf-8")


def test_rule_pack_loader_loads_documents_with_version_and_checksum():
    loader = RulePackLoader(rules_dir="rules", rule_set_version="1.2.0")

    payload = loader.load()

    assert payload["version"] == "1.2.0"
    assert payload["checksum"]
    assert set(payload["documents"]) == {"coding", "testing", "security"}
    assert payload["documents"]["coding"]["bullet_count"] >= 1


def test_rule_pack_loader_rejects_invalid_version_format():
    loader = RulePackLoader(rules_dir="rules", rule_set_version="version-one")

    with pytest.raises(RulePackValidationError, match="Invalid rule set version"):
        loader.load()


def test_rule_pack_loader_rejects_missing_rule_document():
    base_dir = Path("tests/unit/_tmp_rules_missing")
    _write_rule(base_dir / "coding_rules.md", "# Coding\n- Keep output deterministic")
    _write_rule(base_dir / "testing_rules.md", "# Testing\n- Add a failing test first")

    try:
        loader = RulePackLoader(rules_dir=str(base_dir), rule_set_version="1.0")
        with pytest.raises(FileNotFoundError, match="Rule file not found"):
            loader.load()
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def test_rule_pack_loader_rejects_invalid_document_structure():
    base_dir = Path("tests/unit/_tmp_rules_invalid")
    _write_rule(base_dir / "coding_rules.md", "# Coding\n- Keep output deterministic")
    _write_rule(base_dir / "testing_rules.md", "# Testing\nNo bullet list here")
    _write_rule(base_dir / "security_rules.md", "# Security\n- Redact secrets")

    try:
        loader = RulePackLoader(rules_dir=str(base_dir), rule_set_version="1.0")
        with pytest.raises(RulePackValidationError, match="at least one rule bullet"):
            loader.load()
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)

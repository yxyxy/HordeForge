from registry.placeholder_mapping import (
    PLACEHOLDER_CONTRACT_MAP,
    extract_placeholders,
    resolve_contract_for_key,
    resolve_contract_for_placeholder,
    root_key,
)


def test_extract_placeholders_from_string():
    value = "Use {{dod}} and {{specification.section}}"
    assert extract_placeholders(value) == ["dod", "specification.section"]


def test_extract_placeholders_from_nested_values():
    payload = {
        "a": "{{tests}}",
        "b": ["{{code_patch}}", {"c": "{{feature_spec}}"}],
        "d": None,
    }
    placeholders = extract_placeholders(payload)
    assert set(placeholders) == {"tests", "code_patch", "feature_spec"}


def test_root_key_extracts_first_segment():
    assert root_key("specification.section") == "specification"
    assert root_key("tests") == "tests"


def test_resolve_contract_for_key():
    assert resolve_contract_for_key("dod") == "context.dod.v1"
    assert resolve_contract_for_key("unknown") is None


def test_resolve_contract_for_placeholder():
    assert resolve_contract_for_placeholder("feature_spec.section") == "context.spec.v1"
    assert resolve_contract_for_placeholder("unknown") is None


def test_mapping_contains_core_placeholders():
    for key in [
        "dod",
        "specification",
        "feature_spec",
        "tests",
        "code_patch",
        "fixed_code_patch",
        "final_code_patch",
    ]:
        assert key in PLACEHOLDER_CONTRACT_MAP

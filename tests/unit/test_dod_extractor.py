from agents.dod_extractor import (
    DodExtractor,
    build_dod_prompt,
    extract_acceptance_criteria_from_markdown,
    extract_bdd_scenarios_from_markdown,
    parse_llm_dod_response,
)


def test_build_dod_prompt():
    """Test prompt building for DoD extraction."""
    prompt = build_dod_prompt("Implement login", "User should be able to login")
    assert "Implement login" in prompt
    assert "User should be able to login" in prompt
    assert "acceptance_criteria" in prompt.lower()


def test_extract_acceptance_criteria_from_checklist():
    """Test extraction from markdown checklists."""
    body = """
## Issue
- [ ] Feature works
- [x] Tests pass
    """
    result = extract_acceptance_criteria_from_markdown(body)
    assert any("Feature works" in c for c in result)
    assert any("Tests pass" in c for c in result)


def test_extract_acceptance_criteria_from_header():
    """Test extraction from Acceptance Criteria header."""
    body = """
## Acceptance Criteria
1. User can login
2. User can logout
    """
    result = extract_acceptance_criteria_from_markdown(body)
    assert any("login" in c.lower() for c in result)
    assert any("logout" in c.lower() for c in result)


def test_extract_bdd_scenarios():
    """Test extraction of BDD scenarios."""
    body = """
## Scenario: User login
Given the user is on the login page
When they enter valid credentials
Then they should be logged in

## Scenario: Failed login
Given wrong credentials
When user tries to login
Then error is shown
    """
    result = extract_bdd_scenarios_from_markdown(body)
    assert len(result) >= 1
    assert any(s["scenario"] == "User login" for s in result)
    assert any("login page" in s.get("given", "").lower() for s in result)


def test_parse_llm_dod_response():
    """Test parsing LLM response."""
    response = '''
    {
        "acceptance_criteria": ["Test 1", "Test 2"],
        "bdd_scenarios": [{"scenario": "Test", "given": "A", "when": "B", "then": "C"}],
        "confidence": 0.9
    }
    '''
    result = parse_llm_dod_response(response)
    assert result["acceptance_criteria"] == ["Test 1", "Test 2"]
    assert len(result["bdd_scenarios"]) == 1
    assert result["confidence"] == 0.9


def test_dod_extractor_returns_valid_agent_result_with_dod_artifact():
    agent = DodExtractor()
    result = agent.run({"issue": {"body": "Implement login feature"}})

    assert result["status"] == "SUCCESS"
    assert set(result.keys()) == {"status", "artifacts", "decisions", "logs", "next_actions"}
    assert result["artifacts"]
    artifact = result["artifacts"][0]
    assert artifact["type"] == "dod"
    assert artifact["content"]["schema_version"] == "1.0"
    assert artifact["content"]["acceptance_criteria"]
    assert isinstance(artifact["content"]["bdd_scenarios"], list)


def test_dod_extractor_accepts_issue_as_string():
    agent = DodExtractor()
    result = agent.run({"issue": "Ship with docs and tests"})

    assert result["status"] == "SUCCESS"
    criteria = result["artifacts"][0]["content"]["acceptance_criteria"]
    assert "Acceptance criteria extracted from issue body." in criteria


def test_dod_extractor_handles_missing_issue_context():
    agent = DodExtractor()
    result = agent.run({})

    assert result["status"] == "SUCCESS"
    assert result["logs"]
    assert result["next_actions"] == ["specification_writer"]

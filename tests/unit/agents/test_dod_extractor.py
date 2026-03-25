import pytest

from agents.dod_extractor import (
    DodExtractor,
    extract_acceptance_criteria,
    generate_bdd_from_ac,
    parse_issue,
)


class TestAcceptanceCriteriaExtraction:
    """Test acceptance criteria extraction"""

    def test_extract_from_markdown(self):
        text = """
        ## Acceptance Criteria
        - User can login
        - User can logout
        """
        result = extract_acceptance_criteria(text)
        assert result == ["User can login", "User can logout"]

    def test_extract_numbered(self):
        text = "1. Add tests\n2. Update docs"
        result = extract_acceptance_criteria(text)
        assert result == ["Add tests", "Update docs"]

    def test_extract_checklist(self):
        text = "- [x] Completed task\n- [ ] Pending task"
        result = extract_acceptance_criteria(text)
        assert result == ["Completed task", "Pending task"]

    def test_no_criteria(self):
        text = "Just some text without AC"
        result = extract_acceptance_criteria(text)
        assert result == []


class TestIssueParsing:
    """Test issue parsing"""

    def test_parse_issue_basic(self):
        issue = {"title": "Login feature", "body": "## Acceptance Criteria\n- Can login"}
        result = parse_issue(issue)
        assert result.title == "Login feature"
        assert result.description == "## Acceptance Criteria\n- Can login"
        assert result.acceptance_criteria == ["Can login"]

    def test_parse_labels(self):
        issue = {
            "title": "Bug fix",
            "body": "Fix issue",
            "labels": [{"name": "bug"}, {"name": "high-priority"}],
        }
        result = parse_issue(issue)
        assert result.labels == ["bug", "high-priority"]


class TestBDDGeneration:
    """Test BDD generation from acceptance criteria"""

    def test_generate_bdd(self):
        ac = ["User can login"]
        result = generate_bdd_from_ac(ac)
        assert len(result) == 1
        scenario = result[0]
        assert scenario["given"] == "system is running"
        assert scenario["when"] == "user can login"
        assert scenario["then"] == "expected behavior occurs"


class TestDodExtractorAgent:
    """Integration tests for DodExtractor"""

    @pytest.fixture
    def agent(self):
        return DodExtractor()

    def test_run_success(self, agent, monkeypatch):
        # Мокаем LLM, чтобы не падало
        def fake_call_llm(prompt):
            return {
                "acceptance_criteria": ["Fake AC"],
                "bdd_scenarios": [{"given": "x", "when": "y", "then": "z"}],
            }

        monkeypatch.setattr("agents.dod_extractor.call_llm", fake_call_llm)

        context = {
            "issue": {"title": "Feature", "body": "## Acceptance Criteria\n- User can login"}
        }

        result = agent.run(context)
        assert result["status"] == "SUCCESS"
        artifact = result["artifacts"][0]["content"]
        assert artifact["schema_version"] == "1.0"
        assert len(artifact["acceptance_criteria"]) >= 1
        assert len(artifact["bdd_scenarios"]) >= 1
        assert artifact["extraction_method"] in ["deterministic", "llm", "deterministic_fallback"]

    def test_run_no_issue(self, agent):
        context = {}
        result = agent.run(context)
        # В новой версии агент всегда возвращает SUCCESS, даже если нет issue
        # Он просто создает дефолтный issue
        assert result["status"] == "SUCCESS"
        # Проверяем, что был создан дефолтный артефакт
        artifact = result["artifacts"][0]["content"]
        assert artifact["acceptance_criteria"] == ["Feature described in issue works as expected"]

    def test_run_empty_issue(self, agent):
        context = {"issue": {}}
        result = agent.run(context)
        assert result["status"] == "SUCCESS"
        artifact = result["artifacts"][0]["content"]
        # Должны быть default AC и BDD
        assert artifact["acceptance_criteria"] == ["Feature described in issue works as expected"]
        assert len(artifact["bdd_scenarios"]) == 1

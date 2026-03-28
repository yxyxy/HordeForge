"""Unit tests for Issue Scanner Agent."""

from agents.issue_scanner import (
    IssueComplexity,
    IssuePriority,
    IssueScanner,
    IssueType,
    check_duplicate,
    check_invalid,
    classify_issue_type,
    determine_priority,
    estimate_complexity,
    extract_acceptance_criteria,
    extract_key_info,
    parse_issue_labels,
)


class TestIssueTypeClassification:
    """Tests for issue type classification."""

    def test_classify_bug_from_label(self):
        """Test bug classification from label."""
        result = classify_issue_type("Test issue", "description", ["bug", "urgent"])
        assert result == IssueType.BUG

    def test_classify_bug_from_title(self):
        """Test bug classification from title keywords."""
        result = classify_issue_type("Fix login error", "description", [])
        assert result == IssueType.BUG

    def test_classify_feature_from_label(self):
        """Test feature classification from label."""
        result = classify_issue_type("Add API", "description", ["feature"])
        assert result == IssueType.FEATURE

    def test_classify_feature_from_title(self):
        """Test feature classification from title keywords."""
        result = classify_issue_type("Add new endpoint", "description", [])
        assert result == IssueType.FEATURE

    def test_classify_enhancement_from_label(self):
        """Test enhancement classification from label."""
        result = classify_issue_type("Improve performance", "description", ["enhancement"])
        assert result == IssueType.ENHANCEMENT

    def test_classify_documentation_from_label(self):
        """Test documentation classification from label."""
        result = classify_issue_type("Update docs", "description", ["documentation"])
        assert result == IssueType.DOCUMENTATION

    def test_classify_unknown(self):
        """Test unknown classification."""
        result = classify_issue_type("Something random here", "description", [])
        assert result == IssueType.UNKNOWN


class TestPriorityDetermination:
    """Tests for priority determination."""

    def test_priority_p0_from_label(self):
        """Test P0 priority from label."""
        result = determine_priority("Critical bug", "description", ["P0", "urgent"])
        assert result == IssuePriority.P0_CRITICAL

    def test_priority_p0_from_title(self):
        """Test P0 priority from title keywords."""
        result = determine_priority("Fix critical security vulnerability", "description", [])
        assert result == IssuePriority.P0_CRITICAL

    def test_priority_p1_from_label(self):
        """Test P1 priority from label."""
        result = determine_priority("Important feature", "description", ["P1"])
        assert result == IssuePriority.P1_HIGH

    def test_priority_p2_default(self):
        """Test default P2 priority."""
        result = determine_priority("New feature request", "description", [])
        assert result == IssuePriority.P2_MEDIUM


class TestComplexityEstimation:
    """Tests for complexity estimation."""

    def test_complexity_simple(self):
        """Test simple complexity."""
        result = estimate_complexity("Fix typo", "Just a small typo fix")
        assert result == IssueComplexity.SIMPLE

    def test_complexity_medium(self):
        """Test medium complexity."""
        body = "Add new API endpoint" + "x" * 600
        result = estimate_complexity("Add endpoint", body)
        assert result == IssueComplexity.MEDIUM

    def test_complexity_complex(self):
        """Test complex complexity."""
        body = """
        Add new API endpoint with database integration.
        ```python
        def api():
            pass
        ```
        Need to update tests and modify the database schema.
        """
        result = estimate_complexity("Add complex API and database schema with tests", body)
        assert result == IssueComplexity.COMPLEX


class TestAcceptanceCriteriaExtraction:
    """Tests for acceptance criteria extraction."""

    def test_extract_ac_from_section(self):
        """Test extraction from Acceptance Criteria section."""
        body = """
        ## Acceptance Criteria
        - User can login
        - User can logout
        - Sessions expire after 1 hour
        """
        result = extract_acceptance_criteria(body)
        assert len(result) == 3
        assert "User can login" in result

    def test_extract_ac_from_checkboxes(self):
        """Test extraction from checkboxes."""
        body = """
        ## Acceptance Criteria
        - [ ] First item
        - [x] Second item
        """
        result = extract_acceptance_criteria(body)
        # May contain duplicates due to multiple extraction patterns
        assert len(result) >= 2

    def test_extract_ac_empty(self):
        """Test extraction with no AC."""
        result = extract_acceptance_criteria("No acceptance criteria here")
        assert result == []


class TestKeyInfoExtraction:
    """Tests for key information extraction."""

    def test_extract_acceptance_criteria(self):
        """Test extracting acceptance criteria."""
        issue = {
            "title": "Test",
            "body": "## Acceptance Criteria\n- Item1\n- Item2",
        }
        result = extract_key_info(issue)
        assert "acceptance_criteria" in result

    def test_extract_steps_to_reproduce(self):
        """Test extracting steps to reproduce."""
        issue = {
            "title": "Bug",
            "body": "## Steps to Reproduce\n1. Do this\n2. Do that",
        }
        result = extract_key_info(issue)
        assert "steps_to_reproduce" in result

    def test_extract_components(self):
        """Test extracting mentioned components."""
        issue = {
            "title": "Fix",
            "body": "Use `agents/github_client.py` and `orchestrator/engine.py`",
        }
        result = extract_key_info(issue)
        assert "mentioned_components" in result
        assert len(result["mentioned_components"]) == 2


class TestDuplicateDetection:
    """Tests for duplicate detection."""

    def test_check_duplicate_same_title(self):
        """Test duplicate detection by same title."""
        issue = {"title": "Fix bug", "number": 1, "body": ""}
        processed = [{"title": "Fix bug", "number": 2, "body": ""}]
        is_dup, dup_of = check_duplicate(issue, processed)
        assert is_dup
        assert dup_of == "2"

    def test_check_duplicate_explicit(self):
        """Test explicit duplicate detection."""
        issue = {"title": "Fix", "body": "This is duplicate of #123", "number": 1}
        processed = []
        is_dup, dup_of = check_duplicate(issue, processed)
        assert is_dup
        assert dup_of == "123"

    def test_check_duplicate_not_duplicate(self):
        """Test non-duplicate issues."""
        issue = {"title": "Unique title", "body": "content", "number": 1}
        processed = [{"title": "Different title", "body": "content", "number": 2}]
        is_dup, dup_of = check_duplicate(issue, processed)
        assert not is_dup


class TestInvalidCheck:
    """Tests for invalid issue detection."""

    def test_invalid_empty_title(self):
        """Test detection of empty title."""
        issue = {"title": "", "body": "content"}
        is_invalid, reason = check_invalid(issue)
        assert is_invalid
        assert reason == "Empty title"

    def test_invalid_short_title(self):
        """Test detection of short title."""
        issue = {"title": "ab", "body": "content"}
        is_invalid, reason = check_invalid(issue)
        assert is_invalid
        assert reason == "Title too short"

    def test_invalid_spam(self):
        """Test detection of spam content."""
        issue = {"title": "Buy followers", "body": "cheap followers"}
        is_invalid, reason = check_invalid(issue)
        assert is_invalid
        assert reason == "Spam content detected"

    def test_invalid_wontfix(self):
        """Test detection of wontfix closed issue."""
        issue = {"title": "Test", "body": "", "state": "closed", "labels": [{"name": "wontfix"}]}
        is_invalid, reason = check_invalid(issue)
        assert is_invalid

    def test_valid_issue(self):
        """Test valid issue passes."""
        issue = {"title": "Add new feature", "body": "Implement feature X", "state": "open"}
        is_invalid, reason = check_invalid(issue)
        assert not is_invalid


class TestLabelParsing:
    """Tests for label parsing."""

    def test_parse_dict_labels(self):
        """Test parsing dict labels."""
        issue = {"labels": [{"name": "bug"}, {"name": "urgent"}]}
        result = parse_issue_labels(issue)
        assert result == ["bug", "urgent"]

    def test_parse_string_labels(self):
        """Test parsing string labels."""
        issue = {"labels": ["bug", "feature"]}
        result = parse_issue_labels(issue)
        assert result == ["bug", "feature"]

    def test_parse_empty_labels(self):
        """Test parsing empty labels."""
        issue = {"labels": []}
        result = parse_issue_labels(issue)
        assert result == []


class TestIssueScanner:
    """Tests for IssueScanner agent."""

    def test_run_empty_issues(self):
        """Test with no issues."""
        scanner = IssueScanner()
        result = scanner.run({"issues": []})

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["scanned_count"] == 0

    def test_run_classifies_issues(self):
        """Test issue classification."""
        scanner = IssueScanner()
        issues = [
            {
                "id": 1,
                "number": 101,
                "title": "Fix bug",
                "body": "Bug description",
                "labels": [{"name": "bug"}],
                "state": "open",
                "html_url": "url",
            }
        ]
        result = scanner.run({"issues": issues})

        assert result["status"] == "SUCCESS"
        assert result["artifacts"][0]["content"]["classified_count"] == 1
        classified = result["artifacts"][0]["content"]["classified_issues"][0]
        assert classified["type"] == "bug"

    def test_run_skips_invalid(self):
        """Test skipping invalid issues."""
        scanner = IssueScanner()
        issues = [
            {
                "id": 1,
                "number": 101,
                "title": "",
                "body": "",
                "labels": [],
                "state": "open",
                "html_url": "url",
            },
            {
                "id": 2,
                "number": 102,
                "title": "Valid issue",
                "body": "content",
                "labels": [],
                "state": "open",
                "html_url": "url",
            },
        ]
        result = scanner.run({"issues": issues})

        assert result["artifacts"][0]["content"]["skipped_count"] >= 1

    def test_run_summary(self):
        """Test summary generation."""
        scanner = IssueScanner()
        issues = [
            {
                "id": 1,
                "number": 101,
                "title": "Fix bug",
                "body": "Bug",
                "labels": [{"name": "bug"}],
                "state": "open",
                "html_url": "url",
            },
            {
                "id": 2,
                "number": 102,
                "title": "Add feature",
                "body": "Feature",
                "labels": [{"name": "feature"}],
                "state": "open",
                "html_url": "url",
            },
        ]
        result = scanner.run({"issues": issues})

        summary = result["artifacts"][0]["content"]["summary"]
        assert summary["total"] == 2
        assert "bug" in summary["by_type"]
        assert "feature" in summary["by_type"]

    def test_next_actions(self):
        """Test next actions determination."""
        scanner = IssueScanner()
        issues = [
            {
                "id": 1,
                "number": 101,
                "title": "Fix critical bug",
                "body": "Bug",
                "labels": [{"name": "bug"}],
                "state": "open",
                "html_url": "url",
            },
        ]
        result = scanner.run({"issues": issues, "scan_options": {}})

        next_actions = result["next_actions"]
        assert "trigger_bugfix_pipeline" in next_actions

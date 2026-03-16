"""Issue Scanner Agent - Scans and analyzes GitHub issues for classification and prioritization."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.context_utils import build_agent_result

logger = logging.getLogger("hordeforge.issue_scanner")


from agents.base import BaseAgent


class IssueType(Enum):
    """Issue types classification."""

    BUG = "bug"
    FEATURE = "feature"
    ENHANCEMENT = "enhancement"
    DOCUMENTATION = "documentation"
    QUESTION = "question"
    REFACTORING = "refactoring"
    UNKNOWN = "unknown"


class IssuePriority(Enum):
    """Issue priority levels."""

    P0_CRITICAL = "P0"
    P1_HIGH = "P1"
    P2_MEDIUM = "P2"
    P3_LOW = "P3"


class IssueComplexity(Enum):
    """Issue complexity estimation."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class ScannedIssue:
    """Represents a scanned and classified GitHub issue."""

    id: int
    number: int
    title: str
    body: str
    labels: list[str]
    issue_type: IssueType
    priority: IssuePriority
    complexity: IssueComplexity
    has_acceptance_criteria: bool = False
    is_duplicate: bool = False
    is_invalid: bool = False
    invalid_reason: str | None = None
    key_info: dict[str, Any] = field(default_factory=dict)


# Keywords for issue type classification
TYPE_KEYWORDS: dict[IssueType, list[str]] = {
    IssueType.BUG: [
        "bug",
        "fix",
        "error",
        "broken",
        "fail",
        "crash",
        "wrong",
        "incorrect",
        "unexpected",
        "issue",
        "defect",
    ],
    IssueType.FEATURE: [
        "add",
        "implement",
        "create",
        "new",
        "feature",
        "support",
        "enable",
    ],
    IssueType.ENHANCEMENT: [
        "improve",
        "enhance",
        "optimize",
        "refactor",
        "upgrade",
        "update",
        "better",
    ],
    IssueType.DOCUMENTATION: [
        "doc",
        "docs",
        "documentation",
        "readme",
        "guide",
        "comment",
        "example",
    ],
    IssueType.QUESTION: [
        "question",
        "how",
        "why",
        "what",
        "help",
        "?",
    ],
    IssueType.REFACTORING: [
        "refactor",
        "cleanup",
        "restructure",
        "reorganize",
    ],
}

# Priority indicators
PRIORITY_INDICATORS: dict[IssuePriority, list[str]] = {
    IssuePriority.P0_CRITICAL: [
        "critical",
        "urgent",
        "emergency",
        "security",
        "vulnerability",
        "breach",
        "data loss",
        "service down",
        "blocker",
        "p0",
    ],
    IssuePriority.P1_HIGH: [
        "important",
        "high priority",
        "major",
        "p1",
        "asap",
    ],
    IssuePriority.P2_MEDIUM: [
        "medium",
        "normal",
        "p2",
    ],
    IssuePriority.P3_LOW: [
        "low",
        "nice to have",
        "p3",
        "optional",
        "minor",
    ],
}


def classify_issue_type(title: str, body: str, labels: list[str]) -> IssueType:
    """Classify issue type based on title, body, and labels.

    Args:
        issue_title: Issue title
        issue_body: Issue body
        labels: Issue labels

    Returns:
        Classified IssueType
    """
    combined = f"{title} {body}".lower()
    labels_str = " ".join(labels).lower()

    # Check labels first (highest priority)
    for issue_type, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in labels_str:
                return issue_type

    # Check title and body
    for issue_type, keywords in TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in combined:
                return issue_type

    return IssueType.UNKNOWN


def determine_priority(title: str, body: str, labels: list[str]) -> IssuePriority:
    """Determine issue priority based on content and labels.

    Args:
        issue_title: Issue title
        issue_body: Issue body
        labels: Issue labels

    Returns:
        Determined IssuePriority
    """
    combined = f"{title} {body}".lower()
    labels_str = " ".join(labels).lower()

    # Check for priority indicators
    for priority, indicators in PRIORITY_INDICATORS.items():
        for indicator in indicators:
            if indicator in combined or indicator in labels_str:
                return priority

    return IssuePriority.P2_MEDIUM


def estimate_complexity(title: str, body: str) -> IssueComplexity:
    """Estimate issue complexity based on content.

    Args:
        issue_title: Issue title
        issue_body: Issue body

    Returns:
        Estimated IssueComplexity
    """
    # Check for complexity indicators
    body_length = len(body)
    has_code_blocks = "```" in body
    has_api_mention = "api" in body.lower() or "endpoint" in body.lower()
    has_database = "database" in body.lower() or "db" in body.lower()
    has_tests = "test" in body.lower()

    complexity_score = 0

    # Length factor
    if body_length > 1000:
        complexity_score += 2
    elif body_length > 500:
        complexity_score += 1

    # Technical complexity
    if has_code_blocks:
        complexity_score += 1
    if has_api_mention:
        complexity_score += 1
    if has_database:
        complexity_score += 1
    if has_tests:
        complexity_score += 1

    # Title complexity
    if " and " in title.lower() or " or " in title.lower():
        complexity_score += 1

    if complexity_score >= 4:
        return IssueComplexity.COMPLEX
    if complexity_score >= 2:
        return IssueComplexity.MEDIUM
    return IssueComplexity.SIMPLE


def extract_acceptance_criteria(body: str) -> list[str]:
    """Extract acceptance criteria from issue body.

    Args:
        issue_body: Issue body text

    Returns:
        List of acceptance criteria strings
    """
    if not body:
        return []

    criteria: list[str] = []

    # Look for Acceptance Criteria section
    ac_section_pattern = re.compile(
        r"(?:^|\n)\s*#+\s*Acceptance\s+Criteria\s*\n(.*?)(?=\n\s*#+\s*|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    ac_match = ac_section_pattern.search(body)

    if ac_match:
        ac_text = ac_match.group(1)

        # Extract bullet points
        bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
        for match in bullet_pattern.finditer(ac_text):
            criteria.append(match.group(1).strip())

        # Extract numbered items
        numbered_pattern = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)
        for match in numbered_pattern.finditer(ac_text):
            criteria.append(match.group(1).strip())

        # Extract checkboxes
        checklist_pattern = re.compile(r"^\s*-\s*\[\s*[xX]?\s*\]\s*(.+)$", re.MULTILINE)
        for match in checklist_pattern.finditer(ac_text):
            criteria.append(match.group(1).strip())

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for c in criteria:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def extract_key_info(issue: dict[str, Any]) -> dict[str, Any]:
    """Extract key information from issue.

    Args:
        issue: GitHub issue data

    Returns:
        Dictionary with extracted key information
    """
    body = issue.get("body", "") or issue.get("description", "")

    key_info: dict[str, Any] = {}

    # Extract acceptance criteria
    ac = extract_acceptance_criteria(body)
    if ac:
        key_info["acceptance_criteria"] = ac

    # Extract DoD (Definition of Done)
    dod_pattern = re.compile(
        r"(?:^|\n)#+\s*(?:Definition\s+of\s+Done|DoD)\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    dod_match = dod_pattern.search(body)
    if dod_match:
        key_info["definition_of_done"] = dod_match.group(1).strip()

    # Extract steps to reproduce (for bugs)
    steps_pattern = re.compile(
        r"(?:^|\n)#+\s*Steps?\s+to\s+Reproduce\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    steps_match = steps_pattern.search(body)
    if steps_match:
        key_info["steps_to_reproduce"] = steps_match.group(1).strip()

    # Extract expected/actual behavior
    expected_pattern = re.compile(
        r"(?:^|\n)#+\s*Expected\s+(?:Behavior|Result)\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    expected_match = expected_pattern.search(body)
    if expected_match:
        key_info["expected_behavior"] = expected_match.group(1).strip()

    actual_pattern = re.compile(
        r"(?:^|\n)#+\s*Actual\s+(?:Behavior|Result)\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    actual_match = actual_pattern.search(body)
    if actual_match:
        key_info["actual_behavior"] = actual_match.group(1).strip()

    # Extract environment info
    env_pattern = re.compile(
        r"(?:^|\n)#+\s*Environment\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    env_match = env_pattern.search(body)
    if env_match:
        key_info["environment"] = env_match.group(1).strip()

    # Extract mentioned files/components
    component_pattern = re.compile(r"`([^`]+)`")
    components = component_pattern.findall(body)
    if components:
        key_info["mentioned_components"] = list(set(components))

    return key_info


def check_duplicate(
    issue: dict[str, Any], processed_issues: list[dict[str, Any]]
) -> tuple[bool, str | None]:
    """Check if issue is a duplicate.

    Args:
        issue: Current issue
        processed_issues: List of previously processed issues

    Returns:
        Tuple of (is_duplicate, duplicate_of_number)
    """
    title = issue.get("title", "").lower()
    body = issue.get("body", "").lower()

    # Check if body contains "duplicate of #N" (explicit duplicate marker)
    if "duplicate" in body and "#" in body:
        dup_pattern = re.compile(r"duplicate\s+of\s+#(\d+)", re.IGNORECASE)
        match = dup_pattern.search(body)
        if match:
            return True, match.group(1)

    # Check against previously processed issues
    for processed in processed_issues:
        processed_title = processed.get("title", "").lower()
        # Check title similarity (simple approach)
        if title == processed_title:
            return True, str(processed.get("number", ""))

    return False, None


def check_invalid(issue: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if issue is invalid or should be skipped.

    Args:
        issue: GitHub issue data

    Returns:
        Tuple of (is_invalid, reason)
    """
    title = issue.get("title", "").strip()
    body = issue.get("body", "") or issue.get("description", "")

    # Check for empty title
    if not title:
        return True, "Empty title"

    # Check for very short title
    if len(title) < 5:
        return True, "Title too short"

    # Check for spam-like content
    spam_patterns = [
        r"buy\s+followers",
        r"cheap\s+followers",
        r"click\s+here",
        r"earn\s+money\s+online",
    ]
    combined = f"{title} {body}".lower()
    for pattern in spam_patterns:
        if re.search(pattern, combined):
            return True, "Spam content detected"

    # Check for wontfix/duplicate closed issues
    state = issue.get("state", "open")
    if state == "closed":
        labels = issue.get("labels", [])
        label_names = [
            label.get("name", "") if isinstance(label, dict) else str(label) for label in labels
        ]
        if "wontfix" in label_names or "duplicate" in label_names:
            return True, "Closed as wontfix/duplicate"

    return False, None


def parse_issue_labels(issue: dict[str, Any]) -> list[str]:
    """Parse labels from issue data.

    Args:
        issue: GitHub issue data

    Returns:
        List of label names
    """
    labels = issue.get("labels", [])
    if not labels:
        return []

    label_names = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name", "")
            if name:
                label_names.append(name)
        elif isinstance(label, str):
            label_names.append(label)

    return label_names


class IssueScanner(BaseAgent):
    """Issue Scanner Agent - Scans and analyzes GitHub issues."""

    name = "issue_scanner"
    description = "Scans and analyzes GitHub issues for classification and prioritization"

    def __init__(self) -> None:
        self._processed_issue_ids: set[int] = set()

    def run(self, context: dict[str, Any]) -> dict:
        """Run issue scanning and analysis.

        Args:
            context: Execution context with GitHub client and options

        Returns:
            Agent result with scanned issues and analysis
        """
        # Get GitHub client from context
        github_client = context.get("github_client")
        repo = context.get("repo", "")
        options = context.get("scan_options", {})

        # Get scan parameters
        state = options.get("state", "open")
        labels_filter = options.get("labels", [])
        since = options.get("since")
        max_issues = options.get("max_issues", 50)

        # Get previously processed issues for duplicate detection
        processed_issues = context.get("processed_issues", [])

        # Fetch issues from GitHub or use provided issues
        issues = context.get("issues", [])

        if github_client and not issues:
            try:
                result = github_client.get_issues(
                    state=state,
                    labels=",".join(labels_filter) if labels_filter else None,
                    since=since,
                    per_page=min(max_issues, 100),
                )
                issues = result.get("issues", [])
            except Exception as e:
                logger.error(f"Failed to fetch issues: {e}")
                return build_agent_result(
                    status="FAILURE",
                    artifact_type="issue_scan",
                    artifact_content={},
                    reason=f"Failed to fetch issues: {str(e)}",
                    confidence=0.0,
                    logs=[f"GitHub API error: {str(e)}"],
                    next_actions=[],
                )

        if not issues:
            return build_agent_result(
                status="SUCCESS",
                artifact_type="issue_scan",
                artifact_content={
                    "scanned_count": 0,
                    "classified_issues": [],
                    "summary": {"total": 0, "by_type": {}, "by_priority": {}},
                },
                reason="No issues found to scan",
                confidence=1.0,
                logs=["No issues to scan"],
                next_actions=[],
            )

        # Scan and classify each issue
        classified_issues: list[dict[str, Any]] = []
        skipped_issues: list[dict[str, Any]] = []
        logs: list[str] = []

        for issue in issues:
            if not isinstance(issue, dict):
                continue

            issue_id = issue.get("id")
            if not isinstance(issue_id, int):
                continue

            # Skip already processed issues
            if issue_id in self._processed_issue_ids:
                skipped_issues.append({"id": issue_id, "reason": "already_processed"})
                continue

            # Check if invalid
            is_invalid, invalid_reason = check_invalid(issue)
            if is_invalid:
                self._processed_issue_ids.add(issue_id)
                skipped_issues.append({"id": issue_id, "reason": invalid_reason})
                continue

            # Check for duplicates
            is_duplicate, duplicate_of = check_duplicate(issue, processed_issues)
            if is_duplicate:
                self._processed_issue_ids.add(issue_id)
                skipped_issues.append({"id": issue_id, "reason": f"duplicate_of #{duplicate_of}"})
                continue

            # Parse labels
            labels = parse_issue_labels(issue)

            # Classify issue
            title = issue.get("title", "")
            body = issue.get("body", "") or issue.get("description", "")

            issue_type = classify_issue_type(title, body, labels)
            priority = determine_priority(title, body, labels)
            complexity = estimate_complexity(title, body)

            # Extract key information
            key_info = extract_key_info(issue)

            # Check for acceptance criteria
            has_ac = bool(key_info.get("acceptance_criteria"))

            # Create scanned issue object
            scanned = ScannedIssue(
                id=issue_id,
                number=issue.get("number", 0),
                title=title,
                body=body,
                labels=labels,
                issue_type=issue_type,
                priority=priority,
                complexity=complexity,
                has_acceptance_criteria=has_ac,
                key_info=key_info,
            )

            # Mark as processed
            self._processed_issue_ids.add(issue_id)

            # Convert to dict for output
            classified_issues.append(
                {
                    "id": scanned.id,
                    "number": scanned.number,
                    "title": scanned.title,
                    "type": scanned.issue_type.value,
                    "priority": scanned.priority.value,
                    "complexity": scanned.complexity.value,
                    "has_acceptance_criteria": scanned.has_acceptance_criteria,
                    "labels": scanned.labels,
                    "key_info": scanned.key_info,
                    "url": issue.get(
                        "html_url", f"https://github.com/{repo}/issues/{scanned.number}"
                    ),
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                }
            )

        # Build summary
        summary = self._build_summary(classified_issues)

        # Determine next actions based on found issues
        next_actions = self._determine_next_actions(classified_issues, options)

        logs.append(f"Scanned {len(issues)} issues")
        logs.append(f"Classified {len(classified_issues)} issues")
        logs.append(f"Skipped {len(skipped_issues)} issues")
        logs.append(f"Types: {summary['by_type']}")
        logs.append(f"Priorities: {summary['by_priority']}")

        return build_agent_result(
            status="SUCCESS",
            artifact_type="issue_scan",
            artifact_content={
                "scanned_count": len(issues),
                "classified_count": len(classified_issues),
                "skipped_count": len(skipped_issues),
                "classified_issues": classified_issues,
                "skipped_issues": skipped_issues,
                "summary": summary,
            },
            reason=f"Scanned and classified {len(classified_issues)} issues",
            confidence=0.9,
            logs=logs,
            next_actions=next_actions,
        )

    def _build_summary(self, issues: list[dict[str, Any]]) -> dict[str, Any]:
        """Build summary statistics from classified issues.

        Args:
            issues: List of classified issues

        Returns:
            Summary dictionary
        """
        by_type: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        by_complexity: dict[str, int] = {}
        with_ac = 0
        without_ac = 0

        for issue in issues:
            issue_type = issue.get("type", "unknown")
            priority = issue.get("priority", "P2")
            complexity = issue.get("complexity", "simple")

            by_type[issue_type] = by_type.get(issue_type, 0) + 1
            by_priority[priority] = by_priority.get(priority, 0) + 1
            by_complexity[complexity] = by_complexity.get(complexity, 0) + 1

            if issue.get("has_acceptance_criteria"):
                with_ac += 1
            else:
                without_ac += 1

        return {
            "total": len(issues),
            "by_type": by_type,
            "by_priority": by_priority,
            "by_complexity": by_complexity,
            "with_acceptance_criteria": with_ac,
            "without_acceptance_criteria": without_ac,
        }

    def _determine_next_actions(
        self,
        issues: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> list[str]:
        """Determine next actions based on scanned issues.

        Args:
            issues: List of classified issues
            options: Scan options

        Returns:
            List of next action names
        """
        if not issues:
            return []

        next_actions = []

        # Check for high priority bugs
        has_critical_bugs = any(
            i.get("type") == "bug" and i.get("priority") == "P0" for i in issues
        )
        if has_critical_bugs:
            next_actions.append("trigger_bugfix_pipeline")

        # Check for features
        has_features = any(i.get("type") == "feature" for i in issues)
        if has_features:
            next_actions.append("trigger_feature_pipeline")

        # Check for issues without acceptance criteria
        needs_dod = any(not i.get("has_acceptance_criteria") for i in issues)
        if needs_dod:
            next_actions.append("dod_extractor")

        return next_actions

    def reset_processed(self) -> None:
        """Reset the set of processed issue IDs."""
        self._processed_issue_ids.clear()

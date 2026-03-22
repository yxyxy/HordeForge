"""DoD Extractor Agent - Generates acceptance criteria and BDD scenarios."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


@dataclass
class IssueData:
    """Represents parsed GitHub issue data."""

    title: str = ""
    description: str = ""
    labels: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


def extract_acceptance_criteria(text: str) -> list[str]:
    """Extract acceptance criteria from markdown text."""

    if not text:
        return []

    criteria: list[str] = []

    ac_section_pattern = re.compile(
        r"(?:^|\n)#+\s*Acceptance\s+Criteria\s*\n(.*?)(?=\n#+|\n---|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    ac_match = ac_section_pattern.search(text)

    if ac_match:
        ac_text = ac_match.group(1)

        bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
        for match in bullet_pattern.finditer(ac_text):
            criteria.append(match.group(1).strip())

    numbered_pattern = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)

    for match in numbered_pattern.finditer(text):
        criteria.append(match.group(1).strip())

    checklist_pattern = re.compile(r"^\s*-\s*\[\s*[xX]?\s*\]\s*(.+)$", re.MULTILINE)

    for match in checklist_pattern.finditer(text):
        criteria.append(match.group(1).strip())

    if not criteria:
        bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)

        for match in bullet_pattern.finditer(text):
            item = match.group(1).strip()

            if len(item) > 5:
                criteria.append(item)

    seen = set()
    unique: list[str] = []

    for c in criteria:
        key = c.lower()

        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def parse_issue(issue_data: dict[str, Any]) -> IssueData:
    """Parse GitHub issue."""

    title = issue_data.get("title", "")
    body = issue_data.get("body", "") or issue_data.get("description", "")

    labels: list[str] = []

    if "labels" in issue_data:
        raw_labels = issue_data["labels"]

        if isinstance(raw_labels, list):
            for label in raw_labels:
                if isinstance(label, dict):
                    labels.append(label.get("name", ""))
                elif isinstance(label, str):
                    labels.append(label)

        elif isinstance(raw_labels, str):
            labels.append(raw_labels)

    ac = extract_acceptance_criteria(body)

    return IssueData(
        title=title,
        description=body,
        labels=labels,
        acceptance_criteria=ac,
    )


def build_dod_prompt(issue: IssueData) -> str:
    """Build LLM prompt for DoD generation."""

    return f"""
You are a senior software architect.

Analyze the following issue and generate:

1. Acceptance Criteria
2. BDD scenarios

Return ONLY JSON.

Issue title:
{issue.title}

Issue description:
{issue.description}

JSON format:

{{
 "acceptance_criteria": ["..."],
 "bdd_scenarios": [
   {{
     "given": "...",
     "when": "...",
     "then": "..."
   }}
 ]
}}

Rules:
- Minimum 1 acceptance criteria
- Minimum 1 BDD scenario
- BDD must follow Given / When / Then
"""


def call_llm(prompt: str) -> dict[str, Any]:
    """
    Placeholder LLM call.

    Replace with HordeForge LLM connector.
    """

    # TODO integrate cline / model gateway
    raise NotImplementedError("LLM connector not implemented")


def generate_bdd_from_ac(ac: list[str]) -> list[dict[str, str]]:
    """Generate simple BDD scenarios from acceptance criteria."""

    scenarios: list[dict[str, str]] = []

    for criterion in ac:
        scenarios.append(
            {
                "given": "system is running",
                "when": criterion.lower(),
                "then": "expected behavior occurs",
            }
        )

    return scenarios


def validate_contract(result: dict[str, Any]) -> bool:
    """Basic validation for DoD contract."""

    if result.get("schema_version") != "1.0":
        return False

    if not result.get("acceptance_criteria"):
        return False

    if not result.get("bdd_scenarios"):
        return False

    return True


class DodExtractor(BaseAgent):
    """DoD Extractor Agent."""

    name = "dod_extractor"
    description = "Generates acceptance criteria and BDD scenarios."

    def run(self, context: dict) -> dict:
        issue = context.get("issue")

        if issue is None:  # Only fail if the 'issue' key is missing entirely
            result = build_agent_result(
                status="FAILURE",
                artifact_type="dod",
                artifact_content={},
                reason="No issue data provided",
                confidence=0.0,
                logs=["missing issue context"],
                next_actions=[],
            )
            # Добавляем прямые ключи для совместимости с ожиданиями тестов
            result["reason"] = "No issue data provided"
            return result

        parsed = parse_issue(issue)

        logs: list[str] = []

        method = "deterministic"

        ac = parsed.acceptance_criteria

        bdd: list[dict[str, str]] = []

        if ac:
            logs.append(f"deterministic extraction found {len(ac)} AC")
            bdd = generate_bdd_from_ac(ac)
        else:
            logs.append("no acceptance criteria found, using defaults")
            # When no AC found and no LLM available, use defaults
            ac = ["Feature described in issue works as expected"]
            bdd = generate_bdd_from_ac(ac)
            method = "default_fallback"

        # Ensure we have at least one acceptance criterion
        if not ac:
            ac = ["Feature described in issue works as expected"]

        # Ensure we have at least one BDD scenario
        if not bdd:
            bdd = generate_bdd_from_ac(ac)
            if method == "llm":
                method = "deterministic_fallback"

        artifact = {
            "schema_version": "1.0",
            "title": parsed.title,
            "acceptance_criteria": ac,
            "bdd_scenarios": bdd,
            "extraction_method": method,
        }

        if not validate_contract(artifact):
            return build_agent_result(
                status="FAILURE",
                artifact_type="dod",
                artifact_content={},
                reason="contract validation failed",
                confidence=0.1,
                logs=["schema validation failed"],
                next_actions=[],
            )

        logs.append(f"generated {len(ac)} acceptance criteria")
        logs.append(f"generated {len(bdd)} bdd scenarios")

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="dod",
            artifact_content=artifact,
            reason="DoD generated successfully",
            confidence=0.9 if method != "llm" else 0.8,
            logs=logs,
            next_actions=["task_decomposer"],
        )

        # Добавляем прямые ключи для совместимости с ожиданиями тестов
        result["artifact_type"] = "dod"
        result["artifact_content"] = artifact

        return result


DoDExtractor = DodExtractor

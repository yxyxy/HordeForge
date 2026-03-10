# =========================================================================
# DoD Extraction (HF-P6-002)
# =========================================================================

from __future__ import annotations

import json
import re
from typing import Any

from agents.context_utils import build_agent_result

# Prompt for LLM-based DoD extraction (HF-P6-002-ST02)
DOD_EXTRACTION_PROMPT = """You are an expert at extracting Definition of Done (DoD) from GitHub issues.

## Task
Analyze the following GitHub issue and extract a comprehensive Definition of Done.

## Issue Title
{title}

## Issue Body
{body}

## Instructions
1. Extract clear, testable acceptance criteria
2. Identify any BDD scenarios (Given/When/Then format)
3. Note any specific requirements or constraints
4. Consider edge cases and error conditions

## Output Format (JSON)
{{
    "acceptance_criteria": [
        "Criterion 1 - must be testable",
        "Criterion 2"
    ],
    "bdd_scenarios": [
        {{
            "scenario": "Scenario name",
            "given": "Given condition",
            "when": "When action",
            "then": "Then expected result"
        }}
    ],
    "test_hints": [
        "What tests should be written"
    ],
    "confidence": 0.0-1.0
}}

Respond with valid JSON only, no markdown."""


def build_dod_prompt(title: str, body: str) -> str:
    """Build prompt for DoD extraction.

    Args:
        title: Issue title
        body: Issue body

    Returns:
        Formatted prompt string
    """
    return DOD_EXTRACTION_PROMPT.format(
        title=title or "No title",
        body=body or "No description provided",
    )


def parse_llm_dod_response(response: str) -> dict[str, Any]:
    """Parse LLM response into DoD structure.

    Args:
        response: Raw LLM response

    Returns:
        Parsed DoD dict

    Raises:
        ValueError: If response cannot be parsed
    """
    # Try to extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        raise ValueError("No JSON found in LLM response")

    json_str = json_match.group(0)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in LLM response: {e}") from e

    # Ensure required fields
    if "acceptance_criteria" not in parsed:
        parsed["acceptance_criteria"] = []
    if "bdd_scenarios" not in parsed:
        parsed["bdd_scenarios"] = []

    return parsed


def extract_acceptance_criteria_from_markdown(body: str) -> list[str]:
    """Extract acceptance criteria from markdown formats.

    Args:
        body: Issue body text

    Returns:
        List of acceptance criteria
    """
    criteria = []

    # Extract from checklists: - [ ] or - [x]
    checklist_pattern = re.compile(r"^\s*-\s*\[\s*[xX]?\s*\]\s*(.+)$", re.MULTILINE)
    for match in checklist_pattern.finditer(body):
        criteria.append(match.group(1).strip())

    # Extract from numbered lists under "Acceptance Criteria" header
    ac_section_pattern = re.compile(
        r"(?:^|\n)##?\s*(?:Acceptance\s+Criteria|Acceptance\s+criteria|AC)\s*\n(.*?)(?=\n##|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    ac_match = ac_section_pattern.search(body)
    if ac_match:
        ac_text = ac_match.group(1)
        numbered_pattern = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)
        for match in numbered_pattern.finditer(ac_text):
            criteria.append(match.group(1).strip())

    # Extract from bullet points
    bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
    for match in bullet_pattern.finditer(body):
        text = match.group(1).strip()
        if len(text) > 10:  # Filter out short bullets
            criteria.append(text)

    return criteria


def extract_bdd_scenarios_from_markdown(body: str) -> list[dict[str, str]]:
    """Extract BDD scenarios from Gherkin format.

    Args:
        body: Issue body text

    Returns:
        List of BDD scenario dicts
    """
    scenarios = []

    # Gherkin-style: ## Scenario or ### Scenario
    scenario_pattern = re.compile(
        r"(?:^|\n)(##+|)\s*[Ss]cenario:?\s*(.+?)(?=\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    # Find all Scenario sections
    for match in scenario_pattern.finditer(body):
        scenario_name = match.group(2).strip()
        section_start = match.end()

        # Find next Scenario or end
        next_match = re.search(r"(?:^|\n)(##+|)\s*[Ss]cenario:", body[section_start:])
        if next_match:
            section_text = body[section_start : section_start + next_match.start()]
        else:
            section_text = body[section_start:]

        # Extract Given/When/Then
        given_match = re.search(r"Given\s+(.+?)(?:\n|$)", section_text, re.IGNORECASE)
        when_match = re.search(r"When\s+(.+?)(?:\n|$)", section_text, re.IGNORECASE)
        then_match = re.search(r"Then\s+(.+?)(?:\n|$)", section_text, re.IGNORECASE)

        if given_match or when_match or then_match:
            scenarios.append({
                "scenario": scenario_name,
                "given": given_match.group(1).strip() if given_match else "",
                "when": when_match.group(1).strip() if when_match else "",
                "then": then_match.group(1).strip() if then_match else "",
            })

    return scenarios


class DodExtractor:
    name = "dod_extractor"
    description = "Extracts Definition of Done from issue context using LLM when available."

    def __init__(self, llm_wrapper=None):
        """Initialize DodExtractor with optional LLM wrapper.

        Args:
            llm_wrapper: Optional LLM wrapper for enhanced extraction
        """
        self._llm = llm_wrapper

    def _extract_with_llm(self, title: str, body: str) -> dict[str, Any]:
        """Extract DoD using LLM.

        Args:
            title: Issue title
            body: Issue body

        Returns:
            Parsed DoD from LLM

        Raises:
            RuntimeError: If LLM extraction fails
        """
        if self._llm is None:
            # Try to get LLM wrapper
            try:
                from agents.llm_wrapper import get_llm_wrapper

                self._llm = get_llm_wrapper()
            except Exception:  # noqa: BLE001
                pass

        if self._llm is None:
            raise RuntimeError("No LLM wrapper available")

        prompt = build_dod_prompt(title, body)
        response = self._llm.complete(prompt)
        return parse_llm_dod_response(response)

    def run(self, context: dict) -> dict:
        issue = context.get("issue") or {}
        issue_title = ""
        issue_text = ""

        if isinstance(issue, dict):
            issue_title = issue.get("title", "")
            issue_text = issue.get("description", "") or issue.get("body", "")
        elif isinstance(issue, str):
            issue_text = issue

        # Try LLM extraction first
        llm_extraction_failed = False
        llm_result = None

        if issue_text:
            try:
                llm_result = self._extract_with_llm(issue_title, issue_text)
            except Exception:  # noqa: BLE001
                llm_extraction_failed = True

        # Fallback to deterministic extraction
        criteria = []
        bdd_scenarios = []

        if llm_result:
            criteria = llm_result.get("acceptance_criteria", [])
            bdd_scenarios = llm_result.get("bdd_scenarios", [])
            confidence = llm_result.get("confidence", 0.85)
            extraction_method = "llm"
        else:
            # Deterministic extraction from markdown
            criteria = extract_acceptance_criteria_from_markdown(issue_text)
            bdd_scenarios = extract_bdd_scenarios_from_markdown(issue_text)

            if not criteria:
                criteria = [
                    "Implementation exists and matches issue intent.",
                    "Basic tests are present and executable.",
                    "No obvious regressions introduced by the change.",
                ]

            confidence = 0.72 if llm_extraction_failed else 0.85
            extraction_method = "deterministic_fallback" if llm_extraction_failed else "deterministic"

        # Add note about extraction if we had issue text and criteria came from fallback
        if issue_text and (extraction_method.startswith("deterministic") or not criteria):
            if "Acceptance criteria extracted from issue body." not in criteria:
                criteria.append("Acceptance criteria extracted from issue body.")

        return build_agent_result(
            status="SUCCESS",
            artifact_type="dod",
            artifact_content={
                "schema_version": "1.0",
                "title": issue_title,
                "acceptance_criteria": criteria,
                "bdd_scenarios": bdd_scenarios,
                "extraction_method": extraction_method,
            },
            reason=f"DoD extracted using {extraction_method} logic.",
            confidence=confidence,
            logs=[f"DoD extracted using {extraction_method} method."],
            next_actions=["specification_writer"],
        )


# Backward-compatible alias for earlier naming.
DoDExtractor = DodExtractor


# Backward-compatible alias for earlier naming.
DoDExtractor = DodExtractor

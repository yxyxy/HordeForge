"""BDD Generator Agent - Generates BDD scenarios in Gherkin format.

Stage-1 improvements:
- builds from acceptance criteria when available
- supports technical/repair-friendly fallback phrasing
- stricter passthrough validation
- adds quality/specificity metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class BDDComponentType(Enum):
    """Types of BDD components that can be generated."""

    FEATURE = "feature"
    SCENARIO = "scenario"
    STEP_DEFINITION = "step_definition"


@dataclass
class BDDScenario:
    """Represents a BDD scenario in Gherkin format."""

    title: str
    given: str
    when: str
    then: str
    and_steps: list[str] = field(default_factory=list)
    scenario_type: str = "success"


@dataclass
class BDDFeature:
    """Represents a BDD feature in Gherkin format."""

    title: str
    description: str
    scenarios: list[BDDScenario] = field(default_factory=list)
    background: str = ""


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _extract_feature_name(feature_description: str) -> str:
    feature = feature_description
    for token in ["Add", "Implement", "Create", "Fix", "Update", "Improve"]:
        feature = feature.replace(token, "")
    feature = feature.split(".")[0].strip() or feature_description

    words = feature.split()
    stop_words = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "by"}
    acronyms = {"api", "jwt", "ui", "ci", "cd", "sql"}
    capitalized_words: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in stop_words:
            continue
        if lowered in acronyms:
            capitalized_words.append(lowered.upper())
        else:
            capitalized_words.append(word.capitalize())
    return " ".join(capitalized_words) or "Feature"


def _extract_spec_mode(feature_description: str, labels: list[str]) -> str:
    combined = f"{feature_description} {' '.join(labels)}".lower()
    if (
        "ci incident" in combined
        or "kind:ci-incident" in combined
        or "source:ci_scanner_pipeline" in combined
    ):
        return "ci_incident"
    if any(token in combined for token in ["bug", "fix", "regression", "failure", "error"]):
        return "bugfix"
    if any(token in combined for token in ["infra", "config", "workflow", "pipeline", "docker"]):
        return "infra"
    return "feature"


def _generate_feature_description(feature_description: str, spec_mode: str) -> str:
    feature_lower = feature_description.lower()
    if spec_mode == "feature":
        if any(word in feature_lower for word in ["user", "customer", "client"]):
            role = "user"
        elif any(word in feature_lower for word in ["admin", "administrator", "manager"]):
            role = "administrator"
        elif any(word in feature_lower for word in ["api", "service", "endpoint"]):
            role = "developer"
        else:
            role = "user"
        return (
            f"As a {role},\n"
            f"  I want to {feature_description.lower()},\n"
            "  So that I can achieve the expected outcome"
        )

    if spec_mode == "ci_incident":
        return (
            "In order to restore CI stability,\n"
            "  the failing path must be reproduced, fixed, and verified,\n"
            "  so that the affected checks pass again"
        )

    if spec_mode == "bugfix":
        return (
            "In order to restore expected behaviour,\n"
            "  the failing scenario must be corrected without broad regressions,\n"
            "  so that the system behaves predictably again"
        )

    return (
        "In order to implement the requested technical change,\n"
        "  the affected components must be updated safely,\n"
        "  so that the system remains stable"
    )


def _build_scenarios_from_criteria(criteria: list[str], spec_mode: str) -> list[BDDScenario]:
    scenarios: list[BDDScenario] = []
    for index, criterion in enumerate(criteria, start=1):
        title = criterion.rstrip(".")
        if spec_mode == "ci_incident":
            scenarios.append(
                BDDScenario(
                    title=f"Repair criterion {index}: {title}",
                    given="the failing CI job and relevant test context are available",
                    when=f"the fix is applied to satisfy: {title}",
                    then="the affected CI checks pass without introducing new failures",
                    and_steps=["regression coverage is updated where needed"],
                    scenario_type="success",
                )
            )
        elif spec_mode == "bugfix":
            scenarios.append(
                BDDScenario(
                    title=f"Regression criterion {index}: {title}",
                    given="the original failing scenario is reproducible",
                    when=f"the implementation satisfies: {title}",
                    then="the defect no longer reproduces",
                    and_steps=["existing expected behaviour remains intact"],
                    scenario_type="success",
                )
            )
        else:
            scenarios.append(
                BDDScenario(
                    title=f"Acceptance criterion {index}: {title}",
                    given="the relevant preconditions are met",
                    when=f"the user or system performs the action for: {title}",
                    then="the expected outcome is observed",
                    and_steps=[],
                    scenario_type="success",
                )
            )
    return scenarios


def _generate_default_scenarios(feature_description: str, spec_mode: str) -> list[BDDScenario]:
    feature_lower = feature_description.lower()
    if spec_mode == "ci_incident":
        return [
            BDDScenario(
                title="Reproduce the failing CI job",
                given="the failing workflow and artifacts are available",
                when="the affected job is rerun in isolated mode",
                then="the original failure is reproduced deterministically",
                scenario_type="success",
            ),
            BDDScenario(
                title="Verify the repair",
                given="a targeted fix has been applied",
                when="the affected checks are executed again",
                then="the previously failing checks pass",
                and_steps=["no new regression is introduced in nearby checks"],
                scenario_type="failure",
            ),
        ]

    if spec_mode == "bugfix":
        return [
            BDDScenario(
                title="Confirm the bug is fixed",
                given="the original failing case exists",
                when="the corrected implementation is executed",
                then="the incorrect behaviour no longer appears",
                scenario_type="success",
            ),
            BDDScenario(
                title="Guard against regressions",
                given="the fix is present",
                when="related behaviour is exercised",
                then="existing behaviour remains unchanged",
                scenario_type="failure",
            ),
        ]

    if any(word in feature_lower for word in ["login", "authenticate", "access"]):
        return [
            BDDScenario(
                title="Successful Login",
                given="I have valid login credentials",
                when="I enter my username and password",
                then="I am logged in successfully",
                and_steps=["I am redirected to my dashboard", "My session is created"],
            ),
            BDDScenario(
                title="Failed Login",
                given="I have invalid login credentials",
                when="I enter incorrect username or password",
                then="authentication fails",
                and_steps=["an error message is displayed", "my session is not created"],
                scenario_type="failure",
            ),
        ]

    if any(word in feature_lower for word in ["api", "endpoint", "service"]):
        return [
            BDDScenario(
                title="Successful execution",
                given="the service is reachable and inputs are valid",
                when="the operation is invoked",
                then="the expected response is returned",
            ),
            BDDScenario(
                title="Handles invalid input",
                given="the service receives invalid input",
                when="validation is triggered",
                then="a controlled error is returned",
                scenario_type="failure",
            ),
            BDDScenario(
                title="Rate limiting under load",
                given="request volume exceeds the configured threshold",
                when="additional requests arrive",
                then="requests are throttled gracefully",
                scenario_type="edge_case",
            ),
        ]

    return [
        BDDScenario(
            title="Successful execution",
            given="the relevant preconditions are met",
            when="the action is performed",
            then="the action completes successfully",
        ),
        BDDScenario(
            title="Failed execution",
            given="a blocking condition exists",
            when="the action is attempted",
            then="the system rejects the action safely",
            scenario_type="failure",
        ),
    ]


def generate_gherkin_feature(
    feature_description: str, scenarios: list[BDDScenario], spec_mode: str
) -> str:
    feature_name = _extract_feature_name(feature_description)
    feature_desc = _generate_feature_description(feature_description, spec_mode)
    gherkin = f"Feature: {feature_name}\n"
    gherkin += f"  {feature_desc}\n\n"
    for index, scenario in enumerate(scenarios):
        gherkin += f"  Scenario: {scenario.title}\n"
        gherkin += f"    Given {scenario.given}\n"
        gherkin += f"    When {scenario.when}\n"
        gherkin += f"    Then {scenario.then}\n"
        for and_step in scenario.and_steps:
            gherkin += f"    And {and_step}\n"
        if index < len(scenarios) - 1:
            gherkin += "\n"
    return gherkin


def generate_scenario(
    feature: str, scenario_type: str = "success", spec_mode: str = "feature"
) -> str:
    scenarios = _generate_default_scenarios(feature, spec_mode)
    for scenario in scenarios:
        if scenario.scenario_type == scenario_type:
            lines = [
                f"Given {scenario.given}",
                f"When {scenario.when}",
                f"Then {scenario.then}",
            ]
            lines.extend(f"And {step}" for step in scenario.and_steps)
            return "\n".join(lines)
    scenario = scenarios[0]
    return f"Given {scenario.given}\nWhen {scenario.when}\nThen {scenario.then}"


class BDDGenerator(BaseAgent):
    """BDD Generator Agent - Generates BDD scenarios in Gherkin format."""

    name = "bdd_generator"
    description = "Generates BDD scenarios in Gherkin format with Given-When-Then structure."

    def run(self, context: dict) -> dict:
        existing_bdd = context.get("bdd_specification")
        if isinstance(existing_bdd, dict) and (
            _normalize_text(existing_bdd.get("gherkin_feature"))
            or (isinstance(existing_bdd.get("scenarios"), dict) and existing_bdd.get("scenarios"))
        ):
            passthrough_content = dict(existing_bdd)
            passthrough_content.setdefault(
                "quality_signals",
                {
                    "scenario_count": len(passthrough_content.get("scenarios", {})),
                    "specificity": "high"
                    if _normalize_text(passthrough_content.get("gherkin_feature"))
                    else "medium",
                },
            )
            passthrough_content.setdefault(
                "plan_provenance",
                {
                    "source": context.get("plan_source", "upstream_pipeline"),
                    "passthrough": True,
                    "rebuilt": False,
                },
            )
            return build_agent_result(
                status="SUCCESS",
                artifact_type="bdd_specification",
                artifact_content=passthrough_content,
                reason="BDD specification passed through from upstream pipeline.",
                confidence=0.95,
                logs=["BDD specification reused from upstream pipeline (passthrough mode)."],
                next_actions=["test_generator"],
            )

        issue = context.get("issue", {}) if isinstance(context.get("issue"), dict) else {}
        spec = context.get("spec") if isinstance(context.get("spec"), dict) else {}
        feature_description = _normalize_text(
            issue.get("title") or context.get("feature_description")
        )
        if not feature_description and isinstance(spec, dict):
            feature_description = _normalize_text(
                spec.get("summary") or spec.get("feature_description")
            )

        if not feature_description:
            return build_agent_result(
                status="FAILED",
                artifact_type="bdd_specification",
                artifact_content={},
                reason="No feature description provided in context.",
                confidence=1.0,
                logs=["No feature description found in issue or specification context."],
                next_actions=["specification_writer", "request_human_input"],
            )

        labels: list[str] = []
        raw_labels = issue.get("labels", [])
        if isinstance(raw_labels, list):
            for label in raw_labels:
                labels.append(
                    _normalize_text(label.get("name") if isinstance(label, dict) else label)
                )

        acceptance_criteria = []
        dod = context.get("dod") if isinstance(context.get("dod"), dict) else {}
        if isinstance(spec, dict):
            acceptance_criteria.extend(_coerce_list(spec.get("acceptance_criteria")))
        if isinstance(dod, dict):
            acceptance_criteria.extend(_coerce_list(dod.get("acceptance_criteria")))
        acceptance_criteria = _coerce_list(acceptance_criteria)

        spec_mode = _extract_spec_mode(feature_description, labels)
        scenarios = (
            _build_scenarios_from_criteria(acceptance_criteria, spec_mode)
            if acceptance_criteria
            else _generate_default_scenarios(feature_description, spec_mode)
        )
        gherkin_feature = generate_gherkin_feature(feature_description, scenarios, spec_mode)

        scenario_map = {
            scenario.scenario_type: generate_scenario(
                feature_description, scenario.scenario_type, spec_mode
            )
            for scenario in scenarios
        }
        result_content = {
            "schema_version": "1.0",
            "feature_description": feature_description,
            "gherkin_feature": gherkin_feature,
            "scenarios": scenario_map,
            "generation_context": {
                "feature_type": self._identify_feature_type(feature_description),
                "spec_mode": spec_mode,
                "criteria_seed_count": len(acceptance_criteria),
                "complexity_estimate": max(1, len(feature_description.split()) // 10 + 1),
            },
            "quality_signals": {
                "scenario_count": len(scenarios),
                "specificity": "high" if acceptance_criteria else "medium",
                "generic_fallback_used": not bool(acceptance_criteria),
            },
            "plan_provenance": {
                "source": context.get("plan_source", "generated"),
                "passthrough": False,
                "rebuilt": False,
            },
        }

        result = build_agent_result(
            status="SUCCESS",
            artifact_type="bdd_specification",
            artifact_content=result_content,
            reason="BDD specification generated successfully.",
            confidence=0.9,
            logs=[
                f"Generated BDD for: {feature_description[:80]}",
                f"spec_mode={spec_mode}",
                f"scenario_count={len(scenarios)}",
            ],
            next_actions=["test_generator"],
        )
        result["artifact_type"] = "bdd_specification"
        result["artifact_content"] = result_content
        result["confidence"] = 0.9
        return result

    def _identify_feature_type(self, feature_description: str) -> str:
        feature_lower = feature_description.lower()
        if any(word in feature_lower for word in ["api", "endpoint", "service"]):
            return "api"
        if any(word in feature_lower for word in ["ui", "interface", "form", "page"]):
            return "ui"
        if any(word in feature_lower for word in ["auth", "authentication", "login", "register"]):
            return "authentication"
        if any(word in feature_lower for word in ["data", "database", "model", "schema"]):
            return "data_layer"
        return "general"


BDDGeneratorAgent = BDDGenerator

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result

PYTHON_ERRORS = {
    "syntax_error": r"(syntaxerror.*invalid syntax|invalid syntax)",
    "indentation_error": r"(indentationerror|unexpected indent|unindent does not match)",
    "import_error": r"(importerror|modulenotfounderror|no module named)",
    "type_error": r"(typeerror.*unsupported operand|unsupported operand|typeerror)",
    "runtime_error": r"(traceback \(most recent call last\)|runtimeerror|valueerror|keyerror|indexerror)",
}

JS_TS_ERRORS = {
    "js_syntax": r"(syntaxerror.*unexpected token|unexpected token)",
    "js_reference": r"(referenceerror|is not defined)",
    "js_type": r"(typeerror.*cannot read property|cannot read property|cannot read properties of)",
    "runtime_error": r"(unhandledpromiserejection|error: command failed|npm err!)",
}

GO_ERRORS = {
    "go_compile": r"(undefined:|build failed|compile failed)",
    "go_runtime": r"(panic:|runtime error)",
    "go_test": r"(--- fail:|fail\s+\S+\s+\[|^\s*fail\s*$)",
}

JAVA_ERRORS = {
    "java_compile": r"(cannot find symbol|\.java:\d+.*error:)",
    "java_runtime": r"(nullpointerexception|arrayindexoutofbounds|exception in thread)",
}

TEST_FAILURE_PATTERNS = [
    r"\bassertionerror\b",
    r"\bfailed tests?\b",
    r"\btest failed\b",
    r"\bfailed test\b",
    r"short test summary info",
    r"=+ .*failed.* =+",
    r"\bFAILED\s+[\w/.\-:\\\[\]]+::[\w\[\]-]+",
    r"\bE\s+assert\b",
    r"\bRan \d+ tests? .*FAILED\b",
    r"\bTests:\s+\d+\s+failed\b",
    r"\bjest\b.*\bfailed\b",
    r"\bvitest\b.*\bfailed\b",
]

INFRA_PATTERNS = [
    r"(failed to push)",
    r"(installation not allowed)",
    r"(denied:)",
    r"(permission denied)",
    r"(timeout|timed out|connection.*timeout)",
    r"(network.*error|network.*failure|connection.*refused)",
    r"(dns.*error|resolve.*error)",
    r"(out of memory|oom|memory.*limit)",
    r"(disk.*full|storage.*exceeded|quota exceeded|no space left on device)",
    r"(authentication failed|auth failed|unauthorized|forbidden)",
    r"(ssl.*error|tls.*error|certificate.*error|x509:)",
    r"(proxy.*error|firewall.*error)",
    r"(service.*unavailable|server.*down|bad gateway|gateway timeout)",
    r"(build agent|runner|executor).*error",
    r"(container|pod|k8s|kubernetes).*failed",
    r"(docker.*error|image.*pull.*failed|failed to solve with frontend dockerfile)",
]

BUILD_FAILURE_PATTERNS = [
    r"\bbuild failed\b",
    r"\bbuild failure\b",
    r"\bcompilation failed\b",
    r"\bmake: \*\*\*.*error\b",
]

SEVERITY_MAP = {
    "syntax_error": "critical",
    "indentation_error": "critical",
    "go_compile": "critical",
    "java_compile": "critical",
    "js_syntax": "critical",
    "test_failure": "major",
    "collection_error": "major",
    "path_error": "major",
    "js_type": "major",
    "js_reference": "major",
    "import_error": "major",
    "type_error": "major",
    "runtime_error": "major",
    "go_runtime": "major",
    "java_runtime": "major",
    "build_failure": "major",
    "infrastructure": "major",
    "go_test": "major",
    "lint_warning": "minor",
}


def _normalize_line(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_line(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def parse_logs(log_text: str) -> list[str]:
    if not log_text:
        return []

    errors: list[str] = []
    error_patterns = [
        r"\b(?:error|exception|traceback|assertionerror|failed|failure|panic:)\b.*",
        r"^.*\b(?:error|exception|traceback|assertionerror|failed|failure|panic:)\b.*$",
    ]
    negative_noise_patterns = [
        r"\b0 errors?\b",
        r"\b0 failures?\b",
        r"\bwithout errors?\b",
        r"\bno errors?\b",
        r"\ball tests passed\b",
        r"\bpassed\b.*\b0 failed\b",
    ]

    for raw_line in log_text.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue

        lowered = line.lower()
        if any(re.search(p, lowered, re.IGNORECASE) for p in negative_noise_patterns):
            continue

        if len(line) > 500:
            line = line[:500] + "..."

        for pattern in error_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(line)
                break

    return _dedupe_keep_order(errors)


def detect_flaky_tests(log_text: str) -> list[str]:
    if not log_text:
        return []

    flaky_indicators = [
        r"(flaky|intermittent|non-deterministic|random failure)",
        r"(passed on retry|failed only sometimes|sometimes fails)",
        r"(retry|re-run|rerun).*test",
        r"test.*failed.*but.*passed",
        r"(unstable|inconsistent).*test",
    ]

    detected_tests: list[str] = []
    test_name_patterns = [
        r"\btest_[A-Za-z0-9_]+\b",
        r"\b[Test][A-Za-z0-9_]+\b",
        r"\b[A-Za-z0-9_]+Test\b",
        r'"([^"]*test[^"]*)"',
        r"'([^']*test[^']*)'",
        r"\b[\w./\\:-]+::test_[A-Za-z0-9_\[\]-]+\b",
    ]

    for line in log_text.splitlines():
        line_lower = line.lower()
        if any(re.search(indicator, line_lower) for indicator in flaky_indicators):
            for pattern in test_name_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    candidate = " ".join(match) if isinstance(match, tuple) else str(match)
                    candidate = candidate.strip("\"' ")
                    if candidate:
                        detected_tests.append(candidate)

    return _dedupe_keep_order(detected_tests)


def detect_infra_errors(log_text: str) -> list[str]:
    if not log_text:
        return []

    infra_errors: list[str] = []
    for line in log_text.splitlines():
        line_normalized = _normalize_line(line)
        if not line_normalized:
            continue
        lowered = line_normalized.lower()
        for pattern in INFRA_PATTERNS:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                infra_errors.append(match.group(0))
    return _dedupe_keep_order(infra_errors)


def detect_language(text: str) -> str:
    if not text:
        return "unknown"

    t = text.lower()

    python_score = 0
    js_score = 0
    go_score = 0
    java_score = 0

    if "traceback (most recent call last)" in t:
        python_score += 3
    if 'file "' in t and ".py" in t:
        python_score += 2
    if "assertionerror" in t or "pytest" in t or "unittest" in t:
        python_score += 2

    if ".js:" in t or ".ts:" in t or "node_modules" in t:
        js_score += 2
    if "unexpected token" in t or "referenceerror" in t or "npm err!" in t:
        js_score += 2
    if "jest" in t or "vitest" in t:
        js_score += 2

    if ".go:" in t or "panic:" in t:
        go_score += 2
    if "--- fail:" in t or "go test" in t:
        go_score += 2

    if ".java:" in t or "exception in thread" in t:
        java_score += 2
    if "nullpointerexception" in t or "cannot find symbol" in t:
        java_score += 2

    scores = {
        "python": python_score,
        "javascript": js_score,
        "go": go_score,
        "java": java_score,
    }

    best_language, best_score = max(scores.items(), key=lambda item: item[1])
    return best_language if best_score > 0 else "unknown"


def extract_file_line_from_trace(trace: str) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    if not trace:
        return locations

    python_pattern = re.compile(
        r'File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+([^\s]+))?',
        re.IGNORECASE,
    )
    for match in python_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "function": match.group(3) or "",
                    "language": "python",
                }
            )
        except (TypeError, ValueError):
            continue

    js_pattern = re.compile(
        r"at\s+(?:.*?\s+)?\(?((?:[A-Za-z]:)?[^():\n]+?\.(?:js|ts|jsx|tsx)):(\d+):\d+\)?",
        re.IGNORECASE,
    )
    for match in js_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": match.group(1),
                    "line": int(match.group(2)),
                    "function": "",
                    "language": "javascript",
                }
            )
        except (TypeError, ValueError):
            continue

    java_pattern = re.compile(r"at\s+([^\(]+)\(([^:()]+\.java):(\d+)\)", re.IGNORECASE)
    for match in java_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": match.group(2),
                    "line": int(match.group(3)),
                    "function": match.group(1).strip(),
                    "language": "java",
                }
            )
        except (TypeError, ValueError):
            continue

    go_pattern = re.compile(
        r"(^|\s)([^\s:()]+\.go):(\d+)(?::\d+)?",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in go_pattern.finditer(trace):
        filepath = match.group(2)
        if "/go/" in filepath or "\\go\\" in filepath:
            continue
        try:
            locations.append(
                {
                    "file": filepath,
                    "line": int(match.group(3)),
                    "function": "",
                    "language": "go",
                }
            )
        except (TypeError, ValueError):
            continue

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for loc in locations:
        key = (loc.get("file"), loc.get("line"), loc.get("function"), loc.get("language"))
        if key not in seen:
            deduped.append(loc)
            seen.add(key)

    return deduped


def determine_severity(classification: str) -> str:
    return SEVERITY_MAP.get(classification, "major")


def _pick_most_severe(classifications: list[str]) -> str:
    priority = {"critical": 3, "major": 2, "minor": 1, "unknown": 0}
    best = "unknown"
    best_score = -1
    for classification in classifications:
        score = priority.get(determine_severity(classification), 0)
        if score > best_score:
            best = classification
            best_score = score
    return best


def _fingerprint(text: str) -> str:
    if not text:
        return ""
    normalized = re.sub(r"\d+", "N", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _extract_test_targets(text: str) -> list[str]:
    if not text:
        return []

    targets: list[str] = []
    patterns = [
        r"([\w./\\-]+\.py::test_[\w\[\]-]+)",
        r"\bFAILED\s+([\w./\\-]+\.py::[\w\[\]-]+)",
        r"\bERROR\s+([\w./\\-]+\.py::[\w\[\]-]+)",
        r"\b([\w./\\-]+\.py)\b",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for match in matches:
            targets.append(str(match).strip())

    normalized: list[str] = []
    for item in targets:
        candidate = item.replace("\\", "/")
        for prefix in ("workspace/repo/", "/workspace/repo/", "workspace/", "repo/"):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix) :]
                break
        if candidate:
            normalized.append(candidate)

    return _dedupe_keep_order(normalized)


def _extract_repository_files_from_locations(locations: list[dict[str, Any]]) -> list[str]:
    files: list[str] = []
    for location in locations:
        file_path = str(location.get("file") or "").strip().replace("\\", "/")
        if not file_path:
            continue
        if "/site-packages/" in file_path or "/usr/" in file_path:
            continue
        files.append(file_path)
    return _dedupe_keep_order(files)


def classify_failure_text(text: str) -> str:
    if not text:
        return "unknown"

    normalized_text = _normalize_line(text)
    lowered = normalized_text.lower()

    if "file or directory not found" in lowered:
        return "path_error"
    if "collected 0 items" in lowered or "no tests collected" in lowered:
        return "collection_error"

    for pattern in BUILD_FAILURE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "build_failure"

    for pattern in INFRA_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "infrastructure"

    for pattern in TEST_FAILURE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "test_failure"

    for label, pattern in PYTHON_ERRORS.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            return label

    for label, pattern in JS_TS_ERRORS.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            return label

    for label, pattern in GO_ERRORS.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            return label

    for label, pattern in JAVA_ERRORS.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            return label

    if re.search(r"\b(?:lint|warning)\b", lowered, re.IGNORECASE):
        return "lint_warning"

    return "unknown"


class CiFailureAnalyzer(BaseAgent):
    name = "ci_failure_analyzer"
    description = "Parses CI failures with language-aware classification, fingerprinting and root-cause selection."

    @staticmethod
    def _classify_failure(failed_jobs: list[dict[str, Any]]) -> str:
        if not failed_jobs:
            return "unknown"

        per_job: list[str] = []
        for job in failed_jobs:
            text = " ".join(
                str(job.get(key, "") or "") for key in ("name", "reason", "logs")
            ).strip()
            per_job.append(classify_failure_text(text))

        return _pick_most_severe(per_job)

    @staticmethod
    def _extract_issue_comments_text(issue: dict[str, Any]) -> str:
        comments = issue.get("comments")
        if not isinstance(comments, list):
            return ""

        parts: list[str] = []
        for item in comments:
            if not isinstance(item, dict):
                continue
            body = item.get("body")
            if isinstance(body, str) and body.strip():
                parts.append(body.strip())
        return "\n".join(parts)

    @staticmethod
    def _extract_failed_job_names(text: str) -> list[str]:
        if not text:
            return []

        patterns = [
            r"^\s*(?:\d+\.\s*)?\*\*([^*:\n\r]{2,120})\*\*\s*:\s*failed steps",
            r"^\s*(?:\d+\.\s*)?([A-Z][A-Za-z0-9 _./:-]{2,100})\s*:\s*failed steps",
        ]

        matches: list[str] = []
        for pattern in patterns:
            found = re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            for item in found:
                candidate = item if isinstance(item, str) else " ".join(item)
                candidate = _normalize_line(candidate)
                if not candidate:
                    continue
                lowered = candidate.lower()
                if any(
                    token in lowered for token in ["agent:opened", "agent:planning", "agent:ready"]
                ):
                    continue
                if len(candidate) > 120:
                    continue
                matches.append(candidate)

        cleaned: list[str] = []
        for item in matches:
            lowered = item.lower()
            if any(
                token in lowered
                for token in [
                    "acceptance criteria",
                    "definition of done",
                    "planning update",
                    "generated by hordeforge",
                ]
            ):
                continue
            cleaned.append(item)

        return _dedupe_keep_order(cleaned)

    @classmethod
    def _extract_job_logs_from_issue(cls, body: str, job_name: str) -> str:
        if not body or not job_name:
            return ""

        escaped_job_name = re.escape(job_name)
        pattern = r"\*\*" + escaped_job_name + r"\*\*.*?failed steps:.*?\n\s+-\s+logs:\s+`([^`]+)`"
        match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
        if match:
            logs_raw = match.group(1)
            excerpt_match = re.search(r"excerpt=([^\s;]+(?:\s+[^\s;]+)*)", logs_raw)
            if excerpt_match:
                return excerpt_match.group(1).strip()
            return logs_raw.strip()

        fallback_pattern = (
            r"\*\*" + escaped_job_name + r"\*\*.*?(?:excerpt=|error=|E\s+)([^\n]{20,500})"
        )
        fallback_match = re.search(fallback_pattern, body, re.DOTALL | re.IGNORECASE)
        if fallback_match:
            return fallback_match.group(1).strip()

        return ""

    @classmethod
    def _build_ci_run_from_issue(cls, issue: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not isinstance(issue, dict):
            return (
                {
                    "status": "failed",
                    "failed_jobs": [
                        {
                            "name": "unknown-ci-failure",
                            "reason": "missing issue context",
                            "logs": "",
                        }
                    ],
                },
                False,
            )

        title = str(issue.get("title") or "").strip()
        body = str(issue.get("body") or issue.get("description") or "").strip()
        comments_text = cls._extract_issue_comments_text(issue)

        full_text = "\n\n".join(part for part in [title, body, comments_text] if part).strip()
        failed_job_names = cls._extract_failed_job_names(full_text)
        reason_source = full_text[:2000] if full_text else "issue-based ci incident handoff"

        failed_jobs: list[dict[str, Any]] = []
        for job_name in failed_job_names[:10]:
            job_logs = cls._extract_job_logs_from_issue(body, job_name)
            if not job_logs:
                job_logs = full_text[:12000]
            failed_jobs.append(
                {
                    "name": job_name,
                    "reason": reason_source,
                    "logs": job_logs[:12000],
                }
            )

        if not failed_jobs:
            fallback_name = title or "ci-incident"
            failed_jobs.append(
                {
                    "name": fallback_name[:120],
                    "reason": reason_source or "issue-based ci incident handoff",
                    "logs": full_text[:12000],
                }
            )

        return (
            {
                "status": "failed",
                "failed_jobs": failed_jobs,
                "source": "issue_handoff",
                "issue_number": issue.get("number"),
            },
            True,
        )

    def run(self, context: dict[str, Any]) -> dict:
        ci_run = context.get("ci_run")
        issue = context.get("issue")
        mock_mode = bool(context.get("mock_mode"))
        dry_run = bool(context.get("dry_run"))

        fallback_used = False
        issue_handoff_used = False

        if not isinstance(ci_run, dict):
            if isinstance(issue, dict):
                ci_run, issue_handoff_used = self._build_ci_run_from_issue(issue)
                fallback_used = True
            else:
                fallback_used = True
                ci_run = {
                    "status": "failed",
                    "failed_jobs": [{"name": "default-test", "reason": "default failure"}],
                }

        failed_jobs_raw = ci_run.get("failed_jobs")
        failed_jobs = (
            [job for job in failed_jobs_raw if isinstance(job, dict)]
            if isinstance(failed_jobs_raw, list)
            else []
        )

        if not failed_jobs:
            fallback_used = True
            failed_jobs = [
                {"name": "default-test", "reason": "default failure", "logs": "default logs"}
            ]

        classification = self._classify_failure(failed_jobs)
        severity = determine_severity(classification)

        all_locations: list[dict[str, Any]] = []
        combined_logs_parts: list[str] = []
        per_job_analysis: list[dict[str, Any]] = []
        job_languages: list[str] = []
        all_test_targets: list[str] = []

        for index, job in enumerate(failed_jobs):
            job_name = str(job.get("name") or f"job_{index + 1}")
            job_reason = str(job.get("reason") or "")
            job_logs = str(job.get("logs") or job_reason or "")
            combined_text = " ".join(
                part for part in [job_name, job_reason, job_logs] if part
            ).strip()

            combined_logs_parts.append(job_logs)

            locations = extract_file_line_from_trace(job_logs)
            for location in locations:
                if location not in all_locations:
                    all_locations.append(location)

            job_classification = classify_failure_text(combined_text)
            job_severity = determine_severity(job_classification)
            job_language = detect_language(job_logs or combined_text)
            job_languages.append(job_language)

            job_parsed_errors = parse_logs(job_logs)
            job_flaky_tests = detect_flaky_tests(job_logs)
            job_infra_errors = detect_infra_errors(job_logs)
            job_fingerprint = _fingerprint(job_logs) if job_logs else ""
            job_test_targets = _extract_test_targets(job_logs)
            all_test_targets.extend(job_test_targets)

            per_job_analysis.append(
                {
                    "job_name": job_name,
                    "classification": job_classification,
                    "severity": job_severity,
                    "language": job_language,
                    "fingerprint": job_fingerprint,
                    "locations": locations[:10],
                    "parsed_errors": job_parsed_errors,
                    "flaky_tests": job_flaky_tests,
                    "infra_errors": job_infra_errors,
                    "test_targets": job_test_targets[:10],
                }
            )

        combined_logs = " ".join(combined_logs_parts).strip()
        detected_language = detect_language(combined_logs)
        dominant_language = detected_language

        non_unknown_languages = [language for language in job_languages if language != "unknown"]
        if non_unknown_languages:
            dominant_language = Counter(non_unknown_languages).most_common(1)[0][0]

        fingerprint = _fingerprint(combined_logs) if combined_logs else None
        parsed_errors = parse_logs(combined_logs)
        flaky_tests = detect_flaky_tests(combined_logs)
        infra_errors = detect_infra_errors(combined_logs)
        files = _extract_repository_files_from_locations(all_locations)
        test_targets = _dedupe_keep_order(all_test_targets)

        analysis = {
            "classification": classification,
            "severity": severity,
            "failed_jobs_count": len(failed_jobs),
            "details": failed_jobs,
            "locations": all_locations[:10],
            "ci_status": ci_run.get("status", "unknown"),
            "language": detected_language,
            "dominant_language": dominant_language,
            "job_languages": job_languages,
            "fingerprint": fingerprint,
            "parsed_errors": parsed_errors,
            "flaky_tests": flaky_tests,
            "infra_errors": infra_errors,
            "per_job_analysis": per_job_analysis,
            "fallback_used": fallback_used,
            "issue_handoff_used": issue_handoff_used,
            "files": files[:20],
            "test_targets": test_targets[:20],
        }

        logs = [
            f"classification={classification}",
            f"severity={severity}",
            f"language={detected_language}",
            f"dominant_language={dominant_language}",
            f"fingerprint={fingerprint}",
            f"parsed_errors_count={len(parsed_errors)}",
            f"flaky_tests_count={len(flaky_tests)}",
            f"infra_errors_count={len(infra_errors)}",
            f"files_count={len(files)}",
            f"test_targets_count={len(test_targets)}",
        ]

        if issue_handoff_used:
            logs.append("source=issue_handoff")

        if fallback_used:
            if mock_mode or dry_run:
                logs.append("fallback_ci_run_payload_used=mock_or_dry_run")
            elif issue_handoff_used:
                logs.append("fallback_ci_run_payload_used=adapted_from_issue")
            else:
                logs.append("fallback_ci_run_payload_used=missing_or_invalid_payload")

        for item in per_job_analysis:
            logs.append(
                "job="
                f"{item['job_name']} "
                f"classification={item['classification']} "
                f"severity={item['severity']} "
                f"language={item['language']}"
            )

        return build_agent_result(
            status="SUCCESS",
            artifact_type="failure_analysis",
            artifact_content=analysis,
            reason=f"CI failure analyzed: {classification} (severity: {severity}).",
            confidence=0.9,
            logs=logs,
            next_actions=["ci_incident_handoff"],
        )

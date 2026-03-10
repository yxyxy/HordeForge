# =========================================================================
# agents/ci_failure_analyzer.py
# CI Failure Analysis (HF-P6-003) — полностью исправленная версия
# =========================================================================

from __future__ import annotations

import hashlib
import re
from typing import Any

from agents.context_utils import build_agent_result

# =========================================================================
# Error classification patterns
# =========================================================================

PYTHON_ERRORS = {
    "syntax_error": r"(syntaxerror.*invalid syntax|invalid syntax)",
    "indentation_error": r"(indentationerror|unexpected indent|unindent does not match)",
    "import_error": r"(importerror|modulenotfounderror|no module named)",
    "type_error": r"(typeerror.*unsupported operand|unsupported operand)",
}

JS_TS_ERRORS = {
    "js_syntax": r"(syntaxerror.*unexpected token|unexpected token)",
    "js_reference": r"(referenceerror|is not defined)",
    "js_type": r"(typeerror.*cannot read property|cannot read property)",
}

GO_ERRORS = {
    "go_compile": r"(undefined:)",
    "go_runtime": r"(panic:|runtime error)",
    "go_test": r"(--- fail:|--- pass:)",
}

JAVA_ERRORS = {
    "java_compile": r"(cannot find symbol|\.java:\d+.*error:)",
    "java_runtime": r"(nullpointerexception|arrayindexoutofbounds|exception in thread)",
}

SEVERITY_MAP = {
    "syntax_error": "critical",
    "indentation_error": "critical",
    "go_compile": "critical",
    "java_compile": "critical",
    "js_syntax": "critical",
    "test_failure": "major",
    "js_type": "major",
    "js_reference": "major",
    "import_error": "major",
    "type_error": "major",
    "runtime_error": "major",
    "go_runtime": "major",
    "java_runtime": "major",
    "build_failure": "major",
    "infrastructure": "major",
    "lint_warning": "minor",
    "go_test": "minor",
}

# =========================================================================
# Language detection (basic heuristics)
# =========================================================================


def detect_language(text: str) -> str:
    """Detect likely language from combined logs (heuristic)."""
    if not text:
        return "unknown"
    t = text.lower()
    if "traceback (most recent call last)" in t or "file \"" in t and ".py" in t:
        return "python"
    if ".js" in t or "node_modules" in t or "unexpected token" in t:
        return "javascript"
    if ".go" in t or "panic:" in t:
        return "go"
    if ".java" in t or "exception in thread" in t:
        return "java"
    return "unknown"


# =========================================================================
# Stack trace extraction
# =========================================================================


def extract_file_line_from_trace(trace: str) -> list[dict[str, Any]]:
    """
    Extract file/line/function locations from a log/stacktrace.
    Supports Python, JavaScript (including Windows paths), Go, Java.
    Returns a list of dicts: {"file": str, "line": int, "function": str, "language": str}
    """
    locations: list[dict[str, Any]] = []

    if not trace:
        return locations

    # Python: File "path", line N, in func
    python_pattern = re.compile(
        r'File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+([^\s]+))?', re.IGNORECASE
    )
    for m in python_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "function": m.group(3) or "",
                    "language": "python",
                }
            )
        except Exception:
            continue

    # JavaScript: at function (C:\path\to\file.js:15:5) or at C:\path\to\file.js:15:5
    # Accept ":" inside path (for Windows drives) — capture greedily up to last colon-number-number
    js_pattern = re.compile(r"at\s+(?:.*?\s+)?\(?(.+?):(\d+):\d+\)?", re.IGNORECASE)
    for m in js_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "function": "",
                    "language": "javascript",
                }
            )
        except Exception:
            continue

    # Java: at package.Class.method(File.java:25)
    java_pattern = re.compile(r"at\s+([^\(]+)\(([^:]+):(\d+)\)", re.IGNORECASE)
    for m in java_pattern.finditer(trace):
        try:
            locations.append(
                {
                    "file": m.group(2),
                    "line": int(m.group(3)),
                    "function": m.group(1).strip(),
                    "language": "java",
                }
            )
        except Exception:
            continue

    # Go: path/to/file.go:123 or file.go:123 (skip likely stdlib entries)
    go_pattern = re.compile(r"(^|\s)([^\s:]+\.go):(\d+)(?::\d+)?", re.IGNORECASE | re.MULTILINE)
    for m in go_pattern.finditer(trace):
        filepath = m.group(2)
        if "/go/" in filepath or "\\go\\" in filepath:
            # likely stdlib/tooling — skip
            continue
        try:
            locations.append(
                {
                    "file": filepath,
                    "line": int(m.group(3)),
                    "function": "",
                    "language": "go",
                }
            )
        except Exception:
            continue

    # Deduplicate while preserving order
    deduped: list[dict[str, Any]] = []
    seen = set()
    for loc in locations:
        key = (loc.get("file"), loc.get("line"), loc.get("function"), loc.get("language"))
        if key not in seen:
            deduped.append(loc)
            seen.add(key)

    return deduped


# =========================================================================
# Utilities: severity, fingerprinting, selection
# =========================================================================


def determine_severity(classification: str) -> str:
    return SEVERITY_MAP.get(classification, "major")


def _pick_most_severe(classifications: list[str]) -> str:
    """
    Given per-job classifications, return the classification with the highest severity.
    Priority: critical > major > minor > unknown.
    If multiple with same severity, return the first encountered.
    """
    priority = {"critical": 3, "major": 2, "minor": 1, "unknown": 0}
    best = "unknown"
    best_score = -1
    for c in classifications:
        score = priority.get(determine_severity(c), 0)
        if score > best_score:
            best = c
            best_score = score
    return best


def _fingerprint(text: str) -> str:
    """
    Create a short deterministic fingerprint for similar CI failures.
    Normalize numbers to reduce noise.
    """
    if not text:
        return ""
    normalized = re.sub(r"\d+", "N", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


# =========================================================================
# Failure classification
# =========================================================================


def classify_failure_text(text: str) -> str:
    """
    Classify a single text blob (job reason/logs) into a classification label.
    """
    if not text:
        return "unknown"

    t = text.lower()

    # Generic top-level checks (keep first to satisfy tests expecting 'build_failure')
    if "build failed" in t or "build failure" in t:
        return "build_failure"

    if "test failed" in t or "failed test" in t or "failed:" in t and "test" in t:
        return "test_failure"

    if "timeout" in t or "network" in t or "connection timed out" in t:
        return "infrastructure"

    if "lint" in t or "warning" in t:
        return "lint_warning"

    # Python-specific
    for label, pattern in PYTHON_ERRORS.items():
        if re.search(pattern, t, re.IGNORECASE):
            return label

    # JavaScript/TypeScript-specific
    for label, pattern in JS_TS_ERRORS.items():
        if re.search(pattern, t, re.IGNORECASE):
            return label

    # Go-specific
    for label, pattern in GO_ERRORS.items():
        if re.search(pattern, t, re.IGNORECASE):
            return label

    # Java-specific
    for label, pattern in JAVA_ERRORS.items():
        if re.search(pattern, t, re.IGNORECASE):
            return label

    return "unknown"


# =========================================================================
# CI Failure Analyzer (main agent)
# =========================================================================


class CiFailureAnalyzer:
    name = "ci_failure_analyzer"
    description = "Parses CI failures with language-aware classification, fingerprinting and root-cause selection."

    @staticmethod
    def _classify_failure(failed_jobs: list[dict[str, Any]]) -> str:
        """
        Classify each failed job separately and pick most severe classification.
        """
        if not failed_jobs:
            return "unknown"

        per_job: list[str] = []
        for job in failed_jobs:
            # combine job name, reason, logs — job-level only
            text = " ".join(
                str(job.get(k, "") or "") for k in ("name", "reason", "logs")
            ).strip()
            label = classify_failure_text(text)
            per_job.append(label)

        return _pick_most_severe(per_job)

    def run(self, context: dict[str, Any]) -> dict:
        ci_run = context.get("ci_run")

        # Missing or malformed payload -> partial success fallback
        if not isinstance(ci_run, dict):
            return build_agent_result(
                status="PARTIAL_SUCCESS",
                artifact_type="failure_analysis",
                artifact_content={
                    "classification": "unknown",
                    "severity": "major",
                    "failed_jobs_count": 0,
                    "details": [],
                    "locations": [],
                    "language": "unknown",
                    "fingerprint": None,
                },
                reason="CI payload missing; returned fallback classification.",
                confidence=0.5,
                logs=["No ci_run payload provided; fallback used."],
                next_actions=["test_fixer"],
            )

        failed_jobs_raw = ci_run.get("failed_jobs")
        failed_jobs = [j for j in failed_jobs_raw if isinstance(j, dict)] if isinstance(failed_jobs_raw, list) else []

        # Classify root cause (per-job + pick most severe)
        classification = self._classify_failure(failed_jobs)
        severity = determine_severity(classification)

        # Extract and deduplicate locations across jobs
        all_locations: list[dict[str, Any]] = []
        combined_logs_parts: list[str] = []

        for job in failed_jobs:
            logs = job.get("logs") or job.get("reason") or ""
            logs_str = str(logs)
            combined_logs_parts.append(logs_str)
            locs = extract_file_line_from_trace(logs_str)
            for loc in locs:
                if loc not in all_locations:
                    all_locations.append(loc)

        combined_logs = " ".join(combined_logs_parts).strip()
        detected_language = detect_language(combined_logs)
        fingerprint = _fingerprint(combined_logs) if combined_logs else None

        analysis = {
            "classification": classification,
            "severity": severity,
            "failed_jobs_count": len(failed_jobs),
            "details": failed_jobs,
            "locations": all_locations[:10],  # limit to reasonable number
            "ci_status": ci_run.get("status", "unknown"),
            "language": detected_language,
            "fingerprint": fingerprint,
        }

        return build_agent_result(
            status="SUCCESS",
            artifact_type="failure_analysis",
            artifact_content=analysis,
            reason=f"CI failure analyzed: {classification} (severity: {severity}).",
            confidence=0.9,
            logs=[
                f"classification={classification}",
                f"severity={severity}",
                f"language={detected_language}",
                f"fingerprint={fingerprint}",
            ],
            next_actions=["test_fixer"],
        )
"""Language and framework detection utilities for test generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".m": "objective-c",
}

FRAMEWORK_PATTERNS = {
    "python": {
        "pytest": ["pytest.ini", "pyproject.toml", "conftest.py", "tests/"],
        "unittest": ["unittest", "test_*.py", "*_test.py"],
        "nose": ["nose2", "nosetests"],
        "django": ["manage.py", "settings.py", "django"],
        "flask": ["app.py", "wsgi.py", "flask"],
    },
    "javascript": {
        "jest": ["jest.config.js", "jest.config.ts", "package.json"],
        "mocha": ["mocha.opts", ".mocharc.json"],
        "vitest": ["vitest.config.js", "vitest.config.ts"],
        "jasmine": ["jasmine.json", "spec/support/jasmine.json"],
        "karma": ["karma.conf.js"],
    },
    "typescript": {
        "jest": ["jest.config.js", "jest.config.ts"],
        "mocha": ["mocha.opts", ".mocharc.json"],
        "vitest": ["vitest.config.js"],
        "jasmine": ["jasmine.json"],
    },
    "go": {
        "testing": ["_test.go"],
        "ginkgo": ["ginkgo", "gomega"],
        "testify": ["testify", "assert", "require"],
    },
    "java": {
        "junit": ["junit", "TestCase"],
        "testng": ["testng", "@Test"],
        "spock": ["spock"],
    },
    "ruby": {
        "rspec": ["spec/", "spec_helper.rb", "_spec.rb"],
        "minitest": ["minitest", "test_helper.rb"],
    },
}


@dataclass
class LanguageInfo:
    """Information about detected language and framework."""

    language: str
    framework: str | None = None
    test_directory: str | None = None
    test_file_pattern: str | None = None
    config_files: list[str] | None = None


def detect_language_from_files(files: list[str]) -> str | None:
    """Detect primary language from file list.

    Args:
        files: List of file paths

    Returns:
        Language identifier or None
    """
    extension_counts: dict[str, int] = {}

    for f in files:
        ext = Path(f).suffix.lower()
        if ext in LANGUAGE_EXTENSIONS:
            lang = LANGUAGE_EXTENSIONS[ext]
            extension_counts[lang] = extension_counts.get(lang, 0) + 1

    if not extension_counts:
        return None

    return max(extension_counts, key=extension_counts.get)


def detect_language_from_manifest(repo_path: str) -> str | None:
    """Detect language from manifest files.

    Args:
        repo_path: Path to repository root

    Returns:
        Language identifier or None
    """
    manifest_mappings = {
        "package.json": "javascript",
        "setup.py": "python",
        "pyproject.toml": "python",
        "requirements.txt": "python",
        "Pipfile": "python",
        "go.mod": "go",
        "Gemfile": "ruby",
        "pom.xml": "java",
        "build.gradle": "java",
        "Cargo.toml": "rust",
        "composer.json": "php",
        "Podfile": "objective-c",
        "Cartfile": "objective-c",
    }

    repo_path_obj = Path(repo_path)
    for manifest, language in manifest_mappings.items():
        if (repo_path_obj / manifest).exists():
            return language

    return None


def detect_framework(language: str, repo_path: str) -> str | None:
    """Detect testing framework for given language.

    Args:
        language: Programming language
        repo_path: Path to repository root

    Returns:
        Framework name or None
    """
    repo_path_obj = Path(repo_path)
    patterns = FRAMEWORK_PATTERNS.get(language, {})

    for framework, indicators in patterns.items():
        for indicator in indicators:
            # Check for files
            if "/" in indicator or indicator.startswith("*"):
                # Directory or pattern
                if indicator.endswith("/"):
                    # Directory
                    if (repo_path_obj / indicator).exists():
                        return framework
                elif "*" in indicator:
                    # Glob pattern
                    for _f in repo_path_obj.rglob(indicator):
                        return framework
            else:
                # Specific file
                if (repo_path_obj / indicator).exists():
                    return framework

    return None


def get_test_directory(language: str, repo_path: str) -> str | None:
    """Get the standard test directory for the language.

    Args:
        language: Programming language
        repo_path: Path to repository root

    Returns:
        Test directory path or None
    """
    repo_path_obj = Path(repo_path)

    test_dirs = {
        "python": ["tests/", "test/", "spec/"],
        "javascript": ["__tests__/", "tests/", "spec/", "test/"],
        "typescript": ["__tests__/", "tests/", "spec/", "test/"],
        "go": ["*_test.go"],  # Same as source
        "ruby": ["spec/", "test/"],
        "java": ["src/test/java/"],
    }

    for test_dir in test_dirs.get(language, []):
        if "*" in test_dir:
            # Pattern-based (like Go)
            return None  # Tests are in same directory
        if (repo_path_obj / test_dir).exists():
            return test_dir

    return None


def get_test_file_pattern(language: str, framework: str | None = None) -> str:
    """Get test file naming pattern for language/framework.

    Args:
        language: Programming language
        framework: Optional framework

    Returns:
        Glob pattern for test files
    """
    patterns = {
        "python": "test_*.py",
        "javascript": "*.test.js",
        "typescript": "*.test.ts",
        "go": "*_test.go",
        "ruby": "*_spec.rb",
        "java": "*Test.java",
    }

    if framework == "pytest":
        return "test_*.py"
    elif framework == "rspec":
        return "*_spec.rb"

    return patterns.get(language, f"test_*.{language}")


def detect_language_info(repo_path: str, files: list[str]) -> LanguageInfo:
    """Detect complete language and framework information.

    Args:
        repo_path: Path to repository root
        files: List of files in repository

    Returns:
        LanguageInfo with detected information
    """
    # Try manifest first
    language = detect_language_from_manifest(repo_path)

    # Fall back to file extension analysis
    if not language:
        language = detect_language_from_files(files)

    # Default to Python
    language = language or "python"

    # Detect framework
    framework = detect_framework(language, repo_path)

    # Get test directory
    test_directory = get_test_directory(language, repo_path)

    # Get test file pattern
    test_file_pattern = get_test_file_pattern(language, framework)

    return LanguageInfo(
        language=language,
        framework=framework,
        test_directory=test_directory,
        test_file_pattern=test_file_pattern,
    )

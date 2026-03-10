"""Unit tests for language detector and test templates (HF-P5-004)."""

import tempfile
from pathlib import Path

from agents.language_detector import (
    LanguageInfo,
    detect_framework,
    detect_language_from_files,
    detect_language_from_manifest,
    detect_language_info,
    get_test_directory,
    get_test_file_pattern,
)
from agents.test_templates import (
    generate_test_file,
    get_go_test_template,
    get_javascript_jest_template,
    get_python_pytest_template,
    get_python_unittest_template,
    get_ruby_rspec_template,
    get_test_imports,
    get_typescript_jest_template,
)


class TestDetectLanguageFromFiles:
    """Tests for language detection from files."""

    def test_detect_python(self):
        """Test Python detection from .py files."""
        files = ["main.py", "utils.py", "test_main.py"]
        assert detect_language_from_files(files) == "python"

    def test_detect_javascript(self):
        """Test JavaScript detection."""
        files = ["index.js", "app.js", "bundle.js"]
        assert detect_language_from_files(files) == "javascript"

    def test_detect_typescript(self):
        """Test TypeScript detection."""
        files = ["index.ts", "app.tsx", "types.ts"]
        assert detect_language_from_files(files) == "typescript"

    def test_detect_go(self):
        """Test Go detection."""
        files = ["main.go", "util.go", "handler.go"]
        assert detect_language_from_files(files) == "go"

    def test_detect_ruby(self):
        """Test Ruby detection."""
        files = ["app.rb", "config.rb", "model.rb"]
        assert detect_language_from_files(files) == "ruby"

    def test_empty_list(self):
        """Test empty file list returns None."""
        assert detect_language_from_files([]) is None

    def test_unknown_extensions(self):
        """Test unknown extensions returns None."""
        files = ["data.dat", "config.cfg"]
        assert detect_language_from_files(files) is None


class TestDetectLanguageFromManifest:
    """Tests for language detection from manifest files."""

    def test_detect_python_pyproject(self):
        """Test Python detection from pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").touch()
            assert detect_language_from_manifest(tmpdir) == "python"

    def test_detect_python_setup(self):
        """Test Python detection from setup.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "setup.py").touch()
            assert detect_language_from_manifest(tmpdir) == "python"

    def test_detect_javascript_package(self):
        """Test JavaScript detection from package.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "package.json").touch()
            assert detect_language_from_manifest(tmpdir) == "javascript"

    def test_detect_go_mod(self):
        """Test Go detection from go.mod."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "go.mod").touch()
            assert detect_language_from_manifest(tmpdir) == "go"

    def test_no_manifest(self):
        """Test detection when no manifest exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert detect_language_from_manifest(tmpdir) is None


class TestDetectFramework:
    """Tests for framework detection."""

    def test_detect_pytest(self):
        """Test pytest detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pytest.ini").touch()
            assert detect_framework("python", tmpdir) == "pytest"

    def test_detect_jest(self):
        """Test Jest detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "jest.config.js").touch()
            assert detect_framework("javascript", tmpdir) == "jest"

    def test_detect_rspec(self):
        """Test RSpec detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "spec").mkdir()
            Path(tmpdir, "spec", "spec_helper.rb").touch()
            assert detect_framework("ruby", tmpdir) == "rspec"

    def test_no_framework(self):
        """Test when no framework detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert detect_framework("python", tmpdir) is None


class TestGetTestDirectory:
    """Tests for test directory detection."""

    def test_python_tests_dir(self):
        """Test Python tests directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "tests").mkdir()
            assert get_test_directory("python", tmpdir) == "tests/"

    def test_python_test_dir(self):
        """Test Python test directory (singular)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test").mkdir()
            assert get_test_directory("python", tmpdir) == "test/"

    def test_javascript_tests_dir(self):
        """Test JavaScript __tests__ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "__tests__").mkdir()
            assert get_test_directory("javascript", tmpdir) == "__tests__/"

    def test_no_test_dir(self):
        """Test when no test directory exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert get_test_directory("python", tmpdir) is None


class TestGetTestFilePattern:
    """Tests for test file pattern."""

    def test_python_pytest_pattern(self):
        """Test Python pytest pattern."""
        assert get_test_file_pattern("python", "pytest") == "test_*.py"

    def test_python_unittest_pattern(self):
        """Test Python unittest pattern."""
        assert get_test_file_pattern("python", "unittest") == "test_*.py"

    def test_javascript_pattern(self):
        """Test JavaScript pattern."""
        assert get_test_file_pattern("javascript") == "*.test.js"

    def test_typescript_pattern(self):
        """Test TypeScript pattern."""
        assert get_test_file_pattern("typescript") == "*.test.ts"

    def test_go_pattern(self):
        """Test Go pattern."""
        assert get_test_file_pattern("go") == "*_test.go"

    def test_ruby_rspec_pattern(self):
        """Test Ruby RSpec pattern."""
        assert get_test_file_pattern("ruby", "rspec") == "*_spec.rb"


class TestDetectLanguageInfo:
    """Tests for complete language info detection."""

    def test_detect_python_with_pytest(self):
        """Test full Python detection with pytest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").touch()
            Path(tmpdir, "pytest.ini").touch()
            Path(tmpdir, "tests").mkdir()

            info = detect_language_info(tmpdir, ["main.py", "utils.py"])

            assert info.language == "python"
            assert info.framework == "pytest"
            assert info.test_directory == "tests/"
            assert info.test_file_pattern == "test_*.py"

    def test_detect_javascript_with_jest(self):
        """Test full JavaScript detection with Jest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "package.json").touch()
            Path(tmpdir, "jest.config.js").touch()

            info = detect_language_info(tmpdir, ["index.js", "app.js"])

            assert info.language == "javascript"
            assert info.framework == "jest"


class TestTestTemplates:
    """Tests for test templates."""

    def test_python_pytest_template(self):
        """Test Python pytest template."""
        template = get_python_pytest_template()
        assert "import pytest" in template
        assert "class Test" in template

    def test_python_unittest_template(self):
        """Test Python unittest template."""
        template = get_python_unittest_template()
        assert "import unittest" in template
        assert "unittest.TestCase" in template

    def test_javascript_jest_template(self):
        """Test JavaScript Jest template."""
        template = get_javascript_jest_template()
        assert "describe(" in template
        assert "test(" in template

    def test_typescript_jest_template(self):
        """Test TypeScript Jest template."""
        template = get_typescript_jest_template()
        assert "describe(" in template
        assert "require(" in template

    def test_go_test_template(self):
        """Test Go test template."""
        template = get_go_test_template()
        assert "func Test" in template
        assert "testing.T" in template

    def test_ruby_rspec_template(self):
        """Test Ruby RSpec template."""
        template = get_ruby_rspec_template()
        assert "RSpec.describe" in template
        assert "expect" in template


class TestGenerateTestFile:
    """Tests for test file generation."""

    def test_generate_python_test(self):
        """Test Python test file generation."""
        result = generate_test_file(
            language="python",
            framework="pytest",
            module_name="my_module",
            class_name="MyClass",
            test_name="test_something",
            test_description="something works",
        )
        assert "my_module" in result
        assert "MyClass" in result
        assert "test_something" in result
        assert "something works" in result

    def test_generate_javascript_test(self):
        """Test JavaScript test file generation."""
        result = generate_test_file(
            language="javascript",
            framework="jest",
            module_name="myModule",
            class_name="MyClass",
            test_name="does something",
            test_description="should do something",
            test_suite="main",
        )
        assert "describe(" in result

    def test_generate_go_test(self):
        """Test Go test file generation."""
        result = generate_test_file(
            language="go",
            framework="testing",
            module_name="mymodule",
            class_name="MyClass",
            test_name="Something",
            test_description="something works",
            package_name="mypackage",
        )
        assert "package mypackage" in result
        assert "func TestSomething" in result


class TestGetTestImports:
    """Tests for test imports."""

    def test_python_pytest_imports(self):
        """Test Python pytest imports."""
        imports = get_test_imports("python", "pytest")
        assert "import pytest" in imports

    def test_python_unittest_imports(self):
        """Test Python unittest imports."""
        imports = get_test_imports("python", "unittest")
        assert "import unittest" in imports

    def test_go_imports(self):
        """Test Go imports."""
        imports = get_test_imports("go", "testing")
        assert '"testing"' in imports

    def test_ruby_rspec_imports(self):
        """Test Ruby RSpec imports."""
        imports = get_test_imports("ruby", "rspec")
        assert "spec_helper" in imports[0]


class TestLanguageInfo:
    """Tests for LanguageInfo dataclass."""

    def test_language_info_defaults(self):
        """Test LanguageInfo default values."""
        info = LanguageInfo(language="python")
        assert info.language == "python"
        assert info.framework is None
        assert info.test_directory is None

    def test_language_info_full(self):
        """Test LanguageInfo with all fields."""
        info = LanguageInfo(
            language="python",
            framework="pytest",
            test_directory="tests/",
            test_file_pattern="test_*.py",
            config_files=["pytest.ini", "pyproject.toml"],
        )
        assert info.language == "python"
        assert info.framework == "pytest"
        assert info.test_directory == "tests/"

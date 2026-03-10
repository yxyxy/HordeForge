"""Test templates for different languages and frameworks."""

from __future__ import annotations


def get_python_pytest_template() -> str:
    """Get Python pytest test template."""
    return '''"""Tests for {module_name}."""

import pytest
from unittest.mock import Mock, patch


class Test{class_name}:
    """Test cases for {class_name}."""

    @pytest.fixture
    def mock_deps(self):
        """Setup mock dependencies."""
        # Add your fixtures here
        pass

    def test_{test_name}(self, mock_deps):
        """Test {test_description}."""
        # Arrange
        # Act
        # Assert
        pass


# Add more test classes as needed
'''


def get_python_unittest_template() -> str:
    """Get Python unittest test template."""
    return '''"""Tests for {module_name}."""

import unittest
from unittest.mock import Mock, patch


class Test{class_name}(unittest.TestCase):
    """Test cases for {class_name}."""

    def setUp(self):
        """Set up test fixtures."""
        pass

    def tearDown(self):
        """Tear down test fixtures."""
        pass

    def test_{test_name}(self):
        """Test {test_description}."""
        # Arrange
        # Act
        # Assert
        pass


if __name__ == "__main__":
    unittest.main()
'''


def get_javascript_jest_template() -> str:
    """Get JavaScript/TypeScript Jest test template."""
    return '''describe("{class_name}", () => {{
  beforeEach(() => {{
    // Setup
  }});

  afterEach(() => {{
    // Cleanup
  }});

  describe("{test_suite}", () => {{
    test("{test_description}", () => {{
      // Arrange
      // Act
      // Assert
    }});
  }});
}});
'''


def get_typescript_jest_template() -> str:
    """Get TypeScript Jest test template."""
    return '''describe("{class_name}", () => {{
  beforeEach(() => {{
    // Setup
  }});

  afterEach(() => {{
    // Cleanup
  }});

  describe("{test_suite}", () => {{
    test("{test_description}", () => {{
      // Arrange
      const {{}} = require("{{module_name}}");

      // Act

      // Assert
      expect(true).toBe(true);
    }});
  }});
}});
'''


def get_go_test_template() -> str:
    """Get Go test template."""
    return '''package {package_name}

import (
    "testing"
)

func Test{test_name}(t *testing.T) {{
    // Arrange

    // Act

    // Assert
}}

func Benchmark{test_name}(b *testing.B) {{
    for i := 0; i < b.N; i++ {{
        // Run the test
    }}
}}
'''


def get_ruby_rspec_template() -> str:
    """Get Ruby RSpec test template."""
    return '''RSpec.describe {class_name} do
  let(:subject) {{ described_class.new }}

  before do
    # Setup
  end

  describe "#{{method_name}}" do
    it "{test_description}" do
      # Arrange

      # Act

      # Expect
      expect(subject).to be_valid
    end
  end
end
'''


# Mapping of language/framework to template getter
TEMPLATE_GETTERS = {
    ("python", "pytest"): get_python_pytest_template,
    ("python", "unittest"): get_python_unittest_template,
    ("python", None): get_python_pytest_template,
    ("javascript", "jest"): get_javascript_jest_template,
    ("javascript", None): get_javascript_jest_template,
    ("typescript", "jest"): get_typescript_jest_template,
    ("typescript", None): get_typescript_jest_template,
    ("go", "testing"): get_go_test_template,
    ("go", None): get_go_test_template,
    ("ruby", "rspec"): get_ruby_rspec_template,
    ("ruby", None): get_ruby_rspec_template,
}


def get_test_template(language: str, framework: str | None = None) -> str:
    """Get the appropriate test template for language/framework.

    Args:
        language: Programming language
        framework: Testing framework (optional)

    Returns:
        Test template string
    """
    key = (language, framework)
    if key in TEMPLATE_GETTERS:
        return TEMPLATE_GETTERS[key]()

    # Fall back to language-only lookup
    if (language, None) in TEMPLATE_GETTERS:
        return TEMPLATE_GETTERS[(language, None)]()

    # Ultimate fallback to Python pytest
    return get_python_pytest_template()


def generate_test_file(
    language: str,
    framework: str | None,
    module_name: str,
    class_name: str,
    test_name: str,
    test_description: str,
    test_suite: str = "main",
    method_name: str = "",
    package_name: str = "",
) -> str:
    """Generate a test file from template with placeholders filled.

    Args:
        language: Programming language
        framework: Testing framework
        module_name: Module/file being tested
        class_name: Class being tested
        test_name: Name of test function
        test_description: Description of what test verifies
        test_suite: Name of test suite/describe block
        method_name: Method being tested (for Ruby)
        package_name: Package name (for Go)

    Returns:
        Filled test template
    """
    template = get_test_template(language, framework)

    replacements = {
        "{module_name}": module_name,
        "{class_name}": class_name,
        "{test_name}": test_name,
        "{test_description}": test_description,
        "{test_suite}": test_suite,
        "{method_name}": method_name,
        "{package_name}": package_name,
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


def get_test_imports(language: str, framework: str | None = None) -> list[str]:
    """Get standard imports for test file.

    Args:
        language: Programming language
        framework: Testing framework

    Returns:
        List of import statements
    """
    imports = {
        "python": {
            "pytest": ["import pytest", "from unittest.mock import Mock, patch"],
            "unittest": ["import unittest", "from unittest.mock import Mock, patch"],
            None: ["import pytest", "from unittest.mock import Mock, patch"],
        },
        "javascript": {
            "jest": [],  # ESM imports handled differently
            "mocha": [],
            None: [],
        },
        "typescript": {
            "jest": [],  # ESM imports handled differently
            None: [],
        },
        "go": {
            "testing": ['"testing"'],
            None: ['"testing"'],
        },
        "ruby": {
            "rspec": ["require 'spec_helper'"],
            "minitest": ["require 'minitest/autorun'"],
            None: ["require 'minitest/autorun'"],
        },
    }

    lang_imports = imports.get(language, {})
    return lang_imports.get(framework, lang_imports.get(None, []))

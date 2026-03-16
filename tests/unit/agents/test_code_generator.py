"""TDD: Test-Driven Development для Code Generator Agent"""

import os
import tempfile

from agents.code_generator import (
    CodeGenerator,
    FileType,
    RepositoryAnalysis,
    analyze_repository,
    generate_diff_patch,
    select_target_file,
)


class TestRepositoryAnalysis:
    """TDD: Repository Analysis"""

    def test_scan_project_structure(self):
        """TDD: Scan project structure"""
        # Create a temporary directory with test files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            test_file1 = os.path.join(temp_dir, "test1.py")
            test_file2 = os.path.join(temp_dir, "test2.js")
            os.makedirs(os.path.join(temp_dir, "src"))
            test_file3 = os.path.join(temp_dir, "src", "service.py")

            with open(test_file1, "w") as f:
                f.write("# Test file 1")
            with open(test_file2, "w") as f:
                f.write("// Test file 2")
            with open(test_file3, "w") as f:
                f.write("# Test file 3")

            # Analyze repository
            analysis = analyze_repository(temp_dir)

            # Assert
            assert "files" in analysis.file_tree
            assert analysis.language == FileType.PYTHON
            assert len(analysis.main_directories) >= 0
            assert len(analysis.target_files) > 0

    def test_identify_language_python(self):
        """TDD: Identify Python language"""
        # Create a temporary directory with Python files
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.py")
            with open(test_file, "w") as f:
                f.write("# Python file")

            analysis = analyze_repository(temp_dir)
            assert analysis.language == FileType.PYTHON

    def test_identify_language_javascript(self):
        """TDD: Identify JavaScript language"""
        # Create a temporary directory with JavaScript files
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.js")
            with open(test_file, "w") as f:
                f.write("// JavaScript file")

            analysis = analyze_repository(temp_dir)
            assert analysis.language == FileType.JAVASCRIPT

    def test_identify_language_unknown(self):
        """TDD: Identify unknown language"""
        # Create a temporary directory with unknown files
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("Text file")

            analysis = analyze_repository(temp_dir)
            assert analysis.language == FileType.UNKNOWN

    def test_nonexistent_directory(self):
        """TDD: Handle nonexistent directory"""
        analysis = analyze_repository("/nonexistent/path")
        assert analysis.language == FileType.UNKNOWN
        assert analysis.file_tree == {}


class TestTargetFileSelection:
    """TDD: Target File Selection"""

    def test_select_file_by_feature(self):
        """TDD: Select file by feature name"""
        # Create mock repository analysis
        analysis = RepositoryAnalysis()
        analysis.target_files = ["src/user_service.py", "src/auth.py", "src/api_handler.py"]

        # Test user feature
        feature = "add user"
        selected_file = select_target_file(feature, analysis)

        # Assert
        assert selected_file is not None
        assert "user" in selected_file.lower()

    def test_select_file_by_api_feature(self):
        """TDD: Select file by API feature"""
        # Create mock repository analysis
        analysis = RepositoryAnalysis()
        analysis.target_files = ["src/user_service.py", "src/api_handler.py", "src/models.py"]

        # Test API feature
        feature = "create API endpoint"
        selected_file = select_target_file(feature, analysis)

        # Assert
        assert selected_file is not None
        assert "api" in selected_file.lower()

    def test_select_file_no_match(self):
        """TDD: Select file when no match found"""
        # Create mock repository analysis
        analysis = RepositoryAnalysis()
        analysis.target_files = ["src/utils.py", "src/config.py"]

        # Test feature with no matching keywords
        feature = "unknown feature"
        selected_file = select_target_file(feature, analysis)

        # Assert - should return first file
        assert selected_file == "src/utils.py"

    def test_select_file_empty_analysis(self):
        """TDD: Select file with empty analysis"""
        # Create empty repository analysis
        analysis = RepositoryAnalysis()
        analysis.target_files = []

        # Test feature
        feature = "add user"
        selected_file = select_target_file(feature, analysis)

        # Assert - should return None
        assert selected_file is None


class TestDiffPatchGeneration:
    """TDD: Diff Patch Generation"""

    def test_generate_diff_new_file(self):
        """TDD: Generate diff for new file"""
        # Arrange
        new_code = "def add_user(name):\n    pass"

        # Act
        diff = generate_diff_patch("users.py", "", new_code)

        # Assert
        assert "diff --git a/users.py b/users.py" in diff
        assert "new file mode 100644" in diff
        assert "--- /dev/null" in diff
        assert "+++ b/users.py" in diff
        assert "@@ -0,0 +1,2 @@" in diff
        assert "+def add_user(name):" in diff
        assert "+    pass" in diff

    def test_generate_diff_existing_file(self):
        """TDD: Generate diff for existing file"""
        # Arrange
        old_code = "def add_user(name):\n    pass"
        new_code = "def add_user(name, email):\n    pass"

        # Act
        diff = generate_diff_patch("users.py", old_code, new_code)

        # Assert
        assert "diff --git a/users.py b/users.py" in diff
        assert "--- a/users.py" in diff
        assert "+++ b/users.py" in diff
        assert "@@" in diff
        assert "-def add_user(name):" in diff
        assert "+def add_user(name, email):" in diff

    def test_generate_diff_empty_old_content(self):
        """TDD: Generate diff with empty old content"""
        # Arrange
        old_code = ""
        new_code = "print('Hello, World!')"

        # Act
        diff = generate_diff_patch("hello.py", old_code, new_code)

        # Assert
        assert "diff --git a/hello.py b/hello.py" in diff
        assert "new file mode 100644" in diff
        assert "@@ -0,0 +1,1 @@" in diff
        assert "+print('Hello, World!')" in diff

    def test_generate_diff_complex_changes(self):
        """TDD: Generate diff with complex changes"""
        # Arrange
        old_code = """def greet(name):
    return f"Hello, {name}!"

def add(a, b):
    return a + b"""

        new_code = """def greet(name, title=""):
    if title:
        return f"Hello, {title} {name}!"
    return f"Hello, {name}!"

def subtract(a, b):
    return a - b"""

        # Act
        diff = generate_diff_patch("utils.py", old_code, new_code)

        # Assert
        assert "diff --git a/utils.py b/utils.py" in diff
        assert 'def greet(name, title=""):' in diff
        assert "+def subtract(a, b):" in diff
        assert "-def add(a, b):" in diff


class TestCodeGeneratorAgent:
    """TDD: Code Generator Agent Integration Tests"""

    def test_run_with_valid_feature(self):
        """TDD: Code generator runs with valid feature data"""
        # Arrange
        context = {
            "issue": {
                "title": "Implement user login API",
                "body": "Add API endpoint for user login with JWT authentication",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "code_patch"
        assert "files" in result["artifact_content"]
        assert "repository_analysis" in result["artifact_content"]
        assert result["confidence"] > 0.8

    def test_run_handles_empty_feature(self):
        """TDD: Code generator handles empty feature description"""
        # Arrange
        context = {"issue": {"title": "", "body": ""}}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_handles_missing_issue(self):
        """TDD: Code generator handles missing issue data"""
        # Arrange
        context = {}
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "FAILURE"

    def test_run_generates_python_code(self):
        """TDD: Code generator generates Python code"""
        # Arrange
        context = {
            "issue": {
                "title": "Add user registration",
                "body": "Implement user registration with email verification",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]
        assert "files" in content
        assert len(content["files"]) > 0
        file_patch = content["files"][0]
        assert "user" in file_patch["path"].lower()
        assert "def " in file_patch["new_content"]  # Python code indicator

    def test_run_generates_api_code(self):
        """TDD: Code generator generates API code for API features"""
        # Arrange
        context = {
            "issue": {
                "title": "Create API endpoint for user management",
                "body": "Implement CRUD operations for user entities",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]
        assert "files" in content
        file_patch = content["files"][0]
        assert "api" in file_patch["path"].lower() or "handler" in file_patch["path"].lower()

    def test_run_generates_proper_diff_format(self):
        """TDD: Code generator produces proper diff format"""
        # Arrange
        context = {
            "issue": {
                "title": "Add user management",
                "body": "Implement user management functionality",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]
        file_patch = content["files"][0]
        diff = file_patch["diff"]

        # Check diff format
        assert "diff --git" in diff
        assert "---" in diff
        assert "+++" in diff
        assert "@@" in diff

    def test_run_with_real_repository(self):
        """TDD: Code generator with real repository analysis"""
        # Arrange
        context = {
            "issue": {
                "title": "Add authentication service",
                "body": "Implement user authentication service",
            }
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        content = result["artifact_content"]

        # Check repository analysis
        repo_analysis = content["repository_analysis"]
        assert "language" in repo_analysis
        assert "main_directories" in repo_analysis
        assert "target_files_found" in repo_analysis

        # Check that language was detected
        assert repo_analysis["language"] in ["python", "javascript", "go", "java", "unknown"]

    def test_run_generates_all_required_fields(self):
        """TDD: Code generator generates all required fields"""
        # Arrange
        context = {
            "issue": {"title": "Test feature implementation", "body": "Implement test feature"}
        }
        generator = CodeGenerator()

        # Act
        result = generator.run(context)

        # Assert
        content = result["artifact_content"]

        # Check required fields
        assert "schema_version" in content
        assert "files" in content
        assert "decisions" in content
        assert "repository_analysis" in content
        assert "dry_run" in content
        assert "expected_failures" in content

        # Check file structure
        file_patch = content["files"][0]
        assert "path" in file_patch
        assert "diff" in file_patch
        assert "old_content" in file_patch
        assert "new_content" in file_patch
        assert "is_new_file" in file_patch

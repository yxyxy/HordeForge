"""TDD: Test-Driven Development для Architecture Planner Agent"""

from pathlib import Path

from agents.architecture_planner import (
    ArchitecturePlanner,
    ImpactLevel,
    analyze_code_structure,
    analyze_rag_documentation,
    calculate_impact_scope,
    generate_architecture_proposal,
    identify_affected_components,
)


class TestRAGDocumentationAnalysis:
    """TDD: RAG Documentation Analysis"""

    def test_analyze_rag_for_auth_pattern(self):
        """TDD: Analyze RAG for authentication pattern"""
        # Arrange
        feature = "Add JWT authentication to API"

        # Act
        result = analyze_rag_documentation(feature)

        # Assert
        assert "auth" in result["identified_patterns"]
        assert any(rec["aspect"] == "authentication" for rec in result["recommendations"])

    def test_analyze_rag_for_api_pattern(self):
        """TDD: Analyze RAG for API pattern"""
        # Arrange
        feature = "Add new API endpoints for user management"

        # Act
        result = analyze_rag_documentation(feature)

        # Assert
        assert "api" in result["identified_patterns"]
        assert any(rec["aspect"] == "api_design" for rec in result["recommendations"])

    def test_analyze_rag_for_database_pattern(self):
        """TDD: Analyze RAG for database pattern"""
        # Arrange
        feature = "Add new database models for orders"

        # Act
        result = analyze_rag_documentation(feature)

        # Assert
        assert "database" in result["identified_patterns"]
        assert any(rec["aspect"] == "data_layer" for rec in result["recommendations"])

    def test_analyze_rag_with_empty_feature(self):
        """TDD: Handle empty feature gracefully"""
        # Arrange
        feature = ""

        # Act
        result = analyze_rag_documentation(feature)

        # Assert
        assert result["identified_patterns"] == []
        assert result["recommendations"] == []


class TestCodeStructureAnalysis:
    """TDD: Code Structure Analysis"""

    def test_analyze_basic_project_structure(self, tmp_path):
        """TDD: Analyze basic project structure"""
        # Arrange
        # Create a temporary project structure
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "v1").mkdir()
        (tmp_path / "api" / "v1" / "users.py").write_text("# API code")
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "user.py").write_text("# Model code")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_users.py").write_text("# Test code")

        # Act
        result = analyze_code_structure(str(tmp_path))

        # Assert
        assert "api" in [m.replace("\\", "/").replace("\\\\", "/") for m in result["modules"]]
        assert "models" in [m.replace("\\", "/").replace("\\\\", "/") for m in result["modules"]]
        assert "tests" in [m.replace("\\", "/").replace("\\\\", "/") for m in result["modules"]]
        assert any(
            "api/v1/users.py" in f.replace("\\", "/").replace("\\\\", "/") for f in result["files"]
        )
        assert "python" in result["technologies"]

    def test_analyze_structure_with_nested_dirs(self, tmp_path):
        """TDD: Analyze structure with nested directories"""
        # Arrange
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "api").mkdir()
        (tmp_path / "backend" / "models").mkdir()
        (tmp_path / "backend" / "services").mkdir()

        # Act
        result = analyze_code_structure(str(tmp_path))

        # Assert
        assert "backend" in [m.replace("\\", "/").replace("\\\\", "/") for m in result["modules"]]
        assert any(
            "api" in d.replace("\\", "/").replace("\\\\", "/") for d in result["directories"]
        )
        assert any(
            "models" in d.replace("\\", "/").replace("\\\\", "/") for d in result["directories"]
        )
        assert any(
            "services" in d.replace("\\", "/").replace("\\\\", "/") for d in result["directories"]
        )

    def test_ignore_hidden_directories(self, tmp_path):
        """TDD: Ignore hidden directories in analysis"""
        # Arrange
        (tmp_path / ".git").mkdir()
        (tmp_path / ".venv").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# Main code")

        # Act
        result = analyze_code_structure(str(tmp_path))

        # Assert
        assert ".git" not in result["directories"]
        assert ".venv" not in result["directories"]
        assert "src" in result["modules"]


class TestAffectedComponentIdentification:
    """TDD: Affected Component Identification"""

    def test_identify_affected_modules_for_auth_feature(self):
        """TDD: Identify modules for auth feature"""
        # Arrange
        feature = "Add user authentication"
        code_structure = {
            "modules": ["api", "auth", "models", "utils"],
            "files": ["api/users.py", "auth/service.py", "models/user.py"],
            "directories": ["api", "auth", "models"],
        }

        # Act
        affected = identify_affected_components(feature, code_structure)

        # Assert
        assert "auth" in affected["modules"]
        assert any("auth" in f for f in affected["files"])

    def test_identify_affected_modules_for_api_feature(self):
        """TDD: Identify modules for API feature"""
        # Arrange
        feature = "Add user API endpoints"
        code_structure = {
            "modules": ["api", "models", "schemas"],
            "files": ["api/users.py", "models/user.py", "schemas/user.py"],
            "directories": ["api", "models", "schemas"],
        }

        # Act
        affected = identify_affected_components(feature, code_structure)

        # Assert
        assert "api" in affected["modules"]
        assert any("api" in f for f in affected["files"])

    def test_identify_affected_modules_for_model_feature(self):
        """TDD: Identify modules for model feature"""
        # Arrange
        feature = "Add new user model fields"
        code_structure = {
            "modules": ["api", "models", "schemas"],
            "files": ["api/users.py", "models/user.py", "schemas/user.py"],
            "directories": ["api", "models", "schemas"],
        }

        # Act
        affected = identify_affected_components(feature, code_structure)

        # Assert
        assert "models" in affected["modules"]
        assert any("models" in f for f in affected["files"])


class TestImpactScopeCalculation:
    """TDD: Impact Scope Calculation"""

    def test_calculate_high_impact_for_major_changes(self):
        """TDD: Calculate high impact for major changes"""
        # Arrange
        feature = "Refactor core authentication system"
        affected = {
            "modules": ["auth", "api", "models", "tests"],
            "files": ["auth/main.py", "api/auth.py"],
        }

        # Act
        impact = calculate_impact_scope(feature, affected)

        # Assert
        assert impact == ImpactLevel.HIGH

    def test_calculate_medium_impact_for_standard_changes(self):
        """TDD: Calculate medium impact for standard changes"""
        # Arrange
        feature = "Add new user profile endpoint"
        affected = {"modules": ["api", "models"], "files": ["api/users.py", "models/user.py"]}

        # Act
        impact = calculate_impact_scope(feature, affected)

        # Assert
        assert impact == ImpactLevel.MEDIUM

    def test_calculate_low_impact_for_minor_changes(self):
        """TDD: Calculate low impact for minor changes"""
        # Arrange
        feature = "Fix typo in user form"
        affected = {"modules": ["api"], "files": ["api/users.py"]}

        # Act
        impact = calculate_impact_scope(feature, affected)

        # Assert
        assert impact == ImpactLevel.LOW

    def test_calculate_impact_based_on_component_count(self):
        """TDD: Calculate impact based on number of affected components"""
        # Arrange
        feature = "Add new feature"
        affected_many = {"modules": [f"mod{i}" for i in range(15)], "files": []}
        affected_few = {"modules": ["mod1"], "files": []}

        # Act
        impact_many = calculate_impact_scope(feature, affected_many)
        impact_few = calculate_impact_scope(feature, affected_few)

        # Assert
        assert impact_many == ImpactLevel.HIGH
        assert impact_few == ImpactLevel.LOW


class TestArchitectureProposalGeneration:
    """TDD: Architecture Proposal Generation"""

    def test_generate_proposal_for_api_feature(self, tmp_path):
        """TDD: Generate proposal for API feature"""
        # Arrange
        feature = "Add user API endpoints"
        (tmp_path / "api").mkdir()
        (tmp_path / "models").mkdir()
        (tmp_path / "api" / "users.py").write_text("# API code")
        (tmp_path / "models" / "user.py").write_text("# Model code")

        # Act
        proposal = generate_architecture_proposal(feature, str(tmp_path))

        # Assert
        assert len(proposal.modules_to_modify) >= 1
        assert any("api" in mod for mod in proposal.modules_to_modify)
        assert len(proposal.files_to_create) >= 1
        assert any("api" in f for f in proposal.files_to_create)
        assert proposal.impact_scope in [ImpactLevel.LOW, ImpactLevel.MEDIUM, ImpactLevel.HIGH]

    def test_generate_proposal_for_auth_feature(self, tmp_path):
        """TDD: Generate proposal for auth feature"""
        # Arrange
        feature = "Add JWT authentication"
        (tmp_path / "auth").mkdir(exist_ok=True)
        (tmp_path / "api").mkdir(exist_ok=True)
        (tmp_path / "auth" / "service.py").write_text("# Auth service")
        (tmp_path / "api" / "auth.py").write_text("# Auth API")

        # Act
        proposal = generate_architecture_proposal(feature, str(tmp_path))

        # Assert
        assert any("auth" in mod for mod in proposal.modules_to_modify)
        assert proposal.risk_level in ["low", "medium", "high"]

    def test_generate_proposal_creates_appropriate_files(self):
        """TDD: Generate proposal creates appropriate files"""
        # Arrange
        feature = "Add product API endpoints"
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create minimal project structure
            api_dir = Path(tmp_dir) / "api"
            api_dir.mkdir()
            (api_dir / "v1").mkdir()

            # Act
            proposal = generate_architecture_proposal(feature, tmp_dir)

            # Assert
            assert any("product" in f.lower() for f in proposal.files_to_create)
            assert any("api" in f for f in proposal.files_to_create)


class TestArchitecturePlannerAgent:
    """TDD: Architecture Planner Agent Integration Tests"""

    def test_run_with_valid_feature(self, tmp_path):
        """TDD: Architecture planner runs with valid feature data"""
        # Arrange
        context = {
            "feature_description": "Add user authentication API",
            "project_path": str(tmp_path),
        }
        planner = ArchitecturePlanner()

        # Act
        result = planner.run(context)

        # Assert
        assert result["status"] == "SUCCESS"
        assert result["artifact_type"] == "architecture_proposal"
        assert "proposal" in result["artifact_content"]
        assert "analysis" in result["artifact_content"]
        assert result["confidence"] > 0.8

    def test_run_with_empty_feature(self):
        """TDD: Architecture planner handles empty feature"""
        # Arrange
        context = {"feature_description": "", "project_path": "."}
        planner = ArchitecturePlanner()

        # Act
        result = planner.run(context)

        # Assert
        assert result["status"] == "FAILED"

    def test_run_without_feature_description(self):
        """TDD: Architecture planner handles missing feature description"""
        # Arrange
        context = {"project_path": "."}
        planner = ArchitecturePlanner()

        # Act
        result = planner.run(context)

        # Assert
        assert result["status"] == "FAILED"

    def test_run_generates_expected_structure(self, tmp_path):
        """TDD: Architecture planner generates expected structure"""
        # Arrange
        context = {
            "feature_description": "Implement user CRUD operations",
            "project_path": str(tmp_path),
        }
        planner = ArchitecturePlanner()

        # Act
        result = planner.run(context)

        # Assert
        content = result["artifact_content"]
        assert "proposal" in content
        assert "modules_to_modify" in content["proposal"]
        assert "files_to_create" in content["proposal"]
        assert "impact_scope" in content["proposal"]
        assert "analysis" in content
        assert "rag_patterns" in content["analysis"]
        assert "code_structure_summary" in content["analysis"]

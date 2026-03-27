"""
Dependency Checker Agent

An agent that checks project dependencies for vulnerabilities and outdated components.
"""

import json
import logging
import os
from typing import Any

import packaging.version
import requests
from pydantic import BaseModel, Field

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DependencyContext(BaseModel):
    """Context for dependency checking operations"""

    project_path: str = Field(..., description="Path to the project directory")
    config_file: str | None = Field(
        None, description="Configuration file path (e.g., package.json, requirements.txt)"
    )


class DependencyScanResult(BaseModel):
    """Response model for dependency scanning"""

    status: str = Field(..., description="Overall status of the operation")
    dependencies: list[dict[str, Any]] = Field(..., description="List of discovered dependencies")
    project_path: str = Field(..., description="Path of the scanned project")
    details: dict[str, Any] | None = Field(None, description="Additional details about the scan")


class VulnerabilityCheckResult(BaseModel):
    """Response model for vulnerability checking"""

    status: str = Field(..., description="Overall status of the operation")
    vulnerabilities: list[dict[str, Any]] = Field(
        ..., description="List of discovered vulnerabilities"
    )
    dependency_count: int = Field(..., description="Total number of dependencies checked")
    vulnerable_count: int = Field(..., description="Number of dependencies with vulnerabilities")


class UpdateRecommendationResult(BaseModel):
    """Response model for update recommendations"""

    status: str = Field(..., description="Overall status of the operation")
    recommendations: list[dict[str, Any]] = Field(..., description="List of update recommendations")
    outdated_count: int = Field(..., description="Number of outdated dependencies")
    total_count: int = Field(..., description="Total number of dependencies")


class DependencyCheckerAgent(BaseAgent):
    """
    Dependency Checker Agent

    Checks project dependencies for vulnerabilities and outdated components.
    Supports various package managers and integrates with vulnerability databases.
    """

    def __init__(self):
        self.supported_formats = [
            "package.json",  # npm/yarn
            "requirements.txt",  # pip
            "Pipfile",  # pipenv
            "pyproject.toml",  # poetry/pip
            "pom.xml",  # maven
            "build.gradle",  # gradle
            "Gemfile",  # bundler (Ruby)
            "go.mod",  # Go modules
        ]
        self.vulnerability_db_url = "https://api.osv.dev/v1/query"

    def run(self, context: DependencyContext) -> dict[str, Any]:
        """
        Main entry point for the Dependency Checker Agent

        Args:
            context: DependencyContext containing project information

        Returns:
            Dictionary with dependency checking results
        """
        logger.info(f"Starting Dependency Checker Agent for project {context.project_path}")

        # Scan dependencies
        scan_result = self.scan_dependencies(context.project_path)

        # Check for vulnerabilities if dependencies were found
        vulnerability_result = None
        if scan_result.dependencies:
            vulnerability_result = self.check_vulnerabilities(scan_result.dependencies)

        # Generate update recommendations
        update_result = self.recommend_updates(scan_result.dependencies)

        return {
            "status": "completed",
            "scan_result": scan_result,
            "vulnerability_result": vulnerability_result,
            "update_result": update_result,
        }

    def scan_dependencies(self, project_path: str) -> DependencyScanResult:
        """
        Scan project dependencies from various configuration files

        Args:
            project_path: Path to the project directory

        Returns:
            DependencyScanResult with discovered dependencies
        """
        try:
            dependencies = []

            # Look for supported dependency files in the project directory
            for filename in self.supported_formats:
                file_path = os.path.join(project_path, filename)

                if os.path.exists(file_path):
                    deps = self._parse_dependency_file(file_path, filename)
                    dependencies.extend(deps)

            return DependencyScanResult(
                status="success",
                dependencies=dependencies,
                project_path=project_path,
                details={
                    "files_scanned": len(
                        [
                            f
                            for f in self.supported_formats
                            if os.path.exists(os.path.join(project_path, f))
                        ]
                    )
                },
            )
        except Exception as e:
            logger.error(f"Error scanning dependencies in {project_path}: {str(e)}")
            return DependencyScanResult(
                status="error",
                dependencies=[],
                project_path=project_path,
                details={"error": str(e)},
            )

    def _parse_dependency_file(self, file_path: str, file_type: str) -> list[dict[str, Any]]:
        """
        Parse a dependency file based on its type

        Args:
            file_path: Path to the dependency file
            file_type: Type of the dependency file

        Returns:
            List of dependencies
        """
        dependencies = []

        if file_type == "package.json":
            # Parse package.json for npm dependencies
            with open(file_path, encoding="utf-8") as f:
                try:
                    package_json = json.load(f)
                    deps = package_json.get("dependencies", {})
                    dev_deps = package_json.get("devDependencies", {})

                    for name, version in {**deps, **dev_deps}.items():
                        # Extract version from version specifiers like "^1.0.0", "~1.0.0", etc.
                        clean_version = version.strip("^~=>").split("||")[0].strip()
                        dependencies.append(
                            {
                                "name": name,
                                "version": clean_version,
                                "type": "npm",
                                "file": file_path,
                            }
                        )
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse {file_path} as JSON")

        elif file_type == "requirements.txt":
            # Parse requirements.txt for pip dependencies
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Handle different version specifiers
                        if "==" in line:
                            name, version = line.split("==", 1)
                            dependencies.append(
                                {
                                    "name": name.strip(),
                                    "version": version.strip(),
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )
                        elif ">=" in line:
                            name, version = line.split(">=", 1)
                            dependencies.append(
                                {
                                    "name": name.strip(),
                                    "version": version.strip(),
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )
                        elif "<=" in line:
                            name, version = line.split("<=", 1)
                            dependencies.append(
                                {
                                    "name": name.strip(),
                                    "version": version.strip(),
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )
                        elif ">" in line:
                            name, version = line.split(">", 1)
                            dependencies.append(
                                {
                                    "name": name.strip(),
                                    "version": version.strip(),
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )
                        elif "<" in line:
                            name, version = line.split("<", 1)
                            dependencies.append(
                                {
                                    "name": name.strip(),
                                    "version": version.strip(),
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )
                        else:
                            # Just package name without version
                            dependencies.append(
                                {
                                    "name": line,
                                    "version": "unknown",
                                    "type": "pip",
                                    "file": file_path,
                                }
                            )

        elif file_type == "Pipfile":
            # Parse Pipfile for pipenv dependencies
            import toml

            with open(file_path, encoding="utf-8") as f:
                try:
                    pipfile = toml.load(f)
                    deps = pipfile.get("packages", {})
                    dev_deps = pipfile.get("dev-packages", {})

                    for name, version_info in {**deps, **dev_deps}.items():
                        if isinstance(version_info, str):
                            version = version_info
                        elif isinstance(version_info, dict):
                            version = version_info.get("version", "unknown")
                        else:
                            version = "unknown"

                        # Clean version string
                        clean_version = str(version).strip("^~=>").split("||")[0].strip()

                        dependencies.append(
                            {
                                "name": name,
                                "version": clean_version,
                                "type": "pipenv",
                                "file": file_path,
                            }
                        )
                except Exception:
                    logger.warning(f"Could not parse {file_path} as TOML")

        elif file_type == "pyproject.toml":
            # Parse pyproject.toml for poetry/pip dependencies
            import toml

            with open(file_path, encoding="utf-8") as f:
                try:
                    pyproject = toml.load(f)
                    # Poetry dependencies
                    tool_section = pyproject.get("tool", {})
                    poetry_section = tool_section.get("poetry", {})
                    poetry_deps = poetry_section.get("dependencies", {})
                    poetry_dev_deps = poetry_section.get("dev-dependencies", {})

                    for name, version_info in {**poetry_deps, **poetry_dev_deps}.items():
                        if name == "python":  # Skip python version requirement
                            continue

                        if isinstance(version_info, str):
                            version = version_info
                        elif isinstance(version_info, dict):
                            version = version_info.get("version", "unknown")
                        else:
                            version = "unknown"

                        # Clean version string
                        clean_version = str(version).strip("^~=>").split("||")[0].strip()

                        dependencies.append(
                            {
                                "name": name,
                                "version": clean_version,
                                "type": "poetry",
                                "file": file_path,
                            }
                        )
                except Exception:
                    logger.warning(f"Could not parse {file_path} as TOML")

        # Add more parsers for other formats as needed

        return dependencies

    def check_vulnerabilities(self, dependencies: list[dict[str, Any]]) -> VulnerabilityCheckResult:
        """
        Check dependencies for known vulnerabilities using NVD database

        Args:
            dependencies: List of dependencies to check

        Returns:
            VulnerabilityCheckResult with vulnerability information
        """
        try:
            vulnerabilities = []

            for dep in dependencies:
                name = dep.get("name", "")
                version = dep.get("version", "")

                # Skip if version is unknown
                if version == "unknown":
                    continue

                vulns = self._query_vulnerability_database(name, version, dep.get("type", ""))
                if vulns:
                    vulnerabilities.extend(vulns)

            return VulnerabilityCheckResult(
                status="vulnerabilities_found" if vulnerabilities else "clean",
                vulnerabilities=vulnerabilities,
                dependency_count=len(dependencies),
                vulnerable_count=len(vulnerabilities),
            )
        except Exception as e:
            logger.error(f"Error checking vulnerabilities: {str(e)}")
            return VulnerabilityCheckResult(
                status="error",
                vulnerabilities=[],
                dependency_count=len(dependencies),
                vulnerable_count=0,
            )

    def _query_vulnerability_database(
        self, package_name: str, version: str, package_type: str
    ) -> list[dict[str, Any]]:
        """
        Query vulnerability database for a specific package and version.

        Args:
            package_name: Name of the package
            version: Version of the package
            package_type: Type of package manager (npm, pip, etc.)

        Returns:
            List of vulnerabilities for the package
        """
        ecosystem = self._resolve_osv_ecosystem(package_type)
        if ecosystem is None:
            return []

        payload = {
            "package": {
                "name": package_name,
                "ecosystem": ecosystem,
            },
            "version": version,
        }

        try:
            response = requests.post(self.vulnerability_db_url, json=payload, timeout=10)
            if response.status_code != 200:
                return []
            data = response.json()
        except Exception:
            return []

        vulnerabilities = []
        for vuln in data.get("vulns", []):
            if not isinstance(vuln, dict):
                continue

            vuln_id = str(vuln.get("id", "UNKNOWN"))
            details = vuln.get("details") or vuln.get("summary") or ""
            if not isinstance(details, str):
                details = str(details)

            aliases = vuln.get("aliases")
            primary_alias = None
            if isinstance(aliases, list) and aliases:
                primary_alias = aliases[0]

            vulnerabilities.append(
                {
                    "id": vuln_id,
                    "package": package_name,
                    "version": version,
                    "severity": self._extract_osv_severity(vuln),
                    "description": details[:5000] if details else "No description provided",
                    "url": f"https://osv.dev/vulnerability/{vuln_id}",
                    "alias": primary_alias,
                }
            )

        return vulnerabilities

    @staticmethod
    def _resolve_osv_ecosystem(package_type: str) -> str | None:
        mapping = {
            "npm": "npm",
            "pip": "PyPI",
            "pipenv": "PyPI",
            "poetry": "PyPI",
            "go": "Go",
            "gem": "RubyGems",
            "maven": "Maven",
        }
        return mapping.get(str(package_type).strip().lower())

    @staticmethod
    def _extract_osv_severity(vuln: dict[str, Any]) -> str:
        database_specific = vuln.get("database_specific")
        if isinstance(database_specific, dict):
            severity = database_specific.get("severity")
            if isinstance(severity, str) and severity.strip():
                return severity.strip().upper()

        severity_list = vuln.get("severity")
        if isinstance(severity_list, list) and severity_list:
            first_item = severity_list[0]
            if isinstance(first_item, dict):
                sev_type = first_item.get("type")
                if isinstance(sev_type, str) and sev_type.strip():
                    return sev_type.strip().upper()

        return "UNKNOWN"

    def recommend_updates(self, dependencies: list[dict[str, Any]]) -> UpdateRecommendationResult:
        """
        Recommend updates for outdated dependencies

        Args:
            dependencies: List of dependencies to check for updates

        Returns:
            UpdateRecommendationResult with update recommendations
        """
        try:
            recommendations = []
            outdated_count = 0

            for dep in dependencies:
                name = dep.get("name", "")
                current_version = dep.get("version", "")

                # Skip if version is unknown
                if current_version == "unknown":
                    continue

                latest_version = self._get_latest_version(name, dep.get("type", ""))

                if latest_version and self._is_outdated(current_version, latest_version):
                    recommendations.append(
                        {
                            "name": name,
                            "current_version": current_version,
                            "latest_version": latest_version,
                            "type": dep.get("type", ""),
                            "can_update": True,
                        }
                    )
                    outdated_count += 1

            return UpdateRecommendationResult(
                status="updates_available" if outdated_count > 0 else "up_to_date",
                recommendations=recommendations,
                outdated_count=outdated_count,
                total_count=len(dependencies),
            )
        except Exception as e:
            logger.error(f"Error recommending updates: {str(e)}")
            return UpdateRecommendationResult(
                status="error", recommendations=[], outdated_count=0, total_count=len(dependencies)
            )

    def _get_latest_version(self, package_name: str, package_type: str) -> str | None:
        """
        Get the latest version of a package from the respective registry

        Args:
            package_name: Name of the package
            package_type: Type of package manager (npm, pip, etc.)

        Returns:
            Latest version string or None if not found
        """
        try:
            if package_type == "npm":
                # Query npm registry
                response = requests.get(f"https://registry.npmjs.org/{package_name}", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("dist-tags", {}).get("latest")
            elif package_type in ["pip", "pipenv", "poetry"]:
                # Query PyPI
                response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("info", {}).get("version")
            # Add more registries as needed
        except Exception:
            # If online lookup fails, return None
            pass

        return None

    def _is_outdated(self, current_version: str, latest_version: str) -> bool:
        """
        Check if the current version is outdated compared to the latest version

        Args:
            current_version: Current version of the package
            latest_version: Latest version of the package

        Returns:
            True if the current version is outdated, False otherwise
        """
        try:
            # Use packaging.version to compare versions properly
            curr_ver = packaging.version.parse(current_version)
            latest_ver = packaging.version.parse(latest_version)
            return curr_ver < latest_ver
        except Exception:
            return False


# Backward compatibility for testing
def scan_dependencies(project_path: str):
    """Wrapper function for testing dependency scanning"""
    agent = DependencyCheckerAgent()
    return agent.scan_dependencies(project_path)


def check_vulnerabilities(dependencies: list[dict[str, Any]]):
    """Wrapper function for testing vulnerability checking"""
    agent = DependencyCheckerAgent()
    return agent.check_vulnerabilities(dependencies)


def recommend_updates(dependencies: list[dict[str, Any]]):
    """Wrapper function for testing update recommendations"""
    agent = DependencyCheckerAgent()
    return agent.recommend_updates(dependencies)

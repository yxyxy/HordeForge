"""
GitLab CI Client for CI Monitor Agent
"""

from typing import Any

import requests


class GitLabClient:
    """
    Client for interacting with GitLab CI
    """

    def __init__(self, base_url: str, token: str):
        """
        Initialize GitLab client

        Args:
            base_url: Base URL of the GitLab instance
            token: Personal access token for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()

        # Set up authentication header
        self.session.headers.update(
            {
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def get_pipeline_status(self, pipeline_id: str) -> str | None:
        """
        Get the status of a GitLab pipeline

        Args:
            pipeline_id: ID of the pipeline (format: "project_id:pipeline_id" or just pipeline_id if project context is known)

        Returns:
            Status of the pipeline (e.g., 'success', 'failure', 'pending', 'running')
        """
        try:
            # Split the pipeline_id to get project_id and pipeline_id if in format "project_id:pipeline_id"
            if ":" in pipeline_id:
                project_id, pipeline_id_part = pipeline_id.split(":", 1)
            else:
                # If we can't determine project_id from the pipeline_id, we'll need to handle this differently
                # For now, assume pipeline_id is the full path or that project_id is embedded
                project_id = None
                pipeline_id_part = pipeline_id

            # If project_id is not provided in the pipeline_id, we need to extract it differently
            # For this implementation, we'll assume pipeline_id is in the format "project_path:pipeline_id"
            if project_id is None:
                # Try to split by '/' to get project path
                parts = pipeline_id_part.split(":")
                if len(parts) >= 2:
                    project_path = ":".join(parts[:-1])
                    pipeline_id_part = parts[-1]
                else:
                    # If we can't parse it, return None
                    return None

                # Convert project path to URL-encoded format
                project_encoded = project_path.replace("/", "%2F")
                url = f"{self.base_url}/api/v4/projects/{project_encoded}/pipelines/{pipeline_id_part}"
            else:
                url = f"{self.base_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id_part}"

            response = self.session.get(url)
            response.raise_for_status()

            pipeline_info = response.json()

            # Map GitLab pipeline status to standard CI status
            status = pipeline_info.get("status")

            if status in ["created", "waiting_for_resource", "preparing", "pending"]:
                return "pending"
            elif status in ["running", "manual", "scheduled"]:
                return "running"
            elif status == "success":
                return "success"
            elif status in ["failed", "canceled", "skipped"]:
                return status  # Return the original status for failed, canceled, skipped
            else:
                return "unknown"

        except requests.exceptions.RequestException as e:
            print(f"Error fetching GitLab pipeline status: {e}")
            return None
        except KeyError:
            # If the expected keys aren't found, return unknown
            return "unknown"

    def get_pipeline_details(self, project_id: str, pipeline_id: str) -> dict[str, Any] | None:
        """
        Get detailed information about a specific pipeline

        Args:
            project_id: ID or path of the project
            pipeline_id: ID of the pipeline

        Returns:
            Detailed pipeline information
        """
        try:
            # Encode project ID if it contains slashes
            project_encoded = project_id.replace("/", "%2F")
            url = f"{self.base_url}/api/v4/projects/{project_encoded}/pipelines/{pipeline_id}"

            response = self.session.get(url)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error fetching GitLab pipeline details: {e}")
            return None

    def get_project_pipelines(self, project_id: str, limit: int = 10) -> list | None:
        """
        Get recent pipelines for a project

        Args:
            project_id: ID or path of the project
            limit: Number of pipelines to return (default 10)

        Returns:
            List of recent pipelines
        """
        try:
            # Encode project ID if it contains slashes
            project_encoded = project_id.replace("/", "%2F")
            url = f"{self.base_url}/api/v4/projects/{project_encoded}/pipelines?per_page={limit}"

            response = self.session.get(url)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error fetching GitLab project pipelines: {e}")
            return None

    def get_pipeline_jobs(self, project_id: str, pipeline_id: str) -> list | None:
        """
        Get all jobs for a specific pipeline

        Args:
            project_id: ID or path of the project
            pipeline_id: ID of the pipeline

        Returns:
            List of jobs in the pipeline
        """
        try:
            # Encode project ID if it contains slashes
            project_encoded = project_id.replace("/", "%2F")
            url = f"{self.base_url}/api/v4/projects/{project_encoded}/pipelines/{pipeline_id}/jobs"

            response = self.session.get(url)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error fetching GitLab pipeline jobs: {e}")
            return None

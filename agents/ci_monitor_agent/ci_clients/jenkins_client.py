"""
Jenkins CI Client for CI Monitor Agent
"""

from typing import Any

import requests


class JenkinsClient:
    """
    Client for interacting with Jenkins CI
    """

    def __init__(
        self, base_url: str, username: str = None, password: str = None, token: str = None
    ):
        """
        Initialize Jenkins client

        Args:
            base_url: Base URL of the Jenkins instance
            username: Username for authentication
            password: Password for authentication
            token: API token for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        # Set up authentication
        if token:
            self.session.auth = (username or "", token)
        elif username and password:
            self.session.auth = (username, password)

        # Set headers
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def get_pipeline_status(self, pipeline_id: str) -> str | None:
        """
        Get the status of a Jenkins pipeline/job

        Args:
            pipeline_id: ID/name of the pipeline/job

        Returns:
            Status of the pipeline (e.g., 'success', 'failure', 'pending', 'running')
        """
        try:
            # Jenkins API endpoint for job info
            url = f"{self.base_url}/job/{pipeline_id}/lastBuild/api/json"

            response = self.session.get(url)
            response.raise_for_status()

            build_info = response.json()

            # Map Jenkins build result to standard CI status
            result = build_info.get("result")
            building = build_info.get("building", False)

            if building:
                return "running"
            elif result == "SUCCESS":
                return "success"
            elif result == "FAILURE":
                return "failure"
            elif result == "UNSTABLE":
                return "unstable"
            elif result == "ABORTED":
                return "aborted"
            else:
                return "unknown"

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Jenkins pipeline status: {e}")
            return None
        except KeyError:
            # If the expected keys aren't found, return unknown
            return "unknown"

    def get_build_details(
        self, pipeline_id: str, build_number: int = None
    ) -> dict[str, Any] | None:
        """
        Get detailed information about a specific build

        Args:
            pipeline_id: ID/name of the pipeline/job
            build_number: Build number (defaults to last build)

        Returns:
            Detailed build information
        """
        try:
            if build_number is None:
                url = f"{self.base_url}/job/{pipeline_id}/lastBuild/api/json"
            else:
                url = f"{self.base_url}/job/{pipeline_id}/{build_number}/api/json"

            response = self.session.get(url)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Jenkins build details: {e}")
            return None

    def get_job_list(self) -> list | None:
        """
        Get list of all jobs in Jenkins

        Returns:
            List of job names
        """
        try:
            url = f"{self.base_url}/api/json?tree=jobs[name]"
            response = self.session.get(url)
            response.raise_for_status()

            data = response.json()
            return [job["name"] for job in data.get("jobs", [])]

        except requests.exceptions.RequestException as e:
            print(f"Error fetching Jenkins job list: {e}")
            return None

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import aiohttp
from pydantic import BaseModel

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class RepoConnector(BaseAgent):
    """
    Repo Connector Agent
    Connects to repositories and fetches issues, PRs, and metadata.
    """

    name = "repo_connector"
    description = "Connects repository context and returns deterministic metadata."

    class Config(BaseModel):
        repo_url: str
        token: str | None = None
        provider: str = "github"  # "github", "gitlab", "bitbucket"
        mock_mode: bool = False

    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _extract_repo_name(self, repo_url: str) -> str:
        """
        Extract repository name from URL in format 'owner/repo'.
        Handles both HTTPS and SSH formats.
        """
        if repo_url.startswith("git@"):
            # SSH format: git@github.com:owner/repo.git
            path_part = repo_url.split(":")[1]
            parts = path_part.split("/")
            repo_name = parts[-1].rstrip(".git")
            owner = parts[-2]
            return f"{owner}/{repo_name}"
        else:
            # HTTPS format: https://github.com/owner/repo.git
            parsed = urlparse(repo_url)
            path_parts = [part for part in parsed.path.strip("/").split("/") if part]
            if len(path_parts) >= 2:
                repo_name = path_parts[-1].rstrip(".git")
                owner = path_parts[-2]
                return f"{owner}/{repo_name}"
            else:
                raise ValueError(f"Invalid repository URL format: {repo_url}")

    async def connect_api(self, config: Config) -> dict[str, Any]:
        """
        Establish API connection to repository provider.
        """
        if config.mock_mode:
            return {
                "status": "connected",
                "provider": config.provider,
                "repo": config.repo_url,
                "authenticated": bool(config.token),
                "metadata": {
                    "files_structure": ["src/", "tests/", "README.md"],
                    "languages": ["python"],
                    "dependencies": ["requirements.txt"],
                },
            }

        try:
            if config.provider == "github":
                repo_name = self._extract_repo_name(config.repo_url)
                url = f"https://api.github.com/repos/{repo_name}"
                headers = {"User-Agent": "HordeForge-RepoConnector/1.0"}
                if config.token:
                    headers["Authorization"] = f"Bearer {config.token}"

                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        repo_data = await response.json()
                        return {
                            "status": "connected",
                            "provider": config.provider,
                            "repo": repo_data["full_name"],
                            "authenticated": bool(config.token),
                            "repo_data": repo_data,
                            "metadata": {
                                "description": repo_data.get("description", ""),
                                "language": repo_data.get("language"),
                                "stars": repo_data.get("stargazers_count", 0),
                                "forks": repo_data.get("forks_count", 0),
                                "size": repo_data.get("size", 0),
                            },
                        }
                    elif response.status == 401:
                        return {
                            "status": "failed",
                            "error": "Authentication failed - invalid token",
                            "details": "Token may be expired or invalid",
                        }
                    elif response.status == 404:
                        return {
                            "status": "failed",
                            "error": "Repository not found",
                            "details": "Check if the repository URL is correct and accessible",
                        }
                    else:
                        return {
                            "status": "failed",
                            "error": f"API connection failed: {response.status}",
                            "details": await response.text(),
                        }
            else:
                return {
                    "status": "failed",
                    "error": f"Unsupported provider: {config.provider}",
                    "supported_providers": ["github"],
                }
        except Exception as e:
            return {"status": "failed", "error": str(e), "exception_type": type(e).__name__}

    async def fetch_issues(
        self, config: Config, state: str = "open", labels: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Fetch issues from repository.
        """
        if config.mock_mode:
            return {
                "status": "success",
                "issues": [
                    {
                        "number": 1,
                        "title": "Sample issue",
                        "state": "open",
                        "labels": [{"name": "bug"}] if labels and "bug" in labels else [],
                        "body": "Sample issue description",
                        "created_at": "2026-03-10T00:00:00Z",
                    }
                ]
                if state == "open"
                else [],
            }

        try:
            if config.provider == "github":
                repo_name = self._extract_repo_name(config.repo_url)
                url = f"https://api.github.com/repos/{repo_name}/issues"
                params = {"state": state}
                if labels:
                    params["labels"] = ",".join(labels)

                headers = {"User-Agent": "HordeForge-RepoConnector/1.0"}
                if config.token:
                    headers["Authorization"] = f"Bearer {config.token}"

                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        issues = await response.json()
                        # Filter out pull requests since GitHub API returns both issues and PRs
                        issues_only = [issue for issue in issues if "pull_request" not in issue]

                        return {
                            "status": "success",
                            "issues": issues_only,
                            "count": len(issues_only),
                        }
                    else:
                        return {
                            "status": "failed",
                            "error": f"Failed to fetch issues: {response.status}",
                            "details": await response.text(),
                        }
            else:
                return {
                    "status": "failed",
                    "error": f"Unsupported provider: {config.provider}",
                    "supported_providers": ["github"],
                }
        except Exception as e:
            return {"status": "failed", "error": str(e), "exception_type": type(e).__name__}

    async def fetch_prs(self, config: Config, state: str = "open") -> dict[str, Any]:
        """
        Fetch pull requests from repository.
        """
        if config.mock_mode:
            return {
                "status": "success",
                "prs": [
                    {
                        "number": 1,
                        "title": "Sample PR",
                        "state": state,
                        "draft": False,
                        "merged": state == "closed",
                        "body": "Sample PR description",
                        "created_at": "2026-03-10T00:00:00Z",
                    }
                ]
                if state == "open"
                else [],
            }

        try:
            if config.provider == "github":
                repo_name = self._extract_repo_name(config.repo_url)
                url = f"https://api.github.com/repos/{repo_name}/pulls"
                params = {"state": state}

                headers = {"User-Agent": "HordeForge-RepoConnector/1.0"}
                if config.token:
                    headers["Authorization"] = f"Bearer {config.token}"

                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        prs = await response.json()

                        return {"status": "success", "prs": prs, "count": len(prs)}
                    else:
                        return {
                            "status": "failed",
                            "error": f"Failed to fetch PRs: {response.status}",
                            "details": await response.text(),
                        }
            else:
                return {
                    "status": "failed",
                    "error": f"Unsupported provider: {config.provider}",
                    "supported_providers": ["github"],
                }
        except Exception as e:
            return {"status": "failed", "error": str(e), "exception_type": type(e).__name__}

    async def run(self, context: dict) -> dict:
        """
        Main entry point for the agent.
        """
        return await self._run_async(context)

    async def _run_async(self, context: dict) -> dict:
        """
        Async implementation of run - called internally by sync run() method.
        """
        repo_url = context.get("repo_url")
        token = context.get("github_token") or context.get("token")
        mock_mode = bool(context.get("mock_mode", False))
        operation = context.get("operation", "connect")
        state = context.get("state", "open")
        labels = context.get("labels", [])

        if not isinstance(repo_url, str) or not repo_url.strip():
            result = build_agent_result(
                status="BLOCKED",
                artifact_type="repository_metadata",
                artifact_content={"available": False},
                reason="Repository URL is required for initialization.",
                confidence=1.0,
                logs=["Missing required context: repo_url."],
                next_actions=["request_repository_context"],
            )
            return result

        config = self.Config(repo_url=repo_url.strip(), token=token, mock_mode=mock_mode)

        async with self:
            if operation == "connect":
                result = await self.connect_api(config)
            elif operation == "fetch_issues":
                result = await self.fetch_issues(config, state, labels)
            elif operation == "fetch_prs":
                result = await self.fetch_prs(config, state)
            else:
                result = build_agent_result(
                    status="BLOCKED",
                    artifact_type="repository_operation",
                    artifact_content={},
                    reason=f"Unknown operation: {operation}",
                    confidence=1.0,
                    logs=[f"Invalid operation requested: {operation}"],
                    next_actions=["request_valid_operation"],
                )
                return result

            if result["status"] in ["connected", "success"]:
                # Extract repository metadata for test compatibility
                repo_data = result.get("repo_data", {})
                full_name = repo_data.get("full_name", "")
                parts = full_name.split("/") if full_name else ["", ""]

                # Build metadata in format expected by tests
                metadata = {
                    "repo_url": config.repo_url,
                    "owner": parts[0] if len(parts) > 0 else "",
                    "repo_name": parts[1] if len(parts) > 1 else "",
                    "has_auth": bool(token),
                    "connection_mode": "mock" if mock_mode else "live",
                    "mock_mode": mock_mode,
                    **result.get("metadata", {}),
                }

                agent_result = build_agent_result(
                    status="SUCCESS",
                    artifact_type="repository_data",  # Changed to match test expectation
                    artifact_content=metadata,
                    reason=f"Repository {operation} completed successfully",
                    confidence=0.95,
                    logs=[f"Repository {operation} operation completed"],
                    next_actions=["process_repository_data"],
                )
                return agent_result
            else:
                agent_result = build_agent_result(
                    status="FAILED",
                    artifact_type="repository_operation",
                    artifact_content={},
                    reason=f"Repository operation failed: {result.get('error', 'Unknown error')}",
                    confidence=0.5,
                    logs=[f"Repository operation failed: {result.get('error')}"],
                    next_actions=["retry_repository_operation", "check_credentials"],
                )
                return agent_result


def main():
    """
    Example usage of RepoConnector agent.
    """
    connector = RepoConnector()

    # Example context for connecting to a repository
    context = {
        "repo_url": "https://github.com/example/repo",
        "token": "your_token_here",
        "operation": "connect",
    }

    result = connector.run(context)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

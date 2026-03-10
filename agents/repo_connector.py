from __future__ import annotations

import re
from urllib.parse import urlparse

from agents.context_utils import build_agent_result


class RepoConnector:
    name = "repo_connector"
    description = "Connects repository context and returns deterministic metadata."

    @staticmethod
    def _parse_repo_url(repo_url: str) -> dict[str, str]:
        if repo_url.startswith("git@"):
            pattern = r"^git@([^:]+):([^/]+)/(.+?)(?:\.git)?$"
            match = re.match(pattern, repo_url)
            if not match:
                raise ValueError(f"Invalid repository URL: {repo_url}")
            host, owner, repo_name = match.groups()
            return {"host": host, "owner": owner, "repo_name": repo_name}

        parsed = urlparse(repo_url)
        path_parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(path_parts) < 2:
            raise ValueError(f"Invalid repository URL: {repo_url}")
        owner = path_parts[0]
        repo_name = path_parts[1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        host = parsed.netloc or "github.com"
        return {"host": host, "owner": owner, "repo_name": repo_name}

    def run(self, context: dict) -> dict:
        repo_url = context.get("repo_url")
        token = context.get("github_token") or context.get("token")
        mock_mode = bool(context.get("mock_mode", False))

        if not isinstance(repo_url, str) or not repo_url.strip():
            return build_agent_result(
                status="BLOCKED",
                artifact_type="repository_metadata",
                artifact_content={"available": False},
                reason="Repository URL is required for initialization.",
                confidence=1.0,
                logs=["Missing required context: repo_url."],
                next_actions=["request_repository_context"],
            )

        parsed = self._parse_repo_url(repo_url.strip())
        metadata = {
            "repo_url": repo_url.strip(),
            "host": parsed["host"],
            "owner": parsed["owner"],
            "repo_name": parsed["repo_name"],
            "full_name": f"{parsed['owner']}/{parsed['repo_name']}",
            "default_branch": "main",
            "has_auth": bool(token),
            "mock_mode": mock_mode,
            "connection_mode": "mock" if mock_mode else "live",
        }
        return build_agent_result(
            status="SUCCESS",
            artifact_type="repository_metadata",
            artifact_content=metadata,
            reason="Repository metadata assembled from provided context.",
            confidence=0.95,
            logs=[f"Repository metadata prepared for {metadata['full_name']}."],
            next_actions=["rag_initializer"],
        )

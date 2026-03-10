#!/usr/bin/env python3
"""Setup script for test sandbox repository.

This script populates a GitHub sandbox repository with test data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
import yaml


def create_issue(
    session: requests.Session,
    api_url: str,
    token: str,
    title: str,
    body: str,
    labels: list[str],
) -> dict:
    """Create a GitHub issue."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{api_url}/issues"
    data = {"title": title, "body": body, "labels": labels}
    
    response = session.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()


def create_file(
    session: requests.Session,
    api_url: str,
    token: str,
    path: str,
    content: str,
    branch: str = "main",
    message: str = "Add test file",
) -> dict:
    """Create or update a file in the repository."""
    import base64
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{api_url}/contents/{path}"
    
    # Check if file exists
    get_response = session.get(url, headers=headers, params={"ref": branch})
    sha = None
    if get_response.status_code == 200:
        sha = get_response.json().get("sha")
    
    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        data["sha"] = sha
    
    response = session.put(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()


def create_branch(
    session: requests.Session,
    api_url: str,
    token: str,
    branch_name: str,
    base_branch: str = "main",
) -> dict:
    """Create a new branch."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    
    # Get SHA of base branch
    ref_url = f"{api_url}/git/ref/heads/{base_branch}"
    ref_response = session.get(ref_url, headers=headers)
    ref_response.raise_for_status()
    base_sha = ref_response.json()["object"]["sha"]
    
    # Create new branch
    create_url = f"{api_url}/git/refs"
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": base_sha,
    }
    response = session.post(create_url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()


def setup_sandbox(
    token: str,
    org: str,
    repo: str,
    config_path: str | None = None,
) -> None:
    """Set up the test sandbox repository."""
    session = requests.Session()
    api_url = f"https://api.github.com/repos/{org}/{repo}"
    
    # Load config
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    issues_config = config.get("issues", [])
    code_files = config.get("code_files", [])
    test_files = config.get("test_files", [])
    
    print(f"Setting up sandbox: {org}/{repo}")
    
    # Create issues
    print(f"\nCreating {len(issues_config)} issues...")
    for issue in issues_config:
        try:
            result = create_issue(
                session,
                api_url,
                token,
                issue["title"],
                issue["body"],
                issue.get("labels", []),
            )
            print(f"  ✓ Created issue: {result['number']} - {issue['title']}")
        except Exception as e:
            print(f"  ✗ Failed to create issue: {e}")
    
    # Create code files
    print(f"\nCreating {len(code_files)} code files...")
    for file in code_files:
        try:
            result = create_file(
                session,
                api_url,
                token,
                file["path"],
                file["content"],
                message=f"Add {file['path']}",
            )
            print(f"  ✓ Created: {file['path']}")
        except Exception as e:
            print(f"  ✗ Failed to create {file['path']}: {e}")
    
    # Create test files
    print(f"\nCreating {len(test_files)} test files...")
    for file in test_files:
        try:
            result = create_file(
                session,
                api_url,
                token,
                file["path"],
                file["content"],
                message=f"Add test: {file['path']}",
            )
            print(f"  ✓ Created: {file['path']}")
        except Exception as e:
            print(f"  ✗ Failed to create {file['path']}: {e}")
    
    print("\n✓ Sandbox setup complete!")
    print(f"  Repository: https://github.com/{org}/{repo}")
    print(f"  Issues: https://github.com/{org}/{repo}/issues")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Set up test sandbox repository")
    parser.add_argument("--token", required=True, help="GitHub personal access token")
    parser.add_argument("--org", required=True, help="GitHub organization")
    parser.add_argument("--repo", default="hordeforge-sandbox", help="Repository name")
    parser.add_argument("--config", help="Path to config file")
    
    args = parser.parse_args()
    
    try:
        setup_sandbox(
            token=args.token,
            org=args.org,
            repo=args.repo,
            config_path=args.config,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

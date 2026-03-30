"""Patch workflow orchestrator for applying code changes to GitHub repositories.

This module provides the PatchWorkflowOrchestrator class that handles the complete
workflow of applying generated code patches: branch creation, committing files,
pushing, and creating pull requests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.github_client import (
    GitHubApiError,
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a file change in a patch."""

    path: str
    content: str
    change_type: str  # "create", "modify", "delete"
    sha: str | None = None  # Required for modify/delete


@dataclass
class PatchWorkflowResult:
    """Result of a patch workflow execution."""

    success: bool = False
    branch_name: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    files_changed: list[str] = field(default_factory=list)
    commit_sha: str | None = None
    error: str | None = None
    rollback_performed: bool = False


@dataclass
class PatchWorkflowConfig:
    """Configuration for patch workflow."""

    branch_prefix: str = "hordeforge/"
    base_branch: str = "main"
    commit_message_prefix: str = "HordeForge: "
    max_retries: int = 2


class PatchWorkflowOrchestrator:
    """Orchestrates the complete patch application workflow.

    Workflow steps:
    1. Validate patch (check files exist for modify/delete)
    2. Create feature branch from base
    3. Apply each file change (create/modify/delete)
    4. Push branch to remote
    5. Create pull request
    6. Rollback on failure (delete branch)
    """

    def __init__(
        self,
        github_client: GitHubClient,
        config: PatchWorkflowConfig | None = None,
    ) -> None:
        self.client = github_client
        self.config = config or PatchWorkflowConfig()
        self.logger = logging.getLogger("hordeforge.patch_workflow")

    def apply_patch(
        self,
        files: list[FileChange],
        pr_title: str,
        pr_body: str,
        branch_name: str | None = None,
    ) -> PatchWorkflowResult:
        """Apply a complete patch and create a pull request.

        Args:
            files: List of file changes to apply
            pr_title: Title for the pull request
            pr_body: Body/description for the pull request
            branch_name: Optional branch name (generated if not provided)

        Returns:
            PatchWorkflowResult with success status and PR details
        """
        # Generate branch name if not provided
        if not branch_name:
            import uuid

            short_id = uuid.uuid4().hex[:8]
            branch_name = f"{self.config.branch_prefix}feature-{short_id}"

        result = PatchWorkflowResult(branch_name=branch_name)

        try:
            # Step 1: Validate patch
            self._validate_patch(files)

            # Step 2: Create branch
            self.logger.info(f"Creating branch: {branch_name}")
            self.client.create_branch(branch_name, self.config.base_branch)

            # Step 3: Apply file changes
            files_changed = []
            for fc in files:
                self._apply_file_change(fc, branch_name)
                files_changed.append(fc.path)

            result.files_changed = files_changed

            # Step 4: Push branch
            self.logger.info(f"Pushing branch: {branch_name}")
            # Note: Branch is automatically pushed when we commit

            # Step 5: Create PR
            self.logger.info(f"Creating pull request: {pr_title}")
            pr = self.client.create_pr(
                title=pr_title,
                head=branch_name,
                base=self.config.base_branch,
                body=pr_body,
            )

            result.pr_number = pr.get("number")
            result.pr_url = pr.get("html_url")
            result.success = True

            self.logger.info(f"Patch applied successfully. PR #{result.pr_number}: {result.pr_url}")
            return result

        except (GitHubApiError, GitHubAuthError) as e:
            result.error = str(e)
            self.logger.error(f"Patch workflow failed: {e}")

            # Attempt rollback
            try:
                self.logger.info(f"Attempting rollback: deleting branch {branch_name}")
                self.client.delete_branch(branch_name)
                result.rollback_performed = True
            except Exception as rollback_error:
                self.logger.error(f"Rollback failed: {rollback_error}")

            return result

    def _validate_patch(self, files: list[FileChange]) -> None:
        """Validate patch before applying.

        Raises:
            ValueError: If patch is invalid
        """
        for fc in files:
            if fc.change_type == "delete":
                if not fc.sha:
                    raise ValueError(f"Cannot delete {fc.path}: SHA required")

            elif fc.change_type == "modify":
                if not fc.sha:
                    # Try to get SHA from existing file
                    try:
                        file_info = self.client.get_file_content(fc.path)
                        fc.sha = file_info.get("sha")
                    except GitHubNotFoundError:
                        # File doesn't exist - treat as create
                        fc.change_type = "create"
                        fc.sha = None

            elif fc.change_type == "create":
                # Check if file already exists
                try:
                    file_info = self.client.get_file_content(fc.path)
                    fc.sha = file_info.get("sha")
                    self.logger.warning(f"File {fc.path} exists, will update (SHA: {fc.sha})")
                    fc.change_type = "modify"
                except GitHubNotFoundError:
                    pass  # New file - good

    def _apply_file_change(self, fc: FileChange, branch: str) -> None:
        """Apply a single file change.

        Args:
            fc: File change to apply
            branch: Branch to apply change to
        """
        commit_message = (
            f"{self.config.commit_message_prefix}{fc.change_type.capitalize()} {fc.path}"
        )

        if fc.change_type == "delete":
            self.logger.info(f"Deleting file: {fc.path}")
            self.client.delete_file(
                path=fc.path,
                message=commit_message,
                sha=fc.sha,
                branch=branch,
            )
        else:
            self.logger.info(f"{fc.change_type.capitalize()} file: {fc.path}")
            self.client.create_or_update_file(
                path=fc.path,
                content=fc.content,
                message=commit_message,
                branch=branch,
                sha=fc.sha,
            )


def create_patch_from_code_result(code_result: dict[str, Any]) -> list[FileChange]:
    """Create FileChange objects from code generation result.

    Args:
        code_result: Result from LLM code generation

    Returns:
        List of FileChange objects
    """
    files: list[FileChange] = []

    raw_files = code_result.get("files", [])
    if not isinstance(raw_files, list):
        return files

    for file_data in raw_files:
        if not isinstance(file_data, dict):
            continue

        path_raw = file_data.get("path")
        path = str(path_raw).strip() if isinstance(path_raw, str) else ""
        if not path:
            continue

        change_type_raw = file_data.get("change_type")
        change_type = str(change_type_raw).strip().lower() if change_type_raw else ""

        content = file_data.get("content")
        if not isinstance(content, str):
            diff = file_data.get("diff")
            content = str(diff) if isinstance(diff, str) else ""

        if change_type not in {"create", "modify", "delete"}:
            diff_text = file_data.get("diff")
            if isinstance(diff_text, str):
                first_line = diff_text.strip().splitlines()[0] if diff_text.strip() else ""
                if first_line.startswith("# "):
                    candidate = first_line.removeprefix("# ").strip().lower()
                    if candidate in {"create", "modify", "delete"}:
                        change_type = candidate
            if change_type not in {"create", "modify", "delete"}:
                change_type = "create"

        fc = FileChange(path=path, content=content, change_type=change_type)
        files.append(fc)

    return files


def apply_code_patch(
    github_client: GitHubClient,
    code_result: dict[str, Any],
    pr_title: str,
    pr_body: str,
    branch_name: str | None = None,
) -> PatchWorkflowResult:
    """Convenience function to apply a code patch.

    Args:
        github_client: GitHubClient instance
        code_result: Result from LLM code generation
        pr_title: Title for the pull request
        pr_body: Body for the pull request
        branch_name: Optional branch name

    Returns:
        PatchWorkflowResult
    """
    orchestrator = PatchWorkflowOrchestrator(github_client)
    files = create_patch_from_code_result(code_result)
    return orchestrator.apply_patch(files, pr_title, pr_body, branch_name)

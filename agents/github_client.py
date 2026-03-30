from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests


class GitHubClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        url: str | None = None,
        response_body: Any | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.url = url
        self.response_body = response_body
        self.retryable = retryable


class GitHubTransportError(GitHubClientError):
    pass


class GitHubApiError(GitHubClientError):
    pass


class GitHubAuthError(GitHubApiError):
    pass


class GitHubNotFoundError(GitHubApiError):
    pass


class GitHubValidationError(GitHubApiError):
    pass


class GitHubRateLimitError(GitHubApiError):
    pass


class GitHubServerError(GitHubApiError):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str,
        repo: str,
        *,
        session: requests.Session | Any | None = None,
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
        timeout_seconds: float = 15.0,
    ) -> None:
        normalized_token = str(token).strip()
        if not normalized_token:
            raise ValueError("GitHub token must be a non-empty string")
        self.repo = repo
        self.api_url = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"token {normalized_token}",
            "Accept": "application/vnd.github+json",
        }
        self.session = session or requests.Session()
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = max(0.0, float(backoff_seconds))
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.logger = logging.getLogger("hordeforge.github_client")

    # =========================================================================
    # Pagination Helpers (HF-P6-001)
    # =========================================================================

    def _parse_link_header(self, response: requests.Response) -> dict[str, str]:
        """Parse Link header and return dict of rel -> url.

        Args:
            response: HTTP response with Link header

        Returns:
            Dict with 'next', 'prev', 'first', 'last' keys mapped to URLs
        """
        links: dict[str, str] = {}
        link_header = response.headers.get("Link") or response.headers.get("link")
        if not link_header:
            return links

        # Parse Link header: <url>; rel="name", <url2>; rel="name2"
        pattern = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"')
        for match in pattern.finditer(link_header):
            url, rel = match.groups()
            links[rel] = url

        return links

    def _extract_page_info(self, response: requests.Response) -> dict[str, Any]:
        """Extract pagination info from response headers.

        Args:
            response: HTTP response

        Returns:
            Dict with page info: current_page, per_page, total, has_next, has_prev
        """
        info: dict[str, Any] = {
            "current_page": 1,
            "per_page": 30,
            "total": None,
            "has_next": False,
            "has_prev": False,
        }

        # Parse Link header
        links = self._parse_link_header(response)
        info["has_next"] = "next" in links
        info["has_prev"] = "prev" in links

        # Try to get per_page from query params in Link URLs
        if "next" in links:
            parsed = urlparse(links["next"])
            params = dict(p.split("=") for p in parsed.query.split("&") if "=" in p)
            if "per_page" in params:
                info["per_page"] = int(params["per_page"])
            if "page" in params:
                info["current_page"] = int(params["page"])

        # Try X-Total-Count header for total
        total = response.headers.get("X-Total-Count")
        if total:
            try:
                info["total"] = int(total)
            except ValueError:
                pass

        return info

    def _log_pagination(self, method: str, page_info: dict[str, Any]) -> None:
        """Log pagination information.

        Args:
            method: API method name
            page_info: Page info dict from _extract_page_info
        """
        self.logger.info(
            "github_pagination method=%s page=%s per_page=%s total=%s has_next=%s has_prev=%s",
            method,
            page_info.get("current_page", "?"),
            page_info.get("per_page", "?"),
            page_info.get("total", "?"),
            page_info.get("has_next", False),
            page_info.get("has_prev", False),
        )

    # =========================================================================
    # Base Request with Pagination (HF-P6-001-ST04)
    # =========================================================================

    def _request_with_pagination(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        auto_paginate: bool = False,
        max_pages: int = 10,
    ) -> dict[str, Any]:
        """Make HTTP request with optional automatic pagination.

        Args:
            method: HTTP method
            path: API path
            payload: Request body
            params: Query parameters
            auto_paginate: If True, follow 'next' links automatically
            max_pages: Maximum pages to fetch when auto_paginate=True

        Returns:
            Dict with 'items' (list), 'pagination' (page info), 'raw' (full response)
        """
        if not auto_paginate:
            # Single request without pagination
            result = self._request(method, path, payload=payload, params=params)
            return {
                "items": result.get("items", []) if isinstance(result, dict) else result,
                "pagination": {
                    "current_page": 1,
                    "per_page": params.get("per_page", 30) if params else 30,
                },
                "raw": result,
            }

        # Auto-paginate: collect all pages
        all_items: list[Any] = []
        page = params.get("page", 1) if params else 1
        per_page = params.get("per_page", 30) if params else 30
        pages_fetched = 0

        current_params = dict(params) if params else {}
        current_params["per_page"] = per_page

        while pages_fetched < max_pages:
            current_params["page"] = page
            result = self._request(method, path, payload=payload, params=current_params)

            # Get response for header info
            # We need to make a separate request to get headers
            url = f"{self.api_url}{path}"
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=self.headers,
                json=payload,
                params=current_params,
                timeout=self.timeout_seconds,
            )

            page_info = self._extract_page_info(response)
            self._log_pagination(method.upper() + " " + path, page_info)

            # Extract items
            if isinstance(result, dict):
                items = result.get("items", [])
                if not items:
                    items = result.get("pulls", [])
                    if not items:
                        items = result.get("issues", [])
            else:
                items = result if isinstance(result, list) else []

            all_items.extend(items)
            pages_fetched += 1

            # Check if there's a next page
            if not page_info.get("has_next"):
                break

            page += 1

        return {
            "items": all_items,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total": len(all_items),
                "pages_fetched": pages_fetched,
            },
            "raw": {"items": all_items},
        }

    @staticmethod
    def _safe_json(response: Any) -> Any | None:
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _is_success_status(status_code: int) -> bool:
        return 200 <= status_code < 300

    @staticmethod
    def _is_transient_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _resolve_backoff(self, attempt: int, response: Any | None = None) -> float:
        backoff = self.backoff_seconds * (2 ** max(0, attempt - 1))
        if response is None:
            return backoff

        retry_after_raw = ""
        headers = getattr(response, "headers", None)
        if headers and hasattr(headers, "get"):
            retry_after_raw = str(headers.get("Retry-After", "")).strip()
        if not retry_after_raw:
            return backoff

        try:
            retry_after = float(retry_after_raw)
        except ValueError:
            return backoff
        return max(backoff, max(0.0, retry_after))

    def _log_retry(
        self,
        *,
        method: str,
        url: str,
        attempt: int,
        backoff_seconds: float,
        reason: str,
        status_code: int | None = None,
    ) -> None:
        self.logger.warning(
            (
                "github_request_retry method=%s url=%s attempt=%s max_retries=%s "
                "status_code=%s backoff_seconds=%.2f reason=%s"
            ),
            method.upper(),
            url,
            attempt,
            self.max_retries,
            status_code if status_code is not None else "n/a",
            backoff_seconds,
            reason,
        )

    @staticmethod
    def _format_error_message(payload: Any, fallback_text: str) -> str:
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or fallback_text
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                details: list[str] = []
                for item in errors:
                    if isinstance(item, dict):
                        detail = item.get("message") or item.get("code") or item.get("field")
                        if detail:
                            details.append(str(detail))
                    elif item:
                        details.append(str(item))
                if details:
                    return f"{message} ({'; '.join(details)})"
            return str(message)
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        return fallback_text

    @staticmethod
    def _is_rate_limit_403(status_code: int, payload: Any, headers: Any) -> bool:
        if status_code != 403:
            return False

        if headers and hasattr(headers, "get"):
            remaining = str(headers.get("X-RateLimit-Remaining", "")).strip()
            if remaining == "0":
                return True

        if isinstance(payload, dict):
            message = str(payload.get("message", "")).lower()
            if "rate limit" in message:
                return True
        return False

    def _build_api_error(self, method: str, url: str, response: Any) -> GitHubClientError:
        payload = self._safe_json(response)
        fallback_text = str(getattr(response, "text", "")).strip() or "Unknown GitHub API error."
        message = self._format_error_message(payload, fallback_text)
        status_code = int(getattr(response, "status_code", 0))
        is_rate_limit_403 = self._is_rate_limit_403(
            status_code, payload, getattr(response, "headers", {})
        )

        error_cls: type[GitHubClientError]
        if status_code == 401 or (status_code == 403 and not is_rate_limit_403):
            error_cls = GitHubAuthError
        elif status_code == 404:
            error_cls = GitHubNotFoundError
        elif status_code == 422:
            error_cls = GitHubValidationError
        elif status_code == 429 or is_rate_limit_403:
            error_cls = GitHubRateLimitError
        elif status_code >= 500:
            error_cls = GitHubServerError
        else:
            error_cls = GitHubApiError

        retryable = self._is_transient_status(status_code) or is_rate_limit_403
        return error_cls(
            f"GitHub API {status_code} for {method.upper()} {url}: {message}",
            status_code=status_code,
            method=method.upper(),
            url=url,
            response_body=payload if payload is not None else fallback_text,
            retryable=retryable,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_url}{path}"
        retries_done = 0

        while True:
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=self.headers,
                    json=payload,
                    params=params,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                if retries_done < self.max_retries:
                    retries_done += 1
                    backoff = self._resolve_backoff(retries_done)
                    self._log_retry(
                        method=method,
                        url=url,
                        attempt=retries_done,
                        backoff_seconds=backoff,
                        reason=exc.__class__.__name__,
                    )
                    if backoff > 0:
                        time.sleep(backoff)
                    continue
                raise GitHubTransportError(
                    f"GitHub transport error for {method.upper()} {url}: {exc}",
                    method=method.upper(),
                    url=url,
                ) from exc

            status_code = int(getattr(response, "status_code", 0))
            if self._is_success_status(status_code):
                if status_code == 204:
                    return {}
                payload_data = self._safe_json(response)
                if isinstance(payload_data, (dict, list)):
                    return payload_data
                raise GitHubApiError(
                    f"GitHub API {status_code} for {method.upper()} {url}: expected JSON object or array response.",
                    status_code=status_code,
                    method=method.upper(),
                    url=url,
                    response_body=getattr(response, "text", ""),
                )

            error = self._build_api_error(method, url, response)
            if error.retryable and retries_done < self.max_retries:
                retries_done += 1
                backoff = self._resolve_backoff(retries_done, response)
                self._log_retry(
                    method=method,
                    url=url,
                    attempt=retries_done,
                    backoff_seconds=backoff,
                    reason=error.__class__.__name__,
                    status_code=error.status_code,
                )
                if backoff > 0:
                    time.sleep(backoff)
                continue
            raise error

    # =========================================================================
    # Issue Operations with Pagination (HF-P6-001-ST01)
    # =========================================================================

    def get_issues(
        self,
        *,
        state: str = "open",
        labels: str | None = None,
        sort: str = "created",
        direction: str = "desc",
        page: int = 1,
        per_page: int = 30,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Get issues with pagination support.

        Args:
            state: Issue state (open, closed, all)
            labels: Comma-separated label names
            sort: Sort field (created, updated, comments)
            direction: Sort direction (asc, desc)
            page: Page number (1-indexed)
            per_page: Items per page (max 100)
            since: Only issues updated after this timestamp

        Returns:
            Dict with 'issues' list and pagination info
        """
        if per_page > 100:
            raise GitHubValidationError(
                "per_page cannot exceed 100",
                method="GET",
                url=f"{self.api_url}/issues",
            )

        params: dict[str, Any] = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "page": page,
            "per_page": per_page,
        }
        if labels:
            params["labels"] = labels
        if since:
            params["since"] = since

        result = self._request("GET", "/issues", params=params)

        # Make a second request to get pagination headers
        url = f"{self.api_url}/issues"
        response = self.session.request(
            method="GET",
            url=url,
            headers=self.headers,
            params=params,
            json=None,
            timeout=self.timeout_seconds,
        )
        page_info = self._extract_page_info(response)
        self._log_pagination("GET /issues", page_info)

        return {
            "issues": result if isinstance(result, list) else result.get("issues", []),
            "pagination": page_info,
        }

    def list_issues(
        self,
        *,
        state: str = "open",
        labels: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List issues (simple interface).

        Args:
            state: Issue state (open, closed, all)
            labels: Comma-separated label names
            page: Page number
            per_page: Items per page

        Returns:
            List of issues
        """
        result = self.get_issues(
            state=state,
            labels=labels,
            page=page,
            per_page=per_page,
        )
        return result.get("issues", [])

    def get_issue_comments(
        self,
        issue_number: int,
        *,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """Get comments for an issue.

        Args:
            issue_number: Issue number
            page: Page number
            per_page: Items per page (max 100)

        Returns:
            List of issue comments
        """
        if per_page > 100:
            raise GitHubValidationError(
                "per_page cannot exceed 100",
                method="GET",
                url=f"{self.api_url}/issues/{issue_number}/comments",
            )
        result = self._request(
            "GET",
            f"/issues/{issue_number}/comments",
            params={"page": page, "per_page": per_page},
        )
        return result if isinstance(result, list) else []

    # =========================================================================
    # Commit Operations with Pagination (HF-P6-001-ST03)
    # =========================================================================

    def get_commits(
        self,
        *,
        sha: str | None = None,
        path: str | None = None,
        author: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """Get commits with pagination support.

        Args:
            sha: SHA or branch name
            path: File path to filter commits
            author: Commit author
            since: Start date
            until: End date
            page: Page number (1-indexed)
            per_page: Items per page (max 100)

        Returns:
            Dict with 'commits' list and pagination info
        """
        if per_page > 100:
            raise GitHubValidationError(
                "per_page cannot exceed 100",
                method="GET",
                url=f"{self.api_url}/commits",
            )

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        if author:
            params["author"] = author
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        result = self._request("GET", "/commits", params=params)

        # Get pagination headers
        url = f"{self.api_url}/commits"
        response = self.session.request(
            method="GET",
            url=url,
            headers=self.headers,
            params=params,
            json=None,
            timeout=self.timeout_seconds,
        )
        page_info = self._extract_page_info(response)
        self._log_pagination("GET /commits", page_info)

        return {
            "commits": result if isinstance(result, list) else result.get("commits", []),
            "pagination": page_info,
        }

    def list_commits(
        self,
        *,
        sha: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List commits (simple interface).

        Args:
            sha: SHA or branch name
            page: Page number
            per_page: Items per page

        Returns:
            List of commits
        """
        result = self.get_commits(
            sha=sha,
            page=page,
            per_page=per_page,
        )
        return result.get("commits", [])

    # =========================================================================
    # Pull Request Operations with Pagination (HF-P6-001-ST02)
    # =========================================================================

    def list_pull_requests_paginated(
        self,
        *,
        state: str = "open",
        head: str | None = None,
        base: str | None = None,
        sort: str = "created",
        direction: str = "desc",
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List pull requests with pagination support.

        Args:
            state: PR state (open, closed, all)
            head: Filter by head branch
            base: Filter by base branch
            sort: Sort field (created, updated, popularity, long-running)
            direction: Sort direction (asc, desc)
            page: Page number (1-indexed)
            per_page: Items per page (max 100)

        Returns:
            Dict with 'pulls' list and pagination info
        """
        if per_page > 100:
            raise GitHubValidationError(
                "per_page cannot exceed 100",
                method="GET",
                url=f"{self.api_url}/pulls",
            )

        params: dict[str, Any] = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "page": page,
            "per_page": per_page,
        }
        if head:
            params["head"] = head
        if base:
            params["base"] = base

        result = self._request("GET", "/pulls", params=params)

        # Get pagination headers
        url = f"{self.api_url}/pulls"
        response = self.session.request(
            method="GET",
            url=url,
            headers=self.headers,
            params=params,
            json=None,
            timeout=self.timeout_seconds,
        )
        page_info = self._extract_page_info(response)
        self._log_pagination("GET /pulls", page_info)

        return {
            "pulls": result if isinstance(result, list) else result.get("pulls", []),
            "pagination": page_info,
        }

    # =========================================================================
    # Auto-Pagination Support (HF-P6-001-ST04)
    # =========================================================================

    def get_all_issues(
        self,
        *,
        state: str = "open",
        labels: str | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Get all issues with automatic pagination.

        Args:
            state: Issue state
            labels: Filter by labels
            max_pages: Maximum pages to fetch

        Returns:
            List of all issues
        """
        page = 1
        all_issues: list[dict[str, Any]] = []

        while len(all_issues) < max_pages * 100:
            result = self.get_issues(
                state=state,
                labels=labels,
                page=page,
                per_page=100,
            )
            issues = result.get("issues", [])
            if not issues:
                break
            all_issues.extend(issues)

            if not result.get("pagination", {}).get("has_next"):
                break
            page += 1

            if page > max_pages:
                break

        return all_issues

    def get_all_commits(
        self,
        *,
        sha: str | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Get all commits with automatic pagination.

        Args:
            sha: SHA or branch name
            max_pages: Maximum pages to fetch

        Returns:
            List of all commits
        """
        page = 1
        all_commits: list[dict[str, Any]] = []

        while len(all_commits) < max_pages * 100:
            result = self.get_commits(
                sha=sha,
                page=page,
                per_page=100,
            )
            commits = result.get("commits", [])
            if not commits:
                break
            all_commits.extend(commits)

            if not result.get("pagination", {}).get("has_next"):
                break
            page += 1

            if page > max_pages:
                break

        return all_commits

    def get_all_pull_requests(
        self,
        *,
        state: str = "open",
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Get all pull requests with automatic pagination.

        Args:
            state: PR state
            max_pages: Maximum pages to fetch

        Returns:
            List of all pull requests
        """
        page = 1
        all_prs: list[dict[str, Any]] = []

        while len(all_prs) < max_pages * 100:
            result = self.list_pull_requests_paginated(
                state=state,
                page=page,
                per_page=100,
            )
            prs = result.get("pulls", [])
            if not prs:
                break
            all_prs.extend(prs)

            if not result.get("pagination", {}).get("has_next"):
                break
            page += 1

            if page > max_pages:
                break

        return all_prs

    def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        payload = {"title": title, "body": body, "labels": labels or []}
        return self._request("POST", "/issues", payload=payload)

    def comment_issue(self, issue_number: int, comment: str) -> dict[str, Any]:
        payload = {"body": comment}
        return self._request("POST", f"/issues/{issue_number}/comments", payload=payload)

    def update_issue_comment(self, comment_id: int, comment: str) -> dict[str, Any]:
        payload = {"body": comment}
        return self._request("PATCH", f"/issues/comments/{comment_id}", payload=payload)

    def update_issue_labels(self, issue_number: int, labels: list[str]) -> dict[str, Any]:
        payload = {"labels": labels}
        return self._request("PATCH", f"/issues/{issue_number}", payload=payload)

    def update_issue(self, issue_number: int, fields: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/issues/{issue_number}", payload=fields)

    def close_issue(self, issue_number: int) -> dict[str, Any]:
        return self.update_issue(issue_number, {"state": "closed"})

    def create_branch(self, branch_name: str, from_branch: str = "main") -> dict[str, Any]:
        payload = {
            "ref": f"refs/heads/{branch_name}",
            "sha": self.get_branch_sha(from_branch),
        }
        return self._request("POST", "/git/refs", payload=payload)

    def get_branch_sha(self, branch: str) -> str:
        result = self._request("GET", f"/git/refs/heads/{branch}")
        try:
            return str(result["object"]["sha"])
        except KeyError as exc:
            raise GitHubApiError(
                f"GitHub API response for branch '{branch}' does not contain object.sha.",
                method="GET",
                url=f"{self.api_url}/git/refs/heads/{branch}",
                response_body=result,
            ) from exc

    def create_pr(
        self,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
    ) -> dict[str, Any]:
        payload = {"title": title, "head": head, "base": base, "body": body}
        return self._request("POST", "/pulls", payload=payload)

    def get_workflow_runs(self, workflow_id: str, branch: str = "main") -> dict[str, Any]:
        return self._request(
            "GET",
            f"/actions/workflows/{workflow_id}/runs",
            params={"branch": branch},
        )

    # =========================================================================
    # Branch Management (HF-P5-003)
    # =========================================================================

    def delete_branch(self, branch_name: str) -> dict[str, Any]:
        """Delete a branch by name."""
        # First get the ref
        ref_result = self._request("GET", f"/git/refs/heads/{branch_name}")
        sha = ref_result.get("object", {}).get("sha")
        if not sha:
            raise GitHubApiError(
                f"Could not find SHA for branch {branch_name}",
                method="GET",
                url=f"{self.api_url}/git/refs/heads/{branch_name}",
            )

        # Delete using the SHA
        return self._request("DELETE", f"/git/refs/heads/{branch_name}")

    def get_branch(self, branch_name: str) -> dict[str, Any]:
        """Get branch information."""
        return self._request("GET", f"/branches/{branch_name}")

    def list_branches(self) -> list[dict[str, Any]]:
        """List all branches in the repository."""
        result = self._request("GET", "/branches")
        if isinstance(result, list):
            return result
        return result.get("branches", [])

    # =========================================================================
    # File Operations (HF-P5-003)
    # =========================================================================

    def get_file_content(self, path: str, ref: str | None = None) -> dict[str, Any]:
        """Get file content from repository."""
        params = {}
        if ref:
            params["ref"] = ref

        try:
            return self._request("GET", f"/contents/{path}", params=params)
        except GitHubNotFoundError:
            # File doesn't exist
            raise GitHubNotFoundError(
                f"File not found: {path}",
                method="GET",
                url=f"{self.api_url}/contents/{path}",
            ) from None

    def get_commit(self, sha: str) -> dict[str, Any]:
        """Get commit information."""
        return self._request("GET", f"/commits/{sha}")

    def create_or_update_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in the repository.

        Args:
            path: File path in the repository
            content: File content (will be base64 encoded)
            message: Commit message
            branch: Branch to commit to (optional)
            sha: SHA of file being updated (required for updates)
        """
        import base64

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        }
        if branch:
            payload["branch"] = branch
        if sha:
            payload["sha"] = sha

        return self._request("PUT", f"/contents/{path}", payload=payload)

    def delete_file(
        self,
        path: str,
        message: str,
        sha: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Delete a file from the repository.

        Args:
            path: File path in the repository
            message: Commit message
            sha: SHA of file to delete
            branch: Branch to delete from (optional)
        """
        params = {"message": message, "sha": sha}
        if branch:
            params["branch"] = branch

        return self._request("DELETE", f"/contents/{path}", payload=params)

    # =========================================================================
    # Pull Request Operations (HF-P5-003, HF-P5-006, HF-P5-007)
    # =========================================================================

    def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        """Get pull request information."""
        return self._request("GET", f"/pulls/{pr_number}")

    def get_pull_request_reviews(self, pr_number: int) -> list[dict[str, Any]]:
        """Get reviews for a pull request."""
        result = self._request("GET", f"/pulls/{pr_number}/reviews")
        if isinstance(result, list):
            return result
        return []

    def list_pull_requests(
        self,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """List pull requests with pagination.

        Args:
            state: PR state (open, closed, all)
            page: Page number
            per_page: Items per page

        Returns:
            List of pull requests
        """
        result = self.list_pull_requests_paginated(
            state=state,
            page=page,
            per_page=per_page,
        )
        return result.get("pulls", [])

    def get_pull_request_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Get list of files changed in a pull request."""
        result = self._request("GET", f"/pulls/{pr_number}/files")
        if isinstance(result, list):
            return result
        return []

    def get_pull_request_diff(self, pr_number: int) -> str:
        """Get the diff of a pull request."""
        # Use raw Accept header for diff
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.v3.diff"
        url = f"{self.api_url}/pulls/{pr_number}"

        response = self.session.get(
            url,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 200:
            return response.text
        raise self._build_api_error("GET", f"/pulls/{pr_number}", response)

    def create_review_comment(
        self,
        pr_number: int,
        body: str,
        commit_id: str,
        path: str,
        line: int,
    ) -> dict[str, Any]:
        """Create a review comment on a pull request."""
        payload = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
        }
        return self._request("POST", f"/pulls/{pr_number}/comments", payload=payload)

    def submit_review(
        self,
        pr_number: int,
        event: str,
        body: str = "",
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Submit a review on a pull request.

        Args:
            pr_number: Pull request number
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            body: Review body message
            comments: List of review comments
        """
        payload: dict[str, Any] = {"event": event, "body": body}
        if comments:
            payload["comments"] = comments
        return self._request("POST", f"/pulls/{pr_number}/reviews", payload=payload)

    # =========================================================================
    # Merge Operations (HF-P5-007)
    # =========================================================================

    def get_mergeable_status(self, pr_number: int) -> dict[str, Any]:
        """Get mergeable status of a pull request."""
        pr = self.get_pull_request(pr_number)
        return {
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "draft": pr.get("draft", False),
        }

    def get_combined_status(self, ref: str) -> dict[str, Any]:
        """Get combined status for a ref (commit/branch)."""
        return self._request("GET", f"/commits/{ref}/status")

    def get_protection_rules(self, branch: str) -> dict[str, Any]:
        """Get branch protection rules."""
        try:
            return self._request("GET", f"/branches/{branch}/protection")
        except GitHubNotFoundError:
            # No protection rules
            return {}

    def merge_pull_request(
        self,
        pr_number: int,
        merge_method: str = "merge",
        title: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request.

        Args:
            pr_number: Pull request number
            merge_method: merge, squash, or rebase
            title: Title for squash merge
            message: Message for squash/merge
        """
        # First check if PR is mergeable
        pr = self.get_pull_request(pr_number)
        if not pr.get("mergeable", True):
            raise GitHubApiError(
                f"Pull request #{pr_number} is not mergeable",
                method="MERGE",
                url=f"{self.api_url}/pulls/{pr_number}/merge",
                response_body=pr,
            )

        payload = {"merge_method": merge_method}
        if title:
            payload["title"] = title
        if message:
            payload["message"] = message

        try:
            return self._request("PUT", f"/pulls/{pr_number}/merge", payload=payload)
        except GitHubNotFoundError:
            # Already merged
            raise GitHubNotFoundError(
                f"Pull request #{pr_number} not found or already merged",
                method="PUT",
                url=f"{self.api_url}/pulls/{pr_number}/merge",
            ) from None

    # =========================================================================
    # Workflow Dispatch (HF-P5-005)
    # =========================================================================

    def dispatch_workflow(
        self,
        workflow_id: str,
        ref: str = "main",
        inputs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a workflow run."""
        payload = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        return self._request(
            "POST", f"/actions/workflows/{workflow_id}/dispatches", payload=payload
        )

    def get_workflow_run(
        self,
        run_id: int,
    ) -> dict[str, Any]:
        """Get a specific workflow run."""
        return self._request("GET", f"/actions/runs/{run_id}")

    def get_workflow_run_jobs(self, run_id: int) -> dict[str, Any]:
        """Get jobs for a workflow run."""
        return self._request("GET", f"/actions/runs/{run_id}/jobs")

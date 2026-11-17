"""Small GitHub REST API client for pull-request review operations."""

import base64
from typing import Any
from urllib.parse import quote

import requests

from app.config import GITHUB_API_BASE, get_github_token


class GitHubClient:
    """Fetch pull-request content and commit reviewed changes to its branch."""

    def __init__(
        self,
        token: str | None = None,
        session: requests.Session | None = None,
        api_base: str = GITHUB_API_BASE,
    ) -> None:
        self.token = token
        self.session = session or requests.Session()
        self.api_base = api_base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self.token or get_github_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> requests.Response:
        response = self.session.request(
            method,
            f"{self.api_base}{path}",
            headers=self._headers(),
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        """Return the GitHub pull-request record."""
        encoded_repo = quote(repo_name, safe="/")
        response = self._request("GET", f"/repos/{encoded_repo}/pulls/{pr_number}")
        return response.json()

    def get_pull_request_files(
        self, repo_name: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """Return all changed files, following GitHub pagination links."""
        encoded_repo = quote(repo_name, safe="/")
        url = f"{self.api_base}/repos/{encoded_repo}/pulls/{pr_number}/files"
        files: list[dict[str, Any]] = []
        params: dict[str, Any] | None = {"per_page": 100}

        while url:
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list):
                raise ValueError(
                    "GitHub returned an invalid pull-request files response."
                )
            files.extend(page)
            url = response.links.get("next", {}).get("url", "")
            params = None

        return files

    def get_file_content(self, repo_name: str, path: str, ref: str) -> str:
        """Read and decode one file at the requested branch or commit."""
        encoded_repo = quote(repo_name, safe="/")
        encoded_path = quote(path, safe="/")
        response = self._request(
            "GET",
            f"/repos/{encoded_repo}/contents/{encoded_path}",
            params={"ref": ref},
        )
        file_record = response.json()
        if file_record.get("type") != "file" or file_record.get("encoding") != "base64":
            raise ValueError(f"GitHub did not return base64 file content for {path!r}.")
        content = "".join(file_record.get("content", "").split())
        try:
            return base64.b64decode(content, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"Could not decode UTF-8 source file {path!r}.") from exc

    def commit_changes(
        self,
        repo_name: str,
        branch_name: str,
        changes: dict[str, str],
        message: str,
    ) -> str:
        """Create one Git commit containing all changed files and update the branch."""
        if not changes:
            raise ValueError("Cannot create a GitHub commit without changed files.")

        encoded_repo = quote(repo_name, safe="/")
        encoded_branch = quote(branch_name, safe="")
        ref = self._request(
            "GET", f"/repos/{encoded_repo}/git/ref/heads/{encoded_branch}"
        ).json()
        parent_sha = ref["object"]["sha"]
        parent = self._request(
            "GET", f"/repos/{encoded_repo}/git/commits/{parent_sha}"
        ).json()
        tree_entries = [
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "content": content,
            }
            for path, content in changes.items()
        ]
        tree = self._request(
            "POST",
            f"/repos/{encoded_repo}/git/trees",
            json={"base_tree": parent["tree"]["sha"], "tree": tree_entries},
        ).json()
        commit = self._request(
            "POST",
            f"/repos/{encoded_repo}/git/commits",
            json={
                "message": message,
                "tree": tree["sha"],
                "parents": [parent_sha],
            },
        ).json()
        self._request(
            "PATCH",
            f"/repos/{encoded_repo}/git/refs/heads/{encoded_branch}",
            json={"sha": commit["sha"]},
        )
        return commit["sha"]

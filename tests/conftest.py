"""Reusable offline dependencies for review workflow tests."""

from typing import Any


class FakeGitHubClient:
    """In-memory GitHub client for graph and API tests."""

    def __init__(self) -> None:
        self.commits: list[dict[str, Any]] = []

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        return {
            "number": pr_number,
            "head": {
                "ref": "feature/review",
                "sha": "abc123",
                "repo": {"full_name": repo_name},
            },
        }

    def get_pull_request_files(
        self, repo_name: str, pr_number: int
    ) -> list[dict[str, str]]:
        return [{"filename": "src/example.py", "status": "modified"}]

    def get_file_content(self, repo_name: str, path: str, ref: str) -> str:
        return "value=1\n"

    def commit_changes(
        self,
        repo_name: str,
        branch_name: str,
        changes: dict[str, str],
        message: str,
    ) -> str:
        self.commits.append(
            {
                "repo_name": repo_name,
                "branch_name": branch_name,
                "changes": changes,
                "message": message,
            }
        )
        return "def456"


class FakeLinter:
    """LangChain-tool-shaped linter stub."""

    def invoke(self, arguments: dict[str, str]) -> str:
        return "No lint errors."


class FakeRefactor:
    """Deterministic refactor function that records reviewer feedback."""

    def __init__(self) -> None:
        self.feedback_seen: list[str] = []

    def __call__(self, code: str, lint_errors: list[str], feedback: str) -> str:
        self.feedback_seen.append(feedback)
        return "value = 1\n"

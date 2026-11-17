"""LangGraph node implementations for the pull-request review workflow."""

from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from app.github_client import GitHubClient
from app.refactor import generate_refactor
from app.state import ReviewState
from app.tools import run_linter_tool


def fetch_pr_node(
    state: ReviewState,
    *,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Fetch changed Python sources and branch metadata from GitHub."""
    client = github_client or GitHubClient()
    pr_repository = state.get("pr_repo_name") or state.get("repo_name")
    pr_number = state.get("pr_number")
    if not pr_repository or pr_number is None:
        raise ValueError("The review state must include a repository and PR number.")

    pull_request = client.get_pull_request(pr_repository, pr_number)
    head = pull_request.get("head", {})
    head_repository = (head.get("repo") or {}).get("full_name") or state.get(
        "repo_name", pr_repository
    )
    branch_name = head.get("ref") or state.get("branch_name")
    head_sha = head.get("sha") or branch_name
    if not head_repository or not branch_name or not head_sha:
        raise ValueError(
            "GitHub pull-request data is missing head repository metadata."
        )

    files = client.get_pull_request_files(pr_repository, pr_number)
    code_contents: dict[str, str] = {}
    for changed_file in files:
        path = changed_file.get("filename", "")
        safe_path = PurePosixPath(path)
        if (
            not path.endswith(".py")
            or changed_file.get("status") == "removed"
            or safe_path.is_absolute()
            or ".." in safe_path.parts
        ):
            continue
        code_contents[path] = client.get_file_content(head_repository, path, head_sha)

    return {
        "repo_name": head_repository,
        "pr_repo_name": pr_repository,
        "branch_name": branch_name,
        "head_sha": head_sha,
        "code_contents": code_contents,
        "is_approved": None,
        "reviewer_feedback": None,
        "status": "fetched",
        "history": [f"Fetched {len(code_contents)} changed Python file(s)."],
    }


def lint_code_node(
    state: ReviewState,
    *,
    linter: Any = run_linter_tool,
) -> dict[str, Any]:
    """Lint each changed Python file using the isolated linter tool."""
    code_contents = state.get("code_contents", {})
    if not code_contents:
        raise ValueError("The pull request contains no changed Python files to review.")

    lint_errors: list[str] = []
    for path, code in code_contents.items():
        if hasattr(linter, "invoke"):
            result = linter.invoke({"code_string": code})
        else:
            result = linter(code)
        if not isinstance(result, str):
            raise TypeError("The linter tool must return a string.")
        if result != "No lint errors." and not result.startswith("No lint errors.\n"):
            lint_errors.append(f"{path}:\n{result}")

    return {
        "lint_errors": lint_errors,
        "status": "linted",
        "history": [
            f"Linted {len(code_contents)} file(s); "
            f"found {len(lint_errors)} issue set(s)."
        ],
    }


def propose_refactor_node(
    state: ReviewState,
    *,
    refactor_fn: Callable[[str, list[str], str], str] = generate_refactor,
) -> dict[str, Any]:
    """Ask the configured model for corrected code for each changed file."""
    lint_errors = state.get("lint_errors", [])
    feedback = state.get("reviewer_feedback") or ""
    refactored_code: dict[str, str] = {}
    for path, code in state.get("code_contents", {}).items():
        file_errors = [error for error in lint_errors if error.startswith(f"{path}:\n")]
        result = refactor_fn(code, file_errors, feedback)
        if not isinstance(result, str) or not result.strip():
            raise ValueError(f"The refactor model returned empty code for {path!r}.")
        refactored_code[path] = result.strip()

    return {
        "refactored_code": refactored_code,
        "is_approved": None,
        "status": "awaiting_approval",
        "history": [
            "Generated refactors" + (" using reviewer feedback." if feedback else ".")
        ],
    }


def apply_changes_node(
    state: ReviewState,
    *,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Commit approved refactored source files to the PR head branch."""
    if state.get("is_approved") is not True:
        raise ValueError("Refactored changes cannot be applied before approval.")
    repo_name = state.get("repo_name")
    branch_name = state.get("branch_name")
    changes = state.get("refactored_code", {})
    if not repo_name or not branch_name or not changes:
        raise ValueError("The review state is missing the branch or refactored files.")

    client = github_client or GitHubClient()
    commit_sha = client.commit_changes(
        repo_name,
        branch_name,
        changes,
        "Apply reviewed Python refactors",
    )
    return {
        "status": "completed",
        "history": [f"Committed approved refactors as {commit_sha}."],
    }

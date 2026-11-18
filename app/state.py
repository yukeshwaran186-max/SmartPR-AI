"""Typed state carried between review graph nodes."""

import operator
from typing import Annotated, NotRequired, TypedDict


class ReviewState(TypedDict):
    """Data persisted for one pull-request review thread."""

    pr_url: str
    code_contents: dict[str, str]
    lint_errors: list[str]
    refactored_code: dict[str, str]
    is_approved: bool | None
    reviewer_feedback: str | None
    history: Annotated[list[str], operator.add]
    repo_name: NotRequired[str]
    pr_repo_name: NotRequired[str]
    pr_number: NotRequired[int]
    branch_name: NotRequired[str]
    head_sha: NotRequired[str]
    status: NotRequired[str]

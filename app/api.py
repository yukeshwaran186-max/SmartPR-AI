"""FastAPI routes for GitHub pull-request review threads."""

import logging
import re
from typing import Any
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.graph import build_review_graph
from app.state import ReviewState

logger = logging.getLogger(__name__)


class RepositoryPayload(BaseModel):
    """Repository fields used from a GitHub webhook."""

    full_name: str = Field(min_length=3)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError(
                "Repository full_name must have the form owner/repository."
            )
        return value


class PullRequestHeadPayload(BaseModel):
    """Pull-request source branch information."""

    ref: str = Field(min_length=1)
    repo: RepositoryPayload | None = None


class PullRequestPayload(BaseModel):
    """Pull-request fields needed to identify the review target."""

    number: int = Field(gt=0)
    html_url: str = Field(min_length=1)
    head: PullRequestHeadPayload


class GitHubWebhookPayload(BaseModel):
    """Subset of GitHub's pull_request webhook event."""

    action: str | None = None
    repository: RepositoryPayload
    pull_request: PullRequestPayload


class ApprovalRequest(BaseModel):
    """Approval or rejection decision for a proposed refactor."""

    approved: bool
    feedback: str | None = None


class ReviewResponse(BaseModel):
    """Status returned for a review thread."""

    thread_id: str
    status: str
    detail: str
    refactored_code: dict[str, str] | None = None
    lint_errors: list[str] | None = None


def create_app(review_graph: Any | None = None) -> FastAPI:
    """Create the API with review-thread state stored in the graph checkpointer."""
    graph = review_graph or build_review_graph()
    app = FastAPI(
        title="Autonomous Code Review & Refactoring Agent",
        version="1.0.0",
        description="Review changed Python files and apply only approved refactors.",
    )
    @app.post(
        "/api/webhooks/github",
        response_model=ReviewResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_review(payload: GitHubWebhookPayload) -> ReviewResponse:
        """Start a review and stop at its human-approval interrupt."""
        thread_id = str(uuid4())
        pr_repository = payload.repository.full_name
        head_repository = (
            payload.pull_request.head.repo.full_name
            if payload.pull_request.head.repo
            else pr_repository
        )
        thread_config = {"configurable": {"thread_id": thread_id}}
        initial_state: ReviewState = {
            "pr_url": payload.pull_request.html_url,
            "repo_name": head_repository,
            "pr_repo_name": pr_repository,
            "pr_number": payload.pull_request.number,
            "branch_name": payload.pull_request.head.ref,
            "code_contents": {},
            "lint_errors": [],
            "refactored_code": {},
            "is_approved": None,
            "reviewer_feedback": None,
            "history": [],
            "status": "starting",
        }

        try:
            graph.invoke(initial_state, config=thread_config)
            snapshot = graph.get_state(thread_config)
            if "apply_changes_node" not in snapshot.next:
                raise RuntimeError("Review graph did not pause at the approval gate.")
        except requests.RequestException:
            logger.exception(
                "GitHub request failed while starting review",
                extra={"thread_id": thread_id},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub request failed while starting the review.",
            ) from None
        except RuntimeError as exc:
            logger.exception(
                "Review could not be started",
                extra={"thread_id": thread_id},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from None
        except ValueError as exc:
            logger.exception(
                "Pull-request payload could not be reviewed",
                extra={"thread_id": thread_id},
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from None

        logger.info(
            "Review paused for approval",
            extra={"thread_id": thread_id, "status": "awaiting_approval"},
        )
        return ReviewResponse(
            thread_id=thread_id,
            status="awaiting_approval",
            detail="Review is ready for human approval.",
            refactored_code=snapshot.values.get("refactored_code", {}),
            lint_errors=snapshot.values.get("lint_errors", []),
        )

    @app.post(
        "/api/reviews/{thread_id}/approve",
        response_model=ReviewResponse,
    )
    def decide_review(thread_id: str, decision: ApprovalRequest) -> ReviewResponse:
        """Resume an approved review or regenerate after reviewer feedback."""
        thread_config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(thread_config)
        if not snapshot.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown review thread.",
            )

        if "apply_changes_node" not in snapshot.next:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This review is not waiting for an approval decision.",
            )

        if decision.approved:
            graph.update_state(thread_config, {"is_approved": True})
            try:
                graph.invoke(None, config=thread_config)
                final_state = graph.get_state(thread_config)
            except requests.RequestException:
                logger.exception(
                    "GitHub request failed while applying approved review",
                    extra={"thread_id": thread_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="GitHub request failed while applying the review.",
                ) from None
            except RuntimeError as exc:
                logger.exception(
                    "Approved review could not be applied",
                    extra={"thread_id": thread_id},
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from None
            logger.info(
                "Review completed",
                extra={"thread_id": thread_id, "status": "completed"},
            )
            return ReviewResponse(
                thread_id=thread_id,
                status=final_state.values.get("status", "completed"),
                detail="Approved changes were committed to the pull-request branch.",
                refactored_code=final_state.values.get("refactored_code", {}),
                lint_errors=final_state.values.get("lint_errors", []),
            )

        graph.update_state(
            thread_config,
            {
                "is_approved": False,
                "reviewer_feedback": decision.feedback,
            },
            as_node="fetch_pr_node",
        )
        try:
            graph.invoke(None, config=thread_config)
            updated_state = graph.get_state(thread_config)
        except requests.RequestException:
            logger.exception(
                "GitHub request failed while restarting rejected review",
                extra={"thread_id": thread_id},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub request failed while restarting the review.",
            ) from None
        except RuntimeError as exc:
            logger.exception(
                "Rejected review could not be regenerated",
                extra={"thread_id": thread_id},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from None

        logger.info(
            "Rejected refactor regenerated and paused for approval",
            extra={"thread_id": thread_id, "status": "awaiting_approval"},
        )
        return ReviewResponse(
            thread_id=thread_id,
            status=updated_state.values.get("status", "awaiting_approval"),
            detail="Feedback was recorded and a revised proposal is ready.",
            refactored_code=updated_state.values.get("refactored_code", {}),
            lint_errors=updated_state.values.get("lint_errors", []),
        )

    return app

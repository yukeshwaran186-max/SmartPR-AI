"""Offline tests for GitHub webhook and human approval endpoints."""

import sqlite3

from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

from app.api import create_app
from app.graph import build_review_graph
from conftest import FakeGitHubClient, FakeLinter, FakeRefactor


def _client(refactor: FakeRefactor | None = None):
    github = FakeGitHubClient()
    refactor = refactor or FakeRefactor()
    graph = build_review_graph(
        checkpointer=MemorySaver(),
        github_client=github,
        refactor_fn=refactor,
        linter=FakeLinter(),
    )
    return TestClient(create_app(graph)), github, refactor


def _webhook_payload() -> dict[str, object]:
    return {
        "action": "opened",
        "repository": {
            "full_name": "acme/project",
            "html_url": "https://github.com/acme/project",
        },
        "pull_request": {
            "number": 12,
            "html_url": "https://github.com/acme/project/pull/12",
            "head": {
                "ref": "feature/review",
                "repo": {"full_name": "acme/project"},
            },
        },
    }


def test_webhook_starts_review_and_reject_reruns_refactor() -> None:
    refactor = FakeRefactor()
    client, github, _ = _client(refactor)

    response = client.post("/api/webhooks/github", json=_webhook_payload())

    assert response.status_code == 202
    thread_id = response.json()["thread_id"]
    assert response.json()["status"] == "awaiting_approval"
    assert github.commits == []

    rejection = client.post(
        f"/api/reviews/{thread_id}/approve",
        json={"approved": False, "feedback": "Do not rename this value."},
    )

    assert rejection.status_code == 200
    assert rejection.json()["status"] == "awaiting_approval"
    assert refactor.feedback_seen == ["", "Do not rename this value."]
    assert github.commits == []


def test_approval_endpoint_commits_changes() -> None:
    client, github, _ = _client()
    started = client.post("/api/webhooks/github", json=_webhook_payload())
    thread_id = started.json()["thread_id"]

    response = client.post(
        f"/api/reviews/{thread_id}/approve",
        json={"approved": True, "feedback": None},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert len(github.commits) == 1
    duplicate = client.post(
        f"/api/reviews/{thread_id}/approve",
        json={"approved": True},
    )
    assert duplicate.status_code == 409


def test_approval_resumes_thread_after_app_restart(tmp_path) -> None:
    checkpoint_path = tmp_path / "reviews.sqlite"
    first_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
    second_connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
    try:
        first_saver = SqliteSaver(first_connection)
        first_saver.setup()
        first_github = FakeGitHubClient()
        first_graph = build_review_graph(
            checkpointer=first_saver,
            github_client=first_github,
            refactor_fn=FakeRefactor(),
            linter=FakeLinter(),
        )
        first_client = TestClient(create_app(first_graph))
        started = first_client.post(
            "/api/webhooks/github", json=_webhook_payload()
        )
        assert started.status_code == 202
        thread_id = started.json()["thread_id"]
        assert first_github.commits == []

        second_saver = SqliteSaver(second_connection)
        second_saver.setup()
        second_github = FakeGitHubClient()
        second_graph = build_review_graph(
            checkpointer=second_saver,
            github_client=second_github,
            refactor_fn=FakeRefactor(),
            linter=FakeLinter(),
        )
        second_client = TestClient(create_app(second_graph))
        approved = second_client.post(
            f"/api/reviews/{thread_id}/approve",
            json={"approved": True},
        )

        assert approved.status_code == 200
        assert approved.json()["status"] == "completed"
        assert len(second_github.commits) == 1
    finally:
        first_connection.close()
        second_connection.close()


def test_api_returns_404_for_unknown_thread_and_422_for_invalid_payload() -> None:
    client, _, _ = _client()

    assert (
        client.post(
            "/api/reviews/not-a-thread/approve",
            json={"approved": True},
        ).status_code
        == 404
    )
    assert client.post("/api/webhooks/github", json={}).status_code == 422

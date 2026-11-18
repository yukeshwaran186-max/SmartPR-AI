"""Tests for approval interrupts and rejection feedback routing."""

from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_review_graph
from conftest import FakeGitHubClient, FakeLinter, FakeRefactor


def _initial_state() -> dict[str, object]:
    return {
        "pr_url": "https://github.com/acme/project/pull/12",
        "repo_name": "acme/project",
        "pr_repo_name": "acme/project",
        "pr_number": 12,
        "branch_name": "feature/review",
        "code_contents": {},
        "lint_errors": [],
        "refactored_code": {},
        "is_approved": None,
        "reviewer_feedback": None,
        "history": [],
    }


def test_graph_pauses_before_apply_changes_node() -> None:
    github = FakeGitHubClient()
    graph = build_review_graph(
        checkpointer=MemorySaver(),
        github_client=github,
        refactor_fn=FakeRefactor(),
        linter=FakeLinter(),
    )
    config = {"configurable": {"thread_id": "pause-test"}}

    graph.invoke(_initial_state(), config=config)

    snapshot = graph.get_state(config)
    assert snapshot.next == ("apply_changes_node",)
    assert snapshot.values["status"] == "awaiting_approval"
    assert github.commits == []


def test_rejection_routes_back_to_refactor_and_preserves_full_history() -> None:
    refactor = FakeRefactor()
    github = FakeGitHubClient()
    graph = build_review_graph(
        checkpointer=MemorySaver(),
        github_client=github,
        refactor_fn=refactor,
        linter=FakeLinter(),
    )
    config = {"configurable": {"thread_id": "reject-test"}}
    graph.invoke(_initial_state(), config=config)

    graph.update_state(
        config,
        {"is_approved": False, "reviewer_feedback": "Keep the public API unchanged."},
        as_node="fetch_pr_node",
    )
    graph.invoke(None, config=config)

    snapshot = graph.get_state(config)
    assert snapshot.next == ("apply_changes_node",)
    assert snapshot.values["reviewer_feedback"] == "Keep the public API unchanged."
    assert snapshot.values["is_approved"] is None
    assert refactor.feedback_seen == ["", "Keep the public API unchanged."]

    graph.update_state(config, {"is_approved": True})
    graph.invoke(None, config=config)

    final_state = graph.get_state(config).values
    assert final_state["history"] == [
        "Fetched 1 changed Python file(s).",
        "Linted 1 file(s); found 0 issue set(s).",
        "Generated refactors.",
        "Linted 1 file(s); found 0 issue set(s).",
        "Generated refactors using reviewer feedback.",
        "Committed approved refactors as def456.",
    ]
    assert len(github.commits) == 1


def test_approved_changes_are_committed() -> None:
    github = FakeGitHubClient()
    graph = build_review_graph(
        checkpointer=MemorySaver(),
        github_client=github,
        refactor_fn=FakeRefactor(),
        linter=FakeLinter(),
    )
    config = {"configurable": {"thread_id": "approve-test"}}
    graph.invoke(_initial_state(), config=config)

    graph.update_state(config, {"is_approved": True})
    graph.invoke(None, config=config)

    assert graph.get_state(config).values["status"] == "completed"
    assert len(github.commits) == 1
    assert github.commits[0]["branch_name"] == "feature/review"

"""Build the persistent LangGraph pull-request review workflow."""

import logging
import sqlite3
from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.config import CHECKPOINT_DB
from app.github_client import GitHubClient
from app.nodes import (
    apply_changes_node,
    fetch_pr_node,
    lint_code_node,
    propose_refactor_node,
)
from app.refactor import generate_refactor
from app.state import ReviewState
from app.tools import run_linter_tool

logger = logging.getLogger(__name__)


def _create_persistent_checkpointer() -> Any:
    """Create a SQLite checkpointer, falling back to in-memory storage."""
    connection: sqlite3.Connection | None = None
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        connection = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
        saver = SqliteSaver(connection)
        saver.setup()
        return saver
    except (ImportError, OSError, sqlite3.Error):
        if connection is not None:
            connection.close()
        logger.exception("Could not initialize SQLite checkpoints; using MemorySaver.")
        return MemorySaver()


def build_review_graph(
    *,
    checkpointer: Any | None = None,
    github_client: GitHubClient | None = None,
    refactor_fn: Any = generate_refactor,
    linter: Any = run_linter_tool,
) -> Any:
    """Compile the review workflow with an interrupt before applying changes."""
    client = github_client or GitHubClient()
    workflow = StateGraph(ReviewState)
    workflow.add_node(
        "fetch_pr_node",
        partial(fetch_pr_node, github_client=client),
    )
    workflow.add_node("lint_code_node", partial(lint_code_node, linter=linter))
    workflow.add_node(
        "propose_refactor_node",
        partial(propose_refactor_node, refactor_fn=refactor_fn),
    )
    workflow.add_node(
        "apply_changes_node",
        partial(apply_changes_node, github_client=client),
    )
    workflow.add_edge(START, "fetch_pr_node")
    workflow.add_edge("fetch_pr_node", "lint_code_node")
    workflow.add_edge("lint_code_node", "propose_refactor_node")
    workflow.add_edge("propose_refactor_node", "apply_changes_node")
    workflow.add_edge("apply_changes_node", END)
    return workflow.compile(
        checkpointer=checkpointer or _create_persistent_checkpointer(),
        interrupt_before=["apply_changes_node"],
    )

"""Tests for isolated lint execution."""

import subprocess

import pytest

from app import tools
from app.tools import run_linter_tool


def test_linter_accepts_valid_python_code() -> None:
    result = run_linter_tool.invoke(
        {"code_string": "def add(a, b):\n    return a + b\n"}
    )

    assert result.startswith("No lint errors.")
    assert result.count("Exit code: 0") == 2


def test_linter_reports_python_syntax_errors() -> None:
    result = run_linter_tool.invoke({"code_string": "def broken(:\n    pass\n"})

    assert "syntax" in result.lower()
    assert "flake8" in result
    assert "black --check" in result


def test_linter_rejects_oversized_source() -> None:
    with pytest.raises(ValueError, match="linting limit"):
        run_linter_tool.invoke({"code_string": " " * 1_000_001})


def test_linter_timeout_reports_bounded_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(command: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            command,
            timeout=15,
            output="o" * 32,
            stderr="e" * 32,
        )

    monkeypatch.setattr(tools.subprocess, "run", timeout)
    monkeypatch.setattr(tools, "MAX_OUTPUT_CHARACTERS", 16)

    result = run_linter_tool.invoke({"code_string": "print('safe')\n"})

    assert "Timed out after 15 seconds." in result
    assert result.count("[output truncated]") == 4

"""Tests for isolated lint execution."""

import pytest

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

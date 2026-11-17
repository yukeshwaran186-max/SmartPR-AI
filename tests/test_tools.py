"""Tests for isolated lint execution."""

from app.tools import run_linter_tool


def test_linter_reports_python_syntax_errors() -> None:
    result = run_linter_tool.invoke({"code_string": "def broken(:\n    pass\n"})

    assert "syntax" in result.lower()
    assert "flake8" in result
    assert "black --check" in result

"""Isolated static analysis tools used by the review workflow."""

import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from app.config import LINTER_TIMEOUT_SECONDS


def _run_linter_command(command: list[str], cwd: Path) -> str:
    """Run one linter command and preserve its output, including timeouts."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=LINTER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else exc.stdout
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else exc.stderr
        )
        return (
            f"$ {' '.join(command)}\nTimed out after "
            f"{LINTER_TIMEOUT_SECONDS} seconds.\n"
            f"stdout:\n{stdout or ''}\nstderr:\n{stderr or ''}"
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required linter executable was not found: {command[0]}"
        ) from exc

    return (
        f"$ {' '.join(command)}\nExit code: {result.returncode}\n"
        f"stdout:\n{result.stdout.strip()}\nstderr:\n{result.stderr.strip()}"
    )


@tool
def run_linter_tool(code_string: str) -> str:
    """Run flake8 and black --check on Python code in an isolated temp folder."""
    with tempfile.TemporaryDirectory(prefix="smartpr-lint-") as temp_dir:
        directory = Path(temp_dir)
        source_file = directory / "review_target.py"
        source_file.write_text(code_string, encoding="utf-8")

        results = [
            _run_linter_command(
                ["flake8", "--max-line-length=88", str(source_file)], directory
            ),
            _run_linter_command(["black", "--check", str(source_file)], directory),
        ]

    if all("Exit code: 0" in result for result in results):
        return "No lint errors.\n" + "\n".join(results)
    return "\n".join(results)

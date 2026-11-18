"""Isolated static analysis tools used by the review workflow."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from app.config import LINTER_TIMEOUT_SECONDS

MAX_SOURCE_BYTES = 1_000_000
MAX_OUTPUT_CHARACTERS = 100_000


def _run_linter_command(command: list[str], cwd: Path) -> str:
    """Run one linter command and preserve its output, including timeouts."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            close_fds=True,
            env=_linter_environment(),
            shell=False,
            stdin=subprocess.DEVNULL,
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

    stdout = _limit_output(result.stdout)
    stderr = _limit_output(result.stderr)
    return (
        f"$ {' '.join(command)}\nExit code: {result.returncode}\n"
        f"stdout:\n{stdout.strip()}\nstderr:\n{stderr.strip()}"
    )


def _linter_environment() -> dict[str, str]:
    """Keep credentials and Python customization out of linter subprocesses."""
    environment = {
        "PATH": os.path.dirname(sys.executable),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if os.name == "nt":
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
            value = os.environ.get(key)
            if value:
                environment[key] = value
    return environment


def _limit_output(output: str) -> str:
    """Bound the linter output included in review state and API responses."""
    if len(output) <= MAX_OUTPUT_CHARACTERS:
        return output
    return output[:MAX_OUTPUT_CHARACTERS] + "\n[output truncated]"


@tool
def run_linter_tool(code_string: str) -> str:
    """Statically lint source in a bounded temp directory without executing it."""
    source_bytes = code_string.encode("utf-8")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ValueError(f"Source exceeds the {MAX_SOURCE_BYTES}-byte linting limit.")

    with tempfile.TemporaryDirectory(prefix="smartpr-lint-") as temp_dir:
        directory = Path(temp_dir)
        source_file = directory / "review_target.py"
        with source_file.open("x", encoding="utf-8") as source:
            source.write(code_string)

        results = [
            _run_linter_command(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "flake8",
                    "--max-line-length=88",
                    str(source_file),
                ],
                directory,
            ),
            _run_linter_command(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "black",
                    "--check",
                    str(source_file),
                ],
                directory,
            ),
        ]

    if all("Exit code: 0" in result for result in results):
        return "No lint errors.\n" + "\n".join(results)
    return "\n".join(results)

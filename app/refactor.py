"""OpenAI-backed Python refactor generation."""

from langchain_openai import ChatOpenAI

from app.config import OPENAI_MODEL, get_openai_api_key


def generate_refactor(
    code: str,
    lint_errors: list[str],
    feedback: str = "",
) -> str:
    """Generate corrected code while explicitly preserving behavior."""
    prompt = f"""You are an expert Python code reviewer.

Fix the listed lint errors and address reviewer feedback, if any, while
preserving the original behavior. Return ONLY the complete corrected Python
source code. Do not use Markdown code fences.

Lint errors:
{lint_errors}

Reviewer feedback:
{feedback or "None"}

Original code:
{code}
"""
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=get_openai_api_key(),
        temperature=0,
    )
    response = llm.invoke(prompt)
    if not isinstance(response.content, str):
        raise TypeError("The refactor model returned non-text content.")
    code = response.content.strip()
    lines = code.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1] == "```":
        code = "\n".join(lines[1:-1]).strip()
    return code

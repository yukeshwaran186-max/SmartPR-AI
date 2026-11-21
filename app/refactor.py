
"""OpenAI-compatible Python refactor generation."""

from langchain_openai import ChatOpenAI

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    OPENAI_MODEL,
    get_openai_api_key,
)


def get_llm() -> ChatOpenAI:
    """Create the configured chat model only when a refactor is requested."""
    if LLM_BASE_URL:
        return ChatOpenAI(
            model=LLM_MODEL or OPENAI_MODEL,
            api_key=LLM_API_KEY or "ollama",
            base_url=LLM_BASE_URL,
            temperature=0,
        )

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=get_openai_api_key(),
        temperature=0,
    )


def generate_refactor(
    code: str,
    lint_errors: list[str],
    feedback: str = "",
) -> str:
    """Generate corrected code while preserving behavior and reviewer intent."""

    prompt = f"""You are an expert Python code reviewer and refactoring engineer.

Your task is to produce a corrected version of the original Python source code.

MANDATORY REQUIREMENTS:
1. Fix every listed lint error.
2. Address every reviewer feedback instruction explicitly.
3. Remove unused imports when requested.
4. Apply requested formatting corrections.
5. Preserve the original program's behavior.
6. Do not ignore or merely describe reviewer feedback.
7. Return the complete corrected Python source code.
8. Do not use Markdown code fences.
9. Do not add explanations or comments about the changes.
10. Do not remove existing functionality.

Before returning the result, internally verify that:
- All reviewer feedback has been addressed.
- The listed lint issues have been corrected.
- The original behavior is preserved.

Lint errors:
{lint_errors}

Reviewer feedback (MUST FOLLOW):
{feedback or "No additional reviewer feedback."}

Original Python source code:
{code}
"""

    response = get_llm().invoke(prompt)

    if not isinstance(response.content, str):
        raise TypeError("The refactor model returned non-text content.")

    refactored_code = response.content.strip()

    lines = refactored_code.splitlines()

    # Remove Markdown code fences if the model includes them.
    if (
        len(lines) >= 2
        and lines[0].strip().startswith("```")
        and lines[-1].strip() == "```"
    ):
        refactored_code = "\n".join(lines[1:-1]).strip()

    if not refactored_code:
        raise ValueError("The refactor model returned empty source code.")

    return refactored_code

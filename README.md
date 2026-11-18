# Autonomous Code Review & Refactoring Agent

A Python service that fetches changed Python files from a GitHub pull request,
runs `flake8` and `black --check`, asks an OpenAI model to propose behavior-
preserving fixes, and waits for a human decision before writing a commit to the
pull-request branch. LangGraph checkpoints review state in SQLite by default.

## Setup

Requirements: Python 3.11+ and a GitHub token with permission to read the pull
request and write to its head branch. OpenAI API access is needed to generate
proposals. Copy `.env.example` to `.env` and set:

```dotenv
GITHUB_TOKEN=your_github_token
OPENAI_API_KEY=your_openai_api_key
```

By default, refactor proposals use OpenAI with `OPENAI_MODEL` (default:
`gpt-4o-mini`) and require `OPENAI_API_KEY`. For an OpenAI-compatible local
server such as Ollama, optionally set `LLM_BASE_URL` and `LLM_MODEL`; set
`LLM_API_KEY` if that endpoint requires a key. With `LLM_BASE_URL` configured,
the service uses the local model settings instead of requiring an OpenAI key.
Example:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5-coder:7b
LLM_API_KEY=ollama
```

Install dependencies and run the service:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive OpenAPI docs are at
`http://127.0.0.1:8000/docs`. `main:app` is the ASGI entry point. The SQLite
checkpoint path defaults to `checkpoints.sqlite` and can be changed with
`CHECKPOINT_DB`.

## Workflow

1. `POST /api/webhooks/github` accepts a GitHub pull-request event, fetches
   changed Python files, lints them, and generates a proposal.
2. The graph pauses immediately before `apply_changes_node`. The response
   includes `thread_id`, proposed code, and lint output for human inspection.
3. `POST /api/reviews/{thread_id}/approve` either approves and commits all
   proposed files in one Git commit, or rejects with feedback. Rejection sends
   the existing code and feedback back through refactor generation, then pauses
   again at the approval gate.

The service writes changes to the pull request's head repository and branch.
Deploy it behind appropriate network access controls; the approval endpoint is
intended for trusted reviewers.

## API examples

Start a review using a GitHub `pull_request` webhook-shaped payload:

```bash
curl -X POST http://127.0.0.1:8000/api/webhooks/github \
  -H "Content-Type: application/json" \
  -d '{
    "action": "opened",
    "repository": {"full_name": "acme/project"},
    "pull_request": {
      "number": 12,
      "html_url": "https://github.com/acme/project/pull/12",
      "head": {
        "ref": "feature/review",
        "repo": {"full_name": "acme/project"}
      }
    }
  }'
```

The response contains a `thread_id` and the proposed code. Use that ID to
approve the proposal and commit it:

```bash
curl -X POST http://127.0.0.1:8000/api/reviews/<thread_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "feedback": null}'
```

Reject and regenerate with reviewer feedback:

```bash
curl -X POST http://127.0.0.1:8000/api/reviews/<thread_id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approved": false, "feedback": "Keep the public API unchanged."}'
```

## Tests

Run the offline test suite (the tests mock GitHub and refactor dependencies):

```powershell
python -m pytest -q
```

The verification tests cover the three critical checks:

1. `tests/test_tools.py::test_linter_reports_python_syntax_errors` runs the
   isolated linter against invalid Python source and verifies the syntax issue.
2. `tests/test_graph.py::test_graph_pauses_before_apply_changes_node` verifies
   that execution pauses at the approval gate without committing.
3. `tests/test_graph.py::test_rejection_routes_back_to_refactor_and_pauses_again`
   verifies that rejection feedback is used and the graph pauses again.

API tests additionally exercise webhook startup, approve/reject decisions,
unknown-thread 404 responses, and invalid-payload 422 responses using FastAPI's
`TestClient`.

## OpenAPI

The checked-in OpenAPI document is `openapi.json`. Regenerate it after API
changes with:

```powershell
python -c "import json; from main import app; open('openapi.json', 'w', encoding='utf-8').write(json.dumps(app.openapi(), indent=2) + '\n')"
```

## Docker

Build and run the API image:

```bash
docker build -t smartpr-ai .
docker run --env-file .env -p 8000:8000 smartpr-ai
```

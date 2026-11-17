"""ASGI entry point for ``uvicorn main:app --reload``."""

from app.api import create_app

app = create_app()

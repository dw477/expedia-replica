"""ASGI entry point; HTTP handling belongs to the HTTP controller."""

from backend.controllers.http import app, create_app

__all__ = ["app", "create_app"]

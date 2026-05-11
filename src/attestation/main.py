"""Attestation Service entrypoint.

Imports and re-exports the FastAPI ``app`` instance from ``app.py`` so that
existing launch commands (uvicorn src.attestation.main:app) continue to work
without modification.
"""

from .core.app import create_app

app = create_app()

"""Deprecated: use core.config.Settings / get_settings() instead."""
from __future__ import annotations

from core.config import Settings as Config, get_settings  # noqa: F401

__all__ = ["Config", "get_settings"]


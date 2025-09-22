# backend/config/logging_cfg.py
from __future__ import annotations
from backend.logging_setup import setup_logging as _setup_logging

LOGGING_CONFIG: dict = {}
__all__ = ["apply_logging_config", "LOGGING_CONFIG"]

def apply_logging_config() -> None:
    """Compatibility shim: call the central logging setup."""
    _setup_logging()

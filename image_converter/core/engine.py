"""Compatibility wrapper for the conversion service."""

from .conversion import engine as _engine

globals().update(
    {
        name: getattr(_engine, name)
        for name in dir(_engine)
        if not name.startswith("__")
    }
)

__all__ = [name for name in globals() if not name.startswith("__")]

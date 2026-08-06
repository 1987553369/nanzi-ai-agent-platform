from __future__ import annotations

from pathlib import Path


def resolve_contained_file(root: str | Path, requested_path: str) -> Path | None:
    """Resolve a regular file only when it remains inside the configured root."""
    root_path = Path(root).resolve()
    try:
        candidate = (root_path / str(requested_path or "")).resolve()
        candidate.relative_to(root_path)
    except (OSError, RuntimeError, ValueError):
        return None

    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None

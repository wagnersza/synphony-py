"""Helpers for keeping workspace paths inside their configured root."""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from synphony.errors import WorkspacePathError


def reject_path_traversal(value: str) -> None:
    """Reject identifiers that carry explicit parent-directory traversal."""
    if ".." in PurePath(value).parts:
        raise WorkspacePathError("workspace identifier must not contain parent traversal")


def safe_child_path(root: str | Path, child_name: str) -> Path:
    """Return `<root>/<child_name>` only when it remains under `root`."""
    root_path = Path(root).expanduser().resolve()
    child_path = (root_path / child_name).resolve()

    if os.path.commonpath([str(root_path), str(child_path)]) != str(root_path):
        raise WorkspacePathError(
            "workspace path escaped configured root",
            details={"root": str(root_path), "path": str(child_path)},
        )

    return child_path

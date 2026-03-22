"""Undo/redo history — JSON snapshot stack for LayerProject."""

from __future__ import annotations

import json
from pathlib import Path


MAX_HISTORY = 20


class History:
    """Manages undo/redo snapshots for a LayerProject.

    Stores project.json snapshots (metadata only, not pixel data).
    """

    def __init__(self, max_size: int = MAX_HISTORY):
        self.max_size = max_size
        self._undo_stack: list[str] = []  # JSON strings
        self._redo_stack: list[str] = []

    def push(self, project_json: str) -> None:
        """Save current state as a snapshot. Clears redo stack."""
        self._undo_stack.append(project_json)
        if len(self._undo_stack) > self.max_size:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 1

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> str | None:
        """Undo: move current state to redo stack, return previous state."""
        if not self.can_undo():
            return None
        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        return self._undo_stack[-1]

    def redo(self) -> str | None:
        """Redo: move state from redo stack back to undo stack."""
        if not self.can_redo():
            return None
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        return state

    @property
    def undo_count(self) -> int:
        return max(0, len(self._undo_stack) - 1)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def save_to_file(self, path: Path) -> None:
        """Persist history to a JSON file."""
        data = {
            "undo_stack": self._undo_stack,
            "redo_stack": self._redo_stack,
            "max_size": self.max_size,
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path) -> History:
        """Load history from a JSON file."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        h = cls(max_size=data.get("max_size", MAX_HISTORY))
        h._undo_stack = data.get("undo_stack", [])
        h._redo_stack = data.get("redo_stack", [])
        return h

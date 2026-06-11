from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SESSION = Path.home() / ".cli-anything-openrefine" / "session.json"


@dataclass
class SessionState:
    base_url: str = "http://127.0.0.1:3333"
    project_id: str | None = None
    project_name: str | None = None
    last_export: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    future: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "last_export": self.last_export,
            "history": self.history,
            "future": self.future,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        return cls(
            base_url=str(data.get("base_url") or "http://127.0.0.1:3333"),
            project_id=data.get("project_id"),
            project_name=data.get("project_name"),
            last_export=data.get("last_export"),
            history=list(data.get("history") or []),
            future=list(data.get("future") or []),
        )


class SessionStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_SESSION

    def load(self) -> SessionState:
        if not self.path.exists():
            return SessionState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Session file is not a JSON object: {self.path}")
        return SessionState.from_dict(data)

    def save(self, state: SessionState) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".session-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state.to_dict(), handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return self.path

    def record(self, state: SessionState, action: str, payload: dict[str, Any]) -> None:
        state.history.append({"action": action, "payload": payload})
        state.future.clear()

    def undo(self, state: SessionState) -> dict[str, Any]:
        if not state.history:
            raise ValueError("No local session action to undo")
        item = state.history.pop()
        state.future.append(item)
        return item

    def redo(self, state: SessionState) -> dict[str, Any]:
        if not state.future:
            raise ValueError("No local session action to redo")
        item = state.future.pop()
        state.history.append(item)
        return item

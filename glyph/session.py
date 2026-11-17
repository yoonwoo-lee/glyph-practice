"""One study session: the feed of events and the files saved along the way."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import List, Optional


class Session:
    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / time.strftime("%Y-%m-%d_%H%M%S")
        (self.dir / "looks").mkdir(parents=True, exist_ok=True)
        self.started = time.time()
        self._events: List[dict] = []
        self._lock = threading.Lock()

    def add_event(self, kind: str, title: str, body: str = "", **meta) -> dict:
        with self._lock:
            event = {
                "id": len(self._events) + 1,
                "time": time.strftime("%H:%M:%S"),
                "kind": kind,
                "title": title,
                "body": body,
                "meta": meta,
            }
            self._events.append(event)
            snapshot = list(self._events)
        try:
            (self.dir / "events.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return event

    def events_since(self, last_id: int = 0) -> List[dict]:
        with self._lock:
            return [e for e in self._events if e["id"] > last_id]

    def events_of(self, *kinds: str) -> List[dict]:
        with self._lock:
            return [e for e in self._events if e["kind"] in kinds]

    def save_look(self, n: int, page_jpg: bytes, crop_jpg: Optional[bytes]) -> None:
        """Keep exactly what the vision model was shown, for debugging."""
        try:
            (self.dir / "looks" / f"{n:03d}_page.jpg").write_bytes(page_jpg)
            if crop_jpg:
                (self.dir / "looks" / f"{n:03d}_new_ink.jpg").write_bytes(crop_jpg)
        except OSError:
            pass

    def save_text(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

"""Persistent registry of chats the bot has talked to.

The registry remembers which chats should receive release announcements and
which release was last announced, so each version is announced exactly once
across restarts.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Iterable, Optional, Set

logger = logging.getLogger(__name__)


class UserRegistry:
    """JSON-file backed set of chat IDs plus the last announced version."""

    def __init__(self, path: Path):
        """
        Args:
            path: JSON file used for persistence. Created on first save.
        """
        self.path = Path(path)
        self._lock = threading.Lock()
        self._chat_ids: Set[int] = set()
        self._last_announced_version: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._chat_ids = {int(c) for c in data.get("chat_ids", [])}
            self._last_announced_version = data.get("last_announced_version")
        except (OSError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Could not read user registry {self.path}: {e}; starting empty")

    def _save(self) -> None:
        """Write atomically so a crash never leaves a truncated file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "chat_ids": sorted(self._chat_ids),
            "last_announced_version": self._last_announced_version,
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def chat_ids(self) -> Set[int]:
        with self._lock:
            return set(self._chat_ids)

    @property
    def last_announced_version(self) -> Optional[str]:
        with self._lock:
            return self._last_announced_version

    def add(self, chat_id: int) -> bool:
        """Remember a chat. Returns True if it was new."""
        with self._lock:
            if chat_id in self._chat_ids:
                return False
            self._chat_ids.add(chat_id)
            self._save()
            return True

    def remove(self, chat_id: int) -> None:
        """Forget a chat (e.g. the user blocked the bot)."""
        with self._lock:
            if chat_id in self._chat_ids:
                self._chat_ids.discard(chat_id)
                self._save()

    def mark_announced(self, version: str) -> None:
        with self._lock:
            self._last_announced_version = version
            self._save()

    def recipients(self, extra: Iterable[int] = ()) -> Set[int]:
        """Known chats plus any configured extra IDs (e.g. allowed users)."""
        return self.chat_ids | set(extra)

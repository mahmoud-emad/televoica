"""SQLite database of the people who use the bot.

Keeps one profile per Telegram user (name, username, language, first/last
seen, request count, blocked flag) and a log of every transcription request,
so we always know who our users are and how they use the bot. It also holds
the release that was last announced, so each version is announced exactly
once across restarts.

Only data Telegram sends with each message is stored; no audio or text.
"""

import json
import logging
import sqlite3
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,   -- also the chat id for private chats
    username      TEXT,
    first_name    TEXT,
    last_name     TEXT,
    language_code TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    blocked       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    kind          TEXT,
    audio_seconds REAL,
    chars         INTEGER,
    ok            INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_user ON requests(user_id);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UserRegistry:
    """SQLite-backed user database (file ``televoica.db`` in the data dir)."""

    def __init__(self, path: Path):
        """
        Args:
            path: SQLite file. Created, with its folder, on first use. A
                ``users.json`` from an older version next to it is imported.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()
        self._import_legacy_json(self.path.with_name("users.json"))

    def _import_legacy_json(self, legacy: Path) -> None:
        if not legacy.exists():
            return
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            for chat_id in data.get("chat_ids", []):
                self.upsert(int(chat_id))
            if data.get("last_announced_version") and not self.last_announced_version:
                self.mark_announced(data["last_announced_version"])
            legacy.rename(legacy.with_suffix(".json.imported"))
            logger.info(f"Imported legacy {legacy.name} into {self.path.name}")
        except (OSError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Could not import legacy {legacy}: {e}")

    def _meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    @property
    def last_announced_version(self) -> Optional[str]:
        return self._meta("last_announced_version")

    def mark_announced(self, version: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO meta(key, value) VALUES('last_announced_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (version,),
            )
            self._db.commit()

    # ------------------------------------------------------------------ users

    def upsert(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
        seen_at: Optional[str] = None,
    ) -> bool:
        """Create or refresh a user; returns True if the user is new.

        Messaging the bot again clears the blocked flag. Profile fields that
        Telegram did not send keep their stored value. ``seen_at`` overrides
        the timestamp (used when importing history).
        """
        now = seen_at or _now()
        with self._lock:
            existed = self._db.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            self._db.execute(
                """
                INSERT INTO users(user_id, username, first_name, last_name, language_code,
                                  first_seen, last_seen)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username      = COALESCE(excluded.username, username),
                    first_name    = COALESCE(excluded.first_name, first_name),
                    last_name     = COALESCE(excluded.last_name, last_name),
                    language_code = COALESCE(excluded.language_code, language_code),
                    last_seen     = excluded.last_seen,
                    blocked       = 0
                """,
                (user_id, username, first_name, last_name, language_code, now, now),
            )
            self._db.commit()
        return existed is None

    def add(self, chat_id: int) -> bool:
        """Remember a chat by id only. Returns True if it was new."""
        return self.upsert(chat_id)

    def remove(self, chat_id: int) -> None:
        """The user blocked the bot: keep their profile, stop messaging them."""
        with self._lock:
            self._db.execute("UPDATE users SET blocked = 1 WHERE user_id = ?", (chat_id,))
            self._db.commit()

    def get(self, user_id: int) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        """All users, most active first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM users ORDER BY request_count DESC, first_seen"
            ).fetchall()
        return [dict(r) for r in rows]

    @property
    def chat_ids(self) -> set[int]:
        """Users who can currently be messaged (not blocked)."""
        with self._lock:
            rows = self._db.execute("SELECT user_id FROM users WHERE blocked = 0").fetchall()
        return {r["user_id"] for r in rows}

    def recipients(self, extra: Iterable[int] = ()) -> set[int]:
        """Reachable users plus any configured extra IDs, minus blocked users."""
        with self._lock:
            rows = self._db.execute("SELECT user_id FROM users WHERE blocked = 1").fetchall()
        blocked = {r["user_id"] for r in rows}
        return (self.chat_ids | set(extra)) - blocked

    # --------------------------------------------------------------- requests

    def record_request(
        self,
        user_id: int,
        kind: str,
        ok: bool,
        audio_seconds: Optional[float] = None,
        chars: Optional[int] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Log one transcription request and bump the user's counters."""
        created_at = created_at or _now()
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO users(user_id, first_seen, last_seen) VALUES(?, ?, ?)",
                (user_id, created_at, created_at),
            )
            self._db.execute(
                "INSERT INTO requests(user_id, kind, audio_seconds, chars, ok, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (user_id, kind, audio_seconds, chars, int(ok), created_at),
            )
            self._db.execute(
                "UPDATE users SET request_count = request_count + 1, "
                "first_seen = MIN(first_seen, ?), last_seen = MAX(last_seen, ?) "
                "WHERE user_id = ?",
                (created_at, created_at, user_id),
            )
            self._db.commit()

    def stats(self) -> dict:
        """Totals for dashboards and the ``televoica users`` command."""
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS users, COALESCE(SUM(blocked), 0) AS blocked, "
                "COALESCE(SUM(request_count), 0) AS requests FROM users"
            ).fetchone()
        return dict(row)

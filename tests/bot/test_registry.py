"""Tests for the SQLite user database."""

import json

from televoica.bot.registry import UserRegistry


def test_upsert_creates_and_updates_profile(tmp_path):
    db = UserRegistry(tmp_path / "state" / "televoica.db")
    assert db.upsert(7, username="ann", first_name="Ann", language_code="en") is True
    assert db.upsert(7, first_name="Anna") is False  # refresh, not new

    user = db.get(7)
    assert user["username"] == "ann"  # missing fields keep their stored value
    assert user["first_name"] == "Anna"
    assert user["language_code"] == "en"


def test_data_persists_across_instances(tmp_path):
    path = tmp_path / "televoica.db"
    UserRegistry(path).upsert(1, username="a")
    db = UserRegistry(path)
    db.add(2)
    db.mark_announced("0.2.0")

    again = UserRegistry(path)
    assert again.chat_ids == {1, 2}
    assert again.last_announced_version == "0.2.0"


def test_blocked_users_are_kept_but_not_messaged(tmp_path):
    db = UserRegistry(tmp_path / "televoica.db")
    db.upsert(1, username="a")
    db.upsert(2)
    db.remove(1)

    assert db.get(1)["username"] == "a"  # profile is never deleted
    assert db.chat_ids == {2}
    assert db.recipients(extra=[1, 3]) == {2, 3}  # extras cannot override a block

    db.upsert(1)  # messaging the bot again unblocks
    assert db.chat_ids == {1, 2}


def test_record_request_updates_counters_and_stats(tmp_path):
    db = UserRegistry(tmp_path / "televoica.db")
    db.upsert(1, first_name="A")
    db.record_request(1, "voice message", True, audio_seconds=12.5, chars=80)
    db.record_request(1, "audio file", False)

    assert db.get(1)["request_count"] == 2
    assert db.stats() == {"users": 1, "blocked": 0, "requests": 2}
    assert [u["user_id"] for u in db.list_users()] == [1]


def test_record_request_creates_unknown_user(tmp_path):
    db = UserRegistry(tmp_path / "televoica.db")
    db.record_request(9, "voice message", True)
    assert db.get(9)["request_count"] == 1


def test_imports_legacy_json_once(tmp_path):
    (tmp_path / "users.json").write_text(
        json.dumps({"chat_ids": [4, 5], "last_announced_version": "0.1.0"})
    )
    db = UserRegistry(tmp_path / "televoica.db")

    assert db.chat_ids == {4, 5}
    assert db.last_announced_version == "0.1.0"
    assert not (tmp_path / "users.json").exists()
    assert (tmp_path / "users.json.imported").exists()


def test_backfilled_requests_move_first_seen_back(tmp_path):
    db = UserRegistry(tmp_path / "televoica.db")
    db.upsert(1, seen_at="2026-05-19T10:00:00+00:00")
    db.record_request(1, "voice message", True, created_at="2026-05-19T10:00:00+00:00")
    db.record_request(1, "voice message", True, created_at="2026-06-01T10:00:00+00:00")

    user = db.get(1)
    assert user["first_seen"] == "2026-05-19T10:00:00+00:00"
    assert user["last_seen"] == "2026-06-01T10:00:00+00:00"

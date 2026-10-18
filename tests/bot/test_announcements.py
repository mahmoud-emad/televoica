"""Tests for release announcements."""

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from telegram.error import Forbidden, NetworkError

import televoica
from televoica.bot import announcements
from televoica.bot.announcements import (
    announce_release,
    extract_summary,
    format_announcement,
    read_release_notes,
    release_url,
)
from televoica.bot.registry import UserRegistry

REPO = "https://github.com/Mahmoud-Emad/televoica"
NOTES = "# Title\n\nintro\n\n## Summary\n\n- one\n- two\n\n## Details\n\nlong text\n"


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(announcements, "SEND_INTERVAL_SECONDS", 0)


@pytest.fixture
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "1.0.0.md").write_text(NOTES, encoding="utf-8")
    return d


def run(coro):
    return asyncio.run(coro)


def test_extract_summary_uses_summary_section():
    assert extract_summary(NOTES) == "- one\n- two"


def test_extract_summary_falls_back_to_first_paragraph():
    assert extract_summary("# T\n\nfirst para\n\nsecond") == "first para"


def test_format_announcement_has_bullets_and_link():
    text = format_announcement("1.0.0", "- one\n- two", release_url(REPO + "/", "1.0.0"))
    assert "v1.0.0" in text
    assert "• one\n• two" in text
    assert text.endswith(f"Full release notes: {REPO}/releases/tag/v1.0.0")


def test_read_release_notes_missing_returns_none(tmp_path):
    assert read_release_notes("9.9.9", tmp_path) is None


def test_announces_to_all_recipients_once(tmp_path, notes_dir):
    registry = UserRegistry(tmp_path / "users.json")
    registry.add(1)
    bot = AsyncMock()

    sent = run(announce_release(bot, registry, "1.0.0", REPO, extra_recipients=[2], notes_dir=notes_dir))

    assert sent == 2
    assert {c.kwargs["chat_id"] for c in bot.send_message.call_args_list} == {1, 2}
    assert "releases/tag/v1.0.0" in bot.send_message.call_args.kwargs["text"]
    assert registry.last_announced_version == "1.0.0"

    # Second start on the same version must not message anyone again.
    bot.reset_mock()
    assert run(announce_release(bot, registry, "1.0.0", REPO, notes_dir=notes_dir)) == 0
    bot.send_message.assert_not_called()


def test_missing_notes_sends_nothing_and_does_not_mark(tmp_path, notes_dir):
    registry = UserRegistry(tmp_path / "users.json")
    registry.add(1)
    bot = AsyncMock()

    assert run(announce_release(bot, registry, "2.0.0", REPO, notes_dir=notes_dir)) == 0
    bot.send_message.assert_not_called()
    assert registry.last_announced_version is None


def test_blocked_user_is_removed_and_others_still_get_it(tmp_path, notes_dir):
    registry = UserRegistry(tmp_path / "users.json")
    registry.add(1)
    registry.add(2)
    bot = AsyncMock()

    async def send_message(chat_id, **kwargs):
        if chat_id == 1:
            raise Forbidden("bot was blocked by the user")

    bot.send_message.side_effect = send_message

    sent = run(announce_release(bot, registry, "1.0.0", REPO, notes_dir=notes_dir))

    assert sent == 1
    assert registry.chat_ids == {2}
    assert registry.last_announced_version == "1.0.0"


def test_other_send_errors_do_not_abort(tmp_path, notes_dir):
    registry = UserRegistry(tmp_path / "users.json")
    registry.add(1)
    registry.add(2)
    bot = AsyncMock()

    async def send_message(chat_id, **kwargs):
        if chat_id == 1:
            raise NetworkError("boom")

    bot.send_message.side_effect = send_message

    assert run(announce_release(bot, registry, "1.0.0", REPO, notes_dir=notes_dir)) == 1
    assert registry.chat_ids == {1, 2}  # transient failure keeps the user


def test_current_version_has_release_notes_with_summary():
    """Every version bump must ship notes; the Release workflow depends on it."""
    notes = read_release_notes(televoica.__version__)
    assert notes, f"release_notes/{televoica.__version__}.md is missing"
    assert extract_summary(notes)
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    assert re.search(rf'^version = "{re.escape(televoica.__version__)}"', pyproject, re.M)

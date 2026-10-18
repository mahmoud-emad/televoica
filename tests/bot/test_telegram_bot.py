"""Tests for chat tracking and startup announcements in the Telegram bot."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from televoica.bot.telegram_bot import TelegramSTTBot
from televoica.config.settings import Settings, TelegramConfig


def make_bot(tmp_path, allowed=None, announce=True):
    settings = Settings(
        telegram=TelegramConfig(bot_token="token"),
        telegram_bot=True,
        data_dir=tmp_path / "data",
        temp_dir=tmp_path / "tmp",
    )
    settings.telegram.allowed_users = allowed or []
    settings.telegram.announce_releases = announce
    return TelegramSTTBot(settings=settings, engine=MagicMock())


def update(user_id, chat_id, chat_type="private"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username="ann",
            first_name="Ann",
            last_name=None,
            language_code="ar",
        ),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
    )


def test_tracks_private_chats(tmp_path):
    bot = make_bot(tmp_path)
    asyncio.run(bot._track_user(update(7, 7), None))
    assert bot.registry.chat_ids == {7}
    user = bot.registry.get(7)
    assert (user["username"], user["first_name"], user["language_code"]) == ("ann", "Ann", "ar")


def test_ignores_group_chats_and_disallowed_users(tmp_path):
    bot = make_bot(tmp_path, allowed=[7])
    asyncio.run(bot._track_user(update(7, -100, chat_type="supergroup"), None))
    asyncio.run(bot._track_user(update(8, 8), None))
    assert bot.registry.chat_ids == set()


def test_post_init_announces_to_known_and_allowed_users(tmp_path):
    bot = make_bot(tmp_path, allowed=[2])
    bot.registry.add(1)
    app = SimpleNamespace(bot=AsyncMock())

    with patch("televoica.bot.telegram_bot.announce_release", new=AsyncMock()) as announce:
        asyncio.run(bot._post_init(app))

    args, kwargs = announce.call_args
    assert args[0] is app.bot and args[1] is bot.registry
    assert kwargs["extra_recipients"] == {2}


def test_post_init_respects_opt_out_and_swallows_errors(tmp_path):
    off = make_bot(tmp_path, announce=False)
    with patch("televoica.bot.telegram_bot.announce_release", new=AsyncMock()) as announce:
        asyncio.run(off._post_init(SimpleNamespace(bot=AsyncMock())))
    announce.assert_not_called()

    on = make_bot(tmp_path / "b")
    with patch(
        "televoica.bot.telegram_bot.announce_release",
        new=AsyncMock(side_effect=RuntimeError("telegram down")),
    ):
        asyncio.run(on._post_init(SimpleNamespace(bot=AsyncMock())))  # must not raise


def test_record_request_stores_usage_and_never_raises(tmp_path):
    bot = make_bot(tmp_path)
    bot._record_request(7, "voice message", True, 12.0, "hello")
    assert bot.registry.get(7)["request_count"] == 1

    bot.registry.record_request = MagicMock(side_effect=RuntimeError("disk full"))
    bot._record_request(7, "voice message", True, 12.0, "hello")  # must not raise

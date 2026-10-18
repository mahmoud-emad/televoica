"""Release announcements sent to bot users after an update.

Each release has a notes file ``release_notes/<version>.md``. Its
``## Summary`` section becomes the short chat message; the full file is
published as a GitHub Release, which the message links to.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Iterable, Optional

from televoica.bot.registry import UserRegistry

logger = logging.getLogger(__name__)

DEFAULT_NOTES_DIR = Path(__file__).resolve().parents[2] / "release_notes"
SEND_INTERVAL_SECONDS = 0.05  # stay well under Telegram's ~30 msg/s limit


def read_release_notes(version: str, notes_dir: Path = DEFAULT_NOTES_DIR) -> Optional[str]:
    """Return the notes markdown for a version, or None if there is none."""
    path = Path(notes_dir) / f"{version}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def extract_summary(markdown: str) -> str:
    """Pull the short chat summary out of a notes file.

    Uses the body of the ``## Summary`` section; falls back to the first
    paragraph after the title when there is no such section.
    """
    match = re.search(r"^##\s+Summary\s*$(.*?)(?=^##\s|\Z)", markdown, re.M | re.S)
    if match:
        return match.group(1).strip()
    body = [ln for ln in markdown.splitlines() if not ln.startswith("#")]
    paragraphs = [p.strip() for p in "\n".join(body).split("\n\n") if p.strip()]
    return paragraphs[0] if paragraphs else ""


def release_url(repo_url: str, version: str) -> str:
    return f"{repo_url.rstrip('/')}/releases/tag/v{version}"


def format_announcement(version: str, summary: str, url: str) -> str:
    # Plain text on purpose: no parse_mode means no escaping pitfalls.
    summary = re.sub(r"^\s*[-*]\s+", "• ", summary, flags=re.M)
    return f"🚀 Televoica was updated to v{version}\n\n{summary}\n\nFull release notes: {url}"


async def announce_release(
    bot,
    registry: UserRegistry,
    version: str,
    repo_url: str,
    extra_recipients: Iterable[int] = (),
    notes_dir: Path = DEFAULT_NOTES_DIR,
) -> int:
    """Send the release summary to every known chat, once per version.

    Returns the number of chats successfully messaged. Does nothing when the
    version was already announced or has no notes file.
    """
    if registry.last_announced_version == version:
        logger.info(f"Release v{version} already announced; skipping")
        return 0

    notes = read_release_notes(version, notes_dir)
    if not notes:
        logger.info(f"No release notes for v{version}; skipping announcement")
        return 0

    try:
        from telegram.error import Forbidden, RetryAfter
    except ImportError:
        raise ImportError(
            "python-telegram-bot is not installed. "
            "Install it with: pip install python-telegram-bot"
        )

    text = format_announcement(version, extract_summary(notes), release_url(repo_url, version))
    sent = 0
    for chat_id in sorted(registry.recipients(extra_recipients)):
        try:
            try:
                await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
            except RetryAfter as e:
                await asyncio.sleep(float(e.retry_after) + 1)
                await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
            sent += 1
        except Forbidden:
            logger.info(f"Chat {chat_id} blocked the bot; removing from registry")
            registry.remove(chat_id)
        except Exception as e:
            logger.warning(f"Could not send release notes to chat {chat_id}: {e}")
        await asyncio.sleep(SEND_INTERVAL_SECONDS)

    registry.mark_announced(version)
    logger.info(f"Announced v{version} to {sent} chat(s)")
    return sent

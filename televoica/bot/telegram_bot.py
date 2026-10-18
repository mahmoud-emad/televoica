"""
Telegram bot implementation for speech-to-text conversion.

This module implements the Telegram bot that receives voice messages
and uses the SpeechToTextEngine to transcribe them.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from televoica import __version__
from televoica.bot.announcements import announce_release
from televoica.bot.registry import UserRegistry
from televoica.core.audio import (
    DEFAULT_CHUNK_SECONDS,
    probe_duration_seconds,
    split_into_chunks,
)
from televoica.core.engine import SpeechToTextEngine
from televoica.config.settings import Settings

# Files longer than this are split into chunks so we can show progress
# and avoid loading huge audio into Whisper at once.
CHUNK_THRESHOLD_SECONDS = DEFAULT_CHUNK_SECONDS

logger = logging.getLogger(__name__)


class TelegramSTTBot:
    """
    Telegram bot for speech-to-text conversion.
    
    This bot receives voice messages and audio files, transcribes them
    using the SpeechToTextEngine, and sends back the transcribed text.
    """

    def __init__(self, settings: Settings, engine: Optional[SpeechToTextEngine] = None):
        """
        Initialize the Telegram bot.

        Args:
            settings: Application settings
            engine: Optional SpeechToTextEngine instance. If None, creates a new one.
        """
        self.settings = settings
        self.engine = engine or SpeechToTextEngine()
        self.bot_token = settings.telegram.bot_token
        self.allowed_users = set(settings.telegram.allowed_users)
        self.max_file_size = settings.telegram.max_file_size_mb * 1024 * 1024  # Convert to bytes
        
        self.registry = UserRegistry(settings.data_dir / "televoica.db")

        # Will be initialized in run()
        self.application = None
        
        logger.info("TelegramSTTBot initialized")

    def _is_user_allowed(self, user_id: int) -> bool:
        """
        Check if a user is allowed to use the bot.

        Args:
            user_id: Telegram user ID

        Returns:
            True if user is allowed (or if no restrictions are set)
        """
        if not self.allowed_users:
            return True  # No restrictions
        return user_id in self.allowed_users

    async def _track_user(self, update, context):
        """Remember private chats so they can receive release announcements.

        Runs in its own handler group, so it never blocks the real handlers.
        """
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None or chat.type != "private":
            return
        if not self._is_user_allowed(user.id):
            return
        if self.registry.upsert(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        ):
            logger.info(f"Registered new user {user.id} (@{user.username})")

    def _record_request(self, user_id, kind, ok, duration, text) -> None:
        """Log the request for usage stats; must never break the reply."""
        try:
            self.registry.record_request(
                user_id, kind, ok, audio_seconds=duration, chars=len(text or "")
            )
        except Exception as e:
            logger.warning(f"Could not record request for user {user_id}: {e}")

    async def _post_init(self, application):
        """Announce a new release to known chats once the bot is connected."""
        if not self.settings.telegram.announce_releases:
            return
        try:
            await announce_release(
                application.bot,
                self.registry,
                __version__,
                self.settings.telegram.repo_url,
                extra_recipients=self.allowed_users,
            )
        except Exception as e:
            # Never let an announcement problem stop the bot from starting.
            logger.error(f"Release announcement failed: {e}", exc_info=True)

    async def start_command(self, update, context):
        """Handle /start command."""
        try:
            from telegram import Update
            from telegram.ext import ContextTypes
        except ImportError:
            raise ImportError(
                "python-telegram-bot is not installed. "
                "Install it with: pip install python-telegram-bot"
            )
        
        user_id = update.effective_user.id
        
        if not self._is_user_allowed(user_id):
            await update.message.reply_text(
                "⛔ Sorry, you are not authorized to use this bot."
            )
            return
        
        welcome_message = (
            "👋 Welcome to Televoica Bot!\n\n"
            "Send me a voice message or audio file, and I'll transcribe it for you.\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/help - Show help information\n"
            "/info - Show bot information"
        )
        
        await update.message.reply_text(welcome_message)

    async def help_command(self, update, context):
        """Handle /help command."""
        user_id = update.effective_user.id
        
        if not self._is_user_allowed(user_id):
            await update.message.reply_text(
                "⛔ Sorry, you are not authorized to use this bot."
            )
            return
        
        help_message = (
            "ℹ️ How to use this bot:\n\n"
            "1. Send a voice message (record using Telegram's voice recorder)\n"
            "2. Or send an audio file (MP3, OGG, WAV, etc.)\n"
            "3. Wait for the transcription\n\n"
            f"Maximum file size: {self.settings.telegram.max_file_size_mb} MB\n\n"
            "The bot uses advanced speech recognition to provide accurate transcriptions."
        )
        
        await update.message.reply_text(help_message)

    async def info_command(self, update, context):
        """Handle /info command."""
        user_id = update.effective_user.id
        
        if not self._is_user_allowed(user_id):
            await update.message.reply_text(
                "⛔ Sorry, you are not authorized to use this bot."
            )
            return
        
        provider_name = self.engine.provider.__class__.__name__
        info_message = (
            f"🤖 Bot Information:\n\n"
            f"STT Provider: {provider_name}\n"
            f"Max File Size: {self.settings.telegram.max_file_size_mb} MB\n"
            f"Version: {__version__}"
        )
        
        await update.message.reply_text(info_message)

    async def handle_voice(self, update, context):
        """Handle voice messages."""
        user_id = update.effective_user.id

        if not self._is_user_allowed(user_id):
            await update.message.reply_text(
                "⛔ Sorry, you are not authorized to use this bot."
            )
            return

        voice = update.message.voice
        if voice.file_size > self.max_file_size:
            await update.message.reply_text(
                f"⚠️ File too large. Maximum size is {self.settings.telegram.max_file_size_mb} MB."
            )
            return

        await self._process_audio(
            update=update,
            context=context,
            file_id=voice.file_id,
            user_id=user_id,
            file_suffix=".ogg",
            initial_text="🎙️ Downloading your voice message...",
            kind="voice message",
        )

    async def handle_audio(self, update, context):
        """Handle audio files."""
        user_id = update.effective_user.id

        if not self._is_user_allowed(user_id):
            await update.message.reply_text(
                "⛔ Sorry, you are not authorized to use this bot."
            )
            return

        audio = update.message.audio
        if audio.file_size > self.max_file_size:
            await update.message.reply_text(
                f"⚠️ File too large. Maximum size is {self.settings.telegram.max_file_size_mb} MB."
            )
            return

        file_suffix = Path(audio.file_name).suffix if audio.file_name else ".mp3"
        await self._process_audio(
            update=update,
            context=context,
            file_id=audio.file_id,
            user_id=user_id,
            file_suffix=file_suffix,
            initial_text="🎵 Downloading your audio file...",
            kind="audio file",
        )

    async def _process_audio(
        self,
        update,
        context,
        *,
        file_id: str,
        user_id: int,
        file_suffix: str,
        initial_text: str,
        kind: str,
    ):
        """Download, optionally chunk, transcribe, and reply.

        Long files are split into ~5-min chunks and transcribed sequentially
        with per-chunk progress edits so the user sees forward motion. Every
        Whisper call runs in a worker thread so the asyncio event loop stays
        responsive (and Telegram long-polling doesn't drop).
        """
        processing_msg = await update.message.reply_text(initial_text)
        file_path = self.settings.temp_dir / f"{file_id}{file_suffix}"
        chunk_dir: Optional[Path] = None

        duration = None
        text = ""
        ok = False
        try:
            tg_file = await context.bot.get_file(file_id)
            await tg_file.download_to_drive(file_path)
            logger.info(f"Downloaded {kind} from user {user_id}: {file_path}")

            duration = await asyncio.to_thread(probe_duration_seconds, file_path)
            if duration is None:
                logger.info("Could not probe duration; transcribing as single chunk")

            if duration and duration > CHUNK_THRESHOLD_SECONDS:
                text = await self._transcribe_chunked(
                    file_path, duration, processing_msg
                )
            else:
                await processing_msg.edit_text("📝 Transcribing...")
                text = await asyncio.to_thread(
                    self.engine.transcribe_file, file_path
                )

            if text:
                await self._send_transcription(processing_msg, text)
                ok = True
                logger.info(f"Transcription sent to user {user_id}")
            else:
                await processing_msg.edit_text("⚠️ No speech detected in the audio.")

        except Exception as e:
            logger.error(f"Error processing {kind}: {e}", exc_info=True)
            await processing_msg.edit_text(
                f"❌ Error processing {kind}: {str(e)}"
            )
        finally:
            self._record_request(user_id, kind, ok, duration, text)
            file_path.unlink(missing_ok=True)
            if chunk_dir is not None:
                shutil.rmtree(chunk_dir, ignore_errors=True)

    async def _transcribe_chunked(
        self, file_path: Path, duration: float, processing_msg
    ) -> str:
        """Split a long file into chunks and transcribe them in order."""
        minutes = duration / 60
        await processing_msg.edit_text(
            f"🎬 Audio is ~{minutes:.1f} min — splitting into chunks..."
        )

        chunk_dir = Path(tempfile.mkdtemp(prefix="televoica_chunks_", dir=self.settings.temp_dir))
        try:
            chunks = await asyncio.to_thread(
                split_into_chunks, file_path, chunk_dir, CHUNK_THRESHOLD_SECONDS
            )
            total = len(chunks)
            logger.info(f"Split {file_path.name} into {total} chunks")

            parts: list[str] = []
            for idx, chunk in enumerate(chunks, start=1):
                await processing_msg.edit_text(
                    f"📝 Transcribing chunk {idx}/{total}..."
                )
                part = await asyncio.to_thread(self.engine.transcribe_file, chunk)
                if part:
                    parts.append(part.strip())
                chunk.unlink(missing_ok=True)

            return " ".join(parts).strip()
        finally:
            shutil.rmtree(chunk_dir, ignore_errors=True)

    @staticmethod
    async def _send_transcription(processing_msg, text: str) -> None:
        """Send the transcription, splitting across messages if needed.

        Telegram caps message bodies at 4096 chars; long transcripts get
        broken into multiple replies on whitespace boundaries.
        """
        header = "📝 Transcription:\n\n"
        max_len = 4000  # leave headroom for the header / safety margin

        if len(text) + len(header) <= max_len:
            await processing_msg.edit_text(header + text)
            return

        first, rest = TelegramSTTBot._split_for_telegram(text, max_len - len(header))
        await processing_msg.edit_text(header + first)
        chat = processing_msg.chat
        for piece in rest:
            await chat.send_message(piece)

    @staticmethod
    def _split_for_telegram(text: str, first_size: int) -> tuple[str, list[str]]:
        """Split text on whitespace into a first piece and follow-ups (~4000 chars)."""
        chunk_size = 4000
        words = text.split(" ")
        pieces: list[str] = []
        current = ""
        limit = first_size
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > limit:
                pieces.append(current)
                current = word
                limit = chunk_size
            else:
                current = candidate
        if current:
            pieces.append(current)
        return pieces[0], pieces[1:]

    async def error_handler(self, update, context):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

    def run(self):
        """
        Start the Telegram bot.
        
        This method blocks until the bot is stopped.
        """
        try:
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
        except ImportError:
            raise ImportError(
                "python-telegram-bot is not installed. "
                "Install it with: pip install python-telegram-bot"
            )
        
        logger.info("Starting Telegram bot...")
        
        # Create application with generous HTTP timeouts so post-transcription
        # edits to long-running messages don't fail on slow networks.
        self.application = (
            Application.builder()
            .token(self.bot_token)
            .connect_timeout(30.0)
            .read_timeout(60.0)
            .write_timeout(60.0)
            .pool_timeout(30.0)
            .post_init(self._post_init)
            .build()
        )
        
        # Track chats first (group -1 runs before, and never blocks, the handlers below)
        self.application.add_handler(MessageHandler(filters.ALL, self._track_user), group=-1)

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("info", self.info_command))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.AUDIO, self.handle_audio))
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        # Start bot
        logger.info("Bot is running. Press Ctrl+C to stop.")
        self.application.run_polling(allowed_updates=["message"])

    def stop(self):
        """Stop the Telegram bot."""
        if self.application:
            logger.info("Stopping Telegram bot...")
            self.application.stop()


"""
Main CLI entry point for the speech-to-text robot.

This module provides command-line interfaces for:
1. Transcribing audio files (standalone mode)
2. Running the Telegram bot
"""

import sys
import logging
from pathlib import Path
from typing import Optional
import argparse

from televoica.core.engine import SpeechToTextEngine
from televoica.core.providers import (
    FasterWhisperProvider,
    create_provider,
    GoogleCloudSTTProvider,
    WhisperProvider,
)
from televoica.config.settings import load_config, Settings


def setup_logging(level: str = "INFO"):
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # httpx logs every request URL, which contains the bot token
    logging.getLogger("httpx").setLevel(logging.WARNING)


def transcribe_command(args):
    """Handle the transcribe command (standalone mode)."""
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Create provider based on arguments
    if args.provider == "faster_whisper":
        provider = FasterWhisperProvider({
            "model": args.whisper_model,
            "device": args.device,
            "language": args.language,
        })
    elif args.provider == "whisper":
        provider = WhisperProvider({
            "model": args.whisper_model,
            "device": args.device,
            "language": args.language,
        })
    elif args.provider == "google_cloud":
        provider = GoogleCloudSTTProvider({
            "credentials_path": args.google_credentials,
            "language_code": args.language or "en-US",
        })
    else:
        logger.error(f"Unknown provider: {args.provider}")
        sys.exit(1)
    
    # Create engine
    engine = SpeechToTextEngine(provider=provider)
    
    # Transcribe file
    audio_file = Path(args.audio_file)
    
    if not audio_file.exists():
        logger.error(f"Audio file not found: {audio_file}")
        sys.exit(1)
    
    logger.info(f"Transcribing: {audio_file}")
    
    try:
        text = engine.transcribe_file(audio_file)
        
        # Output result
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(text)
            logger.info(f"Transcription saved to: {output_path}")
        else:
            print("\n" + "="*50)
            print("TRANSCRIPTION:")
            print("="*50)
            print(text)
            print("="*50 + "\n")
    
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        sys.exit(1)


def users_command(args):
    """List the users known to the bot (read-only)."""
    from televoica.bot.registry import UserRegistry

    settings = load_config()
    db_path = settings.data_dir / "televoica.db"
    if not db_path.exists():
        print(f"No user database at {db_path}")
        sys.exit(1)

    registry = UserRegistry(db_path)
    stats = registry.stats()
    print(f"{stats['users']} users ({stats['blocked']} blocked), {stats['requests']} requests\n")
    print(f"{'ID':<12} {'Name':<24} {'Username':<20} {'Lang':<5} {'Reqs':>5}  {'First seen':<11} Last seen")
    for u in registry.list_users():
        name = f"{u['first_name'] or ''} {u['last_name'] or ''}".strip()
        username = f"@{u['username']}" if u["username"] else "-"
        flag = " (blocked)" if u["blocked"] else ""
        print(
            f"{u['user_id']:<12} {name[:24]:<24} {username[:20]:<20} "
            f"{(u['language_code'] or '-'):<5} {u['request_count']:>5}  "
            f"{u['first_seen'][:10]:<11} {u['last_seen'][:10]}{flag}"
        )


def bot_command(args):
    """Handle the bot command (Telegram bot mode)."""
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Load configuration
    config_file = Path(args.config) if args.config else None
    settings = load_config(config_file=config_file)
    
    # Override with command-line arguments
    if args.provider:
        settings.stt.provider = args.provider
    if args.whisper_model:
        settings.stt.whisper_model = args.whisper_model
    if args.device:
        settings.stt.whisper_device = args.device
    
    # Enable Telegram bot mode
    settings.telegram_bot = True
    
    # Create STT provider
    try:
        provider = create_provider(settings.stt)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    
    # Create engine
    engine = SpeechToTextEngine(provider=provider)
    
    # Create and run bot
    from televoica.bot.telegram_bot import TelegramSTTBot
    
    bot = TelegramSTTBot(settings=settings, engine=engine)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        bot.stop()
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Televoica Robot: Transcribe audio files or run a Telegram bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transcribe an audio file (standalone mode)
  televoica transcribe audio.mp3
  
  # Transcribe with specific provider and model
  televoica transcribe audio.mp3 --provider whisper --whisper-model medium
  
  # Run Telegram bot
  televoica bot
  
  # Run bot with custom configuration
  televoica bot --config config.yaml --provider whisper --whisper-model small
        """
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Transcribe command (standalone mode)
    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe an audio file (standalone mode)"
    )
    transcribe_parser.add_argument(
        "audio_file",
        help="Path to audio file to transcribe"
    )
    transcribe_parser.add_argument(
        "-o", "--output",
        help="Output file for transcription (default: print to stdout)"
    )
    transcribe_parser.add_argument(
        "-p", "--provider",
        choices=["faster_whisper", "whisper", "google_cloud"],
        default="faster_whisper",
        help="STT provider to use (default: faster_whisper)"
    )
    transcribe_parser.add_argument(
        "--whisper-model",
        default="large-v3",
        help="Whisper model, e.g. tiny, base, small, medium, large-v3, large-v3-turbo (default: large-v3)"
    )
    transcribe_parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Device to run on (default: auto)"
    )
    transcribe_parser.add_argument(
        "-l", "--language",
        help="Language code (e.g., 'en', 'ar', 'en-US')"
    )
    transcribe_parser.add_argument(
        "--google-credentials",
        help="Path to Google Cloud credentials JSON file"
    )
    transcribe_parser.set_defaults(func=transcribe_command)
    
    # Bot command (Telegram bot mode)
    bot_parser = subparsers.add_parser(
        "bot",
        help="Run Telegram bot"
    )
    bot_parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (YAML or JSON)"
    )
    bot_parser.add_argument(
        "-p", "--provider",
        choices=["faster_whisper", "whisper", "google_cloud"],
        help="STT provider to use (overrides config file)"
    )
    bot_parser.add_argument(
        "--whisper-model",
        help="Whisper model, e.g. small, medium, large-v3 (overrides config file)"
    )
    bot_parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        help="Device to run on (overrides config file)"
    )
    bot_parser.set_defaults(func=bot_command)

    # Users command (inspect the user database)
    users_parser = subparsers.add_parser(
        "users",
        help="List the users the bot knows (reads STT_DATA_DIR)"
    )
    users_parser.set_defaults(func=users_command)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Run command
    args.func(args)


if __name__ == "__main__":
    main()


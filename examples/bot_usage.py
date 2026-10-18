"""
Example: Running the Telegram bot programmatically.

This example demonstrates how to run the Telegram bot from Python code.
Configuration is loaded from the .env file in the project root.

Setup:
1. Copy .env.example to .env
2. Add your TELEGRAM_BOT_TOKEN to .env
3. Run this script: python examples/bot_usage.py
"""

import os
import logging
from pathlib import Path
from televoica.core.engine import SpeechToTextEngine
from televoica.core.providers import create_provider
from televoica.bot.telegram_bot import TelegramSTTBot
from televoica.config.settings import load_config


def load_env_file():
    """Load environment variables from .env file if it exists."""
    # Try multiple locations for .env file
    possible_locations = [
        Path.cwd() / ".env",  # Current working directory
        Path(__file__).parent.parent / ".env",  # Project root (relative to this file)
    ]

    for env_file in possible_locations:
        if env_file.exists():
            print(f"Loading environment from {env_file}")
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Parse key=value
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove inline comments (everything after #)
                        if '#' in value:
                            value = value.split('#')[0].strip()

                        # Only set if not already in environment and value is not empty
                        if key and value and key not in os.environ:
                            os.environ[key] = value
            return True

    return False


def run_bot():
    """Run the Telegram bot with configuration from .env file."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # httpx logs every request URL, which contains the bot token
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Load configuration from environment variables (.env file)
    settings = load_config()

    # Ensure bot mode is enabled
    settings.telegram_bot = True

    print("=" * 60)
    print("Televoica Bot Configuration")
    print("=" * 60)
    print(f"Provider: {settings.stt.provider}")
    print(f"Model: {settings.stt.whisper_model}")
    print(f"Device: {settings.stt.whisper_device}")
    print(f"Max file size: {settings.telegram.max_file_size_mb}MB")
    if settings.telegram.allowed_users:
        print(f"Allowed users: {settings.telegram.allowed_users}")
    else:
        print("Allowed users: All users")
    print("=" * 60)
    print()

    # Create STT engine
    provider = create_provider(settings.stt)
    engine = SpeechToTextEngine(provider=provider)

    # Create and run bot
    bot = TelegramSTTBot(settings=settings, engine=engine)

    try:
        print("Starting Telegram bot...")
        print("Press Ctrl+C to stop")
        print()
        bot.run()
    except KeyboardInterrupt:
        print("\n\nBot stopped by user")
        bot.stop()





if __name__ == "__main__":
    print()
    print("=" * 60)
    print("Televoica Telegram Bot")
    print("=" * 60)
    print()

    # Try to load .env file first
    env_loaded = load_env_file()
    print()

    # Check if bot token is set
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("ERROR: TELEGRAM_BOT_TOKEN not found!")
        print()
        print("Setup instructions:")
        print()
        print("1. Copy the example file:")
        print("   cp .env.example .env")
        print()
        print("2. Edit .env and add your bot token:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        print()
        print("3. Get a bot token from @BotFather on Telegram:")
        print("   - Open @BotFather")
        print("   - Send /newbot")
        print("   - Follow instructions")
        print("   - Copy the token")
        print()
        exit(1)

    # Run the bot
    run_bot()


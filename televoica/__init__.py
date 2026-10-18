"""
Televoica: A modular speech-to-text library with optional Telegram bot integration.

This package provides:
1. Core speech-to-text functionality (standalone library)
2. Optional Telegram bot integration for voice message transcription
"""

__version__ = "0.2.0"
__author__ = "Mahmoud-Emad"

from televoica.core.engine import SpeechToTextEngine
from televoica.core.providers import (
    STTProvider,
    WhisperProvider,
    FasterWhisperProvider,
)

__all__ = [
    "SpeechToTextEngine",
    "STTProvider",
    "WhisperProvider",
    "FasterWhisperProvider",
]


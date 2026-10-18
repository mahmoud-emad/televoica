"""
Core speech-to-text functionality.

This module provides the core STT engine that can be used independently
of the Telegram bot integration.
"""

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


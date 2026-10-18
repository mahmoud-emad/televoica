"""
Core speech-to-text engine.

This module provides the main SpeechToTextEngine class that orchestrates
the transcription process using different STT providers.
"""

from pathlib import Path
from typing import Optional, Union
import logging

from televoica.core.providers import STTProvider, FasterWhisperProvider

logger = logging.getLogger(__name__)


class SpeechToTextEngine:
    """
    Main speech-to-text engine that can be used as a standalone library.
    
    This class provides a high-level interface for speech-to-text conversion
    and can work with different STT providers.
    """

    def __init__(self, provider: Optional[STTProvider] = None):
        """
        Initialize the speech-to-text engine.

        Args:
            provider: STT provider to use. If None, uses FasterWhisperProvider with default settings.
        """
        self.provider = provider or FasterWhisperProvider()
        logger.info(f"SpeechToTextEngine initialized with {self.provider.__class__.__name__}")

    def transcribe_file(self, audio_file: Union[str, Path]) -> str:
        """
        Transcribe an audio file to text.

        Args:
            audio_file: Path to the audio file

        Returns:
            Transcribed text

        Raises:
            FileNotFoundError: If the audio file doesn't exist
            Exception: If transcription fails
        """
        audio_path = Path(audio_file)
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        logger.info(f"Transcribing file: {audio_path}")
        return self.provider.transcribe(audio_path)

    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Audio data as bytes
            format: Audio format (e.g., 'ogg', 'mp3', 'wav')

        Returns:
            Transcribed text

        Raises:
            Exception: If transcription fails
        """
        logger.info(f"Transcribing audio bytes ({len(audio_bytes)} bytes, format: {format})")
        return self.provider.transcribe_bytes(audio_bytes, format)

    def set_provider(self, provider: STTProvider):
        """
        Change the STT provider.

        Args:
            provider: New STT provider to use
        """
        self.provider = provider
        logger.info(f"Provider changed to {provider.__class__.__name__}")


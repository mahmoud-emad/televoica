"""Tests for the SpeechToTextEngine."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from televoica.core.engine import SpeechToTextEngine
from televoica.core.providers import STTProvider


class MockProvider(STTProvider):
    """Mock STT provider for testing."""
    
    def transcribe(self, audio_file: Path) -> str:
        return f"Mock transcription of {audio_file.name}"
    
    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        return f"Mock transcription of {len(audio_bytes)} bytes"


class TestSpeechToTextEngine:
    """Test cases for SpeechToTextEngine."""
    
    def test_init_with_default_provider(self):
        """Test initialization with default provider."""
        with patch('televoica.core.engine.FasterWhisperProvider'):
            engine = SpeechToTextEngine()
            assert engine.provider is not None
    
    def test_init_with_custom_provider(self):
        """Test initialization with custom provider."""
        provider = MockProvider()
        engine = SpeechToTextEngine(provider=provider)
        assert engine.provider == provider
    
    def test_transcribe_file_success(self, tmp_path):
        """Test successful file transcription."""
        # Create a temporary audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_text("fake audio data")
        
        # Create engine with mock provider
        provider = MockProvider()
        engine = SpeechToTextEngine(provider=provider)
        
        # Transcribe
        result = engine.transcribe_file(audio_file)
        
        assert result == f"Mock transcription of {audio_file.name}"
    
    def test_transcribe_file_not_found(self):
        """Test transcription with non-existent file."""
        provider = MockProvider()
        engine = SpeechToTextEngine(provider=provider)
        
        with pytest.raises(FileNotFoundError):
            engine.transcribe_file("nonexistent.mp3")
    
    def test_transcribe_bytes(self):
        """Test transcription from bytes."""
        provider = MockProvider()
        engine = SpeechToTextEngine(provider=provider)
        
        audio_bytes = b"fake audio data"
        result = engine.transcribe_bytes(audio_bytes, format="mp3")
        
        assert result == f"Mock transcription of {len(audio_bytes)} bytes"
    
    def test_set_provider(self):
        """Test changing the provider."""
        provider1 = MockProvider()
        provider2 = MockProvider()
        
        engine = SpeechToTextEngine(provider=provider1)
        assert engine.provider == provider1
        
        engine.set_provider(provider2)
        assert engine.provider == provider2
    
    def test_transcribe_file_with_string_path(self, tmp_path):
        """Test transcription with string path instead of Path object."""
        audio_file = tmp_path / "test.mp3"
        audio_file.write_text("fake audio data")
        
        provider = MockProvider()
        engine = SpeechToTextEngine(provider=provider)
        
        # Pass string path
        result = engine.transcribe_file(str(audio_file))
        
        assert result == f"Mock transcription of {audio_file.name}"


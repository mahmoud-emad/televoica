"""Tests for STT providers."""

import sys

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from televoica.core.providers import (
    STTProvider,
    WhisperProvider,
    FasterWhisperProvider,
    GoogleCloudSTTProvider,
)


class TestSTTProvider:
    """Test cases for the abstract STTProvider."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Test that STTProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            STTProvider()


class TestWhisperProvider:
    """Test cases for WhisperProvider."""
    
    def test_init_with_defaults(self):
        """Test initialization with default configuration."""
        provider = WhisperProvider()
        
        assert provider.model_size == "base"
        assert provider.device == "cpu"
        assert provider.language is None
    
    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        config = {
            "model": "medium",
            "device": "cuda",
            "language": "en",
        }
        provider = WhisperProvider(config)
        
        assert provider.model_size == "medium"
        assert provider.device == "cuda"
        assert provider.language == "en"
    
    @patch.dict(sys.modules, {"whisper": MagicMock()})
    def test_load_model(self):
        mock_load_model = sys.modules["whisper"].load_model
        """Test lazy loading of Whisper model."""
        mock_model = MagicMock()
        mock_load_model.return_value = mock_model

        provider = WhisperProvider({"model": "base"})
        assert provider._model is None

        provider._load_model()

        assert provider._model == mock_model
        mock_load_model.assert_called_once_with("base", device="cpu")

    @patch.dict(sys.modules, {"whisper": MagicMock()})
    def test_transcribe(self, tmp_path):
        mock_load_model = sys.modules["whisper"].load_model
        """Test transcription of audio file."""
        # Setup mock
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  Test transcription  "}
        mock_load_model.return_value = mock_model

        # Create temporary audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_text("fake audio")

        # Transcribe
        provider = WhisperProvider()
        result = provider.transcribe(audio_file)

        assert result == "Test transcription"
        mock_model.transcribe.assert_called_once()

    @patch.dict(sys.modules, {"whisper": MagicMock()})
    def test_transcribe_bytes(self, tmp_path):
        mock_load_model = sys.modules["whisper"].load_model
        """Test transcription of audio bytes."""
        # Setup mock
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "Test transcription"}
        mock_load_model.return_value = mock_model

        # Transcribe bytes
        provider = WhisperProvider()
        audio_bytes = b"fake audio data"
        result = provider.transcribe_bytes(audio_bytes, format="ogg")

        assert result == "Test transcription"


class TestGoogleCloudSTTProvider:
    """Test cases for GoogleCloudSTTProvider."""
    
    def test_init_with_defaults(self):
        """Test initialization with default configuration."""
        provider = GoogleCloudSTTProvider()
        
        assert provider.credentials_path is None
        assert provider.language_code == "en-US"
    
    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        config = {
            "credentials_path": "/path/to/creds.json",
            "language_code": "ar-SA",
        }
        provider = GoogleCloudSTTProvider(config)
        
        assert provider.credentials_path == "/path/to/creds.json"
        assert provider.language_code == "ar-SA"
    
    @patch('televoica.core.providers.GoogleCloudSTTProvider._load_client')
    def test_load_client(self, mock_load_client):
        """Test lazy loading of Google Cloud client."""
        # Create a mock client
        mock_client = MagicMock()

        # Setup the provider
        provider = GoogleCloudSTTProvider()
        provider._client = None

        # Manually set the client to simulate loading
        def set_client():
            provider._client = mock_client

        mock_load_client.side_effect = set_client

        # Call load_client
        provider._load_client()

        # Verify client was set
        assert provider._client == mock_client
        mock_load_client.assert_called_once()



class TestFasterWhisperProvider:
    """Test cases for FasterWhisperProvider."""

    def test_defaults(self):
        """Defaults favor accuracy: large-v3, beam search, VAD."""
        provider = FasterWhisperProvider()
        assert provider.model_size == "large-v3"
        assert provider.device == "auto"
        assert provider.beam_size == 5
        assert provider.vad_filter is True
        assert provider.language is None

    def test_transcribe_passes_accuracy_options(self, tmp_path):
        """Language, prompt, beam search and VAD reach the model; segments are joined."""
        provider = FasterWhisperProvider(
            {"language": "ar", "initial_prompt": "Televoica", "beam_size": 7}
        )
        model = Mock()
        info = Mock(language="ar", language_probability=0.99)
        model.transcribe.return_value = (
            iter([Mock(text=" hello "), Mock(text="world ")]),
            info,
        )
        provider._model = model

        audio = tmp_path / "a.ogg"
        audio.write_bytes(b"x")

        assert provider.transcribe(audio) == "hello world"
        kwargs = model.transcribe.call_args.kwargs
        assert kwargs["language"] == "ar"
        assert kwargs["initial_prompt"] == "Televoica"
        assert kwargs["beam_size"] == 7
        assert kwargs["vad_filter"] is True
        assert kwargs["condition_on_previous_text"] is False


class TestCreateProvider:
    """create_provider maps settings to the right provider class."""

    def test_default_settings_give_faster_whisper_large_v3(self):
        from televoica.config.settings import STTConfig
        from televoica.core.providers import create_provider

        provider = create_provider(STTConfig())
        assert isinstance(provider, FasterWhisperProvider)
        assert provider.model_size == "large-v3"

    def test_legacy_and_unknown_providers(self):
        from televoica.config.settings import STTConfig
        from televoica.core.providers import create_provider

        assert isinstance(create_provider(STTConfig(provider="whisper")), WhisperProvider)
        with pytest.raises(ValueError):
            create_provider(STTConfig(provider="nope"))

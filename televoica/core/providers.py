"""
Speech-to-text provider implementations.

This module contains different STT provider implementations that can be used
with the SpeechToTextEngine.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the STT provider.

        Args:
            config: Optional configuration dictionary for the provider
        """
        self.config = config or {}

    @abstractmethod
    def transcribe(self, audio_file: Path) -> str:
        """
        Transcribe audio file to text.

        Args:
            audio_file: Path to the audio file

        Returns:
            Transcribed text

        Raises:
            Exception: If transcription fails
        """
        pass

    @abstractmethod
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
        pass


class WhisperProvider(STTProvider):
    """OpenAI Whisper-based speech-to-text provider."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Whisper provider.

        Args:
            config: Configuration dictionary with optional keys:
                - model: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
                - device: Device to run on ('cpu', 'cuda')
                - language: Language code (e.g., 'en', 'ar')
        """
        super().__init__(config)
        self.model_size = self.config.get("model", "base")
        self.device = self.config.get("device", "cpu")
        self.language = self.config.get("language", None)
        self._model = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            try:
                import whisper
                logger.info(f"Loading Whisper model: {self.model_size}")
                self._model = whisper.load_model(self.model_size, device=self.device)
                logger.info("Whisper model loaded successfully")
            except ImportError:
                raise ImportError(
                    "openai-whisper is not installed. "
                    "Install it with: pip install openai-whisper"
                )

    def transcribe(self, audio_file: Path) -> str:
        """
        Transcribe audio file using Whisper.

        Args:
            audio_file: Path to the audio file

        Returns:
            Transcribed text
        """
        self._load_model()
        
        logger.info(f"Transcribing audio file: {audio_file}")
        
        try:
            result = self._model.transcribe(
                str(audio_file),
                language=self.language,
                fp16=False  # Use FP32 for CPU compatibility
            )
            text = result["text"].strip()
            logger.info(f"Transcription successful: {len(text)} characters")
            return text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """
        Transcribe audio bytes using Whisper.

        Args:
            audio_bytes: Audio data as bytes
            format: Audio format

        Returns:
            Transcribed text
        """
        import tempfile
        
        # Save bytes to temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = Path(temp_file.name)
        
        try:
            return self.transcribe(temp_path)
        finally:
            # Clean up temporary file
            temp_path.unlink(missing_ok=True)


class FasterWhisperProvider(STTProvider):
    """faster-whisper (CTranslate2) provider tuned for accuracy.

    Runs Whisper large-v3 by default with beam search, voice-activity
    detection and temperature fallback, which removes most silence
    hallucinations and repetition loops of the plain openai-whisper call.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize faster-whisper provider.

        Args:
            config: Configuration dictionary with optional keys:
                - model: Model name or path ('large-v3', 'large-v3-turbo', 'medium', ...)
                - device: 'auto', 'cpu' or 'cuda'
                - compute_type: 'auto', 'int8', 'float16', ... ('auto' picks per device)
                - language: Language code (e.g., 'en', 'ar'); None to auto-detect
                - initial_prompt: Text biasing spelling/vocabulary of the transcript
                - beam_size: Beam search width (default 5)
                - vad_filter: Skip non-speech with Silero VAD (default True)
        """
        super().__init__(config)
        self.model_size = self.config.get("model") or "large-v3"
        self.device = self.config.get("device") or "auto"
        self.compute_type = self.config.get("compute_type") or "auto"
        self.language = self.config.get("language") or None
        self.initial_prompt = self.config.get("initial_prompt") or None
        self.beam_size = int(self.config.get("beam_size") or 5)
        self.vad_filter = self.config.get("vad_filter", True)
        self._model = None

    def _load_model(self):
        """Lazy load the faster-whisper model."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise ImportError(
                    "faster-whisper is not installed. "
                    "Install it with: pip install faster-whisper"
                )
            device = self.device
            compute_type = self.compute_type
            if compute_type == "auto":
                compute_type = "float16" if device == "cuda" else "int8"
            logger.info(
                f"Loading faster-whisper model: {self.model_size} "
                f"(device={device}, compute_type={compute_type})"
            )
            self._model = WhisperModel(
                self.model_size, device=device, compute_type=compute_type
            )
            logger.info("faster-whisper model loaded successfully")

    def transcribe(self, audio_file: Path) -> str:
        """
        Transcribe audio file using faster-whisper.

        Args:
            audio_file: Path to the audio file

        Returns:
            Transcribed text
        """
        self._load_model()

        logger.info(f"Transcribing audio file: {audio_file}")

        try:
            segments, info = self._model.transcribe(
                str(audio_file),
                language=self.language,
                task="transcribe",
                beam_size=self.beam_size,
                best_of=self.beam_size,
                temperature=[0.0, 0.2, 0.4, 0.6],
                condition_on_previous_text=False,
                initial_prompt=self.initial_prompt,
                vad_filter=self.vad_filter,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            # `segments` is a lazy generator; consuming it runs the decoding.
            text = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info(
                f"Transcription successful: {len(text)} characters "
                f"(language={info.language}, p={info.language_probability:.2f})"
            )
            return text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """
        Transcribe audio bytes using faster-whisper.

        Args:
            audio_bytes: Audio data as bytes
            format: Audio format

        Returns:
            Transcribed text
        """
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = Path(temp_file.name)

        try:
            return self.transcribe(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)


class GoogleCloudSTTProvider(STTProvider):
    """Google Cloud Televoica provider."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Google Cloud STT provider.

        Args:
            config: Configuration dictionary with optional keys:
                - credentials_path: Path to Google Cloud credentials JSON
                - language_code: Language code (e.g., 'en-US', 'ar-SA')
        """
        super().__init__(config)
        self.credentials_path = self.config.get("credentials_path")
        self.language_code = self.config.get("language_code", "en-US")
        self._client = None

    def _load_client(self):
        """Lazy load the Google Cloud Speech client."""
        if self._client is None:
            try:
                from google.cloud import speech
                import os
                
                if self.credentials_path:
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
                
                self._client = speech.SpeechClient()
                logger.info("Google Cloud Speech client initialized")
            except ImportError:
                raise ImportError(
                    "google-cloud-speech is not installed. "
                    "Install it with: pip install google-cloud-speech"
                )

    def transcribe(self, audio_file: Path) -> str:
        """
        Transcribe audio file using Google Cloud Televoica.

        Args:
            audio_file: Path to the audio file

        Returns:
            Transcribed text
        """
        with open(audio_file, "rb") as f:
            audio_bytes = f.read()
        
        return self.transcribe_bytes(audio_bytes)

    def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """
        Transcribe audio bytes using Google Cloud Televoica.

        Args:
            audio_bytes: Audio data as bytes
            format: Audio format

        Returns:
            Transcribed text
        """
        self._load_client()
        
        from google.cloud import speech
        
        # Map format to Google Cloud encoding
        encoding_map = {
            "ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            "mp3": speech.RecognitionConfig.AudioEncoding.MP3,
            "wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        }
        
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=encoding_map.get(format, speech.RecognitionConfig.AudioEncoding.OGG_OPUS),
            language_code=self.language_code,
        )
        
        logger.info("Sending audio to Google Cloud Televoica")
        response = self._client.recognize(config=config, audio=audio)
        
        # Combine all transcription results
        transcripts = [result.alternatives[0].transcript for result in response.results]
        text = " ".join(transcripts).strip()
        
        logger.info(f"Transcription successful: {len(text)} characters")
        return text


"""Tests for configuration management."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch

from televoica.config.settings import (
    Settings,
    TelegramConfig,
    load_config,
    _load_from_env,
)


class TestSettings:
    """Test cases for Settings dataclass."""
    
    def test_default_settings(self):
        """Test default settings initialization."""
        settings = Settings()
        
        assert settings.telegram_bot is False
        assert settings.stt.provider == "faster_whisper"
        assert settings.telegram.enabled is False
        assert settings.log_level == "INFO"
    
    def test_telegram_bot_enables_telegram(self):
        """Test that telegram_bot=True enables telegram."""
        settings = Settings(
            telegram_bot=True,
            telegram=TelegramConfig(bot_token="test_token")
        )
        
        assert settings.telegram.enabled is True
    
    def test_telegram_bot_requires_token(self):
        """Test that telegram_bot=True requires a bot token."""
        with pytest.raises(ValueError, match="Telegram bot token is required"):
            Settings(telegram_bot=True)
    
    def test_temp_dir_creation(self, tmp_path):
        """Test that temp directory is created."""
        temp_dir = tmp_path / "test_temp"
        settings = Settings(temp_dir=temp_dir)
        
        assert settings.temp_dir.exists()
        assert settings.temp_dir.is_dir()


class TestLoadFromEnv:
    """Test cases for loading configuration from environment variables."""
    
    def test_load_telegram_bot_mode(self):
        """Test loading telegram_bot mode from env."""
        with patch.dict(os.environ, {"STT_TELEGRAM_BOT": "true"}):
            config = _load_from_env()
            assert config["telegram_bot"] is True
        
        with patch.dict(os.environ, {"STT_TELEGRAM_BOT": "false"}):
            config = _load_from_env()
            assert config["telegram_bot"] is False
    
    def test_load_provider(self):
        """Test loading STT provider from env."""
        with patch.dict(os.environ, {"STT_PROVIDER": "google_cloud"}):
            config = _load_from_env()
            assert config["stt_provider"] == "google_cloud"
    
    def test_load_whisper_settings(self):
        """Test loading Whisper settings from env."""
        env_vars = {
            "STT_WHISPER_MODEL": "large",
            "STT_WHISPER_DEVICE": "cuda",
            "STT_WHISPER_LANGUAGE": "en",
        }
        
        with patch.dict(os.environ, env_vars):
            config = _load_from_env()
            assert config["whisper_model"] == "large"
            assert config["whisper_device"] == "cuda"
            assert config["whisper_language"] == "en"
    
    def test_load_telegram_settings(self):
        """Test loading Telegram settings from env."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_ALLOWED_USERS": "123,456,789",
            "TELEGRAM_MAX_FILE_SIZE_MB": "50",
        }
        
        with patch.dict(os.environ, env_vars):
            config = _load_from_env()
            assert config["telegram_bot_token"] == "test_token"
            assert config["telegram_allowed_users"] == [123, 456, 789]
            assert config["telegram_max_file_size_mb"] == 50
    
    def test_load_log_level(self):
        """Test loading log level from env."""
        with patch.dict(os.environ, {"STT_LOG_LEVEL": "DEBUG"}):
            config = _load_from_env()
            assert config["log_level"] == "DEBUG"


class TestLoadConfig:
    """Test cases for load_config function."""
    
    def test_load_config_from_env(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "STT_PROVIDER": "whisper",
            "STT_WHISPER_MODEL": "medium",
            "STT_LOG_LEVEL": "DEBUG",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = load_config()
            
            assert settings.stt.provider == "whisper"
            assert settings.stt.whisper_model == "medium"
            assert settings.log_level == "DEBUG"
    
    def test_load_config_defaults(self):
        """Test loading configuration with defaults."""
        with patch.dict(os.environ, {}, clear=True):
            settings = load_config()
            
            assert settings.telegram_bot is False
            assert settings.stt.provider == "faster_whisper"
            assert settings.stt.whisper_model == "large-v3"
            assert settings.log_level == "INFO"



class TestReleaseAnnouncementSettings:
    """Settings for persistent state and release announcements."""

    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_config()
        assert settings.telegram.announce_releases is True
        assert settings.telegram.repo_url.endswith("/televoica")
        assert settings.data_dir.name == ".televoica"

    def test_env_overrides(self, tmp_path):
        env = {
            "STT_DATA_DIR": str(tmp_path),
            "STT_ANNOUNCE_RELEASES": "false",
            "STT_REPO_URL": "https://example.com/r",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_config()
        assert settings.data_dir == tmp_path
        assert settings.telegram.announce_releases is False
        assert settings.telegram.repo_url == "https://example.com/r"

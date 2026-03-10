from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_settings import CliApp

from ffsubsync_batch.config import Config


class TestConfigFromEnv:
    def test_required_fields_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONARR_URL", "http://sonarr:8989")
        monkeypatch.setenv("SONARR_API_KEY", "abc123")
        config = CliApp.run(Config, cli_args=[])
        assert config.sonarr_url == "http://sonarr:8989"
        assert config.sonarr_api_key == "abc123"

    def test_defaults_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONARR_URL", "http://localhost:8989")
        monkeypatch.setenv("SONARR_API_KEY", "key")
        config = CliApp.run(Config, cli_args=[])
        assert config.max_offset == 120
        assert config.dry_run is False
        assert config.backup_dir_name == ".original-sub"
        assert config.reference_stream == "a:0"
        assert config.vad == "subs_then_webrtc"
        assert config.sub_extensions == ["srt"]
        assert config.workers == 2

    def test_env_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONARR_URL", "http://example.com")
        monkeypatch.setenv("SONARR_API_KEY", "key")
        monkeypatch.setenv("MAX_OFFSET", "300")
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setenv("WORKERS", "8")
        config = CliApp.run(Config, cli_args=[])
        assert config.max_offset == 300
        assert config.dry_run is True
        assert config.workers == 8

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            CliApp.run(Config, cli_args=[])


class TestConfigFromCLI:
    def test_cli_args_override_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SONARR_URL", "http://from-env:8989")
        monkeypatch.setenv("SONARR_API_KEY", "env-key")
        config = CliApp.run(Config, cli_args=["--sonarr_url", "http://from-cli:8989"])
        assert config.sonarr_url == "http://from-cli:8989"
        assert config.sonarr_api_key == "env-key"

    def test_all_cli_args(self) -> None:
        config = CliApp.run(
            Config,
            cli_args=[
                "--sonarr_url",
                "http://cli:8989",
                "--sonarr_api_key",
                "cli-key",
                "--max_offset",
                "60",
                "--dry_run",
                "true",
                "--workers",
                "4",
                "--series_filter",
                "Friends",
                "--vad",
                "webrtc",
            ],
        )
        assert config.sonarr_url == "http://cli:8989"
        assert config.sonarr_api_key == "cli-key"
        assert config.max_offset == 60
        assert config.dry_run is True
        assert config.workers == 4
        assert config.series_filter == "Friends"
        assert config.vad == "webrtc"

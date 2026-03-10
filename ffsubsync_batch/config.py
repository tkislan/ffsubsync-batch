from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """All configuration, sourced from environment variables and/or CLI arguments."""

    sonarr_url: str = Field(description="Sonarr base URL, e.g. http://sonarr:8989")
    sonarr_api_key: str = Field(description="Sonarr API key")
    series_filter: str = Field(
        default="",
        description="Optional substring filter on series title (case-insensitive)",
    )
    log_file: str = Field(default="/tmp/ffsubsync-batch.log")
    max_offset: int = Field(default=120, description="Max offset in seconds for ffsubsync")
    dry_run: bool = Field(default=False)
    backup_dir_name: str = Field(
        default=".original-sub", description="Hidden backup directory name"
    )
    reference_stream: str = Field(
        default="a:0",
        description="Audio stream to use as reference (e.g. a:0 for first audio track)",
    )
    vad: str = Field(
        default="subs_then_webrtc",
        description="VAD engine: subs_then_webrtc, webrtc, subs_then_auditok, auditok",
    )
    sub_extensions: list[str] = Field(
        default=["srt"],
        description="Subtitle extensions to look for",
    )
    workers: int = Field(
        default=2,
        description="Number of parallel ffsubsync workers",
    )

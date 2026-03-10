from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def logger() -> logging.Logger:
    """A silent logger that won't pollute test output."""
    log = logging.getLogger("test_sync_subtitles")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture
def media_tree(tmp_path: Path) -> dict[str, Any]:
    """
    Create a realistic media directory structure:
      tmp_path/
        Series A/
          Season 01/
            Series A - S01E01.mkv     (dummy video)
            Series A - S01E01.srt     (subtitle)
            Series A - S01E01.eng.srt (second subtitle)
            Series A - S01E02.mkv
            Series A - S01E02.srt
        Series B/
          Season 01/
            Series B - S01E01.mkv
            Series B - S01E01.srt
    """
    series_a = tmp_path / "Series A" / "Season 01"
    series_a.mkdir(parents=True)

    vid_a1 = series_a / "Series A - S01E01.mkv"
    vid_a1.write_bytes(b"\x00" * 100)
    srt_a1 = series_a / "Series A - S01E01.srt"
    srt_a1.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n")
    srt_a1_eng = series_a / "Series A - S01E01.eng.srt"
    srt_a1_eng.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello English\n")

    vid_a2 = series_a / "Series A - S01E02.mkv"
    vid_a2.write_bytes(b"\x00" * 100)
    srt_a2 = series_a / "Series A - S01E02.srt"
    srt_a2.write_text("1\n00:00:02,000 --> 00:00:04,000\nWorld\n")

    series_b = tmp_path / "Series B" / "Season 01"
    series_b.mkdir(parents=True)

    vid_b1 = series_b / "Series B - S01E01.mkv"
    vid_b1.write_bytes(b"\x00" * 100)
    srt_b1 = series_b / "Series B - S01E01.srt"
    srt_b1.write_text("1\n00:00:05,000 --> 00:00:07,000\nBye\n")

    return {
        "root": tmp_path,
        "series_a_dir": tmp_path / "Series A",
        "series_b_dir": tmp_path / "Series B",
        "vid_a1": vid_a1,
        "srt_a1": srt_a1,
        "srt_a1_eng": srt_a1_eng,
        "vid_a2": vid_a2,
        "srt_a2": srt_a2,
        "vid_b1": vid_b1,
        "srt_b1": srt_b1,
    }


def make_sonarr_series_json(series_id: int, title: str, path: str) -> dict[str, Any]:
    """Build a realistic Sonarr series API response dict."""
    return {
        "id": series_id,
        "title": title,
        "path": path,
        "sortTitle": title.lower(),
        "status": "continuing",
        "seasonCount": 1,
        "episodeFileCount": 1,
        "monitored": True,
        "seasons": [{"seasonNumber": 1, "monitored": True}],
    }


def make_sonarr_episode_file_json(
    file_id: int,
    series_id: int,
    season_number: int,
    path: str,
    relative_path: str,
) -> dict[str, Any]:
    """Build a realistic Sonarr episode file API response dict."""
    return {
        "id": file_id,
        "seriesId": series_id,
        "seasonNumber": season_number,
        "relativePath": relative_path,
        "path": path,
        "size": 100,
        "dateAdded": "2024-01-01T00:00:00Z",
        "sceneName": "",
        "releaseGroup": "",
        "quality": {
            "quality": {"id": 1, "name": "HDTV-720p"},
            "revision": {"version": 1, "real": 0},
        },
    }

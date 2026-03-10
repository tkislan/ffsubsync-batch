from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ffsubsync_batch.subtitles import (
    backup_subtitle,
    find_subtitles,
    next_backup_path,
    restore_backup,
)


class TestFindSubtitles:
    def test_finds_exact_stem_match(self, media_tree: dict[str, Any]) -> None:
        subs = find_subtitles(media_tree["vid_a1"], ["srt"])
        names = [s.name for s in subs]
        assert "Series A - S01E01.srt" in names

    def test_finds_dot_suffixed_match(self, media_tree: dict[str, Any]) -> None:
        subs = find_subtitles(media_tree["vid_a1"], ["srt"])
        names = [s.name for s in subs]
        assert "Series A - S01E01.eng.srt" in names

    def test_returns_sorted(self, media_tree: dict[str, Any]) -> None:
        subs = find_subtitles(media_tree["vid_a1"], ["srt"])
        assert subs == sorted(subs)

    def test_does_not_match_other_episodes(self, media_tree: dict[str, Any]) -> None:
        subs = find_subtitles(media_tree["vid_a2"], ["srt"])
        names = [s.name for s in subs]
        assert "Series A - S01E01.srt" not in names
        assert "Series A - S01E02.srt" in names

    def test_filters_by_extension(self, media_tree: dict[str, Any]) -> None:
        subs = find_subtitles(media_tree["vid_a1"], ["ass"])
        assert subs == []

    def test_multiple_extensions(self, tmp_path: Path) -> None:
        vid = tmp_path / "show.mkv"
        vid.write_bytes(b"\x00")
        (tmp_path / "show.srt").write_text("sub")
        (tmp_path / "show.ass").write_text("sub")
        (tmp_path / "show.txt").write_text("not a sub")

        subs = find_subtitles(vid, ["srt", "ass"])
        names = [s.name for s in subs]
        assert "show.srt" in names
        assert "show.ass" in names
        assert "show.txt" not in names

    def test_empty_directory(self, tmp_path: Path) -> None:
        vid = tmp_path / "video.mkv"
        vid.write_bytes(b"\x00")
        assert find_subtitles(vid, ["srt"]) == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        vid = tmp_path / "nonexistent_dir" / "video.mkv"
        assert find_subtitles(vid, ["srt"]) == []


class TestNextBackupPath:
    def test_first_backup(self, tmp_path: Path) -> None:
        path = next_backup_path(tmp_path, "show.srt")
        assert path == tmp_path / "show.srt.backup.001"

    def test_increments_when_exists(self, tmp_path: Path) -> None:
        (tmp_path / "show.srt.backup.001").write_text("old")
        path = next_backup_path(tmp_path, "show.srt")
        assert path == tmp_path / "show.srt.backup.002"

    def test_skips_gaps(self, tmp_path: Path) -> None:
        (tmp_path / "show.srt.backup.001").write_text("old")
        (tmp_path / "show.srt.backup.002").write_text("old")
        path = next_backup_path(tmp_path, "show.srt")
        assert path == tmp_path / "show.srt.backup.003"


class TestBackupSubtitle:
    def test_creates_backup(self, tmp_path: Path, logger: logging.Logger) -> None:
        srt = tmp_path / "episode.srt"
        srt.write_text("original content")
        backup_dir = tmp_path / ".backup"

        result = backup_subtitle(srt, backup_dir, logger)
        assert result is not None
        assert result.exists()
        assert result.read_text() == "original content"

    def test_creates_backup_dir(self, tmp_path: Path, logger: logging.Logger) -> None:
        srt = tmp_path / "episode.srt"
        srt.write_text("content")
        backup_dir = tmp_path / "nested" / "backup"

        backup_subtitle(srt, backup_dir, logger)
        assert backup_dir.is_dir()

    def test_increments_on_repeated_backup(self, tmp_path: Path, logger: logging.Logger) -> None:
        srt = tmp_path / "episode.srt"
        srt.write_text("v1")
        backup_dir = tmp_path / ".backup"

        b1 = backup_subtitle(srt, backup_dir, logger)
        srt.write_text("v2")
        b2 = backup_subtitle(srt, backup_dir, logger)

        assert b1 is not None and b2 is not None
        assert b1 != b2
        assert b1.read_text() == "v1"
        assert b2.read_text() == "v2"

    def test_preserves_original(self, tmp_path: Path, logger: logging.Logger) -> None:
        srt = tmp_path / "episode.srt"
        srt.write_text("original")
        backup_dir = tmp_path / ".backup"

        backup_subtitle(srt, backup_dir, logger)
        assert srt.read_text() == "original"


class TestRestoreBackup:
    def test_restores_content(self, tmp_path: Path, logger: logging.Logger) -> None:
        backup = tmp_path / "backup.srt"
        backup.write_text("original content")
        srt = tmp_path / "episode.srt"
        srt.write_text("corrupted")

        restore_backup(backup, srt, logger)
        assert srt.read_text() == "original content"

    def test_restore_when_original_missing(self, tmp_path: Path, logger: logging.Logger) -> None:
        backup = tmp_path / "backup.srt"
        backup.write_text("saved")
        srt = tmp_path / "episode.srt"

        restore_backup(backup, srt, logger)
        assert srt.read_text() == "saved"

    def test_restore_from_missing_backup_logs_error(
        self, tmp_path: Path, logger: logging.Logger
    ) -> None:
        backup = tmp_path / "nonexistent.srt"
        srt = tmp_path / "episode.srt"
        srt.write_text("current")

        restore_backup(backup, srt, logger)
        assert srt.read_text() == "current"

from __future__ import annotations

import logging
import shutil
from pathlib import Path


def next_backup_path(backup_dir: Path, srt_name: str) -> Path:
    """
    Return the next available backup path with auto-incrementing suffix.
    e.g. .original-sub/Show - S01E01.eng.srt.backup.001
    """
    counter = 1
    while True:
        candidate = backup_dir / f"{srt_name}.backup.{counter:03d}"
        if not candidate.exists():
            return candidate
        counter += 1


def backup_subtitle(srt_path: Path, backup_dir: Path, logger: logging.Logger) -> Path | None:
    """
    Back up a subtitle file into the backup directory.
    Returns the backup path on success, None on failure.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = next_backup_path(backup_dir, srt_path.name)
    logger.info("    Backing up to: %s/%s", backup_dir.name, backup_path.name)

    try:
        shutil.copy2(str(srt_path), str(backup_path))
        return backup_path
    except OSError as e:
        logger.error("    Failed to create backup: %s", e)
        return None


def find_subtitles(episode_path: Path, sub_extensions: list[str]) -> list[Path]:
    """
    Find all subtitle files matching the video's basename prefix.
    For a video named 'Show - S01E01.mkv', matches 'Show - S01E01.*.srt',
    'Show - S01E01.srt', etc.
    """
    ep_dir = episode_path.parent
    ep_stem = episode_path.stem

    results: list[Path] = []
    try:
        for item in ep_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lstrip(".").lower() not in sub_extensions:
                continue
            item_stem = item.stem
            if item_stem == ep_stem or item_stem.startswith(ep_stem + "."):
                results.append(item)
    except OSError:
        pass

    return sorted(results)


def restore_backup(backup_path: Path, srt_path: Path, logger: logging.Logger) -> None:
    """Restore a subtitle from its backup."""
    logger.info("    Restoring from backup...")
    try:
        shutil.copy2(str(backup_path), str(srt_path))
        logger.info("    Restored successfully")
    except OSError as e:
        logger.error("    RESTORE FAILED (%s) — original preserved at: %s", e, backup_path)

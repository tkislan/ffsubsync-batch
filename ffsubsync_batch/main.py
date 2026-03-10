import logging
import sys
from pathlib import Path

import requests
from pydantic_settings import CliApp

from ffsubsync_batch.config import Config
from ffsubsync_batch.logging import setup_logging
from ffsubsync_batch.sonarr import SonarrAPIError, SonarrClient
from ffsubsync_batch.subtitles import backup_subtitle, find_subtitles, next_backup_path
from ffsubsync_batch.sync import (
    PendingSyncTask,
    SyncJob,
    SyncJobResult,
    run_sync_parallel,
    worker_run_sync,
)
from ffsubsync_batch.toolcheck import check_ffmpeg, check_ffsubsync


def worker_run_sync_dry_run(job: SyncJob) -> SyncJobResult:
    logger = logging.getLogger("sync_subtitles_dry_run")
    logger.info(
        "    DRY RUN: would sync %s against %s into %s",
        job.subtitle_path,
        job.video_path,
        job.output_path,
    )
    return SyncJobResult(video_path=job.video_path, subtitle_path=job.subtitle_path, success=True)


def collect_sync_tasks(
    client: SonarrClient,
    config: Config,
    logger: logging.Logger,
) -> list[PendingSyncTask]:
    """
    Walk all series via Sonarr API, discover subtitle files on the filesystem,
    back them up, and return a list of tasks ready for parallel sync.
    """
    try:
        all_series = client.get_series()
    except SonarrAPIError as e:
        logger.error("Failed to fetch series from Sonarr: %s", e)
        return []
    except requests.ConnectionError as e:
        logger.error("Cannot connect to Sonarr at %s: %s", config.sonarr_url, e)
        return []

    logger.info("Found %d series in Sonarr", len(all_series))

    filter_lower = config.series_filter.lower()
    all_series = [s for s in all_series if filter_lower in s.title.lower()]
    logger.info("After filter '%s': %d series", config.series_filter, len(all_series))

    if len(all_series) > 1:
        logger.error(
            "Filter '%s' matched %d series (expected exactly 1). Matching series:",
            config.series_filter,
            len(all_series),
        )
        for s in sorted(all_series, key=lambda s: s.title.lower()):
            logger.error("  - %s", s.title)
        return []

    all_series.sort(key=lambda s: s.sort_title or s.title.lower())

    try:
        series = all_series.pop()
    except IndexError:
        logger.error("No series matched filter '%s'.", config.series_filter)
        return []

    tasks: list[PendingSyncTask] = []

    logger.info("────────────────────────────────────────────────────")
    logger.info("Processing series: %s (ID: %d)", series.title, series.id)
    logger.info("  Path: %s", series.path)

    series_path = Path(series.path)
    if not series_path.is_dir():
        logger.warning("  Series path does not exist: %s — skipping", series.path)
        if not config.dry_run:
            return []

    try:
        episode_files = client.get_episode_files(series.id)
    except SonarrAPIError as e:
        logger.warning("  Failed to fetch episode files: %s — skipping", e)
        if not config.dry_run:
            return []

    logger.info("  Found %d episode file(s)", len(episode_files))

    for ep_file in episode_files:
        ep_path = Path(ep_file.path)
        if not ep_path.is_file():
            logger.warning("  Video file missing: %s", ep_path)
            if not config.dry_run:
                continue

        subtitles = (
            find_subtitles(ep_path, config.sub_extensions)
            if not config.dry_run
            else [ep_path.parent / "dummy.srt"]
        )
        for srt_path in subtitles:
            logger.info("  FOUND SUB: %s", srt_path.name)
            logger.info("    Video:   %s", ep_path.name)

            backup_dir = ep_path.parent / config.backup_dir_name

            backup_path = (
                backup_subtitle(srt_path, backup_dir, logger)
                if not config.dry_run
                else next_backup_path(backup_dir, srt_path.name)
            )
            if backup_path is None:
                logger.error("    Skipping (backup failed): %s", srt_path)
                continue

            output_path = srt_path.with_suffix(".synced.tmp")

            tasks.append(
                PendingSyncTask(
                    video_path=ep_path,
                    srt_path=srt_path,
                    backup_path=backup_path,
                    output_path=output_path,
                )
            )

    return tasks


def main(cli_args: list[str] | None = None) -> int:
    config = CliApp.run(Config, cli_args=cli_args if cli_args is not None else sys.argv[1:])
    logger = setup_logging()

    logger.info("===== ffsubsync batch run started =====")
    logger.info("Sonarr URL: %s", config.sonarr_url)
    logger.info("Series filter: %s", config.series_filter)
    logger.info("Backup dir: %s", config.backup_dir_name)
    logger.info("Sub extensions: %s", ", ".join(config.sub_extensions))
    logger.info("Workers: %d", config.workers)
    logger.info("Reference stream: %s", config.reference_stream)
    logger.info("VAD: %s", config.vad)
    logger.info("Dry run: %s", config.dry_run)

    if not check_ffmpeg():
        logger.error("ffmpeg not found. Please install it.")
        if not config.dry_run:
            return 1

    if not check_ffsubsync():
        logger.error("ffsubsync is not installed.")
        if not config.dry_run:
            return 1

    client = SonarrClient(config.sonarr_url, config.sonarr_api_key)
    tasks = collect_sync_tasks(client, config, logger)

    if not tasks:
        logger.info("No subtitles to sync.")
        return 0

    worker_fn = worker_run_sync if not config.dry_run else worker_run_sync_dry_run
    stats = run_sync_parallel(worker_fn, tasks, config, logger)

    logger.info("")
    logger.info("===== Batch run complete =====")
    logger.info("Total subtitle files found: %d", stats.total)
    logger.info("Successfully synced:        %d", stats.synced)
    logger.info("Failed:                     %d", stats.failed)

    if stats.errors:
        logger.warning("Errors:")
        for err in stats.errors:
            logger.warning("  - %s", err)

    if stats.failed > 0:
        logger.warning("%d file(s) failed.", stats.failed)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

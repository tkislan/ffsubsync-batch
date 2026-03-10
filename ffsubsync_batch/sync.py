from __future__ import annotations

import logging
import multiprocessing as mp
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ffsubsync.ffsubsync import make_parser, run

from ffsubsync_batch.config import Config
from ffsubsync_batch.subtitles import restore_backup


@dataclass
class SyncJob:
    """A single sync task to be sent to a worker process."""

    video_path: str
    subtitle_path: str
    output_path: str
    max_offset: int
    reference_stream: str
    vad: str


@dataclass
class SyncJobResult:
    """Result of a single subtitle sync operation, returned from the worker."""

    video_path: str
    subtitle_path: str
    success: bool
    offset_seconds: float | None = None
    framerate_scale_factor: float | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class SyncStats:
    total: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class PendingSyncTask:
    """Tracks a subtitle awaiting sync, including its backup path."""

    video_path: Path
    srt_path: Path
    backup_path: Path
    output_path: Path


def run_ffsubsync(job: SyncJob) -> dict[str, Any]:
    """
    Run ffsubsync on a single job and return the raw result dict.
    Isolated so it can be easily mocked in tests.
    """
    unparsed_args = [
        job.video_path,
        "-i",
        job.subtitle_path,
        "-o",
        job.output_path,
        "--max-offset-seconds",
        str(job.max_offset),
        "--reference-stream",
        job.reference_stream,
        "--vad",
        job.vad,
    ]

    parser = make_parser()
    parsed_args = parser.parse_args(args=unparsed_args)
    result = run(parsed_args)
    return result if isinstance(result, dict) else {}


def worker_run_sync(job: SyncJob) -> SyncJobResult:
    """
    Worker function: runs ffsubsync in an isolated process.

    Each worker gets its own copy of the ffsubsync internals (argparse state,
    tqdm instances, numpy arrays, ffmpeg subprocess), so they don't interfere.
    """
    start = time.monotonic()

    try:
        result = run_ffsubsync(job)
        elapsed = time.monotonic() - start

        offset = result.get("offset_seconds")
        scale = result.get("framerate_scale_factor")

        if not Path(job.output_path).is_file():
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=False,
                error="ffsubsync completed but output file was not created",
                elapsed_seconds=elapsed,
            )

        return SyncJobResult(
            video_path=job.video_path,
            subtitle_path=job.subtitle_path,
            success=True,
            offset_seconds=offset,
            framerate_scale_factor=scale,
            elapsed_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        return SyncJobResult(
            video_path=job.video_path,
            subtitle_path=job.subtitle_path,
            success=False,
            error=f"{type(e).__name__}: {e}",
            elapsed_seconds=elapsed,
        )


def _log_sync_success(result: SyncJobResult, srt_name: str, logger: logging.Logger) -> None:
    offset_str = f"{result.offset_seconds:.2f}s" if result.offset_seconds is not None else "?"
    scale_str = (
        f"{result.framerate_scale_factor:.3f}" if result.framerate_scale_factor is not None else "?"
    )
    logger.info(
        "  SUCCESS (%.1fs, offset=%s, scale=%s): %s",
        result.elapsed_seconds,
        offset_str,
        scale_str,
        srt_name,
    )


def run_sync_parallel(
    worker_fn: Callable[[SyncJob], SyncJobResult],
    tasks: list[PendingSyncTask],
    config: Config,
    logger: logging.Logger,
) -> SyncStats:
    """
    Run ffsubsync on all tasks in parallel using a process pool.

    Why multiprocessing instead of threading or direct calls?
    - ffsubsync internally spawns ffmpeg for audio extraction (I/O + CPU bound)
    - ffsubsync uses global state (tqdm, logging) -- separate processes isolate this
    - While one worker waits on ffmpeg I/O, another can run FFT correlation
    - With 2-4 workers, typical throughput doubles vs sequential processing
    """
    stats = SyncStats(total=len(tasks))

    if not tasks:
        return stats

    jobs = [
        SyncJob(
            video_path=str(task.video_path),
            subtitle_path=str(task.srt_path),
            output_path=str(task.output_path),
            max_offset=config.max_offset,
            reference_stream=config.reference_stream,
            vad=config.vad,
        )
        for task in tasks
    ]

    task_map: dict[tuple[str, str], PendingSyncTask] = {
        (str(t.video_path), str(t.srt_path)): t for t in tasks
    }

    logger.info("")
    logger.info(
        "===== Starting sync: %d subtitle(s) with %d worker(s) =====",
        len(jobs),
        config.workers,
    )

    # maxtasksperchild=1 ensures each sync gets a completely fresh process,
    # preventing any leaked state (tqdm bars, ffmpeg handles) between runs
    with mp.Pool(processes=config.workers, maxtasksperchild=1) as pool:
        results = pool.map(worker_fn, jobs)

    for result in results:
        task = task_map[(result.video_path, result.subtitle_path)]
        srt_path = task.srt_path
        output_path = task.output_path
        backup_path = task.backup_path

        if result.success and (output_path.is_file() or config.dry_run):
            try:
                logger.info("  Moving %s to %s", output_path, srt_path)
                if not config.dry_run:
                    shutil.move(str(output_path), str(srt_path))
                stats.synced += 1
                _log_sync_success(result, srt_path.name, logger)
            except OSError as e:
                stats.failed += 1
                stats.errors.append(f"Failed to replace original: {srt_path} ({e})")
                logger.error("  Failed to replace %s with synced version: %s", srt_path, e)
                if not config.dry_run:
                    restore_backup(backup_path, srt_path, logger)
        else:
            stats.failed += 1
            error_msg = result.error or "Unknown error"
            stats.errors.append(f"{srt_path}: {error_msg}")
            logger.error(
                "  FAILED (%.1fs): %s — %s",
                result.elapsed_seconds,
                srt_path.name,
                error_msg,
            )

            if not config.dry_run:
                if output_path.is_file():
                    output_path.unlink(missing_ok=True)

                restore_backup(backup_path, srt_path, logger)

    return stats

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ffsubsync_batch.config import Config
from ffsubsync_batch.sync import (
    PendingSyncTask,
    SyncJob,
    SyncJobResult,
    run_sync_parallel,
    worker_run_sync,
)


def _test_config() -> Config:
    return Config(
        sonarr_url="http://test:8989",
        sonarr_api_key="test-key",
        series_filter="test",
        workers=1,
    )


def make_task(tmp_path: Path, name: str = "ep01") -> PendingSyncTask:
    """Create a PendingSyncTask with real files on disk."""
    tmp_path.mkdir(parents=True, exist_ok=True)

    video = tmp_path / f"{name}.mkv"
    video.write_bytes(b"\x00" * 100)

    srt = tmp_path / f"{name}.srt"
    srt.write_text(f"original content for {name}")

    backup_dir = tmp_path / ".backup"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / f"{name}.srt.backup.001"
    backup.write_text(f"original content for {name}")

    output = tmp_path / f"{name}.synced.tmp"

    return PendingSyncTask(
        video_path=video,
        srt_path=srt,
        backup_path=backup,
        output_path=output,
    )


class TestWorkerRunSync:
    def test_success_with_output_file(self, tmp_path: Path) -> None:
        job = SyncJob(
            video_path=str(tmp_path / "video.mkv"),
            subtitle_path=str(tmp_path / "sub.srt"),
            output_path=str(tmp_path / "out.srt"),
            max_offset=120,
            reference_stream="a:0",
            vad="subs_then_webrtc",
        )
        (tmp_path / "video.mkv").write_bytes(b"\x00")
        (tmp_path / "sub.srt").write_text("sub")

        def fake_run(j: SyncJob) -> dict[str, Any]:
            Path(j.output_path).write_text("synced")
            return {"offset_seconds": 1.5, "framerate_scale_factor": 1.0}

        with patch("ffsubsync_batch.sync.run_ffsubsync", side_effect=fake_run):
            result = worker_run_sync(job)

        assert result.success is True
        assert result.offset_seconds == 1.5
        assert result.framerate_scale_factor == 1.0

    def test_failure_when_ffsubsync_raises(self, tmp_path: Path) -> None:
        job = SyncJob(
            video_path=str(tmp_path / "video.mkv"),
            subtitle_path=str(tmp_path / "sub.srt"),
            output_path=str(tmp_path / "out.srt"),
            max_offset=120,
            reference_stream="a:0",
            vad="subs_then_webrtc",
        )

        with patch(
            "ffsubsync_batch.sync.run_ffsubsync",
            side_effect=RuntimeError("ffmpeg crashed"),
        ):
            result = worker_run_sync(job)

        assert result.success is False
        assert "RuntimeError" in (result.error or "")

    def test_failure_when_output_missing(self, tmp_path: Path) -> None:
        job = SyncJob(
            video_path=str(tmp_path / "video.mkv"),
            subtitle_path=str(tmp_path / "sub.srt"),
            output_path=str(tmp_path / "out.srt"),
            max_offset=120,
            reference_stream="a:0",
            vad="subs_then_webrtc",
        )

        def fake_run(j: SyncJob) -> dict[str, Any]:
            return {"offset_seconds": 0.0}

        with patch("ffsubsync_batch.sync.run_ffsubsync", side_effect=fake_run):
            result = worker_run_sync(job)

        assert result.success is False
        assert "not created" in (result.error or "")


class TestRunSyncParallel:
    def test_successful_sync_replaces_original(
        self, tmp_path: Path, logger: logging.Logger
    ) -> None:
        task = make_task(tmp_path, "ep01")
        original_content = task.srt_path.read_text()

        def fake_worker(job: SyncJob) -> SyncJobResult:
            Path(job.output_path).write_text("synced content")
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=True,
                offset_seconds=2.0,
                framerate_scale_factor=1.0,
                elapsed_seconds=0.5,
            )

        stats = run_sync_parallel(fake_worker, [task], _test_config(), logger)

        assert stats.synced == 1
        assert stats.failed == 0
        assert task.srt_path.read_text() == "synced content"
        assert task.backup_path.read_text() == original_content

    def test_failed_sync_restores_original(self, tmp_path: Path, logger: logging.Logger) -> None:
        task = make_task(tmp_path, "ep01")
        original_content = task.srt_path.read_text()

        def fake_worker(job: SyncJob) -> SyncJobResult:
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=False,
                error="ffsubsync crashed",
                elapsed_seconds=1.0,
            )

        stats = run_sync_parallel(fake_worker, [task], _test_config(), logger)

        assert stats.failed == 1
        assert stats.synced == 0
        assert task.srt_path.read_text() == original_content

    def test_mixed_results(self, tmp_path: Path, logger: logging.Logger) -> None:
        ok_dir = tmp_path / "ok"
        task_ok = make_task(ok_dir, "ep01")

        fail_dir = tmp_path / "fail"
        task_fail = make_task(fail_dir, "ep02")
        original_fail_content = task_fail.srt_path.read_text()

        def fake_worker(job: SyncJob) -> SyncJobResult:
            if "ep01" in job.subtitle_path:
                Path(job.output_path).write_text("synced")
                return SyncJobResult(
                    video_path=job.video_path,
                    subtitle_path=job.subtitle_path,
                    success=True,
                    offset_seconds=1.0,
                    elapsed_seconds=0.3,
                )
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=False,
                error="crash",
                elapsed_seconds=0.1,
            )

        stats = run_sync_parallel(fake_worker, [task_ok, task_fail], _test_config(), logger)

        assert stats.synced == 1
        assert stats.failed == 1
        assert task_ok.srt_path.read_text() == "synced"
        assert task_fail.srt_path.read_text() == original_fail_content

    def test_empty_tasks(self, logger: logging.Logger) -> None:
        stats = run_sync_parallel(worker_run_sync, [], _test_config(), logger)
        assert stats.total == 0
        assert stats.synced == 0
        assert stats.failed == 0

    def test_output_file_exists_but_move_fails(
        self, tmp_path: Path, logger: logging.Logger
    ) -> None:
        task = make_task(tmp_path, "ep01")
        original_content = task.srt_path.read_text()

        def fake_worker(job: SyncJob) -> SyncJobResult:
            Path(job.output_path).write_text("synced content")
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=True,
                offset_seconds=1.0,
                elapsed_seconds=0.2,
            )

        with patch(
            "ffsubsync_batch.sync.shutil.move",
            side_effect=OSError("permission denied"),
        ):
            stats = run_sync_parallel(fake_worker, [task], _test_config(), logger)

        assert stats.failed == 1
        assert task.srt_path.read_text() == original_content

    def test_sync_failure_cleans_up_temp_file(self, tmp_path: Path, logger: logging.Logger) -> None:
        task = make_task(tmp_path, "ep01")

        def fake_worker(job: SyncJob) -> SyncJobResult:
            Path(job.output_path).write_text("partial output")
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=False,
                error="partial failure",
                elapsed_seconds=0.5,
            )

        run_sync_parallel(fake_worker, [task], _test_config(), logger)

        assert not task.output_path.exists()

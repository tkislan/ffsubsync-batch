from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import responses as responses_mock

from ffsubsync_batch.config import Config
from ffsubsync_batch.main import collect_sync_tasks
from ffsubsync_batch.sonarr import SonarrClient
from ffsubsync_batch.sync import SyncJob, SyncJobResult, run_sync_parallel

from .conftest import make_sonarr_episode_file_json, make_sonarr_series_json

SONARR_URL = "http://sonarr:8989"


def make_config(tmp_path: Path, **overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "sonarr_url": SONARR_URL,
        "sonarr_api_key": "test-key",
        "log_file": str(tmp_path / "test.log"),
        "backup_dir_name": ".original-sub",
        "sub_extensions": ["srt"],
        "dry_run": False,
        "workers": 1,
        "max_offset": 120,
        "reference_stream": "a:0",
        "vad": "subs_then_webrtc",
        "series_filter": "Series A",
    }
    defaults.update(overrides)
    return Config(**defaults)


class TestCollectSyncTasks:
    @responses_mock.activate
    def test_discovers_subtitles_and_creates_tasks(
        self, media_tree: dict[str, Any], logger: logging.Logger, tmp_path: Path
    ) -> None:
        series_a_dir = str(media_tree["series_a_dir"])
        vid_a1 = media_tree["vid_a1"]

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(1, "Series A", series_a_dir)],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    10, 1, 1, str(vid_a1), "Season 01/Series A - S01E01.mkv"
                ),
            ],
        )

        config = make_config(tmp_path)
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert len(tasks) == 2
        srt_names = sorted(t.srt_path.name for t in tasks)
        assert srt_names == ["Series A - S01E01.eng.srt", "Series A - S01E01.srt"]
        for task in tasks:
            assert task.backup_path.exists()

    @responses_mock.activate
    def test_filter_matching_multiple_series_returns_empty(
        self, media_tree: dict[str, Any], logger: logging.Logger, tmp_path: Path
    ) -> None:
        series_a_dir = str(media_tree["series_a_dir"])
        series_b_dir = str(media_tree["series_b_dir"])

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[
                make_sonarr_series_json(1, "Series A", series_a_dir),
                make_sonarr_series_json(2, "Series B", series_b_dir),
            ],
        )

        config = make_config(tmp_path, series_filter="Series")
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert tasks == []

    @responses_mock.activate
    def test_dry_run_collects_tasks_without_backups(
        self, media_tree: dict[str, Any], logger: logging.Logger, tmp_path: Path
    ) -> None:
        series_a_dir = str(media_tree["series_a_dir"])

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(1, "Series A", series_a_dir)],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    10, 1, 1, str(media_tree["vid_a1"]), "Season 01/Series A - S01E01.mkv"
                ),
            ],
        )

        config = make_config(tmp_path, dry_run=True)
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert len(tasks) == 2
        srt_names = sorted(t.srt_path.name for t in tasks)
        assert srt_names == ["Series A - S01E01.eng.srt", "Series A - S01E01.srt"]

        backup_dir = media_tree["vid_a1"].parent / ".original-sub"
        assert not backup_dir.exists()

    @responses_mock.activate
    def test_series_filter_narrows_results(
        self, media_tree: dict[str, Any], logger: logging.Logger, tmp_path: Path
    ) -> None:
        series_a_dir = str(media_tree["series_a_dir"])
        series_b_dir = str(media_tree["series_b_dir"])

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[
                make_sonarr_series_json(1, "Series A", series_a_dir),
                make_sonarr_series_json(2, "Series B", series_b_dir),
            ],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    20, 2, 1, str(media_tree["vid_b1"]), "Season 01/Series B - S01E01.mkv"
                ),
            ],
        )

        config = make_config(tmp_path, series_filter="Series B")
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert len(tasks) == 1
        assert tasks[0].srt_path.name == "Series B - S01E01.srt"

    @responses_mock.activate
    def test_api_error_returns_empty(self, logger: logging.Logger, tmp_path: Path) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json={"error": "fail"},
            status=500,
        )

        config = make_config(tmp_path)
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert tasks == []

    @responses_mock.activate
    def test_missing_video_file_skipped(self, tmp_path: Path, logger: logging.Logger) -> None:
        series_dir = tmp_path / "Show"
        series_dir.mkdir()
        season_dir = series_dir / "Season 01"
        season_dir.mkdir()
        (season_dir / "show - S01E01.srt").write_text("sub")

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(1, "Show", str(series_dir))],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    10,
                    1,
                    1,
                    str(season_dir / "show - S01E01.mkv"),
                    "Season 01/show - S01E01.mkv",
                ),
            ],
        )

        config = make_config(tmp_path, series_filter="Show")
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert tasks == []

    @responses_mock.activate
    def test_episode_file_api_error_skips_series(
        self, media_tree: dict[str, Any], logger: logging.Logger, tmp_path: Path
    ) -> None:
        series_a_dir = str(media_tree["series_a_dir"])

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(1, "Series A", series_a_dir)],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json={"error": "not found"},
            status=404,
        )

        config = make_config(tmp_path)
        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, logger)

        assert tasks == []


class TestMainIntegration:
    @responses_mock.activate
    def test_end_to_end_happy_path(self, media_tree: dict[str, Any], tmp_path: Path) -> None:
        """Full pipeline: API -> discover -> backup -> sync -> replace."""
        series_a_dir = str(media_tree["series_a_dir"])

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(1, "Series A", series_a_dir)],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    10, 1, 1, str(media_tree["vid_a1"]), "Season 01/Series A - S01E01.mkv"
                ),
            ],
        )

        def fake_worker(job: SyncJob) -> SyncJobResult:
            Path(job.output_path).write_text("synced subtitle data")
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=True,
                offset_seconds=3.14,
                framerate_scale_factor=1.0,
                elapsed_seconds=1.0,
            )

        config = make_config(tmp_path)
        log = logging.getLogger("test_e2e")
        log.handlers.clear()
        log.addHandler(logging.NullHandler())

        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, log)
        assert len(tasks) == 2

        stats = run_sync_parallel(fake_worker, tasks, config, log)

        assert stats.synced == 2
        assert stats.failed == 0

        for task in tasks:
            assert task.srt_path.read_text() == "synced subtitle data"
            assert task.backup_path.exists()

    @responses_mock.activate
    def test_end_to_end_failure_preserves_originals(
        self, media_tree: dict[str, Any], tmp_path: Path
    ) -> None:
        """Sync fails -> originals must be preserved from backups."""
        series_b_dir = str(media_tree["series_b_dir"])
        original_content = media_tree["srt_b1"].read_text()

        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[make_sonarr_series_json(2, "Series B", series_b_dir)],
        )
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                make_sonarr_episode_file_json(
                    20, 2, 1, str(media_tree["vid_b1"]), "Season 01/Series B - S01E01.mkv"
                ),
            ],
        )

        def fake_worker(job: SyncJob) -> SyncJobResult:
            return SyncJobResult(
                video_path=job.video_path,
                subtitle_path=job.subtitle_path,
                success=False,
                error="ffmpeg segfault",
                elapsed_seconds=0.1,
            )

        config = make_config(tmp_path, series_filter="Series B")
        log = logging.getLogger("test_e2e_fail")
        log.handlers.clear()
        log.addHandler(logging.NullHandler())

        client = SonarrClient(SONARR_URL, "test-key")
        tasks = collect_sync_tasks(client, config, log)
        assert len(tasks) == 1

        stats = run_sync_parallel(fake_worker, tasks, config, log)

        assert stats.failed == 1
        assert media_tree["srt_b1"].read_text() == original_content

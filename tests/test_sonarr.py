from __future__ import annotations

import pytest
import responses as responses_mock

from ffsubsync_batch.sonarr import SonarrAPIError, SonarrClient

SONARR_URL = "http://sonarr:8989"


@pytest.fixture
def client() -> SonarrClient:
    return SonarrClient(SONARR_URL, "test-api-key")


class TestSonarrClientGetSeries:
    @responses_mock.activate
    def test_returns_parsed_series(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[
                {
                    "id": 1,
                    "title": "Breaking Bad",
                    "path": "/tv/Breaking Bad",
                    "sortTitle": "breaking bad",
                    "status": "ended",
                    "seasonCount": 5,
                    "episodeFileCount": 62,
                    "monitored": True,
                    "seasons": [{"seasonNumber": 1, "monitored": True}],
                },
                {
                    "id": 2,
                    "title": "The Wire",
                    "path": "/tv/The Wire",
                    "sortTitle": "wire",
                },
            ],
            status=200,
        )

        series = client.get_series()
        assert len(series) == 2
        assert series[0].title == "Breaking Bad"
        assert series[0].id == 1
        assert series[1].title == "The Wire"

    @responses_mock.activate
    def test_handles_empty_list(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[],
            status=200,
        )
        assert client.get_series() == []

    @responses_mock.activate
    def test_raises_on_http_error(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json={"error": "Unauthorized"},
            status=401,
        )
        with pytest.raises(SonarrAPIError) as exc_info:
            client.get_series()
        assert exc_info.value.status_code == 401

    @responses_mock.activate
    def test_raises_on_non_array_response(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json={"message": "not an array"},
            status=200,
        )
        with pytest.raises(SonarrAPIError):
            client.get_series()


class TestSonarrClientGetEpisodeFiles:
    @responses_mock.activate
    def test_returns_parsed_episode_files(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[
                {
                    "id": 10,
                    "seriesId": 1,
                    "seasonNumber": 1,
                    "relativePath": "Season 01/show - S01E01.mkv",
                    "path": "/tv/show/Season 01/show - S01E01.mkv",
                    "size": 500_000_000,
                    "dateAdded": "2024-01-01T00:00:00Z",
                    "quality": {
                        "quality": {"id": 4, "name": "HDTV-720p"},
                        "revision": {"version": 1, "real": 0},
                    },
                }
            ],
            status=200,
        )

        files = client.get_episode_files(1)
        assert len(files) == 1
        assert files[0].series_id == 1
        assert files[0].season_number == 1
        assert files[0].path == "/tv/show/Season 01/show - S01E01.mkv"

    @responses_mock.activate
    def test_raises_on_server_error(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json={"error": "Internal Server Error"},
            status=500,
        )
        with pytest.raises(SonarrAPIError) as exc_info:
            client.get_episode_files(1)
        assert exc_info.value.status_code == 500

    @responses_mock.activate
    def test_sends_series_id_param(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/episodefile",
            json=[],
            status=200,
        )
        client.get_episode_files(42)
        assert "seriesId=42" in (responses_mock.calls[0].request.url or "")


class TestSonarrClientHeaders:
    @responses_mock.activate
    def test_sends_api_key_header(self, client: SonarrClient) -> None:
        responses_mock.add(
            responses_mock.GET,
            f"{SONARR_URL}/api/v3/series",
            json=[],
            status=200,
        )
        client.get_series()
        assert responses_mock.calls[0].request.headers["X-Api-Key"] == "test-api-key"

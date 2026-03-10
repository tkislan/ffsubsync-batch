from __future__ import annotations

from typing import Any

import requests

from ffsubsync_batch.models import SonarrEpisodeFile, SonarrSeries


class SonarrAPIError(Exception):
    def __init__(self, endpoint: str, status_code: int, body: str):
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body
        super().__init__(f"Sonarr API error: {endpoint} returned HTTP {status_code}")


class SonarrClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Api-Key": api_key,
                "Accept": "application/json",
            }
        )

    def _get(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[Any] | dict[str, Any]:
        url = f"{self.base_url}/api/v3/{endpoint}"
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            raise SonarrAPIError(endpoint, resp.status_code, resp.text[:500])
        return resp.json()  # type: ignore[no-any-return]

    def get_series(self) -> list[SonarrSeries]:
        data = self._get("series")
        if not isinstance(data, list):
            raise SonarrAPIError("series", 200, f"Expected array, got {type(data).__name__}")
        return [SonarrSeries.model_validate(item) for item in data]

    def get_episode_files(self, series_id: int) -> list[SonarrEpisodeFile]:
        data = self._get("episodefile", params={"seriesId": series_id})
        if not isinstance(data, list):
            raise SonarrAPIError("episodefile", 200, f"Expected array, got {type(data).__name__}")
        return [SonarrEpisodeFile.model_validate(item) for item in data]

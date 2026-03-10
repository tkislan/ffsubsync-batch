from __future__ import annotations

from pydantic import BaseModel, Field


class SonarrSeason(BaseModel):
    season_number: int = Field(alias="seasonNumber")
    monitored: bool = False

    model_config = {"populate_by_name": True}


class SonarrSeries(BaseModel):
    """Response item from GET /api/v3/series."""

    id: int
    title: str
    path: str
    sort_title: str = Field(alias="sortTitle", default="")
    status: str = Field(default="")
    season_count: int = Field(alias="seasonCount", default=0)
    episode_file_count: int = Field(alias="episodeFileCount", default=0)
    monitored: bool = Field(default=True)
    seasons: list[SonarrSeason] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "allow"}


class QualityModel(BaseModel):
    id: int = 0
    name: str = ""

    model_config = {"extra": "allow"}


class QualityRevision(BaseModel):
    version: int = 1
    real: int = 0

    model_config = {"extra": "allow"}


class QualityWrapper(BaseModel):
    quality: QualityModel = Field(default_factory=QualityModel)
    revision: QualityRevision = Field(default_factory=QualityRevision)

    model_config = {"extra": "allow"}


class SonarrEpisodeFile(BaseModel):
    """Response item from GET /api/v3/episodefile?seriesId=X."""

    id: int
    series_id: int = Field(alias="seriesId")
    season_number: int = Field(alias="seasonNumber")
    relative_path: str = Field(alias="relativePath")
    path: str
    size: int = Field(default=0)
    date_added: str = Field(alias="dateAdded", default="")
    scene_name: str = Field(alias="sceneName", default="")
    release_group: str = Field(alias="releaseGroup", default="")
    quality: QualityWrapper = Field(default_factory=QualityWrapper)

    model_config = {"populate_by_name": True, "extra": "allow"}

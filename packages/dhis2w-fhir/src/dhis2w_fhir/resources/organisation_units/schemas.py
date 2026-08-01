"""Organisation-unit schemas: the emitter projection, its geometry, and the selection table."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class OrganisationUnitSelection(BaseModel):
    """Which DHIS2 organisation units to generate - the `[generate.organisation_units]` table of `fhir.toml`."""

    root: str | None = None
    max_level: int | None = None
    terminology: bool = False

    @field_validator("root", mode="before")
    @classmethod
    def _empty_root_is_none(cls, value: object) -> object:
        """Treat the scaffolded `root = ""` placeholder as unset."""
        return None if value == "" else value

    @field_validator("max_level", mode="before")
    @classmethod
    def _zero_level_is_none(cls, value: object) -> object:
        """Treat the scaffolded `max_level = 0` placeholder as unset."""
        return None if value == 0 else value


class GeoPoint(BaseModel):
    """A WGS84 position - the Point coordinates or polygon centroid that `Location.position` renders."""

    model_config = ConfigDict(frozen=True)

    longitude: float
    latitude: float


class OrganisationUnitIn(BaseModel):
    """The organisation-unit projection consumed by the emitter.

    `latitude`/`longitude` hold the Point coordinates, or the area-weighted centroid for
    Polygon/MultiPolygon geometry; GeoJSON stores `[longitude, latitude]`, so the mapper
    must swap. `boundary_geojson` carries the compact GeoJSON Feature wrapping the geometry
    of every unit whose geometry parses, Points and non-positional types included.
    `closed` is true for a unit whose DHIS2 `closedDate` has passed.
    """

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    short_name: str | None = None
    code: str | None = None
    level: int
    path: str
    parent_uid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    boundary_geojson: str | None = None
    contact_person: str | None = None
    email: str | None = None
    phone_number: str | None = None
    closed: bool = False

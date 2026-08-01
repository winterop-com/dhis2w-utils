"""Unit tests for how the service maps DHIS2 geometry onto Location position and the boundary payload."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from dhis2w_client.generated.v42.schemas import OrganisationUnit
from dhis2w_fhir import service
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

_TODAY = date(2026, 8, 1)

_SQUARE = [[[0.0, 0.0], [4.0, 0.0], [4.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]


def _unit(uid: str, geometry: dict[str, Any] | None, **extra: Any) -> OrganisationUnit:
    """Build a generated OrganisationUnit for the mapper."""
    payload: dict[str, Any] = {"id": uid, "name": f"Unit {uid}", "level": 2, "path": f"/Root0000000/{uid}"}
    if geometry is not None:
        payload["geometry"] = geometry
    payload.update(extra)
    return OrganisationUnit.model_validate(payload)


def _map(model: OrganisationUnit, tally: service.GeometryTally | None = None) -> OrganisationUnitIn:
    """Map one unit, asserting it survived the mapper."""
    mapped = service._organisation_unit_input(model, tally or service.GeometryTally(), _TODAY)
    assert mapped is not None
    return mapped


def test_point_geometry_yields_a_position() -> None:
    """A Point lands directly in Location.position, GeoJSON's [lng, lat] swapped."""
    mapped = _map(_unit("Pnt1aaaaaaa", {"type": "Point", "coordinates": [-11.7383, 7.9647]}))
    assert mapped.latitude == 7.9647
    assert mapped.longitude == -11.7383
    assert mapped.boundary_geojson is not None


def test_polygon_geometry_yields_the_centroid_without_a_note() -> None:
    """A Polygon contributes its shoelace centroid - nominal behaviour, so it raises no note."""
    tally = service.GeometryTally()
    mapped = _map(_unit("Ply1aaaaaaa", {"type": "Polygon", "coordinates": _SQUARE}), tally)
    assert mapped.latitude == 1.0
    assert mapped.longitude == 2.0
    assert mapped.boundary_geojson is not None
    assert tally.to_notes() == []


def test_other_geometry_types_are_embedded_without_a_position() -> None:
    """LineString, MultiPoint, and friends carry their GeoJSON but get no position."""
    tally = service.GeometryTally()
    line = _map(_unit("Lin1aaaaaaa", {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}), tally)
    points = _map(_unit("Mpt1aaaaaaa", {"type": "MultiPoint", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}), tally)
    collection = _map(
        _unit(
            "Gcl1aaaaaaa",
            {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [1.0, 2.0]}]},
        ),
        tally,
    )
    for mapped in (line, points, collection):
        assert mapped.latitude is None
        assert mapped.longitude is None
        assert mapped.boundary_geojson is not None
    notes = tally.to_notes()
    assert len(notes) == 1
    assert "3 organisation units have GeometryCollection, LineString, MultiPoint geometry" in notes[0]
    assert "embedded without position" in notes[0]


def test_malformed_geometry_gets_neither_position_nor_boundary() -> None:
    """Only empty or unusable coordinates count as malformed, and those emit nothing."""
    tally = service.GeometryTally()
    empty = _map(_unit("Emp1aaaaaaa", {"type": "Polygon", "coordinates": []}), tally)
    missing = _map(_unit("Mis1aaaaaaa", {"type": "Point"}), tally)
    hollow = _map(_unit("Hol1aaaaaaa", {"type": "GeometryCollection", "geometries": []}), tally)
    for mapped in (empty, missing, hollow):
        assert mapped.latitude is None
        assert mapped.boundary_geojson is None
    notes = tally.to_notes()
    assert len(notes) == 1
    assert notes[0].startswith("3 organisation units have malformed geometry; no position or boundary emitted")


def test_units_without_geometry_are_untouched() -> None:
    """A unit with no geometry at all is neither noted nor given a boundary."""
    tally = service.GeometryTally()
    mapped = _map(_unit("Non1aaaaaaa", None), tally)
    assert mapped.boundary_geojson is None
    assert tally.to_notes() == []


def test_boundary_payload_is_a_geojson_feature() -> None:
    """The boundary payload wraps the geometry in a Feature carrying the DHIS2 identity."""
    geometry = {"type": "Point", "coordinates": [-11.7383, 7.9647]}
    mapped = _map(_unit("Pnt1aaaaaaa", geometry))
    assert mapped.boundary_geojson is not None
    feature = json.loads(mapped.boundary_geojson)
    assert feature == {
        "type": "Feature",
        "geometry": geometry,
        "properties": {"dhis2Uid": "Pnt1aaaaaaa", "name": "Unit Pnt1aaaaaaa", "level": 2},
    }
    # Compact and key-sorted, so a regenerate with unchanged metadata is byte-identical.
    assert ", " not in mapped.boundary_geojson
    assert ": " not in mapped.boundary_geojson
    assert mapped.boundary_geojson.index('"geometry"') < mapped.boundary_geojson.index('"properties"')


def test_closed_date_in_the_past_closes_the_unit() -> None:
    """A closedDate on or before today marks the unit closed; a future one does not."""
    assert _map(_unit("Cls1aaaaaaa", None, closedDate="2020-01-01")).closed is True
    assert _map(_unit("Cls2aaaaaaa", None, closedDate="2026-08-01")).closed is True
    assert _map(_unit("Opn1aaaaaaa", None, closedDate="2099-01-01")).closed is False
    assert _map(_unit("Opn2aaaaaaa", None)).closed is False

"""DHIS2 attribute values shared by every component: the projection plus the emit-time code index."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AttributeValueIn(BaseModel):
    """One DHIS2 attribute value: the attribute it belongs to, and the value the instance holds.

    DHIS2 sends `{"attribute": {"id": "ihn1wb9eho8"}, "value": "KE03"}` and nothing else - no
    code, no name, no value type - so the projection carries the UID and the value alone and
    the attribute's code is joined from `AttributeCodeIndex` at emit time. The value is a
    string whatever the attribute's declared DHIS2 value type; a GeoJSON-valued attribute
    arrives as the serialised document.
    """

    model_config = ConfigDict(frozen=True)

    attribute_uid: str
    value: str


class AttributeCodeIndex(BaseModel):
    """Every DHIS2 attribute's code keyed by its UID - the join one generate run resolves once.

    An attribute DHIS2 left without a code is absent from the mapping rather than present with
    an empty one: most instances code few of their attributes, and some code none of them, so
    every consumer reads through `code_for` and decides what a missing code means for it.
    """

    model_config = ConfigDict(frozen=True)

    codes: dict[str, str] = Field(default_factory=dict)

    def code_for(self, attribute_uid: str) -> str | None:
        """The attribute's DHIS2 code, or None when the instance left it unset."""
        return self.codes.get(attribute_uid)

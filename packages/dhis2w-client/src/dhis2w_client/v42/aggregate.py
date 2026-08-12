"""Typed models for DHIS2 aggregate data values (shim over generated/v42/oas).

Covers the `/api/dataValueSets` GET response (a `DataValueSet` envelope
containing a list of `DataValue`s). The corresponding POST/import path
returns a `WebMessageResponse` (see `dhis2w_client/envelopes.py`).

Covers the sibling completeness resource too: `CompleteDataSetRegistration` is
the row `/api/completeDataSetRegistrations` files under the same
`(dataSet, period, organisationUnit, attributeOptionCombo)` key the values ride,
and `CompleteDataSetRegistrations` is the envelope a batch of them posts as.

Distinct from the *generated* `DataElement` / `DataSet` / `CategoryOptionCombo`
metadata models (those come out of `/api/schemas` codegen) — these describe
the **runtime values** captured against that metadata. OpenAPI ships both
shapes under `components/schemas/{DataValue,DataValueSet}`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_client.generated.v42.oas import DataValue, DataValueSet

__all__ = [
    "CompleteDataSetRegistration",
    "CompleteDataSetRegistrations",
    "DataValue",
    "DataValueSet",
]


class CompleteDataSetRegistration(BaseModel):
    """One statement that a data set is reported complete for a period, an organisation unit, and a combo.

    The key is the same four facts `/api/dataValueSets` files values under, and completeness is a
    separate claim about them: the values are what was reported, and this is the reporter saying the
    report is finished. DHIS2 fills `attributeOptionCombo` with the default combo, `date` with today,
    and `storedBy` with the authenticated user when the write names none of them.

    Hand-written rather than generated: the OpenAPI document declares
    `/api/completeDataSetRegistrations` with an untyped request body and ships no component schema for
    the row it carries, so there is nothing under `generated/v{41,42,43}/oas` to import (BUGS.md 80).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    dataSet: str | None = None
    period: str | None = None
    organisationUnit: str | None = None
    attributeOptionCombo: str | None = None
    date: str | None = None
    """The day the report was completed, as `YYYY-MM-DD`. DHIS2 stores today's date when none is given."""

    storedBy: str | None = None
    """Who reported it complete, stored verbatim - DHIS2 does not check it against its user table."""

    completed: bool | None = None


class CompleteDataSetRegistrations(BaseModel):
    """The envelope `POST /api/completeDataSetRegistrations` reads a batch of registrations from."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    completeDataSetRegistrations: list[CompleteDataSetRegistration] = Field(default_factory=list)

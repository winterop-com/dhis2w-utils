"""Typed models for DHIS2 aggregate data values (shim over generated/v41/oas).

Covers the `/api/dataValueSets` GET response (a `DataValueSet` envelope
containing a list of `DataValue`s). The corresponding POST/import path
returns a `WebMessageResponse` (see `dhis2w_client/envelopes.py`).

Distinct from the *generated* `DataElement` / `DataSet` / `CategoryOptionCombo`
metadata models (those come out of `/api/schemas` codegen) — these describe
the **runtime values** captured against that metadata. OpenAPI ships both
shapes under `components/schemas/{DataValue,DataValueSet}`.
"""

from __future__ import annotations

from dhis2w_client.generated.v41.oas import DataValue, DataValueSet

__all__ = ["DataValue", "DataValueSet"]

"""Read access to DHIS2 dataset completeness — `client.complete_data_set_registrations`.

`GET /api/completeDataSetRegistrations` returns the completeness claims filed
against the same `(dataSet, period, organisationUnit, attributeOptionCombo)` key
`/api/dataValueSets` files values under. The write side posts a
`CompleteDataSetRegistrations` envelope back; this accessor reads it and parses
the same typed envelope, mirroring `client.data_values.export`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from dhis2w_client.v41.aggregate import CompleteDataSetRegistrations

if TYPE_CHECKING:
    from dhis2w_client.v41.client import Dhis2Client


class CompleteDataSetRegistrationsAccessor:
    """`Dhis2Client.complete_data_set_registrations` — read `/api/completeDataSetRegistrations`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool for every request."""
        self._client = client

    async def export(
        self,
        *,
        data_set: str | Sequence[str] | None = None,
        period: str | Sequence[str] | None = None,
        org_unit: str | Sequence[str] | None = None,
        children: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
        created: str | None = None,
        last_updated: str | None = None,
        extra_params: Mapping[str, Any] | None = None,
    ) -> CompleteDataSetRegistrations:
        """GET `/api/completeDataSetRegistrations` and return the parsed envelope.

        The read side of the completeness resource, shaped like
        `client.data_values.export`. `data_set`, `period`, and `org_unit` each
        accept a single id or a sequence of ids, and repeat as
        `dataSet=`/`period=`/`orgUnit=` query params the way DHIS2 expects.

        - `children=True` -> `children=true`: include the org units below each
          `org_unit`.
        - `start_date` / `end_date` (`YYYY-MM-DD`): select by date range instead
          of by `period`.
        - `created` (`YYYY-MM-DD`): return only registrations filed on or after
          then.
        - `last_updated` (`YYYY-MM-DD`): return only registrations touched since
          then.
        - `extra_params` covers the rest of the surface (`idScheme`,
          `orgUnitIdScheme`, `dataSetIdScheme`, `attributeOptionComboIdScheme`,
          ...). Pass a flat mapping or a list of 2-tuples.

        Buffers the whole response into a typed `CompleteDataSetRegistrations`.

        Raises `Dhis2ApiError` on 4xx / 5xx.
        """
        params: dict[str, Any] = {}
        for key, value in (("dataSet", data_set), ("period", period), ("orgUnit", org_unit)):
            if value is None:
                continue
            params[key] = [value] if isinstance(value, str) else list(value)
        if children:
            params["children"] = "true"
        if start_date is not None:
            params["startDate"] = start_date
        if end_date is not None:
            params["endDate"] = end_date
        if created is not None:
            params["created"] = created
        if last_updated is not None:
            params["lastUpdated"] = last_updated
        if extra_params:
            params.update(extra_params)
        raw = await self._client.get_raw("/api/completeDataSetRegistrations", params=params)
        return CompleteDataSetRegistrations.model_validate(raw)


__all__ = ["CompleteDataSetRegistrationsAccessor"]

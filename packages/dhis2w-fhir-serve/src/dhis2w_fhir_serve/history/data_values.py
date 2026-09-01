"""The DHIS2 read behind one data set's responses: the values, for the periods and unit a request named.

THREE FACTS DECIDE THE SHAPE OF THIS READ.

1. **The organisation unit and the periods are the request's, and the read carries nothing else.**
   `/api/dataValueSets` will happily answer for a whole subtree (`children=true`) or for an open
   date range, and either turns one request into a read of a national data set. The route requires
   the unit and at least one period for exactly that reason, and this function sends what the route
   settled and no more.
2. **There is no cursor and no offset.** The endpoint offers `limit`, which truncates silently and
   therefore cannot page: a client walking pages would be handed the same truncated head every time
   and never told. So the bounded selection is read whole and the route pages the ordered result,
   which is also what makes `Bundle.total` an honest number rather than a guess.
3. **The attribute option combo is filtered here rather than asked for.** The read is already bounded
   by the data set, the unit, and the periods, so narrowing it further at the instance saves nothing -
   and a filter the instance did not apply would answer every combo to a client that asked for one,
   silently. Keeping it out of the wire read makes the same request of every major, and the grouped
   answer is narrowed exactly.

A DELETED VALUE IS NOT PART OF THE ANSWER. `includeDeleted` is not passed, so a soft-deleted value
is absent - which is what a read of what the instance holds now means.

WHAT `reader` IS HERE IS THE POINT OF THE PARAMETER, as it is for the register: every read takes a
`RegisterReader` and never a `Dhis2Client`, so whose credentials the values are read under is settled
per request. Under `[serve] auth = "dhis2"` it is the caller's own header, and DHIS2 enforces sharing
on the data set, on the category options behind both the category option combos and the attribute
option combos, and the organisation unit against the caller's data view scope. Those refusals do not
all look like the register's: an unshared tracked entity is a 404, while an organisation unit outside
the caller's scope is a refusal carrying a message. See `dhis2w_fhir_serve.passthrough`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_client.generated.v42.oas import DataValueSet

if TYPE_CHECKING:
    from dhis2w_fhir_serve.passthrough import RegisterReader

#: Where a data set's values are exported from.
DATA_VALUE_SETS_PATH = "/api/dataValueSets"


async def fetch_data_values(
    reader: RegisterReader,
    *,
    data_set_uid: str,
    organisation_unit_uid: str,
    period_isos: tuple[str, ...],
) -> DataValueSet:
    """Read one data set's values for one organisation unit over the periods a request named.

    The periods ride as repeated `period=` values, which is how the endpoint takes several of them,
    and the answer is validated into the generated envelope rather than walked as a raw body.
    """
    parameters: dict[str, Any] = {
        "dataSet": data_set_uid,
        "orgUnit": organisation_unit_uid,
        "period": list(period_isos),
    }
    return DataValueSet.model_validate(await reader.get_raw(DATA_VALUE_SETS_PATH, params=parameters))

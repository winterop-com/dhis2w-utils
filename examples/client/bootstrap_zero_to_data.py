"""End-to-end bootstrap — from zero org unit to a data value in one script.

Mirrors upstream `example_5_zero_to_data.py`. Walks through the full chain
you'd hit when wiring a fresh DHIS2 for a new locality:

1. Create an org unit under the Sierra Leone root.
2. Grant admin capture + view access on that org unit.
3. Create a data element.
4. Create a monthly data set linking the DE + the OU.
5. Grant admin data-write sharing on the data set.
6. POST a data value against it.
7. Tear it all back down (reverse order so FK constraints are happy).

Useful both as a worked example and as a smoke-test for the write paths
on a freshly-booted instance. Runs idempotent against reruns because
UIDs are minted server-side via /api/system/id.

Usage:
    uv run python examples/client/bootstrap_zero_to_data.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from _runner import run_example
from dhis2w_client import (
    ACCESS_READ_WRITE_DATA,
    DataValue,
    DataValueSet,
    Dhis2Client,
    SharingBuilder,
    apply_sharing,
    generate_uid,
)

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import AggregationType, DataElementDomain, PeriodType, ValueType
from dhis2w_client.generated.v42.schemas import DataElement, DataSet, DataSetElement, OrganisationUnit
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

PARENT_OU_UID = "PMa2VCrupOd"  # Kambia — seeded level-2 OU that's already in admin's capture scope,
# so a new OU under it inherits write access without needing a user-PATCH dance.


async def _default_category_combo(client: Dhis2Client) -> str:
    """Fetch the built-in default category combo UID via the typed accessor."""
    combos = await client.resources.category_combos.list(filters=["name:eq:default"], fields="id")
    return str(combos[0].id)


def _step(label: str) -> None:
    print(f"\n>>> {label}")


async def main() -> None:
    """Run the seven-step bootstrap, then clean up."""
    async with open_client(profile_from_env()) as client:
        ou_uid = generate_uid()
        de_uid = generate_uid()
        ds_uid = generate_uid()
        me = await client.system.me()
        admin_uid = str(me.id)
        cc_uid = await _default_category_combo(client)
        print(f"minted: ou={ou_uid} de={de_uid} ds={ds_uid} admin={admin_uid} cc={cc_uid}")

        # Built up-front so the cleanup block can reference it even if an early step fails.
        dv_payload = DataValueSet(
            dataValues=[DataValue(dataElement=de_uid, period="202603", orgUnit=ou_uid, value="42")],
        )

        try:
            # 1. CREATE ORG UNIT
            _step("1/7 create org unit")
            await client.resources.organisation_units.create(
                OrganisationUnit(
                    id=ou_uid,
                    code=f"EX_OU_{ou_uid}",
                    name=f"Example clinic {ou_uid}",
                    shortName=f"Ex {ou_uid[:6]}",
                    openingDate=datetime(2025, 1, 1),
                    parent=Reference(id=PARENT_OU_UID),
                ),
            )

            # 2. CAPTURE + VIEW SCOPE is inherited from the parent OU (Kambia is already
            #    in admin's capture scope per the seeded e2e fixture, so any child of it
            #    is writable by admin without touching /api/users/{id}). Left as a
            #    one-liner instead of a no-op step so the original "grant user
            #    explicit access" pattern is still visible in comment form:
            #      PATCH /api/users/{admin_uid}
            #        [{"op":"add","path":"/organisationUnits/-","value":{"id": ou_uid}},
            #         {"op":"add","path":"/dataViewOrganisationUnits/-","value":{"id": ou_uid}}]
            #    Use that shape when creating a sibling-of-scope OU (e.g. parented at
            #    the country root) which WON'T inherit.

            # 3. CREATE DATA ELEMENT
            _step("3/7 create data element")
            await client.resources.data_elements.create(
                DataElement(
                    id=de_uid,
                    code=f"EX_DE_{de_uid}",
                    name=f"Example indicator {de_uid}",
                    shortName=f"Ex DE {de_uid[:6]}",
                    domainType=DataElementDomain.AGGREGATE,
                    valueType=ValueType.INTEGER_ZERO_OR_POSITIVE,
                    aggregationType=AggregationType.SUM,
                    categoryCombo=Reference(id=cc_uid),
                ),
            )

            # 4. CREATE DATA SET (w/ DE + OU assignments)
            _step("4/7 create data set linking DE + OU")
            await client.resources.data_sets.create(
                DataSet(
                    id=ds_uid,
                    code=f"EX_DS_{ds_uid}",
                    name=f"Example monthly dataset {ds_uid}",
                    shortName=f"Ex DS {ds_uid[:6]}",
                    periodType=PeriodType.MONTHLY,
                    categoryCombo=Reference(id=cc_uid),
                    dataSetElements=[DataSetElement(dataElement=Reference(id=de_uid), dataSet=Reference(id=ds_uid))],
                    organisationUnits=[Reference(id=ou_uid)],
                    openFuturePeriods=0,
                    timelyDays=15,
                ),
            )

            # 5. GRANT ADMIN DATA-WRITE SHARING ON THE DATASET
            #
            # Typed helper — builds the sharing-object wire shape and POSTs it
            # to `/api/sharing?type=dataSet&id=<uid>`. Replaces the raw JSON
            # Patch pattern — cleaner, typed, and covered by respx tests.
            _step("5/7 grant admin data-write sharing on the dataset")
            sharing = SharingBuilder(owner_user_id=admin_uid).grant_user(admin_uid, ACCESS_READ_WRITE_DATA)
            await apply_sharing(client, "dataSet", ds_uid, sharing)

            # 6. POST ONE DATA VALUE — reuse the typed `DataValueSet` built above.
            _step("6/7 POST a data value against the new DS/DE/OU")
            response: dict[str, Any] = await client.post_raw(
                "/api/dataValueSets",
                dv_payload.model_dump(exclude_none=True),
            )
            print(f"    importCount: {json.dumps(response.get('response', {}).get('importCount', {}))}")

        finally:
            # 7. CLEANUP — soft-delete the data value first, then metadata in reverse dependency
            #    order (DS -> DE -> OU). The data-value delete is important: DHIS2 refuses to delete
            #    DataElements or OrgUnits referenced by any stored data value. With audits / changelogs
            #    disabled in infra/home/dhis.conf, the metadata delete then completes cleanly.
            _step("7/7 cleanup: delete data value -> DS -> DE -> OU")
            try:
                await client.post_raw(
                    "/api/dataValueSets",
                    dv_payload.model_dump(exclude_none=True),
                    params={"importStrategy": "DELETE"},
                )
                print("    deleted data value")
            except Exception as exc:  # noqa: BLE001
                print(f"    skipped data value delete: {exc}")
            cleanups = [
                ("dataSets", ds_uid, client.resources.data_sets.delete),
                ("dataElements", de_uid, client.resources.data_elements.delete),
                ("organisationUnits", ou_uid, client.resources.organisation_units.delete),
            ]
            for resource, uid, delete_fn in cleanups:
                try:
                    await delete_fn(uid)
                    print(f"    deleted {resource}/{uid}")
                except Exception as exc:  # noqa: BLE001
                    print(f"    skipped {resource}/{uid}: {exc}")


if __name__ == "__main__":
    run_example(main)

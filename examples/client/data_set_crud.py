"""Full CRUD lifecycle for a data set — create, assign members, read, update, delete.

Shows the assignment dance DHIS2 requires for data sets: you need to
create the data set *and* attach a list of data-set-elements referencing
existing data elements *and* a list of organisation-unit assignments in
the same POST, or you end up with an empty dataset nothing can write to.

Uses UIDs from the seeded Sierra Leone fixture (fClA2Erf6IO, PMa2VCrupOd,
etc) so the created dataset has something meaningful to reference. Cleans
up even on failure via a try/finally.

Usage:
    uv run python examples/06_data_set_crud.py

Env: same as 01_whoami.py.
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client import Dhis2Client, generate_uid

# v42 is the canonical baseline: swap `.v42` for `.v41` / `.v43` to pin another major.
from dhis2w_client.generated.v42.common import Reference
from dhis2w_client.generated.v42.enums import PeriodType
from dhis2w_client.generated.v42.schemas import DataSet, DataSetElement
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

# Seeded UIDs from infra/v42/dump.sql.gz — see docs/local-setup.md.
DATA_ELEMENT_UIDS = ["fClA2Erf6IO", "UOlfIjgN8X6", "I78gJm4KBo7"]
ORG_UNIT_UIDS = ["PMa2VCrupOd", "kJq2mPyFEHo"]


async def _default_category_combo(client: Dhis2Client) -> str:
    """Fetch the built-in default category combo UID via the typed accessor."""
    combos = await client.resources.category_combos.list(filters=["name:eq:default"], fields="id")
    return str(combos[0].id)


async def main() -> None:
    """Walk a data set through its full lifecycle."""
    async with open_client(profile_from_env()) as client:
        uid = generate_uid()
        print(f"minted UID: {uid}")
        category_combo_uid = await _default_category_combo(client)

        new_dataset = DataSet(
            id=uid,
            code=f"EX_DS_{uid}",
            name=f"Example monthly dataset {uid}",
            shortName=f"Ex DS {uid[:6]}",
            periodType=PeriodType.MONTHLY,
            categoryCombo=Reference(id=category_combo_uid),
            dataSetElements=[
                DataSetElement(dataElement=Reference(id=de_uid), dataSet=Reference(id=uid))
                for de_uid in DATA_ELEMENT_UIDS
            ],
            organisationUnits=[Reference(id=ou_uid) for ou_uid in ORG_UNIT_UIDS],
            openFuturePeriods=0,
            timelyDays=15,
        )
        created = await client.resources.data_sets.create(new_dataset)
        print(f"\nCREATE  {created.get('status', '?')}  uid={uid}")

        try:
            fetched = await client.resources.data_sets.get(
                uid,
                fields=(
                    "id,code,name,periodType,timelyDays,"
                    "dataSetElements[dataElement[id,name]],"
                    "organisationUnits[id,name]"
                ),
            )
            print(
                f"READ    id={fetched.id}  periodType={fetched.periodType}  "
                f"elements={len(fetched.dataSetElements or [])}  orgunits={len(fetched.organisationUnits or [])}"
            )

            # JSON Patch for partial update — no typed accessor today; raw by design.
            await client.patch_raw(
                f"/api/dataSets/{uid}",
                [{"op": "replace", "path": "/timelyDays", "value": 30}],
            )
            updated = await client.resources.data_sets.get(uid, fields="id,name,timelyDays,lastUpdated")
            print(f"PATCH   timelyDays={updated.timelyDays}  lastUpdated={updated.lastUpdated}")
        finally:
            deleted = await client.resources.data_sets.delete(uid)
            print(f"\nDELETE  {deleted.get('status', '?')}  uid={uid}")


if __name__ == "__main__":
    run_example(main)

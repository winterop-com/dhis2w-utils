"""The whole chain in one run: scaffold a project, serve it, capture a form, forward it, read the value out of DHIS2.

Every other example in this directory is deliberately about one link. This one is deliberately the
whole chain, committed against a real instance, because a reader who has understood every link still
has to see them joined. Each link has its own file, and those are the ones to read first:

- [`build_aggregate_response.py`](build_aggregate_response.py) - what an aggregate submission carries.
- [`send_response.py`](send_response.py) - what a facade does with one, and why a 201 is not an import.
- [`forward_spool.py`](forward_spool.py) - what a drain reports, dry run by default.

Eight steps, one printed line each:

1. Scaffold a project selecting one data set. Offline, no SUSHI, no docker.
2. Serve it in-process - `create_app` under its own lifespan, reached over an ASGI transport, no port
   bound. The startup builds the guide off the instance, which is why the project needs no compile.
3. `$generate` fills the served form: a postable skeleton carrying real period and place.
4. Answer one question with a number this file states, so there is one value to go looking for.
5. POST it. The facade stores a receipt; DHIS2 has still never heard of it.
6. `forward_responses(import_responses=True)` - the drain that commits.
7. Read the number back out of `/api/dataValueSets` with the dhis2w client.
8. Post the same envelope under `importStrategy=DELETE`, which takes every value back off.

**This run writes to DHIS2 and then removes what it wrote.** It reports into the first monthly period
the data set holds no value at, so its cleanup deletes exactly what it created and can never remove a
value it did not write. It registers no data set completeness for the same reason: a registration is
not a data value, and `importStrategy=DELETE` would not take it back. The scratch project directory
goes at the end of the run whatever happens.

Usage:
    uv run python examples/fhir/client/fhir_to_dhis2_end_to_end.py

Requires a DHIS2 profile (`d2w profile list`) and the `[serve]` extra - `uv sync --all-extras`.
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
from _runner import run_example
from dhis2w_client import Profile
from dhis2w_core.client_context import open_client
from dhis2w_fhir import InitOptions, load_project, service
from dhis2w_fhir.conversion import PERIOD_ISO_SUB_EXTENSION
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from pydantic import BaseModel, ConfigDict

#: Child Health in the seeded Sierra Leone instance: monthly, and assigned to the districts. One data
#: set is the whole selection, which is what keeps the scaffold and the live build a few seconds.
DATA_SET_ID = "BfMAe6Itzgt"

#: How deep the published organisation-unit registry goes: level 2 is fourteen Locations, not a thousand.
MAXIMUM_ORGANISATION_UNIT_LEVEL = 2

#: The number this run reports, chosen to be one nothing else would have written.
REPORTED_VALUE = 4207

#: How many months ahead the run will look for a period the data set holds no value at.
MAXIMUM_PERIODS_SEARCHED = 12

#: The host the in-process facade answers under. Nothing resolves it: every request goes straight
#: into the application through an ASGI transport, so no port is bound and none has to be free.
FACADE_BASE_URL = "http://end-to-end.example"

FHIR_JSON = "application/fhir+json"
CREATED = 201
FACADE_TIMEOUT_SECONDS = 60.0

#: The scaffold `d2w fhir init` writes - `fhir.toml` plus the SUSHI skeleton, written offline.
INIT_OPTIONS = InitOptions(
    ig_id="dhis2.fhir.endtoend",
    canonical="http://example.org/fhir/end-to-end",
    name="EndToEnd",
    title="DHIS2 FHIR End To End",
    publisher="Example Org",
    max_level=MAXIMUM_ORGANISATION_UNIT_LEVEL,
    data_set_ids=[DATA_SET_ID],
)


class Submission(BaseModel):
    """What one capture left behind: the receipt the facade minted and the DHIS2 keys it will land on."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    period: str
    organisation_unit: str
    link_id: str
    """The question answered with `REPORTED_VALUE`, whose text before the dot is the data element UID."""


async def main() -> None:
    """Run the chain end to end against the instance the active profile names, and clean up after it."""
    project_root = Path(tempfile.mkdtemp(prefix="d2w-fhir-end-to-end-"))
    try:
        await service.init_project(project_root, INIT_OPTIONS, force=True)
        print(f"1. scaffolded a project selecting data set {DATA_SET_ID} at {project_root}")
        project = load_project(project_root)
        generation = service.resolve_generation_profile(project)
        submission = await _capture_one_submission(project_root, generation.profile)

        # The drain is the only step that writes. Completeness is left unregistered so that every
        # mark this run makes on the instance is a data value, and every data value is deleted below.
        report = await service.forward_responses(
            generation.profile, project, import_responses=True, register_completeness=False
        )
        print(f"6. drained the spool into {generation.profile.base_url}, committing: {report.counts_line}")
        if len(report.accepted) != 1:
            for outcome in report.outcomes:
                print(f"   {outcome.kind} {outcome.response_id}: {outcome.import_outcome or outcome.refusals}")
            return
        await _read_back_and_remove(generation.profile, submission)
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


async def _capture_one_submission(project_root: Path, profile: Profile) -> Submission:
    """Serve the project in-process, fill its form, answer one question, and post the result."""
    app = create_app(ServeSettings(project_dir=project_root, live=True))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=FACADE_BASE_URL,
            headers={"Accept": FHIR_JSON},
            timeout=FACADE_TIMEOUT_SECONDS,
        ) as facade,
    ):
        listing = (await facade.get("/Questionnaire")).raise_for_status().json()
        served = [entry["resource"]["id"] for entry in listing.get("entry", [])]
        if DATA_SET_ID not in served:
            raise LookupError(f"the facade serves {served}, none of which is {DATA_SET_ID}")
        print(f"2. the facade serves {len(served)} form(s), one of them Questionnaire/{DATA_SET_ID}")

        skeleton = (await facade.get(f"/Questionnaire/{DATA_SET_ID}/$generate")).raise_for_status().json()
        organisation_unit = str(skeleton["subject"]["reference"]).rsplit("/", 1)[-1]
        period = await _unreported_period(profile, organisation_unit)
        _set_reporting_period(skeleton, period)
        print(f"3. $generate filled it for organisation unit {organisation_unit}, period moved to {period}")

        link_id = _answer_one_question(skeleton.get("item", []))
        print(f"4. answered question {link_id} with {REPORTED_VALUE}")

        created = await facade.post("/QuestionnaireResponse", json=skeleton, headers={"Content-Type": FHIR_JSON})
        if created.status_code != CREATED:
            raise RuntimeError(f"the facade refused the submission: {created.status_code} {created.text}")
        receipt_id = created.headers["location"].rsplit("/", 1)[-1]
        print(f"5. the facade stored receipt {receipt_id}; DHIS2 has not heard of it yet")
    return Submission(receipt_id=receipt_id, period=period, organisation_unit=organisation_unit, link_id=link_id)


async def _unreported_period(profile: Profile, organisation_unit: str) -> str:
    """The first monthly period from this one on that the data set holds no value at, at that place.

    `$generate` dates its skeleton at the last completed period, which on a seeded instance is a
    period full of values. Reporting into an empty one is what lets the cleanup at the end post the
    whole envelope back under DELETE rather than pick this run's values out of somebody else's.
    """
    today = datetime.date.today()
    async with open_client(profile) as client:
        for month in range(MAXIMUM_PERIODS_SEARCHED):
            index = today.year * 12 + today.month - 1 + month
            candidate = f"{index // 12:04d}{index % 12 + 1:02d}"
            parameters = {"dataSet": DATA_SET_ID, "period": candidate, "orgUnit": organisation_unit}
            if not (await client.get_raw("/api/dataValueSets", params=parameters)).get("dataValues"):
                return candidate
    raise RuntimeError(
        f"{DATA_SET_ID} holds values at every one of the next {MAXIMUM_PERIODS_SEARCHED} months at "
        f"{organisation_unit}, so this run has no period it could report into and then clean up"
    )


def _set_reporting_period(skeleton: dict[str, Any], period: str) -> None:
    """Rewrite the ISO period the D2Period extension carries, which is the one DHIS2 imports against."""
    for extension in skeleton.get("extension", []):
        for part in extension.get("extension", []):
            # The date range riding beside the ISO identifier is decoration - the translator reads
            # the identifier and nothing else - so this one string is the whole period change.
            if part.get("url") == PERIOD_ISO_SUB_EXTENSION:
                part["valueString"] = period
                return
    raise LookupError("the generated response carries no D2Period extension to report against")


def _answer_one_question(items: list[dict[str, Any]]) -> str:
    """Answer the first integer question of the filled form with `REPORTED_VALUE`, naming which it was.

    A form's items nest - a data set's sections are groups, and a disaggregated data element is a
    group of its cells - so the walk is depth-first and the first integer it meets is the one edited.
    """
    for item in items:
        for answer in item.get("answer", []):
            if "valueInteger" in answer:
                answer["valueInteger"] = REPORTED_VALUE
                return str(item["linkId"])
        try:
            return _answer_one_question(item.get("item", []))
        except LookupError:
            continue
    raise LookupError("the filled form holds no integer answer, so there is no number to go looking for")


async def _read_back_and_remove(profile: Profile, submission: Submission) -> None:
    """Find the reported number in DHIS2 with the dhis2w client, then delete every value this run wrote."""
    data_element = submission.link_id.split(".", 1)[0]
    parameters = {"dataSet": DATA_SET_ID, "period": submission.period, "orgUnit": submission.organisation_unit}
    async with open_client(profile) as client:
        envelope = await client.get_raw("/api/dataValueSets", params=parameters)
        values = envelope.get("dataValues") or []
        landed = [value for value in values if value.get("dataElement") == data_element]
        reported = next((value for value in landed if value.get("value") == str(REPORTED_VALUE)), None)
        if reported is None:
            raise RuntimeError(f"DHIS2 holds no value {REPORTED_VALUE} for {data_element} - it holds {landed}")
        print(
            f"7. DHIS2 now holds {reported['value']} for data element {reported['dataElement']}, category "
            f"option combination {reported.get('categoryOptionCombo')}, period {submission.period}, "
            f"organisation unit {submission.organisation_unit}"
        )

        # The envelope read back is the envelope the drain posted, because the period held nothing
        # before this run. Posted again under DELETE, it takes every one of those values away.
        removal = await client.post_raw("/api/dataValueSets", envelope, params={"importStrategy": "DELETE"})
        print(f"8. removed the {len(values)} data value(s) this run wrote: {removal.get('status')}")


if __name__ == "__main__":
    run_example(main)

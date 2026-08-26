"""Resolve every part of a published form back to the DHIS2 object it came from, by identifier.

A form's `title` is a display string. It is the last thing to resolve identity from: two DHIS2
instances name things differently, an instance renames a data set on a Tuesday, and a translated
title is not the same string twice. What does not move is the identifier - so a consumer who needs
to know *which* DHIS2 object a form or a question is about reads it, and never the name.

Two places carry that identity, and they answer different questions.

* `Questionnaire.identifier` says which DHIS2 object the *form* is. Each entry names a system of
  the shape `{identifier_system_base}/id/<kind>`, and the last segment of that system is the DHIS2
  object kind: `data-set`, `program`, `program-stage`, `tracked-entity-type`. A `-code` system
  beside it holds the same object's DHIS2 code rather than its UID. A tracker form carries a third
  slice that is its grouping handle - a registration form names the tracked entity type it enrols
  a person as, a stage form names the program the stage belongs to.

* `Questionnaire.item.code` says which DHIS2 object each *question* is. It is a `Coding`, and its
  `system` is the published data dictionary the concept lives in: one CodeSystem for data
  elements, one for tracked entity attributes, one for category option combinations. The `code` is the
  DHIS2 UID and the `display` is the instance's name for it - so the code resolves and the display
  is only for showing a person.

`Questionnaire.code` completes the picture: it is the form-type Coding, and it says whether the
form was generated from a data set, an event program, a tracker program, a program stage, or a
tracked entity type.

Usage:
    uv run python examples/fhir/client/read_form_dhis2_identity.py

Reads the aggregate form and the tracker registration form the example fixture publishes - the
first asks data elements and disaggregated cells, the second asks tracked entity attributes.
"""

from __future__ import annotations

import httpx
from _fixture import aggregate_form_id, registration_form_id, served_facade
from _runner import run_example
from dhis2w_fhir.r4 import CodeSystem, Coding, Questionnaire, QuestionnaireItem

FHIR_JSON = "application/fhir+json"

#: The segment every DHIS2 identifier system carries before the object kind that names it.
IDENTIFIER_SYSTEM_SEGMENT = "/id/"

#: How many questions to resolve per form - enough to show both grammars without printing a whole data set.
RESOLVED_QUESTIONS = 6


def _questions(items: list[QuestionnaireItem] | None) -> list[QuestionnaireItem]:
    """Every item under `items` that carries a concept of its own, groups walked through and dropped."""
    found: list[QuestionnaireItem] = []
    for item in items or []:
        if item.code:
            found.append(item)
        found.extend(_questions(item.item))
    return found


def _object_kind(system: str) -> str:
    """The DHIS2 object kind one identifier system names, which is the segment after `/id/`."""
    _, _, kind = system.partition(IDENTIFIER_SYSTEM_SEGMENT)
    return kind or system


async def _dictionary_title(client: httpx.AsyncClient, system: str) -> str:
    """The title of the published data dictionary one concept was drawn from, found by its canonical."""
    # A concept's `system` is a canonical URL, not an address on this server - so it is searched
    # for rather than fetched, which is what resolves a concept against any server holding the guide.
    bundle = (await client.get("/CodeSystem", params={"url": system})).raise_for_status().json()
    entries = bundle.get("entry", [])
    return CodeSystem.model_validate(entries[0]["resource"]).title or system if entries else f"{system} (not served)"


async def _report_form(client: httpx.AsyncClient, form_id: str) -> None:
    """Print one form's own DHIS2 identity, then the DHIS2 object behind each of its first questions."""
    body = (await client.get(f"/Questionnaire/{form_id}")).raise_for_status().json()
    form = Questionnaire.model_validate(body)
    form_type: Coding | None = form.code[0] if form.code else None

    print(f"{form.title}  (published as Questionnaire/{form.id})")
    print(f"  generated from a DHIS2 {form_type.code if form_type else 'object of unstated kind'}")
    print("  this form is:")
    for identifier in form.identifier or []:
        print(f"    {_object_kind(identifier.system or ''):24} {identifier.value}")

    questions = _questions(form.item)
    dictionaries = {(question.code or [])[0].system or "" for question in questions}
    print("  its questions are drawn from:")
    for system in sorted(dictionaries):
        print(f"    {await _dictionary_title(client, system)}")
    print("  and every item naming a concept resolves to exactly one of them:")
    for question in questions[:RESOLVED_QUESTIONS]:
        concept = (question.code or [])[0]
        # The link id and the concept code are the same DHIS2 UID on a plain question. A data set's
        # disaggregated data element is a group naming the data element, with one cell under it per
        # category option combo: the cell's link id is the pair `<dataElement>.<categoryOptionCombo>`
        # and its concept is the category option combo half, which is why both are worth printing.
        print(f"    {question.linkId:26} -> {concept.code:12} {concept.display}")
    if len(questions) > RESOLVED_QUESTIONS:
        print(f"    ... and {len(questions) - RESOLVED_QUESTIONS} more item(s) resolving the same way")
    print()


async def main() -> None:
    """Resolve two published forms and every question on them back to DHIS2, by identifier alone."""
    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        await _report_form(client, aggregate_form_id())
        await _report_form(client, registration_form_id())

    print("Nothing above was read off a name: every line resolves through an identifier or a concept code.")


if __name__ == "__main__":
    run_example(main)

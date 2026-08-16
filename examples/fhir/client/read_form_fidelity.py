"""Read what a published form states beyond its questions - the DHIS2 facts R4 has no element for.

R4 gives a `Questionnaire` no place to say "this data set is reported monthly", or "this program
stage may be captured twice in one enrollment", or "this instance calls the event date *Visit
date*". DHIS2 states all three, and a capture client that did not know them would build the wrong
period, refuse a legitimate second visit, and label a date in its own words. So each rides an
extension of the guide's own, and this example reads them off the five kinds of form.

| Extension | What DHIS2 fact it carries | Which forms declare it |
| --- | --- | --- |
| `D2PeriodType` | the reporting frequency of the data set | aggregate only |
| `D2DateLabels` | the instance's own words for the dates the form collects | any form the instance labelled |
| `D2Repeatable` | whether one enrollment may capture the stage more than once | tracker program stage only |
| `D2CollectsIncidentDate` | whether the program collects the date of the incident | tracker registration only |
| `D2Description` | the DHIS2 free text about a data element, attribute, or section | any item DHIS2 describes |
| `D2AttributeValue` | a DHIS2 metadata attribute value on the source object | any form whose object holds one |

Two rules make them readable rather than guessable. **Absent means the instance states nothing**,
not "false" - a form carrying no `D2DateLabels` is one the instance labelled nothing on, and the
client uses its own wording. But `D2Repeatable` and `D2CollectsIncidentDate` are declared *either
way* on the form kind that has them, so a client never has to guess about a repeat or an incident
date. And every URL is `{canonical}/StructureDefinition/{id}`, where the ids come from the
project's own `[generate.naming]` prefix - which is why this example derives them from the project
rather than writing them out.

Usage:
    uv run python examples/fhir/client/read_form_fidelity.py

Reads all five kinds of form the example fixture publishes, from the facade the fixture serves.

The registry of every `D2*` extension is at docs/guides/fhir/401-identifiers-and-extensions.md.
"""

from __future__ import annotations

import httpx
from _fixture import (
    aggregate_form_id,
    event_form_id,
    example_project,
    person_form_id,
    registration_form_id,
    served_facade,
    stage_form_id,
)
from _runner import run_example
from dhis2w_fhir import FoundationNaming, load_project
from dhis2w_fhir.r4 import Extension, Questionnaire, QuestionnaireItem
from pydantic import BaseModel

FHIR_JSON = "application/fhir+json"

#: How many described items to quote per form before summarising the rest.
QUOTED_DESCRIPTIONS = 2


class ExtensionUrls(BaseModel):
    """The canonical URL of each declaration this example reads, built from one project's own naming."""

    period_type: str
    date_labels: str
    repeatable: str
    collects_incident_date: str
    description: str
    attribute_value: str

    @classmethod
    def of_project(cls, canonical: str, naming: FoundationNaming) -> ExtensionUrls:
        """Derive every URL as `{canonical}/StructureDefinition/{id}`, the shape the guide publishes them under."""
        return cls(
            period_type=f"{canonical}/StructureDefinition/{naming.period_type_extension_id}",
            date_labels=f"{canonical}/StructureDefinition/{naming.date_labels_extension_id}",
            repeatable=f"{canonical}/StructureDefinition/{naming.repeatable_extension_id}",
            collects_incident_date=f"{canonical}/StructureDefinition/{naming.collects_incident_date_extension_id}",
            description=f"{canonical}/StructureDefinition/{naming.description_extension_id}",
            attribute_value=f"{canonical}/StructureDefinition/{naming.attribute_value_extension_id}",
        )


def _carried(extensions: list[Extension] | None, url: str) -> list[Extension]:
    """Every extension on `extensions` carrying `url` - a list because some of them repeat."""
    return [extension for extension in extensions or [] if extension.url == url]


def _slices(extension: Extension) -> str:
    """One complex extension's sub-extensions, rendered as `slice=value` in the order it states them."""
    return ", ".join(
        f"{part.url}={part.valueString or part.valueCode or part.valueBoolean}" for part in extension.extension or []
    )


def _described_items(items: list[QuestionnaireItem] | None, url: str) -> list[QuestionnaireItem]:
    """Every item of the tree carrying DHIS2 free text about the object it is asked from."""
    found: list[QuestionnaireItem] = []
    for item in items or []:
        if _carried(item.extension, url):
            found.append(item)
        found.extend(_described_items(item.item, url))
    return found


def _report_form(form: Questionnaire, urls: ExtensionUrls) -> None:
    """Print every DHIS2 fact one form states about itself, and say plainly where it states none."""
    print(f"{form.title}  ({form.code[0].code if form.code else 'unstated'} form, Questionnaire/{form.id})")

    for extension in _carried(form.extension, urls.period_type):
        # The period type is what a client builds a valid DHIS2 ISO period from - `Monthly` is `202603`.
        print(f"  reported once per: {extension.valueCode}")
    for extension in _carried(form.extension, urls.date_labels):
        print(f"  this instance calls its dates: {_slices(extension)}")
    for extension in _carried(form.extension, urls.repeatable):
        captured = "more than once" if extension.valueBoolean else "once"
        print(f"  one enrollment captures this stage {captured}")
    for extension in _carried(form.extension, urls.collects_incident_date):
        collects = "collects" if extension.valueBoolean else "does not collect"
        print(f"  the program {collects} the date of the incident the enrollment follows")
    for extension in _carried(form.extension, urls.attribute_value):
        print(f"  a DHIS2 attribute value on the source object: {_slices(extension)}")

    described = _described_items(form.item, urls.description)
    for item in described[:QUOTED_DESCRIPTIONS]:
        text = _carried(item.extension, urls.description)[0].valueString
        print(f"  guidance on {item.linkId}: {text}")
    if len(described) > QUOTED_DESCRIPTIONS:
        print(f"  ... and DHIS2 free text on {len(described) - QUOTED_DESCRIPTIONS} more item(s) of this form")
    if not described:
        print("  this instance describes none of this form's items, so a client shows no guidance text")
    print()


async def main() -> None:
    """Read every kind of published form and print the DHIS2 facts each states beyond its questions."""
    project = load_project(example_project())
    urls = ExtensionUrls.of_project(
        project.config.ig.canonical, FoundationNaming.from_naming(project.config.generate.naming)
    )
    print(f"reading declarations under {project.config.ig.canonical}/StructureDefinition/")
    print()

    form_ids = [
        aggregate_form_id(),
        event_form_id(),
        registration_form_id(),
        stage_form_id(),
        person_form_id(),
    ]
    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        for form_id in form_ids:
            body = (await client.get(f"/Questionnaire/{form_id}")).raise_for_status().json()
            _report_form(Questionnaire.model_validate(body), urls)


if __name__ == "__main__":
    run_example(main)

"""Register a person who is enrolled in nothing: the registration contract without its enrollment half.

Not every person in DHIS2 belongs to a programme. A **tracked entity type** - Person, but equally a
household, a herd, a water point - has attributes of its own, and a bare `trackedEntities` import
stands up somebody who is findable without any programme at all. Enrolling them later is a separate
submission against a tracker programme's own registration form.

The guide publishes a form for that: one per tracked entity type, asking the attributes the *type
itself* collects. This response is `build_registration_response.py` with the enrollment half
removed - same subject shape, same organisation unit, and none of the three enrollment elements:

| Element | On a registration | Here |
| --- | --- | --- |
| `subject.identifier` | required | required, same system |
| `D2OrganisationUnit` | required | required |
| `D2FormType` | `tracker` | `tracked-entity` |
| `D2TrackerEnrollment` | required | not carried |
| `D2EnrolledAt` | required | not carried |
| `D2IncidentAt` | optional | not carried |

That is not a degraded registration - it is what DHIS2 accepts. And because every question of such a
form asks an attribute of the type itself, every answer is written onto the person. There is no
enrollment to split them across, which is why this form has no question the forwarder could put in
the wrong place.

The client still mints the tracked entity UID, for the same reason: nothing on the instance holds it
until this response is imported.

Usage:
    uv run python examples/fhir/client/build_person_response.py

Requires a DHIS2 profile (`d2w profile list`). The UID is minted on every run.
"""

from __future__ import annotations

from _fixture import conversion_context, form_canonical, person_form_id
from _runner import run_example
from dhis2w_client import generate_uid
from dhis2w_fhir import translate_response
from dhis2w_fhir.r4 import (
    Extension,
    Identifier,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Gbenikoro MCHP - the organisation unit that will own this person's record.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

#: When the capture was made. Required on this contract, as on every kind but the aggregate one.
AUTHORED = "2026-01-19T14:00:00"

#: What the form was filled in with, by tracked entity attribute UID.
ANSWERS = {
    "w75KJ2mc4zz": "Fatmata",
    "zDhUuAYrxNC": "Sesay",
    "lZGmxYbs97q": "TB-2026-0184",
}


async def main() -> None:
    """Create one person who is enrolled in nothing, and prove every answer lands on their record."""
    context = conversion_context()
    canonical = form_canonical(person_form_id())
    form = context.forms[canonical]

    tracked_entity_uid = generate_uid()
    print(f"minted tracked entity {tracked_entity_uid} of type {form.tracked_entity_type_uid}")
    print(f"every question of this form is at the entity level: {all(q.entity_level for q in form.questions.values())}")

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        authored=AUTHORED,
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="tracked-entity"),
            # The organisation unit that owns the person's record. Without an enrollment this is the
            # only place a DHIS2 tracked entity is anchored, which is why it stays required.
            Extension(
                url=context.naming.organisation_unit_url,
                valueReference=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
            ),
        ],
        subject=Reference(
            type="Patient",
            identifier=Identifier(system=context.naming.tracked_entity_system, value=tracked_entity_uid),
        ),
        item=[
            QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueString=value)])
            for link_id, value in ANSWERS.items()
        ],
    )

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof: a tracked entity carrying every answer, and no enrollment anywhere on it.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.tracked_entity is not None:
        print(
            f"\nconverts to a {result.target_kind}: tracked entity {result.tracked_entity.trackedEntity} "
            f"of type {result.tracked_entity.trackedEntityType} at {result.tracked_entity.orgUnit}, "
            f"{len(result.tracked_entity.attributes or [])} attribute(s), "
            f"{len(result.tracked_entity.enrollments or [])} enrollment(s)"
        )
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


if __name__ == "__main__":
    run_example(main)

"""Register a person and enrol them in a programme, minting both DHIS2 identities client-side.

A DHIS2 **tracker programme** keeps a longitudinal record. Enrolling someone creates two objects at
once: a **tracked entity** - the person - and an **enrollment** - their participation in that one
programme. The programme's registration form asks the **tracked entity attributes** both are built
from, and the answers split across the two: some describe the person, some describe the enrollment.

Three things make this envelope different from every other.

**The client mints both UIDs.** Nothing on the instance holds either yet, because this response is
what creates them. A DHIS2 UID is eleven characters, the first an ASCII letter and the rest
alphanumeric; `generate_uid()` draws one. That is what lets a client enrol a person and capture the
enrollment's first visits in one breath, naming the enrollment before any of it is sent - see
`build_stage_response.py`.

**The subject is identified, not referenced.** The guide publishes no `Patient` resources: DHIS2
holds the people and the guide describes forms. So `subject` carries no `reference` at all. It
carries an **identifier** - a value plus the system that value is meaningful in - which is FHIR's
way of saying "this subject is real, and it lives in a system this document does not contain".

**The organisation unit moves off the subject.** The subject is now the person, so the place the
registration happened rides on its own `D2OrganisationUnit` extension. That is the one structural
difference between the two aggregate-style kinds and the three tracker ones.

| DHIS2 fact | Where it rides |
| --- | --- |
| which programme | `questionnaire` |
| the person's UID | `subject.identifier`, system `{base}/id/tracked-entity` |
| what kind of thing the subject is | `subject.type` - a person tracks as `Patient` |
| the enrollment's UID | the `D2TrackerEnrollment` extension, a `valueIdentifier` |
| when the enrollment begins | the `D2EnrolledAt` extension |
| where the person is registered | the `D2OrganisationUnit` extension, a reference to a `Location` |
| this is a registration | the `D2FormType` extension, `valueCode` of `tracker` |

A facade checks the two minted UIDs for **shape and nothing else**. Whether the instance already
holds that UID, and whether a `unique` attribute's value is already taken, are global instance
state that no facade holds - DHIS2 refuses the duplicate at import instead.

Usage:
    uv run python examples/fhir/client/build_registration_response.py

Requires a DHIS2 profile (`d2w profile list`). Two UIDs are minted on every run, so the printed
response differs each time.
"""

from __future__ import annotations

from _fixture import conversion_context, form_canonical, registration_form_id
from _runner import run_example
from dhis2w_client import generate_uid
from dhis2w_fhir import translate_response
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    Identifier,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Gbenikoro MCHP, a facility the seeded instance assigns the Child Programme to.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

#: When the enrollment begins, and when the capture was made. Both are required on this contract.
ENROLLED_AT = "2026-01-19T09:00:00"

#: What the registration form was filled in with, by tracked entity attribute UID.
FIRST_NAME_ATTRIBUTE = "w75KJ2mc4zz"
LAST_NAME_ATTRIBUTE = "zDhUuAYrxNC"
GENDER_ATTRIBUTE = "cejWyOfXge6"

TEXT_ANSWERS = {FIRST_NAME_ATTRIBUTE: "Aminata", LAST_NAME_ATTRIBUTE: "Kamara"}

#: The gender answer is a coded one: the attribute is bound to a DHIS2 option set, so the form asks
#: for a concept out of that option set's published CodeSystem rather than for free text.
GENDER_CODE = "Mnp3oXrpAbK"


async def main() -> None:
    """Register one person, enrol them, and prove the response creates both DHIS2 objects."""
    context = conversion_context()
    canonical = form_canonical(registration_form_id())
    form = context.forms[canonical]

    # The two identities this response brings into existence. Nothing has been sent yet.
    tracked_entity_uid = generate_uid()
    enrollment_uid = generate_uid()
    print(f"minted tracked entity {tracked_entity_uid} and enrollment {enrollment_uid}")

    # Which side of the record each answer lands on is the form's statement, not the client's: a
    # question marked entity level asks the person's own record, the rest ride the enrollment.
    for link_id, question in form.questions.items():
        side = "the person" if question.entity_level else "the enrollment"
        print(f"  {link_id}  answers {question.answer_element:14} written onto {side}")

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        authored=ENROLLED_AT,
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="tracker"),
            # The place. A reference to the unit's published Location, exactly as an aggregate
            # response's subject is - it has simply moved off `subject`, which the person now holds.
            Extension(
                url=context.naming.organisation_unit_url,
                valueReference=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
            ),
            # The enrollment, named rather than described. No resource is invented for it: the
            # identifier says which DHIS2 enrollment this is, under the system that means "an
            # enrollment UID".
            Extension(
                url=context.naming.tracker_enrollment_url,
                valueIdentifier=Identifier(
                    system=context.naming.tracker_enrollment_system,
                    value=enrollment_uid,
                ),
            ),
            Extension(url=context.naming.enrolled_at_url, valueDateTime=ENROLLED_AT),
        ],
        subject=Reference(
            type="Patient",
            identifier=Identifier(system=context.naming.tracked_entity_system, value=tracked_entity_uid),
        ),
        item=[
            *(
                QuestionnaireResponseItem(linkId=link_id, answer=[QuestionnaireResponseAnswer(valueString=value)])
                for link_id, value in TEXT_ANSWERS.items()
            ),
            QuestionnaireResponseItem(
                linkId=GENDER_ATTRIBUTE,
                answer=[
                    QuestionnaireResponseAnswer(
                        valueCoding=Coding(
                            system=form.questions[GENDER_ATTRIBUTE].option_system,
                            code=GENDER_CODE,
                        )
                    )
                ],
            ),
        ],
    )

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof, and the split made visible: one response, two DHIS2 objects, the answers divided
    # between them by what the form said about each question.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.tracked_entity is not None:
        print(
            f"\nconverts to a {result.target_kind}: tracked entity {result.tracked_entity.trackedEntity} "
            f"at {result.tracked_entity.orgUnit}, "
            f"{len(result.tracked_entity.attributes or [])} attribute(s) on the person"
        )
        # The enrollment rides inside the person, because the two are created by one `/api/tracker`
        # post: DHIS2 cannot enrol somebody it does not have yet.
        for enrollment in result.tracked_entity.enrollments or []:
            print(
                f"  enrollment {enrollment.enrollment} in programme {enrollment.program}, "
                f"enrolled {enrollment.enrolledAt}, "
                f"{len(enrollment.attributes or [])} attribute(s) on the enrollment"
            )
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


if __name__ == "__main__":
    run_example(main)

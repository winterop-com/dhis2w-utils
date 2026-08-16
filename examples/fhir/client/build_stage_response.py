"""Capture one visit for a person the instance already holds: naming the subject and their enrollment.

A DHIS2 **program stage** is one kind of visit in a tracker programme - Birth, Baby Postnatal, the
third antenatal check. Capturing one means saying four things DHIS2 needs and a client cannot guess:
which stage form, which person, which enrollment of theirs, and when.

The person and the enrollment already exist. That is the whole difference from
`build_registration_response.py`, which mints both: here the two UIDs come from the instance, and
**the guide is not where a client finds them**. The IG describes forms, not people. Resolving "this
mother, in the Child Programme" to a pair of UIDs is a DHIS2 operation - `d2w data tracker
enrollment list` on the command line, or the read this example does below.

The envelope is the registration envelope with the *dates* removed. It names an enrollment that
exists rather than dating one it creates, so there is no `D2EnrolledAt` and no `D2IncidentAt`:

| DHIS2 fact | Where it rides |
| --- | --- |
| which stage | `questionnaire` - one form per program stage |
| which person | `subject.identifier`, system `{base}/id/tracked-entity` |
| which enrollment | the `D2TrackerEnrollment` extension, a `valueIdentifier` |
| where the visit happened | the `D2OrganisationUnit` extension |
| when it happened | `authored` |
| this is a stage capture | the `D2FormType` extension, `valueCode` of `tracker-event` |

A stage form also says whether the stage **repeats** - the `D2Repeatable` extension - so a client
knows whether one enrollment may hold several events of it before offering to add another.

Usage:
    uv run python examples/fhir/client/build_stage_response.py

Requires a DHIS2 profile (`d2w profile list`) and at least one enrollment in the tracker programme.
"""

from __future__ import annotations

from _fixture import FixtureError, conversion_context, example_project, form_canonical, stage_form_id
from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_fhir import load_project, service, translate_response
from dhis2w_fhir.r4 import (
    Extension,
    Identifier,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: Where the visit happened - Gbenikoro MCHP, one of the organisation units this guide publishes.
#:
#: This is the clinic the event was captured at, which is a different fact from where the person was
#: registered: somebody enrolled at one facility is seen at another all the time, and DHIS2 stores
#: the event against the place it happened. So a client names the unit it is capturing at rather
#: than echoing the enrollment's.
ORGANISATION_UNIT_UID = "y77LiPqLMoq"

#: When the visit happened.
OCCURRED_AT = "2026-01-19T11:15:00"

#: What was recorded at the birth, by data element UID: Apgar score, then weight in grams.
APGAR_SCORE_ELEMENT = "a3kGcGDCuk6"
BIRTH_WEIGHT_ELEMENT = "UXz7xuGCEhU"
RECORDED = {APGAR_SCORE_ELEMENT: 9, BIRTH_WEIGHT_ELEMENT: 3250}


async def main() -> None:
    """Read one existing enrollment off the instance, then capture a stage event against it."""
    context = conversion_context()
    canonical = form_canonical(stage_form_id())
    form = context.forms[canonical]

    # Where the two UIDs come from: DHIS2, never the guide. The stage form states which programme it
    # belongs to, which is what makes this read possible from the form alone.
    generation = service.resolve_generation_profile(load_project(example_project()))
    async with open_client(generation.profile) as client:
        enrollments = await client.tracker.outstanding(form.program_uid or "")
    if not enrollments:
        raise FixtureError(
            f"the instance holds no enrollment of programme {form.program_uid} that is missing a stage event: "
            f"enrol somebody first, or point this example at an instance that has one"
        )
    enrollment = enrollments[0]
    print(f"programme {form.program_uid}, stage {form.program_stage_uid}")
    print(f"  person     {enrollment.tracked_entity}")
    print(f"  enrollment {enrollment.enrollment}")
    print(f"  registered at organisation unit {enrollment.org_unit}")
    print(f"  this visit is captured at    {ORGANISATION_UNIT_UID}")

    response = QuestionnaireResponse(
        questionnaire=canonical,
        status="completed",
        authored=OCCURRED_AT,
        extension=[
            Extension(url=context.naming.form_type_url, valueCode="tracker-event"),
            Extension(
                url=context.naming.organisation_unit_url,
                valueReference=Reference(reference=f"Location/{ORGANISATION_UNIT_UID}"),
            ),
            # Which of this person's enrollments the visit belongs to. A person may be enrolled in
            # several programmes, and in the same programme more than once, so the event has to say.
            Extension(
                url=context.naming.tracker_enrollment_url,
                valueIdentifier=Identifier(
                    system=context.naming.tracker_enrollment_system,
                    value=enrollment.enrollment,
                ),
            ),
        ],
        # The person the visit is about, named by their DHIS2 UID. No `reference`: a tracker
        # response that also carries one is stored, with a warning saying the reference is ignored.
        subject=Reference(
            type="Patient",
            identifier=Identifier(
                system=context.naming.tracked_entity_system,
                value=enrollment.tracked_entity,
            ),
        ),
        item=[
            QuestionnaireResponseItem(
                linkId=link_id,
                answer=[QuestionnaireResponseAnswer(valueDecimal=recorded)],
            )
            for link_id, recorded in RECORDED.items()
        ],
    )

    print()
    print(response.model_dump_json(indent=2, exclude_none=True, by_alias=True))

    # The proof: the event names the person, the enrollment, and the stage - the three things that
    # place it in an existing record rather than starting a new one.
    result = translate_response(response, context)
    for refusal in result.refusals:
        print(f"refused [{refusal.category}] {refusal.reason}")
    if result.event is not None:
        print(
            f"\nconverts to a {result.target_kind}: programme {result.event.program}, "
            f"stage {result.event.programStage}, person {result.event.trackedEntity}, "
            f"enrollment {result.event.enrollment}, occurred {result.event.occurredAt}, "
            f"{len(result.event.dataValues or [])} data value(s)"
        )
    for note in result.notes:
        print(f"note [{note.category}] {note.message}")


if __name__ == "__main__":
    run_example(main)

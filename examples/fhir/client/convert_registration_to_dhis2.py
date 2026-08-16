"""One captured registration beside the tracked entity and enrollment it becomes - offline, no server.

A tracker programme's registration form enrols a person, and the response answering it is the
only capture that *creates* DHIS2 identities rather than referring to them. Both UIDs are the
client's: it draws a tracked entity UID and an enrollment UID before it sends anything, which is
what lets the same client capture that enrollment's first stage events in the same breath.

Where each thing rides, since a tracker response's subject is the person rather than the place:

    `subject.identifier`     ->  `trackedEntity`   the DHIS2 UID of the person, under
                                                   `{base}/id/tracked-entity`. No `Patient` is
                                                   published anywhere: the guide describes forms,
                                                   and DHIS2 holds the people.
    `D2OrganisationUnit`     ->  `orgUnit`         the unit that owns the person and the enrollment.
    `D2TrackerEnrollment`    ->  `enrollment`      the enrollment UID the client minted.
    `D2EnrolledAt`           ->  `enrolledAt`      when the enrollment begins, required.
    `D2IncidentAt`           ->  `occurredAt`      the incident it follows, where the programme
                                                   collects one.
    an answered item         ->  one `attributes` entry, keyed by the tracked entity attribute UID
                                                   its `linkId` is - written onto the person or onto
                                                   the enrollment, by what the *form* says about that
                                                   question's `D2EntityLevel`.

The second half of this file is the fork worth knowing about. A registration response may state
`D2SubjectExists = true`, meaning the subject identifier names a person the instance already
holds, and then the same form produces a different payload under a different `/api/tracker` key:

    creating the person   ->  a `trackedEntities` entry with the enrollment nested inside it
    enrolling an existing ->  a top-level `enrollments` entry, and no person at all

That is not a formatting preference. An enrollment nested in a `trackedEntities` wrapper has to
be posted `importStrategy=CREATE_AND_UPDATE`, and DHIS2 then silently rewrites the person's
owning organisation unit to the one on the payload (BUGS.md 73). A person this response did not
create is not this response's to move, so the wrapper is never written - and the programme's own
attributes ride the enrollment, because DHIS2 answers `E1018` to a mandatory programme attribute
that arrives on nothing.

For the same reason, an *optional* answer to a question the form marks `D2EntityLevel true` -
a question of the person's own record - refuses the whole response when the subject already
exists, rather than being dropped or written onto a record this capture does not own.

Usage:
    uv run python examples/fhir/client/convert_registration_to_dhis2.py

Reads the example project's guide through the shared fixture; see the README beside this file.
"""

from __future__ import annotations

from _fixture import conversion_context, registration_form_id
from dhis2w_fhir import ConversionContext, ConversionResult, translate_response
from dhis2w_fhir.conversion import FormSpec, QuestionSpec
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    Identifier,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)

#: The two DHIS2 UIDs the client mints - eleven characters, first an ASCII letter. Nothing on the
#: instance holds either one until the payload below is imported.
NEW_TRACKED_ENTITY_UID = "TeZzYyXxWw9"
NEW_ENROLLMENT_UID = "EnAaBbCcDd1"

#: The UID of a person the instance already holds, for the second half of this file.
EXISTING_TRACKED_ENTITY_UID = "TeAlreadyH1"
EXISTING_SUBJECT_ENROLLMENT_UID = "EnAaBbCcDd2"

#: When the capture was made, when the enrollment begins, and when the incident it follows occurred.
CAPTURED_AT = "2026-01-04T08:00:00+00:00"
ENROLLED_AT = "2026-01-04T08:00:00+00:00"
INCIDENT_AT = "2025-12-28T00:00:00+00:00"

#: What this example answers the person's own text questions with.
ANSWERED_TEXT = ("Amina", "Sesay")


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _entity_level_questions(form: FormSpec) -> list[QuestionSpec]:
    """The questions the form asks of the person's own record, which is where their answers are written."""
    return [question for question in form.questions.values() if question.entity_level is not False]


def _enrollment_level_questions(form: FormSpec) -> list[QuestionSpec]:
    """The questions only the programme asks, whose answers are written onto the enrollment it creates."""
    return [question for question in form.questions.values() if question.entity_level is False]


def _answer_for(context: ConversionContext, question: QuestionSpec, index: int) -> QuestionnaireResponseAnswer:
    """One answer in the element the question asks it on - a coded one drawn from the served terminology."""
    if question.option_system is not None:
        table = context.option_tables.get(question.option_system)
        entry = table.entries[0] if table is not None and table.entries else None
        code = entry.concept_code if entry is not None else "unknown"
        return QuestionnaireResponseAnswer(valueCoding=Coding(system=question.option_system, code=code))
    return QuestionnaireResponseAnswer(valueString=ANSWERED_TEXT[index % len(ANSWERED_TEXT)])


def _registration_response(
    context: ConversionContext,
    form: FormSpec,
    location_id: str,
    items: list[QuestionnaireResponseItem],
    *,
    tracked_entity_uid: str,
    enrollment_uid: str,
    subject_exists: bool,
) -> QuestionnaireResponse:
    """Build the registration submission by hand, exactly as a capture client would post it."""
    naming = context.naming
    extensions = [
        Extension(url=naming.form_type_url, valueCode=form.form_kind),
        # A tracker response's subject is the person, so the place rides an extension of its own.
        Extension(url=naming.organisation_unit_url, valueReference=Reference(reference=f"Location/{location_id}")),
        Extension(
            url=naming.tracker_enrollment_url,
            valueIdentifier=Identifier(system=naming.tracker_enrollment_system, value=enrollment_uid),
        ),
        Extension(url=naming.enrolled_at_url, valueDateTime=ENROLLED_AT),
        Extension(url=naming.incident_at_url, valueDateTime=INCIDENT_AT),
    ]
    if subject_exists:
        # The one marker that changes what the submission means: the subject is a person the
        # instance already holds, so this response enrols them rather than creating them.
        extensions.append(Extension(url=naming.subject_exists_url, valueBoolean=True))
    return QuestionnaireResponse(
        id=f"registration-capture-{'existing' if subject_exists else 'new'}-subject",
        questionnaire=form.canonical,
        status="completed",
        authored=CAPTURED_AT,
        subject=Reference(
            type="Patient",
            identifier=Identifier(system=naming.tracked_entity_system, value=tracked_entity_uid),
        ),
        extension=extensions,
        item=items,
    )


def _print_outcome(label: str, result: ConversionResult) -> None:
    """Print what one registration response became, payload or refusal."""
    print(f"{label}: target {result.target_kind}")
    for refusal in result.refusals:
        print(f"  refused [{refusal.category}] {refusal.link_id or '-'}: {refusal.reason}")
    payload = result.tracked_entity or result.enrollment
    if payload is not None:
        print(payload.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    for note in result.notes:
        print(f"  note [{note.category}] {note.message}")
    print()


def main() -> None:
    """Translate a registration that creates its person, and one that enrols a person already held."""
    context = conversion_context()
    form = _form(context, registration_form_id())
    location_id = sorted(context.organisation_unit_uids_by_location_id)[0]
    on_the_person = _entity_level_questions(form)
    on_the_enrollment = _enrollment_level_questions(form)

    print(f"form: {form.canonical}")
    print(f"programme: {form.program_uid}   tracked entity type: {form.tracked_entity_type_uid}")
    print(f"questions of the person's own record: {', '.join(question.link_id for question in on_the_person) or '-'}")
    print(f"questions only the programme asks:    {', '.join(q.link_id for q in on_the_enrollment) or '-'}\n")

    # A registration that creates the person it enrols answers both levels, and the translator
    # splits the answers by what the form says about each question.
    creating = _registration_response(
        context,
        form,
        location_id,
        [
            QuestionnaireResponseItem(linkId=question.link_id, answer=[_answer_for(context, question, index)])
            for index, question in enumerate([*on_the_person, *on_the_enrollment])
        ],
        tracked_entity_uid=NEW_TRACKED_ENTITY_UID,
        enrollment_uid=NEW_ENROLLMENT_UID,
        subject_exists=False,
    )
    _print_outcome(
        "a registration that creates the person, posted under `trackedEntities`", translate_response(creating, context)
    )

    # A registration for a person the instance already holds answers only what the programme asks:
    # the person's own record belongs to the capture that created it.
    enrolling = _registration_response(
        context,
        form,
        location_id,
        [
            QuestionnaireResponseItem(linkId=question.link_id, answer=[_answer_for(context, question, index)])
            for index, question in enumerate(on_the_enrollment)
        ],
        tracked_entity_uid=EXISTING_TRACKED_ENTITY_UID,
        enrollment_uid=EXISTING_SUBJECT_ENROLLMENT_UID,
        subject_exists=True,
    )
    _print_outcome(
        "a registration that enrols a person already held, posted under `enrollments`",
        translate_response(enrolling, context),
    )

    print("both go to /api/tracker under plain importStrategy=CREATE; only the key differs, and the")
    print("key is what keeps the second payload from rewriting the organisation unit that owns the person.")


if __name__ == "__main__":
    main()

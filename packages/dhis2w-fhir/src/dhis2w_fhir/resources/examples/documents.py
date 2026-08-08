"""FHIR JSON for the example responses the FSH target compiles: one `QuestionnaireResponse` document each.

The twin of the FSH emitter next door. Both read the same `ExampleResponseIn` projection and both
decide the same things - which reporting period the response carries, which extensions its form
kind declares, which `linkId` a captured value answers, which FHIR type that value casts to -
through the shared projection this package exports, so the two paths cannot drift apart. What
differs is the target: the FSH path writes SUSHI source that declares a profile by its `InstanceOf:`
keyword and names a CodeSystem by its `D2OS_..._CS` alias, while this path writes the finished R4
documents with `meta.profile` and every system already absolute, exactly as SUSHI would have
resolved it.

That equality is a test, not a hope: `test_fhir_example_documents.py` rebuilds the compiled example
responses of the local stack straight from the committed source fixtures and asserts each one
equals the SUSHI output key for key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.r4 import (
    Coding,
    Extension,
    Identifier,
    Meta,
    Period,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
)
from dhis2w_fhir.resources.examples import (
    ExampleTally,
    example_answers,
    example_authored,
    example_concept_assignments,
    example_is_complete,
    example_items,
    example_period,
    example_tracker_context,
)
from dhis2w_fhir.resources.option_sets import code_system_canonical, option_set_identity_index
from dhis2w_fhir.resources.questionnaires import bound_option_set_uids

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.period.schemas import PeriodValue
    from dhis2w_fhir.resources.examples.schemas import (
        ExampleAnswer,
        ExampleItem,
        ExampleResponseIn,
        ExampleTrackerContext,
    )
    from dhis2w_fhir.resources.option_sets.schemas import (
        ConceptAssignmentPlan,
        OptionSetIdentity,
        OptionSetIdentityPlan,
        OptionSetIn,
    )
    from dhis2w_fhir.resources.questionnaires.schemas import FormKind, QuestionnaireSourceIn

__all__ = [
    "TRACKED_ENTITY_IDENTIFIER_SEGMENT",
    "TRACKER_ENROLLMENT_IDENTIFIER_SEGMENT",
    "ExampleDocumentBuild",
    "build_example_documents",
]

#: The DHIS2 identifier system a tracked entity is named under - the `$DHIS2-TE` alias resolved.
TRACKED_ENTITY_IDENTIFIER_SEGMENT = "tracked-entity"

#: The DHIS2 identifier system an enrollment is named under - the `$DHIS2-TRACKER-ENROLLMENT` alias resolved.
TRACKER_ENROLLMENT_IDENTIFIER_SEGMENT = "tracker-enrollment"

#: The resource type a tracker-event response names its tracked-entity subject as.
_TRACKER_SUBJECT_TYPE = "Patient"

#: The `QuestionnaireResponse.status` codes R4 admits, which a DHIS2 event status maps onto.
_ResponseStatusCode = Literal["in-progress", "completed", "amended", "entered-in-error", "stopped"]

#: The sub-extension names D2Period carries, in the order the extension declares them.
_PERIOD_ISO_SUB_EXTENSION = "iso"
_PERIOD_TYPE_SUB_EXTENSION = "type"
_PERIOD_RANGE_SUB_EXTENSION = "period"

#: The character separating the whole part of a decimal from its fraction.
_DECIMAL_POINT = "."


class ExampleDocumentBuild(BaseModel):
    """The QuestionnaireResponse documents one run builds, in emission order, with the notes building them raised."""

    model_config = ConfigDict(frozen=True)

    responses: list[QuestionnaireResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class _ExampleSystems(BaseModel):
    """Every absolute URL a built example response names, resolved once from the canonical and the naming tokens.

    This is what the FSH path defers to SUSHI: an `InstanceOf:` keyword naming a profile, a
    `$DHIS2-TE` alias, a `D2OS_..._CS` coding system. A served document carries the resolved URL,
    so the resolution happens here instead.
    """

    model_config = ConfigDict(frozen=True)

    canonical: str
    identifier_base: str
    form_type_extension_url: str
    period_extension_url: str
    organisation_unit_extension_url: str
    tracker_enrollment_extension_url: str
    aggregate_response_profile_url: str
    event_response_profile_url: str
    tracker_event_response_profile_url: str

    @classmethod
    def from_config(cls, config: GenerateConfig, canonical: str) -> _ExampleSystems:
        """Resolve the run's URLs from the IG canonical plus the `[generate]` identifier system base."""
        foundation = FoundationNaming.from_naming(config.naming)
        return cls(
            canonical=canonical,
            identifier_base=f"{config.identifier_system_base}/id",
            form_type_extension_url=_definition_url(canonical, foundation.form_type_extension_id),
            period_extension_url=_definition_url(canonical, foundation.period_extension_id),
            organisation_unit_extension_url=_definition_url(canonical, foundation.organisation_unit_extension_id),
            tracker_enrollment_extension_url=_definition_url(canonical, foundation.tracker_enrollment_extension_id),
            aggregate_response_profile_url=_definition_url(canonical, foundation.aggregate_response_profile_id),
            event_response_profile_url=_definition_url(canonical, foundation.event_response_profile_id),
            tracker_event_response_profile_url=_definition_url(canonical, foundation.tracker_event_response_profile_id),
        )

    def identifier_system(self, segment: str) -> str:
        """The DHIS2 identifier system one object kind is named under (e.g. `.../id/tracked-entity`)."""
        return f"{self.identifier_base}/{segment}"

    def questionnaire_url(self, uid: str) -> str:
        """Canonical URL the form this response answers is published at."""
        return f"{self.canonical}/Questionnaire/{uid}"

    def response_profile_url(self, kind: FormKind) -> str:
        """Canonical URL of the QuestionnaireResponse profile one form kind's complete response conforms to."""
        if kind == "aggregate":
            return self.aggregate_response_profile_url
        if kind == "tracker-event":
            return self.tracker_event_response_profile_url
        return self.event_response_profile_url


def build_example_documents(
    sources: list[QuestionnaireSourceIn],
    responses: list[ExampleResponseIn],
    option_sets: list[OptionSetIn],
    config: GenerateConfig,
    canonical: str,
    *,
    option_set_plan: OptionSetIdentityPlan,
) -> ExampleDocumentBuild:
    """Build one FHIR QuestionnaireResponse per example response, keyed by the instance id the FSH path declares.

    Takes the parameters `build_example_artifacts` takes and decides the same things from them, so
    a caller can build the FSH source and the served documents off one fetch: `option_set_plan` is
    the identity plan the terminology target emits from, so a coded answer names the CodeSystem the
    same run writes, and the concept codes come from `example_concept_assignments` for the same
    reason. A response whose target is not among `sources` is skipped, exactly as the FSH path
    skips it.
    """
    systems = _ExampleSystems.from_config(config, canonical)
    index = option_set_identity_index(option_set_plan, bound_option_set_uids(sources), config)
    sources_by_uid = {source.uid: source for source in sources}
    option_sets_by_uid = {option_set.uid: option_set for option_set in option_sets}
    assignments = example_concept_assignments(option_sets, config)
    tally = ExampleTally()
    documents: list[QuestionnaireResponse] = []
    for response in responses:
        source = sources_by_uid.get(response.target_uid)
        if source is None:
            continue
        documents.append(
            _response_document(
                response, source, option_sets_by_uid, assignments, index.identities, systems, canonical, tally
            )
        )
    notes = list(tally.to_notes())
    if index.unplanned_uids:
        notes.append(
            aggregate_note(
                f"{len(index.unplanned_uids)} option sets a question binds are absent from the option-set "
                "selection; their answer coding systems are derived from the UID",
                index.unplanned_uids,
            )
        )
    return ExampleDocumentBuild(responses=documents, notes=notes)


def _response_document(
    response: ExampleResponseIn,
    source: QuestionnaireSourceIn,
    option_sets_by_uid: dict[str, OptionSetIn],
    assignments: dict[str, ConceptAssignmentPlan],
    identities: dict[str, OptionSetIdentity],
    systems: _ExampleSystems,
    canonical: str,
    tally: ExampleTally,
) -> QuestionnaireResponse:
    """Build one example's QuestionnaireResponse, every name already resolved to the URL it is served under."""
    period = example_period(response, source, tally)
    answers = example_answers(response, source, option_sets_by_uid, assignments, tally)
    authored = example_authored(response, tally)
    tracker = example_tracker_context(response, source, tally)
    complete = example_is_complete(source.kind, period=period, authored=authored, tracker=tracker)
    return QuestionnaireResponse(
        id=response.instance_id,
        meta=Meta(profile=[systems.response_profile_url(source.kind)]) if complete else None,
        extension=_extensions(source.kind, period, tracker, systems),
        questionnaire=systems.questionnaire_url(source.uid),
        status=_status_code(response.status_code),
        subject=_subject(response, tracker, systems),
        authored=authored,
        item=_items(example_items(source, answers), identities, canonical) or None,
    )


def _extensions(
    kind: FormKind,
    period: PeriodValue | None,
    tracker: ExampleTrackerContext | None,
    systems: _ExampleSystems,
) -> list[Extension]:
    """The extensions one response carries, in the order its kind's response profile slices them.

    A tracker-event response leads with the organisation unit it was captured at and the
    enrollment it belongs to, an aggregate response leads with its reporting period, and every
    kind closes with the form type - which is the order the compiled instances carry.
    """
    extensions: list[Extension] = []
    if tracker is not None:
        extensions.append(
            Extension(
                url=systems.organisation_unit_extension_url,
                valueReference=Reference(reference=f"Location/{tracker.organisation_unit_uid}"),
            )
        )
        if tracker.enrollment_uid is not None:
            extensions.append(
                Extension(
                    url=systems.tracker_enrollment_extension_url,
                    valueIdentifier=Identifier(
                        system=systems.identifier_system(TRACKER_ENROLLMENT_IDENTIFIER_SEGMENT),
                        value=tracker.enrollment_uid,
                    ),
                )
            )
    if period is not None:
        extensions.append(_period_extension(period, systems))
    extensions.append(Extension(url=systems.form_type_extension_url, valueCode=kind))
    return extensions


def _period_extension(period: PeriodValue, systems: _ExampleSystems) -> Extension:
    """The D2Period extension: the DHIS2 ISO identifier, its period type, and the range it resolves to."""
    return Extension(
        url=systems.period_extension_url,
        extension=[
            Extension(url=_PERIOD_ISO_SUB_EXTENSION, valueString=period.iso),
            Extension(url=_PERIOD_TYPE_SUB_EXTENSION, valueCode=period.period_type),
            Extension(
                url=_PERIOD_RANGE_SUB_EXTENSION,
                valuePeriod=Period(start=period.start_date.isoformat(), end=period.end_date.isoformat()),
            ),
        ],
    )


def _subject(
    response: ExampleResponseIn, tracker: ExampleTrackerContext | None, systems: _ExampleSystems
) -> Reference | None:
    """The subject of one response: the tracked entity a tracker event was captured for, else the Location.

    A tracker-event response naming no tracked entity carries no subject at all, because the only
    subject its profile admits is a Patient identified by tracked-entity UID.
    """
    if tracker is None:
        return Reference(reference=f"Location/{response.organisation_unit_uid}")
    if tracker.tracked_entity_uid is None:
        return None
    return Reference(
        type=_TRACKER_SUBJECT_TYPE,
        identifier=Identifier(
            system=systems.identifier_system(TRACKED_ENTITY_IDENTIFIER_SEGMENT), value=tracker.tracked_entity_uid
        ),
    )


def _status_code(value: str) -> _ResponseStatusCode:
    """Read a status computed as a plain string as the R4 code it is; a guard test pins the two together."""
    return cast(_ResponseStatusCode, value)


def _items(
    items: list[ExampleItem], identities: dict[str, OptionSetIdentity], canonical: str
) -> list[QuestionnaireResponseItem]:
    """Mirror the shared item tree onto the nested `QuestionnaireResponse.item` structure."""
    return [
        QuestionnaireResponseItem(
            linkId=item.link_id,
            answer=[_answer(answer, identities, canonical) for answer in item.answers] or None,
            item=_items(item.items, identities, canonical) or None,
        )
        for item in items
    ]


def _answer(
    answer: ExampleAnswer, identities: dict[str, OptionSetIdentity], canonical: str
) -> QuestionnaireResponseAnswer:
    """Land one typed answer on the `value[x]` element its element name names."""
    if answer.element == "valueInteger":
        return QuestionnaireResponseAnswer(valueInteger=answer.integer_value)
    if answer.element == "valueDecimal":
        return QuestionnaireResponseAnswer(valueDecimal=_decimal_number(answer.decimal_value or "0"))
    if answer.element == "valueBoolean":
        return QuestionnaireResponseAnswer(valueBoolean=answer.boolean_value)
    if answer.element == "valueDate":
        return QuestionnaireResponseAnswer(valueDate=answer.text_value)
    if answer.element == "valueDateTime":
        return QuestionnaireResponseAnswer(valueDateTime=answer.text_value)
    if answer.element == "valueTime":
        return QuestionnaireResponseAnswer(valueTime=answer.text_value)
    if answer.element == "valueUri":
        return QuestionnaireResponseAnswer(valueUri=_flat(answer.text_value))
    if answer.element == "valueReference":
        return QuestionnaireResponseAnswer(valueReference=Reference(reference=f"Location/{answer.location_uid}"))
    if answer.element == "valueCoding" and answer.coding is not None:
        identity = identities[answer.coding.option_set_uid]
        return QuestionnaireResponseAnswer(
            valueCoding=Coding(
                system=code_system_canonical(canonical, identity.code_system_id),
                code=answer.coding.concept_code,
                display=flatten_whitespace(answer.coding.display),
            )
        )
    return QuestionnaireResponseAnswer(valueString=_flat(answer.text_value))


def _flat(text: str | None) -> str | None:
    """One free-text answer on its single line - the same flattening the quoted FSH literal applies."""
    return None if text is None else flatten_whitespace(text)


def _decimal_number(text: str) -> int | float:
    """Read a lexical decimal as the JSON number it is - a whole number stays whole, as SUSHI writes it."""
    return float(text) if _DECIMAL_POINT in text else int(text)


def _definition_url(canonical: str, definition_id: str) -> str:
    """Canonical URL one generated StructureDefinition - an extension or a response profile - is published at."""
    return f"{canonical}/StructureDefinition/{definition_id}"

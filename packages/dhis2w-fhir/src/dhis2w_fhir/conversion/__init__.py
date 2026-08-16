"""The conversion layer: QuestionnaireResponse -> DHIS2, the reference implementation of the capture contract.

The generate targets take DHIS2 metadata and data to FHIR; this package takes a captured
`QuestionnaireResponse` back to the DHIS2 import payload it reports. It is deliberately a typed
Python translator rather than an executed mapping language, and it is deliberately the *first*
of the two: `docs/fhir/design/conversion.md` makes this code the reference implementation the
later published StructureMaps are held against, so every rule here is written to be read.

Four layers, each a module:

    `schemas`     the translation context and the outcome taxonomy - what a caller assembles and
                  what one translated response answers with.
    `context`     reading the compiled IG artifacts (Questionnaires, CodeSystems, ValueSets,
                  ConceptMaps, Locations) into that context.
    `values`      one question's answers into the DHIS2 wire value, one branch per value type.
    `payloads`    one response into the `/api/dataValueSets` envelope or the `/api/tracker` event
                  its form kind reports, plus `translator` dispatching between them.

The payloads themselves are the generated OpenAPI models `DataValueSet` and `TrackerEvent`, not
hand-rolled mirrors of them. Nothing translates partially: a response the translator cannot read
whole answers with typed refusals naming the link id and the reason, never with a payload that
imports the half of itself that happened to parse.
"""

from __future__ import annotations

from dhis2w_fhir.conversion.artifacts import (
    COMPILED_RESOURCES_RELATIVE_PATH,
    BoundQuestionUids,
    CompiledArtifactReadError,
    CompiledArtifacts,
    CompiledIgMissingError,
    SourcedDocument,
    bound_question_uids,
    build_project_context,
    collect_artifacts,
    load_compiled_artifacts,
)
from dhis2w_fhir.conversion.context import (
    ANSWER_ELEMENTS_BY_ITEM_TYPE,
    CELL_LINK_ID_SEPARATOR,
    OPTION_CODE_PROPERTY,
    OPTION_UID_PROPERTY,
    ConversionContextError,
    build_conversion_context,
    build_form_spec,
    build_option_table,
)
from dhis2w_fhir.conversion.payloads import (
    COMPLETED_EVENT_STATUSES,
    EVENT_STATUSES_BY_RESPONSE_STATUS,
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    AggregateTranslation,
    EventTranslation,
    RegistrationTranslation,
    TranslatedAnswer,
    TranslatedAnswers,
    receipt_event_uid,
    translate_aggregate_response,
    translate_answers,
    translate_event_response,
    translate_tracked_entity_response,
    translate_tracker_event_response,
    translate_tracker_registration_response,
)
from dhis2w_fhir.conversion.schemas import (
    CONCEPT_CODE_TIER,
    FORWARD_TARGET_ORDER,
    OPTION_CODE_TIER,
    OPTION_UID_TIER,
    TARGET_KINDS_BY_FORM_KIND,
    CodedAnswerMode,
    ConversionContext,
    ConversionNaming,
    ConversionNote,
    ConversionNoteCategory,
    ConversionRefusal,
    ConversionRefusalCategory,
    ConversionReport,
    ConversionResult,
    ConversionTargetKind,
    FormSpec,
    OptionEntry,
    OptionLookup,
    OptionTable,
    QuestionSpec,
    ResolvedOption,
    WireValueKind,
)
from dhis2w_fhir.conversion.translator import translate_response, translate_responses
from dhis2w_fhir.conversion.values import (
    ANSWER_VALUE_ELEMENTS,
    LOCATION_REFERENCE_PREFIX,
    MULTI_VALUE_SEPARATOR,
    OrganisationUnitResolution,
    WallClockReading,
    WireValue,
    answer_wire_value,
    decimal_wire_value,
    resolve_option,
    resolve_organisation_unit,
    wall_clock_notes,
    wall_clock_reading,
)

__all__ = [
    "ANSWER_ELEMENTS_BY_ITEM_TYPE",
    "ANSWER_VALUE_ELEMENTS",
    "CELL_LINK_ID_SEPARATOR",
    "COMPILED_RESOURCES_RELATIVE_PATH",
    "COMPLETED_EVENT_STATUSES",
    "CONCEPT_CODE_TIER",
    "EVENT_STATUSES_BY_RESPONSE_STATUS",
    "LOCATION_REFERENCE_PREFIX",
    "MULTI_VALUE_SEPARATOR",
    "OPTION_CODE_PROPERTY",
    "OPTION_CODE_TIER",
    "OPTION_UID_PROPERTY",
    "OPTION_UID_TIER",
    "PERIOD_ISO_SUB_EXTENSION",
    "PERIOD_RANGE_SUB_EXTENSION",
    "PERIOD_TYPE_SUB_EXTENSION",
    "FORWARD_TARGET_ORDER",
    "TARGET_KINDS_BY_FORM_KIND",
    "AggregateTranslation",
    "BoundQuestionUids",
    "CodedAnswerMode",
    "CompiledArtifactReadError",
    "CompiledArtifacts",
    "SourcedDocument",
    "CompiledIgMissingError",
    "ConversionContext",
    "ConversionContextError",
    "ConversionNaming",
    "ConversionNote",
    "ConversionNoteCategory",
    "ConversionRefusal",
    "ConversionRefusalCategory",
    "ConversionReport",
    "ConversionResult",
    "ConversionTargetKind",
    "EventTranslation",
    "RegistrationTranslation",
    "FormSpec",
    "OptionEntry",
    "OptionLookup",
    "OptionTable",
    "OrganisationUnitResolution",
    "QuestionSpec",
    "ResolvedOption",
    "TranslatedAnswer",
    "TranslatedAnswers",
    "WallClockReading",
    "WireValue",
    "WireValueKind",
    "answer_wire_value",
    "bound_question_uids",
    "build_conversion_context",
    "build_form_spec",
    "build_option_table",
    "build_project_context",
    "decimal_wire_value",
    "collect_artifacts",
    "load_compiled_artifacts",
    "receipt_event_uid",
    "resolve_option",
    "resolve_organisation_unit",
    "translate_aggregate_response",
    "translate_answers",
    "translate_event_response",
    "translate_response",
    "translate_responses",
    "translate_tracked_entity_response",
    "translate_tracker_event_response",
    "translate_tracker_registration_response",
    "wall_clock_notes",
    "wall_clock_reading",
]

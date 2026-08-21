"""Receiving a QuestionnaireResponse: reading the contract, checking the submission, saying what happened.

Four modules, in the order a request passes through them. `naming` derives the extension urls and
identifier systems this project's capture contract is written in, from `fhir.toml` alone. `index`
reads one served Questionnaire into the lookups an answer is checked against. `resolve` maps a
received code back to the DHIS2 option it names, against the terminology the facade serves.
`validate` is the phase machine that runs the whole thing, and `outcome` is the OperationOutcome
vocabulary every answer - accepted or refused - is spoken in.

No module here talks to DHIS2. A capture is validated against the served IG and stored as a
receipt; translating that receipt into DHIS2 data values, events, and enrollments is a later phase.
"""

from dhis2w_fhir_serve.capture.index import (
    ANSWER_ELEMENTS_BY_ITEM_TYPE,
    CELL_LINK_ID_SEPARATOR,
    FORM_KINDS,
    CaptureAttributeOptionCombos,
    CaptureIndex,
    CaptureIndexCache,
    CaptureQuestion,
    QuestionKind,
    UnreadableQuestionnaireError,
    build_capture_index,
)
from dhis2w_fhir_serve.capture.naming import (
    GENERATE_SEED_IDENTIFIER_SEGMENT,
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    CaptureNaming,
)
from dhis2w_fhir_serve.capture.outcome import (
    RECEIPT_NOTE,
    CaptureIssue,
    CaptureIssueCode,
    CaptureIssueSeverity,
    CaptureRejection,
    rejection_outcome,
    success_outcome,
)
from dhis2w_fhir_serve.capture.resolve import (
    OPTION_CODE_PROPERTY,
    OPTION_UID_PROPERTY,
    AmbiguousCodingError,
    CodingMatchTier,
    CodingResolutionError,
    CodingResolver,
    CodingResolverSet,
    ResolvedCoding,
    UnresolvableCodingError,
)
from dhis2w_fhir_serve.capture.validate import (
    AMENDED_STATUS,
    ANSWER_VALUE_ELEMENTS,
    CORRECTIONS_CONFIG_KEY,
    DEFAULT_LIFECYCLE_POSTURES,
    DEFAULT_STRICT_CODES,
    ENTERED_IN_ERROR_STATUS,
    ONE_RESPONSE_PER_REQUEST,
    WITHDRAWALS_CONFIG_KEY,
    CaptureLifecyclePostures,
    ValidatedCapture,
    validate_response,
)

__all__ = [
    "AMENDED_STATUS",
    "ANSWER_ELEMENTS_BY_ITEM_TYPE",
    "ANSWER_VALUE_ELEMENTS",
    "CELL_LINK_ID_SEPARATOR",
    "CORRECTIONS_CONFIG_KEY",
    "DEFAULT_LIFECYCLE_POSTURES",
    "DEFAULT_STRICT_CODES",
    "ENTERED_IN_ERROR_STATUS",
    "FORM_KINDS",
    "GENERATE_SEED_IDENTIFIER_SEGMENT",
    "ONE_RESPONSE_PER_REQUEST",
    "OPTION_CODE_PROPERTY",
    "OPTION_UID_PROPERTY",
    "PERIOD_ISO_SUB_EXTENSION",
    "PERIOD_RANGE_SUB_EXTENSION",
    "PERIOD_TYPE_SUB_EXTENSION",
    "RECEIPT_NOTE",
    "WITHDRAWALS_CONFIG_KEY",
    "AmbiguousCodingError",
    "CaptureAttributeOptionCombos",
    "CaptureIndex",
    "CaptureIndexCache",
    "CaptureIssue",
    "CaptureIssueCode",
    "CaptureIssueSeverity",
    "CaptureLifecyclePostures",
    "CaptureNaming",
    "CaptureQuestion",
    "CaptureRejection",
    "CodingMatchTier",
    "CodingResolutionError",
    "CodingResolver",
    "CodingResolverSet",
    "QuestionKind",
    "ResolvedCoding",
    "UnreadableQuestionnaireError",
    "UnresolvableCodingError",
    "ValidatedCapture",
    "build_capture_index",
    "rejection_outcome",
    "success_outcome",
    "validate_response",
]

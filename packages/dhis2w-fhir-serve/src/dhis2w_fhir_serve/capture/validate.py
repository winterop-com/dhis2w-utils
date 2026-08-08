"""The capture phase machine: what a received QuestionnaireResponse has to clear before it is stored.

Validation runs in phases, and a phase that finds an error is the last one to run. That ordering
is what makes the rejection readable: there is no point telling a client its answers are wrong
when the server could not tell which form kind the submission claims to be, and no point checking
a period against a questionnaire that is not served here. Inside a phase every issue is collected,
so one round trip reports every problem at that level rather than one at a time.

    0. Read the body      - JSON, `resourceType`, and the R4 shape of a QuestionnaireResponse (400).
    1. Read the contract  - the D2FormType kind, then the invariants that kind's profile pins (422).
    2. Resolve the form   - the questionnaire canonical, its served Questionnaire, and its index (422).
    3. Read the period    - an aggregate response's ISO period, its type, and the range it claims (422).
    4. Walk the answers   - every item against the index: link ids, cardinality, types, terminology (422).

Warnings never reject. They record what the server had to interpret or could not check - a code
sent in a spelling the contract does not ask for, a required question left unanswered, a date
range that disagrees with the ISO period it was derived from - and they ride back on the
OperationOutcome of the accepted capture and into the stored receipt.

Nothing here talks to DHIS2. A capture is validated against the served IG and stored; translating
a receipt into DHIS2 data values, events, and enrollments is a later phase.
"""

from __future__ import annotations

import json
from typing import Any, Final, cast

from dhis2w_fhir.period import parse_period
from dhis2w_fhir.r4 import (
    Extension,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
)
from dhis2w_fhir.r4.primitives import is_fhir_date, is_fhir_date_time, is_fhir_time
from dhis2w_fhir.resources.questionnaires.schemas import FormKind
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from dhis2w_fhir_serve.capture.index import (
    FORM_KINDS,
    CaptureIndex,
    CaptureIndexCache,
    CaptureQuestion,
    UnreadableQuestionnaireError,
)
from dhis2w_fhir_serve.capture.naming import (
    PERIOD_ISO_SUB_EXTENSION,
    PERIOD_RANGE_SUB_EXTENSION,
    PERIOD_TYPE_SUB_EXTENSION,
    CaptureNaming,
)
from dhis2w_fhir_serve.capture.outcome import CaptureIssue, CaptureIssueCode, CaptureRejection
from dhis2w_fhir_serve.capture.resolve import (
    AmbiguousCodingError,
    CodingResolverSet,
    ResolvedCoding,
    UnresolvableCodingError,
)
from dhis2w_fhir_serve.store import ResourceStore

DEFAULT_STRICT_CODES: Final[bool] = False
"""Whether a code outside the served terminology rejects the capture, unless a project says otherwise.

Roadmap decision 5.1: provisionally lenient at serve. A generated IG is compiled from a DHIS2
instance at a point in time, and an option added since is a fact about the instance, not a
mistake by the client - so the default records the drift as a warning and stores the submission.
This constant is the single flip point for that decision; `ServeSettings.strict_codes` is the
runtime source a request is actually validated against.
"""

#: The status an aggregate capture has to carry. A data value set is reported for a period, not
#: drafted against one, so a half-finished aggregate submission is not something to store as sent.
AGGREGATE_REQUIRED_STATUS = "completed"

#: The resource type a capture request carries, and what a client posting a Bundle is told instead.
QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"
BUNDLE_RESOURCE_TYPE = "Bundle"

#: What a client posting anything but one response per request is told.
ONE_RESPONSE_PER_REQUEST = (
    "this endpoint accepts one QuestionnaireResponse per request; post each response on its own request"
)

#: The prefix a subject or organisation-unit reference names a DHIS2 organisation unit under.
LOCATION_REFERENCE_PREFIX = "Location/"

#: Every `value[x]` element an answer may carry, in the order R4 declares them.
ANSWER_VALUE_ELEMENTS = (
    "valueBoolean",
    "valueDecimal",
    "valueInteger",
    "valueDate",
    "valueDateTime",
    "valueTime",
    "valueString",
    "valueUri",
    "valueAttachment",
    "valueCoding",
    "valueReference",
)

#: How many dash-separated parts a full calendar date carries; a captured date is never partial.
_FULL_DATE_PARTS = 3


class ValidatedCapture(BaseModel):
    """A submission that cleared every phase: what it is, what it answers, and what the server noted."""

    model_config = ConfigDict(frozen=True)

    form_kind: FormKind
    canonical: str
    warnings: tuple[CaptureIssue, ...] = ()
    response: dict[str, Any]
    """The submission as it arrived - the same byte-faithful escape hatch `StoredResponseEnvelope.response` documents.

    What is stored has to read back as what the client sent, so the parsed document is carried
    verbatim rather than re-serialised from the model it was validated through. The dict leaves
    this model only into the spool and out again as an HTTP response body.
    """


def validate_response(
    raw_body: bytes,
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
    strict_codes: bool = DEFAULT_STRICT_CODES,
) -> ValidatedCapture:
    """Run every phase over one received body, answering with what to store or raising what to refuse."""
    payload = _read_body(raw_body)
    response = _read_response(payload)
    warnings: list[CaptureIssue] = []

    form_kind = _declared_form_kind(response, naming)
    _settle(_profile_issues(response, naming, form_kind), warnings)

    index = _resolve_index(response.questionnaire or "", form_kind, indexes, naming, store)
    if form_kind == "aggregate":
        _settle(_period_issues(response, naming), warnings)
    _settle(
        _ItemValidator(index=index, resolvers=CodingResolverSet(store=store), strict=strict_codes).run(response),
        warnings,
    )

    return ValidatedCapture(
        form_kind=form_kind,
        canonical=index.canonical,
        warnings=tuple(warnings),
        response=payload,
    )


def _read_body(raw_body: bytes) -> dict[str, Any]:
    """Phase 0a: the request body as a JSON object, or a 400 naming why it could not be read."""
    try:
        parsed: Any = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise _refusal(400, "structure", None, f"the request body is not valid JSON ({error})") from error
    if not isinstance(parsed, dict):
        raise _refusal(400, "structure", None, "the request body is not a JSON object holding a FHIR resource")
    return cast(dict[str, Any], parsed)


def _read_response(payload: dict[str, Any]) -> QuestionnaireResponse:
    """Phase 0b: the JSON object as an R4 QuestionnaireResponse, or a 400 naming every element it stumbled on."""
    resource_type = payload.get("resourceType")
    if resource_type == BUNDLE_RESOURCE_TYPE:
        raise _refusal(400, "not-supported", "Bundle", ONE_RESPONSE_PER_REQUEST)
    if resource_type != QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE:
        raise _refusal(
            400,
            "invalid",
            "resourceType",
            f"this endpoint receives a {QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}, not a `{resource_type}`",
        )
    try:
        return QuestionnaireResponse.model_validate(payload)
    except ValidationError as error:
        issues = tuple(
            CaptureIssue(
                severity="error",
                code="structure",
                expression=_expression(detail.get("loc", ())),
                diagnostics=str(detail.get("msg", "the element could not be read")),
            )
            for detail in error.errors()
        )
        raise CaptureRejection(400, issues) from error


def _declared_form_kind(response: QuestionnaireResponse, naming: CaptureNaming) -> FormKind:
    """Phase 1a: which DHIS2 form kind the submission claims to be - everything after this branches on it."""
    declared = [extension.valueCode for extension in _extensions(response, naming.form_type_url) if extension.valueCode]
    if not declared:
        raise _refusal(
            422,
            "required",
            "QuestionnaireResponse.extension",
            f"no DHIS2 form type: every response carries one `{naming.form_type_url}` extension with a `valueCode`",
        )
    if len(declared) > 1:
        raise _refusal(
            422,
            "invariant",
            "QuestionnaireResponse.extension",
            f"more than one DHIS2 form type declared ({', '.join(sorted(declared))})",
        )
    for kind in FORM_KINDS:
        if kind == declared[0]:
            return kind
    raise _refusal(
        422,
        "code-invalid",
        "QuestionnaireResponse.extension",
        f"`{declared[0]}` is not a DHIS2 form kind this server captures ({', '.join(FORM_KINDS)})",
    )


def _profile_issues(
    response: QuestionnaireResponse,
    naming: CaptureNaming,
    form_kind: FormKind,
) -> tuple[CaptureIssue, ...]:
    """Phase 1b: every invariant the declared kind's response profile pins, all of them checked."""
    issues: list[CaptureIssue] = []
    if not response.questionnaire:
        issues.append(_error("required", "QuestionnaireResponse.questionnaire", "the response names no questionnaire"))
    if response.status is None:
        issues.append(_error("required", "QuestionnaireResponse.status", "the response carries no status"))
    if form_kind == "aggregate":
        issues.extend(_aggregate_issues(response, naming))
    elif form_kind == "event":
        issues.extend(_authored_issues(response))
        issues.extend(_location_subject_issues(response))
    else:
        issues.extend(_authored_issues(response))
        issues.extend(_tracker_subject_issues(response, naming))
        issues.extend(_tracker_context_issues(response, naming))
    return tuple(issues)


def _aggregate_issues(response: QuestionnaireResponse, naming: CaptureNaming) -> tuple[CaptureIssue, ...]:
    """The aggregate contract: a reporting period, an organisation unit, and a completed submission."""
    issues: list[CaptureIssue] = list(_location_subject_issues(response))
    if response.status is not None and response.status != AGGREGATE_REQUIRED_STATUS:
        issues.append(
            _error(
                "business-rule",
                "QuestionnaireResponse.status",
                f"an aggregate response is stored as reported, so its status has to be "
                f"`{AGGREGATE_REQUIRED_STATUS}`, not `{response.status}`",
            )
        )
    periods = _extensions(response, naming.period_url)
    if len(periods) != 1:
        issues.append(
            _error(
                "required" if not periods else "invariant",
                "QuestionnaireResponse.extension",
                f"an aggregate response carries exactly one `{naming.period_url}` extension, not {len(periods)}",
            )
        )
        return tuple(issues)
    issues.extend(_period_extension_issues(periods[0]))
    return tuple(issues)


def _period_extension_issues(period: Extension) -> tuple[CaptureIssue, ...]:
    """The three facts D2Period slices: the ISO identifier, its period type, and the range it resolves to."""
    issues: list[CaptureIssue] = []
    iso = _sub_extensions(period, PERIOD_ISO_SUB_EXTENSION)
    if len(iso) != 1 or not iso[0].valueString:
        issues.append(
            _error("required", "QuestionnaireResponse.extension", "the period carries no `iso` sub-extension")
        )
    period_type = _sub_extensions(period, PERIOD_TYPE_SUB_EXTENSION)
    if len(period_type) != 1 or not period_type[0].valueCode:
        issues.append(
            _error("required", "QuestionnaireResponse.extension", "the period carries no `type` sub-extension")
        )
    ranges = _sub_extensions(period, PERIOD_RANGE_SUB_EXTENSION)
    if len(ranges) > 1:
        issues.append(
            _error("invariant", "QuestionnaireResponse.extension", "the period carries more than one date range")
        )
    elif ranges and ranges[0].valuePeriod is None:
        issues.append(
            _error(
                "structure", "QuestionnaireResponse.extension", "the period's `period` sub-extension carries no Period"
            )
        )
    return tuple(issues)


def _authored_issues(response: QuestionnaireResponse) -> tuple[CaptureIssue, ...]:
    """The moment the data was captured, which the event and tracker-event contracts both require."""
    if not response.authored:
        return (_error("required", "QuestionnaireResponse.authored", "the response records no `authored` instant"),)
    if not is_fhir_date_time(response.authored):
        return (
            _error(
                "value",
                "QuestionnaireResponse.authored",
                f"`{response.authored}` is not an R4 dateTime",
            ),
        )
    return ()


def _location_subject_issues(response: QuestionnaireResponse) -> tuple[CaptureIssue, ...]:
    """The organisation unit an aggregate or event response reports for, as a Location reference."""
    subject = response.subject
    if subject is None:
        return (_error("required", "QuestionnaireResponse.subject", "the response names no subject"),)
    if not subject.reference:
        return (
            _error(
                "required",
                "QuestionnaireResponse.subject.reference",
                f"the subject carries no `{LOCATION_REFERENCE_PREFIX}<uid>` reference",
            ),
        )
    if not _is_location_reference(subject.reference):
        return (
            _error(
                "value",
                "QuestionnaireResponse.subject.reference",
                f"`{subject.reference}` is not a `{LOCATION_REFERENCE_PREFIX}<uid>` reference",
            ),
        )
    return ()


def _tracker_subject_issues(response: QuestionnaireResponse, naming: CaptureNaming) -> tuple[CaptureIssue, ...]:
    """The tracked entity a tracker-event response is about, named by DHIS2 UID rather than referenced."""
    subject = response.subject
    if subject is None:
        return (_error("required", "QuestionnaireResponse.subject", "the response names no subject"),)
    issues: list[CaptureIssue] = []
    if subject.reference:
        issues.append(
            _warning(
                "informational",
                "QuestionnaireResponse.subject.reference",
                f"the subject reference `{subject.reference}` is ignored: a tracker event names its tracked "
                f"entity by identifier under `{naming.tracked_entity_system}`",
            )
        )
    identifier = subject.identifier
    if identifier is None or not identifier.value:
        issues.append(
            _error(
                "required",
                "QuestionnaireResponse.subject.identifier",
                f"the subject carries no tracked-entity identifier under `{naming.tracked_entity_system}`",
            )
        )
    elif identifier.system != naming.tracked_entity_system:
        issues.append(
            _error(
                "value",
                "QuestionnaireResponse.subject.identifier.system",
                f"the subject identifier names `{identifier.system}`, not `{naming.tracked_entity_system}`",
            )
        )
    return tuple(issues)


def _tracker_context_issues(response: QuestionnaireResponse, naming: CaptureNaming) -> tuple[CaptureIssue, ...]:
    """The two facts a tracker event carries beyond its answers: where it happened, and which enrollment it is on."""
    issues: list[CaptureIssue] = []
    organisation_units = _extensions(response, naming.organisation_unit_url)
    if len(organisation_units) != 1:
        issues.append(
            _error(
                "required" if not organisation_units else "invariant",
                "QuestionnaireResponse.extension",
                f"a tracker event carries exactly one `{naming.organisation_unit_url}` extension, "
                f"not {len(organisation_units)}",
            )
        )
    else:
        reference = organisation_units[0].valueReference
        if reference is None or not reference.reference or not _is_location_reference(reference.reference):
            issues.append(
                _error(
                    "value",
                    "QuestionnaireResponse.extension",
                    f"the organisation unit extension carries no `{LOCATION_REFERENCE_PREFIX}<uid>` reference",
                )
            )
    enrollments = _extensions(response, naming.tracker_enrollment_url)
    if len(enrollments) != 1:
        issues.append(
            _error(
                "required" if not enrollments else "invariant",
                "QuestionnaireResponse.extension",
                f"a tracker event carries exactly one `{naming.tracker_enrollment_url}` extension, "
                f"not {len(enrollments)}",
            )
        )
        return tuple(issues)
    identifier = enrollments[0].valueIdentifier
    if identifier is None or not identifier.value:
        issues.append(
            _error(
                "required",
                "QuestionnaireResponse.extension",
                "the tracker enrollment extension carries no identifier value",
            )
        )
    elif identifier.system != naming.tracker_enrollment_system:
        issues.append(
            _error(
                "value",
                "QuestionnaireResponse.extension",
                f"the tracker enrollment names `{identifier.system}`, not `{naming.tracker_enrollment_system}`",
            )
        )
    return tuple(issues)


def _resolve_index(
    canonical: str,
    form_kind: FormKind,
    indexes: CaptureIndexCache,
    naming: CaptureNaming,
    store: ResourceStore,
) -> CaptureIndex:
    """Phase 2: the served Questionnaire the response answers, and the index its answers are checked against."""
    try:
        index = indexes.resolve(canonical, naming, store)
    except UnreadableQuestionnaireError as error:
        raise _refusal(422, "not-found", "QuestionnaireResponse.questionnaire", error.diagnostics) from error
    if index.form_kind != form_kind:
        raise _refusal(
            422,
            "invariant",
            "QuestionnaireResponse.extension",
            f"the response declares form kind `{form_kind}`, but `{canonical}` is a `{index.form_kind}` form",
        )
    return index


def _period_issues(response: QuestionnaireResponse, naming: CaptureNaming) -> tuple[CaptureIssue, ...]:
    """Phase 3: the ISO period reads as a DHIS2 period, of the type declared, over the range claimed."""
    periods = _extensions(response, naming.period_url)
    iso_extensions = _sub_extensions(periods[0], PERIOD_ISO_SUB_EXTENSION)
    type_extensions = _sub_extensions(periods[0], PERIOD_TYPE_SUB_EXTENSION)
    iso = iso_extensions[0].valueString or ""
    declared_type = type_extensions[0].valueCode or ""
    try:
        parsed = parse_period(iso)
    except ValueError as error:
        return (_error("value", "QuestionnaireResponse.extension", str(error)),)
    issues: list[CaptureIssue] = []
    if parsed.period_type != declared_type:
        issues.append(
            _error(
                "value",
                "QuestionnaireResponse.extension",
                f"the ISO period `{iso}` is a `{parsed.period_type}` period, not a `{declared_type}` one",
            )
        )
    ranges = _sub_extensions(periods[0], PERIOD_RANGE_SUB_EXTENSION)
    claimed = ranges[0].valuePeriod if ranges else None
    if claimed is None:
        return tuple(issues)
    resolved_start = parsed.start_date.isoformat()
    resolved_end = parsed.end_date.isoformat()
    if claimed.start != resolved_start or claimed.end != resolved_end:
        issues.append(
            _warning(
                "value",
                "QuestionnaireResponse.extension",
                f"the date range {claimed.start} to {claimed.end} is not what the ISO period `{iso}` "
                f"resolves to ({resolved_start} to {resolved_end}); the ISO period is what is captured",
            )
        )
    return tuple(issues)


class _ItemValidator(BaseModel):
    """Phase 4: every answered item of one submission, walked against the index of the form it answers."""

    model_config = ConfigDict(frozen=True)

    index: CaptureIndex
    resolvers: CodingResolverSet
    strict: bool

    _issues: list[CaptureIssue] = PrivateAttr(default_factory=list)
    _answered: set[str] = PrivateAttr(default_factory=set)

    def run(self, response: QuestionnaireResponse) -> tuple[CaptureIssue, ...]:
        """Walk the submission's item tree, then note every required question it left unanswered."""
        self._walk(response.item or [])
        for question in self.index.questions.values():
            if question.required and question.link_id not in self._answered:
                self._issues.append(
                    _warning(
                        "required",
                        _item_expression(question.link_id),
                        f"`{question.link_id}` is required by the form and was not answered",
                    )
                )
        return tuple(self._issues)

    def _walk(self, items: list[QuestionnaireResponseItem]) -> None:
        """Read one level of the response's item tree, then the level below it."""
        for item in items:
            self._item(item)
            self._walk(item.item or [])

    def _item(self, item: QuestionnaireResponseItem) -> None:
        """Check one item against what the form says its link id is."""
        link_id = item.linkId
        if not link_id:
            self._issues.append(_error("required", "QuestionnaireResponse.item", "an item carries no `linkId`"))
            return
        if link_id in self.index.group_link_ids:
            if item.answer:
                self._issues.append(
                    _error(
                        "structure",
                        _item_expression(link_id),
                        f"`{link_id}` is a group of the form and carries no answer of its own",
                    )
                )
            return
        question = self.index.questions.get(link_id)
        if question is None:
            self._issues.append(
                _error(
                    "not-found",
                    _item_expression(link_id),
                    f"`{link_id}` is not a question of `{self.index.canonical}`",
                )
            )
            return
        if link_id in self._answered:
            self._issues.append(
                _error("invariant", _item_expression(link_id), f"`{link_id}` is answered more than once")
            )
            return
        self._answered.add(link_id)
        self._answers(question, item.answer or [])

    def _answers(self, question: CaptureQuestion, answers: list[QuestionnaireResponseAnswer]) -> None:
        """Check the answers to one question: how many there may be, and what each one carries."""
        if len(answers) > 1 and not question.repeats:
            self._issues.append(
                _error(
                    "invariant",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` takes one answer, and {len(answers)} were sent",
                )
            )
            return
        selections: list[str] = []
        for answer in answers:
            self._answer(question, answer, selections)
        duplicated = sorted({code for code in selections if selections.count(code) > 1})
        if duplicated:
            self._issues.append(
                _error(
                    "business-rule",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` selects {', '.join(duplicated)} more than once",
                )
            )

    def _answer(
        self,
        question: CaptureQuestion,
        answer: QuestionnaireResponseAnswer,
        selections: list[str],
    ) -> None:
        """Check one answer: that it carries the element the question asks for, and a value that element admits."""
        carried = answer.model_dump(exclude_none=True)
        present = [name for name in ANSWER_VALUE_ELEMENTS if name in carried]
        if not present:
            self._issues.append(
                _error("required", _item_expression(question.link_id), f"`{question.link_id}` carries no value")
            )
            return
        if len(present) > 1:
            self._issues.append(
                _error(
                    "structure",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` carries more than one value ({', '.join(present)})",
                )
            )
            return
        if present[0] != question.answer_element:
            self._issues.append(
                _error(
                    "structure",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` answers as `{question.item_type}`, so it carries "
                    f"`{question.answer_element}`, not `{present[0]}`",
                )
            )
            return
        self._temporal(question, answer)
        self._bounds(question, answer)
        self._coding(question, answer, selections)

    def _temporal(self, question: CaptureQuestion, answer: QuestionnaireResponseAnswer) -> None:
        """Check a date, dateTime, or time answer against the R4 primitive it is written as."""
        if answer.valueDate is not None and not _is_full_date(answer.valueDate):
            self._issues.append(
                _error(
                    "value",
                    _item_expression(question.link_id),
                    f"`{answer.valueDate}` is not a full calendar date; a captured date names a day",
                )
            )
        if answer.valueDateTime is not None and not is_fhir_date_time(answer.valueDateTime):
            self._issues.append(
                _error("value", _item_expression(question.link_id), f"`{answer.valueDateTime}` is not an R4 dateTime")
            )
        if answer.valueTime is not None and not is_fhir_time(answer.valueTime):
            self._issues.append(
                _error("value", _item_expression(question.link_id), f"`{answer.valueTime}` is not an R4 time")
            )

    def _bounds(self, question: CaptureQuestion, answer: QuestionnaireResponseAnswer) -> None:
        """Check a numeric answer against the range the question's DHIS2 value type admits."""
        bounds = question.bounds
        if bounds is None:
            return
        value = answer.valueInteger if answer.valueInteger is not None else answer.valueDecimal
        if value is None:
            return
        if bounds.minimum_value is not None and value < bounds.minimum_value:
            self._issues.append(
                _error(
                    "value",
                    _item_expression(question.link_id),
                    f"{value} is below the minimum {bounds.minimum_value} `{question.link_id}` admits",
                )
            )
        if bounds.maximum_value is not None and value > bounds.maximum_value:
            self._issues.append(
                _error(
                    "value",
                    _item_expression(question.link_id),
                    f"{value} is above the maximum {bounds.maximum_value} `{question.link_id}` admits",
                )
            )

    def _coding(
        self,
        question: CaptureQuestion,
        answer: QuestionnaireResponseAnswer,
        selections: list[str],
    ) -> None:
        """Resolve a coded answer against the terminology the question binds, as strictly as the settings ask."""
        coding = answer.valueCoding
        if coding is None:
            return
        if not coding.code:
            self._issues.append(
                _error(
                    "required",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` carries a coding with no code",
                )
            )
            return
        selections.append(coding.code)
        system = question.option_system
        if system is None:
            self._issues.append(
                _warning(
                    "not-found",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` binds terminology this server does not publish, so `{coding.code}` "
                    f"was stored without being checked",
                )
            )
            return
        if coding.system and coding.system != system:
            self._issues.append(
                _error(
                    "code-invalid",
                    _item_expression(question.link_id),
                    f"`{question.link_id}` is answered from `{system}`, not `{coding.system}`",
                )
            )
            return
        resolver = self.resolvers.for_system(system)
        if resolver is None:
            self._issues.append(
                _warning(
                    "not-found",
                    _item_expression(question.link_id),
                    f"the code system `{system}` is not served here, so `{coding.code}` was stored unchecked",
                )
            )
            return
        try:
            resolved = resolver.resolve(coding.code, strict=self.strict)
        except AmbiguousCodingError as error:
            self._issues.append(_error("multiple-matches", _item_expression(question.link_id), error.diagnostics))
            return
        except UnresolvableCodingError as error:
            self._issues.append(
                CaptureIssue(
                    severity="error" if self.strict else "warning",
                    code="code-invalid",
                    expression=_item_expression(question.link_id),
                    diagnostics=error.diagnostics,
                )
            )
            return
        if resolved.matched_by != "concept-code":
            note = _fallback_note(question, coding.code, resolved)
            self._issues.append(_warning("code-invalid", _item_expression(question.link_id), note))


def _fallback_note(question: CaptureQuestion, code: str, resolved: ResolvedCoding) -> str:
    """What a client is told when its code named the right option in the wrong spelling."""
    return (
        f"linkId {question.link_id}: code '{code}' matched option {resolved.option_uid} by "
        f"{resolved.matched_by}; the contract expects concept code '{resolved.concept_code}'"
    )


def _settle(issues: tuple[CaptureIssue, ...], warnings: list[CaptureIssue]) -> None:
    """End one phase: refuse the submission when it found an error, otherwise carry its warnings forward."""
    if any(issue.is_error() for issue in issues):
        raise CaptureRejection(422, issues)
    warnings.extend(issues)


def _refusal(status: int, code: CaptureIssueCode, expression: str | None, diagnostics: str) -> CaptureRejection:
    """One issue, as the rejection a phase raises when it cannot go on."""
    return CaptureRejection(status, (_error(code, expression, diagnostics),))


def _error(code: CaptureIssueCode, expression: str | None, diagnostics: str) -> CaptureIssue:
    """One issue that refuses the submission."""
    return CaptureIssue(severity="error", code=code, expression=expression, diagnostics=diagnostics)


def _warning(code: CaptureIssueCode, expression: str | None, diagnostics: str) -> CaptureIssue:
    """One issue that annotates an accepted submission."""
    return CaptureIssue(severity="warning", code=code, expression=expression, diagnostics=diagnostics)


def _extensions(response: QuestionnaireResponse, url: str) -> tuple[Extension, ...]:
    """Every extension the response carries under one url."""
    return tuple(extension for extension in response.extension or [] if extension.url == url)


def _sub_extensions(extension: Extension, url: str) -> tuple[Extension, ...]:
    """Every sub-extension one complex extension carries under one slice url."""
    return tuple(nested for nested in extension.extension or [] if nested.url == url)


def _expression(location: object) -> str | None:
    """Name the element a pydantic error points at, in the dotted form an OperationOutcome carries."""
    if not isinstance(location, tuple) or not location:
        return None
    return ".".join(str(part) for part in cast(tuple[object, ...], location))


def _item_expression(link_id: str) -> str:
    """Name one answered item as FHIRPath into the submission."""
    return f"QuestionnaireResponse.item.where(linkId='{link_id}')"


def _is_location_reference(reference: str) -> bool:
    """Whether a reference names a DHIS2 organisation unit's Location instance."""
    return reference.startswith(LOCATION_REFERENCE_PREFIX) and len(reference) > len(LOCATION_REFERENCE_PREFIX)


def _is_full_date(value: str) -> bool:
    """Whether a captured date names a day rather than a year or a month."""
    return is_fhir_date(value) and len(value.split("-")) == _FULL_DATE_PARTS

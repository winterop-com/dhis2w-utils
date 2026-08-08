"""The capture index: one served Questionnaire, read once into what a received response is checked against.

A compiled Questionnaire is a tree; validating an answer against it is a lookup. The index does
that flattening once - every question keyed by its `linkId`, every group link id in a set - so a
submission with two thousand cells costs two thousand dictionary hits and no tree walks.

Two link-id shapes reach a question. A plain question is one DHIS2 data element, and its link id
is the data element UID. A cell of a disaggregated aggregate form is one data element crossed
with one category option combo, and its link id is `<dataElement>.<categoryOptionCombo>` - the
form the questionnaire emitter writes and the only place the pair is carried on the wire.

Terminology binding is resolved here too. A `#choice` question names an `answerValueSet`, and the
CodeSystem behind it is what a coded answer's codes are resolved against. When the value set is
not in the store the binding stays open: `option_system` is None and the capture path validates
coded answers leniently with a warning, because refusing a code against terminology this server
never published would blame the client for the project's own incomplete IG.
"""

from __future__ import annotations

from typing import Any, Literal

from dhis2w_fhir.r4 import Questionnaire, QuestionnaireItem, ValueSet
from dhis2w_fhir.resources.questionnaires.schemas import FORM_KIND_PROFILES, FormKind, NumericBounds
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.store import ResourceStore

QuestionKind = Literal["plain", "cell"]
"""Whether a question captures a data element on its own, or one cell of its disaggregation."""

#: The resource type a questionnaire canonical has to resolve to.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"

#: The separator a disaggregated cell's link id joins its data element and category option combo with.
CELL_LINK_ID_SEPARATOR = "."

#: The `value[x]` element a question answers on, keyed by the R4 item type the questionnaire gives it.
#: The inverse of what the emitter writes: `ITEM_TYPES_BY_VALUE_TYPE` maps a DHIS2 value type onto an
#: item type, and this maps that item type onto the element an answer to it carries.
ANSWER_ELEMENTS_BY_ITEM_TYPE = {
    "boolean": "valueBoolean",
    "decimal": "valueDecimal",
    "integer": "valueInteger",
    "date": "valueDate",
    "dateTime": "valueDateTime",
    "time": "valueTime",
    "string": "valueString",
    "text": "valueString",
    "url": "valueUri",
    "attachment": "valueAttachment",
    "choice": "valueCoding",
    "open-choice": "valueCoding",
    "reference": "valueReference",
}

#: The item types that carry no answer of their own and only nest other items.
_STRUCTURAL_ITEM_TYPES = ("group", "display")

#: The DHIS2 form kinds a served Questionnaire may declare.
FORM_KINDS: tuple[FormKind, ...] = tuple(FORM_KIND_PROFILES)

#: The extensions a numeric question carries its inclusive bounds on.
_MINIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
_MAXIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"


class UnreadableQuestionnaireError(LookupError):
    """Raised when a canonical does not resolve to a Questionnaire this facade can check answers against."""

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


class CaptureQuestion(BaseModel):
    """One answerable question of a served form, as a received answer is checked against it."""

    model_config = ConfigDict(frozen=True)

    link_id: str
    kind: QuestionKind
    data_element_uid: str
    category_option_combo_uid: str | None = None
    item_type: str
    answer_element: str
    repeats: bool = False
    required: bool = False
    bounds: NumericBounds | None = None
    option_system: str | None = None
    """Canonical of the CodeSystem a coded answer is resolved against, or None when the binding is open."""


class CaptureIndex(BaseModel):
    """One served Questionnaire flattened into the lookups a received response is validated with."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    form_kind: FormKind
    target_uid: str
    """The DHIS2 data set, event program, or program stage UID the form was generated from."""

    program_uid: str | None = None
    questions: dict[str, CaptureQuestion] = Field(default_factory=dict)
    group_link_ids: frozenset[str] = frozenset()


class CaptureIndexCache(BaseModel):
    """The per-canonical index cache one running facade keeps, built on first use and held for the process.

    The store is immutable for the life of the process, so an index built from it never goes
    stale. The cache is the facade's second stateful object after the spool, and like the spool
    it assumes the single writing process `d2w fhir serve` is.
    """

    model_config = ConfigDict(frozen=True)

    _indexes: dict[str, CaptureIndex] = PrivateAttr(default_factory=dict)

    def resolve(self, canonical: str, naming: CaptureNaming, store: ResourceStore) -> CaptureIndex:
        """The index for one questionnaire canonical, building it the first time it is asked for."""
        cached = self._indexes.get(canonical)
        if cached is not None:
            return cached
        entry = store.by_canonical(canonical)
        if entry is None:
            raise UnreadableQuestionnaireError(f"no Questionnaire with canonical `{canonical}` is served here")
        if entry.resource_type != QUESTIONNAIRE_RESOURCE_TYPE:
            raise UnreadableQuestionnaireError(
                f"`{canonical}` is served here as a {entry.resource_type}, not a Questionnaire"
            )
        index = build_capture_index(entry.body, naming, store)
        self._indexes[canonical] = index
        return index

    def count(self) -> int:
        """How many questionnaires have been indexed so far."""
        return len(self._indexes)


def build_capture_index(
    questionnaire_body: dict[str, Any],
    naming: CaptureNaming,
    store: ResourceStore,
) -> CaptureIndex:
    """Flatten one compiled Questionnaire into its capture index, resolving every terminology binding."""
    try:
        questionnaire = Questionnaire.model_validate(questionnaire_body)
    except ValidationError as error:
        raise UnreadableQuestionnaireError(f"the served Questionnaire could not be read ({error})") from error
    canonical = questionnaire.url
    if not canonical:
        raise UnreadableQuestionnaireError("the served Questionnaire carries no canonical url")
    form_kind = _form_kind(questionnaire, naming, canonical)

    questions: dict[str, CaptureQuestion] = {}
    group_link_ids: set[str] = set()
    _walk(questionnaire.item or [], store, questions, group_link_ids)

    return CaptureIndex(
        canonical=canonical,
        form_kind=form_kind,
        target_uid=canonical.rsplit("/", 1)[-1],
        program_uid=_program_uid(questionnaire, naming),
        questions=questions,
        group_link_ids=frozenset(group_link_ids),
    )


def _form_kind(questionnaire: Questionnaire, naming: CaptureNaming, canonical: str) -> FormKind:
    """The DHIS2 form kind the questionnaire declares on its D2FormType extension."""
    declared = {
        extension.valueCode
        for extension in questionnaire.extension or []
        if extension.url == naming.form_type_url and extension.valueCode is not None
    }
    for kind in FORM_KINDS:
        if kind in declared:
            return kind
    raise UnreadableQuestionnaireError(f"the served Questionnaire `{canonical}` declares no known DHIS2 form kind")


def _program_uid(questionnaire: Questionnaire, naming: CaptureNaming) -> str | None:
    """The DHIS2 program the form belongs to, as its grouping identifier names it."""
    for identifier in questionnaire.identifier or []:
        if identifier.system == naming.program_identifier_system and identifier.value:
            return identifier.value
    return None


def _walk(
    items: list[QuestionnaireItem],
    store: ResourceStore,
    questions: dict[str, CaptureQuestion],
    group_link_ids: set[str],
) -> None:
    """Collect every question and every group of one item subtree, in document order."""
    for item in items:
        link_id = item.linkId
        if not link_id:
            raise UnreadableQuestionnaireError("the served Questionnaire carries an item with no `linkId`")
        if item.type in _STRUCTURAL_ITEM_TYPES:
            group_link_ids.add(link_id)
            _walk(item.item or [], store, questions, group_link_ids)
            continue
        questions[link_id] = _question(item, link_id, store)
        _walk(item.item or [], store, questions, group_link_ids)


def _question(item: QuestionnaireItem, link_id: str, store: ResourceStore) -> CaptureQuestion:
    """Read one answerable item into the question a received answer is checked against."""
    answer_element = ANSWER_ELEMENTS_BY_ITEM_TYPE.get(item.type or "")
    if answer_element is None:
        raise UnreadableQuestionnaireError(
            f"the served Questionnaire answers `{link_id}` as `{item.type}`, which carries no capture element"
        )
    data_element_uid, separator, category_option_combo_uid = link_id.partition(CELL_LINK_ID_SEPARATOR)
    return CaptureQuestion(
        link_id=link_id,
        kind="cell" if separator else "plain",
        data_element_uid=data_element_uid,
        category_option_combo_uid=category_option_combo_uid if separator else None,
        item_type=item.type or "",
        answer_element=answer_element,
        repeats=bool(item.repeats),
        required=bool(item.required),
        bounds=_bounds(item),
        option_system=_option_system(item, store),
    )


def _bounds(item: QuestionnaireItem) -> NumericBounds | None:
    """The inclusive range the question's `minValue` / `maxValue` extensions pin, when it carries either."""
    minimum = _bound_value(item, _MINIMUM_VALUE_EXTENSION_URL)
    maximum = _bound_value(item, _MAXIMUM_VALUE_EXTENSION_URL)
    if minimum is None and maximum is None:
        return None
    return NumericBounds(minimum_value=minimum, maximum_value=maximum)


def _bound_value(item: QuestionnaireItem, url: str) -> int | None:
    """One bound, read from whichever numeric element the emitter wrote it on."""
    for extension in item.extension or []:
        if extension.url != url:
            continue
        if extension.valueInteger is not None:
            return extension.valueInteger
        if extension.valueDecimal is not None:
            return int(extension.valueDecimal)
    return None


def _option_system(item: QuestionnaireItem, store: ResourceStore) -> str | None:
    """The CodeSystem behind the question's `answerValueSet`, or None when the facade does not serve it."""
    if not item.answerValueSet:
        return None
    entry = store.by_canonical(item.answerValueSet)
    if entry is None:
        return None
    try:
        value_set = ValueSet.model_validate(entry.body)
    except ValidationError:
        return None
    for include in (value_set.compose.include if value_set.compose else None) or []:
        if include.system:
            return include.system
    return None

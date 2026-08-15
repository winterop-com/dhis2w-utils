"""The capture index: one served Questionnaire, read once into what a received response is checked against.

A compiled Questionnaire is a tree; validating an answer against it is a lookup. The index does
that flattening once - every question keyed by its `linkId`, every group link id in a set - so a
submission with two thousand cells costs two thousand dictionary hits and no tree walks.

Two link-id shapes reach a question. A plain question is one DHIS2 data element - or, on a tracker
registration form, one tracked entity attribute - and its link id is that object's UID, which is
why `CaptureQuestion.data_element_uid` carries an attribute UID for the registration kind. A cell
of a disaggregated aggregate form is one data element crossed with one category option combo, and
its link id is `<dataElement>.<categoryOptionCombo>` - the form the questionnaire emitter writes
and the only place the pair is carried on the wire.

Terminology binding is resolved here too. A `#choice` question names an `answerValueSet`, and the
CodeSystem behind it is what a coded answer's codes are resolved against. When the value set is
not in the store the binding stays open: `option_system` is None and the capture path validates
coded answers leniently with a warning, because refusing a code against terminology this server
never published would blame the client for the project's own incomplete IG.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from dhis2w_fhir.r4 import (
    DEFAULT_SUBJECT_RESOURCE_TYPE,
    CodeSystem,
    CodeSystemConcept,
    Coding,
    Questionnaire,
    QuestionnaireItem,
    QuestionnaireItemEnableWhen,
    QuestionnaireResponseAnswer,
    ResourceList,
    ValueSet,
)
from dhis2w_fhir.resources.questionnaires.schemas import CAPTURED_FORM_KINDS, FormKind
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from dhis2w_fhir_serve.capture.naming import CaptureNaming
from dhis2w_fhir_serve.store import ResourceStore

QuestionKind = Literal["plain", "cell"]
"""Whether a question captures a data element on its own, or one cell of its disaggregation."""

#: The resource type a questionnaire canonical has to resolve to.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"

#: The resource type a form's organisation-unit assignment is published as, and the prefix its
#: `D2OrganisationUnitAssignment` extension references it by.
ASSIGNMENT_RESOURCE_TYPE = "List"
ASSIGNMENT_REFERENCE_PREFIX = f"{ASSIGNMENT_RESOURCE_TYPE}/"

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

#: The DHIS2 form kinds this server captures a response for - every kind a generated Questionnaire
#: declares. A form whose kind is not here is refused when its index is first asked for, rather
#: than at the end of a capture that had nowhere to go.
FORM_KINDS: tuple[FormKind, ...] = CAPTURED_FORM_KINDS

#: The extensions a bounded question carries its inclusive range on - a number's or a calendar day's.
_MINIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
_MAXIMUM_VALUE_EXTENSION_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

#: The sub-extension urls a `d2-program-rule` repeat slices one DHIS2 program rule under.
_RULE_SUB_EXTENSION = "rule"
_RULE_NAME_SUB_EXTENSION = "name"
_RULE_DESCRIPTION_SUB_EXTENSION = "description"
_RULE_CONDITION_SUB_EXTENSION = "condition"
_RULE_ACTION_SUB_EXTENSION = "action"

#: The resource type a question's support terminology resolves to.
_CODE_SYSTEM_RESOURCE_TYPE = "CodeSystem"

#: The concept properties the generated support CodeSystems ride DHIS2 facts on: the value type
#: the data-element and attribute pairs both declare, and the uniqueness only the attribute pair does.
_VALUE_TYPE_PROPERTY = "value-type"
_UNIQUE_PROPERTY = "unique"


class UnreadableQuestionnaireError(LookupError):
    """Raised when a canonical does not resolve to a Questionnaire this facade can check answers against."""

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


class CaptureBound(BaseModel):
    """One end of the range a question admits, as its `minValue` / `maxValue` extension states it.

    The element the bound was written on is kept rather than flattened onto one number, because the
    three carry different facts: an integer bound belongs to a whole-number question, a decimal one
    to a measured quantity, and a date one to a calendar day - and `2026-01-01` is not a quantity at
    all. Every reader takes the end it can compare against and leaves the rest alone.
    """

    model_config = ConfigDict(frozen=True)

    integer: int | None = None
    decimal: float | None = None
    date: str | None = None

    @property
    def number(self) -> float | None:
        """The bound as a quantity, or None when it bounds a calendar day rather than a number."""
        return float(self.integer) if self.integer is not None else self.decimal

    @property
    def stated(self) -> str:
        """The bound spelled the way the form states it - the literal a refusal names back to a client."""
        if self.integer is not None:
            return str(self.integer)
        if self.decimal is not None:
            return str(self.decimal)
        return self.date or ""


class CaptureBounds(BaseModel):
    """The inclusive range one question admits, either end of it open."""

    model_config = ConfigDict(frozen=True)

    minimum: CaptureBound | None = None
    maximum: CaptureBound | None = None


class CaptureProgramRule(BaseModel):
    """One DHIS2 program rule the form declares its instance enforces when a submission is imported.

    The whole of it is a claim about the instance rather than about this server: nothing here is
    evaluated at capture, because DHIS2 evaluates its own rules on import and answers a violation
    with `E1300`. What the declaration buys is that a client can say which rules are waiting, and
    that a rejection naming a rule UID can be read back as the rule's own name.
    """

    model_config = ConfigDict(frozen=True)

    rule_uid: str
    name: str
    description: str | None = None
    condition: str
    """The rule's DHIS2 expression, in the machine spelling the instance holds it in."""

    action: str | None = None
    """The DHIS2 program rule action type, as `SHOWWARNING` or `ERRORONCOMPLETE`, when the form states one."""


class CaptureGate(BaseModel):
    """What one item of a served form is asked under: where it sits, and the conditions that show it.

    Every item gets one of these, groups included, because a group's `enableWhen` decides every
    question beneath it and a lookup keyed only by question would lose that. An item the form always
    asks carries no conditions, which is what almost every DHIS2-generated item is.
    """

    model_config = ConfigDict(frozen=True)

    link_id: str
    parent_link_id: str | None = None
    conditions: tuple[QuestionnaireItemEnableWhen, ...] = ()
    behavior: Literal["all", "any"] = "all"
    """How several conditions combine. `all` is the reading that asks fewer questions, which is the safe one."""


class CaptureQuestion(BaseModel):
    """One answerable question of a served form, as a received answer is checked against it."""

    model_config = ConfigDict(frozen=True)

    link_id: str
    kind: QuestionKind
    data_element_uid: str
    """The DHIS2 object the question asks: a data element, or a tracked entity attribute on the registration kind."""

    category_option_combo_uid: str | None = None
    item_type: str
    answer_element: str
    repeats: bool = False
    required: bool = False
    read_only: bool = False
    """Whether the form states that DHIS2 owns this question's value, as `item.readOnly`.

    True on a tracked entity attribute DHIS2 generates: the instance mints the value on import, so
    nothing a client sends for it is used. A generated attribute is answered by DHIS2 and therefore
    left unanswered by `$generate`, and its absence is admitted even when the form marks it required.
    """

    bounds: CaptureBounds | None = None
    option_system: str | None = None
    """Canonical of the CodeSystem a coded answer is resolved against, or None when the binding is open."""

    value_type: str | None = None
    """The DHIS2 value type the served support CodeSystem states for the question's object, when it serves one."""

    unique: bool = False
    """Whether the served terminology declares the question's tracked entity attribute a unique business identifier."""

    display: str | None = None
    """What the question's object is called - the support CodeSystem's display, else the item's own coding's."""


class QuestionFacts(BaseModel):
    """The DHIS2 facts a support-CodeSystem concept states about one question's object.

    A question's item codes its data element or tracked entity attribute from the generated
    support pair, and that CodeSystem's concept carries what the compiled Questionnaire itself
    does not: the DHIS2 value type, and - for a tracked entity attribute - whether DHIS2 declares
    it unique. Everything defaults to the absence a store without the pair serves.
    """

    model_config = ConfigDict(frozen=True)

    value_type: str | None = None
    unique: bool = False
    display: str | None = None


class CaptureAssignment(BaseModel):
    """The organisation units one form may be captured against, as its published assignment List names them.

    `references` holds the literal `Location/<id>` references the List entries carry, which is the
    exact spelling a subject, a tracker organisation-unit extension, and an `ORGANISATION_UNIT`
    answer are written in - so membership is a set lookup rather than a resolution.
    """

    model_config = ConfigDict(frozen=True)

    list_id: str
    references: frozenset[str] = frozenset()

    def admits(self, reference: str) -> bool:
        """Whether one Location reference is inside the assignment."""
        return reference in self.references


class CaptureAttributeOptionCombos(BaseModel):
    """The attribute-option-combo vocabulary one form declares, and the CodeSystem a coding into it names.

    `system` is None when the facade serves no readable ValueSet for the declared canonical. The
    declaration still stands - the form says its responses carry one - but which concepts are in it
    cannot be checked, exactly as an unpublished `answerValueSet` leaves a coded answer's binding open.
    """

    model_config = ConfigDict(frozen=True)

    value_set: str
    system: str | None = None


class CaptureIndex(BaseModel):
    """One served Questionnaire flattened into the lookups a received response is validated with."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    form_kind: FormKind
    target_uid: str
    """The DHIS2 data set, program, or program stage UID the form was generated from."""

    program_uid: str | None = None
    subject_type: str = DEFAULT_SUBJECT_RESOURCE_TYPE
    """The resource type the form declares its responses are about - `Questionnaire.subjectType`.

    A DHIS2 tracked entity type is not always a person, so a project maps its types onto the FHIR
    resource types they are and the generated form states the answer. The served form is the only
    place this facade reads it from: `fhir.toml` is the generator's input and is not on the server
    at all, so what a capture is checked against and what `$generate` mints is what the compiled
    Questionnaire says.
    """

    collects_incident_date: bool = False
    """Whether the program a registration form enrols into collects the date of the incident it follows.

    The form's own `D2CollectsIncidentDate` declaration, which is the only place this facade reads
    the fact from - a compiled store and a `--live` one publish the same declaration, so both
    generate the same registration envelope. A form declaring nothing reads as false, which is what
    the contract makes of a response carrying no `D2IncidentAt`: complete, the extension being 0..1.
    """

    program_rules: tuple[CaptureProgramRule, ...] = ()
    """The DHIS2 program rules the form declares, in the order it lists them - none on a form that lists none."""

    questions: dict[str, CaptureQuestion] = Field(default_factory=dict)
    group_link_ids: frozenset[str] = frozenset()
    gates: dict[str, CaptureGate] = Field(default_factory=dict)
    """Every item of the form, group and question alike, keyed by link id - what each one is asked under."""

    item_link_ids: tuple[str, ...] = ()
    """Every item's link id in document order, which is the order the gates resolve in - a parent before its child."""
    assignment: CaptureAssignment | None = None
    """The form's organisation-unit assignment, or None - which means every published unit may report it."""

    attribute_option_combos: CaptureAttributeOptionCombos | None = None
    """The vocabulary the form's responses key their values from, or None on the default category combo."""


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
    facts_cache: dict[str, dict[str, QuestionFacts]] = {}
    gates: dict[str, CaptureGate] = {}
    _walk(questionnaire.item or [], None, store, questions, group_link_ids, gates, facts_cache)

    return CaptureIndex(
        canonical=canonical,
        form_kind=form_kind,
        target_uid=canonical.rsplit("/", 1)[-1],
        program_uid=_program_uid(questionnaire, naming),
        subject_type=_subject_type(questionnaire),
        collects_incident_date=_collects_incident_date(questionnaire, naming),
        program_rules=_program_rules(questionnaire, naming),
        questions=questions,
        group_link_ids=frozenset(group_link_ids),
        gates=gates,
        item_link_ids=tuple(gates),
        assignment=_assignment(questionnaire, naming, store),
        attribute_option_combos=_attribute_option_combos(questionnaire, naming, store),
    )


def asked_link_ids(
    index: CaptureIndex,
    answers: Mapping[str, Sequence[QuestionnaireResponseAnswer]],
) -> frozenset[str]:
    """Every item the form is asking, given the answers on hand - R4 `enableWhen`, ancestors included.

    THE UNANSWERED RULE. A condition names a question, and a question with no answer satisfies no
    comparison: `=`, `!=`, and the four orderings are all false against nothing, because there is no
    value to compare. `exists` is the one operator that reads absence as a fact, and it holds when
    what it found matches the sense it states - `exists=false` against an unanswered question is
    true. A condition naming a question this form does not have never holds, which hides the item
    rather than showing it unconditionally: the conservative direction for a capture form.

    A HIDDEN ITEM CARRIES NO ANSWER. What the set leaves out is what a submission must not answer -
    a stale answer under a question the form stopped asking is exactly the state DHIS2's own program
    rules exist to prevent, and it would be forwarded as a real data value. Callers drop what falls
    outside the set rather than keeping it for later.

    The pass runs in document order, so an ancestor's verdict is settled before its children are
    reached and a group's conditions decide everything beneath it in one sweep.
    """
    asked: set[str] = set()
    for link_id in index.item_link_ids:
        gate = index.gates.get(link_id)
        if gate is None:
            continue
        if gate.parent_link_id is not None and gate.parent_link_id not in asked:
            continue
        if _conditions_hold(index, gate, answers):
            asked.add(link_id)
    return frozenset(asked)


def _conditions_hold(
    index: CaptureIndex,
    gate: CaptureGate,
    answers: Mapping[str, Sequence[QuestionnaireResponseAnswer]],
) -> bool:
    """Whether one item's own conditions hold - its ancestors are the sweep's business, not this."""
    if not gate.conditions:
        return True
    held = (_condition_holds(index, condition, answers) for condition in gate.conditions)
    return any(held) if gate.behavior == "any" else all(held)


def _condition_holds(
    index: CaptureIndex,
    condition: QuestionnaireItemEnableWhen,
    answers: Mapping[str, Sequence[QuestionnaireResponseAnswer]],
) -> bool:
    """Whether one condition holds against the answers to the question it names.

    R4: a comparison holds when *any* answer to the named question satisfies it, which is what makes
    a condition on a repeating question mean "one of these".
    """
    question = condition.question
    if not question or question not in index.questions:
        return False
    values = [value for answer in answers.get(question, ()) if (value := _comparable_answer(answer)) is not None]
    if condition.operator == "exists":
        return bool(values) == (condition.answerBoolean is not False)
    expected = _comparable_condition(condition)
    if expected is None or condition.operator is None:
        return False
    return any(_compares_as(value, expected, condition.operator) for value in values)


def _comparable_answer(answer: QuestionnaireResponseAnswer) -> bool | float | str | Coding | None:
    """What one answer compares as, or None when it carries nothing two operands can be compared on."""
    if answer.valueBoolean is not None:
        return answer.valueBoolean
    if answer.valueDecimal is not None:
        return float(answer.valueDecimal)
    if answer.valueInteger is not None:
        return float(answer.valueInteger)
    if answer.valueCoding is not None:
        return answer.valueCoding
    return answer.valueDate or answer.valueDateTime or answer.valueTime or answer.valueString or answer.valueUri


def _comparable_condition(condition: QuestionnaireItemEnableWhen) -> bool | float | str | Coding | None:
    """What one condition compares against, read off whichever `answer[x]` it states."""
    if condition.answerBoolean is not None:
        return condition.answerBoolean
    if condition.answerDecimal is not None:
        return float(condition.answerDecimal)
    if condition.answerInteger is not None:
        return float(condition.answerInteger)
    if condition.answerCoding is not None:
        return condition.answerCoding
    return condition.answerDate or condition.answerDateTime or condition.answerTime or condition.answerString


def _compares_as(left: bool | float | str | Coding, right: bool | float | str | Coding, operator: str) -> bool:
    """One comparison, over the kinds of operand R4 admits one on.

    A coding and a boolean answer equality and nothing else - "greater than a concept" means nothing -
    and two operands of different kinds compare false rather than being coerced: a form comparing a
    string against an integer has a bug in it, and answering true would show a question nobody wrote.
    Dates, dateTimes and times compare as text, which is exactly right for the ISO-8601 forms R4 pins.
    """
    if isinstance(left, Coding) or isinstance(right, Coding):
        if not isinstance(left, Coding) or not isinstance(right, Coding):
            return False
        same = left.code == right.code and (left.system is None or right.system is None or left.system == right.system)
        return same if operator == "=" else (not same if operator == "!=" else False)
    if isinstance(left, bool) or isinstance(right, bool):
        if not isinstance(left, bool) or not isinstance(right, bool):
            return False
        return (left == right) if operator == "=" else ((left != right) if operator == "!=" else False)
    if isinstance(left, str) != isinstance(right, str):
        return False
    return _orders_as(left, right, operator)


def _orders_as(left: float | str, right: float | str, operator: str) -> bool:
    """The six comparisons, over the two kinds of operand that admit an ordering."""
    if operator == "=":
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">":
        return left > right  # type: ignore[operator]
    if operator == "<":
        return left < right  # type: ignore[operator]
    if operator == ">=":
        return left >= right  # type: ignore[operator]
    if operator == "<=":
        return left <= right  # type: ignore[operator]
    return False


def _attribute_option_combos(
    questionnaire: Questionnaire, naming: CaptureNaming, store: ResourceStore
) -> CaptureAttributeOptionCombos | None:
    """The attribute-option-combo vocabulary the form declares, or None when it rides the default combo.

    A data set on the default category combo has one attribute option combo and declares nothing,
    so absence here is the contract saying its responses carry no `D2AttributeOptionCombo`.
    """
    for extension in questionnaire.extension or []:
        if extension.url != naming.attribute_option_combos_url or not extension.valueCanonical:
            continue
        return CaptureAttributeOptionCombos(
            value_set=extension.valueCanonical, system=_value_set_system(extension.valueCanonical, store)
        )
    return None


def _form_kind(questionnaire: Questionnaire, naming: CaptureNaming, canonical: str) -> FormKind:
    """The DHIS2 form kind the questionnaire declares on its D2FormType extension.

    Only a kind this server captures resolves: a form the facade serves and reads but cannot
    accept an answer to is refused here, when the index is first asked for, rather than at the
    end of a capture that had nowhere to go.
    """
    declared = {
        extension.valueCode
        for extension in questionnaire.extension or []
        if extension.url == naming.form_type_url and extension.valueCode is not None
    }
    for kind in FORM_KINDS:
        if kind in declared:
            return kind
    raise UnreadableQuestionnaireError(
        f"the served Questionnaire `{canonical}` declares no DHIS2 form kind this server captures "
        f"({', '.join(FORM_KINDS)})"
    )


def _collects_incident_date(questionnaire: Questionnaire, naming: CaptureNaming) -> bool:
    """Whether the form declares its program collects an incident date, false being both answers a form can give.

    A registration form states the fact either way and every other kind states nothing, so absence
    and an explicit false mean the same thing here: no incident date on a response to this form.
    """
    for extension in questionnaire.extension or []:
        if extension.url == naming.collects_incident_date_url and extension.valueBoolean is not None:
            return extension.valueBoolean
    return False


def _assignment(questionnaire: Questionnaire, naming: CaptureNaming, store: ResourceStore) -> CaptureAssignment | None:
    """The assignment List the form names, or None when it names none or the facade does not serve it.

    An unresolvable reference is treated as no assignment rather than as a refusal: the artifact is
    optional by design, and a served IG missing one is the project's incomplete build rather than
    the client's mistake - the same reasoning that leaves an unpublished ValueSet binding open.
    """
    for extension in questionnaire.extension or []:
        if extension.url != naming.organisation_unit_assignment_url:
            continue
        reference = extension.valueReference.reference if extension.valueReference else None
        if not reference or not reference.startswith(ASSIGNMENT_REFERENCE_PREFIX):
            continue
        list_id = reference.removeprefix(ASSIGNMENT_REFERENCE_PREFIX)
        entry = store.by_type_and_id(ASSIGNMENT_RESOURCE_TYPE, list_id)
        if entry is None:
            return None
        try:
            published = ResourceList.model_validate(entry.body)
        except ValidationError:
            return None
        return CaptureAssignment(
            list_id=list_id,
            references=frozenset(
                item.item.reference for item in published.entry or [] if item.item.reference is not None
            ),
        )
    return None


def _program_uid(questionnaire: Questionnaire, naming: CaptureNaming) -> str | None:
    """The DHIS2 program the form belongs to, as its grouping identifier names it."""
    for identifier in questionnaire.identifier or []:
        if identifier.system == naming.program_identifier_system and identifier.value:
            return identifier.value
    return None


def _subject_type(questionnaire: Questionnaire) -> str:
    """The resource type the form is answered about, or the default when it declares none.

    R4 makes `subjectType` optional and repeatable; a generated form always states exactly one, so
    the first entry is the answer and a form that states nothing is read as the default a project
    that configures nothing gets.
    """
    for resource_type in questionnaire.subjectType or []:
        if resource_type:
            return resource_type
    return DEFAULT_SUBJECT_RESOURCE_TYPE


def _walk(
    items: list[QuestionnaireItem],
    parent_link_id: str | None,
    store: ResourceStore,
    questions: dict[str, CaptureQuestion],
    group_link_ids: set[str],
    gates: dict[str, CaptureGate],
    facts_cache: dict[str, dict[str, QuestionFacts]],
) -> None:
    """Collect every question, every group, and every item's gate of one subtree, in document order."""
    for item in items:
        link_id = item.linkId
        if not link_id:
            raise UnreadableQuestionnaireError("the served Questionnaire carries an item with no `linkId`")
        gates[link_id] = CaptureGate(
            link_id=link_id,
            parent_link_id=parent_link_id,
            conditions=tuple(item.enableWhen or ()),
            behavior=item.enableBehavior or "all",
        )
        if item.type in _STRUCTURAL_ITEM_TYPES:
            group_link_ids.add(link_id)
        else:
            questions[link_id] = _question(item, link_id, store, facts_cache)
        _walk(item.item or [], link_id, store, questions, group_link_ids, gates, facts_cache)


def _question(
    item: QuestionnaireItem,
    link_id: str,
    store: ResourceStore,
    facts_cache: dict[str, dict[str, QuestionFacts]],
) -> CaptureQuestion:
    """Read one answerable item into the question a received answer is checked against."""
    answer_element = ANSWER_ELEMENTS_BY_ITEM_TYPE.get(item.type or "")
    if answer_element is None:
        raise UnreadableQuestionnaireError(
            f"the served Questionnaire answers `{link_id}` as `{item.type}`, which carries no capture element"
        )
    data_element_uid, separator, category_option_combo_uid = link_id.partition(CELL_LINK_ID_SEPARATOR)
    facts = _question_facts(item, store, facts_cache)
    return CaptureQuestion(
        link_id=link_id,
        kind="cell" if separator else "plain",
        data_element_uid=data_element_uid,
        category_option_combo_uid=category_option_combo_uid if separator else None,
        item_type=item.type or "",
        answer_element=answer_element,
        repeats=bool(item.repeats),
        required=bool(item.required),
        read_only=bool(item.readOnly),
        bounds=_bounds(item),
        option_system=_option_system(item, store),
        value_type=facts.value_type,
        unique=facts.unique,
        display=facts.display or _coding_display(item),
    )


def _question_facts(
    item: QuestionnaireItem,
    store: ResourceStore,
    facts_cache: dict[str, dict[str, QuestionFacts]],
) -> QuestionFacts:
    """The support-CodeSystem facts behind one question, resolved through the item's own coding."""
    for coding in item.code or []:
        if not coding.system or not coding.code:
            continue
        facts = _facts_for_system(coding.system, store, facts_cache).get(coding.code)
        if facts is not None:
            return facts
    return QuestionFacts()


def _facts_for_system(
    system: str,
    store: ResourceStore,
    facts_cache: dict[str, dict[str, QuestionFacts]],
) -> dict[str, QuestionFacts]:
    """Every concept's facts of one served support CodeSystem, parsed once per system per index build."""
    held = facts_cache.get(system)
    if held is not None:
        return held
    built: dict[str, QuestionFacts] = {}
    entry = store.by_canonical(system)
    if entry is not None and entry.resource_type == _CODE_SYSTEM_RESOURCE_TYPE:
        try:
            code_system = CodeSystem.model_validate(entry.body)
        except ValidationError:
            code_system = None
        for concept in (code_system.concept if code_system is not None else None) or []:
            if concept.code:
                built[concept.code] = _concept_facts(concept)
    facts_cache[system] = built
    return built


def _concept_facts(concept: CodeSystemConcept) -> QuestionFacts:
    """Read one support concept's DHIS2 properties into the facts a question carries."""
    value_type: str | None = None
    unique = False
    for concept_property in concept.property or []:
        if concept_property.code == _VALUE_TYPE_PROPERTY and concept_property.valueCode:
            value_type = concept_property.valueCode
        if concept_property.code == _UNIQUE_PROPERTY:
            unique = bool(concept_property.valueBoolean)
    return QuestionFacts(value_type=value_type, unique=unique, display=concept.display)


def _coding_display(item: QuestionnaireItem) -> str | None:
    """The display the item's own coding carries, which is the object's name as the emitter wrote it."""
    for coding in item.code or []:
        if coding.display:
            return coding.display
    return None


def _bounds(item: QuestionnaireItem) -> CaptureBounds | None:
    """The inclusive range the question's `minValue` / `maxValue` extensions pin, when it carries either."""
    minimum = _bound_value(item, _MINIMUM_VALUE_EXTENSION_URL)
    maximum = _bound_value(item, _MAXIMUM_VALUE_EXTENSION_URL)
    if minimum is None and maximum is None:
        return None
    return CaptureBounds(minimum=minimum, maximum=maximum)


def _bound_value(item: QuestionnaireItem, url: str) -> CaptureBound | None:
    """One bound, on whichever of the three elements R4 admits the extension was written with.

    The element is carried through rather than collapsed onto a number: a date bound is a calendar
    day and rounding one into an integer would state a bound the form never wrote.
    """
    for extension in item.extension or []:
        if extension.url != url:
            continue
        if extension.valueInteger is not None:
            return CaptureBound(integer=extension.valueInteger)
        if extension.valueDecimal is not None:
            return CaptureBound(decimal=float(extension.valueDecimal))
        if extension.valueDate is not None:
            return CaptureBound(date=extension.valueDate)
    return None


def _program_rules(questionnaire: Questionnaire, naming: CaptureNaming) -> tuple[CaptureProgramRule, ...]:
    """Every DHIS2 program rule the form declares, in the order it lists them.

    A rule missing its UID, its name, or its condition is passed over rather than published half
    read: the three together are what makes a rule nameable in a rejection, and a rule stated
    without them says less than nothing.
    """
    rules: list[CaptureProgramRule] = []
    for extension in questionnaire.extension or []:
        if extension.url != naming.program_rule_url:
            continue
        parts = {sub.url: sub for sub in extension.extension or [] if sub.url}
        stated = parts.get(_RULE_SUB_EXTENSION)
        named = parts.get(_RULE_NAME_SUB_EXTENSION)
        tested = parts.get(_RULE_CONDITION_SUB_EXTENSION)
        described = parts.get(_RULE_DESCRIPTION_SUB_EXTENSION)
        acted = parts.get(_RULE_ACTION_SUB_EXTENSION)
        rule_uid = stated.valueId if stated is not None else None
        name = named.valueString if named is not None else None
        condition = tested.valueString if tested is not None else None
        if not rule_uid or not name or not condition:
            continue
        rules.append(
            CaptureProgramRule(
                rule_uid=rule_uid,
                name=name,
                description=described.valueString if described is not None else None,
                condition=condition,
                action=acted.valueCode if acted is not None else None,
            )
        )
    return tuple(rules)


def _option_system(item: QuestionnaireItem, store: ResourceStore) -> str | None:
    """The CodeSystem behind the question's `answerValueSet`, or None when the facade does not serve it."""
    return _value_set_system(item.answerValueSet, store)


def _value_set_system(canonical: str | None, store: ResourceStore) -> str | None:
    """The CodeSystem one served ValueSet includes, or None when the facade serves no readable ValueSet for it."""
    if not canonical:
        return None
    entry = store.by_canonical(canonical)
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

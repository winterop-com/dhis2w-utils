"""DHIS2 program rules read onto a Questionnaire, in three tiers: bounds, enableWhen, and the rest.

DHIS2 enforces program rules on import: a tracker payload whose values a `SHOWERROR` rule refuses
comes back E1300 and no value lands. A generated form that states none of that asks for answers the
server will reject, so every rule the instance holds reaches the form - but only ever as much of it
as R4 can say without inventing a constraint DHIS2 does not enforce or dropping one it does.

Three tiers, and a rule is in exactly one of them:

1. A rule refusing a numeric answer outside a range becomes the core `minValue` / `maxValue`
   extensions on the question it tests.
2. A rule hiding one question on the value of another becomes core `item.enableWhen` entries on the
   question it hides. Where that question is answered from an option set, the DHIS2 rule compares
   against the option code the instance holds and the emitted condition names the concept code the
   bound CodeSystem publishes for that option, which `[generate] concept_code_source` and the
   hostile-name posture decide together. A literal no option of the set carries names no concept at
   all, so that rule goes to tier 3 rather than state a condition no answer can meet.
3. Every other rule is published as a `D2ProgramRule` extension on the Questionnaire, carrying the
   DHIS2 expression verbatim. Nothing about tier 3 is normative: it says the server holds a rule
   this form cannot express, so a consumer knows an answer the form admits may still be refused.

`parse_rule_condition` is what keeps the first two tiers honest. It reads one shape and no other -
a single comparison between one variable and one literal, optionally guarded by `d2:hasValue` on
that same variable - and refuses everything else whole. A rule half-translated would state a
constraint that is neither what DHIS2 enforces nor nothing, so a rule the grammar cannot take
entirely goes to tier 3 entirely.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import PROGRAM_RULE_ACTION_DEFINITIONS
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory, generate_note
from dhis2w_fhir.resources.option_sets.schemas import OptionConceptCodeIndex
from dhis2w_fhir.resources.questionnaires.schemas import (
    BOUND_ELEMENTS_BY_ITEM_TYPE,
    MAXIMUM_VALUE_EXTENSION_URL,
    MINIMUM_VALUE_EXTENSION_URL,
    ProgramRuleIn,
    ProgramRuleVariableIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    item_type,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The action codes a published rule may name itself by - the foundation code list's own concepts.
#: A guard test pins them against the generated `ProgramRuleActionType` enum on all three majors, so
#: a DHIS2 release adding an action type is a deliberate addition rather than a silent `UNKNOWN`.
PROGRAM_RULE_ACTION_TYPES = frozenset(action.code for action in PROGRAM_RULE_ACTION_DEFINITIONS)

#: What a rule whose action type is newer than this guide's code list is published as.
UNKNOWN_PROGRAM_RULE_ACTION = "UNKNOWN"

#: The DHIS2 rule-variable source types that read one question of the form being filled. Every other
#: source type - a previous event, a program-stage-scoped read, a calculated value - answers from
#: outside the single form a Questionnaire is, so a rule reading one is never translated.
_TRANSLATABLE_SOURCE_TYPES = frozenset(
    {"DATAELEMENT_CURRENT_EVENT", "DATAELEMENT_NEWEST_EVENT_PROGRAM", "TEI_ATTRIBUTE"}
)

#: The R4 `enableWhen.operator` codes, keyed by the DHIS2 comparison they invert. DHIS2 hides a
#: question when its condition holds and R4 shows one when its condition holds, so the operator a
#: hide is published under is the negation of the operator DHIS2 wrote.
_INVERTED_OPERATORS = {"==": "!=", "!=": "=", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}

#: The comparison written the other way round, for the literal-first mirror (`99 < #{x}`).
_MIRRORED_OPERATORS = {"==": "==", "!=": "!=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}

#: The R4 operators only an ordered answer admits. A string or a coding compares for equality alone,
#: so a DHIS2 rule ordering one is never translated.
_ORDERED_OPERATORS = frozenset({">", "<", ">=", "<="})

#: The item types whose answers are ordered, and the `answer[x]` element each compares on.
_ORDERED_ANSWER_ELEMENTS = {
    "integer": "answerInteger",
    "decimal": "answerDecimal",
    "date": "answerDate",
    "dateTime": "answerDateTime",
    "time": "answerTime",
}

#: The `answer[x]` element every translatable item type compares on. A type absent here - an
#: attachment, a reference, a url - is never the source of a published condition.
_ANSWER_ELEMENTS = {**_ORDERED_ANSWER_ELEMENTS, "string": "answerString", "text": "answerString"}

#: The `answer[x]` element a question answered from an option set compares on. The DHIS2 rule tests
#: the option code the instance stores, and the coding names the concept code the bound CodeSystem
#: publishes for that option, which the two are joined through `OptionConceptCodeIndex` to reach.
_CODING_ANSWER_ELEMENT = "answerCoding"

_VARIABLE = r"#\{\s*([^{}]+?)\s*\}"
_OPERATOR = r"(==|!=|<=|>=|<|>)"
_COMPARISON = re.compile(rf"^(?:{_VARIABLE}\s*{_OPERATOR}\s*(.+)|(.+?)\s*{_OPERATOR}\s*{_VARIABLE})$", re.DOTALL)
_HAS_VALUE_GUARD = re.compile(r"^d2:hasValue\(\s*(?:'([^']*)'|\"([^\"]*)\"|#\{\s*([^{}]+?)\s*\})\s*\)$")
_NUMBER_LITERAL = re.compile(r"^-?\d+(?:\.\d+)?$")
_STRING_LITERAL = re.compile(r"^'([^']*)'$|^\"([^\"]*)\"$")

#: What DHIS2 substitutes for a variable the event states no value for, per literal kind. The rule
#: engine evaluates a condition over a blank question rather than skipping it, so whether a hidden
#: question is shown before anything is answered is decided by comparing against this.
_BLANK_TEXT = ""
_BLANK_NUMBER = 0.0

LiteralKind = Literal["number", "string", "boolean"]


class RuleComparison(BaseModel):
    """One parsed DHIS2 condition: the variable it reads, how it compares, and the literal it compares to.

    `operator` is always written variable-first, so the literal-first mirror `99 < #{x}` parses to
    the same comparison `#{x} > 99` does.
    """

    model_config = ConfigDict(frozen=True)

    variable: str
    operator: str
    literal_kind: LiteralKind
    text: str = ""
    """The literal's characters for a string comparison, empty for the other two kinds."""

    number: float = 0.0
    """The literal's value for a numeric comparison, zero for the other two kinds."""

    boolean: bool = False
    """The literal's value for a boolean comparison, False for the other two kinds."""

    @property
    def is_blank_text(self) -> bool:
        """Whether the rule compares against the empty string - DHIS2's spelling of "no answer"."""
        return self.literal_kind == "string" and self.text == ""

    def holds_when_blank(self) -> bool:
        """Whether the condition is true of a question nobody has answered yet.

        DHIS2 evaluates a rule over a blank question by substituting the value type's empty value,
        so this decides whether a hidden question starts out hidden. R4 states the opposite for a
        question with no answer - an `enableWhen` a blank answer cannot satisfy leaves the question
        hidden - so a condition false when blank needs the `exists` arm that says so.
        """
        if self.literal_kind == "number":
            return _compare_numbers(_BLANK_NUMBER, self.operator, self.number)
        if self.literal_kind == "string":
            return _compare_equality(self.text == _BLANK_TEXT, self.operator)
        return _compare_equality(self.boolean is False, self.operator)


class EnableWhenCondition(BaseModel):
    """One R4 `enableWhen` entry: the question it reads, the operator, and the typed answer it compares to."""

    model_config = ConfigDict(frozen=True)

    question_link_id: str
    operator: str
    answer_element: str
    text: str = ""
    """The answer's characters for a string or a coding answer, empty otherwise."""

    number: float = 0.0
    integer: int = 0
    boolean: bool = False
    option_set_uid: str | None = None
    """Set exactly when `answer_element` is `answerCoding`, naming the ValueSet the code is drawn from."""


class ItemEnableWhen(BaseModel):
    """Every condition one question is shown under, and the behaviour joining them.

    `behavior` is None for a single condition, which R4 needs no `enableBehavior` for, and `"any"`
    where a hide inverts into a condition plus the `exists` arm that keeps a blank source faithful.
    """

    model_config = ConfigDict(frozen=True)

    conditions: list[EnableWhenCondition]
    behavior: str | None = None


class ProgramRuleBound(BaseModel):
    """One `minValue` / `maxValue` extension a program rule puts on the question it refuses answers to."""

    model_config = ConfigDict(frozen=True)

    url: str
    element: str
    integer: int | None = None
    decimal: float | None = None

    @property
    def literal(self) -> str:
        """The bound as the FSH literal its element takes."""
        if self.integer is not None:
            return str(self.integer)
        return _decimal_literal(self.decimal or 0.0)


class PublishedProgramRule(BaseModel):
    """One rule published as a `D2ProgramRule` entry: the rule this form could not express."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    description: str | None = None
    condition: str
    action: str
    translations: list[TranslationIn] = Field(default_factory=list)


class FormProgramRules(BaseModel):
    """What one form's program rules become on that form: bounds, enableWhen, and the published remainder.

    `bounds` and `enable_when` are keyed by the UID of the question they land on, which is that
    question's `linkId`. `published` holds the rules of the program neither tier expressed, in the
    order the instance returned them.
    """

    model_config = ConfigDict(frozen=True)

    bounds: dict[str, list[ProgramRuleBound]] = Field(default_factory=dict)
    enable_when: dict[str, ItemEnableWhen] = Field(default_factory=dict)
    published: list[PublishedProgramRule] = Field(default_factory=list)

    def bounds_for(self, question_uid: str) -> list[ProgramRuleBound]:
        """The rule-derived bounds one question carries, empty when no rule bounds it."""
        return self.bounds.get(question_uid, [])

    def enable_when_for(self, question_uid: str) -> ItemEnableWhen | None:
        """What one question is shown under, or None when no rule hides it."""
        return self.enable_when.get(question_uid)


class ProgramRulePlan(BaseModel):
    """One run's reading of every program rule, resolved per form so both emitters state the same thing.

    `notes` holds what the reading alone saw: a hide whose option literal the bound set publishes no
    concept for, which is a rule the guide states as its untranslated form.
    """

    model_config = ConfigDict(frozen=True)

    forms: dict[str, FormProgramRules] = Field(default_factory=dict)
    notes: list[GenerateNote] = Field(default_factory=list)

    def for_form(self, source_uid: str) -> FormProgramRules:
        """What one form publishes of its program's rules; an empty reading for a form with none."""
        return self.forms.get(source_uid, FormProgramRules())


def parse_rule_condition(condition: str) -> RuleComparison | None:
    """Parse a DHIS2 rule condition, or None for every expression outside the grammar.

    The grammar entire: one comparison between one `#{variable}` and one literal, in either order,
    optionally joined by `&&` to a `d2:hasValue` guard naming that same variable. A guard adds
    nothing R4 can say - `enableWhen` and the value bounds are both already conditioned on there
    being an answer - so it is read and dropped rather than refused.
    """
    guard, comparison = _split_guard(condition.strip())
    if comparison is None:
        return None
    if "&&" in comparison or "||" in comparison or "d2:" in comparison:
        return None
    if "A{" in comparison or "V{" in comparison or "C{" in comparison:
        return None
    match = _COMPARISON.match(comparison)
    if match is None:
        return None
    if match.group(1) is not None:
        variable, operator, literal_text = match.group(1), match.group(2), match.group(3)
    else:
        variable, operator, literal_text = match.group(6), _MIRRORED_OPERATORS[match.group(5)], match.group(4)
    if "#{" in literal_text:
        return None
    if guard is not None and guard != variable:
        return None
    return _parse_literal(variable, operator, literal_text.strip())


def plan_program_rules(
    sources: list[QuestionnaireSourceIn], option_concept_codes: OptionConceptCodeIndex | None = None
) -> ProgramRulePlan:
    """Read every source's program rules into what each form emits, one tier per rule.

    A rule is resolved once for the whole program and then written onto each of the program's forms,
    because whether it translates depends on where its questions are asked: a hide whose source
    question is on another stage's form is a hide this form cannot state, and the rule is published
    whole instead. That decision is taken here, once, so the FSH and the JSON never differ about it.

    `option_concept_codes` is the run's DHIS2-code-to-concept-code join, which a hide on a coded
    answer names its `answerCoding.code` out of. A reading handed none translates no coded hide at
    all: without the join there is no concept code to name, and a rule stated as a condition the
    published CodeSystem holds no code for is a rule the form gets wrong.
    """
    codes = option_concept_codes if option_concept_codes is not None else OptionConceptCodeIndex()
    forms: dict[str, FormProgramRules] = {}
    notes: list[GenerateNote] = []
    for program_sources in _sources_by_program(sources).values():
        rules = program_sources[0].program_rules
        variables = {variable.name: variable for variable in program_sources[0].program_rule_variables}
        questions = {source.uid: _questions_of(source) for source in program_sources}
        bounds: dict[str, dict[str, list[ProgramRuleBound]]] = {source.uid: {} for source in program_sources}
        enable_when: dict[str, dict[str, ItemEnableWhen]] = {source.uid: {} for source in program_sources}
        published: list[PublishedProgramRule] = []
        for rule in rules:
            unresolved: list[_UnresolvedOptionLiteral] = []
            reading = _read_rule(rule, variables, questions, codes, unresolved)
            if reading is None:
                if unresolved:
                    notes.append(
                        generate_note(
                            GenerateNoteCategory.FORM_STRUCTURE, _unresolved_literal_text(rule, unresolved[0])
                        )
                    )
                published.append(_published_rule(rule))
                continue
            for placed in reading.bounds:
                bounds[placed.form_uid].setdefault(placed.question_uid, []).append(placed.bound)
            for entry in reading.enable_when:
                enable_when[entry.form_uid][entry.question_uid] = entry.shown
        for source in program_sources:
            forms[source.uid] = FormProgramRules(
                bounds=bounds[source.uid], enable_when=enable_when[source.uid], published=published
            )
    return ProgramRulePlan(forms=forms, notes=notes)


def merged_bounds(
    value_type_bounds: list[ProgramRuleBound], rule_bounds: list[ProgramRuleBound]
) -> list[ProgramRuleBound]:
    """One bound per end, taking the tighter of what the value type admits and what a rule refuses.

    A `PERCENTAGE` question already states 0..100, and a rule refusing anything over 99 narrows the
    top end to 99. Publishing both would state one element twice; publishing the looser would state
    a range the server rejects answers from.
    """
    tightest: dict[str, ProgramRuleBound] = {}
    for bound in [*value_type_bounds, *rule_bounds]:
        held = tightest.get(bound.url)
        if held is None or _is_tighter(bound, held):
            tightest[bound.url] = bound
    return [tightest[url] for url in (MINIMUM_VALUE_EXTENSION_URL, MAXIMUM_VALUE_EXTENSION_URL) if url in tightest]


def value_type_bound(url: str, element: str, value: int) -> ProgramRuleBound:
    """One bound a DHIS2 value type states, as the same shape a rule-derived bound takes."""
    if element == "valueInteger":
        return ProgramRuleBound(url=url, element=element, integer=value)
    return ProgramRuleBound(url=url, element=element, decimal=float(value))


class _PlacedBound(BaseModel):
    """One bound, and the form and question it lands on."""

    model_config = ConfigDict(frozen=True)

    form_uid: str
    question_uid: str
    bound: ProgramRuleBound


class _PlacedEnableWhen(BaseModel):
    """One question's showing conditions, and the form the question is asked on."""

    model_config = ConfigDict(frozen=True)

    form_uid: str
    question_uid: str
    shown: ItemEnableWhen


class _UnresolvedOptionLiteral(BaseModel):
    """One rule literal the bound option set publishes no concept code for, and where the rule read it."""

    model_config = ConfigDict(frozen=True)

    question_uid: str
    option_set_uid: str
    literal: str


class _RuleReading(BaseModel):
    """What one fully translated rule puts on which form: its bounds and its enableWhen entries."""

    model_config = ConfigDict(frozen=True)

    bounds: list[_PlacedBound] = Field(default_factory=list)
    enable_when: list[_PlacedEnableWhen] = Field(default_factory=list)


def _read_rule(
    rule: ProgramRuleIn,
    variables: dict[str, ProgramRuleVariableIn],
    questions: dict[str, dict[str, QuestionnaireItemIn]],
    option_concept_codes: OptionConceptCodeIndex,
    unresolved: list[_UnresolvedOptionLiteral],
) -> _RuleReading | None:
    """Translate one rule onto the program's forms, or None when any part of it is inexpressible.

    `unresolved` collects the coded literals the bound sets publish no concept for, so a caller
    holding a refused rule can say which literal refused it.
    """
    comparison = parse_rule_condition(rule.condition)
    if comparison is None or not rule.actions:
        return None
    variable = variables.get(comparison.variable)
    if variable is None or variable.source_type not in _TRANSLATABLE_SOURCE_TYPES:
        return None
    source_uid = variable.question_uid
    if source_uid is None:
        return None
    action_types = {action.action_type for action in rule.actions}
    if action_types == {"SHOWERROR"}:
        return _read_bounding_rule(rule, comparison, source_uid, questions)
    if action_types == {"HIDEFIELD"}:
        return _read_hiding_rule(rule, comparison, source_uid, questions, option_concept_codes, unresolved)
    return None


def _read_bounding_rule(
    rule: ProgramRuleIn,
    comparison: RuleComparison,
    source_uid: str,
    questions: dict[str, dict[str, QuestionnaireItemIn]],
) -> _RuleReading | None:
    """Read a rule refusing answers outside a range as the bound it puts on the question it tests.

    Only where the rule refuses the very question it reads: a `SHOWERROR` displayed against another
    question still refuses on the value of this one, but a bound belongs on the element whose value
    is out of range and nowhere else.
    """
    if comparison.literal_kind != "number" or comparison.operator not in _ORDERED_OPERATORS:
        return None
    if any(action.question_uid != source_uid for action in rule.actions):
        return None
    bounds: list[_PlacedBound] = []
    for form_uid, form_questions in questions.items():
        question = form_questions.get(source_uid)
        if question is None:
            continue
        bound = _bound_of(comparison, question)
        if bound is None:
            return None
        bounds.append(_PlacedBound(form_uid=form_uid, question_uid=source_uid, bound=bound))
    return _RuleReading(bounds=bounds) if bounds else None


def _read_hiding_rule(
    rule: ProgramRuleIn,
    comparison: RuleComparison,
    source_uid: str,
    questions: dict[str, dict[str, QuestionnaireItemIn]],
    option_concept_codes: OptionConceptCodeIndex,
    unresolved: list[_UnresolvedOptionLiteral],
) -> _RuleReading | None:
    """Read a rule hiding questions on one other question's value as the `enableWhen` that shows them.

    Every question the rule hides must be asked on a form that also asks the question it reads:
    `enableWhen` names its source by `linkId`, and a `linkId` no item on the form carries points at
    nothing. A rule hiding a question this form asks from a source it does not is published whole.
    """
    entries: list[_PlacedEnableWhen] = []
    for action in rule.actions:
        target_uid = action.question_uid
        if target_uid is None or target_uid == source_uid:
            return None
        placed = False
        for form_uid, form_questions in questions.items():
            if target_uid not in form_questions:
                continue
            question = form_questions.get(source_uid)
            if question is None:
                return None
            shown = _shown_when(comparison, question, option_concept_codes, unresolved)
            if shown is None:
                return None
            entries.append(_PlacedEnableWhen(form_uid=form_uid, question_uid=target_uid, shown=shown))
            placed = True
        if not placed:
            return None
    return _RuleReading(enable_when=entries)


def _bound_of(comparison: RuleComparison, question: QuestionnaireItemIn) -> ProgramRuleBound | None:
    """The bound one refusing comparison puts on a question, or None where R4 cannot state it.

    The rule names what the server refuses, so the bound is its complement: refusing anything over
    99 admits up to and including 99. A strict refusal - anything from 99 up - has no inclusive
    complement in a decimal, which `minValue` and `maxValue` are the only elements for, so it is a
    bound only on a whole number, where the next admissible value is one step away.
    """
    element = BOUND_ELEMENTS_BY_ITEM_TYPE.get(item_type(question))
    if element is None or question.option_set_uid is not None:
        return None
    is_maximum = comparison.operator in (">", ">=")
    url = MAXIMUM_VALUE_EXTENSION_URL if is_maximum else MINIMUM_VALUE_EXTENSION_URL
    admits_the_limit = comparison.operator in (">", "<")
    if element == "valueInteger":
        limit = int(comparison.number)
        if float(limit) != comparison.number:
            return None
        if admits_the_limit:
            return ProgramRuleBound(url=url, element=element, integer=limit)
        return ProgramRuleBound(url=url, element=element, integer=limit - 1 if is_maximum else limit + 1)
    if not admits_the_limit:
        return None
    return ProgramRuleBound(url=url, element=element, decimal=comparison.number)


def _shown_when(
    comparison: RuleComparison,
    question: QuestionnaireItemIn,
    option_concept_codes: OptionConceptCodeIndex,
    unresolved: list[_UnresolvedOptionLiteral],
) -> ItemEnableWhen | None:
    """The `enableWhen` showing a question a rule hides, or None where R4 cannot state the inversion.

    Two things make the inversion faithful. The operator negates - a hide when the answer is
    `NEGATIVE` shows when it is anything else - and DHIS2's own reading of a blank question is
    carried over: where the DHIS2 condition is false of a blank answer, the question is shown before
    anything is answered, which R4 states as the `exists` arm joined by `enableBehavior = #any`.
    """
    resolved = item_type(question)
    operator = _INVERTED_OPERATORS[comparison.operator]
    if comparison.is_blank_text:
        exists = comparison.operator == "=="
        return ItemEnableWhen(
            conditions=[
                EnableWhenCondition(
                    question_link_id=question.uid, operator="exists", answer_element="answerBoolean", boolean=exists
                )
            ]
        )
    condition = _answer_condition(comparison, question, resolved, operator, option_concept_codes, unresolved)
    if condition is None:
        return None
    if comparison.holds_when_blank():
        return ItemEnableWhen(conditions=[condition])
    return ItemEnableWhen(
        conditions=[
            condition,
            EnableWhenCondition(
                question_link_id=question.uid, operator="exists", answer_element="answerBoolean", boolean=False
            ),
        ],
        behavior="any",
    )


def _answer_condition(
    comparison: RuleComparison,
    question: QuestionnaireItemIn,
    resolved_item_type: str,
    operator: str,
    option_concept_codes: OptionConceptCodeIndex,
    unresolved: list[_UnresolvedOptionLiteral],
) -> EnableWhenCondition | None:
    """One typed `enableWhen` entry, or None where the item type cannot answer the comparison.

    A coded answer compares on the concept code the bound CodeSystem publishes, which is the option
    UID under `concept_code_source = "id"` and the published code under `"code"` - the rewritten one
    where the substitute posture hyphenated it. The DHIS2 rule holds the option code the instance
    stores, so the join is what turns the one into the other; a literal the join has no option for
    refuses the condition and the whole rule with it.
    """
    if question.option_set_uid is not None:
        if comparison.literal_kind != "string" or operator in _ORDERED_OPERATORS:
            return None
        concept_code = option_concept_codes.concept_code(question.option_set_uid, comparison.text)
        if concept_code is None:
            unresolved.append(
                _UnresolvedOptionLiteral(
                    question_uid=question.uid, option_set_uid=question.option_set_uid, literal=comparison.text
                )
            )
            return None
        return EnableWhenCondition(
            question_link_id=question.uid,
            operator=operator,
            answer_element=_CODING_ANSWER_ELEMENT,
            text=concept_code,
            option_set_uid=question.option_set_uid,
        )
    if resolved_item_type == "boolean":
        if comparison.literal_kind != "boolean" or operator in _ORDERED_OPERATORS:
            return None
        return EnableWhenCondition(
            question_link_id=question.uid,
            operator=operator,
            answer_element="answerBoolean",
            boolean=comparison.boolean,
        )
    element = _ANSWER_ELEMENTS.get(resolved_item_type)
    if element is None:
        return None
    if operator in _ORDERED_OPERATORS and resolved_item_type not in _ORDERED_ANSWER_ELEMENTS:
        return None
    if element == "answerInteger":
        if comparison.literal_kind != "number" or float(int(comparison.number)) != comparison.number:
            return None
        return EnableWhenCondition(
            question_link_id=question.uid, operator=operator, answer_element=element, integer=int(comparison.number)
        )
    if element == "answerDecimal":
        if comparison.literal_kind != "number":
            return None
        return EnableWhenCondition(
            question_link_id=question.uid, operator=operator, answer_element=element, number=comparison.number
        )
    if element == "answerString":
        if comparison.literal_kind != "string":
            return None
        return EnableWhenCondition(
            question_link_id=question.uid, operator=operator, answer_element=element, text=comparison.text
        )
    return None


def _unresolved_literal_text(rule: ProgramRuleIn, unresolved: _UnresolvedOptionLiteral) -> str:
    """What one hide reports when the option set it reads publishes no concept for the literal it compares to."""
    return (
        f"program rule {rule.name!r} ({rule.uid}) hides on question {unresolved.question_uid} answering "
        f"{unresolved.literal!r}, which option set {unresolved.option_set_uid} publishes no concept for; "
        "the rule is published whole rather than as an enableWhen"
    )


def _published_rule(rule: ProgramRuleIn) -> PublishedProgramRule:
    """One rule as its `D2ProgramRule` entry, naming what it does through the guide's action code."""
    action = rule.actions[0].action_type if rule.actions else UNKNOWN_PROGRAM_RULE_ACTION
    return PublishedProgramRule(
        uid=rule.uid,
        name=rule.name,
        description=rule.description or None,
        condition=rule.condition,
        action=action if action in PROGRAM_RULE_ACTION_TYPES else UNKNOWN_PROGRAM_RULE_ACTION,
        translations=rule.translations,
    )


def _sources_by_program(sources: list[QuestionnaireSourceIn]) -> dict[str, list[QuestionnaireSourceIn]]:
    """The run's forms grouped by the program whose rules they carry, in the order the run read them."""
    grouped: dict[str, list[QuestionnaireSourceIn]] = {}
    for source in sources:
        if not source.program_rules:
            continue
        program_uid = source.program.uid if source.kind == "tracker-event" and source.program else source.uid
        grouped.setdefault(program_uid, []).append(source)
    return grouped


def _questions_of(source: QuestionnaireSourceIn) -> dict[str, QuestionnaireItemIn]:
    """Every question one form asks, keyed by the UID its `linkId` carries."""
    return {question.uid: question for question in _walk_questions(source)}


def _walk_questions(source: QuestionnaireSourceIn) -> Iterator[QuestionnaireItemIn]:
    """One form's questions, sections first and then the unsectioned rest."""
    for section in source.sections:
        yield from section.items
    yield from source.flat_items


def _split_guard(condition: str) -> tuple[str | None, str | None]:
    """Split one top-level `&&` into its `d2:hasValue` guard and the comparison beside it.

    Returns `(None, condition)` for an unjoined condition and `(None, None)` where the join is
    anything other than one guard and one comparison - two comparisons joined by `&&` state a rule
    over two questions, which neither tier expresses.
    """
    depth = 0
    for index, character in enumerate(condition):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0 and condition[index : index + 2] == "&&":
            left, right = condition[:index].strip(), condition[index + 2 :].strip()
            for guard_side, other in ((left, right), (right, left)):
                match = _HAS_VALUE_GUARD.match(guard_side)
                if match is not None:
                    return next(group for group in match.groups() if group is not None), other
            return None, None
    return None, condition


def _parse_literal(variable: str, operator: str, literal_text: str) -> RuleComparison | None:
    """Read the literal half of a comparison as one of the three kinds the grammar admits."""
    if _NUMBER_LITERAL.match(literal_text):
        return RuleComparison(variable=variable, operator=operator, literal_kind="number", number=float(literal_text))
    match = _STRING_LITERAL.match(literal_text)
    if match is not None:
        text = match.group(1) if match.group(1) is not None else match.group(2)
        return RuleComparison(variable=variable, operator=operator, literal_kind="string", text=text)
    if literal_text in ("true", "false"):
        return RuleComparison(
            variable=variable, operator=operator, literal_kind="boolean", boolean=literal_text == "true"
        )
    return None


def _compare_numbers(left: float, operator: str, right: float) -> bool:
    """Evaluate one numeric comparison the way the DHIS2 rule engine does."""
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    return left >= right


def _compare_equality(equal: bool, operator: str) -> bool:
    """Evaluate an equality comparison; an ordering over a non-numeric answer never holds when blank."""
    if operator == "==":
        return equal
    if operator == "!=":
        return not equal
    return False


def _is_tighter(candidate: ProgramRuleBound, held: ProgramRuleBound) -> bool:
    """Whether one bound admits fewer answers than another already stated at the same end."""
    candidate_value = candidate.integer if candidate.integer is not None else (candidate.decimal or 0.0)
    held_value = held.integer if held.integer is not None else (held.decimal or 0.0)
    if candidate.url == MINIMUM_VALUE_EXTENSION_URL:
        return candidate_value > held_value
    return candidate_value < held_value


def _decimal_literal(value: float) -> str:
    """A decimal bound as FSH writes it: a whole number keeps its point, so the value stays a decimal."""
    return str(int(value)) if value.is_integer() else str(value)

"""Which questions of a form an example may answer, read off the form's own `enableWhen`.

A generated Questionnaire states the DHIS2 hide rules it could express as `item.enableWhen`, and R4
reads a hidden item as one no response answers - the IG publisher says `Item has answer, even though
it is not enabled` about every example that answers one anyway. So an example answers the questions
the form turns out to be asking, and no others.

Which those are is not known until the draw is over: a condition names another question, and the
answer settling it is one the same example holds. The sweep therefore runs over a complete answer
set, and it runs to a fixed point - dropping an answer can close the question that depended on it,
so a chain of three conditions settles in three sweeps. It always terminates, because the answered
set only ever shrinks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.resources.option_sets.schemas import OptionConceptCodeIndex
from dhis2w_fhir.resources.questionnaires.program_rules import EnableWhenCondition, ItemEnableWhen

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dhis2w_fhir.resources.questionnaires.program_rules import FormProgramRules
    from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireSourceIn

__all__ = ["ExampleGate", "asked_question_uids", "form_gates", "settled_question_uids"]

#: The DHIS2 spellings of a true boolean answer, which is what a boolean condition compares against.
_TRUE_LITERALS = frozenset({"true", "1"})

#: The condition element a coded answer compares on, whose value is the concept code the answer's
#: own CodeSystem publishes rather than the DHIS2 option code a data value carries.
_CODING_ANSWER_ELEMENT = "answerCoding"


class ExampleGate(BaseModel):
    """One item of a form as an example reads it: what shows it, and the section it sits under."""

    model_config = ConfigDict(frozen=True)

    uid: str
    parent_uid: str | None = None
    shown: ItemEnableWhen | None = None


def form_gates(source: QuestionnaireSourceIn, rules: FormProgramRules) -> list[ExampleGate]:
    """Every item of one form in document order, sections before the questions they hold.

    A section carries its own conditions, which decide every question beneath it, so a sweep
    reaching a section before its children settles the whole branch in one pass.
    """
    gates: list[ExampleGate] = []
    for section in source.sections:
        gates.append(ExampleGate(uid=section.uid, shown=rules.enable_when_for(section.uid)))
        gates.extend(
            ExampleGate(uid=item.uid, parent_uid=section.uid, shown=rules.enable_when_for(item.uid))
            for item in section.items
        )
    gates.extend(ExampleGate(uid=item.uid, shown=rules.enable_when_for(item.uid)) for item in source.flat_items)
    return gates


def asked_question_uids(
    gates: list[ExampleGate],
    answers: Mapping[str, list[str]],
    option_concept_codes: OptionConceptCodeIndex | None = None,
) -> frozenset[str]:
    """Every item the form is asking given the answers on hand, ancestors included.

    A question with no answer satisfies no comparison: `=`, `!=`, and the four orderings are all
    false against nothing, because there is no value to compare. `exists` is the one operator that
    reads absence as a fact, and it holds when what it found matches the sense it states.

    `option_concept_codes` is the run's DHIS2-code-to-concept-code join. A coded condition compares
    against the concept code the CodeSystem publishes, and the answers here are the DHIS2 values a
    data value carries, so the drawn code is resolved through the same join the condition was
    written through.
    """
    codes = option_concept_codes if option_concept_codes is not None else OptionConceptCodeIndex()
    asked: set[str] = set()
    for gate in gates:
        if gate.parent_uid is not None and gate.parent_uid not in asked:
            continue
        if _conditions_hold(gate.shown, answers, codes):
            asked.add(gate.uid)
    return frozenset(asked)


def settled_question_uids(
    source: QuestionnaireSourceIn,
    rules: FormProgramRules,
    answers: Mapping[str, list[str]],
    option_concept_codes: OptionConceptCodeIndex | None = None,
) -> frozenset[str]:
    """The items one complete answer set leaves the form asking, swept to a fixed point."""
    gates = form_gates(source, rules)
    held = dict(answers)
    while True:
        asked = asked_question_uids(gates, held, option_concept_codes)
        kept = {uid: values for uid, values in held.items() if uid in asked}
        if len(kept) == len(held):
            return asked
        held = kept


def _conditions_hold(
    shown: ItemEnableWhen | None, answers: Mapping[str, list[str]], option_concept_codes: OptionConceptCodeIndex
) -> bool:
    """Whether one item's own conditions hold - its ancestors are the sweep's business, not this."""
    if shown is None or not shown.conditions:
        return True
    held = [_condition_holds(condition, answers, option_concept_codes) for condition in shown.conditions]
    return any(held) if shown.behavior == "any" else all(held)


def _condition_holds(
    condition: EnableWhenCondition, answers: Mapping[str, list[str]], option_concept_codes: OptionConceptCodeIndex
) -> bool:
    """Whether one condition holds against the stored DHIS2 values answering the question it names.

    R4 reads a comparison as holding when *any* answer to the named question satisfies it, which is
    what makes a condition on a repeating question mean "one of these".
    """
    values = answers.get(condition.question_link_id, [])
    if condition.operator == "exists":
        return bool(values) == condition.boolean
    return any(_value_satisfies(condition, value, option_concept_codes) for value in values)


def _value_satisfies(condition: EnableWhenCondition, value: str, option_concept_codes: OptionConceptCodeIndex) -> bool:
    """Whether one stored DHIS2 value satisfies one condition, read on the element the condition states."""
    if condition.answer_element == "answerBoolean":
        return _compares_equal(value.lower() in _TRUE_LITERALS, condition.boolean, condition.operator)
    if condition.answer_element == _CODING_ANSWER_ELEMENT:
        concept_code = option_concept_codes.concept_code(condition.option_set_uid or "", value)
        return concept_code is not None and _compares_equal(concept_code, condition.text, condition.operator)
    if condition.answer_element == "answerString":
        return _compares_equal(value, condition.text, condition.operator)
    number = _as_number(value)
    if number is None:
        return False
    expected = float(condition.integer if condition.answer_element == "answerInteger" else condition.number)
    return _compares_ordered(number, expected, condition.operator)


def _compares_equal(value: object, expected: object, operator: str) -> bool:
    """Whether an unordered answer satisfies an equality condition; every ordering is false of it."""
    if operator == "=":
        return value == expected
    if operator == "!=":
        return value != expected
    return False


def _compares_ordered(value: float, expected: float, operator: str) -> bool:
    """Whether a numeric answer satisfies one of R4's six comparison operators."""
    if operator == "=":
        return value == expected
    if operator == "!=":
        return value != expected
    if operator == ">":
        return value > expected
    if operator == "<":
        return value < expected
    if operator == ">=":
        return value >= expected
    return value <= expected


def _as_number(value: str) -> float | None:
    """One stored DHIS2 value as the number it compares as, or None when it holds no number."""
    try:
        return float(value)
    except ValueError:
        return None

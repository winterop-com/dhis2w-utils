"""Read the DHIS2 program rules a published form carries, in the three tiers they reach it under.

DHIS2 enforces program rules on import, not only in the Capture app: a tracker payload whose
values a `SHOWERROR` rule refuses comes back `E1300` and nothing lands. A form that stated none of
that would ask for answers the server rejects, so every rule a published program holds reaches its
forms - and each rule reaches them in exactly one of three tiers.

**Tier 1, a numeric refusal is a bound.** A rule whose only action is `SHOWERROR` and whose
condition compares one question against one number becomes the core `minValue` / `maxValue`
extensions on that question - the complement of what the rule refuses, so `#{hemoglobin} > 99`
with `SHOWERROR` publishes `maxValue` 99. A `SHOWWARNING` never becomes a bound: DHIS2 lets a
warned value through, and a bound a server accepts answers past is a constraint nobody enforces.

A bound on the form does not say which of two DHIS2 facts produced it - a rule, or the question's
own value type (`PERCENTAGE` admits 0 to 100, `INTEGER_POSITIVE` starts at 1). A client does not
need to know: both are refusals on import, and where the two disagree the tighter one is published.

**Tier 2, a single-question hide is `enableWhen`.** A rule whose actions are all `HIDEFIELD` and
whose condition compares one *other* question against one literal becomes `item.enableWhen` on
each question it hides. The operator comes out negated, because DHIS2 hides when its condition
holds and R4 shows when its own does - a hide when the apgar score is over 7 shows when it is 7 or
less. The second arm, `exists` with `answerBoolean` false, is the blank answer: R4 leaves a
question hidden while nothing satisfies its condition, and DHIS2 would show it, so the arm that
says "or nothing has been answered yet" is added and `enableBehavior` becomes `any`.

**Tier 3, everything else is published whole, non-normatively.** A rule R4 cannot state - two
variables, an `||` chain, a `d2:` function, a negation, an action on another stage's form - rides
a repeating `D2ProgramRule` extension carrying its DHIS2 UID, name, description, verbatim
condition, and action. Nothing about it is normative. It states that the server holds a rule this
form cannot express, so a consumer knows an answer the form admits may still be refused, and can
show the rule to a person even where it cannot evaluate it.

Every form of a program carries its program's rules, stage forms and registration form alike. An
aggregate form carries none: DHIS2 states program rules over programs.

Usage:
    uv run python examples/fhir/client/read_form_program_rules.py

Reads every form the example fixture publishes, from the facade the fixture serves.

The tiering rules are at docs/fhir/401-identifiers-and-extensions.md#program-rules.
"""

from __future__ import annotations

import httpx
from _fixture import example_project, served_facade
from _runner import run_example
from dhis2w_fhir import FoundationNaming, load_project
from dhis2w_fhir.r4 import Extension, Questionnaire, QuestionnaireItem, QuestionnaireItemEnableWhen

FHIR_JSON = "application/fhir+json"

#: The two core R4 extensions a tier-1 refusal, or a DHIS2 value type, publishes a question's limits on.
MINIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/minValue"
MAXIMUM_VALUE_URL = "http://hl7.org/fhir/StructureDefinition/maxValue"

#: The sub-extensions a published rule states itself with, in the order they read best.
RULE_SLICES = ("rule", "name", "action", "condition", "description")


def _bound(item: QuestionnaireItem, url: str) -> str | None:
    """The limit one question carries under `url`, typed to the item as R4 requires, or None."""
    for extension in item.extension or []:
        if extension.url == url:
            value = extension.valueInteger if extension.valueInteger is not None else extension.valueDecimal
            return str(value)
    return None


def _questions(items: list[QuestionnaireItem] | None) -> list[QuestionnaireItem]:
    """Every item of the tree, flattened, so a rule's effect is found wherever the form nests it."""
    found: list[QuestionnaireItem] = []
    for item in items or []:
        found.append(item)
        found.extend(_questions(item.item))
    return found


def _condition(arm: QuestionnaireItemEnableWhen) -> str:
    """One `enableWhen` arm as the sentence it is: this other question, this operator, this answer."""
    if arm.operator == "exists":
        # DHIS2 spells "no answer" as a comparison against the empty string, which R4 has no valid
        # form for, so it arrives as `exists` against a boolean instead.
        return f"{arm.question} {'has an answer' if arm.answerBoolean else 'has no answer yet'}"
    answers = (
        arm.answerBoolean,
        arm.answerDecimal,
        arm.answerInteger,
        arm.answerDate,
        arm.answerDateTime,
        arm.answerTime,
        arm.answerString,
        arm.answerCoding.code if arm.answerCoding else None,
    )
    answered = next((answer for answer in answers if answer is not None), "-")
    return f"{arm.question} {arm.operator} {answered}"


def _stated(part: Extension) -> str:
    """The one value a rule's sub-extension carries - its UID, its action code, or one of its strings."""
    return part.valueId or part.valueCode or part.valueString or "-"


def _published_rule(extension: Extension) -> str:
    """One tier-3 rule as `slice=value` pairs, its condition character for character as DHIS2 holds it."""
    carried = {part.url: part for part in extension.extension or []}
    return "; ".join(
        f"{slice_name}={_stated(carried[slice_name])}" for slice_name in RULE_SLICES if slice_name in carried
    )


def _report_form(form: Questionnaire, program_rule_url: str) -> None:
    """Print the three tiers one form carries, and say plainly which of them it carries nothing under."""
    questions = _questions(form.item)
    bounded = [item for item in questions if _bound(item, MINIMUM_VALUE_URL) or _bound(item, MAXIMUM_VALUE_URL)]
    conditioned = [item for item in questions if item.enableWhen]
    published = [extension for extension in form.extension or [] if extension.url == program_rule_url]

    if not (bounded or conditioned or published):
        print(f"{form.title}  ({form.code[0].code if form.code else 'unstated'} form): no rule reaches this form")
        print()
        return

    print(f"{form.title}  ({form.code[0].code if form.code else 'unstated'} form, Questionnaire/{form.id})")
    for item in bounded:
        lowest = _bound(item, MINIMUM_VALUE_URL)
        highest = _bound(item, MAXIMUM_VALUE_URL)
        limits = ", ".join(
            part for part in (f"from {lowest}" if lowest else "", f"up to {highest}" if highest else "") if part
        )
        print(f"  bound   {item.linkId:14} admits {limits:24} ({item.text})")
    for item in conditioned:
        joiner = " or " if item.enableBehavior == "any" else " and "
        arms = joiner.join(_condition(arm) for arm in item.enableWhen or [])
        print(f"  shown   {item.linkId:14} only when {arms}   ({item.text})")
    for extension in published:
        print(f"  held by DHIS2, not stated by this form: {_published_rule(extension)}")
    print()


async def main() -> None:
    """Read every published form and print the DHIS2 program rules each one carries, tier by tier."""
    project = load_project(example_project())
    naming = FoundationNaming.from_naming(project.config.generate.naming)
    program_rule_url = f"{project.config.ig.canonical}/StructureDefinition/{naming.program_rule_extension_id}"

    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        bundle = (await client.get("/Questionnaire", params={"_count": 100})).raise_for_status().json()

    for entry in bundle.get("entry", []):
        _report_form(Questionnaire.model_validate(entry["resource"]), program_rule_url)

    print("A bound and an `enableWhen` are the form's to enforce. A rule published whole is only the form")
    print("saying DHIS2 holds one it cannot express, so a value this form admits may still come back refused.")
    print("And a bound says nothing about which of the two produced it - a rule, or the DHIS2 value type.")


if __name__ == "__main__":
    run_example(main)

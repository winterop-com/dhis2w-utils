"""The three tiers a DHIS2 program rule reaches a form through, and the grammar that keeps them honest.

Every condition asserted here is one a live instance holds: the local stack's six rules and the
shapes the play `dev-2-43` corpus adds. The point of the grammar is what it refuses, so the refusals
are asserted as thoroughly as the translations - a rule the parser half-read would publish a
constraint neither DHIS2 nor R4 states.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_client.generated.v41.enums import ProgramRuleActionType as ProgramRuleActionTypeV41
from dhis2w_client.generated.v42.enums import ProgramRuleActionType as ProgramRuleActionTypeV42
from dhis2w_client.generated.v43.enums import ProgramRuleActionType as ProgramRuleActionTypeV43
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    build_questionnaire_artifacts,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.conversion.artifacts import CompiledArtifacts, program_rule_names
from dhis2w_fhir.conversion.schemas import CodedAnswerMode, ConversionNaming
from dhis2w_fhir.foundation.schemas import PROGRAM_RULE_ACTION_DEFINITIONS
from dhis2w_fhir.i18n import TranslationIn
from dhis2w_fhir.r4 import Questionnaire
from dhis2w_fhir.resources.option_sets import option_concept_code_index
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.questionnaires.program_rules import (
    PROGRAM_RULE_ACTION_TYPES,
    parse_rule_condition,
    plan_program_rules,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    ProgramRuleActionIn,
    ProgramRuleIn,
    ProgramRuleVariableIn,
)
from dhis2w_fhir.service import (
    ForwardImportIssue,
    ForwardImportOutcome,
    ForwardOutcome,
    ForwardOutcomeKind,
    ForwardReport,
)

_CANONICAL = "http://example.org/fhir"
_PROGRAM_RULE_URL = f"{_CANONICAL}/StructureDefinition/d2-program-rule"


def _question(uid: str, value_type: str = "NUMBER", option_set_uid: str | None = None) -> QuestionnaireItemIn:
    """One question of the form under test."""
    return QuestionnaireItemIn(uid=uid, name=uid, value_type=value_type, option_set_uid=option_set_uid)


def _variable(name: str, question_uid: str, source_type: str = "DATAELEMENT_CURRENT_EVENT") -> ProgramRuleVariableIn:
    """One rule variable reading one question of the form under test."""
    return ProgramRuleVariableIn(name=name, source_type=source_type, data_element_uid=question_uid)


def _rule(condition: str, action_type: str, target_uid: str, uid: str = "Rule1aaaaaa") -> ProgramRuleIn:
    """One program rule taking a single action against one question."""
    return ProgramRuleIn(
        uid=uid,
        name=f"rule {uid}",
        condition=condition,
        actions=[ProgramRuleActionIn(action_type=action_type, data_element_uid=target_uid)],
    )


def _source(
    rules: list[ProgramRuleIn], variables: list[ProgramRuleVariableIn], items: list[QuestionnaireItemIn]
) -> QuestionnaireSourceIn:
    """One event program form carrying the rules of its program."""
    return QuestionnaireSourceIn(
        uid="Prog1aaaaaa",
        name="Programme",
        kind="event",
        flat_items=items,
        program_rules=rules,
        program_rule_variables=variables,
    )


def _option(uid: str, code: str, original_code: str | None = None) -> OptionIn:
    """One option of the set under test, `original_code` set where the substitute posture rewrote its code."""
    return OptionIn(uid=uid, name=uid, code=code, original_code=original_code)


def _option_set(uid: str, options: list[OptionIn]) -> OptionSetIn:
    """One option set a question under test binds its answers to."""
    return OptionSetIn(uid=uid, name=uid, options=options)


def _plan(
    rules: list[ProgramRuleIn],
    variables: list[ProgramRuleVariableIn],
    items: list[QuestionnaireItemIn],
    option_sets: list[OptionSetIn] | None = None,
    config: GenerateConfig | None = None,
) -> Any:
    """One program's rules read against the concept codes the bound option sets publish."""
    resolved = config if config is not None else GenerateConfig()
    return plan_program_rules(
        [_source(rules, variables, items)], option_concept_code_index(option_sets or [], resolved)
    )


def _reading(
    rules: list[ProgramRuleIn],
    variables: list[ProgramRuleVariableIn],
    items: list[QuestionnaireItemIn],
    option_sets: list[OptionSetIn] | None = None,
    config: GenerateConfig | None = None,
) -> Any:
    """What one form publishes of its program's rules."""
    return _plan(rules, variables, items, option_sets, config).for_form("Prog1aaaaaa")


# The conditions the grammar takes, each with the variable, operator, and literal it reads out.
_PARSED = [
    ("#{hemoglobin} > 99", "hemoglobin", ">", 99.0),
    ("99 < #{hemoglobin}", "hemoglobin", ">", 99.0),
    ("#{apgarscore} > 7", "apgarscore", ">", 7.0),
    ("#{apgarscore} <0", "apgarscore", "<", 0.0),
    ("d2:hasValue('hemoglobin') && #{hemoglobin} > 99", "hemoglobin", ">", 99.0),
    ("#{hemoglobin} > 99 && d2:hasValue(#{hemoglobin})", "hemoglobin", ">", 99.0),
]

# Every shape the grammar refuses whole, with why. Each is a condition a live instance holds.
_REFUSED = [
    "#{apgarscore} >= 0 && #{apgarscore} < 4 && #{apgarcomment} == ''",
    "#{apgarscore} <0 && #{apgarcomment} == ''",
    "!#{womanSmoking} ",
    "#{allergies} !== 'Yes'",
    "#{Symptoms} == 'NO'  || #{Symptoms} == ''",
    "d2:hasValue('HHMalariaPositive')  && #{HHMalariaPositive} > #{HHMalariaTest}",
    "d2:hasValue('TestedBy') && #{MalariaSpecies} == ''",
    "(d2:yearsBetween(A{born},V{current_date}) < 12) ||  (d2:yearsBetween(A{born},V{current_date}) > 50)",
    "A{Sex} == 'MALE'",
    "d2:hasValue('lmp') && d2:daysBetween(#{lmp},V{event_date}) <= 0",
    "d2:validatePattern(A{mobile} ,'.*555.*')",
    "#{diastolicbloodpressure} > 0 && #{plurality} == 'Singleton'",
]


@pytest.mark.parametrize(("condition", "variable", "operator", "literal"), _PARSED)
def test_the_grammar_reads_one_comparison_between_a_variable_and_a_literal(
    condition: str, variable: str, operator: str, literal: float
) -> None:
    """A single comparison parses, in either order, with or without a `d2:hasValue` guard on the variable."""
    parsed = parse_rule_condition(condition)

    assert parsed is not None
    assert parsed.variable == variable
    assert parsed.operator == operator
    assert parsed.number == literal


@pytest.mark.parametrize("condition", _REFUSED)
def test_the_grammar_refuses_every_shape_it_cannot_read_whole(condition: str) -> None:
    """Multi-variable, multi-condition, negated, function-valued, and attribute-referencing rules go to tier 3."""
    assert parse_rule_condition(condition) is None


def test_a_guard_naming_a_different_variable_is_refused() -> None:
    """A `d2:hasValue` over one question guarding a comparison over another is a rule about two questions."""
    assert parse_rule_condition("d2:hasValue('lmp') && #{hemoglobin} > 99") is None


def test_a_refusing_rule_becomes_the_bound_it_states() -> None:
    """`SHOWERROR` when the answer is over 99 admits up to and including 99, which is what `maxValue` says."""
    reading = _reading(
        [_rule("#{hemoglobin} > 99", "SHOWERROR", "Hgb1aaaaaaa")],
        [_variable("hemoglobin", "Hgb1aaaaaaa")],
        [_question("Hgb1aaaaaaa")],
    )

    bounds = reading.bounds_for("Hgb1aaaaaaa")
    assert [(bound.url, bound.decimal) for bound in bounds] == [
        ("http://hl7.org/fhir/StructureDefinition/maxValue", 99.0)
    ]
    assert not reading.published


def test_a_strict_refusal_bounds_a_whole_number_one_step_in() -> None:
    """`SHOWERROR` from 99 up admits 98 at most, which an integer question can state and a decimal cannot."""
    integer_reading = _reading(
        [_rule("#{count} >= 99", "SHOWERROR", "Cnt1aaaaaaa")],
        [_variable("count", "Cnt1aaaaaaa")],
        [_question("Cnt1aaaaaaa", value_type="INTEGER")],
    )
    decimal_reading = _reading(
        [_rule("#{ratio} >= 99", "SHOWERROR", "Rat1aaaaaaa")],
        [_variable("ratio", "Rat1aaaaaaa")],
        [_question("Rat1aaaaaaa", value_type="NUMBER")],
    )

    assert [bound.integer for bound in integer_reading.bounds_for("Cnt1aaaaaaa")] == [98]
    assert not decimal_reading.bounds_for("Rat1aaaaaaa")
    assert [rule.uid for rule in decimal_reading.published] == ["Rule1aaaaaa"]


def test_a_rule_bound_narrows_the_bound_the_value_type_already_states() -> None:
    """A percentage already admits 0..100; a rule refusing anything over 99 states 99, and states it once."""
    reading = _reading(
        [_rule("#{share} > 99", "SHOWERROR", "Shr1aaaaaaa")],
        [_variable("share", "Shr1aaaaaaa")],
        [_question("Shr1aaaaaaa", value_type="PERCENTAGE")],
    )
    build = build_questionnaire_documents(
        [
            _source(
                [_rule("#{share} > 99", "SHOWERROR", "Shr1aaaaaaa")],
                [_variable("share", "Shr1aaaaaaa")],
                [_question("Shr1aaaaaaa", value_type="PERCENTAGE")],
            )
        ],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )

    assert [(bound.url.rsplit("/", 1)[-1], bound.decimal) for bound in reading.bounds_for("Shr1aaaaaaa")] == [
        ("maxValue", 99.0)
    ]
    carried = (build.questionnaires[0].item or [])[0].extension or []
    assert [(extension.url.rsplit("/", 1)[-1], extension.valueDecimal) for extension in carried] == [
        ("minValue", 0),
        ("maxValue", 99),
    ]


def test_a_warning_rule_is_published_rather_than_bound() -> None:
    """DHIS2 enforces the error actions on import and lets a warning through, so only an error is a bound."""
    reading = _reading(
        [_rule("#{hemoglobin} < 9", "SHOWWARNING", "Hgb1aaaaaaa")],
        [_variable("hemoglobin", "Hgb1aaaaaaa")],
        [_question("Hgb1aaaaaaa")],
    )

    assert not reading.bounds_for("Hgb1aaaaaaa")
    assert [(rule.uid, rule.action) for rule in reading.published] == [("Rule1aaaaaa", "SHOWWARNING")]


def test_a_hide_becomes_the_enable_when_that_shows_the_question() -> None:
    """DHIS2 hides when its condition holds and R4 shows when its own does, so the operator is negated."""
    reading = _reading(
        [_rule("#{apgarscore} > 7", "HIDEFIELD", "Cmt1aaaaaaa")],
        [_variable("apgarscore", "Apg1aaaaaaa")],
        [_question("Apg1aaaaaaa"), _question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )

    shown = reading.enable_when_for("Cmt1aaaaaaa")
    assert shown is not None
    assert [(entry.question_link_id, entry.operator) for entry in shown.conditions] == [
        ("Apg1aaaaaaa", "<="),
        ("Apg1aaaaaaa", "exists"),
    ]
    assert shown.behavior == "any"
    assert not reading.published


def test_a_hide_that_holds_of_a_blank_answer_needs_no_exists_arm() -> None:
    """DHIS2 reads a blank number as zero, so a hide when the answer is under seven starts out hiding."""
    reading = _reading(
        [_rule("#{apgarscore} < 7", "HIDEFIELD", "Cmt1aaaaaaa")],
        [_variable("apgarscore", "Apg1aaaaaaa")],
        [_question("Apg1aaaaaaa"), _question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )

    shown = reading.enable_when_for("Cmt1aaaaaaa")
    assert shown is not None
    assert [(entry.question_link_id, entry.operator, entry.number) for entry in shown.conditions] == [
        ("Apg1aaaaaaa", ">=", 7.0)
    ]
    assert shown.behavior is None


@pytest.mark.parametrize(("condition", "exists"), [("#{TestedBy} == ''", True), ("#{TestedBy} != ''", False)])
def test_a_comparison_against_the_empty_string_becomes_the_exists_operator(condition: str, exists: bool) -> None:
    """DHIS2 spells "no answer" as the empty string, which R4 states as `exists` - and never as an empty answer."""
    reading = _reading(
        [_rule(condition, "HIDEFIELD", "Oth1aaaaaaa")],
        [_variable("TestedBy", "Tst1aaaaaaa")],
        [_question("Tst1aaaaaaa", value_type="TEXT"), _question("Oth1aaaaaaa", value_type="TEXT")],
    )

    shown = reading.enable_when_for("Oth1aaaaaaa")
    assert shown is not None
    assert [(entry.operator, entry.boolean) for entry in shown.conditions] == [("exists", exists)]


_CODED_HIDE = [_rule("#{MalariaTestResult} == 'NEGATIVE'", "HIDEFIELD", "Spc1aaaaaaa")]
_CODED_HIDE_VARIABLES = [_variable("MalariaTestResult", "Res1aaaaaaa")]
_CODED_HIDE_ITEMS = [
    _question("Res1aaaaaaa", value_type="TEXT", option_set_uid="Os1aaaaaaaa"),
    _question("Spc1aaaaaaa", value_type="TEXT"),
]


def test_a_hide_on_an_option_set_answer_names_the_option_uid_under_the_id_code_source() -> None:
    """The rule holds the DHIS2 option code, and an id-source CodeSystem codes that option by its UID."""
    reading = _reading(
        _CODED_HIDE,
        _CODED_HIDE_VARIABLES,
        _CODED_HIDE_ITEMS,
        [_option_set("Os1aaaaaaaa", [_option("Opt1aaaaaaa", "NEGATIVE"), _option("Opt2aaaaaaa", "POSITIVE")])],
    )

    shown = reading.enable_when_for("Spc1aaaaaaa")
    assert shown is not None
    first = shown.conditions[0]
    assert (first.operator, first.answer_element, first.text, first.option_set_uid) == (
        "!=",
        "answerCoding",
        "Opt1aaaaaaa",
        "Os1aaaaaaaa",
    )


def test_a_hide_on_an_option_set_answer_names_the_option_code_under_the_code_code_source() -> None:
    """A code-source CodeSystem codes the option by its DHIS2 code, which is what the rule already holds."""
    reading = _reading(
        _CODED_HIDE,
        _CODED_HIDE_VARIABLES,
        _CODED_HIDE_ITEMS,
        [_option_set("Os1aaaaaaaa", [_option("Opt1aaaaaaa", "NEGATIVE"), _option("Opt2aaaaaaa", "POSITIVE")])],
        GenerateConfig(concept_code_source="code"),
    )

    shown = reading.enable_when_for("Spc1aaaaaaa")
    assert shown is not None
    assert shown.conditions[0].text == "NEGATIVE"


def test_a_hide_on_a_substituted_option_code_names_the_rewrite_the_guide_published() -> None:
    """The substitute posture hyphenates a code carrying a space, so the rule answer follows the rewrite."""
    reading = _reading(
        [_rule("#{MalariaTestResult} == 'Not detected'", "HIDEFIELD", "Spc1aaaaaaa")],
        _CODED_HIDE_VARIABLES,
        _CODED_HIDE_ITEMS,
        [_option_set("Os1aaaaaaaa", [_option("Opt1aaaaaaa", "Not-detected", original_code="Not detected")])],
        GenerateConfig(concept_code_source="code"),
    )

    shown = reading.enable_when_for("Spc1aaaaaaa")
    assert shown is not None
    assert shown.conditions[0].text == "Not-detected"


def test_a_hide_on_a_literal_no_option_carries_is_published_whole() -> None:
    """An `enableWhen` naming a code the bound CodeSystem never wrote is a condition no answer can meet."""
    plan = _plan(
        [_rule("#{MalariaTestResult} == 'OTHER'", "HIDEFIELD", "Spc1aaaaaaa")],
        _CODED_HIDE_VARIABLES,
        _CODED_HIDE_ITEMS,
        [_option_set("Os1aaaaaaaa", [_option("Opt1aaaaaaa", "NEGATIVE")])],
    )
    reading = plan.for_form("Prog1aaaaaa")

    assert reading.enable_when_for("Spc1aaaaaaa") is None
    assert [published.uid for published in reading.published] == ["Rule1aaaaaa"]
    assert len(plan.notes) == 1
    message = plan.notes[0].message
    assert "rule Rule1aaaaaa" in message
    assert "Res1aaaaaaa" in message
    assert "'OTHER'" in message


def test_a_hide_whose_source_question_the_form_does_not_ask_is_published_whole() -> None:
    """`enableWhen` names its source by link id, so a source no item carries would point at nothing."""
    reading = _reading(
        [_rule("#{apgarscore} > 7", "HIDEFIELD", "Cmt1aaaaaaa")],
        [_variable("apgarscore", "Elsewhere01")],
        [_question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )

    assert reading.enable_when_for("Cmt1aaaaaaa") is None
    assert [rule.uid for rule in reading.published] == ["Rule1aaaaaa"]


def test_a_rule_reading_a_source_type_outside_this_form_is_published_whole() -> None:
    """A variable reading a named program stage answers from outside the one form a Questionnaire is."""
    reading = _reading(
        [_rule("#{apgarscore} > 7", "HIDEFIELD", "Cmt1aaaaaaa")],
        [_variable("apgarscore", "Apg1aaaaaaa", source_type="DATAELEMENT_NEWEST_EVENT_PROGRAM_STAGE")],
        [_question("Apg1aaaaaaa"), _question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )

    assert reading.enable_when_for("Cmt1aaaaaaa") is None
    assert [rule.uid for rule in reading.published] == ["Rule1aaaaaa"]


def test_a_rule_hiding_several_questions_is_all_or_nothing() -> None:
    """One action this form cannot state makes the whole rule a published one - a partial hide is a lie."""
    rule = ProgramRuleIn(
        uid="Rule1aaaaaa",
        name="hide two",
        condition="#{apgarscore} > 7",
        actions=[
            ProgramRuleActionIn(action_type="HIDEFIELD", data_element_uid="Cmt1aaaaaaa"),
            ProgramRuleActionIn(action_type="HIDEFIELD", data_element_uid="Elsewhere01"),
        ],
    )
    reading = _reading(
        [rule],
        [_variable("apgarscore", "Apg1aaaaaaa")],
        [_question("Apg1aaaaaaa"), _question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )

    assert reading.enable_when_for("Cmt1aaaaaaa") is None
    assert [published.uid for published in reading.published] == ["Rule1aaaaaa"]


def test_a_published_rule_carries_the_dhis2_expression_verbatim() -> None:
    """The condition is the string an administrator searches the instance for, spacing and all."""
    condition = "!#{womanSmoking} "
    build = build_questionnaire_artifacts(
        [_source([_rule(condition, "HIDEFIELD", "Smk1aaaaaaa")], [], [_question("Smk1aaaaaaa")])],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )
    documents = build_questionnaire_documents(
        [_source([_rule(condition, "HIDEFIELD", "Smk1aaaaaaa")], [], [_question("Smk1aaaaaaa")])],
        GenerateConfig(),
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], GenerateConfig()),
        attribute_codes=AttributeCodeIndex(),
    )

    assert (
        f'* extension[D2ProgramRule][=].extension[condition].valueString = "{condition}"' in build.artifacts[0].content
    )
    carried = [
        sub.valueString
        for extension in documents.questionnaires[0].extension or []
        if extension.url.endswith("d2-program-rule")
        for sub in extension.extension or []
        if sub.url == "condition"
    ]
    assert carried == [condition]


def test_a_published_rule_carries_the_translations_dhis2_holds_for_it() -> None:
    """A rule's name and free text are translated in the instance, so they ride the standard extension."""
    rule = ProgramRuleIn(
        uid="Rule1aaaaaa",
        name="Hemoglobin warning",
        description="Show a warning",
        condition="#{hemoglobin} < 9",
        translations=[
            TranslationIn(locale="fr", property="NAME", value="Avertissement"),
            TranslationIn(locale="fr", property="DESCRIPTION", value="Montrer un avertissement"),
        ],
        actions=[ProgramRuleActionIn(action_type="SHOWWARNING", data_element_uid="Hgb1aaaaaaa")],
    )
    source = _source([rule], [_variable("hemoglobin", "Hgb1aaaaaaa")], [_question("Hgb1aaaaaaa")])
    config = GenerateConfig(locales=["fr"])
    build = build_questionnaire_artifacts(
        [source],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    documents = build_questionnaire_documents(
        [source],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )

    assert '.extension[name].valueString.extension[=].extension[=].valueString = "Avertissement"' in (
        build.artifacts[0].content
    )
    carried = {
        sub.url: sub
        for extension in documents.questionnaires[0].extension or []
        if extension.url.endswith("d2-program-rule")
        for sub in extension.extension or []
    }
    name_element = carried["name"].valueString_element
    assert name_element is not None
    translation = (name_element.extension or [])[0]
    assert (translation.extension or [])[1].valueString == "Avertissement"


def test_the_action_code_list_covers_every_action_type_all_three_majors_declare() -> None:
    """A DHIS2 release adding an action type is a deliberate addition here, never a silent `UNKNOWN`."""
    declared = (
        {member.value for member in ProgramRuleActionTypeV41}
        | {member.value for member in ProgramRuleActionTypeV42}
        | {member.value for member in ProgramRuleActionTypeV43}
    )

    assert declared <= PROGRAM_RULE_ACTION_TYPES
    assert PROGRAM_RULE_ACTION_TYPES - declared == {"UNKNOWN"}
    assert len({definition.code for definition in PROGRAM_RULE_ACTION_DEFINITIONS}) == len(
        PROGRAM_RULE_ACTION_DEFINITIONS
    )


def test_an_aggregate_form_publishes_no_program_rules() -> None:
    """DHIS2 states program rules over programs, so a data set's form carries none of this at all."""
    data_set = QuestionnaireSourceIn(
        uid="Ds1aaaaaaaa", name="Set", kind="aggregate", flat_items=[_question("De1aaaaaaaa")]
    )

    plan = plan_program_rules([data_set])

    assert not plan.for_form("Ds1aaaaaaaa").published


def test_a_refusal_naming_a_published_rule_reads_as_the_rules_name() -> None:
    """DHIS2 names the rule that refused an import by UID; the guide published the name beside it."""
    questionnaire = Questionnaire.model_validate(
        {
            "resourceType": "Questionnaire",
            "id": "Prog1aaaaaa",
            "extension": [
                {
                    "url": _PROGRAM_RULE_URL,
                    "extension": [
                        {"url": "rule", "valueId": "dahuKlP7jR2"},
                        {"url": "name", "valueString": "Show error for high hemoglobin value"},
                        {"url": "condition", "valueString": "#{hemoglobin} > 99"},
                        {"url": "action", "valueCode": "SHOWERROR"},
                    ],
                }
            ],
        }
    )
    naming = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)
    names = program_rule_names(CompiledArtifacts(questionnaires=(questionnaire,)), naming)
    report = ForwardReport(
        project_root=Path("."),
        dry_run=False,
        coded_answer_mode=CodedAnswerMode.LENIENT,
        outcomes=(
            ForwardOutcome(
                response_id="one",
                spool_path=".serve/responses/rejected/one.json",
                kind=ForwardOutcomeKind.REJECTED,
                import_outcome=ForwardImportOutcome(
                    status="ERROR",
                    issues=(
                        ForwardImportIssue(
                            error_code="E1300",
                            subject="EvT1aaaaaaa",
                            message=(
                                "Generated by ProgramRule (`dahuKlP7jR2`) - `The hemoglobin value cannot be above 99`"
                            ),
                        ),
                    ),
                ),
            ),
        ),
        program_rule_names=names,
    )

    assert names.name_for("dahuKlP7jR2") == "Show error for high hemoglobin value"
    reasons = report.rejection_reasons
    assert [reason.error_code for reason in reasons] == ["E1300"]
    assert reasons[0].reason == ("Generated by ProgramRule (`Show error for high hemoglobin value`) - `...`")


def test_a_refusal_naming_a_rule_the_guide_does_not_publish_still_generalises() -> None:
    """A UID this guide holds no rule for is generalised away, so one cause stays one row."""
    report = ForwardReport(
        project_root=Path("."),
        dry_run=False,
        coded_answer_mode=CodedAnswerMode.LENIENT,
        outcomes=(
            ForwardOutcome(
                response_id="one",
                spool_path=".serve/responses/rejected/one.json",
                kind=ForwardOutcomeKind.REJECTED,
                import_outcome=ForwardImportOutcome(
                    status="ERROR",
                    issues=(
                        ForwardImportIssue(error_code="E1300", message="Generated by ProgramRule (`abcdefghij1`)"),
                    ),
                ),
            ),
        ),
    )

    assert report.rejection_reasons[0].reason == "Generated by ProgramRule (`...`)"


def test_the_forwarded_report_keeps_the_raw_uid_on_the_response_itself() -> None:
    """The roll-up reads for a person and the response's own report stays the machine record."""
    issue = ForwardImportIssue(
        error_code="E1300", subject="EvT1aaaaaaa", message="Generated by ProgramRule (`dahuKlP7jR2`)"
    )
    outcome = ForwardImportOutcome(status="ERROR", issues=(issue,))

    filed = json.loads(outcome.model_dump_json(exclude_none=True))

    assert filed["issues"][0]["message"] == "Generated by ProgramRule (`dahuKlP7jR2`)"


def test_both_emitters_state_the_same_enable_when() -> None:
    """The FSH SUSHI compiles and the document a server hands out say one thing about what shows a question."""
    source = _source(
        [_rule("#{apgarscore} > 7", "HIDEFIELD", "Cmt1aaaaaaa")],
        [_variable("apgarscore", "Apg1aaaaaaa")],
        [_question("Apg1aaaaaaa"), _question("Cmt1aaaaaaa", value_type="LONG_TEXT")],
    )
    config = GenerateConfig()
    build = build_questionnaire_artifacts(
        [source],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )
    documents = build_questionnaire_documents(
        [source],
        config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=option_set_identities([], config),
        attribute_codes=AttributeCodeIndex(),
    )

    content = build.artifacts[0].content
    assert '* item[=].enableWhen[+].question = "Apg1aaaaaaa"' in content
    assert '* item[=].enableWhen[=].operator = #"<="' in content
    assert "* item[=].enableWhen[=].answerDecimal = 7" in content
    assert "* item[=].enableBehavior = #any" in content
    comment = next(item for item in documents.questionnaires[0].item or [] if item.linkId == "Cmt1aaaaaaa")
    assert [
        (entry.question, entry.operator, entry.answerDecimal, entry.answerBoolean) for entry in comment.enableWhen or []
    ] == [
        ("Apg1aaaaaaa", "<=", 7, None),
        ("Apg1aaaaaaa", "exists", None, False),
    ]
    assert comment.enableBehavior == "any"

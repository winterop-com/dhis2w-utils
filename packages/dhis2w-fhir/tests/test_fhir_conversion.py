"""Unit tests for the QR -> DHIS2 translator: every value type, both dials, and each refusal.

The emitters take DHIS2 values to a QuestionnaireResponse; this suite takes them back and asserts
the pair is an identity. Every case therefore starts from an `ExampleResponseIn` holding the DHIS2
wire strings an instance really serves, builds the response document the examples target would
publish for it, and translates that document back - so a change to either direction that breaks the
inverse fails here rather than against a live instance.

`test_fhir_conversion_roundtrip.py` runs the same identity over the committed source fixtures of a
whole generate run. What lives here is what those fixtures do not hold: the temporal value types,
option-set answers under both concept-code modes, `MULTI_TEXT`, `TRUE_ONLY`, organisation-unit
answers, code identity stems, and every way a response can refuse to translate at all.

The R4 models are frozen, so a case that needs a malformed response builds it with `model_copy`
through the small `_with_*` helpers rather than mutating what the emitter produced.
"""

from __future__ import annotations

import datetime

import pytest
from dhis2w_fhir import (
    AttributeCodeIndex,
    GenerateConfig,
    OptionSetIn,
    QuestionnaireItemIn,
    QuestionnaireSourceIn,
    build_example_documents,
    build_questionnaire_documents,
    option_set_identities,
)
from dhis2w_fhir.conversion import (
    CodedAnswerMode,
    ConversionContext,
    ConversionNaming,
    ConversionNoteCategory,
    ConversionRefusalCategory,
    ConversionResult,
    ConversionTargetKind,
    WireValueKind,
    build_conversion_context,
    decimal_wire_value,
    translate_response,
    translate_responses,
    wall_clock_reading,
)
from dhis2w_fhir.period import parse_period
from dhis2w_fhir.r4 import (
    Attachment,
    CodeSystem,
    Coding,
    Extension,
    Identifier,
    Location,
    Period,
    QuestionnaireResponse,
    QuestionnaireResponseAnswer,
    QuestionnaireResponseItem,
    Reference,
    ValueSet,
)
from dhis2w_fhir.resources.examples.schemas import ExampleAnswerIn, ExampleResponseIn
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, build_option_set_concept_maps
from dhis2w_fhir.resources.option_sets.schemas import OptionIn
from dhis2w_fhir.resources.questionnaires import source_items
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    ProgramContextIn,
    QuestionnaireSectionIn,
)

_CANONICAL = "http://example.org/fhir"
_ROOT_ORG_UNIT = "ImspTQPwCqd"
_CLINIC_ORG_UNIT = "DiszpKrYNg8"
_TRACKED_ENTITY = "Te1aaaaaaaa"
_ENROLLMENT = "En1aaaaaaaa"
_ZONE = "Asia/Vientiane"

_CODE_CONCEPTS = GenerateConfig(concept_code_source="code")
_ZONED = GenerateConfig(timezone=_ZONE)

#: The names the default project writes its responses under, which the malformed cases rebuild against.
_NAMING = ConversionNaming.from_config(GenerateConfig(), _CANONICAL)

#: The reporting period the captured data value set covers, as the D2Period extension carries it.
_MONTHLY_PERIOD = parse_period("202601")

#: The binary answer a FILE_RESOURCE question would carry, which DHIS2 stores as an upload instead.
_ATTACHMENT = Attachment(contentType="image/png", data="AA==", title="scan", size=1)

_DEFAULT_COMBO = CategoryComboIn(uid="bjDvmb4bfuf", name="default", is_default=True)
_AGE_COMBO = CategoryComboIn(
    uid="CcAaBbCcDdE",
    name="EPI/nutrition age",
    option_combos=[
        CategoryOptionComboIn(uid="Coc1aaaaaaa", name="<1y", code="U1"),
        CategoryOptionComboIn(uid="Coc2aaaaaaa", name=">1y"),
    ],
)

_GENDER_SET = OptionSetIn(
    uid="Os1aaaaaaaa",
    name="Gender",
    options=[
        OptionIn(uid="Op1aaaaaaaa", code="F", name="Female", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", code="M", name="Male", sort_order=2),
    ],
)
_SYMPTOM_SET = OptionSetIn(
    uid="Os2aaaaaaaa",
    name="Symptoms",
    options=[
        OptionIn(uid="Op3aaaaaaaa", code="FEV", name="Fever", sort_order=1),
        OptionIn(uid="Op4aaaaaaaa", code="CGH", name="Cough", sort_order=2),
        OptionIn(uid="Op5aaaaaaaa", code="RSH", name="Rash", sort_order=3),
    ],
)

#: An option set holding one DHIS2 code twice, so the second concept loses the code to its peer and
#: takes the UID instead - which leaves the set's ConceptMap the only artifact still carrying the code.
_REFERRAL_SET = OptionSetIn(
    uid="Os3aaaaaaaa",
    name="Referral",
    options=[
        OptionIn(uid="Op6aaaaaaaa", code="R", name="Referred", sort_order=1),
        OptionIn(uid="Op7aaaaaaaa", code="R", name="Re-referred", sort_order=2),
    ],
)
_OPTION_SETS = [_GENDER_SET, _SYMPTOM_SET, _REFERRAL_SET]

#: The CodeSystem canonical each option set is published at, which a coded answer names its system by.
_GENDER_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-os-gender-cs"
_REFERRAL_SYSTEM = f"{_CANONICAL}/CodeSystem/d2-os-referral-cs"

#: One question per DHIS2 value type the capture contract answers, so the inverse is checked exhaustively.
_TYPED_ITEMS = [
    QuestionnaireItemIn(uid="Dvt0000001a", name="Cases", value_type="INTEGER"),
    QuestionnaireItemIn(uid="Dvt0000002a", name="Beds", value_type="INTEGER_POSITIVE"),
    QuestionnaireItemIn(uid="Dvt0000003a", name="Deficit", value_type="INTEGER_NEGATIVE"),
    QuestionnaireItemIn(uid="Dvt0000004a", name="Stock", value_type="INTEGER_ZERO_OR_POSITIVE"),
    QuestionnaireItemIn(uid="Dvt0000005a", name="Weight", value_type="NUMBER"),
    QuestionnaireItemIn(uid="Dvt0000006a", name="Coverage", value_type="PERCENTAGE"),
    QuestionnaireItemIn(uid="Dvt0000007a", name="Ratio", value_type="UNIT_INTERVAL"),
    QuestionnaireItemIn(uid="Dvt0000008a", name="Referred", value_type="BOOLEAN"),
    QuestionnaireItemIn(uid="Dvt0000009a", name="Confirmed", value_type="TRUE_ONLY"),
    QuestionnaireItemIn(uid="Dvt0000010a", name="Notes", value_type="TEXT"),
    QuestionnaireItemIn(uid="Dvt0000011a", name="History", value_type="LONG_TEXT"),
    QuestionnaireItemIn(uid="Dvt0000012a", name="Grade", value_type="LETTER"),
    QuestionnaireItemIn(uid="Dvt0000013a", name="Phone", value_type="PHONE_NUMBER"),
    QuestionnaireItemIn(uid="Dvt0000014a", name="Email", value_type="EMAIL"),
    QuestionnaireItemIn(uid="Dvt0000015a", name="Operator", value_type="USERNAME"),
    QuestionnaireItemIn(uid="Dvt0000016a", name="Visit date", value_type="DATE"),
    QuestionnaireItemIn(uid="Dvt0000017a", name="Seen at", value_type="DATETIME"),
    QuestionnaireItemIn(uid="Dvt0000018a", name="Triage time", value_type="TIME"),
    QuestionnaireItemIn(uid="Dvt0000019a", name="Date of birth", value_type="AGE"),
    QuestionnaireItemIn(uid="Dvt0000020a", name="Record", value_type="URL"),
    QuestionnaireItemIn(uid="Dvt0000021a", name="Position", value_type="COORDINATE"),
    QuestionnaireItemIn(uid="Dvt0000022a", name="Referred to", value_type="ORGANISATION_UNIT"),
    QuestionnaireItemIn(uid="Dvt0000023a", name="Gender", value_type="TEXT", option_set_uid="Os1aaaaaaaa"),
    QuestionnaireItemIn(uid="Dvt0000024a", name="Symptoms", value_type="MULTI_TEXT", option_set_uid="Os2aaaaaaaa"),
]

#: The DHIS2 wire value an instance really serves for each typed question - zone-less, lexical, as stored.
_TYPED_VALUES = {
    "Dvt0000001a": "42",
    "Dvt0000002a": "7",
    "Dvt0000003a": "-3",
    "Dvt0000004a": "0",
    "Dvt0000005a": "13.4",
    "Dvt0000006a": "55.5",
    "Dvt0000007a": "0.25",
    "Dvt0000008a": "true",
    "Dvt0000009a": "true",
    "Dvt0000010a": "Seen in outpatients",
    "Dvt0000011a": "Referred by the district hospital",
    "Dvt0000012a": "A",
    "Dvt0000013a": "+23276000000",
    "Dvt0000014a": "clinic@example.invalid",
    "Dvt0000015a": "district_nurse",
    "Dvt0000016a": "2026-01-05",
    "Dvt0000017a": "2026-01-05T09:30:00",
    "Dvt0000018a": "09:30:00",
    "Dvt0000019a": "1990-04-01",
    "Dvt0000020a": "https://example.invalid/record/1",
    "Dvt0000021a": "[12.3,45.6]",
    "Dvt0000022a": _CLINIC_ORG_UNIT,
    "Dvt0000023a": "F",
    "Dvt0000024a": "FEV,CGH",
}

_TYPED_PROGRAM = QuestionnaireSourceIn(
    uid="Pr1aaaaaaaa", name="Value type sweep", kind="event", flat_items=_TYPED_ITEMS
)

_REFERRAL_PROGRAM = QuestionnaireSourceIn(
    uid="Pr2aaaaaaaa",
    name="Referral",
    kind="event",
    flat_items=[
        QuestionnaireItemIn(uid="De8aaaaaaaa", name="Referral", value_type="TEXT", option_set_uid="Os3aaaaaaaa")
    ],
)

_ATTACHMENT_PROGRAM = QuestionnaireSourceIn(
    uid="Pr3aaaaaaaa",
    name="Attachments",
    kind="event",
    flat_items=[QuestionnaireItemIn(uid="De9aaaaaaaa", name="Scan", value_type="FILE_RESOURCE")],
)

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    code="DS_CHILD",
    kind="aggregate",
    period_type="Monthly",
    sections=[
        QuestionnaireSectionIn(
            uid="Sec1aaaaaaa",
            name="Immunization",
            items=[
                QuestionnaireItemIn(
                    uid="De2aaaaaaaa", name="Measles doses given", value_type="INTEGER", category_combo=_AGE_COMBO
                ),
                QuestionnaireItemIn(
                    uid="De3aaaaaaaa",
                    name="Gender",
                    value_type="TEXT",
                    option_set_uid="Os1aaaaaaaa",
                    category_combo=_DEFAULT_COMBO,
                ),
            ],
        )
    ],
)

_BIRTH_STAGE = QuestionnaireSourceIn(
    uid="A03MvHHogjR",
    name="Birth",
    kind="tracker-event",
    program=ProgramContextIn(uid="IpHINAT79UW", name="Child Programme"),
    flat_items=[QuestionnaireItemIn(uid="a3kGcGDCuk6", name="Apgar Score", value_type="INTEGER")],
)


def _terminology(option_sets: list[OptionSetIn], config: GenerateConfig) -> tuple[list[CodeSystem], list[ValueSet]]:
    """The CodeSystem/ValueSet pair the terminology target writes for one selection, parsed back."""
    build = build_option_set_artifacts(
        option_sets, config, _CANONICAL, ig_status="draft", attribute_codes=AttributeCodeIndex()
    )
    code_systems: list[CodeSystem] = []
    value_sets: list[ValueSet] = []
    for artifact in build.artifacts:
        name = artifact.relative_path.rsplit("/", 1)[-1]
        if name.startswith("CodeSystem-"):
            code_systems.append(CodeSystem.model_validate_json(artifact.content))
        elif name.startswith("ValueSet-"):
            value_sets.append(ValueSet.model_validate_json(artifact.content))
    return code_systems, value_sets


def _locations(naming: ConversionNaming, stems_by_uid: dict[str, str]) -> list[Location]:
    """The registry's Locations, whose id is an identity stem and whose identifier is the DHIS2 UID."""
    return [
        Location(id=stem, identifier=[Identifier(system=naming.organisation_unit_system, value=uid)])
        for uid, stem in stems_by_uid.items()
    ]


def _context(
    sources: list[QuestionnaireSourceIn],
    *,
    config: GenerateConfig | None = None,
    coded_answer_mode: CodedAnswerMode = CodedAnswerMode.LENIENT,
    stems_by_uid: dict[str, str] | None = None,
    with_concept_maps: bool = True,
    with_value_types: bool = True,
) -> ConversionContext:
    """Assemble the translation context from the very artifacts a generate run publishes."""
    resolved_config = config if config is not None else GenerateConfig()
    plan = option_set_identities(_OPTION_SETS, resolved_config)
    questionnaires = build_questionnaire_documents(
        sources,
        resolved_config,
        _CANONICAL,
        ig_status="draft",
        option_set_plan=plan,
        attribute_codes=AttributeCodeIndex(),
    ).questionnaires
    code_systems, value_sets = _terminology(_OPTION_SETS, resolved_config)
    naming = ConversionNaming.from_config(resolved_config, _CANONICAL)
    stems = (
        stems_by_uid
        if stems_by_uid is not None
        else {_ROOT_ORG_UNIT: _ROOT_ORG_UNIT, _CLINIC_ORG_UNIT: _CLINIC_ORG_UNIT}
    )
    value_types = {item.uid: item.value_type for source in sources for item in source_items(source)}
    return build_conversion_context(
        naming,
        questionnaires,
        code_systems=code_systems,
        value_sets=value_sets,
        concept_maps=(
            build_option_set_concept_maps(_OPTION_SETS, resolved_config, _CANONICAL, ig_status="draft")
            if with_concept_maps
            else ()
        ),
        locations=_locations(naming, stems),
        value_types_by_data_element=value_types if with_value_types else None,
        coded_answer_mode=coded_answer_mode,
        timezone=resolved_config.timezone,
    )


def _document(
    response: ExampleResponseIn,
    sources: list[QuestionnaireSourceIn],
    *,
    config: GenerateConfig | None = None,
) -> QuestionnaireResponse:
    """The QuestionnaireResponse the examples target publishes for one captured response."""
    resolved_config = config if config is not None else GenerateConfig()
    build = build_example_documents(
        sources,
        [response],
        _OPTION_SETS,
        resolved_config,
        _CANONICAL,
        option_set_plan=option_set_identities(_OPTION_SETS, resolved_config),
    )
    return build.responses[0]


def _with_answers(
    response: QuestionnaireResponse, link_id: str, answers: list[QuestionnaireResponseAnswer] | None
) -> QuestionnaireResponse:
    """One response with the answers to a single question replaced, the frozen models copied through."""
    return response.model_copy(
        update={
            "item": [
                item.model_copy(update={"answer": answers}) if item.linkId == link_id else item
                for item in response.item or []
            ]
        }
    )


def _with_extension(response: QuestionnaireResponse, url: str, replacement: Extension | None) -> QuestionnaireResponse:
    """One response with the extension at `url` replaced, or dropped when there is no replacement."""
    kept = [extension for extension in response.extension or [] if extension.url != url]
    return response.model_copy(update={"extension": kept if replacement is None else [*kept, replacement]})


def _period_extension(iso: str, start: str, end: str) -> Extension:
    """A D2Period extension carrying one ISO period and the range it claims to cover."""
    return Extension(
        url=_NAMING.period_url,
        extension=[
            Extension(url="iso", valueString=iso),
            Extension(url="type", valueCode="Monthly"),
            Extension(url="period", valuePeriod=Period(start=start, end=end)),
        ],
    )


def _rewrite_locations(response: QuestionnaireResponse, stems: dict[str, str]) -> QuestionnaireResponse:
    """Rewrite every `Location/<uid>` reference of one response onto the code stem a registry published."""
    document = response.model_dump_json(exclude_none=True, by_alias=True)
    for uid, stem in stems.items():
        document = document.replace(f"Location/{uid}", f"Location/{stem}")
    return QuestionnaireResponse.model_validate_json(document)


def _typed_response(values: dict[str, str] | None = None) -> ExampleResponseIn:
    """One event response answering every typed question with the DHIS2 value an instance stores."""
    resolved = _TYPED_VALUES if values is None else values
    return ExampleResponseIn(
        instance_id="Pr1aaaaaaaa-example-1",
        target_uid=_TYPED_PROGRAM.uid,
        kind="event",
        organisation_unit_uid=_ROOT_ORG_UNIT,
        status_code="completed",
        authored="2026-01-05T09:30:00",
        answers=[ExampleAnswerIn(data_element_uid=uid, value=value) for uid, value in resolved.items()],
    )


def _aggregate_response() -> ExampleResponseIn:
    """One captured data value set: a disaggregated data element and a coded default-combo one."""
    return ExampleResponseIn(
        instance_id="BfMAe6Itzgt-202601-ImspTQPwCqd",
        target_uid=_DATA_SET.uid,
        kind="aggregate",
        organisation_unit_uid=_ROOT_ORG_UNIT,
        status_code="completed",
        period=_MONTHLY_PERIOD,
        answers=[
            ExampleAnswerIn(data_element_uid="De2aaaaaaaa", category_option_combo_uid="Coc1aaaaaaa", value="11"),
            ExampleAnswerIn(data_element_uid="De2aaaaaaaa", category_option_combo_uid="Coc2aaaaaaa", value="22"),
            ExampleAnswerIn(data_element_uid="De3aaaaaaaa", category_option_combo_uid="bjDvmb4bfuf", value="F"),
        ],
    )


def _tracker_response() -> ExampleResponseIn:
    """One captured tracker event: a stage answered for one enrolled tracked entity."""
    return ExampleResponseIn(
        instance_id="A03MvHHogjR-example-1",
        target_uid=_BIRTH_STAGE.uid,
        kind="tracker-event",
        organisation_unit_uid=_ROOT_ORG_UNIT,
        status_code="completed",
        authored="2026-01-05T09:30:00",
        tracked_entity_uid=_TRACKED_ENTITY,
        enrollment_uid=_ENROLLMENT,
        answers=[ExampleAnswerIn(data_element_uid="a3kGcGDCuk6", value="9")],
    )


def _aggregate_document() -> QuestionnaireResponse:
    """The QuestionnaireResponse the examples target publishes for the captured data value set."""
    return _document(_aggregate_response(), [_DATA_SET])


def _tracker_document() -> QuestionnaireResponse:
    """The QuestionnaireResponse the examples target publishes for the captured tracker event."""
    return _document(_tracker_response(), [_BIRTH_STAGE])


def _values(result: ConversionResult) -> dict[str, str | None]:
    """The event data values one result carries, keyed by data element."""
    assert result.event is not None
    return {value.dataElement or "": value.value for value in result.event.dataValues or []}


def _cells(result: ConversionResult) -> dict[tuple[str | None, str | None], str | None]:
    """The aggregate data values one result carries, keyed by data element and category option combo."""
    assert result.data_value_set is not None
    return {
        (value.dataElement, value.categoryOptionCombo): value.value for value in result.data_value_set.dataValues or []
    }


def _note_categories(result: ConversionResult) -> set[ConversionNoteCategory]:
    """Every note category one result raised."""
    return {note.category for note in result.notes}


def _refusal_categories(result: ConversionResult) -> set[ConversionRefusalCategory]:
    """Every refusal category one result raised."""
    return {refusal.category for refusal in result.refusals}


def _translate_typed(
    values: dict[str, str] | None = None,
    *,
    config: GenerateConfig | None = None,
    with_value_types: bool = True,
) -> ConversionResult:
    """Round-trip one typed event response through the emitter and back through the translator."""
    document = _document(_typed_response(values), [_TYPED_PROGRAM], config=config)
    return translate_response(document, _context([_TYPED_PROGRAM], config=config, with_value_types=with_value_types))


def _coded_document(coding: Coding, config: GenerateConfig | None = None) -> QuestionnaireResponse:
    """The typed response with its Gender answer replaced by one hand-written coding."""
    document = _document(_typed_response(), [_TYPED_PROGRAM], config=config)
    return _with_answers(document, "Dvt0000023a", [QuestionnaireResponseAnswer(valueCoding=coding)])


def _translate_coding(coding: Coding, mode: CodedAnswerMode, config: GenerateConfig | None = None) -> ConversionResult:
    """Translate the typed response with one hand-written coding under one coded-answer dial."""
    context = _context([_TYPED_PROGRAM], config=config, coded_answer_mode=mode)
    return translate_response(_coded_document(coding, config), context)


def _referral_document(concept_code: str) -> QuestionnaireResponse:
    """A code-mode Referral response answering the one question with a hand-written concept code."""
    response = ExampleResponseIn(
        instance_id="Pr2aaaaaaaa-example-1",
        target_uid=_REFERRAL_PROGRAM.uid,
        kind="event",
        organisation_unit_uid=_ROOT_ORG_UNIT,
        status_code="completed",
        authored="2026-01-05T09:30:00",
        answers=[ExampleAnswerIn(data_element_uid="De8aaaaaaaa", value="R")],
    )
    document = _document(response, [_REFERRAL_PROGRAM], config=_CODE_CONCEPTS)
    coding = Coding(system=_REFERRAL_SYSTEM, code=concept_code)
    return _with_answers(document, "De8aaaaaaaa", [QuestionnaireResponseAnswer(valueCoding=coding)])


def test_every_value_type_round_trips_to_the_dhis2_value_the_instance_stores() -> None:
    """The emitted response answers what DHIS2 stored, and the translator writes exactly that back."""
    result = _translate_typed()
    assert result.refusals == ()
    assert result.target_kind == ConversionTargetKind.EVENT
    assert _values(result) == _TYPED_VALUES


@pytest.mark.parametrize(
    ("link_id", "stored"),
    [
        ("Dvt0000001a", "42"),
        ("Dvt0000003a", "-3"),
        ("Dvt0000005a", "13.4"),
        ("Dvt0000007a", "0.25"),
        ("Dvt0000011a", "Referred by the district hospital"),
        ("Dvt0000016a", "2026-01-05"),
        ("Dvt0000017a", "2026-01-05T09:30:00"),
        ("Dvt0000018a", "09:30:00"),
        ("Dvt0000019a", "1990-04-01"),
        ("Dvt0000020a", "https://example.invalid/record/1"),
        ("Dvt0000021a", "[12.3,45.6]"),
        ("Dvt0000023a", "F"),
        ("Dvt0000024a", "FEV,CGH"),
    ],
)
def test_one_value_type_at_a_time_survives_the_round_trip(link_id: str, stored: str) -> None:
    """Each value type is checked on its own, so a failure names the type rather than the sweep."""
    assert _values(_translate_typed())[link_id] == stored


def test_a_whole_decimal_stays_whole_rather_than_gaining_a_fraction() -> None:
    """`2896` is a DHIS2 NUMBER value, and `2896.0` is a different string DHIS2 would store verbatim."""
    assert _values(_translate_typed(dict(_TYPED_VALUES) | {"Dvt0000005a": "2896"}))["Dvt0000005a"] == "2896"


@pytest.mark.parametrize(("carried", "written"), [(2896, "2896"), (13.4, "13.4"), (0.25, "0.25"), (1e-07, "0.0000001")])
def test_a_decimal_answer_is_written_without_a_float_round_trip(carried: int | float, written: str) -> None:
    """The R4 primitive is the lexical boundary; past it the shortest exact decimal is what travels."""
    assert decimal_wire_value(carried) == written


def test_a_multi_text_answer_joins_its_selections_the_way_dhis2_splits_them() -> None:
    """DHIS2 stores a MULTI_TEXT value as one comma-joined list of option codes, in selection order."""
    assert _values(_translate_typed(dict(_TYPED_VALUES) | {"Dvt0000024a": "RSH,FEV"}))["Dvt0000024a"] == "RSH,FEV"


def test_a_true_only_answer_is_written_as_true() -> None:
    """A TRUE_ONLY question DHIS2 holds a value for holds exactly `true`."""
    assert _values(_translate_typed())["Dvt0000009a"] == "true"


def test_a_true_only_question_answered_false_writes_no_data_value_at_all() -> None:
    """DHIS2 spells a false TRUE_ONLY as the absence of the value, never as the string `false`."""
    result = _translate_typed(dict(_TYPED_VALUES) | {"Dvt0000009a": "false"})
    assert "Dvt0000009a" not in _values(result)
    assert ConversionNoteCategory.TRUE_ONLY_FALSE_DROPPED in _note_categories(result)


def test_a_boolean_question_answered_false_writes_false() -> None:
    """A BOOLEAN data element takes both spellings, so `false` is a value rather than an absence."""
    assert _values(_translate_typed(dict(_TYPED_VALUES) | {"Dvt0000008a": "false"}))["Dvt0000008a"] == "false"


def test_a_boolean_false_is_noted_when_the_context_cannot_rule_out_true_only() -> None:
    """R4 answers BOOLEAN and TRUE_ONLY alike, so a context without value types says what it assumed."""
    result = _translate_typed(dict(_TYPED_VALUES) | {"Dvt0000008a": "false"}, with_value_types=False)
    assert ConversionNoteCategory.BOOLEAN_VALUE_TYPE_ASSUMED in _note_categories(result)


def test_a_true_only_question_reads_as_boolean_when_the_context_carries_no_value_type() -> None:
    """Without the DHIS2 value type the distinction is not in the compiled IG, so the question is BOOLEAN."""
    canonical = f"{_CANONICAL}/Questionnaire/{_TYPED_PROGRAM.uid}"
    without = _context([_TYPED_PROGRAM], with_value_types=False).forms[canonical]
    with_types = _context([_TYPED_PROGRAM]).forms[canonical]
    assert without.questions["Dvt0000009a"].wire_kind == WireValueKind.BOOLEAN
    assert with_types.questions["Dvt0000009a"].wire_kind == WireValueKind.TRUE_ONLY


def test_an_organisation_unit_answer_resolves_through_the_published_location_identifier() -> None:
    """A Location id is an identity stem, so the DHIS2 UID comes off the org-unit identifier slice."""
    assert _values(_translate_typed())["Dvt0000022a"] == _CLINIC_ORG_UNIT


def test_an_organisation_unit_answer_resolves_when_the_location_id_is_a_code_stem() -> None:
    """Under code-or-id naming the Location id is the unit's code, and the UID is still what DHIS2 imports."""
    stems = {_ROOT_ORG_UNIT: "SIERRA-LEONE", _CLINIC_ORG_UNIT: "NGELEHUN-CHC"}
    document = _rewrite_locations(_document(_typed_response(), [_TYPED_PROGRAM]), stems)
    result = translate_response(document, _context([_TYPED_PROGRAM], stems_by_uid=stems))
    assert result.refusals == ()
    assert result.event is not None
    assert result.event.orgUnit == _ROOT_ORG_UNIT
    assert _values(result)["Dvt0000022a"] == _CLINIC_ORG_UNIT


def test_an_unpublished_location_reference_refuses_rather_than_guessing_a_uid() -> None:
    """A Location the registry never published identifies no organisation unit, and guessing would import wrong."""
    document = _document(_typed_response(), [_TYPED_PROGRAM])
    result = translate_response(document, _context([_TYPED_PROGRAM], stems_by_uid={_ROOT_ORG_UNIT: _ROOT_ORG_UNIT}))
    assert ConversionRefusalCategory.UNRESOLVABLE_ORGANISATION_UNIT in _refusal_categories(result)
    assert result.event is None


def test_a_context_without_locations_reads_the_reference_as_a_uid_and_says_so() -> None:
    """Nothing to resolve through is not the same as an unresolvable reference, and the note separates them."""
    document = _document(_typed_response(), [_TYPED_PROGRAM])
    result = translate_response(document, _context([_TYPED_PROGRAM], stems_by_uid={}))
    assert result.refusals == ()
    assert ConversionNoteCategory.ORGANISATION_UNIT_ASSUMED in _note_categories(result)
    assert _values(result)["Dvt0000022a"] == _CLINIC_ORG_UNIT


def test_a_coded_answer_resolves_to_the_dhis2_option_code_in_id_mode() -> None:
    """Concept codes are option UIDs there, and the DHIS2 code rides the `dhis2-code` property."""
    assert _values(_translate_typed())["Dvt0000023a"] == "F"


def test_a_coded_answer_resolves_to_the_dhis2_option_code_in_code_mode() -> None:
    """Concept codes are option codes there, which is the very value a DHIS2 data value stores."""
    result = _translate_typed(config=_CODE_CONCEPTS)
    assert result.refusals == ()
    assert _values(result)["Dvt0000023a"] == "F"


def test_a_code_mode_concept_that_lost_its_code_to_a_peer_is_recovered_from_the_concept_map() -> None:
    """The second concept took the UID because a peer held the code, and only the map still carries it."""
    with_map = translate_response(
        _referral_document("Op7aaaaaaaa"), _context([_REFERRAL_PROGRAM], config=_CODE_CONCEPTS)
    )
    without_map = translate_response(
        _referral_document("Op7aaaaaaaa"),
        _context([_REFERRAL_PROGRAM], config=_CODE_CONCEPTS, with_concept_maps=False),
    )
    assert _values(with_map)["De8aaaaaaaa"] == "R"
    assert _values(without_map)["De8aaaaaaaa"] == "Op7aaaaaaaa"
    assert ConversionNoteCategory.OPTION_CODE_UNRECOVERABLE in _note_categories(without_map)


def test_a_lenient_run_accepts_the_option_uid_and_notes_the_spelling() -> None:
    """In code mode the concept code is the DHIS2 code, so a client sending the UID sends the other spelling."""
    result = _translate_coding(
        Coding(system=_GENDER_SYSTEM, code="Op2aaaaaaaa"), CodedAnswerMode.LENIENT, _CODE_CONCEPTS
    )
    assert _values(result)["Dvt0000023a"] == "M"
    assert ConversionNoteCategory.CODED_ANSWER_FALLBACK in _note_categories(result)


def test_a_lenient_run_accepts_the_dhis2_option_code_and_notes_the_spelling() -> None:
    """In id mode the concept code is the UID, so a client sending the DHIS2 code sends the other spelling."""
    result = _translate_coding(Coding(system=_GENDER_SYSTEM, code="M"), CodedAnswerMode.LENIENT)
    assert _values(result)["Dvt0000023a"] == "M"
    assert ConversionNoteCategory.CODED_ANSWER_FALLBACK in _note_categories(result)


def test_a_strict_run_refuses_anything_but_the_concept_code() -> None:
    """Strict is the contract read literally: the code the served CodeSystem publishes, and nothing else."""
    result = _translate_coding(Coding(system=_GENDER_SYSTEM, code="M"), CodedAnswerMode.STRICT)
    assert ConversionRefusalCategory.UNRESOLVABLE_CODING in _refusal_categories(result)
    assert result.event is None


def test_a_strict_run_accepts_the_concept_code_the_contract_asks_for() -> None:
    """The same dial that refuses the DHIS2 code accepts the concept code without a note."""
    result = _translate_coding(Coding(system=_GENDER_SYSTEM, code="Op1aaaaaaaa"), CodedAnswerMode.STRICT)
    assert _values(result)["Dvt0000023a"] == "F"
    assert ConversionNoteCategory.CODED_ANSWER_FALLBACK not in _note_categories(result)


def test_a_coding_the_terminology_does_not_hold_refuses_under_either_dial() -> None:
    """Leniency widens which spelling resolves, never which options exist."""
    result = _translate_coding(Coding(system=_GENDER_SYSTEM, code="ZZZ"), CodedAnswerMode.LENIENT)
    assert ConversionRefusalCategory.UNRESOLVABLE_CODING in _refusal_categories(result)


def test_a_coding_with_no_code_refuses() -> None:
    """A coding naming nothing selects no option, whatever system it claims."""
    result = _translate_coding(Coding(system=_GENDER_SYSTEM), CodedAnswerMode.LENIENT)
    assert ConversionRefusalCategory.MISSING_CODING in _refusal_categories(result)


def test_a_question_binding_terminology_the_context_lacks_sends_the_code_unchecked() -> None:
    """Refusing against terminology the context never carried would blame the client for a partial context."""
    document = _coded_document(Coding(system=_GENDER_SYSTEM, code="Op1aaaaaaaa"))
    context = _context([_TYPED_PROGRAM]).model_copy(update={"option_tables": {}})
    result = translate_response(document, context)
    assert _values(result)["Dvt0000023a"] == "Op1aaaaaaaa"
    assert ConversionNoteCategory.CODED_ANSWER_UNCHECKED in _note_categories(result)


def test_a_zoned_datetime_answer_is_written_as_the_wall_clock_the_project_zone_reads() -> None:
    """DHIS2 stores a zone-less local timestamp, so the offset R4 requires is exactly what comes back off."""
    result = _translate_typed(config=_ZONED)
    assert result.refusals == ()
    assert _values(result)["Dvt0000017a"] == "2026-01-05T09:30:00"
    assert result.event is not None
    assert result.event.occurredAt == datetime.datetime(2026, 1, 5, 9, 30)
    assert ConversionNoteCategory.WALL_CLOCK_DERIVED in _note_categories(result)


@pytest.mark.parametrize(
    ("carried", "zone", "wall_clock"),
    [
        ("2026-01-05T09:30:00+07:00", _ZONE, "2026-01-05T09:30:00"),
        ("2026-01-05T02:30:00Z", _ZONE, "2026-01-05T09:30:00"),
        ("2026-01-05T09:30:00Z", None, "2026-01-05T09:30:00"),
        ("2026-01-05", _ZONE, "2026-01-05"),
    ],
)
def test_a_wall_clock_reading_inverts_the_offset_the_emitter_stamped(
    carried: str, zone: str | None, wall_clock: str
) -> None:
    """`zoned_date_time` stamps the project's offset on; the reading takes the same offset back off."""
    assert wall_clock_reading(carried, zone).value == wall_clock


def test_an_unzoned_timestamp_is_taken_as_already_being_the_wall_clock_and_noted() -> None:
    """A timestamp without an offset states no instant to convert, so it is left alone rather than guessed at."""
    reading = wall_clock_reading("2026-01-05T09:30:00", _ZONE)
    assert reading.value == "2026-01-05T09:30:00"
    assert reading.unzoned


def test_an_aggregate_response_translates_into_the_data_value_set_envelope() -> None:
    """The data set, the ISO period, the organisation unit, and one data value per answered cell."""
    result = translate_response(_aggregate_document(), _context([_DATA_SET]))
    assert result.refusals == ()
    assert result.target_kind == ConversionTargetKind.DATA_VALUE_SET
    assert result.data_value_set is not None
    assert result.data_value_set.dataSet == "BfMAe6Itzgt"
    assert result.data_value_set.period == "202601"
    assert result.data_value_set.orgUnit == _ROOT_ORG_UNIT
    assert _cells(result) == {
        ("De2aaaaaaaa", "Coc1aaaaaaa"): "11",
        ("De2aaaaaaaa", "Coc2aaaaaaa"): "22",
        ("De3aaaaaaaa", None): "F",
    }


def test_a_disaggregated_cell_carries_the_category_option_combo_its_link_id_names() -> None:
    """`<dataElement>.<categoryOptionCombo>` is the only place the pair rides on the wire, both ways."""
    cells = _cells(translate_response(_aggregate_document(), _context([_DATA_SET])))
    assert ("De2aaaaaaaa", "Coc1aaaaaaa") in cells
    assert ("De2aaaaaaaa", None) not in cells


def test_an_aggregate_response_missing_its_period_extension_refuses() -> None:
    """A data value set imports against a period, so a response with none has nothing to report for."""
    document = _with_extension(_aggregate_document(), _NAMING.period_url, None)
    result = translate_response(document, _context([_DATA_SET]))
    assert ConversionRefusalCategory.MISSING_PERIOD in _refusal_categories(result)
    assert result.data_value_set is None


def test_a_malformed_iso_period_refuses_rather_than_importing_against_nothing() -> None:
    """The ISO identifier is what DHIS2 imports against, so it is parsed rather than trusted."""
    document = _with_extension(
        _aggregate_document(), _NAMING.period_url, _period_extension("20260", "2026-01-01", "2026-01-31")
    )
    result = translate_response(document, _context([_DATA_SET]))
    assert ConversionRefusalCategory.MALFORMED_PERIOD in _refusal_categories(result)


def test_a_period_range_disagreeing_with_its_iso_period_is_noted_and_the_iso_period_wins() -> None:
    """The range is derived data; the ISO identifier is the fact DHIS2 stores against."""
    document = _with_extension(
        _aggregate_document(), _NAMING.period_url, _period_extension("202601", "2026-01-01", "2026-01-30")
    )
    result = translate_response(document, _context([_DATA_SET]))
    assert result.data_value_set is not None
    assert result.data_value_set.period == "202601"
    assert ConversionNoteCategory.PERIOD_RANGE_IGNORED in _note_categories(result)


def test_an_aggregate_response_takes_its_complete_date_from_the_authored_instant() -> None:
    """A data value set is reported complete for a period, and `authored` is when that happened."""
    response = _aggregate_response().model_copy(update={"authored": "2026-02-03T08:00:00"})
    result = translate_response(_document(response, [_DATA_SET]), _context([_DATA_SET]))
    assert result.data_value_set is not None
    assert result.data_value_set.completeDate == "2026-02-03"
    assert ConversionNoteCategory.COMPLETE_DATE_DERIVED in _note_categories(result)


def test_a_group_item_answering_nothing_is_skipped_rather_than_refused() -> None:
    """A section group and a disaggregated data element are structure, and structure stores no data value."""
    result = translate_response(_aggregate_document(), _context([_DATA_SET]))
    assert result.refusals == ()
    assert len(_cells(result)) == 3


def test_the_context_reads_the_link_id_grammar_off_the_questionnaire() -> None:
    """A plain question is a data element; a cell is the pair, split on the separator the emitter joins with."""
    form = _context([_DATA_SET]).forms[f"{_CANONICAL}/Questionnaire/{_DATA_SET.uid}"]
    assert form.questions["De2aaaaaaaa.Coc1aaaaaaa"].data_element_uid == "De2aaaaaaaa"
    assert form.questions["De2aaaaaaaa.Coc1aaaaaaa"].category_option_combo_uid == "Coc1aaaaaaa"
    assert form.questions["De3aaaaaaaa"].category_option_combo_uid is None
    assert "Sec1aaaaaaa" in form.group_link_ids
    assert "De2aaaaaaaa" in form.group_link_ids


def test_a_tracker_event_response_carries_its_tracked_entity_and_enrollment() -> None:
    """The subject identifier names the tracked entity; the enrollment extension names the enrollment."""
    result = translate_response(_tracker_document(), _context([_BIRTH_STAGE]))
    assert result.refusals == ()
    assert result.target_kind == ConversionTargetKind.TRACKER_EVENT
    assert result.event is not None
    assert result.event.program == "IpHINAT79UW"
    assert result.event.programStage == "A03MvHHogjR"
    assert result.event.orgUnit == _ROOT_ORG_UNIT
    assert result.event.trackedEntity == _TRACKED_ENTITY
    assert result.event.enrollment == _ENROLLMENT
    assert _values(result) == {"a3kGcGDCuk6": "9"}


def test_a_tracker_event_response_naming_no_tracked_entity_refuses() -> None:
    """A tracker event belongs to one person, and importing it against none would attach it to nobody."""
    result = translate_response(_tracker_document().model_copy(update={"subject": None}), _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.MISSING_SUBJECT in _refusal_categories(result)
    assert result.event is None


def test_a_tracker_event_response_naming_no_enrollment_refuses() -> None:
    """The enrollment is the event's place in the program, and DHIS2 has nowhere to put it without one."""
    document = _with_extension(_tracker_document(), _NAMING.tracker_enrollment_url, None)
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.MISSING_ENROLLMENT in _refusal_categories(result)


def test_a_tracker_event_subject_reference_is_noted_and_not_read() -> None:
    """The tracked-entity identifier is the contract; a reference beside it names a resource DHIS2 has no id for."""
    original = _tracker_document()
    assert original.subject is not None
    document = original.model_copy(
        update={"subject": original.subject.model_copy(update={"reference": "Patient/whatever"})}
    )
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert result.event is not None
    assert result.event.trackedEntity == _TRACKED_ENTITY
    assert ConversionNoteCategory.SUBJECT_REFERENCE_IGNORED in _note_categories(result)


@pytest.mark.parametrize(
    ("status", "event_status", "collapsed"),
    [
        ("completed", "COMPLETED", True),
        ("in-progress", "ACTIVE", False),
        ("stopped", "SKIPPED", False),
        ("amended", "COMPLETED", True),
    ],
)
def test_the_status_inverse_writes_the_dhis2_event_status_and_names_the_collapse(
    status: str, event_status: str, collapsed: bool
) -> None:
    """`COMPLETED`, `SCHEDULE`, `OVERDUE`, and `VISITED` all read forward as `completed`, and the inverse says so."""
    document = _tracker_document().model_copy(update={"status": status})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert result.event is not None
    assert result.event.status is not None
    assert result.event.status.value == event_status
    assert (ConversionNoteCategory.STATUS_COLLAPSED in _note_categories(result)) is collapsed


def test_an_entered_in_error_response_refuses_because_retraction_is_not_an_import() -> None:
    """R4 has a lifecycle state for a mistaken response; DHIS2 has a deletion, which is a different call."""
    document = _tracker_document().model_copy(update={"status": "entered-in-error"})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.UNMAPPABLE_STATUS in _refusal_categories(result)


def test_an_event_response_recording_no_occurrence_refuses() -> None:
    """`authored` is the only statement of when the event happened, and DHIS2 requires one."""
    document = _tracker_document().model_copy(update={"authored": None})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.MISSING_OCCURRENCE in _refusal_categories(result)


def test_a_response_answering_a_link_id_the_form_does_not_ask_refuses() -> None:
    """An unknown link id names no data element, so the value has nowhere to go and no default to take."""
    original = _tracker_document()
    unknown = QuestionnaireResponseItem(linkId="Unknown0001", answer=[QuestionnaireResponseAnswer(valueInteger=1)])
    document = original.model_copy(update={"item": [*(original.item or []), unknown]})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.UNKNOWN_LINK_ID in _refusal_categories(result)
    assert result.event is None


def test_an_answer_on_the_wrong_value_element_refuses() -> None:
    """The Questionnaire says which `value[x]` a question answers on; anything else is not that question's answer."""
    document = _with_answers(_tracker_document(), "a3kGcGDCuk6", [QuestionnaireResponseAnswer(valueString="nine")])
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.ANSWER_ELEMENT_MISMATCH in _refusal_categories(result)


def test_an_item_carrying_no_answer_refuses() -> None:
    """An answered item with nothing on it states no value, which is not the same as leaving the question out."""
    result = translate_response(_with_answers(_tracker_document(), "a3kGcGDCuk6", None), _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.MISSING_ANSWER_VALUE in _refusal_categories(result)


def test_a_non_repeating_question_answered_twice_refuses() -> None:
    """One DHIS2 data value per question, so two answers leave the translator choosing, which it will not do."""
    document = _with_answers(
        _tracker_document(),
        "a3kGcGDCuk6",
        [QuestionnaireResponseAnswer(valueInteger=9), QuestionnaireResponseAnswer(valueInteger=8)],
    )
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert ConversionRefusalCategory.REPEATED_ANSWER in _refusal_categories(result)


def test_a_response_declaring_no_form_type_refuses() -> None:
    """The form kind decides which payload the response becomes, so there is nothing to translate without it."""
    document = _tracker_document().model_copy(update={"extension": None})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert _refusal_categories(result) == {ConversionRefusalCategory.NO_FORM_TYPE}


def test_a_response_answering_a_form_the_context_does_not_carry_refuses() -> None:
    """A canonical the context holds no Questionnaire for is a refusal rather than a guess at the grammar."""
    document = _tracker_document().model_copy(update={"questionnaire": f"{_CANONICAL}/Questionnaire/nothing"})
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert _refusal_categories(result) == {ConversionRefusalCategory.UNKNOWN_FORM}


def test_a_response_declaring_the_wrong_form_kind_refuses() -> None:
    """A tracker-event form answered as an aggregate response would translate into the wrong payload entirely."""
    document = _with_extension(
        _tracker_document(), _NAMING.form_type_url, Extension(url=_NAMING.form_type_url, valueCode="aggregate")
    )
    result = translate_response(document, _context([_BIRTH_STAGE]))
    assert _refusal_categories(result) == {ConversionRefusalCategory.FORM_KIND_MISMATCH}


def test_a_form_carrying_no_dhis2_identifier_refuses_rather_than_reading_its_canonical() -> None:
    """A questionnaire canonical ends in an identity stem, which under code naming is not a DHIS2 UID."""
    context = _context([_BIRTH_STAGE])
    canonical = f"{_CANONICAL}/Questionnaire/{_BIRTH_STAGE.uid}"
    stripped = context.forms[canonical].model_copy(update={"program_stage_uid": None})
    result = translate_response(_tracker_document(), context.model_copy(update={"forms": {canonical: stripped}}))
    assert ConversionRefusalCategory.MISSING_TARGET_IDENTIFIER in _refusal_categories(result)


def test_an_attachment_answer_refuses_because_dhis2_uploads_it_separately() -> None:
    """A FILE_RESOURCE value is an upload with a UID of its own, not something a data value can carry."""
    document = _document(_tracker_response(), [_BIRTH_STAGE]).model_copy(
        update={
            "questionnaire": f"{_CANONICAL}/Questionnaire/{_ATTACHMENT_PROGRAM.uid}",
            "subject": Reference(reference=f"Location/{_ROOT_ORG_UNIT}"),
            "extension": [Extension(url=_NAMING.form_type_url, valueCode="event")],
            "item": [
                QuestionnaireResponseItem(
                    linkId="De9aaaaaaaa", answer=[QuestionnaireResponseAnswer(valueAttachment=_ATTACHMENT)]
                )
            ],
        }
    )
    result = translate_response(document, _context([_ATTACHMENT_PROGRAM]))
    assert ConversionRefusalCategory.UNSUPPORTED_ANSWER_VALUE in _refusal_categories(result)


def test_a_batch_report_keeps_one_result_per_response_and_routes_the_refusals() -> None:
    """A refusal never stops the responses behind it: the report carries both halves in drain order."""
    good = _tracker_document()
    bad = good.model_copy(update={"questionnaire": f"{_CANONICAL}/Questionnaire/nothing"})
    report = translate_responses([good, bad], _context([_BIRTH_STAGE]))
    assert len(report.results) == 2
    assert len(report.translated) == 1
    assert len(report.refused) == 1
    assert len(report.events) == 1
    assert report.data_value_sets == ()

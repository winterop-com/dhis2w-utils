"""Unit tests for FHIR-safety validation: instance-wide sweep, deep option/attribute passes, reports."""

import re
from datetime import UTC, datetime

import pytest
from dhis2w_fhir.config import GenerateConfig, HostileNamePosture, NamingConfig
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation import build_code_validation, render_validation_markdown
from dhis2w_fhir.validation.pdf import render_validation_pdf
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationFinding,
    ValidationScope,
)

_CONFIG = GenerateConfig()
_CODE_MODE = GenerateConfig(concept_code_source="code")
_GENERATED_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _set(uid: str, name: str, options: list[OptionIn]) -> OptionSetIn:
    """Build an option set source."""
    return OptionSetIn(uid=uid, name=name, options=options)


def _validate(
    option_sets: list[OptionSetIn], collections: list[MetadataCollectionIn] | None = None
) -> FhirValidationReport:
    """Run validation in code mode - the severities the option findings carry when they bite."""
    return build_code_validation(option_sets, collections or [], _CODE_MODE)


def test_clean_instance_has_no_findings() -> None:
    """Valid unique codes yield an empty findings list and exact counts."""
    report = _validate(
        [_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code="M", name="Male")])],
        [MetadataCollectionIn(resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", code="DE1")])],
    )
    assert report.findings == []
    assert report.option_set_count == 1
    assert report.option_count == 1
    assert report.resource_type_count == 1
    assert report.object_count == 1


def test_sweep_flags_invalid_and_duplicate_codes() -> None:
    """The instance-wide sweep flags invalid and duplicated codes as warnings - neither aborts a build."""
    collection = MetadataCollectionIn(
        resource="dataElements",
        items=[
            MetadataItemIn(uid="De1aaaaaaaa", name="Bad", code=" X "),
            MetadataItemIn(uid="De2aaaaaaaa", name="One", code="DUP"),
            MetadataItemIn(uid="De3aaaaaaaa", name="Two", code="DUP"),
            MetadataItemIn(uid="De4aaaaaaaa", name="NoCode"),
        ],
    )
    report = _validate([], [collection])
    categories = [(finding.severity, finding.category) for finding in report.findings]
    assert categories == [("warning", "invalid-code"), ("warning", "duplicate-code"), ("warning", "duplicate-code")]
    assert all(finding.resource_type == "dataElements" for finding in report.findings)


def test_option_invalid_code_is_a_warning() -> None:
    """Edge whitespace makes an option code invalid, so code-source generation falls back to the UID."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])])
    assert [finding.category for finding in report.findings] == ["invalid-code"]
    assert report.findings[0].resource_type == "options"
    assert "[in Sex]" in report.findings[0].name
    assert report.warning_count == 1
    assert report.error_count == 0


def test_invalid_code_findings_name_the_defect() -> None:
    """The invalid-code message says which defect the code carries, on both passes."""
    report = _validate(
        [_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])],
        [
            MetadataCollectionIn(
                resource="categoryOptions", items=[MetadataItemIn(uid="Co1aaaaaaaa", name="Blue", code="BLUE\nBLUE")]
            )
        ],
    )
    messages = {finding.resource_type: finding.message for finding in report.findings}
    assert messages["categoryOptions"] == "code is not a valid FHIR code: code contains a line break"
    assert messages["options"] == (
        "code is not a valid FHIR code: code has leading whitespace; code-source generation falls back to the UID"
    )


def test_option_missing_code_is_a_warning() -> None:
    """An option without a code warns about the UID fallback."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", name="Male")])])
    assert [finding.category for finding in report.findings] == ["missing-code"]
    assert report.warning_count == 1


def test_option_duplicate_codes_are_warnings() -> None:
    """The same code on two options in one set breaks CodeSystem uniqueness, degrading the emitted pair."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", code="X", name="One"),
        OptionIn(uid="Op2aaaaaaaa", code="X", name="Two"),
    ]
    report = _validate([_set("Aa1aaaaaaaa", "Dup", options)])
    assert [finding.category for finding in report.findings] == ["duplicate-code", "duplicate-code"]
    assert report.warning_count == 2
    assert report.error_count == 0


def test_spaced_code_is_info() -> None:
    """A FHIR-valid code containing spaces is flagged info (quoted #\"...\" form needed)."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code="two words", name="S")])])
    assert [finding.category for finding in report.findings] == ["spaced-code"]
    assert report.info_count == 1


def test_uid_mode_downgrades_the_code_findings() -> None:
    """In id mode the option code findings are informational - generation is not reading codes yet."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad"),
        OptionIn(uid="Op2aaaaaaaa", name="NoCode"),
        OptionIn(uid="Op3aaaaaaaa", code="X", name="One"),
        OptionIn(uid="Op4aaaaaaaa", code="X", name="Two"),
    ]
    report = build_code_validation([_set("Aa1aaaaaaaa", "Sex", options)], [], _CONFIG)
    assert {finding.severity for finding in report.findings} == {"info"}
    assert sorted(finding.category for finding in report.findings) == [
        "duplicate-code",
        "duplicate-code",
        "invalid-code",
        "missing-code",
    ]
    assert report.error_count == 0
    assert report.warning_count == 0
    assert all(finding.message.endswith("switching to code mode)") for finding in report.findings)


def test_code_mode_keeps_the_code_findings_biting() -> None:
    """In code mode the same option findings keep their warning severities."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad"),
        OptionIn(uid="Op2aaaaaaaa", name="NoCode"),
    ]
    report = build_code_validation([_set("Aa1aaaaaaaa", "Sex", options)], [], _CODE_MODE)
    assert report.warning_count == 2
    assert report.error_count == 0
    assert not any("switching to code mode" in finding.message for finding in report.findings)


def test_code_source_override_wins_over_the_config() -> None:
    """The explicit code_source argument overrides `concept_code_source` in both directions."""
    sets = [_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad")])]
    assert build_code_validation(sets, [], _CONFIG, "code").warning_count == 1
    assert build_code_validation(sets, [], _CODE_MODE, "id").warning_count == 0
    assert build_code_validation(sets, [], _CODE_MODE, "id").info_count == 1


def test_sweep_severities_ignore_the_code_source() -> None:
    """The instance-wide sweep keeps its severities in id mode - only the option pass is gated."""
    collection = MetadataCollectionIn(
        resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", name="Bad", code=" X ")]
    )
    assert build_code_validation([], [collection], _CONFIG).warning_count == 1
    assert build_code_validation([], [collection], _CODE_MODE).warning_count == 1


def test_organisation_units_without_a_code_warn() -> None:
    """Every organisation unit should carry both identifiers, so a missing code is a finding there only."""
    report = build_code_validation(
        [],
        [
            MetadataCollectionIn(
                resource="organisationUnits",
                items=[
                    MetadataItemIn(uid="Ou1aaaaaaaa", name="Coded", code="SL"),
                    MetadataItemIn(uid="Ou2aaaaaaaa", name="Uncoded"),
                ],
            ),
            MetadataCollectionIn(resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", name="NoCode")]),
        ],
        _CONFIG,
    )
    assert [(finding.severity, finding.category, finding.uid) for finding in report.findings] == [
        ("warning", "missing-code", "Ou2aaaaaaaa")
    ]
    assert "falls back to the UID" in report.findings[0].message


#: The naming configs whose identity stems come from DHIS2 codes - what the code-stem pass grades.
_CODE_OR_ID_STEMS = GenerateConfig(naming=NamingConfig(source="code-or-id"))
_CODE_STEMS = GenerateConfig(naming=NamingConfig(source="code"))


def _attributes(*items: MetadataItemIn) -> MetadataCollectionIn:
    """Build the sweep's `attributes` collection - the only source the deep attribute pass reads."""
    return MetadataCollectionIn(resource="attributes", items=list(items))


def test_an_uncoded_attribute_is_informational_and_names_every_context() -> None:
    """An uncoded attribute emits a D2AttributeValue without its code on all five contexted types."""
    report = build_code_validation(
        [],
        [
            _attributes(
                MetadataItemIn(uid="AtrFhirOpS1", name="FHIR code system URI", code="FHIR_CODE_SYSTEM_URI"),
                MetadataItemIn(uid="AtrFhirDsQ1", name="FHIR questionnaire source form"),
            )
        ],
        _CONFIG,
    )
    assert [(finding.severity, finding.category, finding.uid) for finding in report.findings] == [
        ("info", "missing-code", "AtrFhirDsQ1")
    ]
    assert report.findings[0].resource_type == "attributes"
    assert "attributeCode sub-extension" in report.findings[0].message
    for resource_type in ("Organization", "Location", "CodeSystem", "ValueSet", "Questionnaire"):
        assert resource_type in report.findings[0].message


def test_the_attribute_pass_reads_the_sweep_and_nothing_else() -> None:
    """The pass needs no request of its own, so an instance whose sweep holds no attributes finds none."""
    report = build_code_validation(
        [],
        [MetadataCollectionIn(resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", name="Uncoded")])],
        _CONFIG,
    )
    assert report.findings == []
    assert report.attribute_count == 0


def test_the_report_counts_the_attributes_the_deep_pass_visited() -> None:
    """The report states its deep coverage, so a partial check cannot read as a full one."""
    report = build_code_validation(
        [],
        [_attributes(MetadataItemIn(uid="At1aaaaaaaa", name="One", code="ONE"), MetadataItemIn(uid="At2aaaaaaaa"))],
        _CONFIG,
    )
    assert report.attribute_count == 2
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert "- attributes (deep pass): 2" in markdown


@pytest.mark.parametrize("code_source", ["id", "code"])
def test_the_attribute_finding_is_independent_of_the_code_source(code_source: str) -> None:
    """The attribute code rides in a valueString, not a concept code, so the code source never gates it."""
    report = build_code_validation(
        [],
        [_attributes(MetadataItemIn(uid="At1aaaaaaaa", name="Uncoded"))],
        _CONFIG,
        code_source,  # type: ignore[arg-type]
    )
    assert [finding.severity for finding in report.findings] == ["info"]
    assert "informational in id mode" not in report.findings[0].message


#: A naming surface whose codes exercise every stem defect: missing, unusable, colliding, and clean.
_STEM_COLLECTION = MetadataCollectionIn(
    resource="optionSets",
    items=[
        MetadataItemIn(uid="Os1aaaaaaaa", name="Uncoded"),
        MetadataItemIn(uid="Os2aaaaaaaa", name="Spaced", code="bad code"),
        MetadataItemIn(uid="Os3aaaaaaaa", name="Twin one", code="twin"),
        MetadataItemIn(uid="Os4aaaaaaaa", name="Twin two", code="twin"),
        MetadataItemIn(uid="Os5aaaaaaaa", name="Clean", code="clean"),
    ],
)


def test_code_or_id_grades_stem_defects_as_fallback_warnings() -> None:
    """Missing, unusable, and colliding codes are the objects code-or-id silently falls back on."""
    report = build_code_validation([], [_STEM_COLLECTION], _CODE_OR_ID_STEMS)
    stems = [finding for finding in report.findings if finding.category == "code-stem-fallback"]
    assert [(finding.severity, finding.scope, finding.uid) for finding in stems] == [
        ("warning", "selection", "Os2aaaaaaaa"),
        ("warning", "selection", "Os3aaaaaaaa"),
        ("warning", "selection", "Os4aaaaaaaa"),
        ("warning", "selection", "Os1aaaaaaaa"),
    ]
    assert "is not a valid FHIR id" in stems[0].message
    assert "is shared by 2 selected option sets" in stems[1].message
    assert "has no code" in stems[3].message
    assert all("falls back to the id" in finding.message for finding in stems)


def test_code_source_grades_stem_defects_as_errors() -> None:
    """What generate refuses under `source = "code"` is exactly what validate grades error."""
    report = build_code_validation([], [_STEM_COLLECTION], _CODE_STEMS)
    stems = [finding for finding in report.findings if finding.category == "code-stem-refusal"]
    assert [(finding.severity, finding.uid) for finding in stems] == [
        ("error", "Os2aaaaaaaa"),
        ("error", "Os3aaaaaaaa"),
        ("error", "Os4aaaaaaaa"),
        ("error", "Os1aaaaaaaa"),
    ]
    assert all("refuses the run" in finding.message for finding in stems)
    assert report.error_count == 4


def test_stem_defects_are_silent_in_id_mode() -> None:
    """Id-sourced stems are the UID verbatim, so no code can degrade or refuse the run."""
    report = build_code_validation([], [_STEM_COLLECTION], _CONFIG)
    assert [finding for finding in report.findings if finding.category.startswith("code-stem")] == []


def test_a_collection_that_is_no_naming_surface_raises_no_stem_finding() -> None:
    """A data element is a concept inside the support terminology, so its code is never a stem."""
    collection = MetadataCollectionIn(
        resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", name="Uncoded")]
    )
    assert build_code_validation([], [collection], _CODE_STEMS).findings == []


def test_a_data_set_code_collides_with_an_event_program_code_across_collections() -> None:
    """Data sets, event programs, and stages all become Questionnaire-<stem>, one id namespace."""
    collections = [
        MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name="ANC", code="ANC")]),
        MetadataCollectionIn(resource="programs", items=[MetadataItemIn(uid="Pr1aaaaaaaa", name="ANC", code="ANC")]),
    ]
    report = build_code_validation([], collections, _CODE_OR_ID_STEMS)
    stems = [finding for finding in report.findings if finding.category == "code-stem-fallback"]
    assert [(finding.resource_type, finding.uid) for finding in stems] == [
        ("dataSets", "Ds1aaaaaaaa"),
        ("programs", "Pr1aaaaaaaa"),
    ]
    assert all("is shared by 2 selected questionnaire targets" in finding.message for finding in stems)


def test_a_tracker_program_code_never_collides_with_a_data_set_code() -> None:
    """A tracker program's stem names a stage directory, not a Questionnaire - its own namespace."""
    collections = [
        MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name="ANC", code="ANC")]),
        MetadataCollectionIn(resource="programs", items=[MetadataItemIn(uid="Pr1aaaaaaaa", name="ANC", code="ANC")]),
    ]
    scope = ValidationScope(
        data_sets=frozenset({"Ds1aaaaaaaa"}),
        programs=frozenset({"Pr1aaaaaaaa"}),
        tracker_programs=frozenset({"Pr1aaaaaaaa"}),
    )
    report = build_code_validation([], collections, _CODE_OR_ID_STEMS, scope=scope)
    assert [finding for finding in report.findings if finding.category == "code-stem-fallback"] == []


def test_validate_error_parity_with_the_generate_refusal() -> None:
    """The same fixture a validate error names is the one `d2w fhir generate` refuses to emit."""
    from dhis2w_fhir.attributes import AttributeCodeIndex
    from dhis2w_fhir.names import CodeStemError
    from dhis2w_fhir.resources.option_sets import build_option_set_artifacts

    uncoded = _set("Os1aaaaaaaa", "Uncoded", [])
    sweep = MetadataCollectionIn(resource="optionSets", items=[MetadataItemIn(uid="Os1aaaaaaaa", name="Uncoded")])
    report = build_code_validation([], [sweep], _CODE_STEMS)
    assert [(finding.severity, finding.uid) for finding in report.findings] == [("error", "Os1aaaaaaaa")]
    with pytest.raises(CodeStemError, match="Uncoded \\(Os1aaaaaaaa\\) has no code"):
        build_option_set_artifacts(
            [uncoded], _CODE_STEMS, "http://example.org/fhir", ig_status="draft", attribute_codes=AttributeCodeIndex()
        )


def test_findings_sorted_errors_first() -> None:
    """Errors sort before warnings and infos."""
    report = _validate(
        [_set("Aa1aaaaaaaa", "Zulu", [OptionIn(uid="Op1aaaaaaaa", name="NoCode")])],
        [
            MetadataCollectionIn(
                resource="optionSets", items=[MetadataItemIn(uid="Os1aaaaaaaa", name="Hostile", code="A<B")]
            )
        ],
    )
    assert [finding.severity for finding in report.findings] == ["error", "warning"]


def test_report_json_carries_counts() -> None:
    """The computed severity counts land in the serialized report, the selection split beside them."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])])
    dumped = report.model_dump()
    assert dumped["warning_count"] == 1
    assert dumped["error_count"] == 0
    assert dumped["selection_warning_count"] == 1
    assert dumped["selection_error_count"] == 0


def test_markdown_report_groups_by_type() -> None:
    """The markdown report groups findings under per-resource-type sections."""
    report = _validate(
        [_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])],
        [MetadataCollectionIn(resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", code=" X ")])],
    )
    markdown = render_validation_markdown(report, "probe (https://dhis2.example)", _GENERATED_AT)
    assert "# FHIR-safety validation report" in markdown
    assert "Target: probe (https://dhis2.example)" in markdown
    assert "## dataElements" in markdown
    assert "## options" in markdown
    assert "| warning | selection | invalid-code |" in markdown


def test_markdown_report_clean() -> None:
    """A clean report says so instead of rendering empty tables."""
    markdown = render_validation_markdown(_validate([]), "probe", _GENERATED_AT)
    assert "No findings" in markdown


#: The play 2.42 data set whose name aborts the IG publisher's HTML parse.
_MORTALITY_NAME = "Mortality < 5 years by gender"


def _hostile(report: FhirValidationReport) -> list[ValidationFinding]:
    """The template-hostile-name findings of one report, in report order."""
    return [finding for finding in report.findings if finding.category == "template-hostile-name"]


def test_a_template_hostile_name_is_one_error_naming_the_character_and_the_consequence() -> None:
    """The real play 2.42 data set name yields exactly one error saying the build fails, and why."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="dataSets",
                items=[MetadataItemIn(uid="YFTk3VdO9av", name=_MORTALITY_NAME, code="DS_MORT")],
            )
        ],
    )
    findings = _hostile(report)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].resource_type == "dataSets"
    assert findings[0].uid == "YFTk3VdO9av"
    assert findings[0].name == _MORTALITY_NAME
    assert findings[0].message == (
        f"name {_MORTALITY_NAME} contains '<' which the IG publisher template injects into HTML "
        "unescaped, so `make build` fails: the publisher strict-parses the page it just wrote and "
        "cannot read it back; change the name in DHIS2"
    )


def test_a_name_carrying_only_the_survivable_characters_stays_a_warning() -> None:
    """'>' and '&' cost a malformed page and the build lives, so they are graded below an aborted one."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="dataSets",
                items=[MetadataItemIn(uid="YFTk3VdO9aw", name="Mortality > 5 years & over", code="DS_OVER")],
            )
        ],
    )
    findings = _hostile(report)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "render malformed" in findings[0].message


def test_a_clean_name_raises_no_template_finding() -> None:
    """A name with no HTML-significant character is not a finding at all."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="dataSets",
                items=[MetadataItemIn(uid="BfMAe6Itzgt", name="Child Health", code="DS_CH")],
            )
        ],
    )
    assert _hostile(report) == []


@pytest.mark.parametrize(
    ("name", "character"),
    [
        (_MORTALITY_NAME, "<"),
        ("A > B comparison", ">"),
        ("Cases & deaths", "&"),
        ("<b>bold</b>", "<"),
        ("Under 5 &amp; over", "&"),
    ],
)
def test_every_html_significant_character_is_flagged(name: str, character: str) -> None:
    """All three of `<`, `>`, and `&` break the template, and the message names the one it found first."""
    report = _validate(
        [], [MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name=name)])]
    )
    findings = _hostile(report)
    assert len(findings) == 1
    assert f"contains {character!r}" in findings[0].message


def test_option_names_are_checked_by_the_deep_pass() -> None:
    """Options are excluded from the sweep, so the deep pass covers the names that land in page tables."""
    report = _validate(
        [
            _set(
                "Os1aaaaaaaa",
                "Age band",
                [
                    OptionIn(uid="Op1aaaaaaaa", code="LT5", name="< 5 years"),
                    OptionIn(uid="Op2aaaaaaaa", code="GE5", name="5 years and over"),
                ],
            )
        ]
    )
    findings = _hostile(report)
    assert len(findings) == 1
    assert findings[0].resource_type == "options"
    assert findings[0].uid == "Op1aaaaaaaa"
    assert findings[0].name == "< 5 years [in Age band]"
    assert "contains '<'" in findings[0].message


def test_an_option_set_name_is_flagged_once_by_the_sweep_alone() -> None:
    """The sweep already covers optionSets, so the deep pass must not report the same set a second time."""
    report = build_code_validation(
        [_set("Os1aaaaaaaa", _MORTALITY_NAME, [OptionIn(uid="Op1aaaaaaaa", code="M", name="Male")])],
        [MetadataCollectionIn(resource="optionSets", items=[MetadataItemIn(uid="Os1aaaaaaaa", name=_MORTALITY_NAME)])],
        _CONFIG,
    )
    findings = _hostile(report)
    assert len(findings) == 1
    assert findings[0].resource_type == "optionSets"


@pytest.mark.parametrize("code_source", ["id", "code"])
def test_the_template_finding_is_independent_of_the_code_source(code_source: str) -> None:
    """The finding is about published pages, not about codes, so id mode does not downgrade it."""
    report = build_code_validation(
        [_set("Os1aaaaaaaa", "Age band", [OptionIn(uid="Op1aaaaaaaa", code="LT5", name="< 5 years")])],
        [MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name=_MORTALITY_NAME)])],
        _CONFIG,
        code_source,  # type: ignore[arg-type]
    )
    findings = _hostile(report)
    # An option name and a data set name, both carrying '<': one grade for one sentence, whichever
    # surface the name sits on, because the publisher writes both into the same unescaped HTML.
    assert [finding.severity for finding in findings] == ["error", "error"]
    assert not any("informational in id mode" in finding.message for finding in findings)


def test_an_invisible_character_in_a_name_is_rendered_visibly() -> None:
    """The message reuses the code renderer, so a line break in a name prints as an escape."""
    report = _validate(
        [],
        [MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name="A <b>\nB")])],
    )
    assert "name A <b>\\nB contains" in _hostile(report)[0].message


#: A DHIS2 name carrying both characters a Markdown table cannot take raw: a pipe and a line break.
_HOSTILE_CELL_NAME = "A|B\nC"


def test_a_markdown_row_survives_a_pipe_and_a_line_break_in_the_message() -> None:
    """The detail column quotes the DHIS2 name back, so it takes the same cell escaping the name column does."""
    finding = ValidationFinding(
        severity="warning",
        category="template-hostile-name",
        resource_type="dataElements",
        uid="De1aaaaaaaa",
        name=_HOSTILE_CELL_NAME,
        message=f"name {_HOSTILE_CELL_NAME} contains '<' which the IG publisher template injects unescaped",
    )
    markdown = render_validation_markdown(FhirValidationReport(findings=[finding]), "probe", _GENERATED_AT)

    rows = [line for line in markdown.splitlines() if line.startswith("| warning |")]
    assert len(rows) == 1
    assert len(re.split(r"(?<!\\)\|", rows[0])) == 8
    assert rows[0].count("A\\|B C") == 2
    assert "\n" not in rows[0]


def test_a_markdown_row_escapes_the_uid_beside_the_name() -> None:
    """Both halves of the object column are DHIS2 text, so both are made table-safe."""
    finding = ValidationFinding(
        severity="error",
        category="invalid-code",
        resource_type="dataElements",
        uid="De1|aaaaaaa",
        name="Plain",
        message="code is not a valid FHIR code",
    )
    markdown = render_validation_markdown(FhirValidationReport(findings=[finding]), "probe", _GENERATED_AT)

    row = next(line for line in markdown.splitlines() if line.startswith("| error |"))
    assert "Plain (De1\\|aaaaaaa)" in row
    assert len(re.split(r"(?<!\\)\|", row)) == 8


#: The option-set code that aborts the publisher on a real national instance.
_HOSTILE_CODE = "ENTO - IRS < 6 Months"


def _hostile_code(report: FhirValidationReport) -> list[ValidationFinding]:
    """The template-hostile-code findings of one report, in report order."""
    return [finding for finding in report.findings if finding.category == "template-hostile-code"]


def test_a_template_hostile_code_is_an_error_because_it_aborts_the_build() -> None:
    """A code carrying `<` rides an identifier value the publisher writes raw, which kills the build."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="optionSets",
                items=[MetadataItemIn(uid="csRsm0D7guY", name="MAL ENTO: IRS 6 Months", code=_HOSTILE_CODE)],
            )
        ],
    )
    findings = _hostile_code(report)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].resource_type == "optionSets"
    assert findings[0].uid == "csRsm0D7guY"
    assert findings[0].code == _HOSTILE_CODE
    assert "identifier value" in findings[0].message
    # A clean name means the cosmetic sibling stays silent - the two findings are independent.
    assert _hostile(report) == []


def test_a_hostile_code_on_a_collection_that_emits_no_identifier_is_not_a_finding() -> None:
    """A dashboard is never generated, so its code reaches no page and costs nothing."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="dashboards",
                items=[MetadataItemIn(uid="upvQqwKmR0P", name="Dashboard", code="CHAS S&E HIV")],
            ),
            MetadataCollectionIn(
                resource="dataElements",
                items=[MetadataItemIn(uid="imGvvLi8joq", name="Element", code="SC_BR_Outbreaks<R_Q3")],
            ),
        ],
    )
    assert _hostile_code(report) == []


def test_an_unconfirmed_hostile_character_in_a_code_is_a_warning_not_an_error() -> None:
    """Only `<` has been seen to abort a build, so `&` and `>` do not claim to."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="organisationUnits",
                items=[
                    MetadataItemIn(uid="Aa1aaaaaaaa", name="Facility", code="A&E"),
                    MetadataItemIn(uid="Bb2bbbbbbbb", name="Ward", code="OVER>5"),
                ],
            )
        ],
    )
    assert [finding.severity for finding in _hostile_code(report)] == ["warning", "warning"]


def test_a_clean_code_and_an_absent_code_raise_no_template_finding() -> None:
    """The check reads a code when there is one and is silent otherwise."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="optionSets",
                items=[
                    MetadataItemIn(uid="Aa1aaaaaaaa", name="Sex", code="SEX"),
                    MetadataItemIn(uid="Bb2bbbbbbbb", name="Age", code=None),
                ],
            )
        ],
    )
    assert _hostile_code(report) == []


def test_a_hostile_name_and_a_hostile_code_on_one_object_are_two_findings() -> None:
    """Two surfaces the publisher writes unescaped, two fixes in DHIS2, so neither absorbs the other."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource="optionSets",
                items=[MetadataItemIn(uid="csRsm0D7guY", name=_MORTALITY_NAME, code=_HOSTILE_CODE)],
            )
        ],
    )
    assert [finding.severity for finding in _hostile(report)] == ["error"]
    assert [finding.severity for finding in _hostile_code(report)] == ["error"]


@pytest.mark.parametrize("resource_type_count", [1, 29, 30, 31, 45, 60, 61])
def test_the_pdf_renders_at_every_contents_page_boundary(resource_type_count: int) -> None:
    """The contents placeholder reserves whole pages, and the render has to fill exactly what it reserved."""
    report = _validate(
        [],
        [
            MetadataCollectionIn(
                resource=f"collection{index:03d}",
                items=[MetadataItemIn(uid=f"Uid{index:08d}", name="Object", code=" leading space is not a code")],
            )
            for index in range(resource_type_count)
        ],
    )
    assert len({finding.resource_type for finding in report.findings}) == resource_type_count

    rendered = render_validation_pdf(report, target="probe", generated_at=datetime(2026, 1, 1, tzinfo=UTC))

    assert rendered.startswith(b"%PDF")


#: A validate run reading a project that publishes rewritten names and hyphenated codes.
_SUBSTITUTE_CONFIG = GenerateConfig(concept_code_source="code", hostile_names=HostileNamePosture.SUBSTITUTE)

#: The same project answering the same question with today's refusal instead.
_REFUSE_CONFIG = GenerateConfig(concept_code_source="code", hostile_names=HostileNamePosture.REFUSE)

#: A play 2.42 data element whose name the guide publishes rewritten under `substitute`.
_VITAMIN_NAME = "Vitamin A given to < 5y"


def _graded(config: GenerateConfig, name: str, code: str | None = None) -> ValidationFinding:
    """The single name finding one data set raises under the posture the given config states."""
    report = build_code_validation(
        [],
        [MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name=name, code=code)])],
        config,
    )
    findings = _hostile(report)
    assert len(findings) == 1
    return findings[0]


def test_under_substitute_a_build_aborting_name_is_informational_and_states_both_spellings() -> None:
    """The guide rewrites the name, so the finding says what is published rather than demanding a change."""
    finding = _graded(_SUBSTITUTE_CONFIG, _VITAMIN_NAME)
    assert finding.severity == "info"
    assert finding.message == (
        "published as 'Vitamin A given to under 5y' - the name is rewritten for publication "
        "(hostile_names = \"substitute\"); DHIS2 keeps 'Vitamin A given to < 5y'"
    )
    assert "change the name in DHIS2" not in finding.message


@pytest.mark.parametrize(
    "config", [_REFUSE_CONFIG, GenerateConfig(concept_code_source="code")], ids=["refuse", "unset"]
)
def test_under_refuse_and_unset_the_same_name_stays_an_error(config: GenerateConfig) -> None:
    """Both postures publish the name byte-true, so the build really does abort and the grade holds."""
    finding = _graded(config, _VITAMIN_NAME)
    assert finding.severity == "error"
    assert "so `make build` fails" in finding.message
    assert "change the name in DHIS2" in finding.message


def test_the_other_comparison_is_downgraded_under_substitute_too() -> None:
    """The rewrite treats '>' as it treats '<', so a '>' name publishes as words and its page is well-formed."""
    finding = _graded(_SUBSTITUTE_CONFIG, "Mortality > 5 years")
    assert finding.severity == "info"
    assert "published as 'Mortality over 5 years'" in finding.message
    assert "render malformed" not in finding.message


def test_a_survivable_character_stays_a_warning_under_substitute() -> None:
    """Nothing stands in a bare '&''s place, so it malforms its pages under either posture."""
    finding = _graded(_SUBSTITUTE_CONFIG, "R&D bednets")
    assert finding.severity == "warning"
    assert "render malformed" in finding.message
    assert "rewritten for publication" not in finding.message


def test_a_name_carrying_both_keeps_the_grade_the_rewrite_cannot_remove() -> None:
    """With both comparisons rewritten away the '&' is still in the published name, so the page is still malformed."""
    finding = _graded(_SUBSTITUTE_CONFIG, "Age < 5 & > 1")
    assert finding.severity == "warning"
    assert "published as 'Age under 5 & over 1'" in finding.message
    assert "the published name still contains '&'" in finding.message


def test_under_substitute_an_option_name_is_downgraded_by_the_deep_pass_too() -> None:
    """An option's name is rewritten exactly as a data set's is, so the deep pass grades it the same way."""
    report = build_code_validation(
        [_set("Os1aaaaaaaa", "Age band", [OptionIn(uid="Op1aaaaaaaa", code="LT5", name="< 5 years")])],
        [],
        _SUBSTITUTE_CONFIG,
    )
    findings = _hostile(report)
    assert [finding.severity for finding in findings] == ["info"]
    assert "published as 'under 5 years'" in findings[0].message


def test_under_substitute_a_spaced_code_states_the_hyphenated_form_it_publishes() -> None:
    """The published concept code is the hyphenated one, so the finding names it beside the DHIS2 code."""
    report = build_code_validation(
        [_set("Os1aaaaaaaa", "Diagnosis", [OptionIn(uid="Op1aaaaaaaa", code="Pre eclampsia", name="Pre eclampsia")])],
        [],
        _SUBSTITUTE_CONFIG,
    )
    spaced = [finding for finding in report.findings if finding.category == "spaced-code"]
    assert len(spaced) == 1
    assert spaced[0].severity == "info"
    assert spaced[0].message == (
        "code contains spaces; published as 'Pre-eclampsia' - each space becomes a hyphen for "
        "publication (hostile_names = \"substitute\"); DHIS2 keeps 'Pre eclampsia'"
    )


def test_without_substitute_a_spaced_code_keeps_saying_what_the_quoted_form_costs() -> None:
    """Nothing rewrites the code, so the finding keeps stating the form the guide really emits."""
    report = build_code_validation(
        [_set("Os1aaaaaaaa", "Diagnosis", [OptionIn(uid="Op1aaaaaaaa", code="Pre eclampsia", name="Pre eclampsia")])],
        [],
        _REFUSE_CONFIG,
    )
    spaced = [finding for finding in report.findings if finding.category == "spaced-code"]
    assert [finding.message for finding in spaced] == [
        'code contains spaces; FHIR-valid but emitted in the quoted #"..." form'
    ]


def test_a_build_aborting_code_stays_an_error_under_substitute() -> None:
    """The code substituter rewrites a space and never a '<', so the run is refused under either posture."""
    report = build_code_validation(
        [],
        [
            MetadataCollectionIn(
                resource="optionSets",
                items=[MetadataItemIn(uid="csRsm0D7guY", name="MAL ENTO: IRS 6 Months", code=_HOSTILE_CODE)],
            )
        ],
        _SUBSTITUTE_CONFIG,
    )
    findings = _hostile_code(report)
    assert [finding.severity for finding in findings] == ["error"]
    assert "the substitution rewrites a space in a code and never '<'" in findings[0].message
    assert "change the code in DHIS2" in findings[0].message


def test_the_flag_overrides_the_project_in_both_directions() -> None:
    """A what-if run reads the instance under the other posture, whichever way round it is asked."""
    collections = [
        MetadataCollectionIn(resource="dataSets", items=[MetadataItemIn(uid="Ds1aaaaaaaa", name=_VITAMIN_NAME)])
    ]
    over_refuse = build_code_validation([], collections, _REFUSE_CONFIG, hostile_names=HostileNamePosture.SUBSTITUTE)
    over_substitute = build_code_validation(
        [], collections, _SUBSTITUTE_CONFIG, hostile_names=HostileNamePosture.REFUSE
    )
    assert [finding.severity for finding in _hostile(over_refuse)] == ["info"]
    assert [finding.severity for finding in _hostile(over_substitute)] == ["error"]
    assert over_refuse.hostile_names is HostileNamePosture.SUBSTITUTE
    assert over_substitute.hostile_names is HostileNamePosture.REFUSE


def test_a_substitute_posture_project_carrying_only_rewritten_names_reports_no_error() -> None:
    """The exit code follows the graded severities, so `make refresh` runs clean past validate."""
    report = build_code_validation(
        [],
        [
            MetadataCollectionIn(
                resource="dataSets",
                items=[
                    MetadataItemIn(uid="Ds1aaaaaaaa", name=_VITAMIN_NAME, code="DS_VITA"),
                    MetadataItemIn(uid="Ds2aaaaaaaa", name=_MORTALITY_NAME, code="DS_MORT"),
                ],
            )
        ],
        _SUBSTITUTE_CONFIG,
    )
    assert report.error_count == 0
    assert report.info_count == 2


@pytest.mark.parametrize(
    ("posture", "expected"),
    [
        (HostileNamePosture.SUBSTITUTE, "substitute - a name carrying '<' is rewritten for publication"),
        (HostileNamePosture.REFUSE, "refuse - every name is published exactly as DHIS2 states it"),
        (None, "not set - every name is published exactly as DHIS2 states it"),
    ],
    ids=["substitute", "refuse", "unset"],
)
def test_every_renderer_states_the_posture_the_run_graded_under(
    posture: HostileNamePosture | None, expected: str
) -> None:
    """The report carries the posture, and the Markdown says it in the line the terminal prints."""
    report = build_code_validation([], [], GenerateConfig(hostile_names=posture))
    assert report.hostile_names is posture
    assert report.hostile_names_line.startswith(expected)
    markdown = render_validation_markdown(report, "probe", _GENERATED_AT)
    assert f"- hostile names: {report.hostile_names_line}" in markdown
    assert render_validation_pdf(report, target="probe", generated_at=_GENERATED_AT).startswith(b"%PDF")

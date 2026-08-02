"""Unit tests for FHIR-safety validation: instance-wide sweep, deep option pass, markdown report."""

from datetime import UTC, datetime

from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation import build_code_validation, render_validation_markdown
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
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
    """The instance-wide sweep flags invalid codes as errors and per-type duplicates as warnings."""
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
    assert categories == [("error", "invalid-code"), ("warning", "duplicate-code"), ("warning", "duplicate-code")]
    assert all(finding.resource_type == "dataElements" for finding in report.findings)


def test_option_invalid_code_is_an_error() -> None:
    """Edge whitespace makes an option code invalid per the R4 code datatype."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])])
    assert [finding.category for finding in report.findings] == ["invalid-code"]
    assert report.findings[0].resource_type == "options"
    assert "[in Sex]" in report.findings[0].name
    assert report.error_count == 1


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


def test_option_duplicate_codes_are_errors() -> None:
    """The same code on two options in one set breaks CodeSystem uniqueness."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", code="X", name="One"),
        OptionIn(uid="Op2aaaaaaaa", code="X", name="Two"),
    ]
    report = _validate([_set("Aa1aaaaaaaa", "Dup", options)])
    assert [finding.category for finding in report.findings] == ["duplicate-code", "duplicate-code"]
    assert report.error_count == 2


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
    """In code mode the same option findings keep their error/warning severities."""
    options = [
        OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad"),
        OptionIn(uid="Op2aaaaaaaa", name="NoCode"),
    ]
    report = build_code_validation([_set("Aa1aaaaaaaa", "Sex", options)], [], _CODE_MODE)
    assert report.error_count == 1
    assert report.warning_count == 1
    assert not any("switching to code mode" in finding.message for finding in report.findings)


def test_code_source_override_wins_over_the_config() -> None:
    """The explicit code_source argument overrides `concept_code_source` in both directions."""
    sets = [_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Bad")])]
    assert build_code_validation(sets, [], _CONFIG, "code").error_count == 1
    assert build_code_validation(sets, [], _CODE_MODE, "id").error_count == 0
    assert build_code_validation(sets, [], _CODE_MODE, "id").info_count == 1


def test_sweep_severities_ignore_the_code_source() -> None:
    """The instance-wide sweep keeps its severities in id mode - only the option pass is gated."""
    collection = MetadataCollectionIn(
        resource="dataElements", items=[MetadataItemIn(uid="De1aaaaaaaa", name="Bad", code=" X ")]
    )
    assert build_code_validation([], [collection], _CONFIG).error_count == 1
    assert build_code_validation([], [collection], _CODE_MODE).error_count == 1


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


def test_name_derived_checks_only_in_name_mode() -> None:
    """Long names raise findings only when naming derives from names; id mode never overflows."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    sets = [_set("Cc3cccccccc", long_name, [])]
    assert build_code_validation(sets, [], _CONFIG).findings == []
    named = build_code_validation(sets, [], GenerateConfig(naming=NamingConfig(source="name")))
    assert [finding.category for finding in named.findings] == ["long-name"]


def test_findings_sorted_errors_first() -> None:
    """Errors sort before warnings and infos."""
    sets = [
        _set("Aa1aaaaaaaa", "Zulu", [OptionIn(uid="Op1aaaaaaaa", name="NoCode")]),
        _set("Bb2bbbbbbbb", "Alpha", [OptionIn(uid="Op2aaaaaaaa", code=" bad ", name="Bad")]),
    ]
    report = _validate(sets)
    assert [finding.severity for finding in report.findings] == ["error", "warning"]


def test_report_json_carries_counts() -> None:
    """The computed severity counts land in the serialized report."""
    report = _validate([_set("Aa1aaaaaaaa", "Sex", [OptionIn(uid="Op1aaaaaaaa", code=" M ", name="Male")])])
    dumped = report.model_dump()
    assert dumped["error_count"] == 1
    assert dumped["warning_count"] == 0


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
    assert "| error | invalid-code |" in markdown


def test_markdown_report_clean() -> None:
    """A clean report says so instead of rendering empty tables."""
    markdown = render_validation_markdown(_validate([]), "probe", _GENERATED_AT)
    assert "No findings" in markdown

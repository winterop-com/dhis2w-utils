"""Unit tests for FHIR-safety validation of option-set codes and names."""

from dhis2w_fhir.models import GenerateConfig, OptionInput, OptionSetInput
from dhis2w_fhir.validation import build_code_validation

_CONFIG = GenerateConfig()


def _set(uid: str, name: str, options: list[OptionInput]) -> OptionSetInput:
    """Build an option set input."""
    return OptionSetInput(uid=uid, name=name, options=options)


def test_clean_instance_has_no_findings() -> None:
    """Valid unique codes yield an empty findings list and exact counts."""
    report = build_code_validation(
        [_set("Aa1aaaaaaaa", "Sex", [OptionInput(uid="Op1aaaaaaaa", code="M", name="Male")])], _CONFIG
    )
    assert report.findings == []
    assert report.option_set_count == 1
    assert report.option_count == 1
    assert report.error_count == 0


def test_invalid_code_is_an_error() -> None:
    """Edge whitespace makes a code invalid per the R4 code datatype."""
    report = build_code_validation(
        [_set("Aa1aaaaaaaa", "Sex", [OptionInput(uid="Op1aaaaaaaa", code=" M ", name="Male")])], _CONFIG
    )
    assert [finding.category for finding in report.findings] == ["invalid-code"]
    assert report.findings[0].severity == "error"
    assert report.error_count == 1


def test_missing_code_is_a_warning() -> None:
    """An option without a code warns about the UID fallback."""
    report = build_code_validation([_set("Aa1aaaaaaaa", "Sex", [OptionInput(uid="Op1aaaaaaaa", name="Male")])], _CONFIG)
    assert [finding.category for finding in report.findings] == ["missing-code"]
    assert report.warning_count == 1


def test_duplicate_codes_are_errors() -> None:
    """The same code on two options in one set breaks CodeSystem uniqueness."""
    options = [
        OptionInput(uid="Op1aaaaaaaa", code="X", name="One"),
        OptionInput(uid="Op2aaaaaaaa", code="X", name="Two"),
    ]
    report = build_code_validation([_set("Aa1aaaaaaaa", "Dup", options)], _CONFIG)
    assert [finding.category for finding in report.findings] == ["duplicate-code", "duplicate-code"]
    assert report.error_count == 2


def test_spaced_code_is_info() -> None:
    """A FHIR-valid code containing spaces is flagged info (quoted #\"...\" form needed)."""
    report = build_code_validation(
        [_set("Aa1aaaaaaaa", "Sex", [OptionInput(uid="Op1aaaaaaaa", code="two words", name="Spaced")])], _CONFIG
    )
    assert [finding.category for finding in report.findings] == ["spaced-code"]
    assert report.info_count == 1


def test_long_name_and_collision_are_infos() -> None:
    """Id truncation and slug collisions surface as infos on the owning sets."""
    long_name = "Residence of the malaria case/s that prompted foci investigation"
    sets = [
        _set("Aa1aaaaaaaa", "Sex", []),
        _set("Bb2bbbbbbbb", "SEX", []),
        _set("Cc3cccccccc", long_name, []),
    ]
    report = build_code_validation(sets, _CONFIG)
    categories = {finding.category for finding in report.findings}
    assert categories == {"name-collision", "long-name"}


def test_findings_sorted_errors_first() -> None:
    """Errors sort before warnings and infos."""
    sets = [
        _set("Aa1aaaaaaaa", "Zulu", [OptionInput(uid="Op1aaaaaaaa", name="NoCode")]),
        _set("Bb2bbbbbbbb", "Alpha", [OptionInput(uid="Op2aaaaaaaa", code=" bad ", name="Bad")]),
    ]
    report = build_code_validation(sets, _CONFIG)
    assert [finding.severity for finding in report.findings] == ["error", "warning"]


def test_report_json_carries_counts() -> None:
    """The computed severity counts land in the serialized report."""
    report = build_code_validation(
        [_set("Aa1aaaaaaaa", "Sex", [OptionInput(uid="Op1aaaaaaaa", code=" M ", name="Male")])], _CONFIG
    )
    dumped = report.model_dump()
    assert dumped["error_count"] == 1
    assert dumped["warning_count"] == 0

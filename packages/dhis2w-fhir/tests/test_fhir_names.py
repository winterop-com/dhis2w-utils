"""Unit tests for dhis2w_fhir.names helpers and the cnl-0 shape of every emitted FSH name."""

import re

import pytest
from dhis2w_fhir.config import GenerateConfig, NamingConfig
from dhis2w_fhir.foundation import build_foundation_artifacts
from dhis2w_fhir.names import (
    code_or_uid,
    describe_code_defect,
    fsh_code,
    is_valid_fhir_code,
    join_name_segments,
    kebab,
    page_text,
    pascal,
    quote,
)
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.resources.questionnaires import build_questionnaire_artifacts
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireItemIn, QuestionnaireSourceIn


def test_pascal_collapses_punctuation() -> None:
    """Free text with punctuation collapses to PascalCase."""
    assert pascal("Birth type") == "BirthType"
    assert pascal("ANC 1st visit (fixed)") == "ANC1stVisitFixed"


def test_pascal_never_starts_with_digit() -> None:
    """A digit-leading result gets the fallback prefixed."""
    assert pascal("1st visit") == "Generated1stVisit"


def test_pascal_empty_uses_fallback() -> None:
    """Empty or symbol-only input falls back."""
    assert pascal("") == "Generated"
    assert pascal("!!!", fallback="Fallback") == "Fallback"


def test_kebab_lowercases_and_joins() -> None:
    """Free text becomes a kebab-case slug."""
    assert kebab("Birth type") == "birth-type"
    assert kebab("ANC 1st visit (fixed)") == "anc-1st-visit-fixed"
    assert kebab("") == "generated"


def test_quote_escapes_and_flattens() -> None:
    """Backslashes and quotes are escaped; newlines and runs of whitespace flatten to one space."""
    assert quote('say "hi"') == '"say \\"hi\\""'
    assert quote("back\\slash") == '"back\\\\slash"'
    assert quote("line one\nline  two") == '"line one line two"'


def test_fsh_code_quotes_spaces() -> None:
    """Codes with spaces use the quoted form."""
    assert fsh_code("ABC123") == "#ABC123"
    assert fsh_code("ANC 01") == '#"ANC 01"'


def test_fsh_code_escapes_like_quote() -> None:
    """The quoted form escapes backslashes and double quotes exactly as `quote` does."""
    assert fsh_code('say "hi" now') == '#"say \\"hi\\" now"'
    assert fsh_code("back\\slash here") == '#"back\\\\slash here"'
    assert fsh_code('both \\ and " here') == '#"both \\\\ and \\" here"'
    assert fsh_code('say "hi" now')[2:-1] == quote('say "hi" now')[1:-1]


def test_code_or_uid_falls_back() -> None:
    """The code slot carries the DHIS2 code when usable and repeats the UID otherwise."""
    assert code_or_uid("SL", "ImspTQPwCqd") == "SL"
    assert code_or_uid("two words", "ImspTQPwCqd") == "two words"
    assert code_or_uid(None, "ImspTQPwCqd") == "ImspTQPwCqd"
    assert code_or_uid("", "ImspTQPwCqd") == "ImspTQPwCqd"
    assert code_or_uid(" padded ", "ImspTQPwCqd") == "ImspTQPwCqd"


def test_is_valid_fhir_code() -> None:
    """FHIR code datatype: non-empty, no leading/trailing/double whitespace."""
    assert is_valid_fhir_code("ANC-01")
    assert is_valid_fhir_code("two words")
    assert not is_valid_fhir_code(None)
    assert not is_valid_fhir_code("")
    assert not is_valid_fhir_code(" leading")
    assert not is_valid_fhir_code("trailing ")
    assert not is_valid_fhir_code("double  space")
    assert not is_valid_fhir_code("tab\tinside")


def test_describe_code_defect_is_none_for_a_valid_code() -> None:
    """A code the R4 datatype accepts carries no defect."""
    assert describe_code_defect("ANC-01") is None
    assert describe_code_defect("two words") is None


def test_describe_code_defect_names_each_defect() -> None:
    """Every defect the helper knows about gets its own phrase."""
    assert describe_code_defect("") == "code is empty"
    assert describe_code_defect("BLUE\nBLUE") == "code contains a line break"
    assert describe_code_defect("BLUE\rBLUE") == "code contains a line break"
    assert describe_code_defect("tab\tinside") == "code contains a tab"
    assert describe_code_defect(" M") == "code has leading whitespace"
    assert describe_code_defect("M ") == "code has trailing whitespace"
    assert describe_code_defect("double  space") == "code contains consecutive spaces"


def test_describe_code_defect_reports_the_first_applicable_defect() -> None:
    """A code carrying several defects reports the one earliest in the fixed order."""
    assert describe_code_defect(" BLUE\nBLUE") == "code contains a line break"
    assert describe_code_defect(" tab\there ") == "code contains a tab"
    assert describe_code_defect(" double  space") == "code has leading whitespace"
    assert describe_code_defect("double  space ") == "code has trailing whitespace"


def test_describe_code_defect_falls_through_to_the_generic_phrase() -> None:
    """Whitespace outside the named list still yields a phrase rather than None."""
    assert describe_code_defect("non\xa0breaking") == "code contains whitespace"


def test_join_name_segments_drops_the_empty_ones() -> None:
    """Underscores join what is there; an empty naming token leaves no leading or doubled underscore."""
    assert join_name_segments("D2OS", "BirthType") == "D2OS_BirthType"
    assert join_name_segments("", "BirthType") == "BirthType"
    assert join_name_segments("D2OS", "Sex", "Aa1aaaaaaaa") == "D2OS_Sex_Aa1aaaaaaaa"
    assert join_name_segments("", "") == ""


# R4 cnl-0: a computational name matches [A-Z]([A-Za-z0-9_]){0,254}.
_CNL_0 = re.compile(r"^[A-Z][A-Za-z0-9_]{0,254}$")

#: The FSH declaration keywords whose token is a FHIR computational name.
_DECLARATION_KEYWORDS = ("CodeSystem: ", "ValueSet: ", "Extension: ", "Profile: ")

_OPTION_SET = OptionSetIn(
    uid="Xa1b2c3d4e5",
    name="Birth type",
    options=[OptionIn(uid="kRRUtYaGett", code="NB", name="Natural Birth", sort_order=1)],
)

_ORGANISATION_UNIT = OrganisationUnitIn(uid="ImspTQPwCqd", name="Sierra Leone", level=1, path="/ImspTQPwCqd")

_DATA_SET = QuestionnaireSourceIn(
    uid="BfMAe6Itzgt",
    name="Child Health",
    kind="aggregate",
    flat_items=[QuestionnaireItemIn(uid="De1aaaaaaaa", name="BCG doses given", value_type="INTEGER")],
)


def _emitted_contents(config: GenerateConfig) -> list[str]:
    """Every FSH file the emitters produce for one naming configuration."""
    contents = [artifact.content for artifact in build_foundation_artifacts(config, ig_status="draft")]
    contents += [
        artifact.content for artifact in build_option_set_artifacts([_OPTION_SET], config, ig_status="draft").artifacts
    ]
    contents.append(build_organisation_unit_profiles(config, ig_status="draft").content)
    contents.append(build_organisation_unit_level_terminology([1], config, ig_status="draft").content)
    contents.append(build_organisation_unit_terminology([_ORGANISATION_UNIT], config, ig_status="draft").content)
    contents += [
        artifact.content
        for artifact in build_questionnaire_artifacts(
            [_DATA_SET], config, "http://example.org/fhir", ig_status="draft"
        ).artifacts
    ]
    return contents


def _declared_names(content: str) -> list[str]:
    """The computational name of every CodeSystem, ValueSet, Extension, and Profile declared in one file."""
    return [line.split(": ", 1)[1].strip() for line in content.splitlines() if line.startswith(_DECLARATION_KEYWORDS)]


def test_every_declared_fsh_name_matches_cnl_0() -> None:
    """Underscored names stay within R4 cnl-0: an upper-case letter, then letters, digits, and underscores."""
    for config in (GenerateConfig(), GenerateConfig(naming=NamingConfig(source="name"))):
        declared = [name for content in _emitted_contents(config) for name in _declared_names(content)]
        assert declared
        for name in declared:
            assert _CNL_0.match(name), name


def test_questionnaire_name_matches_cnl_0() -> None:
    """Questionnaire.name is a computational name too, so the underscored form must satisfy cnl-0."""
    build = build_questionnaire_artifacts([_DATA_SET], GenerateConfig(), "http://example.org/fhir", ig_status="draft")
    content = next(
        artifact.content for artifact in build.artifacts if artifact.relative_path.endswith("BfMAe6Itzgt.fsh")
    )
    name = next(line for line in content.splitlines() if line.startswith("* name = ")).split('"')[1]
    assert name == "D2DS_BfMAe6Itzgt"
    assert _CNL_0.match(name)


#: A real play-2.42 data set name. Its `<` is what aborts the IG publisher's HTML parse.
_MORTALITY_NAME = "Mortality < 5 years by gender"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_MORTALITY_NAME, '"Mortality &lt; 5 years by gender"'),
        ("A > B", '"A &gt; B"'),
        ("Cases & deaths", '"Cases &amp; deaths"'),
        ("<b>&amp;</b>", '"&lt;b&gt;&amp;amp;&lt;/b&gt;"'),
        ('He said "hi"', '"He said \\"hi\\""'),
        ("", '""'),
    ],
)
def test_page_text_escapes_markup_before_quoting(value: str, expected: str) -> None:
    """A page title's markup characters become entities, ampersand first so an entity is not double-escaped."""
    assert page_text(value) == expected


def test_page_text_leaves_ordinary_names_alone() -> None:
    """A name with no markup character reads exactly as `quote` renders it."""
    assert page_text("Child Health") == quote("Child Health")

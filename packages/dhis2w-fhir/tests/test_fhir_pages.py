"""Tests for the pages target: the five site pages, the per-artifact intros, and markdown escaping."""

from __future__ import annotations

import re

from dhis2w_fhir import (
    GenerateConfig,
    OptionIn,
    OptionSetIn,
    OrganisationUnitIn,
    build_option_set_artifacts,
    build_organisation_unit_instances,
    build_questionnaire_artifacts,
)
from dhis2w_fhir.names import markdown_text
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.resources.pages import INTRO_SUFFIX, PAGES_DIRECTORY, SITE_PAGE_FILENAMES, build_page_artifacts
from dhis2w_fhir.resources.pages.schemas import PagesIn
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
)

_CANONICAL = "http://example.org/fhir"

_AGE_COMBO = CategoryComboIn(
    uid="CcAaBbCcDdE",
    name="EPI/nutrition age",
    is_default=False,
    option_combos=[CategoryOptionComboIn(uid="Coc1aaaaaaa", name="<1y", code="U1")],
)

_DEATHS = QuestionnaireItemIn(uid="De1aaaaaaaa", name="Deaths", value_type="INTEGER", category_combo=_AGE_COMBO)
_GENDER = QuestionnaireItemIn(uid="De2aaaaaaaa", name="Gender", value_type="TEXT", option_set_uid="Os1aaaaaaaa")
_COMMENT = QuestionnaireItemIn(uid="De3aaaaaaaa", name="Comment", value_type="LONG_TEXT")

#: The play 2.42 data set whose name holds the character the IG publisher's HTML parse chokes on.
_DATA_SET = QuestionnaireSourceIn(
    uid="YFTk3VdO9av",
    name="Mortality < 5 years by gender",
    code="DS_MORT",
    description="Deaths under five,\r\nby gender.",
    kind="aggregate",
    period_type="Monthly",
    sections=[QuestionnaireSectionIn(uid="Sec1aaaaaaa", name="Deaths | reported", items=[_DEATHS, _GENDER])],
    flat_items=[_COMMENT],
)

_EVENT_PROGRAM = QuestionnaireSourceIn(
    uid="VBqh0ynB2wv",
    name="Malaria case registration",
    kind="event",
    flat_items=[QuestionnaireItemIn(uid="qrur9Dvnyt5", name="Age in years", value_type="INTEGER")],
)

_DESCRIBED_OPTION_SET = OptionSetIn(
    uid="Os1aaaaaaaa",
    name="Gender & age band",
    description="How gender and age are reported.",
    options=[
        OptionIn(uid="Op1aaaaaaaa", name="Fixed, >1y | special", code="FIXED", sort_order=1),
        OptionIn(uid="Op2aaaaaaaa", name="Female", code="F", sort_order=2),
    ],
)

_PLAIN_OPTION_SET = OptionSetIn(
    uid="Os2aaaaaaaa",
    name="Birth type",
    options=[OptionIn(uid="Op3aaaaaaaa", name="Single", sort_order=1)],
)

_ROOT_UNIT = OrganisationUnitIn(
    uid="ImspTQPwCqd",
    name="Sierra Leone",
    level=1,
    path="/ImspTQPwCqd",
    description="The national root unit.",
    latitude=8.5,
    longitude=-11.8,
    boundary_geojson='{"type":"Feature"}',
)

_CHILD_UNIT = OrganisationUnitIn(
    uid="O6uvpzGd5pu",
    name="Bo",
    level=2,
    path="/ImspTQPwCqd/O6uvpzGd5pu",
    parent_uid="ImspTQPwCqd",
)


def _pages_input() -> PagesIn:
    """The fixture every page test renders from."""
    return PagesIn(
        forms=[_DATA_SET, _EVENT_PROGRAM],
        option_sets=[_DESCRIBED_OPTION_SET, _PLAIN_OPTION_SET],
        organisation_units=[_ROOT_UNIT, _CHILD_UNIT],
    )


def _pages(config: GenerateConfig | None = None) -> dict[str, str]:
    """Build the page artifacts and index them by file name."""
    build = build_page_artifacts(_pages_input(), config or GenerateConfig())
    return {
        artifact.relative_path.removeprefix(f"{PAGES_DIRECTORY}/"): artifact.content for artifact in build.artifacts
    }


def test_every_site_page_is_emitted_once() -> None:
    """The five site pages are always emitted, each into the pagecontent sync directory."""
    build = build_page_artifacts(_pages_input(), GenerateConfig())
    site_pages = [
        artifact.relative_path for artifact in build.artifacts if not artifact.relative_path.endswith(INTRO_SUFFIX)
    ]
    assert site_pages == [f"{PAGES_DIRECTORY}/{name}" for name in SITE_PAGE_FILENAMES]
    assert {artifact.kind for artifact in build.artifacts} == {"page"}


def test_forms_page_catalogs_both_form_kinds() -> None:
    """forms.md holds a Data sets and an Event programs section, each with one linked catalog row."""
    forms = _pages()["forms.md"]
    assert forms.startswith("# Forms\n")
    assert "## Data sets" in forms
    assert "## Event programs" in forms
    assert (
        "| [Mortality &lt; 5 years by gender](Questionnaire-YFTk3VdO9av.html) "
        "| `YFTk3VdO9av` | `DS_MORT` | Monthly | 1 | 3 |"
    ) in forms
    assert (
        "| [Malaria case registration](Questionnaire-VBqh0ynB2wv.html) | `VBqh0ynB2wv` | `VBqh0ynB2wv` | 0 | 1 |"
        in (forms)
    )


def test_forms_page_lists_sections_and_the_unsectioned_remainder() -> None:
    """Under the catalog each form gets a subsection listing its sections plus the questions outside them."""
    forms = _pages()["forms.md"]
    assert "### Mortality &lt; 5 years by gender" in forms
    assert "- Deaths \\| reported (2 questions)" in forms
    assert "- Outside any section (1 questions)" in forms


def test_forms_page_escapes_names_for_markdown_and_for_table_cells() -> None:
    """A name holding `<` is HTML-escaped everywhere, and a name holding `|` cannot break out of its cell."""
    forms = _pages()["forms.md"]
    assert "Mortality < 5 years" not in forms
    assert "Deaths | reported" not in forms


def test_registry_page_summarises_the_hierarchy() -> None:
    """registry.md carries the totals, the root unit, the level table, and the profile pointers."""
    registry = _pages()["registry.md"]
    assert registry.startswith("# Registry\n")
    assert "| Organisation units | 2 |" in registry
    assert "| Units with a position | 1 |" in registry
    assert "| Units with boundary geometry | 1 |" in registry
    assert "**Sierra Leone** (`ImspTQPwCqd`)" in registry
    assert "| 1 | 1 |" in registry
    assert "| 2 | 1 |" in registry
    assert "`D2Organization`" in registry
    assert "`D2Location`" in registry
    assert "`partOf`" in registry


def test_terminology_page_links_every_option_set_and_the_support_systems() -> None:
    """terminology.md catalogs the option sets by concept count and links the support CodeSystems the run emits."""
    terminology = _pages()["terminology.md"]
    assert "| [Birth type](CodeSystem-d2-os-Os2aaaaaaaa-cs.html) | 1 | no |" in terminology
    assert "| [Gender &amp; age band](CodeSystem-d2-os-Os1aaaaaaaa-cs.html) | 2 | no |" in terminology
    assert "[Data elements](CodeSystem-d2-de-cs.html)" in terminology
    assert "[Category option combos](CodeSystem-d2-coc-cs.html)" in terminology
    assert "[Form types](CodeSystem-d2-form-type-cs.html)" in terminology
    assert "[Period types](CodeSystem-d2-period-type-cs.html)" in terminology


def test_terminology_page_reports_a_code_fallback_in_code_mode() -> None:
    """In code mode a set holding an option with no usable DHIS2 code is flagged as falling back to the UID."""
    config = GenerateConfig.model_validate({"concept_code_source": "code"})
    terminology = _pages(config)["terminology.md"]
    assert "| [Birth type](CodeSystem-d2-os-Os2aaaaaaaa-cs.html) | 1 | yes |" in terminology
    assert "| [Gender &amp; age band](CodeSystem-d2-os-Os1aaaaaaaa-cs.html) | 2 | no |" in terminology


def test_identifiers_page_tabulates_the_twelve_naming_systems() -> None:
    """identifiers.md explains the two identifier slices and lists every declared NamingSystem."""
    identifiers = _pages()["identifiers.md"]
    assert "`dhis2id`" in identifiers
    assert "`dhis2code`" in identifiers
    assert "`http://dhis2.org/fhir/property/dhis2-code`" in identifiers
    rows = [line for line in identifiers.splitlines() if line.startswith("| `D2")]
    assert len(rows) == 12
    assert "| `D2OrgUnitIdentifierSystem` | `http://dhis2.org/fhir/id/org-unit` |" in identifiers
    assert "| `D2CategoryOptionComboCodeIdentifierSystem` | " in identifiers


def test_periods_page_documents_the_extension_and_every_registered_period_type() -> None:
    """periods.md documents the three D2Period sub-extensions and tabulates the parser's whole registry."""
    periods = _pages()["periods.md"]
    assert "| `iso` | 1..1 | `string` |" in periods
    assert "| `type` | 1..1 | `code` |" in periods
    assert "| `period` | 0..1 | `Period` |" in periods
    for definition in PERIOD_TYPE_DEFINITIONS:
        assert f"| `{definition.name}` | `" in periods
    tabulated = [line for line in periods.splitlines() if re.match(r"^\| `[A-Za-z]+` \| `", line)]
    assert len(tabulated) == len(PERIOD_TYPE_DEFINITIONS)


def test_periods_page_examples_are_pinned_to_the_reference_date() -> None:
    """The ISO examples come from the fixed reference date, so a regenerate never moves with the calendar."""
    periods = _pages()["periods.md"]
    assert "| `Monthly` | `202512` | 2025-12-01 to 2025-12-31 |" in periods
    assert "| `Yearly` | `2025` | 2025-01-01 to 2025-12-31 |" in periods


def test_every_questionnaire_gets_an_intro() -> None:
    """Both form kinds earn an intro naming their DHIS2 source, and only the data set states a period type."""
    pages = _pages()
    data_set = pages[f"Questionnaire-YFTk3VdO9av{INTRO_SUFFIX}"]
    assert data_set.startswith("Generated from the DHIS2 data set Mortality &lt; 5 years by gender (YFTk3VdO9av).\n")
    assert "Deaths under five,\nby gender." in data_set
    assert "| Period type | Monthly |" in data_set
    assert "| Form type | `aggregate` |" in data_set
    assert "| Deaths \\| reported | 2 |" in data_set
    assert "| Outside any section | 1 |" in data_set
    event = pages[f"Questionnaire-VBqh0ynB2wv{INTRO_SUFFIX}"]
    assert event.startswith("Generated from the DHIS2 event program Malaria case registration (VBqh0ynB2wv).\n")
    assert "| Period type |" not in event
    assert "| Form type | `event` |" in event


def test_code_system_intro_is_gated_on_the_dhis2_description() -> None:
    """An option set carrying a description earns a CodeSystem intro; one without earns nothing."""
    pages = _pages()
    intro = pages[f"CodeSystem-d2-os-Os1aaaaaaaa-cs{INTRO_SUFFIX}"]
    assert intro.startswith("How gender and age are reported.\n")
    assert "Generated from the DHIS2 option set Gender &amp; age band (Os1aaaaaaaa)." in intro
    assert f"CodeSystem-d2-os-Os2aaaaaaaa-cs{INTRO_SUFFIX}" not in pages


def test_organization_intro_is_gated_on_the_dhis2_description() -> None:
    """An organisation unit carrying a description earns an Organization intro; one without earns nothing."""
    pages = _pages()
    intro = pages[f"Organization-ImspTQPwCqd{INTRO_SUFFIX}"]
    assert intro.startswith("The national root unit.\n")
    assert "Generated from the DHIS2 organisation unit Sierra Leone (ImspTQPwCqd), level 1." in intro
    assert f"Organization-O6uvpzGd5pu{INTRO_SUFFIX}" not in pages


def test_questionnaire_link_targets_match_the_emitted_instances() -> None:
    """Every forms.md link names the Questionnaire instance the questionnaire target actually emits."""
    config = GenerateConfig()
    build = build_questionnaire_artifacts([_DATA_SET, _EVENT_PROGRAM], config, _CANONICAL, ig_status="draft")
    forms = _pages()["forms.md"]
    instance_names = [artifact.fsh_name for artifact in build.artifacts if artifact.kind == "instances"]
    assert instance_names
    for instance_name in instance_names:
        assert f"]({instance_name}.html)" in forms


def test_code_system_link_targets_match_the_emitted_ids() -> None:
    """Every terminology.md link names the CodeSystem id the option-set target actually emits."""
    config = GenerateConfig()
    build = build_option_set_artifacts([_DESCRIBED_OPTION_SET, _PLAIN_OPTION_SET], config, ig_status="draft")
    terminology = _pages()["terminology.md"]
    emitted_ids = [re.search(r"^Id: (.+)$", artifact.content, re.M) for artifact in build.artifacts]
    assert len(emitted_ids) == 2
    for match in emitted_ids:
        assert match is not None
        assert f"](CodeSystem-{match.group(1)}.html)" in terminology


def test_organization_intro_names_the_emitted_instance() -> None:
    """The Organization intro file stem is the very instance name the registry target emits."""
    build = build_organisation_unit_instances([_ROOT_UNIT, _CHILD_UNIT], GenerateConfig())
    emitted = {
        match
        for artifact in build.artifacts
        for match in re.findall(r"^Instance: (Organization-\S+)$", artifact.content, re.M)
    }
    assert "Organization-ImspTQPwCqd" in emitted
    assert f"Organization-ImspTQPwCqd{INTRO_SUFFIX}" in _pages()


def test_markdown_text_escapes_in_the_documented_order() -> None:
    """The helper escapes `&` before the angle brackets, pipes only in a cell, and normalises CRLF in body text."""
    assert markdown_text("a & b < c > d") == "a &amp; b &lt; c &gt; d"
    assert markdown_text("Fixed, >1y | special", table_cell=True) == "Fixed, &gt;1y \\| special"
    assert markdown_text("one\r\ntwo") == "one\ntwo"
    assert markdown_text("one\r\ntwo", table_cell=True) == "one two"
    assert markdown_text("") == ""

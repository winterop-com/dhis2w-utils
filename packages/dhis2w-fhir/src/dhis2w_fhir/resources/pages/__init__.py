"""Markdown emission for the IG's narrative layer: five site pages plus the per-artifact intros.

SUSHI publishes everything under `ig/input/pagecontent/` without a `pages:`
block, and the IG publisher injects a `<Type>-<id>-intro.md` into the top of
the matching artifact page. Both halves are written here, into one sync
directory, and both carry the generated markdown header - so the
hand-authored `index.md` sitting beside them survives every clean and
regenerate.

The pages read the same projections the FSH targets emit from, never a
second endpoint, and every DHIS2-derived string goes through
`names.markdown_text` on the way in: a data set called "Mortality < 5 years
by gender" has to reach the publisher's strict HTML parse escaped, and a name
holding a pipe has to stay inside its table cell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from dhis2w_fhir.foundation import build_naming_system_declarations
from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.names import code_or_uid, markdown_text
from dhis2w_fhir.period.parser import parse_period
from dhis2w_fhir.period.recent import recent_periods
from dhis2w_fhir.period.schemas import PERIOD_TYPE_DEFINITIONS
from dhis2w_fhir.resources.option_sets import option_set_code_fallback, option_set_identities
from dhis2w_fhir.resources.organisation_units.naming import OrganisationUnitNaming
from dhis2w_fhir.resources.pages.schemas import (
    PERIOD_EXAMPLE_REFERENCE_DATE,
    CodeSystemIntroView,
    FormRow,
    FormSectionRow,
    IdentifiersView,
    LevelRow,
    OptionSetRow,
    OrganizationIntroView,
    PagesIn,
    PeriodsView,
    PeriodTypeRow,
    QuestionnaireIntroView,
    RegistryView,
    SupportCodeSystemRow,
    TerminologyView,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    FormKind,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
)
from dhis2w_fhir.writer import FshArtifact, FshBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn

__all__ = [
    "INTRO_SUFFIX",
    "PAGES_BASE_SUBDIRECTORY",
    "PAGES_DIRECTORY",
    "SITE_PAGE_FILENAMES",
    "build_page_artifacts",
]

#: Sync directory holding every generated page, relative to `ig/input/`.
PAGES_DIRECTORY = "pagecontent"

#: The directory under the project's `ig/` that `PAGES_DIRECTORY` is resolved against.
PAGES_BASE_SUBDIRECTORY = "input"

#: What names a per-artifact intro the IG publisher injects into an artifact page.
INTRO_SUFFIX = "-intro.md"

#: The site pages, in menu order. Stable kebab file names: the scaffolded menu links them.
SITE_PAGE_FILENAMES = ("forms.md", "registry.md", "terminology.md", "identifiers.md", "periods.md")

#: How each form kind reads in prose on the pages it appears on.
_KIND_LABELS: dict[FormKind, str] = {"aggregate": "data set", "event": "event program"}

#: What a data set with no DHIS2 period type shows in the period-type column.
_ABSENT_TEXT = "-"

_ENVIRONMENT = Environment(
    loader=PackageLoader("dhis2w_fhir.resources.pages", "templates"),
    autoescape=select_autoescape(default=False),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_page_artifacts(pages: PagesIn, config: GenerateConfig) -> FshBuild:
    """Build the five site pages plus every per-artifact intro the fetched metadata earns."""
    build = FshBuild()
    forms = [_form_row(source) for source in sorted(pages.forms, key=lambda item: (item.name, item.uid))]
    build.artifacts.append(_forms_page(forms))
    build.artifacts.append(_registry_page(pages.organisation_units, config))
    build.artifacts.append(_terminology_page(pages, config))
    build.artifacts.append(_identifiers_page(config))
    build.artifacts.append(_periods_page(config))
    build.artifacts.extend(_questionnaire_intros(forms))
    build.artifacts.extend(_code_system_intros(pages, config))
    build.artifacts.extend(_organization_intros(pages.organisation_units))
    return build


def _page(filename: str, template_name: str, **values: object) -> FshArtifact:
    """Render one page template into the sync directory's artifact."""
    return FshArtifact(
        relative_path=f"{PAGES_DIRECTORY}/{filename}",
        kind="page",
        fsh_name=filename,
        content=_ENVIRONMENT.get_template(template_name).render(**values),
    )


def _source_items(source: QuestionnaireSourceIn) -> list[QuestionnaireItemIn]:
    """Every question one form carries, sectioned and unsectioned alike."""
    return [item for section in source.sections for item in section.items] + list(source.flat_items)


def _form_row(source: QuestionnaireSourceIn) -> FormRow:
    """Project one form onto the catalog row, escaping every DHIS2-derived string for markdown."""
    return FormRow(
        uid=source.uid,
        kind=source.kind,
        name=markdown_text(source.name),
        cell_name=markdown_text(source.name, table_cell=True),
        code=markdown_text(code_or_uid(source.code, source.uid), table_cell=True),
        description=markdown_text(source.description or ""),
        period_type=markdown_text(source.period_type or _ABSENT_TEXT, table_cell=True),
        section_count=len(source.sections),
        question_count=len(_source_items(source)),
        unsectioned_question_count=len(source.flat_items),
        sections=[
            FormSectionRow(name=markdown_text(section.name, table_cell=True), question_count=len(section.items))
            for section in source.sections
        ],
    )


def _forms_page(forms: list[FormRow]) -> FshArtifact:
    """Build `forms.md`: the data set and event program catalogs plus a section breakdown per form."""
    return _page(
        "forms.md",
        "forms.md.jinja",
        data_sets=[form for form in forms if form.kind == "aggregate"],
        event_programs=[form for form in forms if form.kind == "event"],
    )


def _registry_page(organisation_units: list[OrganisationUnitIn], config: GenerateConfig) -> FshArtifact:
    """Build `registry.md`: the organisation-unit totals, the level table, and the profile pointers."""
    names = OrganisationUnitNaming.from_naming(config.naming)
    levels: dict[int, int] = {}
    for organisation_unit in organisation_units:
        levels[organisation_unit.level] = levels.get(organisation_unit.level, 0) + 1
    root = min(organisation_units, key=lambda item: (item.level, item.path, item.uid), default=None)
    view = RegistryView(
        unit_count=len(organisation_units),
        root_name=markdown_text(root.name) if root is not None else "",
        root_uid=root.uid if root is not None else "",
        position_count=sum(1 for item in organisation_units if item.latitude is not None),
        boundary_count=sum(1 for item in organisation_units if item.boundary_geojson is not None),
        organization_profile=names.organization_profile,
        location_profile=names.location_profile,
        levels=[LevelRow(level=level, unit_count=levels[level]) for level in sorted(levels)],
    )
    return _page("registry.md", "registry.md.jinja", registry=view)


def _terminology_page(pages: PagesIn, config: GenerateConfig) -> FshArtifact:
    """Build `terminology.md`: the option-set catalog plus the support CodeSystems this run emits."""
    by_uid = {option_set.uid: option_set for option_set in pages.option_sets}
    rows = [
        OptionSetRow(
            uid=identity.uid,
            cell_name=markdown_text(identity.name, table_cell=True),
            code_system_id=identity.code_system_id,
            concept_count=len(by_uid[identity.uid].options),
            code_fallback=option_set_code_fallback(by_uid[identity.uid], config),
        )
        for identity in option_set_identities(pages.option_sets, config).identities
    ]
    view = TerminologyView(
        concept_code_source=config.concept_code_source,
        option_sets=rows,
        support_code_systems=_support_code_systems(pages, config),
    )
    return _page("terminology.md", "terminology.md.jinja", terminology=view)


def _support_code_systems(pages: PagesIn, config: GenerateConfig) -> list[SupportCodeSystemRow]:
    """The support CodeSystems this run emits, in artifact order - the two data-dictionary pairs, then foundation."""
    questionnaire_names = QuestionnaireNaming.from_naming(config.naming)
    foundation = FoundationNaming.from_naming(config.naming)
    items = [item for source in pages.forms for item in _source_items(source)]
    rows: list[SupportCodeSystemRow] = []
    if items:
        rows.append(
            SupportCodeSystemRow(
                label="Data elements",
                fsh_name=questionnaire_names.data_element_code_system,
                code_system_id=questionnaire_names.data_element_code_system_id,
                description="Every DHIS2 data element the generated questionnaires ask for.",
            )
        )
    if any(_is_disaggregated(item) for item in items):
        rows.append(
            SupportCodeSystemRow(
                label="Category option combos",
                fsh_name=questionnaire_names.category_option_combo_code_system,
                code_system_id=questionnaire_names.category_option_combo_code_system_id,
                description="Every DHIS2 category option combo the generated questionnaires disaggregate by.",
            )
        )
    rows.append(
        SupportCodeSystemRow(
            label="Form types",
            fsh_name=foundation.form_type_code_system,
            code_system_id=foundation.form_type_code_system_id,
            description="The kind of DHIS2 form a Questionnaire and its responses came from.",
        )
    )
    rows.append(
        SupportCodeSystemRow(
            label="Period types",
            fsh_name=foundation.period_type_code_system,
            code_system_id=foundation.period_type_code_system_id,
            description="The reporting period types the D2Period extension is typed by.",
        )
    )
    return rows


def _is_disaggregated(item: QuestionnaireItemIn) -> bool:
    """Check whether a data element carries a real (non-default) category combo."""
    return item.category_combo is not None and not item.category_combo.is_default


def _identifiers_page(config: GenerateConfig) -> FshArtifact:
    """Build `identifiers.md`: the two identifier slices, the property URIs, and the NamingSystem table."""
    view = IdentifiersView(
        identifier_system_base=config.identifier_system_base,
        concept_code_source=config.concept_code_source,
        naming_systems=build_naming_system_declarations(config),
    )
    return _page("identifiers.md", "identifiers.md.jinja", identifiers=view)


def _periods_page(config: GenerateConfig) -> FshArtifact:
    """Build `periods.md`: the D2Period extension's shape and every period type the parser registers."""
    names = FoundationNaming.from_naming(config.naming)
    view = PeriodsView(
        period_extension=names.period_extension,
        period_extension_id=names.period_extension_id,
        period_type_code_system=names.period_type_code_system,
        period_type_code_system_id=names.period_type_code_system_id,
        period_type_value_set=names.period_type_value_set,
        period_types=[_period_type_row(definition.name) for definition in PERIOD_TYPE_DEFINITIONS],
    )
    return _page("periods.md", "periods.md.jinja", periods=view)


def _period_type_row(period_type: str) -> PeriodTypeRow:
    """One period type's row: the newest ISO period completed by the fixed reference date, and its span."""
    recent = recent_periods(period_type, 1, PERIOD_EXAMPLE_REFERENCE_DATE)
    if not recent:
        return PeriodTypeRow(name=period_type, example_iso=_ABSENT_TEXT, span=_ABSENT_TEXT)
    value = parse_period(recent[0])
    return PeriodTypeRow(
        name=period_type,
        example_iso=value.iso,
        span=f"{value.start_date.isoformat()} to {value.end_date.isoformat()}",
    )


def _questionnaire_intros(forms: list[FormRow]) -> list[FshArtifact]:
    """Build one `Questionnaire-<uid>-intro.md` per generated Questionnaire - every form earns one."""
    return [
        _page(
            f"Questionnaire-{form.uid}{INTRO_SUFFIX}",
            "questionnaire-intro.md.jinja",
            intro=QuestionnaireIntroView(form=form, kind_label=_KIND_LABELS[form.kind], form_type_code=form.kind),
        )
        for form in forms
    ]


def _code_system_intros(pages: PagesIn, config: GenerateConfig) -> list[FshArtifact]:
    """Build a `CodeSystem-<id>-intro.md` for every option set carrying a DHIS2 description, and no others."""
    by_uid = {option_set.uid: option_set for option_set in pages.option_sets}
    artifacts: list[FshArtifact] = []
    for identity in option_set_identities(pages.option_sets, config).identities:
        description = (by_uid[identity.uid].description or "").strip()
        if not description:
            continue
        artifacts.append(
            _page(
                f"CodeSystem-{identity.code_system_id}{INTRO_SUFFIX}",
                "code-system-intro.md.jinja",
                intro=CodeSystemIntroView(
                    code_system_id=identity.code_system_id,
                    uid=identity.uid,
                    name=markdown_text(identity.name),
                    description=markdown_text(description),
                ),
            )
        )
    return artifacts


def _organization_intros(organisation_units: list[OrganisationUnitIn]) -> list[FshArtifact]:
    """Build an `Organization-<uid>-intro.md` for every organisation unit carrying a DHIS2 description."""
    artifacts: list[FshArtifact] = []
    for organisation_unit in sorted(organisation_units, key=lambda item: (item.path, item.uid)):
        description = (organisation_unit.description or "").strip()
        if not description:
            continue
        artifacts.append(
            _page(
                f"Organization-{organisation_unit.uid}{INTRO_SUFFIX}",
                "organization-intro.md.jinja",
                intro=OrganizationIntroView(
                    uid=organisation_unit.uid,
                    name=markdown_text(organisation_unit.name),
                    level=organisation_unit.level,
                    description=markdown_text(description),
                ),
            )
        )
    return artifacts

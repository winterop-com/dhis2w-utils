"""Page schemas: the fetched-input view the pages render from, plus the per-page view-models."""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.foundation.schemas import NamingSystemDeclaration
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIn
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
from dhis2w_fhir.resources.questionnaires.schemas import FormKind, QuestionnaireSourceIn

#: The day the period examples on `periods.md` are resolved against. A fixed date rather than
#: today: the page states what a `Monthly` ISO period looks like, which does not move, and a
#: run-dependent example would rewrite the page on every regenerate.
PERIOD_EXAMPLE_REFERENCE_DATE = datetime.date(2026, 1, 1)


class PagesIn(BaseModel):
    """Everything the narrative pages render from - the projections the other targets already fetched.

    The pages add no endpoint of their own: a form catalog is the questionnaire target's
    sources, the registry is the org-unit target's units, and the terminology page is the
    option-set target's selection, each read through the very projection that target emits from.
    """

    model_config = ConfigDict(frozen=True)

    forms: list[QuestionnaireSourceIn] = Field(default_factory=list)
    option_sets: list[OptionSetIn] = Field(default_factory=list)
    organisation_units: list[OrganisationUnitIn] = Field(default_factory=list)


class FormSectionRow(BaseModel):
    """One section of a form as the forms page and the form's intro list it."""

    model_config = ConfigDict(frozen=True)

    name: str
    question_count: int


class FormRow(BaseModel):
    """One data set or event program as the forms page catalogs it, every string page-escaped."""

    model_config = ConfigDict(frozen=True)

    uid: str
    kind: FormKind
    name: str
    cell_name: str
    code: str
    description: str
    period_type: str
    section_count: int
    question_count: int
    unsectioned_question_count: int
    sections: list[FormSectionRow] = Field(default_factory=list)

    @property
    def page_link(self) -> str:
        """The compiled artifact page this form's Questionnaire lands on."""
        return f"Questionnaire-{self.uid}.html"


class QuestionnaireIntroView(BaseModel):
    """One Questionnaire's intro page: where it came from, how it reports, and its section table."""

    model_config = ConfigDict(frozen=True)

    form: FormRow
    kind_label: str
    form_type_code: str


class CodeSystemIntroView(BaseModel):
    """One option-set CodeSystem's intro page - emitted only for a set carrying a DHIS2 description."""

    model_config = ConfigDict(frozen=True)

    code_system_id: str
    uid: str
    name: str
    description: str


class OrganizationIntroView(BaseModel):
    """One organisation unit's intro page - emitted only for a unit carrying a DHIS2 description."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    level: int
    description: str


class LevelRow(BaseModel):
    """One hierarchy level of the registry and how many organisation units sit at it."""

    model_config = ConfigDict(frozen=True)

    level: int
    unit_count: int


class RegistryView(BaseModel):
    """The organisation-unit registry as the registry page summarises it."""

    model_config = ConfigDict(frozen=True)

    unit_count: int
    root_name: str = ""
    root_uid: str = ""
    position_count: int = 0
    boundary_count: int = 0
    organization_profile: str = ""
    location_profile: str = ""
    levels: list[LevelRow] = Field(default_factory=list)


class OptionSetRow(BaseModel):
    """One option set as the terminology page catalogs it."""

    model_config = ConfigDict(frozen=True)

    uid: str
    cell_name: str
    code_system_id: str
    concept_count: int
    code_fallback: bool

    @property
    def page_link(self) -> str:
        """The compiled artifact page this option set's CodeSystem lands on."""
        return f"CodeSystem-{self.code_system_id}.html"


class SupportCodeSystemRow(BaseModel):
    """One support CodeSystem the terminology page links, when the run emits it."""

    model_config = ConfigDict(frozen=True)

    label: str
    fsh_name: str
    code_system_id: str
    description: str

    @property
    def page_link(self) -> str:
        """The compiled artifact page this support CodeSystem lands on."""
        return f"CodeSystem-{self.code_system_id}.html"


class TerminologyView(BaseModel):
    """The terminology page: the option-set catalog plus the support CodeSystems the run emitted."""

    model_config = ConfigDict(frozen=True)

    concept_code_source: str
    option_sets: list[OptionSetRow] = Field(default_factory=list)
    support_code_systems: list[SupportCodeSystemRow] = Field(default_factory=list)


class IdentifiersView(BaseModel):
    """The identifiers page: the two identifier slices, the concept property URIs, and the NamingSystems."""

    model_config = ConfigDict(frozen=True)

    identifier_system_base: str
    concept_code_source: str
    naming_systems: list[NamingSystemDeclaration] = Field(default_factory=list)


class PeriodTypeRow(BaseModel):
    """One DHIS2 period type as the periods page tabulates it: its code, an ISO example, and that span."""

    model_config = ConfigDict(frozen=True)

    name: str
    example_iso: str
    span: str


class PeriodsView(BaseModel):
    """The periods page: the D2Period extension's shape plus every registered period type."""

    model_config = ConfigDict(frozen=True)

    period_extension: str
    period_extension_id: str
    period_type_code_system: str
    period_type_code_system_id: str
    period_type_value_set: str
    period_types: list[PeriodTypeRow] = Field(default_factory=list)

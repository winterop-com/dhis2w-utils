"""Version-neutral FHIR IG generation: fhir.toml config, FSH emission, and project scaffolding.

Each component owns its schemas; this module is the one stable import
surface over them, so `from dhis2w_fhir import GenerateConfig` keeps working
however the components are arranged internally.
"""

from dhis2w_fhir.config import (
    FHIR_CONFIG_FILENAME,
    FhirProject,
    FhirProjectConfig,
    GenerateConfig,
    IgConfig,
    NamingConfig,
    NoFhirProjectError,
    find_project_fhir_config,
    load_fhir_config,
    load_project,
    write_fhir_config,
)
from dhis2w_fhir.foundation import (
    FORM_TYPE_DEFINITIONS,
    FormTypeDefinition,
    FoundationNaming,
    NamingSystemDeclaration,
    build_foundation_artifacts,
    build_naming_system_declarations,
)
from dhis2w_fhir.i18n import TRANSLATION_EXTENSION_URL, TranslationIn, name_translations, normalize_locale
from dhis2w_fhir.notes import aggregate_note
from dhis2w_fhir.period import (
    PERIOD_TYPE_DEFINITIONS,
    PERIOD_TYPE_NAMES,
    PeriodTypeDefinition,
    PeriodValue,
    parse_period,
)
from dhis2w_fhir.resources.option_sets import build_option_set_artifacts, max_slug_length, option_set_fsh_name
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn, OptionSetSelection
from dhis2w_fhir.resources.organisation_units import (
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology,
    build_organisation_unit_profiles,
    build_organisation_unit_terminology,
)
from dhis2w_fhir.resources.organisation_units.schemas import (
    GeoPoint,
    OrganisationUnitIn,
    OrganisationUnitSelection,
)
from dhis2w_fhir.resources.questionnaires import (
    ITEM_CONTROL_CODE_SYSTEM_URL,
    ITEM_CONTROL_EXTENSION_URL,
    build_questionnaire_artifacts,
)
from dhis2w_fhir.resources.questionnaires.schemas import (
    CategoryComboIn,
    CategoryOptionComboIn,
    QuestionnaireItemIn,
    QuestionnaireNaming,
    QuestionnaireSectionIn,
    QuestionnaireSourceIn,
    TargetSelection,
)
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.scaffold.schemas import InitOptions, ScaffoldFile, ScaffoldReport
from dhis2w_fhir.service import GenerateAllReport, GenerateReport, UnsupportedProgramError
from dhis2w_fhir.validation import build_code_validation, render_validation_markdown
from dhis2w_fhir.validation.pdf import render_validation_pdf
from dhis2w_fhir.validation.report import render_validation_csv
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    SeverityBreakdown,
    ValidationFinding,
)
from dhis2w_fhir.writer import (
    GENERATED_HEADER,
    FshArtifact,
    FshBuild,
    SyncReport,
    clean_generated_files,
    sync_artifacts,
    write_artifacts,
)

__all__ = [
    "FHIR_CONFIG_FILENAME",
    "FORM_TYPE_DEFINITIONS",
    "GENERATED_HEADER",
    "ITEM_CONTROL_CODE_SYSTEM_URL",
    "ITEM_CONTROL_EXTENSION_URL",
    "PERIOD_TYPE_DEFINITIONS",
    "PERIOD_TYPE_NAMES",
    "TRANSLATION_EXTENSION_URL",
    "CategoryComboIn",
    "CategoryOptionComboIn",
    "FhirProject",
    "FhirProjectConfig",
    "FhirValidationReport",
    "FormTypeDefinition",
    "FoundationNaming",
    "FshArtifact",
    "FshBuild",
    "GenerateAllReport",
    "GenerateConfig",
    "GenerateReport",
    "GeoPoint",
    "IgConfig",
    "InitOptions",
    "MetadataCollectionIn",
    "MetadataItemIn",
    "NamingConfig",
    "NamingSystemDeclaration",
    "NoFhirProjectError",
    "OptionIn",
    "OptionSetIn",
    "OptionSetSelection",
    "OrganisationUnitIn",
    "OrganisationUnitSelection",
    "PeriodTypeDefinition",
    "PeriodValue",
    "QuestionnaireItemIn",
    "QuestionnaireNaming",
    "QuestionnaireSectionIn",
    "QuestionnaireSourceIn",
    "ScaffoldFile",
    "ScaffoldReport",
    "SeverityBreakdown",
    "SyncReport",
    "TargetSelection",
    "TranslationIn",
    "UnsupportedProgramError",
    "ValidationFinding",
    "aggregate_note",
    "build_code_validation",
    "build_foundation_artifacts",
    "build_naming_system_declarations",
    "build_option_set_artifacts",
    "build_organisation_unit_instances",
    "build_organisation_unit_level_terminology",
    "build_organisation_unit_profiles",
    "build_organisation_unit_terminology",
    "build_questionnaire_artifacts",
    "build_scaffold_files",
    "clean_generated_files",
    "find_project_fhir_config",
    "load_fhir_config",
    "load_project",
    "max_slug_length",
    "name_translations",
    "normalize_locale",
    "option_set_fsh_name",
    "parse_period",
    "render_validation_csv",
    "render_validation_markdown",
    "render_validation_pdf",
    "sync_artifacts",
    "write_artifacts",
    "write_fhir_config",
]

"""Version-neutral FHIR IG generation: fhir.toml config, FSH emission, and project scaffolding."""

from dhis2w_fhir.config import (
    FHIR_CONFIG_FILENAME,
    NoFhirProjectError,
    find_project_fhir_config,
    load_fhir_config,
    load_project,
    write_fhir_config,
)
from dhis2w_fhir.models import (
    FhirProject,
    FhirProjectConfig,
    FhirValidationReport,
    FshArtifact,
    FshBuild,
    GenerateAllReport,
    GenerateConfig,
    GenerateReport,
    IgConfig,
    InitOptions,
    NamingConfig,
    OptionInput,
    OptionSetInput,
    OptionSetSelection,
    OrgUnitInput,
    OrgUnitSelection,
    ScaffoldFile,
    ScaffoldReport,
    ValidationFinding,
)
from dhis2w_fhir.organization import (
    build_org_unit_instances,
    build_org_unit_level_terminology,
    build_org_unit_profiles,
    build_org_unit_terminology,
)
from dhis2w_fhir.scaffold import build_scaffold_files
from dhis2w_fhir.terminology import build_option_set_artifacts
from dhis2w_fhir.validation import build_code_validation
from dhis2w_fhir.writer import GENERATED_HEADER, clean_generated_files, write_artifacts

__all__ = [
    "FHIR_CONFIG_FILENAME",
    "GENERATED_HEADER",
    "FhirProject",
    "FhirProjectConfig",
    "FhirValidationReport",
    "FshArtifact",
    "FshBuild",
    "GenerateAllReport",
    "GenerateConfig",
    "GenerateReport",
    "IgConfig",
    "InitOptions",
    "NamingConfig",
    "NoFhirProjectError",
    "OptionInput",
    "OptionSetInput",
    "OptionSetSelection",
    "OrgUnitInput",
    "OrgUnitSelection",
    "ScaffoldFile",
    "ScaffoldReport",
    "ValidationFinding",
    "build_code_validation",
    "build_option_set_artifacts",
    "build_org_unit_instances",
    "build_org_unit_level_terminology",
    "build_org_unit_profiles",
    "build_org_unit_terminology",
    "build_scaffold_files",
    "clean_generated_files",
    "find_project_fhir_config",
    "load_fhir_config",
    "load_project",
    "write_artifacts",
    "write_fhir_config",
]

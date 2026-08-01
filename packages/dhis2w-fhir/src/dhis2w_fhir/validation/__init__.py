"""FHIR-safety validation of DHIS2 metadata: are the instance's codes usable in FHIR?

Two passes share one finding shape:

- an instance-wide sweep over `/api/metadata?fields=id,name,code` - every
  metadata object's code checked against the R4 `code` datatype, duplicates
  flagged per collection;
- a deep option-set pass over the same projections the terminology emitter
  consumes, previewing exactly what `concept_code_source = "code"` generation
  would do. With `naming.source = "name"` it also previews which option-set
  names yield truncated or disambiguated ids (id-sourced ids never overflow).
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Literal

from dhis2w_fhir.i18n import TranslationIn, name_translations
from dhis2w_fhir.names import is_valid_fhir_code, kebab, pascal
from dhis2w_fhir.resources.option_sets import max_slug_length
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation.report import render_validation_markdown
from dhis2w_fhir.validation.schemas import FhirValidationReport, MetadataCollectionIn, ValidationFinding

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = ["build_code_validation", "render_validation_markdown"]

# R4 cnl-0: computational names should match [A-Z]([A-Za-z0-9_]){0,254} - 255 characters total.
_MAX_FHIR_NAME_LENGTH = 255

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}

#: Option-pass categories that only bite once generation actually reads DHIS2 codes.
_CODE_MODE_CATEGORIES = frozenset({"invalid-code", "missing-code", "duplicate-code"})

#: Appended to a downgraded option finding so the report says why it is only informational.
_UID_MODE_SUFFIX = " (informational in id mode; will matter when switching to code mode)"

#: The one collection where a missing code is a finding: every unit must carry both identifiers.
_CODE_REQUIRED_COLLECTION = "organisationUnits"


def build_code_validation(
    option_sets: list[OptionSetIn],
    collections: list[MetadataCollectionIn],
    config: GenerateConfig,
    code_source: Literal["id", "code"] | None = None,
) -> FhirValidationReport:
    """Run both validation passes; findings sort by severity, resource type, then name."""
    effective_source = code_source or config.concept_code_source
    findings: list[ValidationFinding] = []
    option_count = 0
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        option_count += len(option_set.options)
        findings.extend(_option_findings(option_set, effective_source, config.locales))
        findings.extend(_option_set_naming_findings(option_set, config))
    object_count = 0
    for collection in sorted(collections, key=lambda item: item.resource):
        object_count += len(collection.items)
        findings.extend(_collection_findings(collection))
    findings.sort(key=lambda finding: (_SEVERITY_RANK[finding.severity], finding.resource_type, finding.name))
    return FhirValidationReport(
        option_set_count=len(option_sets),
        option_count=option_count,
        resource_type_count=len(collections),
        object_count=object_count,
        findings=findings,
    )


def _collection_findings(collection: MetadataCollectionIn) -> list[ValidationFinding]:
    """Instance-wide sweep checks: invalid codes (error) and duplicate codes per collection (warning)."""
    findings: list[ValidationFinding] = []
    code_counts = Counter(item.code for item in collection.items if item.code is not None)
    for item in sorted(collection.items, key=lambda entry: entry.uid):
        name = item.name or item.uid
        if item.code is None:
            if collection.resource == _CODE_REQUIRED_COLLECTION:
                findings.append(
                    ValidationFinding(
                        severity="warning",
                        category="missing-code",
                        resource_type=collection.resource,
                        uid=item.uid,
                        name=name,
                        code=None,
                        message="organisation unit has no code; every unit should carry both the UID and a code "
                        "identifier; the code identifier currently falls back to the UID",
                    )
                )
            continue
        if not is_valid_fhir_code(item.code):
            findings.append(
                ValidationFinding(
                    severity="error",
                    category="invalid-code",
                    resource_type=collection.resource,
                    uid=item.uid,
                    name=name,
                    code=item.code,
                    message="code is not a valid FHIR code (whitespace at the edges or doubled inside)",
                )
            )
        elif code_counts[item.code] > 1:
            findings.append(
                ValidationFinding(
                    severity="warning",
                    category="duplicate-code",
                    resource_type=collection.resource,
                    uid=item.uid,
                    name=name,
                    code=item.code,
                    message=f"code appears on {code_counts[item.code]} objects of this type",
                )
            )
    return findings


def _option_set_naming_findings(option_set: OptionSetIn, config: GenerateConfig) -> list[ValidationFinding]:
    """Name-sourced naming checks - only meaningful when ids/names derive from names."""
    if config.naming.source != "name":
        return []
    findings: list[ValidationFinding] = []
    fsh_name = f"{config.naming.prefix}{config.naming.option_set}{pascal(option_set.name)}VS"
    if len(fsh_name) > _MAX_FHIR_NAME_LENGTH:
        findings.append(
            _set_finding(
                option_set,
                "warning",
                "long-fsh-name",
                "generated FSH name exceeds the 255-character R4 name constraint (cnl-0); shorten the option set "
                "name or the naming tokens",
                config.locales,
            )
        )
    if len(kebab(option_set.name)) > max_slug_length(config):
        findings.append(
            _set_finding(
                option_set,
                "info",
                "long-name",
                "name exceeds the FHIR id length; generated ids are truncated with the UID suffix",
                config.locales,
            )
        )
    return findings


def _option_findings(
    option_set: OptionSetIn, code_source: Literal["id", "code"], locales: list[str]
) -> list[ValidationFinding]:
    """Deep option checks: invalid, missing, spaced, and duplicated codes within one set.

    In id mode the code-shaped findings are downgraded to info: generation is not reading the
    DHIS2 codes yet, so they are a readiness signal for switching to code mode, not a defect.
    """
    findings = _raw_option_findings(option_set, locales)
    if code_source == "code":
        return findings
    return [_downgraded(finding) if finding.category in _CODE_MODE_CATEGORIES else finding for finding in findings]


def _downgraded(finding: ValidationFinding) -> ValidationFinding:
    """Re-issue one option finding as info, saying why it does not bite in id mode."""
    return finding.model_copy(update={"severity": "info", "message": finding.message + _UID_MODE_SUFFIX})


def _raw_option_findings(option_set: OptionSetIn, locales: list[str]) -> list[ValidationFinding]:
    """Deep option checks at their code-mode severities, before any id-mode downgrade."""
    findings: list[ValidationFinding] = []
    valid_codes = Counter(
        option.code for option in option_set.options if option.code is not None and is_valid_fhir_code(option.code)
    )
    for option in sorted(option_set.options, key=lambda item: item.uid):
        if option.code is None:
            findings.append(
                _option_finding(
                    option_set,
                    option,
                    "warning",
                    "missing-code",
                    "option has no code; code-source generation falls back to the UID",
                    locales,
                )
            )
            continue
        if not is_valid_fhir_code(option.code):
            findings.append(
                _option_finding(
                    option_set,
                    option,
                    "error",
                    "invalid-code",
                    "code is not a valid FHIR code (whitespace at the edges or doubled inside); "
                    "code-source generation falls back to the UID",
                    locales,
                )
            )
            continue
        if valid_codes[option.code] > 1:
            findings.append(
                _option_finding(
                    option_set,
                    option,
                    "error",
                    "duplicate-code",
                    f"code appears on more than one option in {option_set.name!r}; a CodeSystem cannot repeat "
                    "concept codes",
                    locales,
                )
            )
        if " " in option.code:
            findings.append(
                _option_finding(
                    option_set,
                    option,
                    "info",
                    "spaced-code",
                    'code contains spaces; FHIR-valid but emitted in the quoted #"..." form',
                    locales,
                )
            )
    return findings


def _translated_name(name: str, translations: list[TranslationIn], locales: list[str]) -> str:
    """Suffix a finding name with the subject's first configured name translation, when it has one."""
    selected = name_translations(translations, locales)
    return f"{name} / {selected[0].value}" if selected else name


def _set_finding(
    option_set: OptionSetIn, severity: str, category: str, message: str, locales: list[str]
) -> ValidationFinding:
    """Build one option-set-level finding."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category=category,
        resource_type="optionSets",
        uid=option_set.uid,
        name=_translated_name(option_set.name, option_set.translations, locales),
        code=option_set.code,
        message=message,
    )


def _option_finding(
    option_set: OptionSetIn,
    option: OptionIn,
    severity: str,
    category: str,
    message: str,
    locales: list[str],
) -> ValidationFinding:
    """Build one option-level finding, carrying the owning set in the name."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category=category,
        resource_type="options",
        uid=option.uid,
        name=_translated_name(f"{option.name} [in {option_set.name}]", option.translations, locales),
        code=option.code,
        message=message,
    )

"""FHIR-safety validation of DHIS2 metadata: are the instance's codes usable in FHIR?

Two passes share one finding shape:

- an instance-wide sweep over `/api/metadata?fields=id,name,code` - every
  metadata object's code checked against the R4 `code` datatype, duplicates
  flagged per collection;
- a deep option-set pass over the same projections the terminology emitter
  consumes, previewing exactly what `concept_code_source = "code"` generation
  would do. With `naming.source = "name"` it also previews which option-set
  names yield truncated or disambiguated ids (uid-sourced ids never overflow).
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from dhis2w_fhir.names import is_valid_fhir_code, kebab, pascal
from dhis2w_fhir.resources.option_sets import max_slug_length
from dhis2w_fhir.resources.option_sets.schemas import OptionSetIn
from dhis2w_fhir.validation.report import render_validation_markdown
from dhis2w_fhir.validation.schemas import FhirValidationReport, MetadataCollectionIn, ValidationFinding

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = ["build_code_validation", "render_validation_markdown"]

# R4 cnl-0: computational names should match [A-Z]([A-Za-z0-9_]){0,254} - 255 characters total.
_MAX_FHIR_NAME_LENGTH = 255

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def build_code_validation(
    option_sets: list[OptionSetIn],
    collections: list[MetadataCollectionIn],
    config: GenerateConfig,
) -> FhirValidationReport:
    """Run both validation passes; findings sort by severity, resource type, then name."""
    findings: list[ValidationFinding] = []
    option_count = 0
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        option_count += len(option_set.options)
        findings.extend(_option_findings(option_set))
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
        if item.code is None:
            continue
        name = item.name or item.uid
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
            )
        )
    if len(kebab(option_set.name)) > max_slug_length(config):
        findings.append(
            _set_finding(
                option_set,
                "info",
                "long-name",
                "name exceeds the FHIR id length; generated ids are truncated with the UID suffix",
            )
        )
    return findings


def _option_findings(option_set: OptionSetIn) -> list[ValidationFinding]:
    """Deep option checks: invalid, missing, spaced, and duplicated codes within one set."""
    findings: list[ValidationFinding] = []
    valid_codes = Counter(
        option.code for option in option_set.options if option.code is not None and is_valid_fhir_code(option.code)
    )
    for option in sorted(option_set.options, key=lambda item: item.uid):
        if option.code is None:
            findings.append(
                _option_finding(
                    option_set,
                    option.uid,
                    option.name,
                    None,
                    "warning",
                    "missing-code",
                    "option has no code; code-source generation falls back to the UID",
                )
            )
            continue
        if not is_valid_fhir_code(option.code):
            findings.append(
                _option_finding(
                    option_set,
                    option.uid,
                    option.name,
                    option.code,
                    "error",
                    "invalid-code",
                    "code is not a valid FHIR code (whitespace at the edges or doubled inside); "
                    "code-source generation falls back to the UID",
                )
            )
            continue
        if valid_codes[option.code] > 1:
            findings.append(
                _option_finding(
                    option_set,
                    option.uid,
                    option.name,
                    option.code,
                    "error",
                    "duplicate-code",
                    f"code appears on more than one option in {option_set.name!r}; a CodeSystem cannot repeat "
                    "concept codes",
                )
            )
        if " " in option.code:
            findings.append(
                _option_finding(
                    option_set,
                    option.uid,
                    option.name,
                    option.code,
                    "info",
                    "spaced-code",
                    'code contains spaces; FHIR-valid but emitted in the quoted #"..." form',
                )
            )
    return findings


def _set_finding(option_set: OptionSetIn, severity: str, category: str, message: str) -> ValidationFinding:
    """Build one option-set-level finding."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category=category,
        resource_type="optionSets",
        uid=option_set.uid,
        name=option_set.name,
        code=option_set.code,
        message=message,
    )


def _option_finding(
    option_set: OptionSetIn,
    option_uid: str,
    option_name: str,
    code: str | None,
    severity: str,
    category: str,
    message: str,
) -> ValidationFinding:
    """Build one option-level finding, carrying the owning set in the name."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category=category,
        resource_type="options",
        uid=option_uid,
        name=f"{option_name} [in {option_set.name}]",
        code=code,
        message=message,
    )

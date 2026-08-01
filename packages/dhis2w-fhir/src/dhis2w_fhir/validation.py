"""FHIR-safety validation of DHIS2 metadata: are the codes usable as FHIR concept codes?

Pure logic over the same option-set inputs the terminology emitter consumes,
so `d2w fhir validate` previews exactly what `concept_code_source = "code"`
generation would do: which codes are invalid (UID fallback), missing, or
duplicated, and which option-set names get truncated or disambiguated ids.
"""

from __future__ import annotations

from collections import Counter

from dhis2w_fhir.models import (
    FhirValidationReport,
    GenerateConfig,
    OptionSetInput,
    ValidationFinding,
)
from dhis2w_fhir.names import is_valid_fhir_code, kebab, pascal
from dhis2w_fhir.terminology import _max_slug_length

# R4 cnl-0: computational names should match [A-Z]([A-Za-z0-9_]){0,254} - 255 characters total.
_MAX_FHIR_NAME_LENGTH = 255


def build_code_validation(option_sets: list[OptionSetInput], config: GenerateConfig) -> FhirValidationReport:
    """Check every option set and option for FHIR-safety; findings are sorted by severity then subject."""
    findings: list[ValidationFinding] = []
    option_count = 0
    max_slug_length = _max_slug_length(config)
    slug_owners: dict[str, str] = {}
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        option_count += len(option_set.options)
        findings.extend(_option_findings(option_set))
        fsh_name = f"{config.naming.prefix}{config.naming.option_set}{pascal(option_set.name)}VS"
        if len(fsh_name) > _MAX_FHIR_NAME_LENGTH:
            findings.append(
                ValidationFinding(
                    severity="warning",
                    category="long-fsh-name",
                    option_set_uid=option_set.uid,
                    option_set_name=option_set.name,
                    message="generated FSH name exceeds the 255-character R4 name constraint (cnl-0); shorten the "
                    "option set name or the naming tokens",
                )
            )
        slug = kebab(option_set.name)
        if len(slug) > max_slug_length:
            findings.append(
                ValidationFinding(
                    severity="info",
                    category="long-name",
                    option_set_uid=option_set.uid,
                    option_set_name=option_set.name,
                    message="name exceeds the FHIR id length; generated ids are truncated with the UID suffix",
                )
            )
        elif slug in slug_owners:
            findings.append(
                ValidationFinding(
                    severity="info",
                    category="name-collision",
                    option_set_uid=option_set.uid,
                    option_set_name=option_set.name,
                    message=f"name collides with option set {slug_owners[slug]} after slugging; UID suffix applied",
                )
            )
        else:
            slug_owners[slug] = option_set.uid
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings.sort(
        key=lambda finding: (severity_rank[finding.severity], finding.option_set_name, finding.option_uid or "")
    )
    return FhirValidationReport(
        option_set_count=len(option_sets),
        option_count=option_count,
        findings=findings,
    )


def _option_findings(option_set: OptionSetInput) -> list[ValidationFinding]:
    """Per-option checks: invalid, missing, spaced, and duplicated codes within one set."""
    findings: list[ValidationFinding] = []
    valid_codes = Counter(
        option.code for option in option_set.options if option.code is not None and is_valid_fhir_code(option.code)
    )
    for option in sorted(option_set.options, key=lambda item: item.uid):
        if option.code is None:
            findings.append(
                _finding(
                    option_set,
                    option.uid,
                    None,
                    "warning",
                    "missing-code",
                    "option has no code; code-source generation falls back to the UID",
                )
            )
            continue
        if not is_valid_fhir_code(option.code):
            findings.append(
                _finding(
                    option_set,
                    option.uid,
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
                _finding(
                    option_set,
                    option.uid,
                    option.code,
                    "error",
                    "duplicate-code",
                    "code appears on more than one option in this set; a CodeSystem cannot repeat concept codes",
                )
            )
        if " " in option.code:
            findings.append(
                _finding(
                    option_set,
                    option.uid,
                    option.code,
                    "info",
                    "spaced-code",
                    'code contains spaces; FHIR-valid but emitted in the quoted #"..." form',
                )
            )
    return findings


def _finding(
    option_set: OptionSetInput,
    option_uid: str,
    code: str | None,
    severity: str,
    category: str,
    message: str,
) -> ValidationFinding:
    """Build one option-level finding."""
    return ValidationFinding(
        severity=severity,  # type: ignore[arg-type]
        category=category,
        option_set_uid=option_set.uid,
        option_set_name=option_set.name,
        option_uid=option_uid,
        code=code,
        message=message,
    )

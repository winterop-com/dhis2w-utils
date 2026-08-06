"""FHIR-safety validation of DHIS2 metadata: are the instance's codes usable in FHIR?

Three passes share one finding shape:

- an instance-wide sweep over `/api/metadata?fields=id,name,code` - every
  metadata object's code checked against the R4 `code` datatype, duplicates
  flagged per collection;
- a deep option-set pass over the same projections the terminology emitter
  consumes, previewing exactly what `concept_code_source = "code"` generation
  would do. With `naming.source = "name"` it also previews which option-set
  names yield truncated or disambiguated ids (id-sourced ids never overflow);
- a deep attribute pass over the sweep's own `attributes` collection, previewing
  which DHIS2 attributes emit a `D2AttributeValue` extension that carries no
  `attributeCode`.

Every pass also checks the object's NAME for the HTML-significant characters the IG
publisher's template injects unescaped (`template-hostile-name`). That check is about
the published pages rather than about codes, so it is a warning in either code source.
Its sibling `template-hostile-code` checks the object's CODE for the same characters
and is an error in either code source, because a code reaches the identifier table the
publisher writes raw and then strict-parses: that one aborts the build rather than
rendering a malformed page.

## What the deep passes do not repeat, and why

The deep passes cover what the sweep structurally cannot: the objects it excludes
(`options`), the peer-dependent outcomes it cannot compute (a concept code assigned
against its set, a slug assigned against its peers), and the emit-time decisions it
does not model (an attribute value's missing code). Everything else generation reads
is already covered instance-wide by the sweep, or is safe by construction:

- **Concept codes.** Option sets are the only terminology source that puts a DHIS2
  code in a concept-code slot, and only under `concept_code_source = "code"`. The
  data-element pair, the category-option-combo pair, the org-unit pair, and the
  org-unit level pair all code their concepts by DHIS2 UID (or by `level-<n>`),
  which is a valid R4 code and unique by construction; a DHIS2 code rides along as
  the `dhis2-code` concept property, which is a `string` and takes any value.
- **Names.** Every metadata collection the emitters read is a top-level collection
  of `/api/metadata` - `dataElements`, `categoryOptionCombos`, `dataSets`,
  `programs`, `sections`, `programStageSections`, `organisationUnits`, `attributes`
  - so the sweep already checks each object's `name`, the text that becomes a
  resource `title` / `name` and a concept `display`. The other DHIS2 text the
  emitters read (`formName`, `shortName`, `description`) lands in resource data
  elements rather than in the page furniture the publisher's template injects raw.
- **Generated ids.** Every emitted resource id is a DHIS2 UID except the
  option-set slug, which is the one name-sourced identity and is checked here.

The one source that is deliberately left to the sweep is the organisation-unit
registry. A deep pass over it would need the paged `_fetch_organisation_units` read
- the single unbounded read in the plugin - and would find nothing the sweep does
not already report: the registry's ids and concept codes are UIDs, its names and
codes are swept, and `organisationUnits` is the one collection where the sweep
already treats a missing code as a finding.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Literal

from dhis2w_fhir.foundation.attribute_values import (
    ATTRIBUTE_CODE_SUB_EXTENSION,
    ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES,
)
from dhis2w_fhir.i18n import TranslationIn, name_translations
from dhis2w_fhir.names import describe_code_defect, is_valid_fhir_code, kebab, pascal
from dhis2w_fhir.resources.option_sets import max_slug_length, option_set_fsh_name
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation.report import display_code, render_validation_markdown
from dhis2w_fhir.validation.schemas import (
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    ValidationFinding,
)

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

#: The sweep collection the deep attribute pass reads - the same objects `resolve_attribute_code_index`
#: builds the emit-time `uid -> code` join from, so the pass needs no request of its own.
_ATTRIBUTE_COLLECTION = "attributes"

#: The characters an object's NAME cannot carry, in the order they are reported. The IG publisher's
#: `fhir2.base.template` writes a resource's title into breadcrumbs and change-history headings
#: without escaping and then strict-parses the result, so one of these in a DHIS2 name yields a
#: malformed page. Generation escapes the page metadata it controls, but the resource's own
#: `title` / `name` elements stay byte-true DHIS2 data - which is the surface that stays broken.
_TEMPLATE_HOSTILE_CHARACTERS = ("<", ">", "&")

#: The swept collections whose objects emit a resource carrying the DHIS2 code as an identifier value -
#: option sets and categories on both halves of their CodeSystem/ValueSet pair, organisation units on both
#: their Organization and Location, data sets and event programs on their Questionnaire. Every other
#: collection either emits nothing or carries its code as a concept code or a `dhis2-code` property, both
#: of which the publisher escapes. A dashboard code holding '<' costs nothing, so it is not a finding.
_CODE_IDENTIFIER_COLLECTIONS = frozenset({"optionSets", "categories", "organisationUnits", "dataSets", "programs"})

#: The one hostile character observed to abort a build from an identifier value: it opens a tag, and the
#: publisher's strict parse of the page it just wrote fails on the malformed cell. '>' is text to an HTML
#: parser and a bare '&' is widely tolerated, so neither is claimed to be fatal without having seen it.
_BUILD_ABORTING_CHARACTER = "<"


def build_code_validation(
    option_sets: list[OptionSetIn],
    collections: list[MetadataCollectionIn],
    config: GenerateConfig,
    code_source: Literal["id", "code"] | None = None,
) -> FhirValidationReport:
    """Run all three validation passes; findings sort by severity, resource type, then name."""
    effective_source = code_source or config.concept_code_source
    findings: list[ValidationFinding] = []
    option_count = 0
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        option_count += len(option_set.options)
        findings.extend(_option_findings(option_set, effective_source, config.locales))
        findings.extend(_option_set_naming_findings(option_set, config))
        findings.extend(_template_hostile_option_findings(option_set, config.locales))
    findings.extend(_option_set_slug_findings(option_sets, config))
    object_count = 0
    for collection in sorted(collections, key=lambda item: item.resource):
        object_count += len(collection.items)
        findings.extend(_collection_findings(collection))
    attributes = _swept_attributes(collections)
    findings.extend(_attribute_findings(attributes))
    findings.sort(key=lambda finding: (_SEVERITY_RANK[finding.severity], finding.resource_type, finding.name))
    return FhirValidationReport(
        option_set_count=len(option_sets),
        option_count=option_count,
        attribute_count=len(attributes),
        resource_type_count=len(collections),
        object_count=object_count,
        findings=findings,
    )


def _swept_attributes(collections: list[MetadataCollectionIn]) -> list[MetadataItemIn]:
    """The DHIS2 attributes the sweep fetched - the deep attribute pass reads no further."""
    matching = [collection for collection in collections if collection.resource == _ATTRIBUTE_COLLECTION]
    return [item for collection in matching for item in collection.items]


def _attribute_findings(attributes: list[MetadataItemIn]) -> list[ValidationFinding]:
    """Deep attribute pass: which attributes emit a D2AttributeValue extension carrying no code.

    The emitter writes the `attributeCode` sub-extension only for an attribute the instance
    coded, so an uncoded one leaves every value it carries resolvable by DHIS2 UID alone. That
    is the emitted IG working as designed - most instances code few of their attributes - so it
    is informational: a coverage signal about how legible the extension is to a consumer who
    does not hold the DHIS2 instance, not a defect that breaks a build.
    """
    contexts = ", ".join(ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES)
    return [
        ValidationFinding(
            severity="info",
            category="missing-code",
            resource_type=_ATTRIBUTE_COLLECTION,
            uid=attribute.uid,
            name=attribute.name or attribute.uid,
            code=None,
            message=f"attribute has no code; every D2AttributeValue extension carrying it omits the "
            f"{ATTRIBUTE_CODE_SUB_EXTENSION} sub-extension, so a consumer resolves the value by the "
            f"attribute UID alone on {contexts}",
        )
        for attribute in sorted(attributes, key=lambda item: item.uid)
        if attribute.code is None
    ]


def _template_hostile_character(name: str) -> str | None:
    """The first HTML-significant character a name carries, or None when the name is safe."""
    return next((character for character in _TEMPLATE_HOSTILE_CHARACTERS if character in name), None)


def _template_hostile_message(name: str, character: str) -> str:
    """Say which character breaks the published pages, and what breaks, in the caller's own words."""
    return (
        f"name {display_code(name)} contains {character!r} which the IG publisher template injects into HTML "
        "unescaped; pages for this resource render malformed until the name is changed"
    )


def _template_hostile_finding(resource_type: str, uid: str, name: str, code: str | None) -> ValidationFinding | None:
    """Flag one object whose name carries a character the publisher's template cannot survive."""
    character = _template_hostile_character(name)
    if character is None:
        return None
    return ValidationFinding(
        severity="warning",
        category="template-hostile-name",
        resource_type=resource_type,
        uid=uid,
        name=name,
        code=code,
        message=_template_hostile_message(name, character),
    )


def _template_hostile_code_finding(
    resource_type: str, uid: str, name: str, code: str | None
) -> ValidationFinding | None:
    """Flag one object whose code reaches an identifier value, the one page surface written unescaped."""
    if resource_type not in _CODE_IDENTIFIER_COLLECTIONS:
        return None
    character = _template_hostile_character(code or "")
    if character is None:
        return None
    aborts = character == _BUILD_ABORTING_CHARACTER
    consequence = (
        "so `make build` aborts with \"Unable to Parse HTML - node 'td' has unexpected content\", and it "
        "aborts in the publisher's last pass, once every resource has already been rendered"
        if aborts
        else "so this code lands on a page surface the publisher does not escape; only '<' is confirmed to "
        "abort a build, which is why this is a warning and '<' is an error"
    )
    return ValidationFinding(
        severity="error" if aborts else "warning",
        category="template-hostile-code",
        resource_type=resource_type,
        uid=uid,
        name=name,
        code=code,
        message=f"code {display_code(code or '')} contains {character!r}; a {resource_type} code becomes an "
        f"identifier value, which the IG publisher writes into a table cell unescaped and then strict-parses, "
        f"{consequence}; change the code in DHIS2",
    )


def _template_hostile_option_findings(option_set: OptionSetIn, locales: list[str]) -> list[ValidationFinding]:
    """Flag the option names the sweep cannot see - options are excluded from it, and land in page tables."""
    findings: list[ValidationFinding] = []
    for option in sorted(option_set.options, key=lambda item: item.uid):
        character = _template_hostile_character(option.name)
        if character is None:
            continue
        findings.append(
            _option_finding(
                option_set,
                option,
                "warning",
                "template-hostile-name",
                _template_hostile_message(option.name, character),
                locales,
            )
        )
    return findings


def _collection_findings(collection: MetadataCollectionIn) -> list[ValidationFinding]:
    """Instance-wide sweep checks: invalid codes (error) and duplicate codes per collection (warning)."""
    findings: list[ValidationFinding] = []
    code_counts = Counter(item.code for item in collection.items if item.code is not None)
    for item in sorted(collection.items, key=lambda entry: entry.uid):
        name = item.name or item.uid
        hostile = _template_hostile_finding(collection.resource, item.uid, name, item.code)
        if hostile is not None:
            findings.append(hostile)
        hostile_code = _template_hostile_code_finding(collection.resource, item.uid, name, item.code)
        if hostile_code is not None:
            findings.append(hostile_code)
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
        defect = describe_code_defect(item.code)
        if defect is not None:
            findings.append(
                ValidationFinding(
                    severity="error",
                    category="invalid-code",
                    resource_type=collection.resource,
                    uid=item.uid,
                    name=name,
                    code=item.code,
                    message=f"code is not a valid FHIR code: {defect}",
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
    fsh_name = f"{option_set_fsh_name(config, pascal(option_set.name))}_VS"
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


def _option_set_slug_findings(option_sets: list[OptionSetIn], config: GenerateConfig) -> list[ValidationFinding]:
    """Name-sourced slug collisions - the half of the naming check that needs the whole selection.

    `option_set_identities` assigns a slug against its peers, so whether one name yields a
    readable id depends on the other names in the run. A per-set check cannot see that; this
    one groups the selection by slug and reports the names the emitter will disambiguate with
    a UID suffix. Over-long slugs are excluded: they take the suffix for their length, which
    `long-name` already reports, so a name would otherwise be flagged twice for one id.
    """
    if config.naming.source != "name":
        return []
    limit = max_slug_length(config)
    within_limit = [option_set for option_set in option_sets if len(kebab(option_set.name)) <= limit]
    slug_counts = Counter(kebab(option_set.name) for option_set in within_limit)
    return [
        _set_finding(
            option_set,
            "info",
            "duplicate-name",
            f"name slugs to {display_code(kebab(option_set.name))}, which "
            f"{slug_counts[kebab(option_set.name)]} option sets in the selection share; generated ids are "
            "disambiguated with the UID suffix, so they no longer read back to the name",
            config.locales,
        )
        for option_set in sorted(within_limit, key=lambda item: (item.name, item.uid))
        if slug_counts[kebab(option_set.name)] > 1
    ]


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
        defect = describe_code_defect(option.code)
        if defect is not None:
            findings.append(
                _option_finding(
                    option_set,
                    option,
                    "error",
                    "invalid-code",
                    f"code is not a valid FHIR code: {defect}; code-source generation falls back to the UID",
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

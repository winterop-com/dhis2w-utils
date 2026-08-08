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
the published pages rather than about codes, so its severity ignores the code source.
Its sibling `template-hostile-code` checks the object's CODE for the same characters,
because a code reaches the identifier table the publisher writes raw and then
strict-parses: an in-scope `<` there aborts the build rather than rendering a
malformed page, which is how it becomes the one error this module grades.

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

## Severity means build impact on the configured IG

Every pass grades against a `ValidationScope` - the UID sets the configured selection
emits, resolved with the same semantics `generate` uses:

- **error**: would abort the configured build - a build-aborting `<` code (the
  `build_aborting_code` predicate the generate gate shares) on an in-scope object of a
  code-identifier collection. Nothing else is an error.
- **warning**: degrades the IG but the build survives - an in-scope code falling back to
  the UID, an in-scope duplicate, an in-scope name or code malforming its page.
- **info**: the same defect on an out-of-scope object (instance hygiene - the
  code-migration watchlist), plus everything that was informational already.

Each finding carries the verdict as `scope`: `selection` for objects the build emits,
`instance` for the rest. With no scope resolved every finding is graded as selected,
which is the unit-test path - `validate_codes` always resolves a real scope.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Literal

from dhis2w_fhir.foundation.attribute_values import (
    ATTRIBUTE_CODE_SUB_EXTENSION,
    ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES,
)
from dhis2w_fhir.i18n import TranslationIn, name_translations
from dhis2w_fhir.names import describe_code_defect, is_valid_fhir_code, is_valid_fhir_id, kebab, pascal
from dhis2w_fhir.resources.option_sets import max_slug_length, option_set_fsh_name
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.validation.report import display_code, render_validation_markdown
from dhis2w_fhir.validation.schemas import (
    SCOPE_SURFACE_FIELDS,
    CodeCoverage,
    FhirValidationReport,
    MetadataCollectionIn,
    MetadataItemIn,
    SurfaceCodeCoverage,
    ValidationFinding,
    ValidationScope,
)

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "ValidationScope",
    "build_aborting_code",
    "build_code_validation",
    "render_validation_markdown",
    "usable_code_stem",
]

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
_CODE_IDENTIFIER_COLLECTIONS = frozenset(
    {"optionSets", "categories", "organisationUnits", "dataSets", "programs", "programStages"}
)

#: The one hostile character observed to abort a build from an identifier value: it opens a tag, and the
#: publisher's strict parse of the page it just wrote fails on the malformed cell. '>' is text to an HTML
#: parser and a bare '&' is widely tolerated, so neither is claimed to be fatal without having seen it.
_BUILD_ABORTING_CHARACTER = "<"


def build_aborting_code(code: str | None) -> bool:
    """Whether one DHIS2 code, emitted as an identifier value, aborts the IG publisher's final pass.

    The single source of truth shared by the validate finding and the generate-time refusal, so the
    two can never disagree about which code the publisher cannot survive.
    """
    return _BUILD_ABORTING_CHARACTER in (code or "")


def usable_code_stem(code: str | None) -> bool:
    """Whether a DHIS2 code could serve as an artifact stem - the bar the code-coverage probe counts against.

    Deliberately narrower than `describe_code_defect`, which grades against the R4 `code` datatype
    (single internal spaces allowed): a stem becomes a resource id and its canonical URL, so it
    takes the R4 `id` constraints - ASCII letters, digits, hyphen, dot, 1-64 characters - which
    exclude spaces and every build-aborting character a fortiori.
    """
    return code is not None and is_valid_fhir_id(code)


def build_code_validation(
    option_sets: list[OptionSetIn],
    collections: list[MetadataCollectionIn],
    config: GenerateConfig,
    code_source: Literal["id", "code"] | None = None,
    *,
    scope: ValidationScope | None = None,
) -> FhirValidationReport:
    """Run all three validation passes; findings sort by severity, resource type, then name.

    `scope` is the resolved emission scope severity grades against; with None every finding is
    graded as selected and no code coverage is computed - the offline path unit tests exercise,
    while `validate_codes` always resolves a real scope.
    """
    effective_source = code_source or config.concept_code_source
    findings: list[ValidationFinding] = []
    option_count = 0
    for option_set in sorted(option_sets, key=lambda item: (item.name, item.uid)):
        option_count += len(option_set.options)
        set_in_scope = _in_scope(scope, "optionSets", option_set.uid)
        findings.extend(_option_findings(option_set, effective_source, config.locales, in_scope=set_in_scope))
        findings.extend(_rescoped(finding, set_in_scope) for finding in _option_set_naming_findings(option_set, config))
        findings.extend(
            _rescoped(finding, set_in_scope)
            for finding in _template_hostile_option_findings(option_set, config.locales)
        )
    findings.extend(
        _rescoped(finding, _in_scope(scope, "optionSets", finding.uid))
        for finding in _option_set_slug_findings(option_sets, config)
    )
    object_count = 0
    for collection in sorted(collections, key=lambda item: item.resource):
        object_count += len(collection.items)
        findings.extend(_collection_findings(collection, scope))
    attributes = _swept_attributes(collections)
    findings.extend(_attribute_findings(attributes))
    findings.sort(key=lambda finding: (_SEVERITY_RANK[finding.severity], finding.resource_type, finding.name))
    return FhirValidationReport(
        option_set_count=len(option_sets),
        option_count=option_count,
        attribute_count=len(attributes),
        resource_type_count=len(collections),
        object_count=object_count,
        code_coverage=None if scope is None else _code_coverage(collections, scope),
        findings=findings,
    )


def _in_scope(scope: ValidationScope | None, resource_type: str, uid: str) -> bool:
    """Whether one object is on the build path; with no scope resolved everything is graded as selected."""
    return True if scope is None else scope.contains(resource_type, uid)


def _rescoped(finding: ValidationFinding, in_scope: bool) -> ValidationFinding:
    """Stamp one finding with its scope, degrading an out-of-scope defect to instance hygiene."""
    return finding.model_copy(
        update={"scope": _scope_label(in_scope), "severity": _degraded(finding.severity, in_scope)}
    )


def _scope_label(in_scope: bool) -> Literal["selection", "instance"]:
    """The scope one finding carries: on the build path or instance hygiene."""
    return "selection" if in_scope else "instance"


def _degraded(severity: Literal["error", "warning", "info"], in_scope: bool) -> Literal["error", "warning", "info"]:
    """The severity a defect really carries: its build-path grade in scope, info out of it."""
    return severity if in_scope else "info"


def _code_coverage(collections: list[MetadataCollectionIn], scope: ValidationScope) -> CodeCoverage:
    """Count per surface how many in-scope objects carry a usable stem code, off the sweep's own read.

    The migration probe of the naming-source roadmap entry: surfaces with no in-scope object are
    left out, so an unselected surface does not pad the rollup with a 0/0 row.
    """
    surfaces: list[SurfaceCodeCoverage] = []
    for collection in sorted(collections, key=lambda item: item.resource):
        if collection.resource not in SCOPE_SURFACE_FIELDS:
            continue
        in_scope_items = [item for item in collection.items if scope.contains(collection.resource, item.uid)]
        if not in_scope_items:
            continue
        surfaces.append(
            SurfaceCodeCoverage(
                surface=collection.resource,
                usable_count=sum(1 for item in in_scope_items if usable_code_stem(item.code)),
                object_count=len(in_scope_items),
            )
        )
    return CodeCoverage(surfaces=surfaces)


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

    The finding reads the same for a unique attribute, whose values are emitted as Identifiers
    rather than as extensions: that namespace is keyed on the attribute UID too, so an uncoded
    unique attribute is exactly as UID-bound as an uncoded annotating one.

    Scope stays `instance`: an attribute applies per-object across every emitted resource type, so
    there is no principled selection mapping for it - the simple, honest reading is instance-wide.
    """
    contexts = ", ".join(ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES)
    return [
        ValidationFinding(
            severity="info",
            scope="instance",
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
    resource_type: str, uid: str, name: str, code: str | None, *, in_scope: bool
) -> ValidationFinding | None:
    """Flag one object whose code reaches an identifier value, the one page surface written unescaped.

    Only an in-scope `<` code is an error - the configured build really dies on it. Out of scope
    the same code is instance hygiene, but the message keeps saying what it would do to a build
    the moment the object were selected.
    """
    if resource_type not in _CODE_IDENTIFIER_COLLECTIONS:
        return None
    character = _template_hostile_character(code or "")
    if character is None:
        return None
    aborts = build_aborting_code(code)
    if aborts and in_scope:
        consequence = (
            "so `make build` aborts with \"Unable to Parse HTML - node 'td' has unexpected content\", and it "
            "aborts in the publisher's last pass, once every resource has already been rendered"
        )
    elif aborts:
        consequence = (
            "the configured selection never emits this object, so no build reads the code today, but it "
            "aborts `make build` the moment the object is selected"
        )
    else:
        consequence = (
            "so this code lands on a page surface the publisher does not escape; only '<' is confirmed to "
            "abort a build, which is why only '<' can be an error"
        )
    return ValidationFinding(
        severity=_degraded("error" if aborts else "warning", in_scope),
        scope=_scope_label(in_scope),
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


def _collection_findings(collection: MetadataCollectionIn, scope: ValidationScope | None) -> list[ValidationFinding]:
    """Instance-wide sweep checks: names, codes, and per-collection duplicates, graded by build impact.

    An in-scope defect is a warning - the build survives, degraded (the one exception is the
    build-aborting `<` code, which `_template_hostile_code_finding` grades error). The same
    defect out of scope is info: instance hygiene the configured build never reads.
    """
    findings: list[ValidationFinding] = []
    code_counts = Counter(item.code for item in collection.items if item.code is not None)
    for item in sorted(collection.items, key=lambda entry: entry.uid):
        name = item.name or item.uid
        in_scope = _in_scope(scope, collection.resource, item.uid)
        hostile = _template_hostile_finding(collection.resource, item.uid, name, item.code)
        if hostile is not None:
            findings.append(_rescoped(hostile, in_scope))
        hostile_code = _template_hostile_code_finding(collection.resource, item.uid, name, item.code, in_scope=in_scope)
        if hostile_code is not None:
            findings.append(hostile_code)
        if item.code is None:
            if collection.resource == _CODE_REQUIRED_COLLECTION:
                findings.append(
                    ValidationFinding(
                        severity=_degraded("warning", in_scope),
                        scope=_scope_label(in_scope),
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
                    severity=_degraded("warning", in_scope),
                    scope=_scope_label(in_scope),
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
                    severity=_degraded("warning", in_scope),
                    scope=_scope_label(in_scope),
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
    option_set: OptionSetIn, code_source: Literal["id", "code"], locales: list[str], *, in_scope: bool
) -> list[ValidationFinding]:
    """Deep option checks: invalid, missing, spaced, and duplicated codes within one set.

    In id mode the code-shaped findings are downgraded to info: generation is not reading the
    DHIS2 codes yet, so they are a readiness signal for switching to code mode, not a defect.
    Every finding then follows its owning set's scope - an option of an unselected set is
    instance hygiene whatever mode the run is in.
    """
    findings = _raw_option_findings(option_set, locales)
    if code_source != "code":
        findings = [
            _downgraded(finding) if finding.category in _CODE_MODE_CATEGORIES else finding for finding in findings
        ]
    return [_rescoped(finding, in_scope) for finding in findings]


def _downgraded(finding: ValidationFinding) -> ValidationFinding:
    """Re-issue one option finding as info, saying why it does not bite in id mode."""
    return finding.model_copy(update={"severity": "info", "message": finding.message + _UID_MODE_SUFFIX})


def _raw_option_findings(option_set: OptionSetIn, locales: list[str]) -> list[ValidationFinding]:
    """Deep option checks at their code-mode, in-scope severities, before any downgrade.

    None of these grade error: an option code lands in a concept-code slot rather than in an
    identifier value, so the worst it does is fall back to the UID or force disambiguation -
    the build survives, degraded.
    """
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
                    "warning",
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
                    "warning",
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

"""FHIR-safety validation of DHIS2 metadata: are the instance's codes usable in FHIR?

Four passes share one finding shape:

- an instance-wide sweep over `/api/metadata?fields=id,name,code` - every
  metadata object's code checked against the R4 `code` datatype, duplicates
  flagged per collection;
- a deep option-set pass over the same projections the terminology emitter
  consumes, previewing exactly what `concept_code_source = "code"` generation
  would do;
- a code-stem pass over the sweep's naming surfaces, previewing exactly what a
  code-sourced `[generate.naming] source` does with each in-scope object: with
  `"code-or-id"` a missing, unusable, or colliding code silently falls back to
  the id (`code-stem-fallback`, warning), and with `"code"` the same object is
  what generate refuses (`code-stem-refusal`, error - the severity parity the
  build-aborting gate keeps: a validate error is a generate refusal);
- a deep attribute pass over the sweep's own `attributes` collection, previewing
  which DHIS2 attributes emit a `D2AttributeValue` extension that carries no
  `attributeCode`.

Every pass also checks the object's NAME for the HTML-significant characters the IG
publisher's template injects unescaped (`template-hostile-name`). That check is about
the published pages rather than about codes, so its severity ignores the code source.
Its sibling `template-hostile-code` checks the object's CODE for the same characters,
because a code reaches the identifier table the publisher writes raw and then
strict-parses. Both grade `<` as an error and the other two characters as warnings,
for the same reason: `<` opens a tag, so the publisher's re-parse of the page it just
wrote fails and `make build` exits non-zero, while `>` and `&` cost a malformed page
the build survives.

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
- **Generated ids.** Under `source = "id"` every emitted resource id is a DHIS2
  UID (or `level-<n>`), valid and unique by construction; under the code sources
  the code-stem pass checks the codes the ids would derive from.

The one source that is deliberately left to the sweep is the organisation-unit
registry. A deep pass over it would need the paged `_fetch_organisation_units` read
- the single unbounded read in the plugin - and would find nothing the sweep does
not already report: the registry's ids and concept codes are UIDs, its names and
codes are swept, and `organisationUnits` is the one collection where the sweep
already treats a missing code as a finding.

## Severity means build impact on the configured IG

Every pass grades against a `ValidationScope` - the UID sets the configured selection
emits, resolved with the same semantics `generate` uses:

- **error**: would abort the configured build - an in-scope `<`, either in the code of a
  code-identifier collection (the `build_aborting_code` predicate the generate gate shares)
  or in any swept object's name. Both reach a page surface the publisher writes unescaped
  and then strict-parses, and both take the build down with them.

  The name half of that grade holds in both directions, which is the property `d2w fhir
  generate` is gated to keep: every name graded a selection-scoped error here refuses a
  generate run, and every name a generate run refuses is graded a selection-scoped error
  here. That is why `SCOPE_SURFACE_FIELDS` names one surface per object kind the gate reads -
  category options, tracked entity types, and tracked entity attributes included - rather than
  only the kinds whose codes become artifact identities.
- **warning**: degrades the IG but the build survives - an in-scope code falling back to
  the UID, an in-scope duplicate, an in-scope `>` or `&` malforming a page.
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
from dhis2w_fhir.names import (
    FHIR_ID_MAX_LENGTH,
    StemSubject,
    describe_code_defect,
    describe_stem_defect,
    is_valid_fhir_code,
    usable_code_stem,
)
from dhis2w_fhir.resources.categories import max_category_slug_length
from dhis2w_fhir.resources.option_sets import max_slug_length
from dhis2w_fhir.resources.option_sets.schemas import OptionIn, OptionSetIn
from dhis2w_fhir.resources.questionnaires.schemas import QUESTIONNAIRE_STEM_SURFACE, TRACKER_PROGRAM_STEM_SURFACE
from dhis2w_fhir.validation.report import display_code, render_validation_markdown
from dhis2w_fhir.validation.schemas import (
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
    "build_aborting_name",
    "build_code_validation",
    "render_validation_markdown",
    "usable_code_stem",
]

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}

#: How the code-stem pass names one object of each naming surface - the sweep collections whose
#: in-scope objects take their artifact ids, canonicals, file names, and FSH names from the
#: identity stem a code-sourced `[generate.naming] source` reads off the DHIS2 code. `dataElements`
#: is deliberately absent: a data element is a concept inside the support terminology, not an
#: artifact of its own, so no stem is ever read from its code.
_STEM_SURFACE_LABELS: dict[str, str] = {
    "optionSets": "option set",
    "categories": "category",
    "organisationUnits": "organisation unit",
    "dataSets": "data set",
    "programs": "program",
    "programStages": "program stage",
}

#: The surfaces the code-migration probe counts: the ones whose objects take an artifact identity from
#: their DHIS2 code, plus `dataElements`, whose codes become the concept codes of the data dictionary.
#: The rest of `SCOPE_SURFACE_FIELDS` is there to grade names by build impact rather than to be counted -
#: a category option, a tracked entity type, and a tracked entity attribute all read their identity from
#: the object that publishes them, so a fraction over them would answer a question nobody asks.
_COVERAGE_SURFACES = frozenset(
    {"optionSets", "categories", "organisationUnits", "dataSets", "programs", "programStages", "dataElements"}
)

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


def build_aborting_name(name: str | None) -> bool:
    """Whether one DHIS2 name, kept byte-true on the emitted resource, aborts the IG publisher's build.

    A name lands on the resource's own `title` / `name` elements, which generation deliberately does
    not escape, and the publisher writes them into pages it strict-parses after writing. The single
    source of truth shared by the `template-hostile-name` error grade and the generate-time refusal.
    """
    return _BUILD_ABORTING_CHARACTER in (name or "")


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
        findings.extend(
            _rescoped(finding, set_in_scope)
            for finding in _template_hostile_option_findings(option_set, config.locales)
        )
    findings.extend(_stem_findings(collections, config, scope))
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
    """Count per surface how many in-scope objects carry a code that can serve as an identity stem.

    The probe a `source = "code"` migration watches: the fraction is the selection that would
    keep its code as the stem, and its complement is what `code-or-id` falls back on. Surfaces
    with no in-scope object are left out, so an unselected surface does not pad the rollup with
    a 0/0 row.
    """
    surfaces: list[SurfaceCodeCoverage] = []
    for collection in sorted(collections, key=lambda item: item.resource):
        if collection.resource not in _COVERAGE_SURFACES:
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
    """Say which character breaks the build or the published pages, and what breaks, in the caller's own words."""
    consequence = (
        "so `make build` fails: the publisher strict-parses the page it just wrote and cannot read it back"
        if character == _BUILD_ABORTING_CHARACTER
        else "so pages for this resource render malformed"
    )
    return (
        f"name {display_code(name)} contains {character!r} which the IG publisher template injects into HTML "
        f"unescaped, {consequence}; change the name in DHIS2"
    )


def _template_hostile_severity(character: str) -> Literal["error", "warning"]:
    """The grade a hostile character carries in a name: build-blocking for '<', degrading for the rest.

    '<' opens a tag, so the publisher's re-parse of its own output fails and the build exits non-zero -
    which is what `error` means here. '>' is text to an HTML parser and a bare '&' is widely tolerated,
    so those cost a malformed page and the build survives them.
    """
    return "error" if character == _BUILD_ABORTING_CHARACTER else "warning"


def _template_hostile_finding(resource_type: str, uid: str, name: str, code: str | None) -> ValidationFinding | None:
    """Flag one object whose name carries a character the publisher's template cannot survive."""
    character = _template_hostile_character(name)
    if character is None:
        return None
    return ValidationFinding(
        severity=_template_hostile_severity(character),
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
                _template_hostile_severity(character),
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


def _stem_budgets(config: GenerateConfig) -> dict[str, int | None]:
    """Per naming surface, the stem budget its artifact ids leave.

    The budgets are the very numbers the emitters bound their stems against, so validate and
    generate can never disagree about which code is too long for a surface. Option-set and
    category ids wrap the stem in naming tokens and suffixes, so those surfaces state what the
    tokens leave; an organisation unit, a data set, a program, and a program stage take the bare
    stem as the whole resource id (or directory name), so their budget is the R4 id limit itself.
    """
    return {
        "optionSets": max_slug_length(config),
        "categories": max_category_slug_length(config),
        "organisationUnits": FHIR_ID_MAX_LENGTH,
        "dataSets": FHIR_ID_MAX_LENGTH,
        "programs": FHIR_ID_MAX_LENGTH,
        "programStages": FHIR_ID_MAX_LENGTH,
    }


def _stem_findings(
    collections: list[MetadataCollectionIn], config: GenerateConfig, scope: ValidationScope | None
) -> list[ValidationFinding]:
    """Code-stem pass: which in-scope objects cannot take their DHIS2 code as the identity stem.

    Runs only under the code-sourced `[generate.naming] source` values, over the in-scope
    objects of each naming surface - a stem is assigned per run over the selection, so an
    out-of-scope code is never a stem and stays with the sweep's generic hygiene findings.
    The defect predicate is `describe_stem_defect`, the same one `resolve_identity_stems`
    decides fall-backs and refusals with, which is what keeps the severities honest: with
    `"code-or-id"` each finding is the warning that this object's artifact ids silently fall
    back to the id, and with `"code"` it is the error that `d2w fhir generate` refuses the run.
    """
    if config.naming.source == "id":
        return []
    budgets = _stem_budgets(config)
    findings: list[ValidationFinding] = []
    for resources, surface_label in _stem_namespaces(collections, scope):
        subjects_by_resource = {
            resource: [
                StemSubject(uid=item.uid, code=item.code, label=item.name or item.uid)
                for item in collection.items
                if _in_scope(scope, resource, item.uid)
            ]
            for resource, collection in resources.items()
        }
        pooled = [subject for subjects in subjects_by_resource.values() for subject in subjects]
        peer_uids = frozenset(subject.uid for subject in pooled)
        peer_code_counts = Counter(
            subject.code for subject in pooled if subject.code is not None and usable_code_stem(subject.code)
        )
        for resource in sorted(subjects_by_resource):
            for subject in sorted(subjects_by_resource[resource], key=lambda entry: entry.uid):
                defect = describe_stem_defect(subject, peer_code_counts, peer_uids, surface_label, budgets[resource])
                if defect is None:
                    continue
                findings.append(_stem_finding(resource, subject, defect, config.naming.source))
    return findings


def _stem_namespaces(
    collections: list[MetadataCollectionIn], scope: ValidationScope | None
) -> list[tuple[dict[str, MetadataCollectionIn], str]]:
    """Group the naming surfaces into the id namespaces generate resolves stems over.

    Option sets, categories, and organisation units each name their own artifacts, so each is
    its own namespace. The questionnaire targets pool: a data set, an event program, and a
    tracker program stage all become `Questionnaire-<stem>` resources, so their codes collide
    across collections exactly as `plan_questionnaire_stems` scans them. A tracker program's
    stem only names its stage directory - a namespace of its own. Without a resolved scope the
    tracker split is unknown, so every program rides the questionnaire pool; the offline
    grading path already treats everything as selected, and over-pooling there can only
    surface a collision one namespace sooner than the live run would.
    """
    by_resource = {collection.resource: collection for collection in collections}
    solo_surfaces = ("optionSets", "categories", "organisationUnits")
    namespaces = [
        ({resource: by_resource[resource]}, _STEM_SURFACE_LABELS[resource])
        for resource in solo_surfaces
        if resource in by_resource
    ]
    programs = by_resource.get("programs")
    tracker_uids = scope.tracker_programs if scope is not None else frozenset()
    event_items = [item for item in programs.items if item.uid not in tracker_uids] if programs else []
    tracker_items = [item for item in programs.items if item.uid in tracker_uids] if programs else []
    pool: dict[str, MetadataCollectionIn] = {}
    for resource in ("dataSets", "programStages"):
        if resource in by_resource:
            pool[resource] = by_resource[resource]
    if programs is not None:
        pool["programs"] = programs.model_copy(update={"items": event_items})
    if pool:
        namespaces.append((pool, QUESTIONNAIRE_STEM_SURFACE))
    if programs is not None and tracker_items:
        namespaces.append(
            ({"programs": programs.model_copy(update={"items": tracker_items})}, TRACKER_PROGRAM_STEM_SURFACE)
        )
    return namespaces


def _stem_finding(resource_type: str, subject: StemSubject, defect: str, source: str) -> ValidationFinding:
    """One code-stem finding, graded by what the configured source does with the defective code."""
    if source == "code":
        return ValidationFinding(
            severity="error",
            scope="selection",
            category="code-stem-refusal",
            resource_type=resource_type,
            uid=subject.uid,
            name=subject.label,
            code=subject.code,
            message=f'{defect}; `d2w fhir generate` refuses the run under [generate.naming] source = "code" '
            "until the code is fixed in DHIS2",
        )
    return ValidationFinding(
        severity="warning",
        scope="selection",
        category="code-stem-fallback",
        resource_type=resource_type,
        uid=subject.uid,
        name=subject.label,
        code=subject.code,
        message=f'{defect}; [generate.naming] source = "code-or-id" falls back to the id for this object\'s '
        "artifact ids, canonical URLs, file names, and FSH names",
    )


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

"""What is not right about the DHIS2 metadata behind this run: the validate findings, plus translation coverage.

TWO ANALYSES, ONE ANSWER. The first is `d2w fhir validate` run over the connection this process
already holds - the same passes, the same graders, the same severity grading, and the same wording,
because a finding a reader acts on must not be phrased one way in a terminal and another way in a
browser. `dhis2w_fhir.service.validate_instance_codes` is the whole of it, and nothing here
re-implements a predicate that lives there.

The second is new here: how much of the selection is translated. DHIS2 holds a translation per
object, per property, per locale, and nothing in a published guide states which locales an instance
is being maintained in - so the answer is read off the objects themselves. The locales in use are
the union of the tags the selection's own translations carry, which needs no system-settings read
and is honest on an instance nobody has configured: an instance with one Lao translation is being
maintained in Lao, whatever a settings page says. Against that set, an object is short a NAME
translation, and short a FORM_NAME translation wherever DHIS2 gives it a form name to translate.

READ ONCE PER RESOURCE KIND. The translation read is one request per scope surface - ten of them -
rather than one per object, and the selection is applied to what comes back rather than written into
a filter that would put a national instance's organisation-unit UIDs into a query string.

REPORTING ONLY. Nothing here writes to DHIS2, and nothing here offers to. Acting on a finding -
changing the name, the code, or the translation in the instance - is the next slice, and the
roadmap is where it is stated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from dhis2w_fhir.i18n import FORM_NAME_PROPERTY, NAME_PROPERTY, normalize_locale
from dhis2w_fhir.service import resolve_validation_scope, validate_instance_codes
from dhis2w_fhir.validation.schemas import SCOPE_SURFACE_FIELDS
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dhis2w_client import Dhis2Client
    from dhis2w_fhir.config import GenerateConfig
    from dhis2w_fhir.validation.schemas import ValidationFinding, ValidationScope

#: What a compiled run answers, in the words a first-time reader can act on. A compiled guide is a
#: directory of resources with no instance behind it, so there is no metadata to grade - and saying
#: "not supported" would leave somebody looking for a setting that does not exist.
COMPILED_RUN_REASON = (
    "This server is reading a compiled implementation guide from disk, so there is no DHIS2 instance "
    "behind it to check. Start the server with --live to read the instance this guide was generated "
    "from."
)

#: The DHIS2 field each finding category is about, so a row says which spelling to go and change.
#: `template-hostile-name` is the one category that can be about either of two fields, and
#: `_FIELD_LABELS_BY_MESSAGE_PREFIX` is what tells them apart.
FIELD_BY_CATEGORY: dict[str, str] = {
    "template-hostile-name": "name",
    "template-hostile-code": "code",
    "invalid-code": "code",
    "missing-code": "code",
    "duplicate-code": "code",
    "code-stem-refusal": "code",
    "code-stem-fallback": "code",
    "unmapped-tracked-entity-type": "tracked entity type mapping",
}

#: The field labels `d2w fhir validate` opens a name finding's message with, longest first.
#:
#: A data element and a tracked entity attribute each carry two spellings DHIS2 puts on a page - the
#: name every vocabulary displays, and the form name a question is asked under - and both are graded
#: under one category, because they cost the same build. Which of the two a finding is about is
#: stated at the head of its own message, which is where this reads it: `test_metadata_health.py`
#: pins the pair against a real run, so a wording change in the validator is a failing test here
#: rather than a column that quietly says the wrong field.
_FIELD_LABELS_BY_MESSAGE_PREFIX = ("form name", "name")

#: What each severity costs the project, in the terms `d2w fhir validate` grades by.
_COST_BY_SEVERITY: dict[str, str] = {
    "error": "The implementation guide build stops on this.",
    "warning": "The build finishes, and what it publishes for this object is degraded.",
    "info": "The build finishes, and publishes this object as it stands.",
}

#: What an out-of-scope finding costs, which is nothing: this project publishes nothing from the object.
_INSTANCE_SCOPE_COST = "This object is outside what this project publishes, so no build of it reads the object."

#: The fields one translation read asks for. `formName` rides along on every surface: DHIS2 answers
#: it on the two collections that have one and omits it everywhere else, exactly as it does for the
#: instance-wide sweep `d2w fhir validate` reads through.
_TRANSLATION_FIELDS = "id,name,formName,translations[locale,property,value]"


class MetadataHealthFinding(BaseModel):
    """One thing `d2w fhir validate` found about a DHIS2 object, as a row states it.

    Every field but `field` and `cost` is the validator's own, carried across unchanged - the
    severity it graded, the scope it graded against, and the sentence it wrote. The two that are
    added here are derived from those: which DHIS2 field the finding is about, and what the grade
    costs this project.
    """

    model_config = ConfigDict(frozen=True)

    severity: Literal["error", "warning", "info"]
    scope: Literal["selection", "instance"]
    category: str
    """The validator's own name for the kind of defect - `invalid-code`, `template-hostile-name`."""

    resource_type: str
    """The DHIS2 metadata collection the object belongs to, in DHIS2's own spelling."""

    uid: str
    name: str
    code: str | None = None
    field: str | None = None
    """The DHIS2 field at fault, or None where the category is about none of an object's own fields."""

    message: str
    """The exact problem, in the validator's own words - the same sentence the report file carries."""

    cost: str
    """What this grade costs the project, said in one sentence rather than as a severity word."""


class MetadataHealthCounts(BaseModel):
    """How many findings there are of each severity, over the whole answer."""

    model_config = ConfigDict(frozen=True)

    errors: int = 0
    warnings: int = 0
    infos: int = 0


class LocaleCoverage(BaseModel):
    """How much of the selection one locale covers: names translated, and form names translated."""

    model_config = ConfigDict(frozen=True)

    locale: str
    """The BCP-47 tag, normalised from the Java locale DHIS2 stores - `pt_BR` reaches here as `pt-BR`."""

    name_count: int = 0
    """Selected objects carrying a NAME translation in this locale."""

    form_name_count: int = 0
    """Selected objects that have a DHIS2 form name and carry a FORM_NAME translation in this locale."""


class TranslationGap(BaseModel):
    """One selected object, and the locales in use it holds no translation for."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    uid: str
    name: str
    missing_name_locales: list[str] = Field(default_factory=list)
    missing_form_name_locales: list[str] = Field(default_factory=list)
    """Stated only for an object DHIS2 gives a form name - everything else has no form name to translate."""


class TranslationCoverage(BaseModel):
    """How far the selection is translated, per locale and per object.

    `locales` is the union of the tags the selection's own translations carry, which is what "in use
    on this instance" means here: an instance is being maintained in the languages somebody has
    written into it, and no system setting states that more honestly than the objects do. An empty
    list is an instance nobody has translated, in which case there are no gaps either - a gap is a
    locale another object already has and this one does not.
    """

    model_config = ConfigDict(frozen=True)

    locales: list[str] = Field(default_factory=list)
    object_count: int = 0
    """Selected objects the translation read covered."""

    form_named_count: int = 0
    """Of those, how many DHIS2 gives a form name - the denominator the form-name counts are read against."""

    per_locale: list[LocaleCoverage] = Field(default_factory=list)
    gaps: list[TranslationGap] = Field(default_factory=list)
    """One entry per selected object short of a translation, in resource type then name order."""


class MetadataHealth(BaseModel):
    """The whole answer: whether this run could look, what it found, and how far the selection is translated.

    `available` false is a compiled run and nothing else. It is answered as a body rather than as a
    refusal because it is a state a screen renders in words - there is nothing wrong with serving a
    compiled guide, and a page that read a 4xx here would have to invent the sentence this carries.
    """

    model_config = ConfigDict(frozen=True)

    available: bool = True
    reason: str | None = None
    """Why there is nothing to report, stated only when `available` is false."""

    graded_under: str | None = None
    """The `[generate] hostile_names` posture the severities were graded under, in the validator's own line."""

    object_count: int = 0
    """Metadata objects the validator swept, across every collection the instance holds."""

    counts: MetadataHealthCounts = Field(default_factory=MetadataHealthCounts)
    findings: list[MetadataHealthFinding] = Field(default_factory=list)
    translations: TranslationCoverage = Field(default_factory=TranslationCoverage)


class TranslatedObject(BaseModel):
    """One selected DHIS2 object as the translation read projects it - what it is called, and in what locales.

    The step between the wire and the coverage: `read_selected_translations` builds these off what
    DHIS2 answered, and `translation_coverage` is a pure function over them, so the arithmetic every
    number on the page is made of is testable without a request.
    """

    model_config = ConfigDict(frozen=True)

    resource_type: str
    uid: str
    name: str
    form_named: bool
    """Whether DHIS2 gives this object a form name - so whether it has one to be short a translation of."""

    name_locales: frozenset[str]
    """The normalised tags this object holds a NAME translation in."""

    form_name_locales: frozenset[str]
    """The normalised tags this object holds a FORM_NAME translation in, empty where it has no form name."""


def compiled_run_health() -> MetadataHealth:
    """What a run serving a compiled guide answers: nothing found, and the reason there is nothing."""
    return MetadataHealth(available=False, reason=COMPILED_RUN_REASON)


async def read_metadata_health(client: Dhis2Client, config: GenerateConfig) -> MetadataHealth:
    """Grade the instance behind this run: the validate findings over the selection, and its translations.

    The selection is resolved once and read by both halves - the validator grades severity against
    it, and the translation read narrows to it - so a national instance is scoped by one set of
    small reads rather than by two.
    """
    scope = await resolve_validation_scope(client, config)
    report = await validate_instance_codes(client, config, scope=scope)
    objects = await read_selected_translations(client, scope)
    return MetadataHealth(
        graded_under=report.hostile_names_line,
        object_count=report.object_count,
        counts=MetadataHealthCounts(errors=report.error_count, warnings=report.warning_count, infos=report.info_count),
        findings=[health_finding(finding) for finding in report.findings],
        translations=translation_coverage(objects),
    )


def health_finding(finding: ValidationFinding) -> MetadataHealthFinding:
    """One validate finding as a row states it: its own grade and wording, plus the field and the cost."""
    return MetadataHealthFinding(
        severity=finding.severity,
        scope=finding.scope,
        category=finding.category,
        resource_type=finding.resource_type,
        uid=finding.uid,
        name=finding.name,
        code=finding.code,
        field=field_at_fault(finding),
        message=finding.message,
        cost=cost_of(finding),
    )


def field_at_fault(finding: ValidationFinding) -> str | None:
    """Which DHIS2 field one finding is about, or None where the category is about no field of the object."""
    if finding.category == "template-hostile-name":
        return next(
            (label for label in _FIELD_LABELS_BY_MESSAGE_PREFIX if finding.message.startswith(f"{label} ")),
            "name",
        )
    return FIELD_BY_CATEGORY.get(finding.category)


def cost_of(finding: ValidationFinding) -> str:
    """What one finding's grade costs this project, in a sentence rather than in a severity word."""
    if finding.scope == "instance":
        return _INSTANCE_SCOPE_COST
    return _COST_BY_SEVERITY[finding.severity]


async def read_selected_translations(client: Dhis2Client, scope: ValidationScope) -> list[TranslatedObject]:
    """Read the translations the selection's objects carry, one bounded request per resource kind.

    Every collection a `ValidationScope` answers for is read whole and then narrowed to the scope,
    rather than filtered by a `id:in:[...]` a national organisation-unit selection would blow the
    query string with. A collection the selection holds nothing of costs no request at all.
    """
    objects: list[TranslatedObject] = []
    for resource_type in sorted(SCOPE_SURFACE_FIELDS):
        surface: frozenset[str] = getattr(scope, SCOPE_SURFACE_FIELDS[resource_type])
        if not surface:
            continue
        body = await client.get_raw(f"/api/{resource_type}", params={"fields": _TRANSLATION_FIELDS, "paging": "false"})
        objects.extend(_translated_objects(resource_type, body, surface))
    return objects


def translation_coverage(objects: list[TranslatedObject]) -> TranslationCoverage:
    """How far the selection is translated: the locales in use, the counts per locale, and every gap.

    "In use" is the union of the tags these objects carry, so an instance nobody has translated has
    no locales, no coverage rows, and no gaps - which is the honest reading of an instance in one
    language rather than a page full of everything being missing.
    """
    locales = sorted({locale for item in objects for locale in item.name_locales | item.form_name_locales})
    if not locales:
        return TranslationCoverage(object_count=len(objects), form_named_count=_form_named(objects))
    return TranslationCoverage(
        locales=locales,
        object_count=len(objects),
        form_named_count=_form_named(objects),
        per_locale=[
            LocaleCoverage(
                locale=locale,
                name_count=sum(1 for item in objects if locale in item.name_locales),
                form_name_count=sum(1 for item in objects if item.form_named and locale in item.form_name_locales),
            )
            for locale in locales
        ],
        gaps=sorted(
            (gap for gap in (_gap(item, locales) for item in objects) if gap is not None),
            key=lambda gap: (gap.resource_type, gap.name, gap.uid),
        ),
    )


def _form_named(objects: list[TranslatedObject]) -> int:
    """How many of the selected objects DHIS2 gives a form name to translate."""
    return sum(1 for item in objects if item.form_named)


def _gap(item: TranslatedObject, locales: list[str]) -> TranslationGap | None:
    """What one object is short of, or None when it is translated into every locale in use."""
    missing_names = [locale for locale in locales if locale not in item.name_locales]
    missing_form_names = (
        [locale for locale in locales if locale not in item.form_name_locales] if item.form_named else []
    )
    if not missing_names and not missing_form_names:
        return None
    return TranslationGap(
        resource_type=item.resource_type,
        uid=item.uid,
        name=item.name,
        missing_name_locales=missing_names,
        missing_form_name_locales=missing_form_names,
    )


def _translated_objects(resource_type: str, body: dict[str, Any], surface: frozenset[str]) -> list[TranslatedObject]:
    """Project one collection's wire answer onto the selected objects it holds, translations folded per property."""
    entries = body.get(resource_type)
    if not isinstance(entries, list):
        return []
    projected: list[TranslatedObject] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        uid = entry.get("id")
        if not isinstance(uid, str) or uid not in surface:
            continue
        form_name = entry.get("formName")
        name = entry.get("name")
        projected.append(
            TranslatedObject(
                resource_type=resource_type,
                uid=uid,
                name=name if isinstance(name, str) and name != "" else uid,
                form_named=isinstance(form_name, str) and form_name != "",
                name_locales=_locales_of(entry.get("translations"), NAME_PROPERTY),
                form_name_locales=_locales_of(entry.get("translations"), FORM_NAME_PROPERTY),
            )
        )
    return projected


def _locales_of(translations: object, property_name: str) -> frozenset[str]:
    """The normalised locale tags one object holds a translation of one property in."""
    if not isinstance(translations, list):
        return frozenset()
    return frozenset(
        normalize_locale(entry["locale"])
        for entry in translations
        if isinstance(entry, dict)
        and entry.get("property") == property_name
        and isinstance(entry.get("locale"), str)
        and entry.get("locale") != ""
        and isinstance(entry.get("value"), str)
        and entry.get("value") != ""
    )

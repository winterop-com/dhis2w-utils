"""What the instance holds that the published guide does not: the drift report behind doctor's last phase.

A guide is a photograph. `d2w fhir generate` reads the instance once, the compiler turns that reading
into artifacts, and from then on the artifacts say what the instance said on the day they were
written. DHIS2 keeps moving: a chiefdom is split, an option is added to a set, a question is dropped
from a stage. Nothing in the published guide knows, and nothing in the toolchain said so until this
module.

Drift is measured inside the project's own selection scope and nowhere else. An organisation unit
outside `[generate.organisation_units]` is not drift - the project never asked for it - and neither
is a data set the selection tables leave out. The scope is read from the same `fhir.toml` the
publication was generated under, so the question is always "does this guide still describe the part
of the instance it claims to describe", never "has the instance changed anywhere".

## The five classes

| Class | Published side | Instance side |
| --- | --- | --- |
| Organisation units | the `Location` of every unit in the registry | the hierarchy under `root`, to `max_level` |
| Options | the concepts of a published option-set `CodeSystem` | that option set's options |
| Tracked entity attributes | a `tracker` or `tracked-entity` form's questions | the program's or type's attributes |
| Data elements | an `aggregate`, `event`, or `tracker-event` form's questions | the data set's or stage's elements |
| Program stages | the `tracker-event` forms a tracker program publishes | that program's stages |

Each class reports in both directions and on renames alike: something the instance gained, something
it lost, and something whose name changed under an identity that did not. A rename matters because
the published display is what a reader of the guide sees - `D2TEA_CS` carries every attribute's name,
a `CodeSystem` concept carries every option's - so a guide naming an object what the instance no
longer calls it is wrong in the way documentation is wrong.

Tracked entity **types** are out of scope. `d2w fhir validate` already names every type the project
never typed, under `unmapped-tracked-entity-type`, and one fact reported twice in two vocabularies is
worse than one report; the drift phase points at that checklist rather than repeating it.

## What is compared, and what is deliberately not

Identity is the DHIS2 UID throughout, because that is what survives a rename and what a consumer
joins on. Names are compared through `flatten_whitespace`, and a published name also matches the
wording `substitute_build_aborting_text` produces: a project generated with `hostile_names =
"substitute"` publishes "Fixed, under 1y" for an instance that says "Fixed, <1y", and reporting that
as a rename would be reporting the toolchain's own rewrite back at the reader.

Codes are not compared. A code change is a real event, but it is one the identifier slices already
carry and one `d2w fhir validate` grades for FHIR-safety, so the drift report stays about the objects
a form asks and the names a reader reads.

The remedy is the same sentence for every finding, which is why it is stated once on the phase rather
than once per row: regenerate, then compile. That is the documented lifecycle - `d2w fhir generate`
re-reads the instance, `make sushi` turns the new source into artifacts - and nothing about a drifted
object needs a different answer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.conversion.artifacts import load_compiled_artifacts
from dhis2w_fhir.names import flatten_whitespace
from dhis2w_fhir.resources.option_sets import code_system_canonical
from dhis2w_fhir.resources.questionnaires.schemas import FORM_KIND_PROFILES, FormKind, QuestionnaireNaming
from dhis2w_fhir.validation.substitution import substitute_build_aborting_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_client import Dhis2Client
    from dhis2w_fhir_engine.r4.resources import CodeSystem, Identifier, Location, Questionnaire, QuestionnaireItem

    from dhis2w_fhir.config import FhirProject, GenerateConfig

__all__ = [
    "DRIFT_REMEDY",
    "TRACKED_ENTITY_TYPE_CROSS_REFERENCE",
    "DriftFinding",
    "DriftKind",
    "DriftReport",
    "DriftSubject",
    "InstanceForm",
    "InstanceObject",
    "InstanceOption",
    "InstanceOptionSet",
    "PublishedForm",
    "PublishedGuide",
    "PublishedObject",
    "PublishedOptionSet",
    "compare_form",
    "compare_option_set",
    "compare_organisation_units",
    "detect_drift",
    "read_published_guide",
    "registry_scope_line",
]

#: The one answer every drifted object has, stated once on the phase rather than once per finding.
#: It is the documented lifecycle and nothing else: a generate re-reads the instance into FSH and
#: pre-built JSON, and a compile turns that source into the artifacts a guide publishes.
DRIFT_REMEDY = "run `d2w fhir generate`, then `make sushi`, to publish the instance as it now stands"

#: Where doctor sends a reader whose drift is about a tracked entity type rather than about the
#: objects this report covers. Stated once, as a cross-reference; the checklist itself is validate's.
TRACKED_ENTITY_TYPE_CROSS_REFERENCE = (
    "tracked entity types are graded by `d2w fhir validate` under `unmapped-tracked-entity-type`, not here"
)

#: How many UIDs one `id:in:[...]` filter carries, matching the oracle's own batch size.
_BATCH_SIZE = 100

#: The DHIS2 form kinds whose questions are tracked entity attributes rather than data elements.
#: Read off `FORM_KIND_PROFILES` rather than restated, so one table decides what a form asks.
_ATTRIBUTE_FORM_KINDS = frozenset(
    kind for kind, profile in FORM_KIND_PROFILES.items() if profile.question_subject == "tracked-entity-attribute"
)


class DriftSubject(StrEnum):
    """The kinds of object this report covers, each spelled as a reader of the guide would say it.

    The first five are what the report is about: the objects a guide carries inside its artifacts.
    The rest name the DHIS2 object one whole artifact was generated from, for the one case where the
    artifact outlived it - a selected option set or form the instance no longer holds. Naming that
    object as an option or a data element would be naming the wrong thing.
    """

    ORGANISATION_UNIT = "organisation unit"
    OPTION = "option"
    TRACKED_ENTITY_ATTRIBUTE = "tracked entity attribute"
    DATA_ELEMENT = "data element"
    PROGRAM_STAGE = "program stage"

    OPTION_SET = "option set"
    DATA_SET = "data set"
    EVENT_PROGRAM = "event program"
    TRACKER_PROGRAM = "tracker program"
    TRACKER_PROGRAM_STAGE = "tracker program stage"
    TRACKED_ENTITY_TYPE = "tracked entity type"


#: The subject one whole published form is named by when the DHIS2 object behind it is gone, in the
#: words `FORM_KIND_PROFILES` already gives each kind, so the report and a generate note agree.
_FORM_SUBJECTS: dict[FormKind, DriftSubject] = {
    "aggregate": DriftSubject.DATA_SET,
    "event": DriftSubject.EVENT_PROGRAM,
    "tracker": DriftSubject.TRACKER_PROGRAM,
    "tracker-event": DriftSubject.TRACKER_PROGRAM_STAGE,
    "tracked-entity": DriftSubject.TRACKED_ENTITY_TYPE,
}

#: Where a whole artifact's own DHIS2 object is held, for the finding that says the instance no
#: longer holds it. The selection is what put it in the guide, so the selection is what names it.
_SELECTION_HOLDER = "this project's selection"


class DriftKind(StrEnum):
    """Which direction one object drifted in."""

    #: The instance holds it and the guide publishes nothing for it.
    ADDED = "added"

    #: The guide publishes it and the instance no longer holds it.
    REMOVED = "removed"

    #: Both hold it, under one identity, under two names.
    RENAMED = "renamed"


class DriftFinding(BaseModel):
    """One drifted object: what it is, where the guide carries it, and what each side says about it."""

    model_config = ConfigDict(frozen=True)

    subject: DriftSubject
    kind: DriftKind
    uid: str
    holder: str
    """The published artifact the object belongs to, in the words the guide names that artifact by."""

    published_name: str | None = None
    instance_name: str | None = None

    @property
    def name(self) -> str:
        """The one name to call this object by: the instance's when it holds it, the guide's otherwise."""
        return self.instance_name or self.published_name or self.uid

    @property
    def title(self) -> str:
        """The object as a finding names it: what it is, what it is called, and its DHIS2 UID."""
        return f"{self.subject.value} {self.name} ({self.uid})"

    @property
    def detail(self) -> str:
        """What each side says about this object, as the one line the finding is read by."""
        if self.kind is DriftKind.ADDED:
            return f"the instance holds it in {self.holder}; the guide publishes nothing for it"
        if self.kind is DriftKind.REMOVED:
            return f"the guide publishes it under {self.holder}; the instance no longer holds it there"
        return (
            f"the guide publishes the name {self.published_name!r} under {self.holder}; "
            f"the instance now says {self.instance_name!r}"
        )


class PublishedObject(BaseModel):
    """One DHIS2 object as the published guide carries it: the UID it is keyed by, the name it shows."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str | None = None


class PublishedOptionSet(BaseModel):
    """One option-set CodeSystem the guide publishes, and the options its concepts stand for."""

    model_config = ConfigDict(frozen=True)

    uid: str
    title: str | None = None
    options: tuple[PublishedObject, ...] = ()
    """One entry per concept, keyed by the concept code - the option UID, or its code in code mode."""


class PublishedForm(BaseModel):
    """One Questionnaire the guide publishes: which DHIS2 object it is keyed to, and what it asks."""

    model_config = ConfigDict(frozen=True)

    resource_id: str
    kind: FormKind
    """The DHIS2 form kind off the form's own `code`: aggregate, event, tracker, tracker-event, tracked-entity."""

    uid: str
    title: str | None = None
    questions: tuple[PublishedObject, ...] = ()

    @property
    def asks_attributes(self) -> bool:
        """Whether this form's questions are tracked entity attributes rather than data elements."""
        return self.kind in _ATTRIBUTE_FORM_KINDS

    @property
    def holder(self) -> str:
        """How a finding names the form the drifted question belongs to."""
        return f"the published form {self.title or self.resource_id} ({self.uid})"


class PublishedGuide(BaseModel):
    """Everything on disk this report reads: the registry, the published option sets, the published forms."""

    model_config = ConfigDict(frozen=True)

    organisation_units: tuple[PublishedObject, ...] = ()
    option_sets: tuple[PublishedOptionSet, ...] = ()
    forms: tuple[PublishedForm, ...] = ()

    @property
    def program_stage_uids(self) -> frozenset[str]:
        """Every program stage the guide publishes a form for, which is what a new stage is missing from."""
        return frozenset(form.uid for form in self.forms if form.kind == "tracker-event")


class InstanceObject(BaseModel):
    """One DHIS2 object as the instance states it today."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str = ""


class InstanceOption(BaseModel):
    """One option as the instance states it today, under both the identities a concept can be keyed by."""

    model_config = ConfigDict(frozen=True)

    uid: str
    code: str | None = None
    name: str = ""


class InstanceOptionSet(BaseModel):
    """One option set as the instance states it today."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str = ""
    options: tuple[InstanceOption, ...] = ()


class InstanceForm(BaseModel):
    """What the instance says a published form's DHIS2 object collects today."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str = ""
    questions: tuple[InstanceObject, ...] = ()
    stages: tuple[InstanceObject, ...] = ()
    """The program's stages, read only for a tracker program - the one kind that publishes a form per stage."""


class DriftReport(BaseModel):
    """Everything one drift pass concluded: what it read, what it read it against, and what moved."""

    model_config = ConfigDict(frozen=True)

    registry_scope: str
    organisation_unit_count: int = 0
    option_set_count: int = 0
    form_count: int = 0
    findings: tuple[DriftFinding, ...] = ()

    @property
    def evidence(self) -> str:
        """The one line this pass is read by, quiet when nothing drifted and remedied when something did."""
        read = (
            f"{self.organisation_unit_count:,} organisation unit(s), {self.option_set_count:,} option set(s), "
            f"and {self.form_count:,} form(s) read against {self.registry_scope}"
        )
        if not self.findings:
            return f"the guide publishes the instance as it now stands: {read}"
        return (
            f"{len(self.findings):,} object(s) moved since the guide was published: {read}. "
            f"{DRIFT_REMEDY}. {TRACKED_ENTITY_TYPE_CROSS_REFERENCE}"
        )


def registry_scope_line(config: GenerateConfig) -> str:
    """The slice of the hierarchy the registry claims to publish, in the words the evidence states it."""
    selection = config.organisation_units
    if selection.root is not None and selection.max_level is not None:
        return f"the hierarchy under {selection.root} down to level {selection.max_level}"
    if selection.root is not None:
        return f"the hierarchy under {selection.root}"
    if selection.max_level is not None:
        return f"the hierarchy down to level {selection.max_level}"
    return "the whole hierarchy"


def read_published_guide(project: FhirProject) -> PublishedGuide:
    """Read what one project publishes off disk, through the reader the served store and check-artifacts use.

    `load_compiled_artifacts` is the single reader of the two published trees - `ig/fsh-generated`
    for what the compiler wrote, `ig/input/resources` for the registry and terminology the emitters
    wrote straight to JSON - so a drift pass, a served store, and a conversion context can never
    disagree about what a project publishes. It raises `CompiledIgMissingError` on a project that was
    generated but never compiled, which is a fact about the project rather than about the instance.
    """
    artifacts = load_compiled_artifacts(project)
    generate = project.config.generate
    identifier_base = f"{generate.identifier_system_base}/id"
    naming = QuestionnaireNaming.from_naming(generate.naming)
    canonical = project.config.ig.canonical
    question_systems = {
        "data-element": code_system_canonical(canonical, naming.data_element_code_system_id),
        "tracked-entity-attribute": code_system_canonical(canonical, naming.tracked_entity_attribute_code_system_id),
    }
    return PublishedGuide(
        organisation_units=_published_organisation_units(artifacts.locations, identifier_base),
        option_sets=_published_option_sets(artifacts.code_systems, identifier_base),
        forms=_published_forms(artifacts.questionnaires, identifier_base, question_systems),
    )


async def detect_drift(client: Dhis2Client, project: FhirProject) -> DriftReport:
    """Read the instance for everything one published guide claims, and report every object that moved."""
    published = read_published_guide(project)
    generate = project.config.generate
    findings: list[DriftFinding] = []
    findings.extend(
        compare_organisation_units(published.organisation_units, await _instance_organisation_units(client, generate))
    )
    instance_option_sets = await _instance_option_sets(client, [option_set.uid for option_set in published.option_sets])
    for option_set in published.option_sets:
        findings.extend(compare_option_set(option_set, instance_option_sets.get(option_set.uid)))
    instance_forms = await _instance_forms(client, published.forms)
    for form in published.forms:
        findings.extend(compare_form(form, instance_forms.get(form.uid), published.program_stage_uids))
    return DriftReport(
        registry_scope=registry_scope_line(generate),
        organisation_unit_count=len(published.organisation_units),
        option_set_count=len(published.option_sets),
        form_count=len(published.forms),
        findings=tuple(findings),
    )


def compare_organisation_units(
    published: Sequence[PublishedObject], instance: Sequence[InstanceObject]
) -> list[DriftFinding]:
    """Judge the published registry against the hierarchy slice the project selected.

    Both sides are already narrowed to the selection, so every difference is drift rather than a
    unit the project never asked for: a unit the instance gained inside the scope, a unit it lost,
    and a unit whose name changed under a UID that did not.
    """
    holder = "the registry scope this project publishes"
    return _compare(DriftSubject.ORGANISATION_UNIT, holder, published, instance)


def compare_option_set(published: PublishedOptionSet, instance: InstanceOptionSet | None) -> list[DriftFinding]:
    """Judge one published CodeSystem's concepts against the options the instance's set holds today.

    A concept is keyed by the option UID under `concept_code_source = "id"` and by the option's DHIS2
    code under `"code"`, so the instance side is indexed under both and the comparison holds whichever
    mode the guide was published in.
    """
    holder = f"the published option set {published.title or published.uid} ({published.uid})"
    if instance is None:
        return [
            DriftFinding(
                subject=DriftSubject.OPTION_SET,
                kind=DriftKind.REMOVED,
                uid=published.uid,
                holder=_SELECTION_HOLDER,
                published_name=published.title,
            )
        ]
    by_identity: dict[str, InstanceOption] = {}
    for option in instance.options:
        by_identity[option.uid] = option
        if option.code:
            by_identity.setdefault(option.code, option)
    findings: list[DriftFinding] = []
    for concept in published.options:
        matched = by_identity.get(concept.uid)
        if matched is None:
            findings.append(
                DriftFinding(
                    subject=DriftSubject.OPTION,
                    kind=DriftKind.REMOVED,
                    uid=concept.uid,
                    holder=holder,
                    published_name=concept.name,
                )
            )
        elif not _names_agree(concept.name, matched.name):
            findings.append(
                DriftFinding(
                    subject=DriftSubject.OPTION,
                    kind=DriftKind.RENAMED,
                    uid=concept.uid,
                    holder=holder,
                    published_name=concept.name,
                    instance_name=flatten_whitespace(matched.name),
                )
            )
    concept_codes = {concept.uid for concept in published.options}
    findings.extend(
        DriftFinding(
            subject=DriftSubject.OPTION, kind=DriftKind.ADDED, uid=option.uid, holder=holder, instance_name=option.name
        )
        for option in instance.options
        if option.uid not in concept_codes and (option.code or "") not in concept_codes
    )
    return findings


def compare_form(
    published: PublishedForm, instance: InstanceForm | None, published_stage_uids: frozenset[str]
) -> list[DriftFinding]:
    """Judge one published form's questions against what the instance says its DHIS2 object collects.

    A tracker registration form answers for its program's attributes and a `tracked-entity` form for
    its type's; every other kind answers for data elements. A tracker program is also asked for its
    stages, because a stage the program gained publishes no form and so asks none of its questions.
    """
    subject = DriftSubject.TRACKED_ENTITY_ATTRIBUTE if published.asks_attributes else DriftSubject.DATA_ELEMENT
    if instance is None:
        return [
            DriftFinding(
                subject=_FORM_SUBJECTS[published.kind],
                kind=DriftKind.REMOVED,
                uid=published.uid,
                holder=_SELECTION_HOLDER,
                published_name=published.title,
            )
        ]
    findings = _compare(subject, published.holder, published.questions, instance.questions)
    findings.extend(
        DriftFinding(
            subject=DriftSubject.PROGRAM_STAGE,
            kind=DriftKind.ADDED,
            uid=stage.uid,
            holder=published.holder,
            instance_name=stage.name,
        )
        for stage in instance.stages
        if stage.uid not in published_stage_uids
    )
    return findings


def _compare(
    subject: DriftSubject, holder: str, published: Sequence[PublishedObject], instance: Sequence[InstanceObject]
) -> list[DriftFinding]:
    """The three-way comparison every class shares: what the instance gained, lost, and renamed."""
    by_uid = {item.uid: item for item in instance}
    published_uids = {item.uid for item in published}
    findings: list[DriftFinding] = []
    for item in published:
        matched = by_uid.get(item.uid)
        if matched is None:
            findings.append(
                DriftFinding(
                    subject=subject, kind=DriftKind.REMOVED, uid=item.uid, holder=holder, published_name=item.name
                )
            )
        elif not _names_agree(item.name, matched.name):
            findings.append(
                DriftFinding(
                    subject=subject,
                    kind=DriftKind.RENAMED,
                    uid=item.uid,
                    holder=holder,
                    published_name=item.name,
                    instance_name=flatten_whitespace(matched.name),
                )
            )
    findings.extend(
        DriftFinding(subject=subject, kind=DriftKind.ADDED, uid=item.uid, holder=holder, instance_name=item.name)
        for item in instance
        if item.uid not in published_uids
    )
    return findings


def _names_agree(published: str | None, instance: str) -> bool:
    """Whether one published name still says what the instance says, through the rewrites a guide may carry.

    A project generated under `hostile_names = "substitute"` publishes "Fixed, under 1y" where the
    instance says "Fixed, <1y", so the substituted wording matches too: that difference is this
    toolchain's own rewrite, and reporting it as a rename would be reporting a decision back at the
    reader who took it.
    """
    if published is None:
        return True
    stated = flatten_whitespace(instance)
    return published in {stated, flatten_whitespace(substitute_build_aborting_text(instance))}


def _published_organisation_units(locations: Sequence[Location], identifier_base: str) -> tuple[PublishedObject, ...]:
    """Every organisation unit the registry publishes, off the Location each unit emits, deduped by UID."""
    system = f"{identifier_base}/org-unit"
    units: dict[str, PublishedObject] = {}
    for location in locations:
        uid = _identifier_value(location.identifier, system)
        if uid:
            units.setdefault(uid, PublishedObject(uid=uid, name=location.name))
    return tuple(units[uid] for uid in sorted(units))


def _published_option_sets(code_systems: Sequence[CodeSystem], identifier_base: str) -> tuple[PublishedOptionSet, ...]:
    """Every option set the guide publishes a CodeSystem for, with the concepts that CodeSystem carries.

    A support vocabulary - the data dictionary's `D2DE_CS`, `D2TEA_CS`, `D2COC_CS`, the form-type
    terminology - carries no DHIS2 identifier at all, so keying on the option-set system is what
    separates the sets a project selected from the vocabularies it emits about them.
    """
    system = f"{identifier_base}/option-set"
    published: list[PublishedOptionSet] = []
    for code_system in code_systems:
        uid = _identifier_value(code_system.identifier, system)
        if not uid:
            continue
        published.append(
            PublishedOptionSet(
                uid=uid,
                title=code_system.title,
                options=tuple(
                    PublishedObject(uid=concept.code, name=concept.display)
                    for concept in code_system.concept or []
                    if concept.code
                ),
            )
        )
    return tuple(sorted(published, key=lambda option_set: option_set.uid))


def _published_forms(
    questionnaires: Sequence[Questionnaire], identifier_base: str, question_systems: dict[str, str]
) -> tuple[PublishedForm, ...]:
    """Every published form, keyed to the DHIS2 object it was generated from and to the questions it asks."""
    forms: list[PublishedForm] = []
    for questionnaire in questionnaires:
        kind = _form_kind(questionnaire)
        if kind is None:
            continue
        profile = FORM_KIND_PROFILES[kind]
        uid = _identifier_value(questionnaire.identifier, f"{identifier_base}/{profile.identifier_segment}")
        if not uid:
            continue
        forms.append(
            PublishedForm(
                resource_id=questionnaire.id or uid,
                kind=kind,
                uid=uid,
                title=questionnaire.title,
                questions=_published_questions(questionnaire.item or [], question_systems[profile.question_subject]),
            )
        )
    return tuple(sorted(forms, key=lambda form: form.uid))


def _published_questions(items: Sequence[QuestionnaireItem], system: str) -> tuple[PublishedObject, ...]:
    """Every DHIS2 object one form asks a question from, read off the coding each question carries.

    The coding is what identifies the object, not the link id: a disaggregated cell's link id joins
    the data element to the category option combo, while its coding names the combo alone. Reading
    the coding keyed to the form's own question system therefore yields the data elements a data set
    collects and nothing else, one entry per object however many cells it disaggregates into.
    """
    collected: dict[str, PublishedObject] = {}

    def walk(nested: Sequence[QuestionnaireItem]) -> None:
        """Collect this level's questions, then every level below it."""
        for item in nested:
            for coding in item.code or []:
                if coding.system == system and coding.code:
                    collected.setdefault(coding.code, PublishedObject(uid=coding.code, name=coding.display))
            walk(item.item or [])

    walk(items)
    return tuple(collected[uid] for uid in sorted(collected))


def _form_kind(questionnaire: Questionnaire) -> FormKind | None:
    """The DHIS2 form kind one published Questionnaire carries on its own `code`."""
    for coding in questionnaire.code or []:
        for kind in FORM_KIND_PROFILES:
            if coding.code == kind:
                return kind
    return None


def _identifier_value(identifiers: Sequence[Identifier] | None, system: str) -> str | None:
    """The value one resource carries under one identifier system, or None when it carries none."""
    for identifier in identifiers or []:
        if identifier.system == system and identifier.value:
            return str(identifier.value)
    return None


async def _instance_organisation_units(client: Dhis2Client, config: GenerateConfig) -> tuple[InstanceObject, ...]:
    """The hierarchy slice the project selected, under the very filters the registry walk applies."""
    filters: list[str] = []
    selection = config.organisation_units
    if selection.root is not None:
        filters.append(f"path:like:{selection.root}")
    if selection.max_level is not None:
        filters.append(f"level:le:{selection.max_level}")
    params: dict[str, Any] = {"fields": "id,name", "paging": "false"}
    if filters:
        params["filter"] = filters
    raw = await client.get_raw("/api/organisationUnits", params=params)
    return _objects(_list(raw, "organisationUnits"))


async def _instance_option_sets(client: Dhis2Client, uids: Sequence[str]) -> dict[str, InstanceOptionSet]:
    """Every published option set as the instance holds it today, read back in `id:in:[...]` batches."""
    resolved: dict[str, InstanceOptionSet] = {}
    for entry in await _read_batched(client, "/api/optionSets", "optionSets", "id,name,options[id,code,name]", uids):
        uid = str(entry.get("id") or "")
        if not uid:
            continue
        resolved[uid] = InstanceOptionSet(
            uid=uid,
            name=str(entry.get("name") or ""),
            options=tuple(
                InstanceOption(
                    uid=str(option.get("id") or ""),
                    code=str(option["code"]) if isinstance(option.get("code"), str) else None,
                    name=str(option.get("name") or ""),
                )
                for option in _list(entry, "options")
                if option.get("id")
            ),
        )
    return resolved


async def _instance_forms(client: Dhis2Client, forms: Sequence[PublishedForm]) -> dict[str, InstanceForm]:
    """What the instance says each published form's DHIS2 object collects today, one read per collection.

    An event program publishes one form for the program while DHIS2 keeps its data elements on the
    single stage underneath, so a program's questions are read off its stages either way and a
    tracker program contributes its stage list besides.
    """
    by_kind: dict[FormKind, list[str]] = {}
    for form in forms:
        by_kind.setdefault(form.kind, []).append(form.uid)
    resolved: dict[str, InstanceForm] = {}
    for entry in await _read_batched(
        client,
        "/api/dataSets",
        "dataSets",
        "id,name,dataSetElements[dataElement[id,name]]",
        by_kind.get("aggregate", []),
    ):
        resolved.update(_one_form(entry, _nested_objects(_list(entry, "dataSetElements"), "dataElement")))
    tracker_uids = frozenset(by_kind.get("tracker", []))
    program_uids = [*by_kind.get("event", []), *tracker_uids]
    for entry in await _read_batched(
        client,
        "/api/programs",
        "programs",
        "id,name,programTrackedEntityAttributes[trackedEntityAttribute[id,name]],"
        "programStages[id,name,programStageDataElements[dataElement[id,name]]]",
        program_uids,
    ):
        stages = _list(entry, "programStages")
        if str(entry.get("id") or "") in tracker_uids:
            attributes = _nested_objects(_list(entry, "programTrackedEntityAttributes"), "trackedEntityAttribute")
            resolved.update(_one_form(entry, attributes, stages=_objects(stages)))
        else:
            # An event program publishes one form for the program, and DHIS2 keeps that program's
            # data elements on the single stage underneath it, so the questions are read off there.
            resolved.update(
                _one_form(
                    entry,
                    _nested_objects(
                        [element for stage in stages for element in _list(stage, "programStageDataElements")],
                        "dataElement",
                    ),
                )
            )
    for entry in await _read_batched(
        client,
        "/api/programStages",
        "programStages",
        "id,name,programStageDataElements[dataElement[id,name]]",
        by_kind.get("tracker-event", []),
    ):
        resolved.update(_one_form(entry, _nested_objects(_list(entry, "programStageDataElements"), "dataElement")))
    for entry in await _read_batched(
        client,
        "/api/trackedEntityTypes",
        "trackedEntityTypes",
        "id,name,trackedEntityTypeAttributes[trackedEntityAttribute[id,name]]",
        by_kind.get("tracked-entity", []),
    ):
        resolved.update(
            _one_form(entry, _nested_objects(_list(entry, "trackedEntityTypeAttributes"), "trackedEntityAttribute"))
        )
    return resolved


def _one_form(
    entry: dict[str, Any], questions: tuple[InstanceObject, ...], stages: tuple[InstanceObject, ...] = ()
) -> dict[str, InstanceForm]:
    """One collection entry as the instance side of one published form, keyed by its UID."""
    uid = str(entry.get("id") or "")
    if not uid:
        return {}
    return {uid: InstanceForm(uid=uid, name=str(entry.get("name") or ""), questions=questions, stages=stages)}


async def _read_batched(
    client: Dhis2Client, path: str, collection_key: str, fields: str, uids: Sequence[str]
) -> list[dict[str, Any]]:
    """One DHIS2 collection read back for a set of UIDs, in `id:in:[...]` batches, at the HTTP boundary."""
    entries: list[dict[str, Any]] = []
    for start in range(0, len(uids), _BATCH_SIZE):
        batch = uids[start : start + _BATCH_SIZE]
        raw = await client.get_raw(
            path, params={"fields": fields, "filter": f"id:in:[{','.join(batch)}]", "paging": "false"}
        )
        entries.extend(_list(raw, collection_key))
    return entries


def _objects(entries: Sequence[dict[str, Any]]) -> tuple[InstanceObject, ...]:
    """One DHIS2 collection as the typed objects it names, wrapped at the HTTP boundary and nowhere past it."""
    collected: dict[str, InstanceObject] = {}
    for entry in entries:
        uid = str(entry.get("id") or "")
        if uid:
            collected.setdefault(uid, InstanceObject(uid=uid, name=str(entry.get("name") or "")))
    return tuple(collected.values())


def _nested_objects(entries: Sequence[dict[str, Any]], key: str) -> tuple[InstanceObject, ...]:
    """The objects one join collection wraps - a data set element's data element, a program's attribute."""
    collected: dict[str, InstanceObject] = {}
    for entry in entries:
        nested = entry.get(key)
        if not isinstance(nested, dict):
            continue
        uid = str(nested.get("id") or "")
        if uid:
            collected.setdefault(uid, InstanceObject(uid=uid, name=str(nested.get("name") or "")))
    return tuple(collected.values())


def _list(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """The list one DHIS2 response carries under one key, at the HTTP boundary and nowhere past it."""
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]

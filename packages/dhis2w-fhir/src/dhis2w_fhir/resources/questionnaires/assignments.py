"""The organisation-unit assignment artifact: one `List` of Locations per form, emitted only when it narrows.

DHIS2 scopes every data set and program to the organisation units it is assigned to, and a capture
against a unit outside that scope is refused at forward time (`E1029`). This module publishes the
scope so a client can honour it: one `List` whose entries are the Locations of the assigned units,
named from the form's `D2OrganisationUnitAssignment` extension.

The economy that makes it publishable is the emission rule: **a List is written only when the
assignment is a proper subset of the published organisation-unit registry.** Assigned everywhere -
the common national case - publishes nothing, and absence means the whole registry, which is what
a consumer already assumed. Tracker stages share their program's List, because DHIS2 hangs the
assignment on the program and not on the stage.

`List` rather than `Group`: R4 binds `Group.member.entity` to Patient, Practitioner,
PractitionerRole, Device, Medication, Substance, and Group, so a Location cannot legally be a
Group member, while `List.entry.item` is `Reference(Resource)` and takes one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir.names import StemResolution
from dhis2w_fhir.notes import GenerateNoteCategory, generate_note
from dhis2w_fhir.r4 import Identifier, ListEntry, Reference, ResourceList
from dhis2w_fhir.resources.questionnaires.schemas import (
    FORM_KIND_PROFILES,
    FormKind,
    QuestionnaireNaming,
    QuestionnaireSourceIn,
    QuestionnaireStemPlan,
    source_program,
)
from dhis2w_fhir.writer import JsonArtifact, JsonBuild

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

__all__ = [
    "ASSIGNMENT_DIRECTORY",
    "ASSIGNMENT_ID_SUFFIX",
    "ASSIGNMENT_LIST_RESOURCE_TYPE",
    "AssignmentBuild",
    "AssignmentContainer",
    "AssignmentContainerKind",
    "AssignmentIndex",
    "AssignmentPlan",
    "assignment_container",
    "assignment_container_kind",
    "assignment_container_uid",
    "build_assignment_artifacts",
]

#: The `ig/input/resources/` subdirectory the assignment Lists own outright - one JSON file per container.
ASSIGNMENT_DIRECTORY = "assignments"

#: The resource type an assignment artifact is published as, and the prefix of its literal reference.
ASSIGNMENT_LIST_RESOURCE_TYPE = "List"

#: The trailing token every assignment List id ends in, after the prefix, kind token, and container stem.
ASSIGNMENT_ID_SUFFIX = "org-units"

AssignmentContainerKind = Literal["data-set", "program"]
"""Which DHIS2 object holds the assignment: a data set for an aggregate form, a program for both others."""

#: The `Location` reference prefix an assignment entry and every capture-side subject are written with.
_LOCATION_REFERENCE_PREFIX = "Location/"


class AssignmentIndex(BaseModel):
    """The organisation units DHIS2 assigns each selected data set and program to, read id-only.

    Keyed by the container's DHIS2 UID - a data set UID for an aggregate form, a program UID for an
    event program and for every stage of a tracker program. A container absent from the index was
    not read, which is not the same as a container assigned to nothing: an absent container emits
    no artifact, an empty one emits a List no unit is on.
    """

    model_config = ConfigDict(frozen=True)

    organisation_units: dict[str, frozenset[str]] = Field(default_factory=dict)

    def assigned(self, container_uid: str) -> frozenset[str] | None:
        """The units one container is assigned to, or None when the container was not read."""
        return self.organisation_units.get(container_uid)


class AssignmentContainer(BaseModel):
    """The DHIS2 object one form's assignment hangs on, with the identity its List artifact rides."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    kind: AssignmentContainerKind
    stem: str
    """The identity stem the container's artifacts derive from - the form's own, or its program's."""


class AssignmentPlan(BaseModel):
    """Which assignment List each form references, keyed by the container the assignment hangs on.

    A form whose container is absent publishes no artifact, and its Questionnaire carries no
    `D2OrganisationUnitAssignment` extension - the whole registry may report it.
    """

    model_config = ConfigDict(frozen=True)

    list_ids: dict[str, str] = Field(default_factory=dict)

    def list_id_for(self, source: QuestionnaireSourceIn) -> str | None:
        """The id of the List scoping one form, or None when the form publishes no assignment."""
        return self.list_ids.get(assignment_container_uid(source))

    def reference_for(self, source: QuestionnaireSourceIn) -> str | None:
        """The literal `List/<id>` reference one form's assignment extension carries, or None."""
        list_id = self.list_id_for(source)
        return None if list_id is None else f"{ASSIGNMENT_LIST_RESOURCE_TYPE}/{list_id}"


class AssignmentBuild(JsonBuild):
    """The assignment Lists one run publishes, plus the plan the questionnaire emitters reference them by."""

    plan: AssignmentPlan = Field(default_factory=AssignmentPlan)


def assignment_container_uid(source: QuestionnaireSourceIn) -> str:
    """The DHIS2 UID of the object one form's assignment hangs on - the stage's program, else the form."""
    return source.uid if source.kind != "tracker-event" else source_program(source).uid


#: The form kinds whose assignment hangs on the tracker program rather than on the form itself. A
#: registration form *is* its program, so it is in here for its stem rather than for its UID: both
#: tracker kinds have to resolve the one container through the program surface, or a run would name
#: one program's List twice under two stems.
_PROGRAM_CONTAINER_KINDS = frozenset({"tracker", "tracker-event"})


def assignment_container_kind(kind: FormKind) -> AssignmentContainerKind:
    """Which DHIS2 object kind holds one form kind's assignment."""
    return "data-set" if kind == "aggregate" else "program"


def assignment_container(source: QuestionnaireSourceIn, stem_plan: QuestionnaireStemPlan) -> AssignmentContainer:
    """The assignment container of one form, resolved through the surface its identity stem lives on.

    A data set and an event program are their own container, so the stem is the form target's.
    Both tracker kinds resolve to the program, whose stem is the directory segment their files
    already nest under - which is what makes a program's registration form and every one of its
    stages share the one artifact DHIS2 hangs the assignment on.
    """
    if source.kind in _PROGRAM_CONTAINER_KINDS:
        program = source_program(source)
        return AssignmentContainer(
            uid=program.uid,
            name=program.name,
            kind="program",
            stem=stem_plan.programs.stem_for(program.uid),
        )
    return AssignmentContainer(
        uid=source.uid,
        name=source.name,
        kind=assignment_container_kind(source.kind),
        stem=stem_plan.targets.stem_for(source.uid),
    )


def build_assignment_artifacts(
    sources: list[QuestionnaireSourceIn],
    assignments: AssignmentIndex,
    config: GenerateConfig,
    *,
    published: StemResolution,
    stem_plan: QuestionnaireStemPlan,
) -> AssignmentBuild:
    """Build one assignment List per container whose assignment narrows the published registry.

    `published` is the registry selection's stem resolution: its keys are the units the run
    publishes a Location for, and its stems are the ids those Locations carry. The assignment is
    intersected with that set before it is judged, so a unit DHIS2 assigns but the registry does
    not publish can never make an assignment look narrower than it is.
    """
    naming = QuestionnaireNaming.from_naming(config.naming)
    published_uids = frozenset(published.stems)
    build = AssignmentBuild()
    list_ids: dict[str, str] = {}
    empty_containers: list[str] = []
    for container in _containers(sources, stem_plan):
        assigned = assignments.assigned(container.uid)
        if assigned is None:
            continue
        members = assigned & published_uids
        if members == published_uids:
            continue
        list_id = _assignment_list_id(naming, container)
        list_ids[container.uid] = list_id
        build.artifacts.append(
            _json_artifact(list_id, _assignment_list(list_id, container, members, published, config))
        )
        if not members:
            empty_containers.append(f"{container.name} ({container.uid})")
    if empty_containers:
        build.notes.append(
            generate_note(
                GenerateNoteCategory.SELECTION_GAP,
                f"{len(empty_containers)} form(s) are assigned to no organisation unit the registry publishes, so "
                f"their assignment List is empty and no unit may report them: {', '.join(sorted(empty_containers))}",
            )
        )
    build.plan = AssignmentPlan(list_ids=list_ids)
    return build


def _containers(sources: list[QuestionnaireSourceIn], stem_plan: QuestionnaireStemPlan) -> list[AssignmentContainer]:
    """Every distinct assignment container of the run, in the order the forms first name it."""
    containers: dict[str, AssignmentContainer] = {}
    for source in sources:
        container = assignment_container(source, stem_plan)
        containers.setdefault(container.uid, container)
    return list(containers.values())


def _assignment_list_id(naming: QuestionnaireNaming, container: AssignmentContainer) -> str:
    """FHIR id of one container's assignment List (e.g. `d2-ds-BfMAe6Itzgt-org-units`)."""
    return naming.assignment_list_id(container.kind, container.stem, container.uid)


def _assignment_list(
    list_id: str,
    container: AssignmentContainer,
    members: frozenset[str],
    published: StemResolution,
    config: GenerateConfig,
) -> ResourceList:
    """One container's assignment as a snapshot List of the Locations its units are published as.

    Entries are ordered by the Location id they reference, so a regenerate of an unchanged
    assignment produces a byte-identical file whatever order DHIS2 returned the units in.
    """
    stems = sorted(published.stem_for(uid) for uid in members)
    return ResourceList(
        id=list_id,
        identifier=[
            Identifier(
                system=_container_identifier_system(container.kind, config),
                value=container.uid,
            )
        ],
        status="current",
        mode="snapshot",
        title=f"{container.name} - assigned organisation units",
        entry=[ListEntry(item=Reference(reference=f"{_LOCATION_REFERENCE_PREFIX}{stem}")) for stem in stems] or None,
    )


def _container_identifier_system(kind: AssignmentContainerKind, config: GenerateConfig) -> str:
    """The DHIS2 identifier system the container UID on the List is stated under."""
    profile = FORM_KIND_PROFILES["aggregate" if kind == "data-set" else "event"]
    return f"{config.identifier_system_base}/id/{profile.identifier_segment}"


def _json_artifact(list_id: str, resource: ResourceList) -> JsonArtifact:
    """Serialise one assignment List as the predefined-resource file the loader reads."""
    return JsonArtifact(
        relative_path=f"{ASSIGNMENT_DIRECTORY}/{ASSIGNMENT_LIST_RESOURCE_TYPE}-{list_id}.json",
        content=f"{resource.model_dump_json(exclude_none=True, by_alias=True, indent=2)}\n",
    )

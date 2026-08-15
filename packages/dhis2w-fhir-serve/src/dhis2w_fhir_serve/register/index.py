"""What the published guide already says about the instance's tracked entities, read once at startup.

An identifier search arrives as `system|value` and has to become a DHIS2 query. Everything needed
for that translation is already in the store, put there by the generate targets:

- A registration Questionnaire carries the tracked entity type it registers, under
  `{base}/id/tracked-entity-type`. The set of those values is the set of types this project's forms
  register into, and one of them is what `/api/tracker/trackedEntities` requires - the endpoint
  refuses a query naming neither a type nor a program (E1003).
- `D2TET_CM` maps each published type onto the FHIR resource type its registrations are served as:
  one row per type, the row's code the type UID, its display the name the instance holds, its target
  the resource. **That map is the contract.** `[generate.tracked_entity_types]` is what generated it,
  but a running facade never reads config to decide what a type is - it reads the artifact the guide
  published, so a served resource and a published `subjectType` cannot disagree. A published type the
  map says nothing about is a `Patient`, which is the same default the map itself was built from.
- `D2TEA_CS` publishes one concept per tracked entity attribute the forms ask, carrying the DHIS2
  code, a `unique` boolean, and a `searchable` boolean. Those two together are the search key set:
  uniqueness is what makes a value name a subject rather than describe one, and searchability is what
  DHIS2 itself declares a clerk may look someone up by. A woman whose first name is searchable but
  not unique is found by her first name in DHIS2, and a facade that keyed on uniqueness alone would
  refuse the one lookup the clinic actually performs.
- The published registry names organisation units, and a registration form's title is the program's
  name, so an enrollment listing can say "Antenatal care at Ngelehun CHC" instead of two UIDs. Both
  are joins onto what the guide published, and both stay silent when it published nothing: a
  program outside this project's selection gets no name rather than a guessed one.

A project that publishes no registration form has no tracked entity type, and every lookup here
answers empty. That is the honest reading of a guide with nobody in it, and the route says so.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dhis2w_fhir.foundation.tracked_entity_attribute_values import (
    tracked_entity_attribute_identifier_system,
    tracked_entity_attribute_value_extension_url,
)
from dhis2w_fhir.r4 import CodeSystem, ConceptMap
from dhis2w_fhir.r4.schemas import DEFAULT_SUBJECT_RESOURCE_TYPE
from dhis2w_fhir.resources.examples.documents import TRACKED_ENTITY_IDENTIFIER_SEGMENT
from dhis2w_fhir.resources.questionnaires import TRACKED_ENTITY_TYPE_IDENTIFIER_SEGMENT
from dhis2w_fhir.resources.questionnaires.schemas import QuestionnaireNaming
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from dhis2w_fhir_serve.log import LOGGER_NAME
from dhis2w_fhir_serve.store import ResourceStore, StoreEntry

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject

#: The resource types the index reads, each for one join it publishes.
QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"
CODE_SYSTEM_RESOURCE_TYPE = "CodeSystem"
CONCEPT_MAP_RESOURCE_TYPE = "ConceptMap"

#: The two resource types an organisation unit is published as. Both carry the DHIS2 UID and the
#: name, and a project may publish either - the registry emits the pair, and a selection with no
#: geometry still emits the Location - so the join reads whichever it finds first.
REGISTRY_RESOURCE_TYPES = ("Organization", "Location")

#: The identifier-system segments the index joins on, beside the tracked-entity pair.
ORGANISATION_UNIT_IDENTIFIER_SEGMENT = "org-unit"
PROGRAM_IDENTIFIER_SEGMENT = "program"

#: The `D2TEA_CS` concept properties this index reads: the DHIS2 code, and the two flags that make
#: an attribute a search key - uniqueness, and the searchability DHIS2 declares for a lookup.
CODE_CONCEPT_PROPERTY = "dhis2-code"
UNIQUE_CONCEPT_PROPERTY = "unique"
SEARCHABLE_CONCEPT_PROPERTY = "searchable"

logger = logging.getLogger(LOGGER_NAME)


class PublishedAttribute(BaseModel):
    """One tracked entity attribute the guide publishes, and what it says about it."""

    model_config = ConfigDict(frozen=True)

    attribute_uid: str
    display: str | None = None
    code: str | None = None
    unique: bool = False
    searchable: bool = False
    """Whether DHIS2 declares the attribute searchable in any context this guide publishes."""

    identifier_system: str
    """The system a value of this attribute is carried under when DHIS2 declares the attribute unique."""

    def is_search_key(self) -> bool:
        """Whether a bare identifier value is looked for under this attribute by default."""
        return self.unique or self.searchable


class PublishedTrackedEntityType(BaseModel):
    """One tracked entity type this guide registers, and the FHIR resource it publishes it as."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str | None = None
    """The name the instance holds for the type, as `D2TET_CM` published it, or None when it published none."""

    resource_type: str = DEFAULT_SUBJECT_RESOURCE_TYPE
    """The FHIR resource a tracked entity of this type is served as - what the published map states."""


class TrackedEntityIndex(BaseModel):
    """The published facts a register lookup resolves against, built once from the store at startup."""

    model_config = ConfigDict(frozen=True)

    tracked_entity_system: str
    """`{base}/id/tracked-entity` - the system whose value is the tracked entity UID itself."""

    tracked_entity_type_system: str
    attribute_value_extension_url: str
    identifier_system_base: str
    tracked_entity_types: tuple[PublishedTrackedEntityType, ...] = ()
    attributes: tuple[PublishedAttribute, ...] = ()
    program_names: dict[str, str] = Field(default_factory=dict)
    organisation_unit_names: dict[str, str] = Field(default_factory=dict)

    _attributes_by_uid: dict[str, PublishedAttribute] = PrivateAttr(default_factory=dict)
    _attributes_by_system: dict[str, PublishedAttribute] = PrivateAttr(default_factory=dict)
    _types_by_uid: dict[str, PublishedTrackedEntityType] = PrivateAttr(default_factory=dict)

    @classmethod
    def from_store(cls, project: FhirProject, store: ResourceStore) -> TrackedEntityIndex:
        """Read every join a register lookup needs out of one loaded store."""
        base = project.config.generate.identifier_system_base
        naming = QuestionnaireNaming.from_naming(project.config.generate.naming)
        tracked_entity_type_system = f"{base}/id/{TRACKED_ENTITY_TYPE_IDENTIFIER_SEGMENT}"
        program_system = f"{base}/id/{PROGRAM_IDENTIFIER_SEGMENT}"
        organisation_unit_system = f"{base}/id/{ORGANISATION_UNIT_IDENTIFIER_SEGMENT}"
        registered_type_uids: list[str] = []
        program_names: dict[str, str] = {}
        organisation_unit_names: dict[str, str] = {}
        attributes: tuple[PublishedAttribute, ...] = ()
        mapping: dict[str, PublishedTrackedEntityType] = {}
        for entry in store.entries:
            if entry.resource_type == QUESTIONNAIRE_RESOURCE_TYPE:
                registered = _identifier_values(entry, tracked_entity_type_system)
                if not registered:
                    continue
                registered_type_uids.extend(registered)
                _record_name(entry, program_system, program_names, "title")
            elif entry.resource_type == CODE_SYSTEM_RESOURCE_TYPE and (
                entry.resource_id == naming.tracked_entity_attribute_code_system_id
            ):
                attributes = _published_attributes(entry, base)
            elif entry.resource_type == CONCEPT_MAP_RESOURCE_TYPE and (
                entry.resource_id == naming.tracked_entity_type_resource_map_id
            ):
                mapping = _mapped_tracked_entity_types(entry)
            elif entry.resource_type in REGISTRY_RESOURCE_TYPES:
                _record_name(entry, organisation_unit_system, organisation_unit_names, "name")
        return cls(
            tracked_entity_system=f"{base}/id/{TRACKED_ENTITY_IDENTIFIER_SEGMENT}",
            tracked_entity_type_system=tracked_entity_type_system,
            attribute_value_extension_url=tracked_entity_attribute_value_extension_url(
                project.config.generate, project.config.ig.canonical
            ),
            identifier_system_base=base,
            tracked_entity_types=_registered_types(registered_type_uids, mapping),
            attributes=attributes,
            program_names=program_names,
            organisation_unit_names=organisation_unit_names,
        )

    def model_post_init(self, context: Any, /) -> None:
        """Key the published facts by UID and by identifier system (private attributes stay settable)."""
        for attribute in self.attributes:
            self._attributes_by_uid.setdefault(attribute.attribute_uid, attribute)
            self._attributes_by_system.setdefault(attribute.identifier_system, attribute)
        for published_type in self.tracked_entity_types:
            self._types_by_uid.setdefault(published_type.uid, published_type)

    def serves_tracked_entities(self) -> bool:
        """True when the guide published a tracked entity type, which is what a DHIS2 search requires."""
        return bool(self.tracked_entity_types)

    def tracked_entity_type_uids(self) -> tuple[str, ...]:
        """Every tracked entity type the published forms register, in the order they register them."""
        return tuple(published.uid for published in self.tracked_entity_types)

    def tracked_entity_type(self, tracked_entity_type_uid: str) -> PublishedTrackedEntityType | None:
        """What the guide publishes about one tracked entity type, or None when it publishes none."""
        return self._types_by_uid.get(tracked_entity_type_uid)

    def attribute(self, attribute_uid: str) -> PublishedAttribute | None:
        """What the guide publishes about one tracked entity attribute, or None when it publishes none."""
        return self._attributes_by_uid.get(attribute_uid)

    def attribute_for_system(self, system: str) -> PublishedAttribute | None:
        """The attribute whose values are carried under one identifier system, or None."""
        return self._attributes_by_system.get(system)

    def search_key_attributes(self) -> tuple[PublishedAttribute, ...]:
        """Every attribute DHIS2 declares unique or searchable - the set a bare identifier value is searched across."""
        return tuple(attribute for attribute in self.attributes if attribute.is_search_key())

    def program_name(self, program_uid: str) -> str | None:
        """The name this guide publishes one program under, or None when the program is outside its selection."""
        return self.program_names.get(program_uid)

    def organisation_unit_name(self, organisation_unit_uid: str) -> str | None:
        """The name this guide publishes one organisation unit under, or None when the registry omits it."""
        return self.organisation_unit_names.get(organisation_unit_uid)


def _identifier_values(entry: StoreEntry, system: str) -> tuple[str, ...]:
    """Every value one resource carries under one identifier system, in the order it carries them."""
    return tuple(token.value for token in entry.identifiers if token.system == system)


def _record_name(entry: StoreEntry, system: str, names: dict[str, str], element: str) -> None:
    """Join the DHIS2 UIDs a resource carries under one system to the name it is published under."""
    name = entry.body.get(element)
    if not isinstance(name, str) or not name:
        return
    for uid in _identifier_values(entry, system):
        names.setdefault(uid, name)


def _registered_types(
    registered_type_uids: list[str], mapping: dict[str, PublishedTrackedEntityType]
) -> tuple[PublishedTrackedEntityType, ...]:
    """Every type the forms register, each carrying what the published map says it is served as.

    A type the map names is that map's row verbatim. A type it does not name is a `Patient` with no
    published display, which is the same default the map was generated under - a project whose forms
    register a type its own vocabulary skipped has still said, by saying nothing, that the type is a
    person. Order is the order the forms register the types in, because that is the order the
    listing pages through them.
    """
    return tuple(mapping.get(uid, PublishedTrackedEntityType(uid=uid)) for uid in dict.fromkeys(registered_type_uids))


def _mapped_tracked_entity_types(entry: StoreEntry) -> dict[str, PublishedTrackedEntityType]:
    """Read `D2TET_CM` into what the guide states per type, or nothing when the document cannot be read.

    One row is one type: the element's code is the tracked entity type UID, its display is the name
    the instance holds, and the first target's code is the FHIR resource type its registrations are
    published as. A row targeting nothing states no resource, so it takes the same `Patient` default
    an absent row does rather than dropping the type out of the register.
    """
    try:
        concept_map = ConceptMap.model_validate(entry.body)
    except ValidationError as error:
        logger.warning("%s: D2TET_CM holds elements this server cannot read (%s)", entry.source, error)
        return {}
    mapped: dict[str, PublishedTrackedEntityType] = {}
    for group in concept_map.group or []:
        for element in group.element or []:
            if element.code is None:
                continue
            targets = [target.code for target in element.target or [] if target.code]
            mapped.setdefault(
                element.code,
                PublishedTrackedEntityType(
                    uid=element.code,
                    name=element.display,
                    resource_type=targets[0] if targets else DEFAULT_SUBJECT_RESOURCE_TYPE,
                ),
            )
    return mapped


def _published_attributes(entry: StoreEntry, identifier_system_base: str) -> tuple[PublishedAttribute, ...]:
    """Read `D2TEA_CS` into what the guide states per attribute, or nothing when the document cannot be read."""
    try:
        code_system = CodeSystem.model_validate(entry.body)
    except ValidationError as error:
        logger.warning("%s: D2TEA_CS holds elements this server cannot read (%s)", entry.source, error)
        return ()
    published: list[PublishedAttribute] = []
    for concept in code_system.concept or []:
        if concept.code is None:
            continue
        code: str | None = None
        unique = False
        searchable = False
        for concept_property in concept.property or []:
            if concept_property.code == CODE_CONCEPT_PROPERTY:
                code = concept_property.valueString
            elif concept_property.code == UNIQUE_CONCEPT_PROPERTY:
                unique = bool(concept_property.valueBoolean)
            elif concept_property.code == SEARCHABLE_CONCEPT_PROPERTY:
                searchable = bool(concept_property.valueBoolean)
        published.append(
            PublishedAttribute(
                attribute_uid=concept.code,
                display=concept.display,
                code=code,
                unique=unique,
                searchable=searchable,
                identifier_system=tracked_entity_attribute_identifier_system(identifier_system_base, concept.code),
            )
        )
    return tuple(published)

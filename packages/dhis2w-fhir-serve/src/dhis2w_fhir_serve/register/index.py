"""What the published guide already says about the instance's tracked entities, read once at startup.

An identifier search arrives as `system|value` and has to become a DHIS2 query. Everything needed
for that translation is already in the store, put there by the generate targets:

- A registration Questionnaire carries the tracked entity type it registers, under
  `{base}/id/tracked-entity-type`. The set of those values is the set of types this project's forms
  register into, and one of them is what `/api/tracker/trackedEntities` requires - the endpoint
  refuses a query naming neither a type nor a program (E1003).
- That same form's questions ARE that type's attributes: one question per attribute, keyed by the
  attribute's DHIS2 UID, and a `#choice` question naming the ValueSet DHIS2's option set is
  published as. So the form answers two things nothing else does - which attributes each type
  collects, and which of them have a vocabulary a caller could enumerate - and those are exactly
  what the register declares as filterable (`register.filtering`). `D2TEA_CS` cannot answer either:
  it publishes every attribute the project's forms ask anywhere, without saying whose.
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

ONE FACT HERE COMES FROM `fhir.toml` RATHER THAN FROM THE GUIDE. `[ips.identity]`
nominates which tracked entity attribute carries a person's name, birth date, and sex, and the guide
publishes that nomination nowhere: `D2TEA_CS` states what an attribute is called and what type its
values are, and no artifact states what one *means*. So the nominations are read from the project
here and checked against the vocabulary while the server starts - a nomination whose published value
type cannot fill the element it was nominated for refuses the run, naming the key and the type it
found (`docs/fhir/design/ips.md` section 4, "Value-shape validation"). The map from a sex value onto
`administrative-gender` is published as a ConceptMap by `d2w fhir generate`, so a consumer audits the
translation without holding this file, but what the server performs it reads from the file - the
nominations the map depends on are not published, and half a dial read from an artifact and half
from a file would be worse than either. `[ips.sections]` is read the same way and for the same
reason, by `dhis2w_fhir_serve.routes.summary` rather than here: a section mapping says what a
summary carries and nothing about the register.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dhis2w_fhir.foundation.tracked_entity_attribute_values import (
    tracked_entity_attribute_identifier_system,
    tracked_entity_attribute_value_extension_url,
)
from dhis2w_fhir.ips import IdentityNominations, nominated_value_type_issues
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

#: The `D2TEA_CS` concept properties this index reads: the DHIS2 code, the two flags that make an
#: attribute a search key - uniqueness, and the searchability DHIS2 declares for a lookup - and the
#: DHIS2 value type an identity nomination is checked against.
CODE_CONCEPT_PROPERTY = "dhis2-code"
UNIQUE_CONCEPT_PROPERTY = "unique"
SEARCHABLE_CONCEPT_PROPERTY = "searchable"
VALUE_TYPE_CONCEPT_PROPERTY = "value-type"

logger = logging.getLogger(LOGGER_NAME)


class NominatedAttributeError(ValueError):
    """A `[ips.identity]` nomination the published vocabulary says cannot fill the element it names.

    Raised while the index is built, so a run that would publish a birth date read off a phone number
    never opens its socket. It is the failure mode `[generate.tracked_entity_types]` has for a
    resource type that is not one, moved to the one check that needs the guide in hand.
    """


class PublishedAttribute(BaseModel):
    """One tracked entity attribute the guide publishes, and what it says about it."""

    model_config = ConfigDict(frozen=True)

    attribute_uid: str
    display: str | None = None
    code: str | None = None
    unique: bool = False
    searchable: bool = False
    """Whether DHIS2 declares the attribute searchable in any context this guide publishes."""

    value_type: str | None = None
    """The DHIS2 value type `D2TEA_CS` publishes for the attribute, or None where it publishes none."""

    identifier_system: str
    """The system a value of this attribute is carried under when DHIS2 declares the attribute unique."""

    value_set: str | None = None
    """The ValueSet a registration form binds the attribute's answers to, where DHIS2 binds an option set.

    Read off the published form rather than off `D2TEA_CS`, because the option set is a binding
    rather than a property of the attribute: the vocabulary already rides the question as
    `answerValueSet`, and the concepts in it are already published as a CodeSystem beside it. A
    consumer offered the value filter reads this canonical to draw the values as a choice; an
    attribute nothing binds carries None, and its values are whatever text the instance holds.
    """

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
    tracked_entity_type_attribute_uids: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    """Which tracked entity attributes each registered type's own forms ask, in the order they ask them.

    The join is one registration form's `linkId`s onto the type that form registers: a registration
    Questionnaire's questions ARE the type's attributes, one question per attribute, each keyed by
    the attribute's DHIS2 UID. Two forms registering one type - the program's and the type's own -
    contribute one union, because a person registered through either holds the same attributes.

    `attributes` alone cannot answer this: `D2TEA_CS` publishes every attribute the project's forms
    ask anywhere, so a register of specimens would otherwise declare a person's date of birth
    filterable. What a type collects is the form's to say.
    """

    program_names: dict[str, str] = Field(default_factory=dict)
    organisation_unit_names: dict[str, str] = Field(default_factory=dict)
    identity: IdentityNominations = Field(default_factory=IdentityNominations)
    """The `[ips.identity]` nominations this project states - the one fact here read from `fhir.toml`."""

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
        asked: dict[str, dict[str, None]] = {}
        bound_value_sets: dict[str, str] = {}
        for entry in store.entries:
            if entry.resource_type == QUESTIONNAIRE_RESOURCE_TYPE:
                registered = _identifier_values(entry, tracked_entity_type_system)
                if not registered:
                    continue
                registered_type_uids.extend(registered)
                _record_asked_attributes(entry, registered, asked, bound_value_sets)
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
        identity = project.config.ips.identity
        attributes = _bound(attributes, bound_value_sets)
        _refuse_unfillable_nominations(identity, attributes)
        return cls(
            tracked_entity_system=f"{base}/id/{TRACKED_ENTITY_IDENTIFIER_SEGMENT}",
            tracked_entity_type_system=tracked_entity_type_system,
            attribute_value_extension_url=tracked_entity_attribute_value_extension_url(
                project.config.generate, project.config.ig.canonical
            ),
            identifier_system_base=base,
            tracked_entity_types=_registered_types(registered_type_uids, mapping),
            attributes=attributes,
            tracked_entity_type_attribute_uids={
                type_uid: tuple(attribute_uids) for type_uid, attribute_uids in asked.items()
            },
            program_names=program_names,
            organisation_unit_names=organisation_unit_names,
            identity=identity,
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

    def attributes_asked_of(self, tracked_entity_type_uid: str) -> tuple[PublishedAttribute, ...]:
        """The attributes one tracked entity type's registration forms ask, in the order they ask them.

        An attribute a form asks and `D2TEA_CS` publishes nothing about is still one of them, carrying
        the identifier system its UID gives it and nothing else - the same reading `_attributes_named`
        takes of an attribute an operator names, and for the same reason: the instance holds the
        values whether or not this project's vocabulary happened to describe them.
        """
        return tuple(
            self._attributes_by_uid.get(attribute_uid)
            or PublishedAttribute(
                attribute_uid=attribute_uid,
                identifier_system=tracked_entity_attribute_identifier_system(
                    self.identifier_system_base, attribute_uid
                ),
            )
            for attribute_uid in self.tracked_entity_type_attribute_uids.get(tracked_entity_type_uid, ())
        )

    def search_key_attributes(self) -> tuple[PublishedAttribute, ...]:
        """Every attribute DHIS2 declares unique or searchable - the set a bare identifier value is searched across."""
        return tuple(attribute for attribute in self.attributes if attribute.is_search_key())

    def program_name(self, program_uid: str) -> str | None:
        """The name this guide publishes one program under, or None when the program is outside its selection."""
        return self.program_names.get(program_uid)

    def program_uids(self) -> tuple[str, ...]:
        """Every program this guide publishes, in the order it published them.

        A sync's enrollment poll needs these because `/api/tracker/enrollments` will be scoped by
        program and by nothing else - it answers `E1003 "Program is mandatory"` to a query naming a
        tracked entity type (BUGS.md 102). So the programs the guide published are the scope an
        enrollment poll walks, where every other register read walks the types the register serves.
        """
        return tuple(self.program_names)

    def organisation_unit_name(self, organisation_unit_uid: str) -> str | None:
        """The name this guide publishes one organisation unit under, or None when the registry omits it."""
        return self.organisation_unit_names.get(organisation_unit_uid)


def _identifier_values(entry: StoreEntry, system: str) -> tuple[str, ...]:
    """Every value one resource carries under one identifier system, in the order it carries them."""
    return tuple(token.value for token in entry.identifiers if token.system == system)


def _record_asked_attributes(
    entry: StoreEntry,
    registered_type_uids: tuple[str, ...],
    asked: dict[str, dict[str, None]],
    bound_value_sets: dict[str, str],
) -> None:
    """Join one registration form's questions onto the type it registers, and onto what they bind.

    A registration Questionnaire asks one question per tracked entity attribute, keyed by the
    attribute's DHIS2 UID - so the form's `linkId`s are the attributes that type collects, in the
    order the instance orders them. A `#choice` question names the ValueSet its answers come from,
    which is the option set DHIS2 binds the attribute to, and that canonical is the one thing a
    consumer needs to offer the attribute's values as a choice rather than as a text box.
    """
    for link_id, value_set in _questions(entry.body.get("item")).items():
        for type_uid in registered_type_uids:
            asked.setdefault(type_uid, {})[link_id] = None
        if value_set is not None:
            bound_value_sets.setdefault(link_id, value_set)


def _questions(items: Any) -> dict[str, str | None]:
    """Every question one form asks, keyed by its `linkId`, carrying the ValueSet it binds if any.

    Walked rather than read one level deep: nothing stops a registration form grouping its questions,
    and a grouped attribute is one the register would otherwise silently decline to filter by.
    """
    found: dict[str, str | None] = {}
    if not isinstance(items, list):
        return found
    for item in items:
        if not isinstance(item, dict):
            continue
        link_id = item.get("linkId")
        if isinstance(link_id, str) and link_id:
            value_set = item.get("answerValueSet")
            found.setdefault(link_id, value_set if isinstance(value_set, str) and value_set else None)
        for nested_link_id, nested_value_set in _questions(item.get("item")).items():
            found.setdefault(nested_link_id, nested_value_set)
    return found


def _bound(
    attributes: tuple[PublishedAttribute, ...], bound_value_sets: dict[str, str]
) -> tuple[PublishedAttribute, ...]:
    """Carry each published attribute's option-set binding onto it, where a form binds one."""
    return tuple(
        attribute
        if attribute.attribute_uid not in bound_value_sets
        else attribute.model_copy(update={"value_set": bound_value_sets[attribute.attribute_uid]})
        for attribute in attributes
    )


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
        value_type: str | None = None
        unique = False
        searchable = False
        for concept_property in concept.property or []:
            if concept_property.code == CODE_CONCEPT_PROPERTY:
                code = concept_property.valueString
            elif concept_property.code == VALUE_TYPE_CONCEPT_PROPERTY:
                value_type = concept_property.valueCode or concept_property.valueString
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
                value_type=value_type,
                identifier_system=tracked_entity_attribute_identifier_system(identifier_system_base, concept.code),
            )
        )
    return tuple(published)


def _refuse_unfillable_nominations(identity: IdentityNominations, attributes: tuple[PublishedAttribute, ...]) -> None:
    """Refuse the run when a nominated attribute's published value type cannot fill its FHIR element.

    An attribute the guide publishes nothing about is not refused - it is outside this project's
    selection, and the run is told so once rather than stopped. `[serve.tracked_entities]
    search_attributes` already settles that an operator naming an attribute outstates what the
    vocabulary happens to carry about it, and the nomination is read either way.
    """
    if not identity.nominates_anything():
        return
    value_types = {
        attribute.attribute_uid: attribute.value_type for attribute in attributes if attribute.value_type is not None
    }
    issues = nominated_value_type_issues(identity, value_types)
    if issues:
        # Logged before it is raised, because the store is built inside the server's own startup:
        # what reaches the terminal otherwise is a traceback with the sentence at the bottom of it,
        # and the sentence is the whole of what an operator has to read.
        refusal = "\n".join(issue.message() for issue in issues)
        for line in refusal.splitlines():
            logger.error("%s", line)
        raise NominatedAttributeError(refusal)
    for attribute_uid in identity.nominated_attribute_uids():
        if attribute_uid not in value_types:
            logger.warning(
                "[ips.identity] nominates tracked entity attribute %s, which this guide publishes nothing "
                "about: its value type could not be checked, and its values are served as nominated",
                attribute_uid,
            )

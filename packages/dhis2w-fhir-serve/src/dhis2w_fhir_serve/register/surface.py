"""What this run serves: what the guide published, narrowed by what `[serve.tracked_entities]` says.

Two sources decide the register, and they answer different questions. `TrackedEntityIndex` reads the
published guide and answers "what does this project know about the instance's subjects" - which
tracked entity types its forms register, which FHIR resource each of them is published as, which
attributes DHIS2 declares unique or searchable, what each identifier system means.
`[serve.tracked_entities]` is the operator's own statement and answers "what may this process say
about them" - whether the register exists at all, whether it lists, and which of the published types
and attributes are in scope.

The narrowing rules, each stated once here so no route re-derives them:

- **The types.** Empty config means the types the published forms register. A stated list is used
  verbatim, for both search and listing - it is a restriction the operator wrote down, and
  intersecting it with the published set would silently serve nothing when a project's forms and its
  `[serve.tracked_entities]` disagree, which is a config error worth surfacing as an empty answer to
  a named type rather than as a mystery. A stated type the guide never published is still served, as
  the `Patient` every unmapped type is.
- **The search keys.** Empty config means the attributes DHIS2 declares unique **or** searchable.
  Uniqueness makes a value name a subject; searchability is DHIS2's own statement that a clerk looks
  people up by it, and a clinic finding a woman by her first name is doing the ordinary thing rather
  than the exceptional one. A stated list is the key set outright, unique or searchable or neither:
  an instance that enforces nothing on the number a district actually files people under still has
  one, and the operator naming it has said so.

What the surface deliberately does not touch is the projection. A served resource still carries as
`identifier[]` exactly the values of the attributes DHIS2 declares unique, whatever this table names
or this server searches, because that element states what the instance enforces and not what this
process looks under.

**Resources come from the published map, never from config.** `register_resource_types` is the set of
FHIR resource types `D2TET_CM` takes the in-scope types onto, and each resource is served over its
own types alone: a `GET /Specimen` searches the types published as Specimen and no others, so a
sample never comes back as a person.
"""

from __future__ import annotations

from dhis2w_fhir.config import TrackedEntitiesConfig
from dhis2w_fhir.foundation.tracked_entity_attribute_values import tracked_entity_attribute_identifier_system
from dhis2w_fhir.r4.schemas import DEFAULT_SUBJECT_RESOURCE_TYPE
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.register.index import PublishedAttribute, PublishedTrackedEntityType, TrackedEntityIndex


class ServedRegister(BaseModel):
    """One FHIR resource type this run serves, and the tracked entity types that ride it."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    tracked_entity_types: tuple[PublishedTrackedEntityType, ...] = ()


class RegisterSurface(BaseModel):
    """What this process answers for: the published index, narrowed by `[serve.tracked_entities]`."""

    model_config = ConfigDict(frozen=True)

    index: TrackedEntityIndex
    tracked_entities: TrackedEntitiesConfig
    served_types: tuple[PublishedTrackedEntityType, ...] = ()
    """The types a search and a listing run over - the published ones, or the ones the table names."""

    search_attributes: tuple[PublishedAttribute, ...] = ()
    """The attributes a bare identifier value is searched across, and whose systems name a key."""

    @classmethod
    def resolve(cls, index: TrackedEntityIndex, tracked_entities: TrackedEntitiesConfig) -> RegisterSurface:
        """Narrow one published index by one `[serve.tracked_entities]` table, once, at startup."""
        stated_types = tuple(tracked_entities.tracked_entity_types)
        stated_attributes = tuple(tracked_entities.search_attributes)
        keys = _attributes_named(index, stated_attributes) if stated_attributes else index.search_key_attributes()
        return cls(
            index=index,
            tracked_entities=tracked_entities,
            served_types=_types_named(index, stated_types) if stated_types else index.tracked_entity_types,
            search_attributes=tuple(keys),
        )

    def serves_tracked_entities(self) -> bool:
        """True when this process answers about the instance at all: the table allows it, and a type is in scope."""
        return self.tracked_entities.enabled and bool(self.served_types)

    def serves_listing(self) -> bool:
        """True when a search naming no identifier is answered with a page rather than a refusal."""
        return self.serves_tracked_entities() and self.tracked_entities.listing

    def registers(self) -> tuple[ServedRegister, ...]:
        """One entry per FHIR resource type this register serves, in the order its types are registered."""
        grouped: dict[str, list[PublishedTrackedEntityType]] = {}
        for served in self.served_types:
            grouped.setdefault(served.resource_type, []).append(served)
        return tuple(
            ServedRegister(resource_type=resource_type, tracked_entity_types=tuple(types))
            for resource_type, types in grouped.items()
        )

    def register_resource_types(self) -> tuple[str, ...]:
        """Every resource type a register route answers on, which is what a read of that type dispatches to.

        A register with no type in scope still claims the default resource. Nothing is served under
        it, but the refusal a client reads then names the register and the line that switched it off,
        rather than saying this server does not serve `Patient` at all - which would be a different
        and less useful fact about a facade whose whole purpose is to serve people.
        """
        resource_types = tuple(register.resource_type for register in self.registers())
        return resource_types or (DEFAULT_SUBJECT_RESOURCE_TYPE,)

    def tracked_entity_type_uids_for(self, resource_type: str) -> tuple[str, ...]:
        """The types one resource is served over, in the order a listing pages through them."""
        return tuple(served.uid for served in self.served_types if served.resource_type == resource_type)

    def attribute_for_system(self, system: str) -> PublishedAttribute | None:
        """The search key one system names, or None when this surface holds no key under it."""
        for attribute in self.search_attributes:
            if attribute.identifier_system == system:
                return attribute
        return None


def _types_named(
    index: TrackedEntityIndex, tracked_entity_type_uids: tuple[str, ...]
) -> tuple[PublishedTrackedEntityType, ...]:
    """One entry per named type, in the order the table names them, published or not.

    A type the guide never published is served as the `Patient` an unmapped type is: the instance
    holds the entities, and a project whose forms happen not to register a type the operator serves
    has not thereby said what that type is.
    """
    return tuple(
        index.tracked_entity_type(uid) or PublishedTrackedEntityType(uid=uid) for uid in tracked_entity_type_uids
    )


def _attributes_named(index: TrackedEntityIndex, attribute_uids: tuple[str, ...]) -> list[PublishedAttribute]:
    """One key per named attribute, in the order the table names them, published or not.

    An attribute the guide never published is still a key: the instance holds the values, and a
    project whose forms happen not to ask for the number people are filed under has not thereby
    stopped that number naming them. Such a key carries the identifier system its UID gives it and
    nothing else the guide would have said about it.
    """
    keys: list[PublishedAttribute] = []
    for attribute_uid in attribute_uids:
        published = index.attribute(attribute_uid)
        keys.append(
            published
            if published is not None
            else PublishedAttribute(
                attribute_uid=attribute_uid,
                identifier_system=tracked_entity_attribute_identifier_system(
                    index.identifier_system_base, attribute_uid
                ),
            )
        )
    return keys

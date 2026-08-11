"""What this run serves for people: what the guide published, narrowed by what `[serve.patients]` says.

Two sources decide the Patient surface, and they answer different questions. `PatientIndex` reads
the published guide and answers "what does this project know about people" - which tracked entity
types its forms register into, which attributes DHIS2 declares unique, what each identifier system
means. `[serve.patients]` is the operator's own statement and answers "what may this process say
about them" - whether the surface exists at all, whether it lists, and which of the published types
and attributes are in scope.

The narrowing rules, each stated once here so no route re-derives them:

- **The types.** Empty config means the types the published forms register into. A stated list is
  used verbatim, for both search and listing - it is a restriction the operator wrote down, and
  intersecting it with the published set would silently serve nothing when a project's forms and
  its `[serve.patients]` disagree, which is a config error worth surfacing as an empty answer to a
  named type rather than as a mystery.
- **The identifier attributes.** Empty config means the attributes DHIS2 declares unique, which is
  what makes a value name a person rather than describe one. A stated list is the key set outright,
  uniqueness or not: an instance that enforces no uniqueness on the number a district actually
  files people under still has one, and the operator naming it has said so.

What the surface deliberately does not touch is the projection. A Patient still carries as
`identifier[]` exactly the values of the attributes DHIS2 declares unique, whatever this table
names, because that element states what the instance enforces and not what this process searches.
"""

from __future__ import annotations

from dhis2w_fhir.config import PatientsConfig
from dhis2w_fhir.foundation.tracked_entity_attribute_values import tracked_entity_attribute_identifier_system
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.patients.index import PatientIndex, PublishedAttribute


class PatientSurface(BaseModel):
    """The people this process answers for: the published index, narrowed by `[serve.patients]`."""

    model_config = ConfigDict(frozen=True)

    index: PatientIndex
    patients: PatientsConfig
    tracked_entity_type_uids: tuple[str, ...] = ()
    """The types a search and a listing run over - the published ones, or the ones the table names."""

    identifier_attributes: tuple[PublishedAttribute, ...] = ()
    """The attributes a bare identifier value is searched across, and whose systems name a key."""

    @classmethod
    def resolve(cls, index: PatientIndex, patients: PatientsConfig) -> PatientSurface:
        """Narrow one published index by one `[serve.patients]` table, once, at startup."""
        stated_types = tuple(patients.tracked_entity_types)
        stated_attributes = tuple(patients.search_attributes)
        keys = _attributes_named(index, stated_attributes) if stated_attributes else index.identifier_attributes()
        return cls(
            index=index,
            patients=patients,
            tracked_entity_type_uids=stated_types or index.tracked_entity_type_uids,
            identifier_attributes=tuple(keys),
        )

    def serves_patients(self) -> bool:
        """True when this process answers for people at all: the table allows it, and a type is in scope."""
        return self.patients.enabled and bool(self.tracked_entity_type_uids)

    def serves_listing(self) -> bool:
        """True when a `GET /Patient` naming no identifier is answered with a page rather than a refusal."""
        return self.serves_patients() and self.patients.listing

    def attribute_for_system(self, system: str) -> PublishedAttribute | None:
        """The identifier key one system names, or None when this surface holds no key under it."""
        for attribute in self.identifier_attributes:
            if attribute.identifier_system == system:
                return attribute
        return None


def _attributes_named(index: PatientIndex, attribute_uids: tuple[str, ...]) -> list[PublishedAttribute]:
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

"""One DHIS2 tracked entity as the FHIR resource its type is registered as - identity, and nothing invented.

WHY THE PROJECTION IS THE SAME WHATEVER THE RESOURCE IS. `D2TET_CM` says a type is served as a
`Patient`, a `Specimen`, a `Group` - and that is a statement about which resource the entity belongs
in, not a promise that DHIS2 holds what that resource defines. A Specimen here therefore carries no
`Specimen.type`, no `collection`, no `subject`: DHIS2 has no specimen-type field, no collection
event on a tracked entity, and no declared link from a sample to the person it came from. It has
tracked entity attributes, and which of them mean those things is a decision each instance makes for
itself, usually differently. The same holds for the people: `Patient.name`, `Patient.gender`, and
`Patient.birthDate` are the elements every FHIR client reaches for first, and none of them is filled
in, because DHIS2 has no first-name attribute, no sex attribute, no date-of-birth attribute. A server
that matched on attribute names would be inventing a semantic mapping and publishing it as fact - and
a wrong `gender` on a person, or a wrong `type` on a sample, is a worse answer than none. When an
instance nominates the mapping (roadmap decision 5.2), the nomination is what fills those elements;
until then a registered resource answers exactly one question, which is what this thing is in this
instance.

WHAT IT DOES CARRY, and where each fact comes from:

- `resourceType` is what the published map takes the entity's tracked entity type onto.
- `id` is the DHIS2 tracked entity UID, so `{resourceType}/<uid>` reads back the same entity.
- `identifier[]` opens with that UID under `{base}/id/tracked-entity` - the very system a
  QuestionnaireResponse names its subject under, so a capture client and a lookup speak one
  language - and then carries one entry per value of an attribute DHIS2 declares **unique**, under
  `{base}/tracked-entity-attribute/{uid}`. Uniqueness is what makes a value name a subject rather
  than describe one; the guide already publishes the flag as a `D2TEA_CS` concept property. A
  searchable attribute that is not unique is a key this server looks under, not an identifier the
  instance enforces, so it rides the extensions with everything else.
- `meta.tag` states the tracked entity type, under `{base}/id/tracked-entity-type`. A tag is R4's
  element for classifying a resource, and the type is a classification rather than a name, so it
  does not belong in `identifier[]` - and stating it as a tag needs no StructureDefinition to
  resolve, which matters because live mode serves none.
- `extension[]` carries every remaining attribute value on the `D2TrackedEntityAttributeValue`
  extension: the attribute's UID, the DHIS2 code when the instance set one, and the value as the
  string DHIS2 sent. Untyped on purpose - it is DHIS2's own value, not a FHIR reading of it.

Values are read off the entity and off its enrollments alike, deduplicated by attribute and value.
A DHIS2 attribute may be collected at the tracked entity type or at the program, and an entity found
by a program attribute's unique value that then came back not carrying it would be an answer
contradicting the question that found it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.tracked_entity_attribute_values import (
    TrackedEntityAttributeValueIn,
    tracked_entity_attribute_identifiers,
    tracked_entity_attribute_value_extensions,
)
from dhis2w_fhir.r4 import Coding, Identifier, Meta, RegisteredEntity

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import TrackerAttribute, TrackerTrackedEntity

    from dhis2w_fhir_serve.register.index import TrackedEntityIndex


def registered_entity_for(
    entity: TrackerTrackedEntity, index: TrackedEntityIndex, resource_type: str
) -> RegisteredEntity:
    """Project one tracked entity onto the resource this server serves it as."""
    tracked_entity_uid = entity.trackedEntity or ""
    values = attribute_values(entity, index)
    identifiers = [Identifier(system=index.tracked_entity_system, value=tracked_entity_uid)]
    identifiers.extend(tracked_entity_attribute_identifiers(values, index.identifier_system_base))
    extensions = tracked_entity_attribute_value_extensions(values, index.attribute_value_extension_url)
    return RegisteredEntity(
        resourceType=resource_type,
        id=tracked_entity_uid,
        meta=_type_tag(entity, index),
        identifier=identifiers,
        extension=extensions or None,
    )


def attribute_values(entity: TrackerTrackedEntity, index: TrackedEntityIndex) -> list[TrackedEntityAttributeValueIn]:
    """Every attribute value the entity holds, entity-level and enrollment-level, each carried once.

    The join onto the guide is what decides how a value is carried: `unique` makes it an identifier,
    and the DHIS2 code and display come from what `D2TEA_CS` published. An attribute the guide never
    published is still carried - the instance holds the value, and dropping it would make the served
    resource depend on which forms this project happened to select - it simply carries no code and is
    never treated as an identifier, because nothing here states that DHIS2 enforces its uniqueness.
    """
    carried: dict[tuple[str, str], TrackedEntityAttributeValueIn] = {}
    for attribute in _attributes(entity):
        if attribute.attribute is None or attribute.value is None:
            continue
        published = index.attribute(attribute.attribute)
        key = (attribute.attribute, attribute.value)
        carried.setdefault(
            key,
            TrackedEntityAttributeValueIn(
                attribute_uid=attribute.attribute,
                value=attribute.value,
                display=published.display if published is not None else attribute.displayName,
                code=published.code if published is not None else attribute.code,
                unique=published.unique if published is not None else False,
            ),
        )
    return list(carried.values())


def _attributes(entity: TrackerTrackedEntity) -> list[TrackerAttribute]:
    """The entity's own attribute values first, then the ones its enrollments carry."""
    attributes = list(entity.attributes or [])
    for enrollment in entity.enrollments or []:
        attributes.extend(enrollment.attributes or [])
    return attributes


def _type_tag(entity: TrackerTrackedEntity, index: TrackedEntityIndex) -> Meta | None:
    """State the tracked entity type as a resource tag, or nothing when the instance named none."""
    if entity.trackedEntityType is None:
        return None
    return Meta(tag=[Coding(system=index.tracked_entity_type_system, code=entity.trackedEntityType)])

"""The D2TrackedEntityAttributeValue extension: what a tracked entity holds, and how a unique value names it.

A tracked entity attribute value is a DHIS2 answer about a person - a phone number, a household
size, a consent flag - and FHIR has no element to put an arbitrary one of those on a Patient. So it
maps onto a complex extension, in the shape `D2AttributeValue` already established for the metadata
attribute values a generated resource carries: the attribute's UID, the code DHIS2 gave it, and the
value. It is a family of its own rather than a second context on `D2AttributeValue` because a
tracked entity attribute is a different DHIS2 object from a metadata attribute, and one extension
claiming to carry both would publish a definition that is false of half its instances.

A value of an attribute DHIS2 declares **unique** is a different thing again: it names the person
rather than describing them, which is exactly what a FHIR `Identifier` is for. Those values leave
the extension and join the resource's identifier list under a namespace of their own,
`{identifier_system_base}/tracked-entity-attribute/{attribute_uid}` - keyed on the UID for the same
reason the metadata-attribute family is, and declared by convention rather than as a NamingSystem
for the same reason: the foundation layer is built from `fhir.toml` alone and never reads an
instance, so it cannot know which tracked entity attributes exist, let alone which are unique.

Which attributes are unique is not a fact this module reads. `D2TEA_CS` publishes a `unique`
boolean per concept, so the guide already states it, and a caller joins the two before building a
value list. `dhis2w_fhir_serve.register.index` is the worked example.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.r4 import Extension, Identifier

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

#: The resource types D2TrackedEntityAttributeValue is contexted on - the projection of a person.
TRACKED_ENTITY_ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES = ("Patient",)

#: The sub-extension carrying the tracked entity attribute's UID - always emitted.
TRACKED_ENTITY_ATTRIBUTE_ID_SUB_EXTENSION = "attributeId"

#: The sub-extension carrying the tracked entity attribute's code - omitted when the instance left it unset.
TRACKED_ENTITY_ATTRIBUTE_CODE_SUB_EXTENSION = "attributeCode"

#: The sub-extension carrying the value the tracked entity holds - always emitted, always a string.
TRACKED_ENTITY_ATTRIBUTE_VALUE_SUB_EXTENSION = "value"

#: The path segment the per-attribute identifier namespaces sit under, one namespace per attribute UID.
TRACKED_ENTITY_ATTRIBUTE_IDENTIFIER_SEGMENT = "tracked-entity-attribute"


class TrackedEntityAttributeValueIn(BaseModel):
    """One tracked entity attribute value, joined to what the guide publishes about the attribute.

    `code` is None for an attribute the instance left uncoded - DHIS2 requires no code on a tracked
    entity attribute - and no `attributeCode` sub-extension is written for it. `unique` is what
    decides whether the value is an identifier or an extension, and it is read from the `unique`
    property `D2TEA_CS` publishes rather than from the value itself.
    """

    model_config = ConfigDict(frozen=True)

    attribute_uid: str
    value: str
    display: str | None = None
    code: str | None = None
    unique: bool = False


def tracked_entity_attribute_value_extension_url(config: GenerateConfig, canonical: str) -> str:
    """Canonical URL of the D2TrackedEntityAttributeValue StructureDefinition under the run's naming tokens."""
    names = FoundationNaming.from_naming(config.naming)
    return f"{canonical}/StructureDefinition/{names.tracked_entity_attribute_value_extension_id}"


def tracked_entity_attribute_identifier_system(identifier_system_base: str, attribute_uid: str) -> str:
    """The identifier system one unique tracked entity attribute's values are carried under."""
    return f"{identifier_system_base}/{TRACKED_ENTITY_ATTRIBUTE_IDENTIFIER_SEGMENT}/{attribute_uid}"


def tracked_entity_attribute_value_extensions(
    attribute_values: list[TrackedEntityAttributeValueIn], url: str
) -> list[Extension]:
    """Build one extension per describing attribute value, in the order the values were given.

    A value of a unique attribute is skipped here: it rides `tracked_entity_attribute_identifiers`
    as an Identifier instead, so no value is carried twice.
    """
    return [
        Extension(url=url, extension=_sub_extensions(attribute_value))
        for attribute_value in attribute_values
        if not attribute_value.unique
    ]


def tracked_entity_attribute_identifiers(
    attribute_values: list[TrackedEntityAttributeValueIn], identifier_system_base: str
) -> list[Identifier]:
    """Build one Identifier per unique attribute value, in the order the values were given.

    The companion of `tracked_entity_attribute_value_extensions` over the same list: between them
    every value the tracked entity holds is emitted exactly once.
    """
    return [
        Identifier(
            system=tracked_entity_attribute_identifier_system(identifier_system_base, attribute_value.attribute_uid),
            value=attribute_value.value,
        )
        for attribute_value in attribute_values
        if attribute_value.unique
    ]


def _sub_extensions(attribute_value: TrackedEntityAttributeValueIn) -> list[Extension]:
    """The nested extensions of one value: the attribute UID, its code when there is one, then the value."""
    nested = [Extension(url=TRACKED_ENTITY_ATTRIBUTE_ID_SUB_EXTENSION, valueString=attribute_value.attribute_uid)]
    if attribute_value.code is not None:
        nested.append(Extension(url=TRACKED_ENTITY_ATTRIBUTE_CODE_SUB_EXTENSION, valueString=attribute_value.code))
    nested.append(Extension(url=TRACKED_ENTITY_ATTRIBUTE_VALUE_SUB_EXTENSION, valueString=attribute_value.value))
    return nested

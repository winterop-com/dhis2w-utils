"""The D2AttributeValue extension: where it is contexted, and the R4 elements the emitters build from it.

A DHIS2 attribute value is an arbitrary key-value pair any metadata object can carry - a national
registry id on a facility, an ICD-10 code on a data element - so it maps onto a complex extension
rather than onto any one FHIR element. The extension is defined in `foundation/`, alongside
D2Period and D2FormType, and every generated resource that can carry one lists it as a context.

A value of an attribute DHIS2 declares **unique** is a different thing: it names its object rather
than annotating it, which is exactly what a FHIR `Identifier` is for. Those values leave the
extension and join the resource's identifier list under a namespace of their own,
`{identifier_system_base}/attribute/{attribute_uid}` - keyed on the UID because a DHIS2 attribute
code may hold spaces, which a system URI cannot.

Those per-attribute namespaces are declared by convention and not as NamingSystems. The foundation
layer is built from `fhir.toml` alone and never reads an instance, so it cannot know which
attributes exist, let alone which are unique - and a NamingSystem naming an attribute that does not
exist would be worse than none. `d2-naming-systems.fsh` therefore declares the fixed DHIS2
identifier systems only, and the `/attribute/<uid>` family is documented in the guide instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.r4 import Extension, Identifier

if TYPE_CHECKING:
    from dhis2w_fhir.attributes import AttributeCodeIndex, AttributeValueIn
    from dhis2w_fhir.config import GenerateConfig

#: The resource types D2AttributeValue is contexted on - every generated resource that carries one.
ATTRIBUTE_VALUE_CONTEXT_RESOURCE_TYPES = ("Organization", "Location", "CodeSystem", "ValueSet", "Questionnaire")

#: The sub-extension carrying the DHIS2 attribute's UID - always emitted.
ATTRIBUTE_ID_SUB_EXTENSION = "attributeId"

#: The sub-extension carrying the DHIS2 attribute's code - omitted when the instance left it unset.
ATTRIBUTE_CODE_SUB_EXTENSION = "attributeCode"

#: The sub-extension carrying the value the DHIS2 object holds - always emitted, always a string.
ATTRIBUTE_VALUE_SUB_EXTENSION = "value"

#: The path segment the per-attribute identifier namespaces sit under, one namespace per attribute UID.
ATTRIBUTE_IDENTIFIER_SEGMENT = "attribute"


def attribute_value_extension_url(config: GenerateConfig, canonical: str) -> str:
    """Canonical URL of the D2AttributeValue StructureDefinition under the run's naming tokens."""
    names = FoundationNaming.from_naming(config.naming)
    return f"{canonical}/StructureDefinition/{names.attribute_value_extension_id}"


def attribute_value_identifier_system(identifier_system_base: str, attribute_uid: str) -> str:
    """The identifier system one unique DHIS2 attribute's values are carried under."""
    return f"{identifier_system_base}/{ATTRIBUTE_IDENTIFIER_SEGMENT}/{attribute_uid}"


def attribute_value_extensions(
    attribute_values: list[AttributeValueIn], attribute_codes: AttributeCodeIndex, url: str
) -> list[Extension]:
    """Build one D2AttributeValue extension per annotating attribute value, in the order DHIS2 returned them.

    A value of a unique attribute is skipped here: it rides `attribute_value_identifiers` as an
    Identifier instead, so no value is carried twice.
    """
    return [
        Extension(url=url, extension=_sub_extensions(attribute_value, attribute_codes))
        for attribute_value in attribute_values
        if not attribute_codes.is_unique(attribute_value.attribute_uid)
    ]


def attribute_value_identifiers(
    attribute_values: list[AttributeValueIn], attribute_codes: AttributeCodeIndex, identifier_system_base: str
) -> list[Identifier]:
    """Build one Identifier per unique DHIS2 attribute value, in the order DHIS2 returned them.

    The companion of `attribute_value_extensions` over the same list: between them every attribute
    value the object carries is emitted exactly once. The emitters append these after the UID and
    code slices every resource already carries, so the identifier order stays stable across runs.
    """
    return [
        Identifier(
            system=attribute_value_identifier_system(identifier_system_base, attribute_value.attribute_uid),
            value=attribute_value.value,
        )
        for attribute_value in attribute_values
        if attribute_codes.is_unique(attribute_value.attribute_uid)
    ]


def _sub_extensions(attribute_value: AttributeValueIn, attribute_codes: AttributeCodeIndex) -> list[Extension]:
    """The nested extensions of one value: the attribute UID, its code when there is one, then the value.

    An attribute the instance left uncoded gets no `attributeCode` sub-extension at all rather than
    an empty one: DHIS2 codes few of its attributes, and an empty code would claim it coded this one.
    """
    code = attribute_codes.code_for(attribute_value.attribute_uid)
    nested = [Extension(url=ATTRIBUTE_ID_SUB_EXTENSION, valueString=attribute_value.attribute_uid)]
    if code is not None:
        nested.append(Extension(url=ATTRIBUTE_CODE_SUB_EXTENSION, valueString=code))
    nested.append(Extension(url=ATTRIBUTE_VALUE_SUB_EXTENSION, valueString=attribute_value.value))
    return nested

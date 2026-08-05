"""The D2AttributeValue extension: where it is contexted, and the R4 extensions the emitters build from it.

A DHIS2 attribute value is an arbitrary key-value pair any metadata object can carry - a national
registry id on a facility, an ICD-10 code on a data element - so it maps onto a complex extension
rather than onto any one FHIR element. The extension is defined in `foundation/`, alongside
D2Period and D2FormType, and every generated resource that can carry one lists it as a context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.foundation.schemas import FoundationNaming
from dhis2w_fhir.r4 import Extension

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


def attribute_value_extension_url(config: GenerateConfig, canonical: str) -> str:
    """Canonical URL of the D2AttributeValue StructureDefinition under the run's naming tokens."""
    names = FoundationNaming.from_naming(config.naming)
    return f"{canonical}/StructureDefinition/{names.attribute_value_extension_id}"


def attribute_value_extensions(
    attribute_values: list[AttributeValueIn], attribute_codes: AttributeCodeIndex, url: str
) -> list[Extension]:
    """Build one D2AttributeValue extension per DHIS2 attribute value, in the order DHIS2 returned them."""
    return [
        Extension(url=url, extension=_sub_extensions(attribute_value, attribute_codes))
        for attribute_value in attribute_values
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

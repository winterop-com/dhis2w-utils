"""The D2OriginalName and D2OriginalCode extensions: where they ride, and the URLs the emitters state them under.

A run under `[generate] hostile_names = "substitute"` publishes a DHIS2 name carrying `<` as the
words it stands for, and a DHIS2 code carrying a space with the space hyphenated. A concept states
the instance's own spelling beside the published one as a concept property; a resource whose whole
identity is one DHIS2 object has no concept to hang a property on, so it states the same two facts
as these extensions. They are definitions the guide ships, which is what makes them resolvable: a
concept-property URI names a property of a CodeSystem and defines no extension, so a resource
carrying one leaves the IG publisher with an extension it cannot find.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.coded import OriginalSpellingExtensionUrls
from dhis2w_fhir.foundation.schemas import FoundationNaming

if TYPE_CHECKING:
    from dhis2w_fhir.config import GenerateConfig

#: The resource types the two extensions are contexted on - every resource that is one DHIS2 object.
ORIGINAL_SPELLING_CONTEXT_RESOURCE_TYPES = ("CodeSystem", "ValueSet")


def original_spelling_extension_urls(config: GenerateConfig, canonical: str) -> OriginalSpellingExtensionUrls:
    """Canonical URLs of the two original-spelling StructureDefinitions under the run's naming tokens."""
    names = FoundationNaming.from_naming(config.naming)
    return OriginalSpellingExtensionUrls(
        code_url=f"{canonical}/StructureDefinition/{names.original_code_extension_id}",
        name_url=f"{canonical}/StructureDefinition/{names.original_name_extension_id}",
    )

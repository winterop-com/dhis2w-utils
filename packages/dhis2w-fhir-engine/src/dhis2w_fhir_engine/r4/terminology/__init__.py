"""FHIR R4 terminology services: code validation, value set membership, and subsumption.

Example:
    ```python
    from dhis2w_fhir_engine.r4.terminology import InMemoryTerminologyService, ValidateCodeRequest

    service = InMemoryTerminologyService()
    service.load_value_sets_from_directory("path/to/valuesets")

    request = ValidateCodeRequest(
        url="http://hl7.org/fhir/ValueSet/observation-status",
        code="final",
        system="http://hl7.org/fhir/observation-status",
    )
    result = service.validate_code(request)
    ```
"""

from .models import (
    CodeableConcept,
    Coding,
    MemberOfRequest,
    MemberOfResponse,
    SubsumesRequest,
    SubsumesResponse,
    ValidateCodeRequest,
    ValidateCodeResponse,
    ValueSet,
    ValueSetCompose,
    ValueSetComposeInclude,
    ValueSetComposeIncludeConcept,
    ValueSetExpansion,
    ValueSetExpansionContains,
)
from .service import (
    FHIRTerminologyService,
    InMemoryTerminologyService,
    TerminologyService,
)

__all__ = [
    # Models
    "Coding",
    "CodeableConcept",
    "ValueSet",
    "ValueSetCompose",
    "ValueSetComposeInclude",
    "ValueSetComposeIncludeConcept",
    "ValueSetExpansion",
    "ValueSetExpansionContains",
    "ValidateCodeRequest",
    "ValidateCodeResponse",
    "SubsumesRequest",
    "SubsumesResponse",
    "MemberOfRequest",
    "MemberOfResponse",
    # Services
    "TerminologyService",
    "InMemoryTerminologyService",
    "FHIRTerminologyService",
]

"""Scope a retrieve with a ValueSet, and answer code questions with a terminology service.

Coded data is where a measure gets specific. "Vaccinated" is not a field on a resource - it is a
`vaccineCode` matching one of a named set of codes, and that named set is a **ValueSet**: a URL
standing for a list of codes, published separately from the library that cites it.

CQL never inlines codes into logic. A library declares `valueset "Name": 'url'` in its header, and
writes `[Immunization: "Name"]`. The URL is resolved outside the library, by whatever holds
terminology - here `add_valueset` on the data source, in production a terminology server. So the same
library scores differently when the ValueSet is republished, which is the point.

The R4 subpackage also ships a terminology service, for the moment a client wants the same question
asked directly rather than folded into a retrieve: is this code a member of that ValueSet?

Usage:
    uv run python examples/fhir/engine/cql_terminology.py

Needs no DHIS2, no server, and no project: the Bundle and the ValueSet are inline.
"""

from __future__ import annotations

from _bundle import (
    DIPHTHERIA_VACCINE_CODE,
    MEASLES_VACCINE_CODE,
    MEASLES_VACCINES_VALUE_SET_URL,
    SNOMED,
    clinic_bundle,
)
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.engine.cql import CQLCode
from dhis2w_fhir_engine.r4 import (
    BundleDataSource,
    InMemoryTerminologyService,
    MemberOfRequest,
    ValidateCodeRequest,
    ValueSet,
)

LIBRARY_SOURCE = f"""
library Terminology version '1.0'
using FHIR version '4.0.1'

codesystem SNOMED: '{SNOMED}'
valueset "Measles Vaccines": '{MEASLES_VACCINES_VALUE_SET_URL}'
code "Diphtheria vaccine": '{DIPHTHERIA_VACCINE_CODE}' from SNOMED display 'Diphtheria vaccine'

define "Every Dose": [Immunization]
define "Measles Doses": [Immunization: "Measles Vaccines"]
define "Diphtheria Doses": [Immunization: "Diphtheria vaccine"]
"""

MEASLES_VALUE_SET = ValueSet.model_validate(
    {
        "resourceType": "ValueSet",
        "url": MEASLES_VACCINES_VALUE_SET_URL,
        "version": "1.0.0",
        "name": "MeaslesVaccines",
        "status": "active",
        "compose": {
            "include": [
                {
                    "system": SNOMED,
                    "concept": [{"code": MEASLES_VACCINE_CODE, "display": "Measles vaccine"}],
                }
            ]
        },
    }
)
"""The published ValueSet: one code, so a retrieve citing it reaches measles doses and nothing else."""


def main() -> None:
    """Scope one retrieve with a ValueSet and one with a single code, then query the terminology service."""
    data_source = BundleDataSource(clinic_bundle())

    # The data source is what resolves a ValueSet URL to codes. Until this line the URL names
    # nothing, and a retrieve citing it cannot narrow anything.
    data_source.add_valueset(
        MEASLES_VACCINES_VALUE_SET_URL,
        [CQLCode(code=MEASLES_VACCINE_CODE, system=SNOMED, display="Measles vaccine")],
    )

    evaluator = CQLEvaluator(data_source=data_source)
    evaluator.compile(LIBRARY_SOURCE)

    every_dose = evaluator.evaluate_definition("Every Dose")
    measles_doses = evaluator.evaluate_definition("Measles Doses")
    diphtheria_doses = evaluator.evaluate_definition("Diphtheria Doses")

    print(f"[Immunization]                         -> {len(every_dose)} dose(s)")
    print(f'[Immunization: "Measles Vaccines"]     -> {len(measles_doses)} dose(s)  (the ValueSet has one code)')
    print(f'[Immunization: "Diphtheria vaccine"]   -> {len(diphtheria_doses)} dose(s)  (the declared code, not a set)')
    print()
    print("which doses each retrieve reached:")
    print(f"  every dose      {[dose['id'] for dose in every_dose]}")
    print(f"  measles only    {[dose['id'] for dose in measles_doses]}")
    print(f"  diphtheria only {[dose['id'] for dose in diphtheria_doses]}")
    print()
    print("The library never named a code in its logic. Republish the ValueSet with a second measles")
    print("code and the same library counts differently - no edit, no recompile.")
    print()

    terminology = InMemoryTerminologyService()
    terminology.add_value_set(MEASLES_VALUE_SET)

    in_set = terminology.validate_code(
        ValidateCodeRequest(url=MEASLES_VACCINES_VALUE_SET_URL, code=MEASLES_VACCINE_CODE, system=SNOMED)
    )
    out_of_set = terminology.validate_code(
        ValidateCodeRequest(url=MEASLES_VACCINES_VALUE_SET_URL, code=DIPHTHERIA_VACCINE_CODE, system=SNOMED)
    )
    membership = terminology.member_of(
        MemberOfRequest(valueSetUrl=MEASLES_VACCINES_VALUE_SET_URL, code=MEASLES_VACCINE_CODE, system=SNOMED)
    )

    print("the same ValueSet asked directly, as FHIR's own terminology operations:")
    print(f"  $validate-code {MEASLES_VACCINE_CODE}    -> {in_set.result}")
    print(f"  $validate-code {DIPHTHERIA_VACCINE_CODE}    -> {out_of_set.result}")
    print(f"  memberOf       {MEASLES_VACCINE_CODE}    -> {membership.result}")
    print()
    print("Same question, two callers: a CQL retrieve narrowing itself, and a client checking one code.")


if __name__ == "__main__":
    main()

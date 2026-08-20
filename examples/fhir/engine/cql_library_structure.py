"""Read a CQL library header by header: what `library`, `using`, `include`, and `define` each declare.

CQL is written as a *library* - a named, versioned document with a header of declarations and a body
of `define` statements. Nothing in it is executed top to bottom: a `define` is a named expression the
caller asks for by name, and the engine works out what else it has to evaluate first.

The header is the part worth reading slowly, because it is where the outside world gets named:

* `library Name version 'x'` - the document's own identity, which is what a MeasureReport cites.
* `using FHIR version '4.0.1'` - the data model retrieves are written against.
* `include FHIRHelpers version '4.0.1'` - another library's definitions, reachable under an alias.
* `codesystem` / `valueset` / `code` / `concept` - terminology, named once, referred to by name after.
* `parameter` - a value the caller supplies, with a default when they do not.

One more declaration exists and this library leaves it out: `context Patient`, which says the
definitions below are evaluated once per person rather than once over the whole data set. That is
what a quality measure needs, so it is `measure_report.py` that shows it.

Usage:
    uv run python examples/fhir/engine/cql_library_structure.py

Needs no DHIS2, no server, and no project: the library and its data are inline.
"""

from __future__ import annotations

from _bundle import MEASLES_VACCINES_VALUE_SET_URL, clinic_bundle
from dhis2w_fhir_engine import CQLEvaluator
from dhis2w_fhir_engine.r4 import BundleDataSource
from pydantic import BaseModel

LIBRARY_SOURCE = f"""
library ChildImmunisation version '1.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1'

codesystem SNOMED: 'http://snomed.info/sct'
valueset "Measles Vaccines": '{MEASLES_VACCINES_VALUE_SET_URL}'
code "Measles vaccine": '836383007' from SNOMED display 'Measles vaccine'

parameter "Measurement Period" Interval<DateTime>
    default Interval[@2024-01-01T00:00:00.0, @2024-12-31T23:59:59.999]

define "Children": [Patient]

define "Doses": [Immunization]

define "Children Count": Count([Patient])

define "Any Dose Recorded": exists [Immunization]

define "Reporting Year": start of "Measurement Period"
"""

#: The definitions this example evaluates, in the order the library declares them.
DEFINITIONS_TO_EVALUATE = ("Children Count", "Any Dose Recorded", "Reporting Year")


class DeclarationSummary(BaseModel):
    """One header declaration kind and the names the compiled library holds under it."""

    kind: str
    names: list[str]

    def rendered(self) -> str:
        """The line as it prints: the declaration kind, then the names it introduced."""
        listed = ", ".join(self.names) if self.names else "-"
        return f"  {self.kind:14} {listed}"


def main() -> None:
    """Compile one library, print what its header declared, then evaluate three of its definitions."""
    evaluator = CQLEvaluator(data_source=BundleDataSource(clinic_bundle()))

    # compile() parses the whole document and returns the typed library; it evaluates nothing.
    library = evaluator.compile(LIBRARY_SOURCE)

    print(f"library {library.name} version {library.version}")
    print()
    print("what the header declared:")
    declarations = [
        DeclarationSummary(kind="using", names=[f"{using.model} {using.version}" for using in library.using]),
        DeclarationSummary(
            kind="include",
            names=[f"{include.library} {include.version}" for include in library.includes],
        ),
        DeclarationSummary(kind="codesystem", names=list(library.codesystems)),
        DeclarationSummary(kind="valueset", names=list(library.valuesets)),
        DeclarationSummary(kind="code", names=list(library.codes)),
        DeclarationSummary(kind="parameter", names=list(library.parameters)),
        DeclarationSummary(kind="define", names=evaluator.get_definitions()),
    ]
    for declaration in declarations:
        print(declaration.rendered())

    print()
    print("`include FHIRHelpers version '4.0.1'` needed no library path: the R4 binding ships it.")
    print()

    print("parameter defaults the caller did not override:")
    for name, value in evaluator.get_parameters().items():
        print(f"  {name}: {value}")

    print()
    print("definitions, asked for by name:")
    for name in DEFINITIONS_TO_EVALUATE:
        print(f"  {name:20} -> {evaluator.evaluate_definition(name)}")

    print()
    print("Nothing ran until a name was asked for. A library is a vocabulary, not a script.")


if __name__ == "__main__":
    main()

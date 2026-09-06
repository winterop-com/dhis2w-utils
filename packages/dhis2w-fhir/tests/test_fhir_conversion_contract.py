"""The conversion contract gate: the published logical model judges the forwarder's aggregate output.

`D2DataValueSet` is the `kind = logical` StructureDefinition the foundation target publishes for the
`/api/dataValueSets` envelope. `tests/data/r4/StructureDefinition-d2-data-value-set.json` is what
SUSHI compiled that FSH into, never edited by hand. This suite reads that compiled artifact, takes
the shape claims out of its differential - which elements exist, which are required, which repeat,
what type each carries - and holds every data value set the Python forwarder produces from the
conversion corpus against them.

What the gate proves:

- The forwarder writes no field the published contract does not declare, and leaves out no field it
  declares as required.
- Nothing the contract types as a single value arrives as a list, and nothing it types as repeating
  arrives as a scalar.
- Every value's JSON type is the one the contract states, and a `date` element really is a calendar
  date.
- The FSH the foundation target emits and the compiled artifact this gate reads are one thing: the
  differential is asserted equal to `DATA_VALUE_SET_ELEMENTS`, the declaration the FSH template is
  rendered from, so an edit to either without the other fails here.
- Every `evaluate` transform of the compiled map carries one parameter, the FHIRPath expression the
  publisher's validator holds it to, and names its variables inside that expression.

What the gate does NOT prove:

- That the StructureMap executes. Nothing in this project runs an FML engine, and the map is a
  contract rather than a runtime; a full engine execution of `D2AggregateResponseToDataValueSet`
  against these responses is out of scope.
- That the forwarder's *values* are right. The contract states shapes, not semantics: it cannot
  tell a correct data element UID from a wrong one, nor a correctly serialised decimal from a
  mangled one. `test_fhir_conversion_roundtrip.py` is the suite that grades the values, cell for
  cell, against the DHIS2 data the examples were built from.
- That DHIS2 accepts the payload. Only a real instance grades that, which is what the dry run of
  `d2w fhir forward` is for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from conversion_corpus import AGGREGATE_IDS, aggregate_payloads
from dhis2w_fhir.foundation import DATA_VALUE_SET_ELEMENTS
from pydantic import BaseModel, ConfigDict

_GOLDEN = Path(__file__).parent / "data" / "r4" / "StructureDefinition-d2-data-value-set.json"
_MAP_GOLDEN = Path(__file__).parent / "data" / "r4" / "StructureMap-d2-aggregate-response-to-data-value-set.json"

#: The FHIR `date` datatype, which is what the contract types `completeDate` as.
_FHIR_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

#: A variable reference inside a FHIRPath expression, which is how an `evaluate` transform reaches its source.
_VARIABLE = re.compile(r"%([A-Za-z][A-Za-z0-9]*)")

#: The FHIR type a nested group of elements carries; its value on the wire is a list of objects.
_BACKBONE = "BackboneElement"


class ContractElement(BaseModel):
    """One shape claim the compiled logical model makes, read straight off its differential."""

    model_config = ConfigDict(frozen=True)

    path: str
    """Dotted path relative to the model root, as the differential spells it minus the root segment."""

    minimum: int
    maximum: str
    element_type: str

    @property
    def required(self) -> bool:
        """Whether the contract says the envelope always carries this element."""
        return self.minimum >= 1

    @property
    def repeats(self) -> bool:
        """Whether the contract says the envelope carries this element more than once."""
        return self.maximum != "1"


def _contract() -> tuple[ContractElement, ...]:
    """Every shape claim the compiled `D2DataValueSet` makes, in the order it declares them."""
    definition = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    root = definition["id"]
    elements: list[ContractElement] = []
    for element in definition["differential"]["element"]:
        path = element["path"]
        if path == root:
            continue
        elements.append(
            ContractElement(
                path=path.removeprefix(f"{root}."),
                minimum=element["min"],
                maximum=element["max"],
                element_type=element["type"][0]["code"],
            )
        )
    return tuple(elements)


def _by_path() -> dict[str, ContractElement]:
    """The contract keyed by the path each claim is about."""
    return {element.path: element for element in _contract()}


def _wire(response_id: str) -> dict[str, Any]:
    """One aggregate response's payload exactly as `d2w fhir forward` posts it to `/api/dataValueSets`."""
    payload = aggregate_payloads()[response_id]
    return payload.model_dump(by_alias=True, exclude_none=True, mode="json")


def _violations(value: Any, element: ContractElement) -> list[str]:
    """Every way one carried value disagrees with the claim the contract makes about its element."""
    if element.repeats:
        if not isinstance(value, list):
            return [f"`{element.path}` repeats and arrived as {type(value).__name__}"]
        return [] if element.element_type == _BACKBONE else _scalar_violations(value, element)
    if isinstance(value, list):
        return [f"`{element.path}` is single-valued and arrived as a list"]
    return _scalar_violations([value], element)


def _scalar_violations(values: list[Any], element: ContractElement) -> list[str]:
    """Every way one element's carried scalars disagree with the FHIR type the contract states."""
    violations: list[str] = []
    for value in values:
        if not isinstance(value, str):
            violations.append(f"`{element.path}` is a {element.element_type} and arrived as {type(value).__name__}")
        elif element.element_type == "date" and _FHIR_DATE.match(value) is None:
            violations.append(f"`{element.path}` is a date and arrived as `{value}`")
    return violations


def test_the_compiled_contract_is_the_declaration_the_fsh_is_rendered_from() -> None:
    """One declaration, two readers: the emitted FSH and the artifact SUSHI compiled cannot drift apart."""
    declared = tuple(
        ContractElement(
            path=element.path,
            minimum=element.minimum,
            maximum=element.maximum,
            element_type=element.element_type,
        )
        for element in DATA_VALUE_SET_ELEMENTS
    )
    assert _contract() == declared


def test_the_compiled_map_reads_a_response_and_writes_the_model_published_beside_it() -> None:
    """SUSHI compiles the FSH-authored instance into the StructureMap resource a consumer reads.

    The map is a contract, so what is pinned here is its shape - the two structures it declares, the
    two groups, and that every element of the logical model is the target of a rule somewhere in
    them. Nothing executes it: an engine run is out of scope for the reasons stated at the top.
    """
    compiled = json.loads(_MAP_GOLDEN.read_text(encoding="utf-8"))
    assert compiled["resourceType"] == "StructureMap"
    assert [structure["mode"] for structure in compiled["structure"]] == ["source", "target"]
    assert compiled["structure"][0]["url"] == "http://hl7.org/fhir/StructureDefinition/QuestionnaireResponse"
    assert compiled["structure"][1]["url"] == json.loads(_GOLDEN.read_text(encoding="utf-8"))["url"]
    assert [group["name"] for group in compiled["group"]] == [
        "AggregateResponseToDataValueSet",
        "ResponseItemToDataValues",
    ]

    written: set[str] = set()

    def _collect(rules: list[dict[str, Any]]) -> None:
        for rule in rules:
            written.update(target["element"] for target in rule.get("target", []) if "element" in target)
            _collect(rule.get("rule", []))

    for group in compiled["group"]:
        _collect(group["rule"])
    assert written == {element.path.rsplit(".", 1)[-1] for element in DATA_VALUE_SET_ELEMENTS}


def test_every_evaluate_transform_carries_the_expression_alone() -> None:
    """`evaluate` takes one parameter, the FHIRPath expression, and names its variables inside it.

    The IG publisher's validator holds `evaluate` to a single parameter, so an expression reaching
    for the rule's source names that variable itself - `%questionnaire.resolve()...` rather than a
    separate `valueId` beside a bare path - and every variable it names is one an enclosing rule or
    the group's own input binds.
    """
    compiled = json.loads(_MAP_GOLDEN.read_text(encoding="utf-8"))
    expressions: list[str] = []

    def _walk(rules: list[dict[str, Any]], bound: frozenset[str]) -> None:
        for rule in rules:
            in_scope = (
                bound
                | {source["variable"] for source in rule.get("source", []) if "variable" in source}
                | {target["variable"] for target in rule.get("target", []) if "variable" in target}
            )
            for target in rule.get("target", []):
                if target.get("transform") != "evaluate":
                    continue
                parameters = target["parameter"]
                assert [sorted(parameter) for parameter in parameters] == [["valueString"]]
                expression = parameters[0]["valueString"]
                expressions.append(expression)
                for variable in _VARIABLE.findall(expression):
                    assert variable in in_scope, f"`{expression}` names `%{variable}`, which nothing binds"
            _walk(rule.get("rule", []), in_scope)

    for group in compiled["group"]:
        _walk(group["rule"], frozenset(inp["name"] for inp in group["input"]))
    assert len(expressions) == 6
    assert all(expression.startswith("%") for expression in expressions)


def test_the_contract_states_the_four_keys_dhis2_stores_a_data_value_under() -> None:
    """The three required keys, the optional fourth, and the completeness date the envelope carries."""
    contract = _by_path()
    assert [path for path, element in contract.items() if element.required and "." not in path] == [
        "dataSet",
        "period",
        "orgUnit",
    ]
    assert not contract["attributeOptionCombo"].required
    assert not contract["completeDate"].required
    assert contract["dataValues"].repeats


@pytest.mark.parametrize("response_id", AGGREGATE_IDS)
def test_every_field_the_forwarder_writes_is_one_the_contract_declares(response_id: str) -> None:
    """The forwarder invents no DHIS2 field: the envelope's keys and every cell's keys are declared."""
    contract = _by_path()
    wire = _wire(response_id)
    assert set(wire) <= {path for path in contract if "." not in path}
    cell_paths = {path.removeprefix("dataValues.") for path in contract if path.startswith("dataValues.")}
    for cell in wire.get("dataValues", []):
        assert set(cell) <= cell_paths


@pytest.mark.parametrize("response_id", AGGREGATE_IDS)
def test_every_required_element_of_the_contract_is_carried(response_id: str) -> None:
    """A payload missing a required key would import as a report of nowhere, or not import at all."""
    contract = _by_path()
    wire = _wire(response_id)
    assert [
        path for path, element in contract.items() if element.required and "." not in path and path not in wire
    ] == []
    for cell in wire.get("dataValues", []):
        missing = [
            path.removeprefix("dataValues.")
            for path, element in contract.items()
            if path.startswith("dataValues.") and element.required and path.removeprefix("dataValues.") not in cell
        ]
        assert missing == []


@pytest.mark.parametrize("response_id", AGGREGATE_IDS)
def test_every_carried_value_has_the_cardinality_and_type_the_contract_states(response_id: str) -> None:
    """Shapes, not semantics: a repeating element is a list, a single one is not, and every scalar types."""
    contract = _by_path()
    wire = _wire(response_id)
    violations: list[str] = []
    for path, value in wire.items():
        violations.extend(_violations(value, contract[path]))
    for cell in wire.get("dataValues", []):
        for name, value in cell.items():
            violations.extend(_violations(value, contract[f"dataValues.{name}"]))
    assert violations == []


def test_the_corpus_reaches_every_element_of_the_contract_except_the_complete_date() -> None:
    """State the coverage boundary outright: no example response is authored, so no payload dates itself.

    The synthetic examples the generate run publishes carry no `authored` instant for an aggregate
    form, and `completeDate` is derived from that instant alone - so the corpus exercises eight of the
    nine elements and the ninth is pinned by the unit check below instead.
    """
    reached = {name for response_id in AGGREGATE_IDS for name in _wire(response_id)}
    reached |= {
        f"dataValues.{name}"
        for response_id in AGGREGATE_IDS
        for cell in _wire(response_id)["dataValues"]
        for name in cell
    }
    assert set(_by_path()) - reached == {"completeDate"}


def test_the_contract_judges_a_payload_that_breaks_it() -> None:
    """The gate is not vacuous: a payload carrying a number where the contract states a string fails."""
    contract = _by_path()
    assert _violations(202401, contract["period"]) == ["`period` is a string and arrived as int"]
    assert _violations(["202401"], contract["period"]) == ["`period` is single-valued and arrived as a list"]
    assert _violations("2026-08", contract["completeDate"]) == []
    assert _violations("2026-08-08T00:00:00", contract["completeDate"]) == [
        "`completeDate` is a date and arrived as `2026-08-08T00:00:00`"
    ]

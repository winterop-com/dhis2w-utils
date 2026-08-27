"""`POST /$evaluate`: the same evaluation as `/facade/evaluate`, said as the `Parameters` a FHIR client reads.

The claims worth pinning are the ones a client depends on. One parameter per define, named by the
define. A single answer rides the parameter itself - `value[x]` for a primitive, `resource` for a
resource - and several ride one `part` apiece. A define that refuses carries its own
OperationOutcome, so the library's other defines still answer. What stopped the whole run rides the
`outcome` parameter with the line and column the parser named. And the operation is declared where
its URL says it is: the server-level slot, because its URL is the service base's.
"""

from __future__ import annotations

from typing import Any

import httpx
from dhis2w_fhir.r4 import Parameters
from dhis2w_fhir_serve.capability import EVALUATE_OPERATION_DEFINITION
from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE
from dhis2w_fhir_serve.routes.evaluate_operation import EVALUATE_OPERATION_PATH

#: A resource with nothing to do with DHIS2, which is the point: the evaluator takes any FHIR JSON.
PATIENT: dict[str, Any] = {
    "resourceType": "Patient",
    "id": "ada",
    "active": True,
    "birthDate": "1815-12-10",
    "name": [{"given": ["Ada", "Byron"], "family": "Lovelace"}],
}

#: Two resources in one Bundle, which is what a CQL retrieve reads through.
BUNDLE: dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": PATIENT},
        {"resource": {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/ada"}}},
    ],
}

LIBRARY = """
library Example version '1.0'
using FHIR version '4.0.1'

define People: [Patient]
define HasCondition: exists [Condition]
define Greeting: 'hello'
define Ratio: 1.5
"""

#: A library whose second define refuses at evaluation time while the first still answers.
REFUSING_LIBRARY = """
library Refusing version '1.0'
using FHIR version '4.0.1'

define Greeting: 'hello'
define Refused: Message('x', true, 'stopped', 'Error', 'this define will not answer')
"""

ELM_LIBRARY = (
    '{"library": {"identifier": {"id": "Probe", "version": "1.0"}, "statements": {"def": ['
    '{"name": "Sum", "expression": {"type": "Add", "operand": ['
    '{"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},'
    '{"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"}]}}]}}}'
)


def _ask(
    language: str,
    source: str,
    *,
    expression: str | None = None,
    context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One `$evaluate` input as the Parameters resource the operation documents."""
    parameter: list[dict[str, Any]] = [
        {"name": "language", "valueCode": language},
        {"name": "source", "valueString": source},
    ]
    if expression is not None:
        parameter.append({"name": "expression", "valueString": expression})
    if context is not None:
        parameter.append({"name": "context", "part": context})
    return {"resourceType": "Parameters", "parameter": parameter}


def _inline(resource: dict[str, Any]) -> list[dict[str, Any]]:
    """The `context` parts naming a resource carried in the request itself."""
    return [{"name": "kind", "valueCode": "inline"}, {"name": "resource", "resource": resource}]


def _named(body: dict[str, Any], name: str) -> dict[str, Any]:
    """The one parameter of that name, so a test says what it is about rather than counting positions."""
    return next(parameter for parameter in body["parameter"] if parameter["name"] == name)


def _names(body: dict[str, Any]) -> list[str]:
    """Every parameter name the answer carries, in the order it carries them."""
    return [parameter["name"] for parameter in body.get("parameter", [])]


async def test_a_single_answer_rides_the_parameter_named_for_the_expression(client: httpx.AsyncClient) -> None:
    """The whole point: one define, one parameter, the answer on the parameter rather than wrapped in one."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.birthDate", context=_inline(PATIENT)),
    )

    assert answered.status_code == 200
    body = answered.json()
    assert body["resourceType"] == "Parameters"
    assert _named(body, "expression") == {"name": "expression", "valueString": "1815-12-10"}


async def test_several_values_ride_one_part_apiece(client: httpx.AsyncClient) -> None:
    """A parameter states one value, and a collection is several - so each one is a part named `value`."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.name.given", context=_inline(PATIENT)),
    )

    assert _named(answered.json(), "expression") == {
        "name": "expression",
        "part": [{"name": "value", "valueString": "Ada"}, {"name": "value", "valueString": "Byron"}],
    }


async def test_a_boolean_takes_the_boolean_value(client: httpx.AsyncClient) -> None:
    """The `value[x]` is the one R4 spells the JSON type with, which for a bool is never `valueString`."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.active", context=_inline(PATIENT)),
    )

    assert _named(answered.json(), "expression") == {"name": "expression", "valueBoolean": True}


async def test_a_cql_library_answers_one_parameter_per_define(client: httpx.AsyncClient) -> None:
    """Every define the library declares, in declaration order, each said in the terms its value has."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("cql", LIBRARY, context=_inline(BUNDLE)),
    )

    body = answered.json()
    assert _names(body) == ["People", "HasCondition", "Greeting", "Ratio"]
    assert _named(body, "HasCondition") == {"name": "HasCondition", "valueBoolean": True}
    assert _named(body, "Greeting") == {"name": "Greeting", "valueString": "hello"}
    assert _named(body, "Ratio") == {"name": "Ratio", "valueDecimal": 1.5}


async def test_a_define_answering_a_resource_carries_it_as_a_resource(client: httpx.AsyncClient) -> None:
    """A retrieve answers documents, and a document rides `resource` rather than being flattened into parts."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("cql", LIBRARY, expression="People", context=_inline(BUNDLE)),
    )

    people = _named(answered.json(), "People")
    assert people["resource"]["resourceType"] == "Patient"
    assert people["resource"]["id"] == "ada"


async def test_a_define_that_refuses_carries_its_own_operation_outcome(client: httpx.AsyncClient) -> None:
    """A refusal belongs to the one define it stopped, so the rest of the library still answers."""
    answered = await client.post(EVALUATE_OPERATION_PATH, json=_ask("cql", REFUSING_LIBRARY))

    body = answered.json()
    assert _named(body, "Greeting") == {"name": "Greeting", "valueString": "hello"}
    outcome = _named(body, "Refused")["part"][0]
    assert outcome["name"] == "outcome"
    assert outcome["resource"]["resourceType"] == "OperationOutcome"
    issue = outcome["resource"]["issue"][0]
    assert issue["severity"] == "error"
    assert issue["code"] == "processing"
    assert "this define will not answer" in issue["diagnostics"]


async def test_a_define_that_matched_nothing_carries_no_parameter(client: httpx.AsyncClient) -> None:
    """FHIR has no empty collection: an expression that matched nothing says so by not being there."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.telecom.value", context=_inline(PATIENT)),
    )

    assert answered.status_code == 200
    assert answered.json() == {"resourceType": "Parameters"}


async def test_an_expression_that_will_not_parse_answers_the_outcome_parameter(client: httpx.AsyncClient) -> None:
    """A parse failure is 200 with the position in it - the request was well formed and this is its answer."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.name..given", context=_inline(PATIENT)),
    )

    assert answered.status_code == 200
    outcome = _named(answered.json(), "outcome")["resource"]
    assert outcome["resourceType"] == "OperationOutcome"
    issue = outcome["issue"][0]
    assert issue["code"] == "invalid"
    # ANTLR counts the offending character from zero; a person counting along the line does not.
    assert issue["diagnostics"].startswith("line 1, column 14: ")


async def test_a_define_the_library_does_not_declare_is_said_in_the_outcome(client: httpx.AsyncClient) -> None:
    """A name nothing answers is the run's diagnostic, not an empty parameter that reads as an empty answer."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("cql", LIBRARY, expression="NoSuchDefine", context=_inline(BUNDLE)),
    )

    issue = _named(answered.json(), "outcome")["resource"]["issue"][0]
    assert issue["code"] == "processing"
    assert "declares no define" in issue["diagnostics"]


async def test_an_elm_library_runs_from_the_json_it_arrived_as(client: httpx.AsyncClient) -> None:
    """ELM is a source like the other two: a library as JSON, answering the define it declares."""
    answered = await client.post(EVALUATE_OPERATION_PATH, json=_ask("elm", ELM_LIBRARY))

    assert _named(answered.json(), "Sum") == {"name": "Sum", "valueInteger": 3}


async def test_a_stored_resource_is_read_out_of_the_served_guide(client: httpx.AsyncClient) -> None:
    """The context a guide's own author reaches for, named here the way a read names it: by type and id."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask(
            "fhirpath",
            "Questionnaire.title",
            context=[
                {"name": "kind", "valueCode": "stored"},
                {"name": "resourceType", "valueCode": "Questionnaire"},
                {"name": "resourceId", "valueString": "d2-pr-anc-visit-q"},
            ],
        ),
    )

    assert _named(answered.json(), "expression") == {"name": "expression", "valueString": "ANC Visit"}


async def test_a_stored_resource_this_server_does_not_hold_is_an_operation_outcome(
    client: httpx.AsyncClient,
) -> None:
    """The two addresses refuse the same way, because they resolve their context through the same function."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask(
            "fhirpath",
            "Questionnaire.title",
            context=[
                {"name": "kind", "valueCode": "stored"},
                {"name": "resourceType", "valueCode": "Questionnaire"},
                {"name": "resourceId", "valueString": "missing"},
            ],
        ),
    )

    assert answered.status_code == 404
    assert answered.json()["resourceType"] == "OperationOutcome"


async def test_a_register_context_says_this_process_holds_no_instance(client: httpx.AsyncClient) -> None:
    """The registered context is live-only here too, and refuses in the register's own words."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask(
            "fhirpath",
            "Patient.identifier.value",
            context=[
                {"name": "kind", "valueCode": "registered"},
                {"name": "trackedEntityUid", "valueString": "TeiPerson01"},
            ],
        ),
    )

    assert answered.status_code == 404
    assert "--live" in answered.json()["issue"][0]["diagnostics"]


async def test_the_plain_json_body_answers_the_same_parameters(client: httpx.AsyncClient) -> None:
    """Parameters in is canonical, and the `/facade/evaluate` body is read too: same evaluation, same answer."""
    as_parameters = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("cql", LIBRARY, context=_inline(BUNDLE)),
    )
    as_json = await client.post(
        EVALUATE_OPERATION_PATH,
        json={"language": "cql", "source": LIBRARY, "context": {"kind": "inline", "resource": BUNDLE}},
    )

    assert as_json.status_code == 200
    assert as_json.content == as_parameters.content


async def test_the_json_answer_is_the_project_s_own_shape_and_this_one_is_not(client: httpx.AsyncClient) -> None:
    """Two addresses, two shapes: the UI's endpoint keeps its rows, and this one answers a resource."""
    rows = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.birthDate",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )
    resource = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.birthDate", context=_inline(PATIENT)),
    )

    assert rows.json()["results"] == [{"name": "expression", "values": ["1815-12-10"], "refusal": None}]
    assert resource.json()["resourceType"] == "Parameters"


async def test_the_answer_is_a_parameters_resource_the_r4_model_round_trips(client: httpx.AsyncClient) -> None:
    """Wire-true is the whole claim: the body validates as R4 Parameters and re-serialises to itself."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("cql", REFUSING_LIBRARY, context=_inline(BUNDLE)),
    )

    parsed = Parameters.model_validate(answered.json())
    assert parsed.model_dump(mode="json", exclude_none=True, by_alias=True) == answered.json()


async def test_the_answer_is_served_as_fhir_json(client: httpx.AsyncClient) -> None:
    """Every FHIR document leaves this server the same way, this operation's answer included."""
    answered = await client.post(EVALUATE_OPERATION_PATH, json=_ask("elm", ELM_LIBRARY))

    assert answered.headers["content-type"].startswith(FHIR_JSON_MEDIA_TYPE)


async def test_a_request_naming_no_source_is_refused(client: httpx.AsyncClient) -> None:
    """An evaluation with no source is not a narrower question - it is no question."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json={"resourceType": "Parameters", "parameter": [{"name": "language", "valueCode": "fhirpath"}]},
    )

    assert answered.status_code == 400
    assert "`source`" in answered.json()["issue"][0]["diagnostics"]


async def test_a_language_this_server_does_not_evaluate_is_refused(client: httpx.AsyncClient) -> None:
    """Three languages and no fourth, named in the refusal so a caller learns which three."""
    answered = await client.post(EVALUATE_OPERATION_PATH, json=_ask("sql", "SELECT 1"))

    assert answered.status_code == 400
    diagnostics = answered.json()["issue"][0]["diagnostics"]
    assert "`fhirpath`" in diagnostics
    assert "`cql`" in diagnostics
    assert "`elm`" in diagnostics


async def test_a_context_kind_this_server_does_not_offer_is_refused_before_anything_runs(
    client: httpx.AsyncClient,
) -> None:
    """Three kinds and no fourth: a request naming one that does not exist never reaches the engine."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask(
            "fhirpath",
            "Patient.id",
            context=[{"name": "kind", "valueCode": "file"}, {"name": "path", "valueString": "/etc/passwd"}],
        ),
    )

    assert answered.status_code == 400
    assert answered.json()["resourceType"] == "OperationOutcome"


async def test_an_inline_context_with_no_resource_is_refused(client: httpx.AsyncClient) -> None:
    """A context that names a kind and then names no resource is a request nothing can be run over."""
    answered = await client.post(
        EVALUATE_OPERATION_PATH,
        json=_ask("fhirpath", "Patient.id", context=[{"name": "kind", "valueCode": "inline"}]),
    )

    assert answered.status_code == 400
    assert "`resource`" in answered.json()["issue"][0]["diagnostics"]


async def test_a_body_that_is_neither_shape_says_which_two_it_takes(client: httpx.AsyncClient) -> None:
    """A refusal that names the two bodies is one a caller can act on without reading the source."""
    answered = await client.post(EVALUATE_OPERATION_PATH, json={"language": "fhirpath"})

    assert answered.status_code == 400
    diagnostics = answered.json()["issue"][0]["diagnostics"]
    assert "Parameters resource" in diagnostics
    assert "/facade/evaluate" in diagnostics


async def test_the_operation_is_declared_at_the_server_level_slot(client: httpx.AsyncClient) -> None:
    """A client following `/metadata` reaches `[base]/$evaluate`, which is the address that answers."""
    body = (await client.get("/metadata")).json()

    declared = body["rest"][0]["operation"]
    assert [operation["name"] for operation in declared] == ["evaluate"]
    assert declared[0]["definition"] == EVALUATE_OPERATION_DEFINITION
    assert "FHIRPath" in declared[0]["documentation"]


async def test_the_declared_operation_is_reachable_at_the_url_its_slot_names(client: httpx.AsyncClient) -> None:
    """The server-level slot names the service base, so `[base]/$evaluate` is what a client posts to."""
    answered = await client.post("/$evaluate", json=_ask("elm", ELM_LIBRARY))

    assert answered.status_code == 200
    assert answered.json()["resourceType"] == "Parameters"

"""`POST /facade/evaluate`: what it answers, what it refuses, and what it will not let an expression reach.

The claims worth pinning are the three the endpoint exists to make. An expression answers a typed
collection rather than whatever Python object the engine held. A bad expression is an answer with a
position in it, never a 500 and never a bare error string. And the only data an expression can reach
is the context the request named - a store read the facade holds, or the JSON the caller posted, or
nothing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from dhis2w_fhir_serve.evaluation import EvaluationLanguage, evaluate_source, json_safe

#: A resource with nothing to do with DHIS2, which is the point: the evaluator serves any FHIR JSON.
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

#: A resource that is not a Patient and carries an id, which is what a stored context always is.
OBSERVATION: dict[str, Any] = {
    "resourceType": "Observation",
    "id": "obs-1",
    "status": "final",
    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
}

LIBRARY = """
library Example version '1.0'
using FHIR version '4.0.1'

define People: [Patient]
define HasCondition: exists [Condition]
define Greeting: 'hello'
"""


def one_define(source: str, name: str) -> str:
    """A one-define CQL library, so a retrieve can be asserted without a fixture library around it."""
    return f"library Probe version '1.0'\nusing FHIR version '4.0.1'\ndefine {name}: {source}"


async def test_a_fhirpath_expression_answers_the_collection_it_matched(client: httpx.AsyncClient) -> None:
    """The whole point: an expression over a posted resource, answered as JSON a browser can render."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.name.given",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )

    assert answered.status_code == 200
    body = answered.json()
    assert body["results"] == [{"name": "expression", "values": ["Ada", "Byron"], "refusal": None}]
    assert body["diagnostics"] == []


async def test_an_expression_that_matches_nothing_answers_an_empty_collection(client: httpx.AsyncClient) -> None:
    """Empty is an answer and is not a refusal - the two states stay apart all the way to the wire."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.telecom.value",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )

    assert answered.json()["results"] == [{"name": "expression", "values": [], "refusal": None}]


async def test_an_expression_that_will_not_parse_answers_where_it_stopped(client: httpx.AsyncClient) -> None:
    """A parse failure is 200 with a position, because the request was well formed and this is its answer."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.name..given",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )

    assert answered.status_code == 200
    diagnostic = answered.json()["diagnostics"][0]
    assert diagnostic["kind"] == "parse"
    assert diagnostic["line"] == 1
    # ANTLR counts the offending character from zero; a person counting along the line does not.
    assert diagnostic["column"] == 14
    assert answered.json()["results"] == []


async def test_a_parse_message_names_the_problem_without_listing_every_legal_token(
    client: httpx.AsyncClient,
) -> None:
    """An unclosed call is "mismatched input '<EOF>'" and nothing else - not ANTLR's whole token set."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.name.given(",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )

    diagnostic = answered.json()["diagnostics"][0]
    assert diagnostic["kind"] == "parse"
    assert diagnostic["line"] == 1
    assert diagnostic["message"] == "mismatched input '<EOF>'"
    assert "expecting" not in diagnostic["message"]
    assert "IDENTIFIER" not in diagnostic["message"]


async def test_a_cql_library_answers_one_row_per_define(client: httpx.AsyncClient) -> None:
    """Every define the library declares, in declaration order, with the retrieves read off the Bundle."""
    answered = await client.post(
        "/facade/evaluate",
        json={"language": "cql", "source": LIBRARY, "context": {"kind": "inline", "resource": BUNDLE}},
    )

    body = answered.json()
    assert body["definitions"] == ["People", "HasCondition", "Greeting"]
    named = {row["name"]: row["values"] for row in body["results"]}
    assert named["HasCondition"] == [True]
    assert named["Greeting"] == ["hello"]
    assert named["People"][0]["id"] == "ada"


async def test_one_define_can_be_asked_for_by_name(client: httpx.AsyncClient) -> None:
    """`expression_name` narrows the answer to the one define a caller wanted."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": LIBRARY,
            "expression_name": "Greeting",
            "context": {"kind": "inline", "resource": BUNDLE},
        },
    )

    assert answered.json()["results"] == [{"name": "Greeting", "values": ["hello"], "refusal": None}]


async def test_a_define_the_library_does_not_declare_is_said_so(client: httpx.AsyncClient) -> None:
    """A name nothing answers is a diagnostic, not an empty row that reads as a define answering nothing."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": LIBRARY,
            "expression_name": "NoSuchDefine",
            "context": {"kind": "inline", "resource": BUNDLE},
        },
    )

    diagnostic = answered.json()["diagnostics"][0]
    assert diagnostic["kind"] == "evaluation"
    assert diagnostic["expression_name"] == "NoSuchDefine"
    assert "declares no define" in diagnostic["message"]


async def test_a_single_resource_context_is_still_retrievable(client: httpx.AsyncClient) -> None:
    """`[Patient]` finds a Patient that was handed in on its own, rather than answering an empty list."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": "library Solo version '1.0'\nusing FHIR version '4.0.1'\ndefine Found: exists [Patient]",
            "context": {"kind": "inline", "resource": PATIENT},
        },
    )

    assert answered.json()["results"] == [{"name": "Found", "values": [True], "refusal": None}]


async def test_a_bundle_is_data_rather_than_a_context_so_a_retrieve_reads_it_whole(
    client: httpx.AsyncClient,
) -> None:
    """A Bundle names no context resource, so `[Condition]` answers every Condition it carries."""
    other = {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/someone-else"}}
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": one_define("[Condition]", "Conditions"),
            "context": {
                "kind": "inline",
                "resource": {**BUNDLE, "entry": [*BUNDLE["entry"], {"resource": other}]},
            },
        },
    )

    assert [row["id"] for row in answered.json()["results"][0]["values"]] == ["c1", "c2"]


async def test_a_non_patient_context_with_an_id_answers_the_context_resource(client: httpx.AsyncClient) -> None:
    """The three-call proof, second call: an Observation carrying an id is retrievable under itself."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": one_define("[Observation]", "Observations"),
            "context": {"kind": "inline", "resource": OBSERVATION},
        },
    )

    assert [row["id"] for row in answered.json()["results"][0]["values"]] == ["obs-1"]


async def test_the_same_context_resource_answers_the_same_with_its_id_taken_off(
    client: httpx.AsyncClient,
) -> None:
    """The three-call proof, third call: an id on the context resource changes no answer."""
    without_id = {key: value for key, value in OBSERVATION.items() if key != "id"}
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": one_define("exists [Observation]", "Any"),
            "context": {"kind": "inline", "resource": without_id},
        },
    )

    assert answered.json()["results"] == [{"name": "Any", "values": [True], "refusal": None}]


async def test_a_stored_questionnaire_is_retrievable_under_its_own_context(client: httpx.AsyncClient) -> None:
    """What the guide's own CQL examples ask: a retrieve for the stored resource the context names."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "cql",
            "source": one_define("[Questionnaire]", "Questionnaires"),
            "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "d2-pr-anc-visit-q"},
        },
    )

    assert [row["id"] for row in answered.json()["results"][0]["values"]] == ["d2-pr-anc-visit-q"]


async def test_an_elm_library_runs_from_the_json_it_arrived_as(client: httpx.AsyncClient) -> None:
    """ELM is parsed here rather than by the engine, which is what keeps a file path out of the source."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "elm",
            "source": (
                '{"library": {"identifier": {"id": "Probe", "version": "1.0"}, "statements": {"def": ['
                '{"name": "Sum", "expression": {"type": "Add", "operand": ['
                '{"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "1"},'
                '{"type": "Literal", "valueType": "{urn:hl7-org:elm-types:r1}Integer", "value": "2"}]}}]}}}'
            ),
        },
    )

    assert answered.json()["results"] == [{"name": "Sum", "values": [3], "refusal": None}]


async def test_an_elm_source_naming_a_file_is_json_that_will_not_parse(client: httpx.AsyncClient) -> None:
    """The sandbox, asserted: a path where a library should be is a parse failure, never a file that opens."""
    answered = await client.post("/facade/evaluate", json={"language": "elm", "source": "/etc/passwd"})

    assert answered.status_code == 200
    assert answered.json()["diagnostics"][0]["kind"] == "parse"
    assert answered.json()["results"] == []


async def test_a_stored_resource_is_read_out_of_the_served_guide(client: httpx.AsyncClient) -> None:
    """The context a guide's own author reaches for: a published resource, named the way a read names it."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Questionnaire.title",
            "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "d2-pr-anc-visit-q"},
        },
    )

    assert answered.json()["results"][0]["values"] == ["ANC Visit"]


async def test_a_stored_resource_this_server_does_not_hold_is_an_operation_outcome(
    client: httpx.AsyncClient,
) -> None:
    """A request this facade cannot serve is a refusal in FHIR's own words, unlike a bad expression."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Questionnaire.title",
            "context": {"kind": "stored", "resource_type": "Questionnaire", "resource_id": "missing"},
        },
    )

    assert answered.status_code == 404
    assert answered.json()["resourceType"] == "OperationOutcome"


async def test_a_register_context_says_this_process_holds_no_instance(client: httpx.AsyncClient) -> None:
    """The register context is live-only, and refuses in the register's own words rather than in a traceback."""
    answered = await client.post(
        "/facade/evaluate",
        json={
            "language": "fhirpath",
            "source": "Patient.identifier.value",
            "context": {"kind": "registered", "tracked_entity_uid": "TeiPerson01"},
        },
    )

    assert answered.status_code == 404
    assert "--live" in answered.json()["issue"][0]["diagnostics"]


async def test_a_context_this_endpoint_does_not_offer_is_refused_before_anything_runs(
    client: httpx.AsyncClient,
) -> None:
    """Three kinds and no fourth: a request naming one that does not exist never reaches the engine."""
    answered = await client.post(
        "/facade/evaluate",
        json={"language": "fhirpath", "source": "Patient.id", "context": {"kind": "file", "path": "/etc/passwd"}},
    )

    assert answered.status_code == 400
    assert answered.json()["resourceType"] == "OperationOutcome"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (float("nan"), "nan"),
        (float("inf"), "inf"),
        ({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]}),
        ((1, 2), [1, 2]),
    ],
)
def test_a_result_is_rendered_as_json_a_strict_parser_takes(value: object, expected: object) -> None:
    """Nothing leaves here that JSON cannot say - `NaN` in a body is a body a strict client refuses."""
    assert json_safe(value) == expected


def test_the_evaluator_is_a_function_a_caller_with_no_server_can_call() -> None:
    """The engine layer holds no FastAPI, which is what lets a batch job answer the endpoint's question."""
    outcome = evaluate_source(EvaluationLanguage.FHIRPATH, "Patient.birthDate", PATIENT)

    assert outcome.results[0].values == ("1815-12-10",)

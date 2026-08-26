"""Tests for `dhis2w_fhir.facade` - the typed client for a running `d2w fhir serve` facade.

Every method is driven against a mocked facade rather than a started one, so what is asserted here
is the contract this client believes in: the paths it calls, the headers it sends, the models it
parses out, and what it does with a refusal. `test_fhir_serve_cli.py` and the served package's own
tests cover the other side of the same contract.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
import respx
from dhis2w_fhir import (
    BearerToken,
    EvaluationLanguage,
    FacadeClient,
    FacadeError,
    InlineResourceContext,
    PersonalAccessToken,
    ResourceQuery,
    UsernamePassword,
)
from dhis2w_fhir.r4 import QuestionnaireResponse

FACADE_URL = "http://facade.test"
FHIR_JSON = "application/fhir+json"

#: What an accepted capture answers with: the informational line first, then whatever it had to note.
_STORED_ID = "9f0c2b1d4e5a6f7089abcdef01234567"


def _capability(*, url_searchable: tuple[str, ...] = ("Questionnaire", "CodeSystem")) -> dict[str, Any]:
    """A CapabilityStatement declaring `url` on the named types and `_id` on one that is not searchable by it."""
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": [FHIR_JSON],
        "software": {"name": "d2w fhir serve", "version": "1.7.0"},
        "rest": [
            {
                "mode": "server",
                "resource": [
                    *(
                        {
                            "type": resource_type,
                            "searchParam": [{"name": "_id", "type": "token"}, {"name": "url", "type": "uri"}],
                        }
                        for resource_type in url_searchable
                    ),
                    {
                        "type": "QuestionnaireResponse",
                        "searchParam": [
                            {"name": "_id", "type": "token"},
                            {"name": "questionnaire", "type": "reference"},
                        ],
                    },
                ],
            }
        ],
    }


def _draft(questionnaire: str = "http://example.org/fhir/Questionnaire/BfMAe6Itzgt") -> dict[str, Any]:
    """A filled form the way `$generate` answers one - postable to the same server unchanged."""
    return {
        "resourceType": "QuestionnaireResponse",
        "questionnaire": questionnaire,
        "status": "completed",
        "item": [{"linkId": "period", "answer": [{"valueString": "202601"}]}],
    }


def _accepted(warnings: list[dict[str, Any]] | None = None) -> httpx.Response:
    """The 201 an accepted capture draws: an OperationOutcome body and the receipt's url on `Location`."""
    stored = {
        "severity": "information",
        "code": "informational",
        "diagnostics": f"stored response {_STORED_ID}; a stored response is the submission as received",
    }
    return httpx.Response(
        201,
        json={"resourceType": "OperationOutcome", "issue": [stored, *(warnings or [])]},
        headers={
            "Location": f"{FACADE_URL}/QuestionnaireResponse/{_STORED_ID}",
            "Content-Type": FHIR_JSON,
        },
    )


def _outcome(diagnostics: str, *, code: str = "not-found", severity: str = "error") -> dict[str, Any]:
    """One refusal as the facade renders every refusal it makes."""
    return {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": severity, "code": code, "diagnostics": diagnostics}],
    }


@respx.mock
@pytest.mark.asyncio
async def test_capability_parses_the_statement_and_holds_it() -> None:
    """`/metadata` is read once and reused - a second call costs no round trip."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL) as facade:
        first = await facade.capability()
        second = await facade.capability()

    assert first.software is not None
    assert first.software.name == "d2w fhir serve"
    assert second is first
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_capability_refresh_asks_again() -> None:
    """`refresh=True` is how a caller that restarted the facade gets the new statement."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL) as facade:
        await facade.capability()
        await facade.capability(refresh=True)

    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_every_request_accepts_fhir_json() -> None:
    """The facade answers `application/fhir+json` and nothing else, so every FHIR call says so."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL) as facade:
        await facade.capability()

    assert route.calls.last.request.headers["accept"] == FHIR_JSON


@respx.mock
@pytest.mark.asyncio
async def test_read_carries_the_document_the_facade_served() -> None:
    """A stored resource is answered verbatim, so every key it had survives the parse."""
    body = {"resourceType": "Questionnaire", "id": "BfMAe6Itzgt", "title": "Child Health", "status": "active"}
    respx.get(f"{FACADE_URL}/Questionnaire/BfMAe6Itzgt").mock(return_value=httpx.Response(200, json=body))
    async with FacadeClient(FACADE_URL) as facade:
        resource = await facade.read("Questionnaire", "BfMAe6Itzgt")

    assert resource.resourceType == "Questionnaire"
    assert resource.model_dump(exclude_none=True) == body


@respx.mock
@pytest.mark.asyncio
async def test_read_response_answers_a_typed_receipt() -> None:
    """The one type a caller reads back most has a typed path, so the answers are navigable."""
    respx.get(f"{FACADE_URL}/QuestionnaireResponse/{_STORED_ID}").mock(
        return_value=httpx.Response(200, json={**_draft(), "id": _STORED_ID})
    )
    async with FacadeClient(FACADE_URL) as facade:
        receipt = await facade.read_response(_STORED_ID)

    assert isinstance(receipt, QuestionnaireResponse)
    assert receipt.id == _STORED_ID
    assert receipt.item is not None
    assert receipt.item[0].linkId == "period"


@respx.mock
@pytest.mark.asyncio
async def test_search_sends_only_the_parameters_the_facade_honours() -> None:
    """A store search ignores what it does not know, so the query model can only spell what it reads."""
    route = respx.get(f"{FACADE_URL}/Questionnaire").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 0})
    )
    async with FacadeClient(FACADE_URL) as facade:
        bundle = await facade.search(
            "Questionnaire",
            ResourceQuery(ids=("a", "b"), urls=("http://example.org/q",), count=5),
        )

    assert bundle.total == 0
    parameters = dict(route.calls.last.request.url.params.multi_items())
    assert parameters == {"_id": "a,b", "url": "http://example.org/q", "_count": "5"}


@respx.mock
@pytest.mark.asyncio
async def test_search_without_a_query_sends_no_parameters() -> None:
    """Listing a type is the query nobody narrowed, and it composes no parameters of its own."""
    route = respx.get(f"{FACADE_URL}/Location").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 3})
    )
    async with FacadeClient(FACADE_URL) as facade:
        await facade.search("Location")

    assert route.calls.last.request.url.params.multi_items() == []


@respx.mock
@pytest.mark.asyncio
async def test_resolve_asks_every_type_that_declares_url() -> None:
    """A canonical says what a resource is, not where it lives, so resolving one asks each type in turn."""
    respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    canonical = "http://example.org/fhir/CodeSystem/ANC"
    respx.get(f"{FACADE_URL}/Questionnaire").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 0})
    )
    respx.get(f"{FACADE_URL}/CodeSystem").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "type": "searchset",
                "total": 1,
                "entry": [{"resource": {"resourceType": "CodeSystem", "id": "ANC", "url": canonical}}],
            },
        )
    )
    async with FacadeClient(FACADE_URL) as facade:
        resolved = await facade.resolve(canonical)

    assert resolved is not None
    assert resolved.resourceType == "CodeSystem"


@respx.mock
@pytest.mark.asyncio
async def test_resolve_never_asks_a_type_that_does_not_search_by_url() -> None:
    """`QuestionnaireResponse` declares `questionnaire` rather than `url`, so a canonical lookup skips it."""
    respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    empty = httpx.Response(200, json={"resourceType": "Bundle", "type": "searchset", "total": 0})
    respx.get(f"{FACADE_URL}/Questionnaire").mock(return_value=empty)
    respx.get(f"{FACADE_URL}/CodeSystem").mock(return_value=empty)
    responses = respx.get(f"{FACADE_URL}/QuestionnaireResponse").mock(return_value=empty)

    async with FacadeClient(FACADE_URL) as facade:
        assert await facade.canonical_resource_types() == ("Questionnaire", "CodeSystem")
        assert await facade.resolve("http://example.org/fhir/CodeSystem/absent") is None

    assert responses.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_generate_asks_for_a_reproducible_draft() -> None:
    """`seed` is what makes a generated draft byte-reproducible, and it rides the query string."""
    route = respx.get(f"{FACADE_URL}/Questionnaire/BfMAe6Itzgt/$generate").mock(
        return_value=httpx.Response(200, json=_draft())
    )
    async with FacadeClient(FACADE_URL) as facade:
        draft = await facade.generate("BfMAe6Itzgt", seed=20260)

    assert draft.status == "completed"
    assert route.calls.last.request.url.params["seed"] == "20260"


@respx.mock
@pytest.mark.asyncio
async def test_generate_without_a_seed_sends_none() -> None:
    """An unseeded draft is a random one, and the client composes no `seed` to say so."""
    route = respx.get(f"{FACADE_URL}/Questionnaire/BfMAe6Itzgt/$generate").mock(
        return_value=httpx.Response(200, json=_draft())
    )
    async with FacadeClient(FACADE_URL) as facade:
        await facade.generate("BfMAe6Itzgt")

    assert "seed" not in route.calls.last.request.url.params


@respx.mock
@pytest.mark.asyncio
async def test_submit_response_reads_the_id_off_the_location_header() -> None:
    """A `create` answers an OperationOutcome, so the id is in the header and nowhere in the body."""
    route = respx.post(f"{FACADE_URL}/QuestionnaireResponse").mock(return_value=_accepted())
    async with FacadeClient(FACADE_URL) as facade:
        receipt = await facade.submit_response(_draft())

    assert receipt.response_id == _STORED_ID
    assert receipt.location == f"{FACADE_URL}/QuestionnaireResponse/{_STORED_ID}"
    assert receipt.note is not None
    assert receipt.note.startswith(f"stored response {_STORED_ID}")
    assert receipt.warnings == ()
    assert route.calls.last.request.headers["content-type"] == FHIR_JSON


@respx.mock
@pytest.mark.asyncio
async def test_submit_response_carries_the_warnings_the_answer_stated() -> None:
    """A submission can be accepted and still have something worth saying about it."""
    warning = {
        "severity": "warning",
        "code": "business-rule",
        "diagnostics": "answer for linkId 'weight' is outside the range the form states",
        "expression": ["QuestionnaireResponse.item[0]"],
    }
    respx.post(f"{FACADE_URL}/QuestionnaireResponse").mock(return_value=_accepted([warning]))
    async with FacadeClient(FACADE_URL) as facade:
        receipt = await facade.submit_response(_draft())

    assert len(receipt.warnings) == 1
    assert receipt.warnings[0].severity == "warning"
    assert receipt.warnings[0].expression == ["QuestionnaireResponse.item[0]"]
    assert receipt.outcome.issue is not None
    assert len(receipt.outcome.issue) == 2


@respx.mock
@pytest.mark.asyncio
async def test_submit_response_takes_a_model_as_readily_as_a_document() -> None:
    """A caller holding a `$generate` draft and one holding a parsed document are both one call away."""
    route = respx.post(f"{FACADE_URL}/QuestionnaireResponse").mock(return_value=_accepted())
    async with FacadeClient(FACADE_URL) as facade:
        await facade.submit_response(QuestionnaireResponse.model_validate(_draft()))

    sent = json.loads(route.calls.last.request.content)
    assert sent["resourceType"] == "QuestionnaireResponse"
    assert sent["item"][0]["answer"][0]["valueString"] == "202601"
    assert "id" not in sent


@respx.mock
@pytest.mark.asyncio
async def test_a_refused_capture_raises_with_every_issue_it_named() -> None:
    """A capture refused at 422 states one issue per thing wrong with it, and all of them survive."""
    body = {
        "resourceType": "OperationOutcome",
        "issue": [
            {"severity": "error", "code": "code-invalid", "diagnostics": "code 'XX' is in no bound ValueSet"},
            {"severity": "error", "code": "required", "diagnostics": "no answer for required linkId 'period'"},
        ],
    }
    respx.post(f"{FACADE_URL}/QuestionnaireResponse").mock(return_value=httpx.Response(422, json=body))
    async with FacadeClient(FACADE_URL) as facade:
        with pytest.raises(FacadeError) as raised:
            await facade.submit_response(_draft())

    error = raised.value
    assert error.status_code == 422
    assert len(error.issues) == 2
    assert "code-invalid" in {issue.code for issue in error.issues}
    assert "no answer for required linkId 'period'" in error.diagnostics
    assert "422" in str(error)


@respx.mock
@pytest.mark.asyncio
async def test_a_refusal_with_no_outcome_body_still_raises_readably() -> None:
    """A proxy in front of the facade answers whatever it answers, so the shape is never assumed."""
    respx.get(f"{FACADE_URL}/Questionnaire/absent").mock(return_value=httpx.Response(502, text="Bad Gateway"))
    async with FacadeClient(FACADE_URL) as facade:
        with pytest.raises(FacadeError) as raised:
            await facade.read("Questionnaire", "absent")

    error = raised.value
    assert error.outcome is None
    assert error.issues == ()
    assert error.body_text == "Bad Gateway"
    assert "Bad Gateway" in str(error)


@respx.mock
@pytest.mark.asyncio
async def test_a_missing_resource_raises_carrying_the_outcome() -> None:
    """Every refusal the facade makes itself renders as an OperationOutcome, including a plain 404."""
    respx.get(f"{FACADE_URL}/Questionnaire/absent").mock(
        return_value=httpx.Response(404, json=_outcome("this server holds no Questionnaire/absent"))
    )
    async with FacadeClient(FACADE_URL) as facade:
        with pytest.raises(FacadeError) as raised:
            await facade.read("Questionnaire", "absent")

    assert raised.value.status_code == 404
    assert raised.value.diagnostics == "this server holds no Questionnaire/absent"


@respx.mock
@pytest.mark.asyncio
async def test_a_bearer_token_is_sent_as_the_token_posture_reads_it() -> None:
    """`token` and `jwt` both take `Authorization: Bearer <token>`."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL, auth=BearerToken(token="s3cret")) as facade:
        await facade.capability()

    assert route.calls.last.request.headers["authorization"] == "Bearer s3cret"


@respx.mock
@pytest.mark.asyncio
async def test_a_username_and_password_are_sent_as_the_dhis2_posture_reads_them() -> None:
    """The `dhis2` posture replays `Basic` against `GET /api/me`, so the client sends exactly that."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL, auth=UsernamePassword(username="admin", password="district")) as facade:
        await facade.capability()

    expected = base64.b64encode(b"admin:district").decode("ascii")
    assert route.calls.last.request.headers["authorization"] == f"Basic {expected}"


@respx.mock
@pytest.mark.asyncio
async def test_a_personal_access_token_is_sent_under_dhis2_own_scheme() -> None:
    """A DHIS2 personal access token travels as `ApiToken`, which is not a scheme HTTP registered."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL, auth=PersonalAccessToken(token="d2pat_abc")) as facade:
        await facade.capability()

    assert route.calls.last.request.headers["authorization"] == "ApiToken d2pat_abc"


@respx.mock
@pytest.mark.asyncio
async def test_no_credential_sends_no_authorization_header() -> None:
    """The `none` posture serves every caller, and a client with no credential composes no header."""
    route = respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with FacadeClient(FACADE_URL) as facade:
        await facade.capability()

    assert "authorization" not in route.calls.last.request.headers


@respx.mock
@pytest.mark.asyncio
async def test_evaluate_posts_plain_json_and_parses_the_outcome() -> None:
    """`/evaluate` is the facade's own endpoint, not FHIR - it answers `application/json`."""
    answer = {
        "language": "fhirpath",
        "results": [{"name": "expression", "values": ["Ada", "Byron"], "refusal": None}],
        "diagnostics": [],
        "definitions": [],
    }
    route = respx.post(f"{FACADE_URL}/evaluate").mock(return_value=httpx.Response(200, json=answer))
    async with FacadeClient(FACADE_URL) as facade:
        outcome = await facade.evaluate(
            EvaluationLanguage.FHIRPATH,
            "Patient.name.given",
            context=InlineResourceContext.over({"resourceType": "Patient", "id": "example"}),
        )

    assert outcome.language is EvaluationLanguage.FHIRPATH
    assert outcome.results[0].values == ("Ada", "Byron")
    request = route.calls.last.request
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    sent = json.loads(request.content)
    assert sent == {
        "language": "fhirpath",
        "source": "Patient.name.given",
        "context": {"kind": "inline", "resource": {"resourceType": "Patient", "id": "example"}},
    }


@respx.mock
@pytest.mark.asyncio
async def test_an_expression_that_will_not_parse_is_an_outcome_not_a_refusal() -> None:
    """A bad expression answers 200 with the position the parser stopped on, which is the whole point."""
    answer = {
        "language": "fhirpath",
        "results": [],
        "diagnostics": [{"kind": "parse", "message": "Syntax error", "line": 1, "column": 18, "expression_name": None}],
        "definitions": [],
    }
    respx.post(f"{FACADE_URL}/evaluate").mock(return_value=httpx.Response(200, json=answer))
    async with FacadeClient(FACADE_URL) as facade:
        outcome = await facade.evaluate("fhirpath", "Patient.name..given")

    assert outcome.results == ()
    assert outcome.diagnostics[0].line == 1
    assert outcome.diagnostics[0].column == 18


@respx.mock
@pytest.mark.asyncio
async def test_evaluate_over_a_typed_resource_dumps_it_for_the_wire() -> None:
    """A caller holding an R4 model should not have to dump it first to name it as the context."""
    answer = {"language": "fhirpath", "results": [], "diagnostics": [], "definitions": []}
    route = respx.post(f"{FACADE_URL}/evaluate").mock(return_value=httpx.Response(200, json=answer))
    async with FacadeClient(FACADE_URL) as facade:
        await facade.evaluate(
            "fhirpath",
            "QuestionnaireResponse.status",
            context=InlineResourceContext.over(QuestionnaireResponse.model_validate(_draft())),
        )

    sent = json.loads(route.calls.last.request.content)
    assert sent["context"]["resource"]["resourceType"] == "QuestionnaireResponse"
    assert sent["context"]["resource"]["status"] == "completed"


@respx.mock
@pytest.mark.asyncio
async def test_a_borrowed_pool_is_left_open_for_its_owner_to_close() -> None:
    """A caller pooling several clients, or a test driving the app in process, keeps its own pool."""
    respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    async with httpx.AsyncClient() as pool:
        async with FacadeClient(FACADE_URL, http_client=pool) as facade:
            await facade.capability()
        assert not pool.is_closed
        assert (await pool.get(f"{FACADE_URL}/metadata")).status_code == 200


@respx.mock
@pytest.mark.asyncio
async def test_a_pool_the_client_opened_is_closed_at_exit() -> None:
    """The client owns what it opened, so leaving the block leaves no socket behind."""
    respx.get(f"{FACADE_URL}/metadata").mock(return_value=httpx.Response(200, json=_capability()))
    facade = FacadeClient(FACADE_URL)
    async with facade:
        await facade.capability()

    assert facade._http_client is None  # noqa: SLF001 - the pool is deliberately not public


@pytest.mark.parametrize("base_url", [f"{FACADE_URL}/", f"{FACADE_URL}//", FACADE_URL])
def test_a_trailing_slash_never_doubles_in_a_path(base_url: str) -> None:
    """A base url copied out of a browser carries a trailing slash, and it must not reach the path."""
    assert FacadeClient(base_url).base_url == FACADE_URL


def test_the_query_model_spells_every_parameter_the_facade_reads() -> None:
    """Each field maps to the parameter name the facade honours, several values comma-separated."""
    query = ResourceQuery(
        ids=("a",),
        urls=("http://example.org/q",),
        identifiers=("http://example.org/id|1", "2"),
        questionnaire="http://example.org/fhir/Questionnaire/x",
        tags=("t",),
        attribute_filters=("w75KJ2mc4zz:eq:Ada",),
        text="lovelace",
        count=10,
        page="opaque-cursor",
    )
    assert dict(query.to_query_parameters()) == {
        "_id": "a",
        "url": "http://example.org/q",
        "identifier": "http://example.org/id|1,2",
        "questionnaire": "http://example.org/fhir/Questionnaire/x",
        "_tag": "t",
        "d2-attribute": "w75KJ2mc4zz:eq:Ada",
        "_content": "lovelace",
        "_count": "10",
        "page": "opaque-cursor",
    }


def test_a_count_of_zero_is_sent_rather_than_dropped() -> None:
    """`_count=0` asks the facade for the total and no entries, which is not the same as asking nothing."""
    assert dict(ResourceQuery(count=0).to_query_parameters()) == {"_count": "0"}

"""Who the facade serves: the three postures, the two scopes, and the refusals that come before a request.

The table under test is posture by scope. For each cell the questions are the same three - which
addresses answer without a credential, which refuse, and what a credential that is accepted then
establishes - and the answers are what `docs/fhir/301-serving.md` states to a deployer.

Two things are checked here that are not about one request at all. The startup refusals live in
`ServeSettings.resolve`, so a posture a run could not honour is a line before the socket opens rather
than a 401 on every caller; and the DHIS2 validator is checked against `respx` for the one property
that matters most - the header that leaves this process is the CALLER'S, never the runtime's.

`/whoami` gets a section of its own, because it is the one address whose answer is the posture's
verdict rather than a resource. The questions there are what each posture names a caller, that the
verdict is the same under both scopes, and that a run checking nobody serves no such address at all.

The last section is the same property one layer down, on the reads themselves: what
`CallerCredentialReader` puts on the wire, and which DHIS2 verdicts it carries back as they stand.
The register routes that use it are exercised end to end in `test_register.py`.
"""

from __future__ import annotations

import base64
import hmac
import json
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from dhis2w_client.errors import Dhis2ApiError, Dhis2ClientError
from dhis2w_fhir.config import FhirProject, ServeAuth, ServeAuthScope, load_fhir_config
from dhis2w_fhir_serve import auth as auth_module
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.auth import (
    AUTHENTICATION_REALM,
    BROWSER_SAFE_BASIC_SCHEME,
    SERVE_TOKENS_VARIABLE,
    AuthState,
    RequestIdentity,
    ServeAuthConfigurationError,
    challenge_for,
    credential_key,
    matches_a_serve_token,
    preflight_auth,
    read_serve_tokens,
    validate_with_dhis2,
)
from dhis2w_fhir_serve.passthrough import (
    FACADE_PROVENANCE_HEADER,
    CallerCredentialReader,
    UpstreamRefusalError,
    open_pass_through_client,
)
from dhis2w_fhir_serve.routes import serve_routers
from dhis2w_fhir_serve.routes.whoami import TOKEN_CALLER_NAME, WHOAMI_PATH, authenticated_caller
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool, StoredResponseEnvelope
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

#: The facade's own address in in-process requests, matching the suite's conftest.
BASE_URL = "http://serve.test"

#: The instance a `dhis2` posture checks its callers against, and the credentials one caller sends.
INSTANCE_URL = "https://play.example.org/dhis"
CALLER_BASIC = f"Basic {base64.b64encode(b'clerk:secret').decode('ascii')}"
CALLER_PERSONAL_ACCESS_TOKEN = "ApiToken d2pat_aCallersOwnToken"
RUNTIME_BASIC = f"Basic {base64.b64encode(b'facade:facade-password').decode('ascii')}"

#: What this deployment's `token` posture accepts, and one value it does not.
DEPLOYMENT_TOKENS = "first-token,second-token"
WRONG_TOKEN = "third-token"


@pytest.fixture
def serving_project(compiled_project: FhirProject, stored_responses: tuple[StoredResponseEnvelope, ...]) -> FhirProject:
    """The compiled project with its spool seeded, which the read and scope cases are served over."""
    spool = ResponseSpool.at(compiled_project.project_root)
    for envelope in stored_responses:
        spool.save(envelope)
    return compiled_project


@pytest.fixture
def receiving_project(capture_project: FhirProject) -> FhirProject:
    """The golden project with an empty spool, which every case that actually captures is served over.

    A submission is validated against the served guide, so a posture test that posts one has to be
    served the guide the goldens answer - `compiled_project` publishes a form the golden does not fill.
    """
    return capture_project


def _settings(project: FhirProject, posture: ServeAuth, scope: ServeAuthScope) -> ServeSettings:
    """One facade's settings for a posture and a scope, over a project on disk."""
    return ServeSettings(
        project_dir=project.project_root,
        auth=posture,
        auth_scope=scope,
        dhis2_base_url=INSTANCE_URL if posture is ServeAuth.DHIS2 else None,
    )


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """An in-process client over one facade, with its lifespan run around the body."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


@pytest.fixture
def deployment_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tokens a `token` posture accepts, which come from the environment and from nowhere else."""
    monkeypatch.setenv(SERVE_TOKENS_VARIABLE, DEPLOYMENT_TOKENS)


@pytest.fixture
def dhis2_identity() -> Iterator[respx.MockRouter]:
    """The instance answering `GET /api/me` for a caller it knows, with every other call unmocked."""
    with respx.mock(base_url=INSTANCE_URL, assert_all_called=False) as router:
        router.get("/api/me").mock(
            return_value=httpx.Response(200, json={"id": "u1", "username": "clerk", "displayName": "A Clerk"})
        )
        yield router


# ---------------------------------------------------------------------------------------------
# The startup refusals: a posture a run could not honour never gets as far as a request.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.7", "fhir.example.org"])
def test_an_interface_other_than_loopback_is_refused_while_no_posture_is_stated(host: str) -> None:
    """The refusal names the line to write, because a deployer meeting it is deciding what to serve."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(posture=ServeAuth.NONE, host=host, live=False, stated=False)

    assert 'auth = "none"' in str(refused.value)
    assert 'auth = "token"' in str(refused.value)
    assert 'auth = "dhis2"' in str(refused.value)
    assert SERVE_TOKENS_VARIABLE in str(refused.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.53", "::1", "localhost", "LOCALHOST", "[::1]"])
def test_loopback_with_no_posture_stated_is_the_demo_and_stays_frictionless(host: str) -> None:
    """A server only this machine can reach is the case the absent key was always about."""
    preflight_auth(posture=ServeAuth.NONE, host=host, live=False, stated=False)


def test_the_same_interface_passes_the_moment_the_posture_is_written_down() -> None:
    """`auth = "none"` is a sentence somebody wrote, which is the whole difference from an absent key."""
    preflight_auth(posture=ServeAuth.NONE, host="0.0.0.0", live=False, stated=True)


def test_the_token_posture_is_refused_with_its_variable_unset() -> None:
    """A server that started with no tokens would refuse every caller, having promised to accept some."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(posture=ServeAuth.TOKEN, host="127.0.0.1", live=False, stated=True, environment={})

    assert SERVE_TOKENS_VARIABLE in str(refused.value)
    assert "fhir.toml" in str(refused.value)


def test_the_token_posture_starts_once_the_variable_names_a_token() -> None:
    """The tokens come from the environment, which is what keeps them out of a file projects commit."""
    preflight_auth(
        posture=ServeAuth.TOKEN,
        host="127.0.0.1",
        live=False,
        stated=True,
        environment={SERVE_TOKENS_VARIABLE: DEPLOYMENT_TOKENS},
    )


def test_the_dhis2_posture_is_refused_on_a_compiled_run() -> None:
    """There is no instance behind a compiled guide, so there is nobody to check a caller against."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(posture=ServeAuth.DHIS2, host="127.0.0.1", live=False, stated=True)

    assert "--live" in str(refused.value)


def test_the_dhis2_posture_starts_on_a_live_run() -> None:
    """A live run reads an instance, which is the instance it checks its callers against."""
    preflight_auth(posture=ServeAuth.DHIS2, host="127.0.0.1", live=True, stated=True)


def test_the_resolve_preflight_is_the_one_the_command_and_an_embedder_share(tmp_path: Path) -> None:
    """The refusal lives in `ServeSettings.resolve`, beside the sibling preflights, so both meet it."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(_PROJECT_CONFIG, encoding="utf-8")
    compiled = tmp_path / "ig" / "fsh-generated" / "resources"
    compiled.mkdir(parents=True)
    (compiled / "Questionnaire-q.json").write_text(json.dumps({"resourceType": "Questionnaire", "id": "q"}))
    project = FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())

    with pytest.raises(ServeAuthConfigurationError):
        ServeSettings.resolve(project, host="0.0.0.0")


_PROJECT_CONFIG = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""


# ---------------------------------------------------------------------------------------------
# The token posture: constant-time comparison, and what a wrong token is told.
# ---------------------------------------------------------------------------------------------


def test_a_presented_token_is_compared_with_hmac_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    """The comparison is the constant-time one, so a refusal's timing says nothing about the token."""
    compared: list[tuple[str, str]] = []

    def _record(left: str, right: str) -> bool:
        compared.append((left, right))
        return left == right

    monkeypatch.setattr(hmac, "compare_digest", _record)

    assert matches_a_serve_token("second-token", ("first-token", "second-token")) is True
    assert compared == [("second-token", "first-token"), ("second-token", "second-token")]


def test_every_configured_token_is_compared_even_after_one_matches() -> None:
    """Returning on the first hit would make the time a request takes name which token was sent."""
    comparisons = 0
    original = hmac.compare_digest

    def _count(left: str, right: str) -> bool:
        nonlocal comparisons
        comparisons += 1
        return bool(original(left, right))

    hmac.compare_digest = _count  # type: ignore[assignment]
    try:
        assert matches_a_serve_token("first-token", ("first-token", "second-token", "third-token")) is True
    finally:
        hmac.compare_digest = original

    assert comparisons == 3


def test_the_tokens_are_read_off_the_environment_variable_comma_separated() -> None:
    """Blanks are dropped rather than accepted, so a trailing comma is not a token that matches nothing."""
    assert read_serve_tokens({SERVE_TOKENS_VARIABLE: " first , ,second, "}) == ("first", "second")
    assert read_serve_tokens({}) == ()


def test_the_cache_key_is_a_hash_rather_than_the_header() -> None:
    """The process holds no plaintext credential in a dictionary, which is what the hash is for."""
    key = credential_key(CALLER_BASIC)

    assert key != CALLER_BASIC
    assert "secret" not in key
    assert key == credential_key(CALLER_BASIC)


async def test_the_token_posture_answers_a_capture_only_for_a_token_it_holds(
    receiving_project: FhirProject, aggregate_response: dict[str, Any], deployment_tokens: None
) -> None:
    """A right token captures, a wrong one is refused, and both are told which scheme this server takes."""
    app = create_app(_settings(receiving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))
    body = json.dumps(aggregate_response)

    async with _client(app) as http:
        anonymous = await http.post("/QuestionnaireResponse", content=body)
        wrong = await http.post(
            "/QuestionnaireResponse", content=body, headers={"Authorization": f"Bearer {WRONG_TOKEN}"}
        )
        right = await http.post(
            "/QuestionnaireResponse", content=body, headers={"Authorization": "Bearer second-token"}
        )

        assert anonymous.status_code == 401
        assert anonymous.headers["www-authenticate"] == challenge_for(ServeAuth.TOKEN)
        assert anonymous.json()["issue"][0]["code"] == "login"
        assert wrong.status_code == 401
        assert right.status_code == 201


async def test_a_credential_in_the_wrong_scheme_is_refused_by_the_token_posture(
    receiving_project: FhirProject, aggregate_response: dict[str, Any], deployment_tokens: None
) -> None:
    """`Basic` is not what this posture takes, and the refusal says which scheme is."""
    app = create_app(_settings(receiving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))

    async with _client(app) as http:
        refused = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": CALLER_BASIC},
        )

        assert refused.status_code == 401
        assert "Bearer" in refused.json()["issue"][0]["diagnostics"]


async def test_a_token_capture_records_no_submitter(
    receiving_project: FhirProject, aggregate_response: dict[str, Any], deployment_tokens: None
) -> None:
    """A static token names nobody, so the receipt names nobody - which is the honest receipt."""
    app = create_app(_settings(receiving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))

    listing: dict[str, Any] = {}
    async with _client(app) as http:
        created = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": "Bearer first-token"},
        )
        assert created.status_code == 201
        listing = (await http.get("/spool")).json()

    captured = [row for row in listing["responses"] if row["submitted_by"] is not None]
    assert captured == []


# ---------------------------------------------------------------------------------------------
# The scopes: which addresses each one leaves open.
# ---------------------------------------------------------------------------------------------


#: The addresses a `write` scope leaves open, one per surface it is claimed to leave open.
OPEN_UNDER_WRITE = ("/metadata", "/Questionnaire", "/Questionnaire/d2-pr-anc-visit-q", "/spool", "/uiconfig")


@pytest.mark.parametrize("path", OPEN_UNDER_WRITE)
async def test_the_write_scope_leaves_every_read_open(
    serving_project: FhirProject, deployment_tokens: None, path: str
) -> None:
    """Reads, the conformance document, and the facade's own listings are served without a credential."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))

    async with _client(app) as http:
        assert (await http.get(path)).status_code == 200


@pytest.mark.parametrize("path", OPEN_UNDER_WRITE)
async def test_the_all_scope_closes_everything_but_the_conformance_document(
    serving_project: FhirProject, deployment_tokens: None, path: str
) -> None:
    """`/metadata` stays open so a client can read the posture it is expected to meet."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, ServeAuthScope.ALL))

    answered: httpx.Response | None = None
    async with _client(app) as http:
        answered = await http.get(path)

    assert answered is not None
    assert answered.status_code == (200 if path == "/metadata" else 401)


async def test_the_all_scope_serves_the_same_reads_once_a_credential_arrives(
    serving_project: FhirProject, deployment_tokens: None
) -> None:
    """Closed is not gone: every address answers as it always did to a caller this server accepts."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, ServeAuthScope.ALL))
    headers = {"Authorization": "Bearer first-token"}

    async with _client(app) as http:
        for path in OPEN_UNDER_WRITE:
            assert (await http.get(path, headers=headers)).status_code == 200


async def test_the_write_scope_guards_the_create_and_nothing_else_that_posts(
    serving_project: FhirProject, deployment_tokens: None
) -> None:
    """`$generate` and `/evaluate` are POSTs that write nothing, so a write scope leaves both open."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))

    generated: httpx.Response | None = None
    evaluated: httpx.Response | None = None
    async with _client(app) as http:
        generated = await http.post("/Questionnaire/d2-pr-anc-visit-q/$generate")
        evaluated = await http.post(
            "/evaluate",
            json={"expression": "1 + 1", "language": "fhirpath", "context": {"kind": "inline", "resource": {}}},
        )

    assert generated is not None and evaluated is not None
    assert generated.status_code != 401
    assert evaluated.status_code != 401


def test_the_guarded_set_under_write_is_the_create_route_and_the_one_that_names_the_caller() -> None:
    """One route is state-changing; the other is the check itself, and the set is stated as data."""
    routers = serve_routers(auth=ServeAuth.TOKEN, auth_scope=ServeAuthScope.WRITE)

    assert [route.path for router in routers.guarded for route in router.routes if isinstance(route, APIRoute)] == [
        WHOAMI_PATH,
        "/QuestionnaireResponse",
    ]


def test_a_server_that_receives_nothing_still_answers_who_is_asking() -> None:
    """Putting a 405 behind a credential would answer "who are you" where the answer is "nothing is taken".

    `/whoami` stays guarded on such a run, because a client with a credential still has a credential
    to check - and this address is the only thing on a receive-nothing facade that could check it.
    """
    routers = serve_routers(capture=False, auth=ServeAuth.TOKEN, auth_scope=ServeAuthScope.WRITE)

    assert [route.path for router in routers.guarded for route in router.routes if isinstance(route, APIRoute)] == [
        WHOAMI_PATH
    ]


def test_the_guarded_set_under_all_is_everything_but_the_conformance_document() -> None:
    """The one document a caller must be able to read is the one that says how to authenticate."""
    routers = serve_routers(auth=ServeAuth.TOKEN, auth_scope=ServeAuthScope.ALL)
    guarded = {route.path for router in routers.guarded for route in router.routes if isinstance(route, APIRoute)}

    assert "/metadata" not in guarded
    assert {"/QuestionnaireResponse", "/spool", "/uiconfig", "/{resource_type}"} <= guarded


def test_the_none_posture_guards_nothing_at_all() -> None:
    """The default costs a request nothing, which is what makes it the default."""
    assert serve_routers(auth=ServeAuth.NONE, auth_scope=ServeAuthScope.ALL).guarded == ()


# ---------------------------------------------------------------------------------------------
# The DHIS2 posture: the caller's own header, cached briefly, and the username it establishes.
# ---------------------------------------------------------------------------------------------


async def test_the_validator_sends_the_callers_header_and_never_the_runtimes(
    dhis2_identity: respx.MockRouter,
) -> None:
    """The one property this posture stands on: the facade's own credentials are not a fallback."""
    username = await validate_with_dhis2(INSTANCE_URL, CALLER_BASIC)

    sent = dhis2_identity.calls.last.request
    assert username == "clerk"
    assert sent.headers["authorization"] == CALLER_BASIC
    assert sent.headers["authorization"] != RUNTIME_BASIC
    assert str(sent.url) == f"{INSTANCE_URL}/api/me"


async def test_a_dhis2_personal_access_token_is_replayed_in_the_scheme_dhis2_sends_it_under(
    dhis2_identity: respx.MockRouter,
) -> None:
    """`ApiToken` is how `dhis2w_client`'s PAT provider spells it, so it is what a caller may present."""
    await validate_with_dhis2(INSTANCE_URL, CALLER_PERSONAL_ACCESS_TOKEN)

    assert dhis2_identity.calls.last.request.headers["authorization"] == CALLER_PERSONAL_ACCESS_TOKEN


async def test_credentials_the_instance_refuses_are_refused_here() -> None:
    """A caller who cannot read `/api/me` cannot use this facade, which is the whole of the posture."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(return_value=httpx.Response(401))
        with pytest.raises(auth_module.UnauthenticatedError) as refused:
            await validate_with_dhis2(INSTANCE_URL, CALLER_BASIC)

    assert "401" in str(refused.value)


async def test_an_unreachable_instance_refuses_rather_than_serves() -> None:
    """This facade cannot say who is calling, and serving anyway would answer the question by giving up."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(side_effect=httpx.ConnectError("no route"))
        with pytest.raises(auth_module.UnauthenticatedError):
            await validate_with_dhis2(INSTANCE_URL, CALLER_BASIC)


async def test_an_answer_naming_no_user_is_refused() -> None:
    """An instance that answered 200 with nobody in it has not established anybody."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(return_value=httpx.Response(200, json={"id": "u1"}))
        with pytest.raises(auth_module.UnauthenticatedError):
            await validate_with_dhis2(INSTANCE_URL, CALLER_BASIC)


async def test_the_instance_is_read_once_for_a_run_of_requests_inside_the_cache_window(
    receiving_project: FhirProject, aggregate_response: dict[str, Any], dhis2_identity: respx.MockRouter
) -> None:
    """A round trip per request would make this facade slower than the instance it fronts."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))
    body = json.dumps(aggregate_response)

    async with _client(app) as http:
        for _ in range(3):
            answered = await http.post("/QuestionnaireResponse", content=body, headers={"Authorization": CALLER_BASIC})
            assert answered.status_code == 201

    assert dhis2_identity.calls.call_count == 1


async def test_the_cached_answer_expires_and_the_instance_is_read_again(
    receiving_project: FhirProject,
    aggregate_response: dict[str, Any],
    dhis2_identity: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Short enough that a disabled account stops working in the minute rather than at the next restart."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))
    body = json.dumps(aggregate_response)
    readings = iter([0.0, auth_module.CREDENTIAL_CACHE_SECONDS + 1.0])
    monkeypatch.setattr(auth_module, "current_monotonic", lambda: next(readings))

    async with _client(app) as http:
        for _ in range(2):
            answered = await http.post("/QuestionnaireResponse", content=body, headers={"Authorization": CALLER_BASIC})
            assert answered.status_code == 201

    assert dhis2_identity.calls.call_count == 2


def test_the_cache_drops_an_entry_the_moment_it_has_expired() -> None:
    """The read is what evicts, so an expired entry is never handed back and never lingers."""
    state = AuthState()
    state.cache.remember("key", "clerk", now=100.0)

    assert state.cache.valid("key", now=100.0 + auth_module.CREDENTIAL_CACHE_SECONDS - 1) is not None
    assert state.cache.valid("key", now=100.0 + auth_module.CREDENTIAL_CACHE_SECONDS) is None
    assert state.cache.entries == {}


async def test_two_callers_do_not_share_one_cached_identity(
    receiving_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The key is the header, so a second caller is a second `/api/me` and a second username."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))
    body = json.dumps(aggregate_response)
    other = f"Basic {base64.b64encode(b'nurse:secret').decode('ascii')}"

    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(
            side_effect=[
                httpx.Response(200, json={"username": "clerk"}),
                httpx.Response(200, json={"username": "nurse"}),
            ]
        )
        listing: dict[str, Any] = {}
        async with _client(app) as http:
            await http.post("/QuestionnaireResponse", content=body, headers={"Authorization": CALLER_BASIC})
            await http.post("/QuestionnaireResponse", content=body, headers={"Authorization": other})
            listing = (await http.get("/spool")).json()

    assert sorted(row["submitted_by"] for row in listing["responses"] if row["submitted_by"]) == ["clerk", "nurse"]


async def test_the_validated_username_lands_on_the_receipt(
    receiving_project: FhirProject, aggregate_response: dict[str, Any], dhis2_identity: respx.MockRouter
) -> None:
    """Attribution is the receipt saying who handed this submission over, which nothing else records."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))

    async with _client(app) as http:
        created = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": CALLER_BASIC},
        )
        assert created.status_code == 201
        listing = (await http.get("/spool")).json()

    captured = [row for row in listing["responses"] if row["submitted_by"] is not None]
    assert [row["submitted_by"] for row in captured] == ["clerk"]


async def test_a_bearer_token_is_refused_by_the_dhis2_posture(
    receiving_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """DHIS2 takes Basic and its own personal access tokens, and the refusal names both."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))

    async with _client(app) as http:
        refused = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": "Bearer whatever"},
        )

    assert refused.status_code == 401
    assert "ApiToken" in refused.json()["issue"][0]["diagnostics"]
    assert refused.headers["www-authenticate"].startswith(f"{BROWSER_SAFE_BASIC_SCHEME} ")


def test_the_dhis2_challenge_is_one_a_browser_hands_back_to_the_page() -> None:
    """`WWW-Authenticate: Basic` makes a browser open its own dialog and leave the request pending.

    That is the whole reason the scheme name is not `Basic`: a capture screen's Submit would sit
    there forever instead of rendering the refusal the server sent it. What callers SEND is
    untouched, and the refusal still says which scheme to send.
    """
    challenge = challenge_for(ServeAuth.DHIS2)

    assert challenge.startswith(f"{BROWSER_SAFE_BASIC_SCHEME} ")
    assert not challenge.startswith("Basic")
    assert f'realm="{AUTHENTICATION_REALM}"' in challenge


async def test_a_stale_credential_meets_that_challenge_on_the_capture_itself(
    receiving_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The case `/whoami` cannot cover: a password changed after somebody signed in, met at the submission."""
    app = create_app(_settings(receiving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))

    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(return_value=httpx.Response(401))
        refused: httpx.Response | None = None
        async with _client(app) as http:
            refused = await http.post(
                "/QuestionnaireResponse",
                content=json.dumps(aggregate_response),
                headers={"Authorization": CALLER_BASIC},
            )

    assert refused is not None
    assert refused.status_code == 401
    assert not refused.headers["www-authenticate"].startswith("Basic")
    assert refused.json()["resourceType"] == "OperationOutcome"


def test_an_identity_is_what_a_route_reads_and_nothing_else() -> None:
    """The model is the whole of what a posture establishes: which posture, and who, where there is a who."""
    assert RequestIdentity(posture=ServeAuth.TOKEN).username is None
    assert RequestIdentity(posture=ServeAuth.DHIS2, username="clerk").username == "clerk"


# ---------------------------------------------------------------------------------------------
# The none posture: unchanged, and stated.
# ---------------------------------------------------------------------------------------------


async def test_the_none_posture_serves_every_caller(
    receiving_project: FhirProject, aggregate_response: dict[str, Any]
) -> None:
    """The default is what it always was, and a capture under it records no submitter."""
    app = create_app(_settings(receiving_project, ServeAuth.NONE, ServeAuthScope.ALL))

    async with _client(app) as http:
        created = await http.post("/QuestionnaireResponse", content=json.dumps(aggregate_response))
        assert created.status_code == 201
        assert (await http.get("/metadata")).status_code == 200
        listing = (await http.get("/spool")).json()

    assert [row for row in listing["responses"] if row["submitted_by"] is not None] == []


async def test_the_posture_crosses_to_the_capture_ui_by_name_and_nothing_else_does(
    serving_project: FhirProject, deployment_tokens: None
) -> None:
    """A screen draws the right prompt from the name; a token on this document would be a leaked token."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, ServeAuthScope.WRITE))

    async with _client(app) as http:
        body = (await http.get("/uiconfig")).json()

    assert body["auth"] == {"posture": "token", "scope": "write", "issuer": None}
    assert DEPLOYMENT_TOKENS not in str(body)


# ---------------------------------------------------------------------------------------------
# `/whoami`: a verdict on a credential, before anything has been done with it.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scope", [ServeAuthScope.WRITE, ServeAuthScope.ALL])
async def test_the_dhis2_posture_names_the_username_the_instance_gave(
    serving_project: FhirProject, dhis2_identity: respx.MockRouter, scope: ServeAuthScope
) -> None:
    """The verdict is the same under both scopes, which is the one thing this address needs to be worth asking."""
    app = create_app(_settings(serving_project, ServeAuth.DHIS2, scope))

    async with _client(app) as http:
        named = await http.get(WHOAMI_PATH, headers={"Authorization": CALLER_BASIC})

    assert named.status_code == 200
    assert named.json() == {"posture": "dhis2", "username": "clerk", "name": "clerk"}


@pytest.mark.parametrize("scope", [ServeAuthScope.WRITE, ServeAuthScope.ALL])
async def test_credentials_the_instance_refuses_are_refused_at_this_address_too(
    serving_project: FhirProject, scope: ServeAuthScope
) -> None:
    """A wrong password answers 401 here rather than being found out at the first capture."""
    app = create_app(_settings(serving_project, ServeAuth.DHIS2, scope))

    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get("/api/me").mock(return_value=httpx.Response(401))
        refused: httpx.Response | None = None
        async with _client(app) as http:
            refused = await http.get(WHOAMI_PATH, headers={"Authorization": CALLER_BASIC})

    assert refused is not None
    assert refused.status_code == 401
    assert refused.json()["resourceType"] == "OperationOutcome"
    assert refused.json()["issue"][0]["code"] == "login"
    assert refused.headers["www-authenticate"] == challenge_for(ServeAuth.DHIS2)


async def test_a_request_with_no_credential_at_all_is_refused_at_this_address(
    serving_project: FhirProject, dhis2_identity: respx.MockRouter
) -> None:
    """The refusal is the one every other route gives, so there is no second vocabulary to read."""
    app = create_app(_settings(serving_project, ServeAuth.DHIS2, ServeAuthScope.WRITE))

    async with _client(app) as http:
        refused = await http.get(WHOAMI_PATH)

    assert refused.status_code == 401
    assert "Basic" in refused.json()["issue"][0]["diagnostics"]


@pytest.mark.parametrize("scope", [ServeAuthScope.WRITE, ServeAuthScope.ALL])
async def test_the_token_posture_names_a_bearer_rather_than_a_person(
    serving_project: FhirProject, deployment_tokens: None, scope: ServeAuthScope
) -> None:
    """A static token names a deployment, so the answer names no username and says so in words."""
    app = create_app(_settings(serving_project, ServeAuth.TOKEN, scope))

    async with _client(app) as http:
        named = await http.get(WHOAMI_PATH, headers={"Authorization": "Bearer first-token"})
        refused = await http.get(WHOAMI_PATH, headers={"Authorization": f"Bearer {WRONG_TOKEN}"})

    assert named.status_code == 200
    assert named.json() == {"posture": "token", "username": None, "name": TOKEN_CALLER_NAME}
    assert refused.status_code == 401


async def test_the_none_posture_names_the_missing_posture_rather_than_a_caller(serving_project: FhirProject) -> None:
    """A server that checks nobody has nobody to name, and says which line would give it somebody.

    The refusal is the address's own rather than the read catch-all's, which would have called
    `whoami` a resource type nobody asked for - it is a fixed path this project documents.
    """
    app = create_app(_settings(serving_project, ServeAuth.NONE, ServeAuthScope.ALL))

    async with _client(app) as http:
        asked = await http.get(WHOAMI_PATH)

    assert asked.status_code == 404
    diagnostics = asked.json()["issue"][0]["diagnostics"]
    assert "authenticates nobody" in diagnostics
    assert "[serve] auth" in diagnostics
    assert "resource type" not in diagnostics


def test_the_answer_is_settled_by_a_posture_rather_than_by_a_scope() -> None:
    """The one path a posture decides the answer of: a refusal under `none`, guarded under both scopes."""

    def _paths(routers: tuple[APIRouter, ...]) -> set[str]:
        return {route.path for router in routers for route in router.routes if isinstance(route, APIRoute)}

    open_to_everyone = serve_routers(auth=ServeAuth.NONE, auth_scope=ServeAuthScope.ALL)
    write = serve_routers(auth=ServeAuth.DHIS2, auth_scope=ServeAuthScope.WRITE)
    everything = serve_routers(auth=ServeAuth.DHIS2, auth_scope=ServeAuthScope.ALL)

    assert WHOAMI_PATH in _paths(open_to_everyone.facade)
    assert WHOAMI_PATH not in _paths(open_to_everyone.guarded)
    assert WHOAMI_PATH in _paths(write.facade) and WHOAMI_PATH in _paths(write.guarded)
    assert WHOAMI_PATH in _paths(everything.facade) and WHOAMI_PATH in _paths(everything.guarded)


def test_a_caller_is_named_from_the_identity_a_posture_established() -> None:
    """One function, so the address and a reader of `RequestIdentity` spell the same caller the same way."""
    person = authenticated_caller(RequestIdentity(posture=ServeAuth.DHIS2, username="clerk"))
    bearer = authenticated_caller(RequestIdentity(posture=ServeAuth.TOKEN))

    assert (person.username, person.name) == ("clerk", "clerk")
    assert (bearer.username, bearer.name) == (None, TOKEN_CALLER_NAME)


# ---------------------------------------------------------------------------------------------
# The pass-through read: whose credentials leave this process, and whose verdict comes back.
# ---------------------------------------------------------------------------------------------


#: One DHIS2 path a register read asks for, and the provenance the facade names itself with.
TRACKER_PATH = "/api/tracker/trackedEntities/PLoWmEuLJl2"
FACADE_PROVENANCE = "dhis2w-fhir-serve/9.9.9"


@asynccontextmanager
async def _reader(header_value: str = CALLER_BASIC) -> AsyncGenerator[CallerCredentialReader]:
    """One caller's reader over the credential-free pool a running facade would hold open."""
    async with open_pass_through_client(INSTANCE_URL, provenance=FACADE_PROVENANCE) as pool:
        yield CallerCredentialReader(
            connection=pool, authorization=header_value, challenge=challenge_for(ServeAuth.DHIS2)
        )


async def test_a_pass_through_read_carries_the_callers_header_and_the_facades_name() -> None:
    """The two headers a read adds: whose credentials it runs under, and what it arrived through."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        route = router.get(TRACKER_PATH).mock(return_value=httpx.Response(200, json={"trackedEntity": "PLoWmEuLJl2"}))
        async with _reader() as reader:
            answered = await reader.get_raw(TRACKER_PATH, {"fields": "trackedEntity"})

    sent = route.calls.last.request
    assert answered == {"trackedEntity": "PLoWmEuLJl2"}
    assert sent.headers["authorization"] == CALLER_BASIC
    assert sent.headers["authorization"] != RUNTIME_BASIC
    assert sent.headers[FACADE_PROVENANCE_HEADER] == FACADE_PROVENANCE
    assert sent.url.params["fields"] == "trackedEntity"


async def test_the_pool_itself_carries_no_credential_to_fall_back_to() -> None:
    """A request that somehow arrived without a caller's header is anonymous, never the facade."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        route = router.get(TRACKER_PATH).mock(return_value=httpx.Response(200, json={}))
        async with open_pass_through_client(INSTANCE_URL, provenance=FACADE_PROVENANCE) as pool:
            await pool.get(TRACKER_PATH)

    assert pool.auth is None
    assert "authorization" not in route.calls.last.request.headers


async def test_the_credential_stays_out_of_the_readers_own_repr() -> None:
    """A model that reaches a log line or a traceback frame prints no password."""
    async with _reader() as reader:
        printed = repr(reader)

    assert "secret" not in printed
    assert CALLER_BASIC not in printed


@pytest.mark.parametrize(("status", "issue"), [(401, "login"), (403, "forbidden")])
async def test_a_verdict_about_the_caller_is_carried_rather_than_replaced(status: int, issue: str) -> None:
    """DHIS2 answered clearly and the answer was about the caller: a 502 would say neither."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get(TRACKER_PATH).mock(return_value=httpx.Response(status, json={"message": "no"}))
        async with _reader() as reader:
            with pytest.raises(UpstreamRefusalError) as refused:
                await reader.get_raw(TRACKER_PATH)

    assert refused.value.status_code == status
    assert refused.value.issue_code == issue
    assert ("WWW-Authenticate" in refused.value.response_headers()) is (status == 401)


async def test_a_verdict_about_the_instance_stays_the_refusal_the_register_already_reads() -> None:
    """A 404 is how a read says nobody is there, and a 400 naming an absent type is how a surface finds nothing."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get(TRACKER_PATH).mock(
            return_value=httpx.Response(404, json={"httpStatusCode": 404, "message": "not found"})
        )
        async with _reader() as reader:
            with pytest.raises(Dhis2ApiError) as refused:
                await reader.get_raw(TRACKER_PATH)

    assert refused.value.status_code == 404
    assert isinstance(refused.value.body, dict)
    assert refused.value.body["message"] == "not found"


async def test_an_unreachable_instance_is_a_failure_to_read_rather_than_an_empty_answer() -> None:
    """The routes answer 502 to this, which is what "this server could not reach DHIS2" means."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get(TRACKER_PATH).mock(side_effect=httpx.ConnectError("no route"))
        async with _reader() as reader:
            with pytest.raises(Dhis2ClientError):
                await reader.get_raw(TRACKER_PATH)


async def test_a_body_that_is_not_json_is_refused_rather_than_read_as_no_results() -> None:
    """A 200 carrying HTML is a proxy or a sign-in page standing in for the API, and hiding it would be worse."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get(TRACKER_PATH).mock(return_value=httpx.Response(200, html="<html>sign in</html>"))
        async with _reader() as reader:
            with pytest.raises(Dhis2ApiError) as refused:
                await reader.get_raw(TRACKER_PATH)

    assert "non-JSON" in refused.value.message


async def test_an_empty_body_is_an_empty_answer_the_way_the_client_reads_one() -> None:
    """DHIS2 answers some reads with nothing at all, and the register reads that as no fields rather than a failure."""
    with respx.mock(base_url=INSTANCE_URL) as router:
        router.get(TRACKER_PATH).mock(return_value=httpx.Response(200, content=b""))
        async with _reader() as reader:
            assert await reader.get_raw(TRACKER_PATH) == {}

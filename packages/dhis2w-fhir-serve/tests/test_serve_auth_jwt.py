"""The `jwt` posture: one external issuer, its published keys, and everything a token has to survive.

WHAT IS REAL HERE. The keys are real RSA and ECDSA keys, generated in this process; the tokens are
really signed with them; the JWKS is the real serialisation of the real public halves; and the
verification is the shipped code path with nothing stubbed inside it. What `respx` stands in for is
the identity provider's two HTTP documents - `/.well-known/openid-configuration` and the JWKS - which
is the only part of this posture that belongs to somebody else's server.

THE TABLE UNDER TEST is one token against one verifier, and the questions are what a reviewer would
ask of any JWT validator: is the signature checked against the right key, is the issuer checked, the
expiry, the not-before, the audience where one was configured; is a key rotation survivable; and can
a caller sending rubbish turn this facade into a load generator pointed at the issuer.

THE TWO THINGS THAT ARE NOT ABOUT A TOKEN AT ALL are the startup refusals - a posture named with no
issuer, and an issuer this machine cannot reach - and the pass-through decision, which under this
posture is a decision NOT to read the register unless the deployment stated that DHIS2 trusts the
same issuer. Both are here because both are properties of a run rather than of a request.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import respx
from dhis2w_fhir.config import FhirProject, ServeAuth, ServeAuthScope, ServeJwtConfig
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.auth import (
    JWT_VERIFIER_ATTRIBUTE,
    RequestIdentity,
    ServeAuthConfigurationError,
    UnauthenticatedError,
    challenge_for,
    open_jwt_verifier,
    preflight_auth,
)
from dhis2w_fhir_serve.capability import (
    JWT_BEARER_TOKEN_SECURITY_TEXT,
    JWT_ISSUER_EXTENSION_URL,
    OAUTH_SECURITY_CODE,
    build_security,
)
from dhis2w_fhir_serve.oidc import (
    JWKS_MINIMUM_CACHE_SECONDS,
    JWT_ALGORITHMS,
    JwtVerifier,
    OidcIssuerUnavailableError,
    TokenRefusedError,
    cache_seconds,
    discover_issuer,
)
from dhis2w_fhir_serve.passthrough import (
    FACADE_PROVENANCE_HEADER,
    RegisterNotForwardableError,
    UpstreamRefusalError,
    open_pass_through_client,
    register_reader,
)
from dhis2w_fhir_serve.routes import FACADE_MOUNT_PATH
from dhis2w_fhir_serve.routes.whoami import WHOAMI_PATH
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.spool import ResponseSpool, StoredResponseEnvelope
from fastapi import FastAPI
from joserfc import jwt as jose_jwt
from joserfc.jwk import ECKey, RSAKey
from starlette.requests import Request

#: The facade's own address in in-process requests, matching the suite's conftest.
BASE_URL = "http://serve.test"

#: Where a caller asks to be named. The router states the path relative to the mount it is
#: included under, and this is that path where a request has to be sent.
WHOAMI_ADDRESS = f"{FACADE_MOUNT_PATH}{WHOAMI_PATH}"

#: The identity provider this deployment federates with, and the two documents it publishes.
ISSUER = "https://idp.example.org/realms/health"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"

#: What this facade was registered as at that provider, and the person one token names.
AUDIENCE = "d2w-fhir-serve"
CALLER = "clerk"

#: The DHIS2 instance a `forward_bearer` run reads, and one register path a caller asks for.
INSTANCE_URL = "https://play.example.org/dhis"
TRACKER_PATH = "/api/tracker/trackedEntities/PLoWmEuLJl2"


class IssuerFixture:
    """One identity provider, standing on real keys - what it signs with, and what it publishes."""

    def __init__(self) -> None:
        """Mint the signing keys this issuer will be known by: one RSA, one ECDSA, one it never publishes."""
        self.rsa = RSAKey.generate_key(2048, parameters={"kid": "rsa-1", "use": "sig", "alg": "RS256"})
        self.ec = ECKey.generate_key("P-256", parameters={"kid": "ec-1", "use": "sig", "alg": "ES256"})
        self.rotated = RSAKey.generate_key(2048, parameters={"kid": "rsa-2", "use": "sig", "alg": "RS256"})
        self.imposter = RSAKey.generate_key(2048, parameters={"kid": "rsa-1", "use": "sig", "alg": "RS256"})
        self.published: list[RSAKey | ECKey] = [self.rsa, self.ec]

    def jwks(self) -> dict[str, Any]:
        """The JWKS document as this issuer serves it - public halves only, which is the whole point."""
        return {"keys": [key.as_dict(private=False) for key in self.published]}

    def discovery(self) -> dict[str, Any]:
        """The discovery document, carrying the four fields an OIDC configuration has to carry."""
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
            "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
            "jwks_uri": JWKS_URL,
        }

    def sign(
        self,
        *,
        key: RSAKey | ECKey | None = None,
        algorithm: str = "RS256",
        kid: str | None = None,
        **claims: Any,
    ) -> str:
        """One token this issuer signs, with whatever claims a case is about."""
        signing = key if key is not None else self.rsa
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "f47ac10b",
            "exp": now + 300,
            "preferred_username": CALLER,
        }
        payload.update(claims)
        for name in [name for name, value in claims.items() if value is None]:
            del payload[name]
        header = {"alg": algorithm, "kid": kid if kid is not None else signing.kid}
        return jose_jwt.encode(header, payload, signing)


@pytest.fixture
def issuer() -> IssuerFixture:
    """The identity provider every case in this file federates with."""
    return IssuerFixture()


@pytest.fixture
def published_issuer(issuer: IssuerFixture) -> Iterator[respx.MockRouter]:
    """That provider actually answering its two documents, with every other call left unmocked."""
    with respx.mock(assert_all_called=False) as router:
        router.get(DISCOVERY_URL).mock(side_effect=lambda request: httpx.Response(200, json=issuer.discovery()))
        router.get(JWKS_URL).mock(side_effect=lambda request: httpx.Response(200, json=issuer.jwks()))
        yield router


@pytest.fixture
def serving_project(compiled_project: FhirProject, stored_responses: tuple[StoredResponseEnvelope, ...]) -> FhirProject:
    """The compiled project with its spool seeded, which the read cases are served over."""
    spool = ResponseSpool.at(compiled_project.project_root)
    for envelope in stored_responses:
        spool.save(envelope)
    return compiled_project


def _jwt_settings(project: FhirProject, **over: Any) -> ServeSettings:
    """One facade's settings under the `jwt` posture, over a project on disk."""
    table: dict[str, Any] = {"issuer": ISSUER, "audience": AUDIENCE}
    table.update(over.pop("jwt", {}))
    return ServeSettings(
        project_dir=project.project_root,
        auth=ServeAuth.JWT,
        auth_scope=over.pop("auth_scope", ServeAuthScope.WRITE),
        jwt=ServeJwtConfig(**table),
        **over,
    )


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """An in-process client over one facade, with its lifespan run around the body."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
            yield http


async def _verifier(issuer_fixture: IssuerFixture, **table: Any) -> JwtVerifier:
    """A verifier that has already read this issuer, which is the state a started server is in."""
    return await discover_issuer(ServeJwtConfig(issuer=ISSUER, **table))


# ---------------------------------------------------------------------------------------------
# The startup refusals: a posture a run could not honour never gets as far as a request.
# ---------------------------------------------------------------------------------------------


def test_the_jwt_posture_is_refused_while_no_issuer_is_named() -> None:
    """There is nothing to verify against, and the refusal names the table and the key to write."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(posture=ServeAuth.JWT, host="127.0.0.1", live=False, stated=True, jwt=ServeJwtConfig())

    assert "[serve.jwt] issuer" in str(refused.value)
    assert "/.well-known/openid-configuration" in str(refused.value)


def test_the_jwt_posture_starts_the_moment_an_issuer_is_named() -> None:
    """An issuer written down is the whole of what this preflight asks for; reaching it is the runtime's."""
    preflight_auth(
        posture=ServeAuth.JWT,
        host="0.0.0.0",
        live=False,
        stated=True,
        jwt=ServeJwtConfig(issuer=ISSUER),
    )


def test_forwarding_a_token_is_refused_on_a_run_with_no_instance_to_forward_to() -> None:
    """A compiled guide has no DHIS2 behind it, so there is nowhere for a forwarded token to go."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(
            posture=ServeAuth.JWT,
            host="127.0.0.1",
            live=False,
            stated=True,
            jwt=ServeJwtConfig(issuer=ISSUER, forward_bearer=True),
        )

    assert "--live" in str(refused.value)


def test_the_refusal_for_an_absent_posture_offers_jwt_among_the_four() -> None:
    """A deployer binding the world reads the four sentences they may write, and this is one of them."""
    with pytest.raises(ServeAuthConfigurationError) as refused:
        preflight_auth(posture=ServeAuth.NONE, host="0.0.0.0", live=False, stated=False)

    assert 'auth = "jwt"' in str(refused.value)
    assert "[serve.jwt] issuer" in str(refused.value)


async def test_an_issuer_this_machine_cannot_reach_refuses_the_run() -> None:
    """A posture that cannot be honoured is a line in a terminal, never a 401 on every caller."""
    with respx.mock as router:
        router.get(DISCOVERY_URL).mock(side_effect=httpx.ConnectError("no route to host"))

        with pytest.raises(ServeAuthConfigurationError) as refused:
            await open_jwt_verifier(ServeJwtConfig(issuer=ISSUER))

    assert ISSUER in str(refused.value)
    assert "[serve.jwt] issuer" in str(refused.value)


async def test_a_discovery_document_that_names_no_keys_refuses_the_run() -> None:
    """An OIDC configuration without a `jwks_uri` names nothing to verify against."""
    with respx.mock as router:
        router.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json={"issuer": ISSUER}))

        with pytest.raises(OidcIssuerUnavailableError):
            await discover_issuer(ServeJwtConfig(issuer=ISSUER))


async def test_an_issuer_that_answers_an_error_refuses_the_run() -> None:
    """A 404 on the well-known path is an issuer identifier that names something else."""
    with respx.mock as router:
        router.get(DISCOVERY_URL).mock(return_value=httpx.Response(404))

        with pytest.raises(OidcIssuerUnavailableError) as refused:
            await discover_issuer(ServeJwtConfig(issuer=ISSUER))

    assert "404" in str(refused.value)


async def test_a_jwks_that_is_not_a_key_set_refuses_the_run(issuer: IssuerFixture) -> None:
    """Reaching the document is not the same as reading it, and both happen before the socket opens."""
    with respx.mock as router:
        router.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=issuer.discovery()))
        router.get(JWKS_URL).mock(return_value=httpx.Response(200, json={"keys": []}))

        with pytest.raises(OidcIssuerUnavailableError) as refused:
            await discover_issuer(ServeJwtConfig(issuer=ISSUER))

    assert JWKS_URL in str(refused.value)


# ---------------------------------------------------------------------------------------------
# One token against one verifier: what holds, and what every kind of wrong is told.
# ---------------------------------------------------------------------------------------------


async def test_a_token_this_issuer_signed_names_the_caller(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """The happy path: signature, issuer, expiry, audience, and the claim that says who this is."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    verified = await verifier.verify(issuer.sign())

    assert verified.username == CALLER
    assert verified.subject == "f47ac10b"
    assert verified.expires_at is not None


async def test_an_ecdsa_signature_is_verified_beside_the_rsa_one(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """Both families are in `JWT_ALGORITHMS`, and an issuer signing with either is an issuer we serve."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    verified = await verifier.verify(issuer.sign(key=issuer.ec, algorithm="ES256"))

    assert verified.username == CALLER
    assert "ES256" in JWT_ALGORITHMS


async def test_a_token_from_another_issuer_is_refused_by_name(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """A signature that holds says who signed, not who this server trusts; the refusal names both."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(iss="https://idp.example.org/realms/other"))

    assert "realms/other" in refused.value.diagnostics
    assert ISSUER in refused.value.diagnostics


async def test_a_token_for_another_audience_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """An issuer minting for several services is minting tokens this facade may not accept for them."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(aud="some-other-service"))

    assert AUDIENCE in refused.value.diagnostics


async def test_an_audience_stated_as_a_list_holds_when_it_names_this_server(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """RFC 7519 lets `aud` be a list, and a token naming several services still names this one."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    verified = await verifier.verify(issuer.sign(aud=["another-service", AUDIENCE]))

    assert verified.username == CALLER


async def test_no_configured_audience_takes_whatever_this_issuer_signed(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """A deployment with an issuer of its own has nothing to disambiguate, and states no audience."""
    verifier = await _verifier(issuer)

    verified = await verifier.verify(issuer.sign(aud=None))

    assert verified.username == CALLER


async def test_an_expired_token_is_refused(issuer: IssuerFixture, published_issuer: respx.MockRouter) -> None:
    """The one property a JWKS validator trades introspection for is short lifetimes, honoured here."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(exp=int(time.time()) - 3600))

    assert "not currently valid" in refused.value.diagnostics


async def test_a_token_that_is_not_valid_yet_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """`nbf` in the future is a token minted for later, and later is not now."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError):
        await verifier.verify(issuer.sign(nbf=int(time.time()) + 3600))


async def test_a_token_with_no_expiry_at_all_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """A token that never expires is a credential nobody can withdraw, and this server takes none."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError):
        await verifier.verify(issuer.sign(exp=None))


async def test_a_signature_by_the_wrong_key_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """Somebody else's RSA key under this issuer's `kid` is the forgery this whole check exists for."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(key=issuer.imposter))

    assert "not signed by the key it names" in refused.value.diagnostics


async def test_a_value_that_is_not_a_token_at_all_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """A caller pasting the wrong string gets a sentence about what this server takes."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify("not-a-token")

    assert ISSUER in refused.value.diagnostics


async def test_a_token_naming_no_username_claim_is_refused(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """This server records who captured every response, so a token naming nobody cannot capture one."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(preferred_username=None))

    assert "preferred_username" in refused.value.diagnostics
    assert "[serve.jwt] username_claim" in refused.value.diagnostics


async def test_a_deployment_may_name_the_claim_its_issuer_puts_the_username_in(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """`preferred_username` is the OIDC convention and the default, not a requirement on the issuer."""
    verifier = await _verifier(issuer, username_claim="dhis2_username")

    verified = await verifier.verify(issuer.sign(preferred_username=None, dhis2_username="mobile-clerk"))

    assert verified.username == "mobile-clerk"


# ---------------------------------------------------------------------------------------------
# The keys: rotation, the cache floor, and what a stream of bad `kid`s costs the issuer.
# ---------------------------------------------------------------------------------------------


async def test_an_unknown_key_id_reads_the_keys_again_and_then_accepts_the_rotation(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """A rotation is the ordinary reason for an unknown `kid`, and refusing it would be an outage."""
    verifier = await _verifier(issuer, audience=AUDIENCE)
    issuer.published = [issuer.rotated, issuer.ec]

    verified = await verifier.verify(issuer.sign(key=issuer.rotated))

    assert verified.username == CALLER
    assert published_issuer.routes[1].call_count == 2


async def test_a_key_id_that_never_existed_is_refused_after_one_refetch(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """One look, then a refusal that says the issuer was asked again and still does not publish it."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    with pytest.raises(TokenRefusedError) as refused:
        await verifier.verify(issuer.sign(kid="never-minted"))

    assert "even after reading them again" in refused.value.diagnostics
    assert published_issuer.routes[1].call_count == 2


async def test_a_stream_of_unknown_key_ids_costs_the_issuer_one_read(
    issuer: IssuerFixture, published_issuer: respx.MockRouter
) -> None:
    """The refetch floor is what stops a caller turning this facade into a load generator."""
    verifier = await _verifier(issuer, audience=AUDIENCE)

    for _ in range(5):
        with pytest.raises(TokenRefusedError):
            await verifier.verify(issuer.sign(kid="never-minted"))

    assert published_issuer.routes[1].call_count == 2


async def test_the_keys_are_held_for_the_floor_however_short_the_issuer_asked(
    issuer: IssuerFixture,
) -> None:
    """`max-age=0` on a document of public keys would make every request a round trip to the issuer."""
    with respx.mock as router:
        router.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=issuer.discovery()))
        jwks = router.get(JWKS_URL).mock(
            return_value=httpx.Response(200, json=issuer.jwks(), headers={"Cache-Control": "max-age=0, no-cache"})
        )
        verifier = await discover_issuer(ServeJwtConfig(issuer=ISSUER))
        for _ in range(3):
            await verifier.verify(issuer.sign())

    assert jwks.call_count == 1
    assert verifier.held is not None
    assert verifier.held.expires_at - verifier.held.fetched_at == pytest.approx(JWKS_MINIMUM_CACHE_SECONDS)


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        ("", 3600.0),
        ("no-store", 3600.0),
        ("max-age=0", JWKS_MINIMUM_CACHE_SECONDS),
        ("max-age=60", JWKS_MINIMUM_CACHE_SECONDS),
        ("public, max-age=86400", 86400.0),
        ("max-age=not-a-number", 3600.0),
    ],
)
def test_a_cache_control_is_honoured_above_the_floor_and_ignored_below_it(stated: str, expected: float) -> None:
    """The floor is the whole of the policy; there is no ceiling, because a rotation is caught by `kid`."""
    assert cache_seconds(httpx.Headers({"Cache-Control": stated} if stated else {})) == expected


# ---------------------------------------------------------------------------------------------
# The posture end to end: what a request is refused with, and who a receipt says captured it.
# ---------------------------------------------------------------------------------------------


async def test_a_request_with_no_token_is_told_which_issuer_to_get_one_from(
    serving_project: FhirProject, published_issuer: respx.MockRouter, aggregate_response: dict[str, Any]
) -> None:
    """Obtaining a token is the issuer's business, so the refusal at least says whose business it is."""
    app = create_app(_jwt_settings(serving_project))

    async with _client(app) as http:
        refused = await http.post("/QuestionnaireResponse", content=json.dumps(aggregate_response))

    assert refused.status_code == 401
    assert ISSUER in refused.json()["issue"][0]["diagnostics"]
    assert ISSUER in refused.headers["www-authenticate"]
    assert refused.headers["www-authenticate"].startswith("Bearer ")


async def test_a_credential_in_the_wrong_scheme_is_refused(
    serving_project: FhirProject, published_issuer: respx.MockRouter, aggregate_response: dict[str, Any]
) -> None:
    """`Basic` is not what this posture takes, and the refusal says which scheme is."""
    app = create_app(_jwt_settings(serving_project))

    async with _client(app) as http:
        refused = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": "Basic Y2xlcms6c2VjcmV0"},
        )

    assert refused.status_code == 401
    assert "Bearer" in refused.json()["issue"][0]["diagnostics"]


async def test_a_capture_records_the_username_the_token_named(
    capture_project: FhirProject,
    published_issuer: respx.MockRouter,
    issuer: IssuerFixture,
    aggregate_response: dict[str, Any],
) -> None:
    """The claim becomes the request identity, and the receipt records it exactly as `dhis2` does."""
    app = create_app(_jwt_settings(capture_project))

    async with _client(app) as http:
        created = await http.post(
            "/QuestionnaireResponse",
            content=json.dumps(aggregate_response),
            headers={"Authorization": f"Bearer {issuer.sign()}"},
        )
        assert created.status_code == 201
        listing = (await http.get("/facade/spool")).json()

    assert [row["submitted_by"] for row in listing["responses"] if row["submitted_by"] is not None] == [CALLER]


async def test_the_issuer_crosses_to_the_capture_ui_and_nothing_else_about_the_table_does(
    serving_project: FhirProject, published_issuer: respx.MockRouter
) -> None:
    """A screen has to name whose token to ask for; the audience and the claim are nobody's business."""
    app = create_app(_jwt_settings(serving_project))

    async with _client(app) as http:
        body = (await http.get("/facade/uiconfig")).json()

    assert body["auth"] == {"posture": "jwt", "scope": "write", "issuer": ISSUER}
    assert AUDIENCE not in json.dumps(body)


async def test_the_verifier_is_on_the_application_by_the_time_a_request_arrives(
    serving_project: FhirProject, published_issuer: respx.MockRouter
) -> None:
    """The issuer is read while the server starts, so no caller ever waits for a JWKS fetch."""
    app = create_app(_jwt_settings(serving_project))

    async with _client(app):
        held = getattr(app.state, JWT_VERIFIER_ATTRIBUTE, None)

    assert isinstance(held, JwtVerifier)
    assert held.jwks_uri == JWKS_URL
    assert held.held is not None


@pytest.mark.parametrize("scope", [ServeAuthScope.WRITE, ServeAuthScope.ALL])
async def test_whoami_names_the_claim_this_server_read_out_of_the_token(
    serving_project: FhirProject, published_issuer: respx.MockRouter, issuer: IssuerFixture, scope: ServeAuthScope
) -> None:
    """The same value a receipt is stamped with, answered on its own so a client can check a token."""
    app = create_app(_jwt_settings(serving_project, auth_scope=scope))

    async with _client(app) as http:
        named = await http.get(WHOAMI_ADDRESS, headers={"Authorization": f"Bearer {issuer.sign()}"})

    assert named.status_code == 200
    assert named.json() == {"posture": "jwt", "username": CALLER, "name": CALLER}


async def test_whoami_refuses_a_token_this_issuer_did_not_sign(
    serving_project: FhirProject, published_issuer: respx.MockRouter, issuer: IssuerFixture
) -> None:
    """A forged token is refused here exactly as it is anywhere else, and told whose token to bring."""
    app = create_app(_jwt_settings(serving_project))

    async with _client(app) as http:
        refused = await http.get(
            WHOAMI_ADDRESS, headers={"Authorization": f"Bearer {issuer.sign(key=issuer.imposter)}"}
        )

    assert refused.status_code == 401
    assert refused.json()["issue"][0]["code"] == "login"
    assert ISSUER in refused.headers["www-authenticate"]


def test_an_identity_under_this_posture_names_the_person_the_claim_named() -> None:
    """The same field the receipts and the pass-through machinery already read, filled by a claim."""
    assert RequestIdentity(posture=ServeAuth.JWT, username=CALLER).username == CALLER


def test_the_challenge_names_the_issuer_a_token_has_to_come_from() -> None:
    """RFC 6750 has no parameter for it, so it rides in `error_description`, which is prose by design."""
    assert challenge_for(ServeAuth.JWT, ISSUER) == (
        f'Bearer realm="d2w fhir serve", error_description="a token from {ISSUER}"'
    )
    assert challenge_for(ServeAuth.JWT) == 'Bearer realm="d2w fhir serve"'


# ---------------------------------------------------------------------------------------------
# What `/metadata` declares: the scheme, the issuer, and what the register does under it.
# ---------------------------------------------------------------------------------------------


def test_the_conformance_document_names_the_issuer_and_no_key() -> None:
    """The issuer is printed inside every token it signs, so stating it discloses nothing."""
    security = build_security(ServeAuth.JWT, ServeAuthScope.WRITE, issuer=ISSUER, forward_bearer=False)

    assert security.extension is not None
    assert security.extension[0].url == JWT_ISSUER_EXTENSION_URL
    assert security.extension[0].valueString == ISSUER
    assert security.service is not None
    assert security.service[0].text == JWT_BEARER_TOKEN_SECURITY_TEXT
    assert security.service[0].coding is not None
    assert security.service[0].coding[0].code == OAUTH_SECURITY_CODE


def test_the_conformance_document_says_the_register_is_not_served_without_forwarding() -> None:
    """A client discovering that from a 501 would be a client this document had misled."""
    security = build_security(ServeAuth.JWT, ServeAuthScope.WRITE, issuer=ISSUER, forward_bearer=False)

    assert security.description is not None
    assert "The register is not served here" in security.description
    assert "forward_bearer" in security.description


def test_the_conformance_document_says_the_register_is_read_as_the_caller_when_it_is() -> None:
    """With both halves stated, the register is answered under DHIS2's own gates for the person asking."""
    security = build_security(ServeAuth.JWT, ServeAuthScope.WRITE, issuer=ISSUER, forward_bearer=True)

    assert security.description is not None
    assert "under your own DHIS2 authorization" in security.description


async def test_the_served_metadata_carries_the_posture_a_client_has_to_meet(
    serving_project: FhirProject, published_issuer: respx.MockRouter
) -> None:
    """`/metadata` is open in every posture, which is what makes the declaration reachable."""
    app = create_app(_jwt_settings(serving_project, auth_scope=ServeAuthScope.ALL))

    async with _client(app) as http:
        statement = (await http.get("/metadata")).json()

    security = statement["rest"][0]["security"]
    assert security["extension"][0]["valueString"] == ISSUER
    assert security["service"][0]["text"] == JWT_BEARER_TOKEN_SECURITY_TEXT


# ---------------------------------------------------------------------------------------------
# `forward_bearer`: the register read as the caller, or not read at all - and never as the facade.
# ---------------------------------------------------------------------------------------------


def _register_request(app: FastAPI, authorization: str | None = None) -> Request:
    """One request as a route handler would meet it, over a facade that has already started.

    Built by hand rather than driven through a route because what is under test is the DECISION
    `register_reader` makes - which channel a register read runs over - and every register route in
    this facade reaches it through the same dependency. `test_register.py` drives the routes.
    """
    headers = [] if authorization is None else [(b"authorization", authorization.encode("ascii"))]
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/Patient",
        "raw_path": b"/Patient",
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "app": app,
        "state": {},
    }
    return Request(scope)


@asynccontextmanager
async def _forwarding_facade(project: FhirProject, *, forward_bearer: bool) -> AsyncGenerator[FastAPI]:
    """A started facade under `jwt`, holding a live connection and the credential-free pool beside it.

    The two connections are put on the application the way `attach_serve_runtime` puts them there.
    A live store is not what this is about - which channel a read runs over is - so the store stays
    the compiled one and the connections are what a live run would have handed the routes.
    """
    app = create_app(_jwt_settings(project, jwt={"forward_bearer": forward_bearer}))
    async with (
        app.router.lifespan_context(app),
        open_pass_through_client(INSTANCE_URL, provenance="dhis2w-fhir-serve/9.9.9") as pool,
    ):
        app.state.live_client = pool
        app.state.caller_client = pool
        yield app


async def test_the_register_is_refused_rather_than_read_as_the_facade(
    serving_project: FhirProject, published_issuer: respx.MockRouter, issuer: IssuerFixture
) -> None:
    """The superuser trap closed: no token forwarded means no register, never the facade's own rights."""
    async with _forwarding_facade(serving_project, forward_bearer=False) as app:
        request = _register_request(app, f"Bearer {issuer.sign()}")

        with pytest.raises(RegisterNotForwardableError) as refused:
            await register_reader(request)

    assert refused.value.status_code == 501
    assert refused.value.issue_code == "not-supported"
    assert "forward_bearer = true" in refused.value.diagnostics
    assert "oidc.jwt.token.authentication.enabled" in refused.value.diagnostics


async def test_the_register_read_carries_the_callers_own_token_when_forwarding_is_stated(
    serving_project: FhirProject, published_issuer: respx.MockRouter, issuer: IssuerFixture
) -> None:
    """The same opaque forward the `dhis2` posture makes, with a `Bearer` value instead of a `Basic` one."""
    token = issuer.sign()

    async with _forwarding_facade(serving_project, forward_bearer=True) as app:
        published_issuer.get(f"{INSTANCE_URL}{TRACKER_PATH}").mock(
            return_value=httpx.Response(200, json={"trackedEntity": "PLoWmEuLJl2"})
        )
        reader = await register_reader(_register_request(app, f"Bearer {token}"))
        assert reader is not None
        answered = await reader.get_raw(TRACKER_PATH)

    sent = published_issuer.calls.last.request
    assert answered == {"trackedEntity": "PLoWmEuLJl2"}
    assert sent.headers["authorization"] == f"Bearer {token}"
    assert sent.headers[FACADE_PROVENANCE_HEADER] == "dhis2w-fhir-serve/9.9.9"


async def test_a_forwarding_run_still_refuses_a_register_read_that_presents_no_token(
    serving_project: FhirProject, published_issuer: respx.MockRouter
) -> None:
    """There is nobody to answer as, and answering as the facade is the read this posture prevents."""
    async with _forwarding_facade(serving_project, forward_bearer=True) as app:
        with pytest.raises(UnauthenticatedError) as refused:
            await register_reader(_register_request(app))

    assert refused.value.status_code == 401
    assert ISSUER in refused.value.challenge


async def test_a_forwarded_refusal_challenges_with_this_runs_own_posture(
    serving_project: FhirProject, published_issuer: respx.MockRouter, issuer: IssuerFixture
) -> None:
    """A 401 from DHIS2 is carried as it stands, and the challenge beside it is this server's own."""
    async with _forwarding_facade(serving_project, forward_bearer=True) as app:
        published_issuer.get(f"{INSTANCE_URL}{TRACKER_PATH}").mock(return_value=httpx.Response(401, json={}))
        reader = await register_reader(_register_request(app, f"Bearer {issuer.sign()}"))
        assert reader is not None

        with pytest.raises(UpstreamRefusalError) as refused:
            await reader.get_raw(TRACKER_PATH)

    assert refused.value.status_code == 401
    assert ISSUER in refused.value.response_headers()["WWW-Authenticate"]


async def test_the_pass_through_pool_is_opened_only_where_a_token_is_forwarded(
    serving_project: FhirProject, published_issuer: respx.MockRouter
) -> None:
    """A posture that forwards nothing opens no channel that could carry anybody's credential."""
    withheld = create_app(_jwt_settings(serving_project, jwt={"forward_bearer": False}))
    async with withheld.router.lifespan_context(withheld):
        assert withheld.state.caller_client is None

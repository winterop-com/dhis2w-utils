"""The `jwt` posture's machinery: one external OIDC issuer, its published keys, and what a token proves.

WHAT THIS POSTURE IS FOR. A ministry that already runs an identity provider has already answered
"who is this person" for every system it fronts, and `[serve] auth = "jwt"` is this facade taking
that answer instead of asking the question a second time. No authorization server is run here, no
client secret is held here, and no token is minted here: a caller arrives with a token their own IdP
gave them, and this module decides whether it is genuine, current, and meant for this server.

VALIDATION IS LOCAL AND OFFLINE-AFTER-THE-FIRST-FETCH. The issuer publishes its signing keys as a
JWKS, this process reads that document, and every token is verified against those keys in memory.
There is no introspection call, so a request costs no round trip to the IdP and the IdP is not in
the path of every read. The cost of that is the one property token introspection would have bought:
a token revoked before it expires stays valid here until it expires. That is the standard trade
every JWKS validator makes, and the answer to it is short token lifetimes at the issuer.

THE KEYS ARE FETCHED ONCE AND HELD. `Cache-Control: max-age` on the JWKS answer is honoured, with a
floor of `JWKS_MINIMUM_CACHE_SECONDS`: an issuer that sends `max-age=0` would otherwise make every
verification a round trip, which is the thing this design exists to avoid. There is no ceiling, and
there does not need to be one - a key rotation shows up as a token signed by a `kid` this process
does not hold, and an unknown `kid` forces one refetch on the spot. That refetch is itself floored
by `JWKS_REFETCH_FLOOR_SECONDS`, so a caller sending nonsense `kid`s cannot turn this facade into a
load generator pointed at somebody's identity provider.

ONLY ASYMMETRIC SIGNATURES ARE ACCEPTED. `JWT_ALGORITHMS` is the RSA and ECDSA family and nothing
else. A JWKS holds public keys, and accepting a symmetric algorithm beside them is the algorithm
confusion attack in one line: a caller signs `HS256` using the public modulus as the shared secret
and the verifier, asked to accept "whatever the header says", agrees. The header is not asked.

WHAT A TOKEN HAS TO CARRY. A signature this issuer's keys verify; `iss` equal to the configured
issuer; `exp` in the future; `nbf` in the past where it is stated; `aud` containing the configured
audience where one is configured; and the claim `[serve.jwt] username_claim` names. That last one is
the whole point of the exercise - it becomes the request identity, so a receipt captured under this
posture records a person rather than a deployment.

`CLOCK_LEEWAY_SECONDS` is what a token's time claims are read with. Two machines that have never
agreed on the second would otherwise refuse each other's perfectly good tokens for a minute either
side of every boundary, and a minute of leeway is the standard allowance for that.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from dhis2w_core.oauth2_preflight import DISCOVERY_PATH, OidcDiscovery
from dhis2w_fhir.config import ServeJwtConfig
from joserfc import jwt as jose_jwt
from joserfc.errors import BadSignatureError, InvalidKeyIdError, JoseError, MissingKeyError
from joserfc.jwk import KeySet
from joserfc.jwt import ClaimsOption
from pydantic import BaseModel, ConfigDict, Field

#: The signature algorithms one token may carry, which are the asymmetric ones and only those.
JWT_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")

#: How long a JWKS answer is held: what `Cache-Control` says, never below the floor, and this when
#: the answer says nothing at all.
JWKS_MINIMUM_CACHE_SECONDS = 300.0
JWKS_DEFAULT_CACHE_SECONDS = 3600.0

#: The shortest interval between two refetches an unknown `kid` forces, so a bad `kid` is not a lever.
JWKS_REFETCH_FLOOR_SECONDS = 60.0

#: How long this server waits for the issuer to answer either of its two documents.
ISSUER_TIMEOUT_SECONDS = 10.0

#: What a token's `exp` and `nbf` are read with, so two unsynchronised clocks still agree.
CLOCK_LEEWAY_SECONDS = 60


class OidcIssuerUnavailableError(RuntimeError):
    """The issuer this run was told to trust could not be read, so the posture cannot be honoured.

    A startup failure rather than a request failure. `dhis2w_fhir_serve.auth.open_jwt_verifier`
    turns it into the same `ServeAuthConfigurationError` the other posture refusals raise, so a
    deployer meets one line naming the key rather than a server that starts and 401s everybody.
    """


class TokenRefusedError(ValueError):
    """One presented token this issuer's keys, or this facade's rules, would not accept.

    Carries the sentence a caller is told and nothing else. `dhis2w_fhir_serve.auth` is what turns
    it into the 401 and the `WWW-Authenticate` challenge that goes with it - this module refuses
    tokens and never writes HTTP.
    """

    def __init__(self, diagnostics: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics


class VerifiedToken(BaseModel):
    """What one accepted token established: who is calling, and the claims that said so."""

    model_config = ConfigDict(frozen=True)

    username: str
    """The value of `[serve.jwt] username_claim`, which becomes the request identity."""

    subject: str | None = None
    """The token's `sub` - the issuer's own stable identifier for the caller, where it stated one."""

    expires_at: int | None = None
    """The token's `exp`, as it stood - what a deployment reads to know how long an answer stays true."""


class PublishedKeys(BaseModel):
    """One JWKS document as this process holds it, and until when it holds it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key_set: KeySet
    """The issuer's public keys, indexed by `kid` - what a signature is checked against."""

    fetched_at: float
    """A `time.monotonic` reading, so holding a document survives the machine's clock being set."""

    expires_at: float
    """When this document stops being reused, from `Cache-Control` and never below the floor."""


class JwtVerifier(BaseModel):
    """One issuer's published keys, held for the life of the process, and the check they answer.

    Built while the server starts, by `discover_issuer`, so a run whose issuer cannot be read is a
    line in a terminal rather than a 401 on every caller. It holds public keys and no secret of any
    kind, which is why it is safe to keep on the application where every request reaches it.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: ServeJwtConfig
    """The `[serve.jwt]` table this run resolved - the issuer, the audience, and the claim to read."""

    issuer: str
    """The issuer identifier every token's `iss` is compared against, as the issuer publishes it."""

    jwks_uri: str
    """Where the keys come from, as `/.well-known/openid-configuration` named it."""

    held: PublishedKeys | None = Field(default=None, repr=False)
    """The keys this process is currently verifying against, or None until the first fetch."""

    forced_at: float | None = None
    """When an unknown `kid` last sent this process back to the issuer, or None while none has."""

    async def verify(self, token: str) -> VerifiedToken:
        """Accept one token, or say in one sentence why it is refused.

        The order is the order a reader would check it in: the signature first, because an unsigned
        assertion's claims are not evidence of anything; then what the claims say; then the claim
        that names the caller. An unknown `kid` is the one case that goes back to the issuer -
        a rotation is the ordinary reason a signature arrives under a key this process does not
        hold, and refusing it without looking would make every rotation an outage.
        """
        decoded = await self._decoded(token)
        self._claims_hold(decoded.claims)
        return VerifiedToken(
            username=self._named_caller(decoded.claims),
            subject=_string_claim(decoded.claims, "sub"),
            expires_at=_integer_claim(decoded.claims, "exp"),
        )

    async def keys(self, *, force: bool = False) -> PublishedKeys:
        """The issuer's keys, fetched when this process holds none, holds stale ones, or is forced.

        `force` is what an unknown `kid` asks for, and it is floored against the last FORCED read
        rather than against the last read of any kind: the first unknown `kid` after a rotation has
        to be able to see the new keys immediately, and every one after it within
        `JWKS_REFETCH_FLOOR_SECONDS` gets what is held. So a rotation costs one request and a stream
        of tokens naming keys that never existed costs this issuer one request a minute.
        """
        now = time.monotonic()
        held = self.held
        if held is not None and not force and held.expires_at > now:
            return held
        if (
            held is not None
            and force
            and self.forced_at is not None
            and now - self.forced_at < JWKS_REFETCH_FLOOR_SECONDS
        ):
            return held
        if force:
            self.forced_at = now
        fetched = await fetch_published_keys(self.jwks_uri)
        self.held = fetched
        return fetched

    async def _decoded(self, token: str) -> jose_jwt.Token:
        """Check one token's signature against the issuer's keys, refetching once for an unknown `kid`."""
        held = await self.keys()
        try:
            return self._decoded_against(token, held)
        except InvalidKeyIdError:
            pass
        except MissingKeyError:
            pass
        refetched = await self.keys(force=True)
        try:
            return self._decoded_against(token, refetched)
        except (InvalidKeyIdError, MissingKeyError) as error:
            raise TokenRefusedError(
                "the token this request carried is signed with a key this server could not find among "
                f"the ones `{self.issuer}` publishes, even after reading them again"
            ) from error

    def _decoded_against(self, token: str, held: PublishedKeys) -> jose_jwt.Token:
        """One decode against one set of keys, with every refusal but an unknown `kid` answered here."""
        try:
            return jose_jwt.decode(token, held.key_set, algorithms=list(JWT_ALGORITHMS))
        except (InvalidKeyIdError, MissingKeyError):
            raise
        except BadSignatureError as error:
            raise TokenRefusedError(
                "the token this request carried is not signed by the key it names, so this server "
                "cannot tell who issued it"
            ) from error
        except (JoseError, ValueError) as error:
            raise TokenRefusedError(
                "the value in `Authorization` is not a JSON Web Token this server can read "
                f"({error}); this server takes a token `{self.issuer}` minted"
            ) from error

    def _claims_hold(self, claims: dict[str, Any]) -> None:
        """Check what one token says about itself: who issued it, when it is good for, and for whom.

        `aud` is an option only where an audience is configured, and that is the difference between
        "this token is for somebody else" and "this server takes whatever this issuer signed". A
        registry that always required it would refuse every issuer that mints audience-less tokens.
        """
        required: dict[str, ClaimsOption] = {
            "iss": {"essential": True, "value": self.issuer},
            "exp": {"essential": True},
        }
        if self.config.audience is not None:
            required["aud"] = {"essential": True, "value": self.config.audience}
        registry = jose_jwt.JWTClaimsRegistry(now=int(time.time()), leeway=CLOCK_LEEWAY_SECONDS, **required)
        try:
            registry.validate(claims)
        except JoseError as error:
            raise TokenRefusedError(self._claim_refusal(claims, error)) from error

    def _claim_refusal(self, claims: dict[str, Any], error: JoseError) -> str:
        """What a caller is told about a token whose signature held and whose claims did not."""
        stated_issuer = _string_claim(claims, "iss")
        if stated_issuer is not None and stated_issuer.rstrip("/") != self.issuer:
            return (
                f"the token this request carried was issued by `{stated_issuer}`, and this server takes "
                f"tokens from `{self.issuer}`"
            )
        if self.config.audience is not None and not _audience_holds(claims, self.config.audience):
            return (
                f"the token this request carried is not for this server: it names no audience `{self.config.audience}`"
            )
        return f"the token this request carried is not currently valid ({error})"

    def _named_caller(self, claims: dict[str, Any]) -> str:
        """The claim `[serve.jwt] username_claim` names, refusing a token that names nobody."""
        named = _string_claim(claims, self.config.username_claim)
        if named is None or named.strip() == "":
            raise TokenRefusedError(
                f"the token this request carried carries no `{self.config.username_claim}` claim, and this "
                "server records who captured every response; state the claim your issuer puts the "
                "username in as `[serve.jwt] username_claim`"
            )
        return named.strip()


async def discover_issuer(config: ServeJwtConfig) -> JwtVerifier:
    """Read one issuer's discovery document and its keys, or refuse the run that asked for it.

    Both reads happen while the server starts, and both have to succeed. An issuer that cannot be
    reached is a posture this process cannot honour, and a facade that started anyway would refuse
    every caller for a reason none of them could act on.
    """
    if config.issuer is None:
        raise OidcIssuerUnavailableError("no issuer is configured")
    discovery = await fetch_issuer_discovery(config.issuer)
    verifier = JwtVerifier(config=config, issuer=discovery.issuer.rstrip("/"), jwks_uri=discovery.jwks_uri)
    verifier.held = await fetch_published_keys(discovery.jwks_uri)
    return verifier


async def fetch_issuer_discovery(issuer: str) -> OidcDiscovery:
    """Read `{issuer}/.well-known/openid-configuration`, which is where the keys are named.

    The issuer the document states is taken over the one that was configured, because that is the
    value its tokens carry as `iss` - an issuer reached at one URL and identifying itself as another
    is a deployment behind a proxy, and comparing against what it says about itself is what makes
    that work. It has to identify itself as something, and a document that names no `jwks_uri` names
    no keys, so both are required fields on the model this parses into.
    """
    url = issuer.rstrip("/") + DISCOVERY_PATH
    try:
        async with httpx.AsyncClient(timeout=ISSUER_TIMEOUT_SECONDS, follow_redirects=True) as http:
            answer = await http.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        raise OidcIssuerUnavailableError(f"`{url}` could not be read ({error})") from error
    if answer.status_code >= 400:
        raise OidcIssuerUnavailableError(f"`{url}` answered {answer.status_code}")
    try:
        return OidcDiscovery.model_validate(answer.json())
    except ValueError as error:
        raise OidcIssuerUnavailableError(
            f"`{url}` did not answer with an OpenID Connect configuration naming an issuer and a `jwks_uri` ({error})"
        ) from error


async def fetch_published_keys(jwks_uri: str) -> PublishedKeys:
    """Read one JWKS document and hold it for as long as its own `Cache-Control` asks, within the floor."""
    try:
        async with httpx.AsyncClient(timeout=ISSUER_TIMEOUT_SECONDS, follow_redirects=True) as http:
            answer = await http.get(jwks_uri, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        raise OidcIssuerUnavailableError(f"`{jwks_uri}` could not be read ({error})") from error
    if answer.status_code >= 400:
        raise OidcIssuerUnavailableError(f"`{jwks_uri}` answered {answer.status_code}")
    try:
        key_set = KeySet.import_key_set(answer.json())
    except (ValueError, KeyError, JoseError) as error:
        raise OidcIssuerUnavailableError(f"`{jwks_uri}` did not answer with a JSON Web Key Set ({error})") from error
    now = time.monotonic()
    return PublishedKeys(key_set=key_set, fetched_at=now, expires_at=now + cache_seconds(answer.headers))


def cache_seconds(headers: httpx.Headers) -> float:
    """How long one JWKS answer is held: what it asked for, never below `JWKS_MINIMUM_CACHE_SECONDS`.

    The floor is the whole of the policy. An issuer that sends `max-age=0` - which several do, out
    of caution about a document that is not secret - would otherwise make every verified request a
    round trip to that issuer, which is slower than the introspection call this design exists to
    avoid. There is no ceiling, because a rotation is caught by the unknown-`kid` refetch rather
    than by an expiry nobody set.
    """
    stated = _max_age(headers.get("cache-control", ""))
    if stated is None:
        return JWKS_DEFAULT_CACHE_SECONDS
    return max(stated, JWKS_MINIMUM_CACHE_SECONDS)


def _max_age(cache_control: str) -> float | None:
    """The `max-age` one `Cache-Control` value states, or None where it states none this can read."""
    for directive in cache_control.split(","):
        name, _, value = directive.strip().partition("=")
        if name.strip().lower() != "max-age":
            continue
        try:
            return float(int(value.strip()))
        except ValueError:
            return None
    return None


def _audience_holds(claims: dict[str, Any], audience: str) -> bool:
    """Whether one token's `aud` - a string or a list of them, per RFC 7519 - names this server."""
    stated = claims.get("aud")
    if isinstance(stated, str):
        return stated == audience
    if isinstance(stated, list):
        return audience in stated
    return False


def _string_claim(claims: dict[str, Any], name: str) -> str | None:
    """One claim read as a string, or None where the token stated none or stated something else."""
    value = claims.get(name)
    return value if isinstance(value, str) else None


def _integer_claim(claims: dict[str, Any], name: str) -> int | None:
    """One claim read as an integer, which is what RFC 7519's time claims are."""
    value = claims.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None

"""Who the facade serves: the four postures, the check they run, and the identity a capture is stamped with.

FOUR POSTURES, ONE DEPENDENCY. `[serve] auth` picks between them and `[serve] auth_scope` picks how
much of the surface the pick covers; the check itself is one FastAPI dependency, mounted on the
routers `dhis2w_fhir_serve.routes.serve_routers` names as guarded. Nothing in a route handler knows
which posture is running - a handler that wants to know who is calling reads `request_identity`,
which answers None wherever no identity was established.

`none` serves every caller. It is the default and it is honest about being one: `/metadata` declares
it in `rest.security` like any other posture, so a client never has to infer an absence, and
`ServeSettings.resolve` refuses to bind an interface other than loopback while the project's
fhir.toml has not written the key down. An absent key on loopback is the zero-friction demo; an
absent key on `0.0.0.0` is a deployment nobody stated, and it is refused before the socket opens.

`token` compares an `Authorization: Bearer <token>` against the values of `D2W_FHIR_SERVE_TOKENS`,
comma-separated. THE TOKENS COME FROM THE ENVIRONMENT AND NOWHERE ELSE - never from fhir.toml, which
is a file projects commit. Comparison is `hmac.compare_digest`, so the time a refusal takes says
nothing about how much of a token was right. Rotation is replacing the variable and restarting the
process: the values are read once, at first use, and a running server holds what it started with.

`dhis2` is the flagship: the caller's DHIS2 credentials are their facade credentials. Whatever the
caller put in `Authorization` - `Basic` for a username and password, `ApiToken` for a DHIS2 personal
access token, which is the header shape `dhis2w_client.v42.auth.pat` sends - is replayed against
`GET /api/me` on the same instance this run reads, in a request of its own that carries the caller's
header and NEVER the runtime's client. The facade's own credentials are not a fallback and are not a
second attempt: a caller who cannot read `/api/me` cannot use this facade. The username DHIS2 answers
with becomes the request identity, and the capture route stamps it onto the receipt.

THE VALIDATION IS CACHED, BRIEFLY, BY A HASH OF THE HEADER. Without a cache every request to a gated
route would cost a round trip to DHIS2, which would make the facade slower than the instance it
fronts. The key is `sha256` of the header value rather than the header itself, so the process holds
no plaintext credential in a dictionary, and entries expire `CREDENTIAL_CACHE_SECONDS` after the
answer that filled them - long enough to make a page of requests one round trip, short enough that a
disabled account stops working in the minute rather than at the next restart.

`jwt` takes a token an identity provider this facade does not run minted. `[serve.jwt] issuer` names
that provider; the facade reads its `/.well-known/openid-configuration` and its JWKS while it starts,
and every request is then verified in memory against those public keys - signature, `iss`, `exp`,
`nbf`, and `aud` where one is configured. `dhis2w_fhir_serve.oidc` is the whole of that machinery and
argues it; what matters here is the outcome: the claim `[serve.jwt] username_claim` names becomes the
request identity, exactly as the DHIS2 username does under `dhis2`, so a receipt captured under this
posture records a person and the pass-through machinery reads the same field it always read.

WHAT `jwt` CANNOT DO ON ITS OWN IS READ THE REGISTER AS THE CALLER. A token this facade accepts is a
token DHIS2 accepts only when the instance was configured to trust the same issuer, through DHIS2's
own `oidc.jwt.token.authentication.enabled`. So `[serve.jwt] forward_bearer` is false by default, and
under it the live register is refused with a 501 that names what would make it answerable. The
refusal is deliberate and the alternative is the trap it exists to close: reading the register as the
facade's own profile would answer every caller with that profile's rights, which under an
administrator profile is DHIS2's whole ownership and access-level model skipped with no audit entry.
`forward_bearer = true` states that the instance does trust the issuer, and the caller's `Authorization`
is then forwarded over exactly the path the `dhis2` posture forwards over - the same opaque header on
the same credential-free pool.

`oauth2` is the posture that is not here. DHIS2 2.43.1's authorization server 500s for any client the
API creates (BUGS.md 96), so there is nothing to build against; `dhis2w_fhir.config.ServeAuth` says
what the name is reserved for and `docs/fhir/301-serving.md` says the same to a deployer. A deployment
that wants bearer tokens from an authorization server today runs `jwt` against the one it already has.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import time
from typing import TYPE_CHECKING

import httpx
from dhis2w_fhir.config import ServeAuth, ServeJwtConfig
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from dhis2w_fhir_serve.errors import ServeError
from dhis2w_fhir_serve.oidc import JwtVerifier, OidcIssuerUnavailableError, TokenRefusedError, discover_issuer
from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir_serve.settings import ServeSettings

#: The request header every posture reads, and the two schemes the DHIS2 posture replays.
AUTHORIZATION_HEADER = "authorization"
BASIC_SCHEME = "Basic"
DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME = "ApiToken"

#: The scheme the token posture takes, and the environment variable its values come from.
BEARER_SCHEME = "Bearer"
SERVE_TOKENS_VARIABLE = "D2W_FHIR_SERVE_TOKENS"

#: What a `WWW-Authenticate` names this server as, in either challenge.
AUTHENTICATION_REALM = "d2w fhir serve"

#: The DHIS2 read one caller's credentials are validated by, and how long an answer to it is reused.
DHIS2_IDENTITY_PATH = "/api/me"
CREDENTIAL_CACHE_SECONDS = 60.0

#: How long the facade waits for the instance to answer `/api/me` before refusing the request.
DHIS2_IDENTITY_TIMEOUT_SECONDS = 10.0

#: Where the auth state, the JWT verifier, and the established identity are held.
AUTH_STATE_ATTRIBUTE = "auth"
JWT_VERIFIER_ATTRIBUTE = "jwt_verifier"
REQUEST_IDENTITY_ATTRIBUTE = "identity"


class UnauthenticatedError(ServeError):
    """The request carried no credential this posture accepts, or one the posture refused.

    401 rather than 403 in every case, the refused credential included: this facade holds no
    permissions of its own, so there is nothing it could grant one caller and withhold from another.
    Either the credential establishes who is calling or it does not, and both answers are the same
    one - present a credential this server accepts.
    """

    status_code = 401
    issue_code = "login"

    def __init__(self, diagnostics: str, challenge: str) -> None:
        super().__init__(diagnostics)
        self.challenge = challenge

    def response_headers(self) -> dict[str, str]:
        """The `WWW-Authenticate` challenge RFC 9110 requires of every 401."""
        return {"WWW-Authenticate": self.challenge}


class ServeAuthConfigurationError(ValueError):
    """A posture this run cannot honour, refused while the settings resolve rather than at a request.

    A `ValueError` because that is what `ServeSettings.resolve` already raises for a stated value it
    cannot mean, and `d2w fhir serve` renders it as one line against the dial it came from.
    """


class RequestIdentity(BaseModel):
    """Who one request established itself as, under the posture that established it."""

    model_config = ConfigDict(frozen=True)

    posture: ServeAuth
    username: str | None = None
    """Who the credential named: the DHIS2 username under `dhis2`, the claim `[serve.jwt]
    username_claim` names under `jwt`. None under `token`, which names no person."""


class ValidatedCredential(BaseModel):
    """One `/api/me` answer, held until it expires - the username DHIS2 gave, and when it stops counting."""

    model_config = ConfigDict(frozen=True)

    username: str
    expires_at: float
    """A `time.monotonic` reading, so the entry survives the machine's clock being set."""


class CredentialCache(BaseModel):
    """The DHIS2 answers this process is still reusing, keyed by a hash of the header that earned them.

    Mutable on purpose - it is state a running process fills - and it holds no plaintext credential:
    the key is `sha256` of the `Authorization` value, so a memory dump of this dictionary names
    nobody's password.
    """

    model_config = ConfigDict(arbitrary_types_allowed=False)

    entries: dict[str, ValidatedCredential] = Field(default_factory=dict)

    def valid(self, key: str, *, now: float) -> ValidatedCredential | None:
        """The unexpired answer under one key, dropping it when it has expired."""
        held = self.entries.get(key)
        if held is None:
            return None
        if held.expires_at <= now:
            del self.entries[key]
            return None
        return held

    def remember(self, key: str, username: str, *, now: float) -> ValidatedCredential:
        """Hold one answer for `CREDENTIAL_CACHE_SECONDS` from the moment it was given."""
        entry = ValidatedCredential(username=username, expires_at=now + CREDENTIAL_CACHE_SECONDS)
        self.entries[key] = entry
        return entry


class AuthState(BaseModel):
    """What the check needs beyond the settings: the tokens this process started with, and its cache.

    The tokens are read once, at first use, because rotation is replacing the variable and restarting
    - a process that re-read the environment per request would honour a rotation nobody restarted for
    and hide the restart the deployment actually needs.

    THEY ARE NOT ON `ServeSettings`, and that is the whole reason this model exists. The settings are
    handed to the app and read back out by `/uiconfig`, so a secret on them would be a secret one
    HTTP response away from a browser. What crosses to the browser is the posture's name.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tokens: tuple[str, ...] = ()
    cache: CredentialCache = Field(default_factory=CredentialCache)

    verifier: JwtVerifier | None = None
    """The `jwt` posture's issuer and its published keys, opened while the server started.

    It holds public keys and no secret, which is what makes it the exception to the paragraph above:
    there is nothing on it a `/uiconfig` response could leak. It is here rather than fetched per
    request because reading an identity provider's JWKS on every call would put that provider in the
    path of every read - see `dhis2w_fhir_serve.oidc`.
    """


def read_serve_tokens(environment: dict[str, str] | None = None) -> tuple[str, ...]:
    """The static bearer tokens `D2W_FHIR_SERVE_TOKENS` names, comma-separated, blanks dropped."""
    raw = (environment if environment is not None else dict(os.environ)).get(SERVE_TOKENS_VARIABLE, "")
    return tuple(value for value in (part.strip() for part in raw.split(",")) if value)


def matches_a_serve_token(presented: str, tokens: tuple[str, ...]) -> bool:
    """Whether one presented token is one of this run's, compared in constant time.

    Every configured token is compared, and the loop does not stop at the first match: returning as
    soon as one hits would make the time a request takes a function of which token was presented,
    which is the leak `hmac.compare_digest` exists to close on the bytes.
    """
    matched = False
    for token in tokens:
        if hmac.compare_digest(presented, token):
            matched = True
    return matched


def current_monotonic() -> float:
    """The reading the cache measures its own entries against - monotonic, so a clock change is not an expiry."""
    return time.monotonic()


def credential_key(header_value: str) -> str:
    """The cache key for one `Authorization` value - a hash, so no plaintext credential is held."""
    return hashlib.sha256(header_value.encode("utf-8")).hexdigest()


def challenge_for(posture: ServeAuth, issuer: str | None = None) -> str:
    """The `WWW-Authenticate` value one posture refuses with.

    `issuer` is stated under `jwt` and ignored everywhere else. RFC 6750 has no parameter for naming
    the authorization server a bearer token should come from, so it rides in `error_description`,
    which is the one place a client is allowed to read prose from - and it is the fact a caller
    holding no token most needs.
    """
    if posture is ServeAuth.DHIS2:
        return f'{BASIC_SCHEME} realm="{AUTHENTICATION_REALM}", charset="UTF-8"'
    if posture is ServeAuth.JWT and issuer is not None:
        return f'{BEARER_SCHEME} realm="{AUTHENTICATION_REALM}", error_description="a token from {issuer}"'
    return f'{BEARER_SCHEME} realm="{AUTHENTICATION_REALM}"'


def request_identity(request: Request) -> RequestIdentity | None:
    """Who this request established itself as, or None where no posture established anybody.

    What the capture route reads to stamp a receipt. None is every request under `none`, every
    request under `token` - a static token names no person - and every request to a route this
    scope leaves open.
    """
    identity: RequestIdentity | None = getattr(request.state, REQUEST_IDENTITY_ATTRIBUTE, None)
    return identity


async def require_authenticated(request: Request) -> None:
    """Establish who is calling, or refuse the request - the dependency the guarded routers carry.

    An embedding application that authenticates its callers some other way mounts its own dependency
    in this one's place: `serve_routers` states which routers it belongs on, and
    `dhis2w_fhir_serve.routes.register_routes` is the only thing that assumes this function. Such an
    application writes its own `RequestIdentity` onto `request.state` under
    `REQUEST_IDENTITY_ATTRIBUTE` if it wants the capture receipts attributed.
    """
    settings = serve_context(request).settings
    if settings.auth is ServeAuth.NONE:
        return
    presented = request.headers.get(AUTHORIZATION_HEADER, "").strip()
    if presented == "":
        raise UnauthenticatedError(
            f"this server takes no request without an `Authorization` header; {_expected(settings)}",
            challenge_for(settings.auth, settings.jwt.issuer),
        )
    state = auth_state(request)
    if settings.auth is ServeAuth.TOKEN:
        _establish_token_identity(request, presented, state)
        return
    if settings.auth is ServeAuth.JWT:
        await _establish_jwt_identity(request, presented, state, settings)
        return
    await _establish_dhis2_identity(request, presented, state, settings)


def auth_state(request: Request) -> AuthState:
    """This app's auth state, built the first time a guarded route is reached.

    Built here rather than in the lifespan for the reason the capture state is: a facade nobody ever
    sends a guarded request to never reads the environment and never allocates a cache. It is
    application state, not request state, so the cache is shared by every request of the process.
    """
    held: AuthState | None = getattr(request.app.state, AUTH_STATE_ATTRIBUTE, None)
    if held is not None:
        return held
    verifier: JwtVerifier | None = getattr(request.app.state, JWT_VERIFIER_ATTRIBUTE, None)
    state = AuthState(tokens=read_serve_tokens(), verifier=verifier)
    setattr(request.app.state, AUTH_STATE_ATTRIBUTE, state)
    return state


async def open_jwt_verifier(config: ServeJwtConfig) -> JwtVerifier:
    """Read the issuer this run trusts, while the server starts, or refuse to serve at all.

    The refusal is a `ServeAuthConfigurationError` so it lands beside the other posture refusals - a
    deployer meets one line naming the key that has to change, whether the problem was an issuer
    nobody wrote down or one nobody could reach.
    """
    try:
        return await discover_issuer(config)
    except OidcIssuerUnavailableError as error:
        raise ServeAuthConfigurationError(
            f'`auth = "jwt"` verifies every caller\'s token against the keys `{config.issuer}` publishes, '
            f"and this server could not read them: {error}. Check `[serve.jwt] issuer` names the issuer "
            "identifier its own tokens carry as `iss`, and that this machine can reach it."
        ) from error


async def validate_with_dhis2(base_url: str, header_value: str) -> str:
    """Replay one caller's `Authorization` against `GET /api/me`, answering with the username DHIS2 gave.

    A REQUEST OF ITS OWN, CARRYING THE CALLER'S HEADER AND NOTHING ELSE. The client the live store was
    built through holds the facade's own credentials, and reusing it here would validate every caller
    as whoever the server logs in as - which would be the facade handing out its own account. So this
    opens a plain `httpx` client, sends exactly what arrived, and closes it.

    Any answer other than a 2xx is a refusal, and so is one the instance never gave: an unreachable
    DHIS2 means this facade cannot say who is calling, and serving the request anyway would be
    answering the question by giving up on it.
    """
    challenge = challenge_for(ServeAuth.DHIS2)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=DHIS2_IDENTITY_TIMEOUT_SECONDS) as http:
            answer = await http.get(
                DHIS2_IDENTITY_PATH,
                headers={"Authorization": header_value, "Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise UnauthenticatedError(
            f"this server could not reach the DHIS2 instance to check the credentials it was given ({error})",
            challenge,
        ) from error
    if answer.status_code >= 400:
        raise UnauthenticatedError(
            f"the DHIS2 instance behind this server refused the credentials it was given "
            f"(`GET {DHIS2_IDENTITY_PATH}` answered {answer.status_code})",
            challenge,
        )
    return _username_from(answer, challenge)


def _username_from(answer: httpx.Response, challenge: str) -> str:
    """The username on one `/api/me` answer, refusing an answer that names nobody."""
    from dhis2w_client import Me

    try:
        identity = Me.model_validate(answer.json())
    except ValueError as error:
        raise UnauthenticatedError(
            f"the DHIS2 instance behind this server did not answer `GET {DHIS2_IDENTITY_PATH}` with a user",
            challenge,
        ) from error
    if not identity.username:
        raise UnauthenticatedError(
            f"the DHIS2 instance behind this server answered `GET {DHIS2_IDENTITY_PATH}` with no username",
            challenge,
        )
    return identity.username


def _establish_token_identity(request: Request, presented: str, state: AuthState) -> None:
    """Accept one static bearer token, or refuse it - the whole of the `token` posture."""
    challenge = challenge_for(ServeAuth.TOKEN)
    scheme, _, value = presented.partition(" ")
    if scheme.lower() != BEARER_SCHEME.lower() or value.strip() == "":
        raise UnauthenticatedError(
            f"this server takes a `{BEARER_SCHEME}` token in `Authorization`, and this request carried `{scheme}`",
            challenge,
        )
    if not matches_a_serve_token(value.strip(), state.tokens):
        raise UnauthenticatedError("the token this request carried is not one this server accepts", challenge)
    setattr(request.state, REQUEST_IDENTITY_ATTRIBUTE, RequestIdentity(posture=ServeAuth.TOKEN))


async def _establish_jwt_identity(request: Request, presented: str, state: AuthState, settings: ServeSettings) -> None:
    """Verify one token against the configured issuer's keys, and record the claim that names the caller.

    Nothing is cached here and nothing needs to be. A JWT carries its own answer: the signature is
    checked in memory against keys this process already holds, so the check costs no round trip and
    there is no `/api/me` answer to reuse. The identity cache the `dhis2` posture keeps exists
    because that posture asks somebody else the question; this one is handed the answer.
    """
    challenge = challenge_for(ServeAuth.JWT, settings.jwt.issuer)
    scheme, _, value = presented.partition(" ")
    if scheme.lower() != BEARER_SCHEME.lower() or value.strip() == "":
        raise UnauthenticatedError(
            f"this server takes a `{BEARER_SCHEME}` token in `Authorization`, and this request carried `{scheme}`",
            challenge,
        )
    if state.verifier is None:
        # Unreachable through a server this package started: `open_serve_runtime` opens the verifier
        # for this posture or refuses to serve. Stated anyway, because an embedding application
        # mounting these routers over a runtime of its own could reach it.
        raise UnauthenticatedError(
            "this server takes a token from an OpenID Connect issuer and holds no keys to check one "
            "against: the runtime was attached without the verifier `open_serve_runtime` opens for the "
            "`jwt` posture",
            challenge,
        )
    try:
        verified = await state.verifier.verify(value.strip())
    except TokenRefusedError as error:
        raise UnauthenticatedError(error.diagnostics, challenge) from error
    setattr(
        request.state, REQUEST_IDENTITY_ATTRIBUTE, RequestIdentity(posture=ServeAuth.JWT, username=verified.username)
    )


async def _establish_dhis2_identity(
    request: Request, presented: str, state: AuthState, settings: ServeSettings
) -> None:
    """Validate one caller against DHIS2, through the cache, and record the username as the identity."""
    challenge = challenge_for(ServeAuth.DHIS2)
    scheme = presented.partition(" ")[0].lower()
    if scheme not in {BASIC_SCHEME.lower(), DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME.lower()}:
        raise UnauthenticatedError(
            f"this server checks credentials against DHIS2, which takes `{BASIC_SCHEME}` or "
            f"`{DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME}` in `Authorization`, and this request carried "
            f"`{presented.partition(' ')[0]}`",
            challenge,
        )
    if settings.dhis2_base_url is None:
        # Unreachable through `ServeSettings.resolve`, which refuses this posture on a run with no
        # instance behind it. Stated here anyway: the alternative is a `None` base url reaching httpx.
        raise UnauthenticatedError("this server has no DHIS2 instance to check credentials against", challenge)
    key = credential_key(presented)
    now = current_monotonic()
    held = state.cache.valid(key, now=now)
    if held is None:
        held = state.cache.remember(key, await validate_with_dhis2(settings.dhis2_base_url, presented), now=now)
    setattr(request.state, REQUEST_IDENTITY_ATTRIBUTE, RequestIdentity(posture=ServeAuth.DHIS2, username=held.username))


def _expected(settings: ServeSettings) -> str:
    """What one posture says it wants, on the refusal a request with no credential at all gets."""
    if settings.auth is ServeAuth.DHIS2:
        return (
            "send the DHIS2 username and password you would sign in to the instance with, as HTTP "
            f"{BASIC_SCHEME}, or a DHIS2 personal access token as `{DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME}`"
        )
    if settings.auth is ServeAuth.JWT:
        return (
            f"send a token from `{settings.jwt.issuer}` as `{BEARER_SCHEME} <token>`; obtaining one is "
            "that issuer's business and not this server's"
        )
    return f"send one of this deployment's tokens as `{BEARER_SCHEME} <token>`"


def preflight_auth(
    *,
    posture: ServeAuth,
    host: str,
    live: bool,
    stated: bool,
    jwt: ServeJwtConfig | None = None,
    environment: dict[str, str] | None = None,
) -> None:
    """Refuse, before anything binds, every posture this run could not actually honour.

    Five refusals, each about a run rather than about a request, which is why they are here and not
    in the dependency. A server that starts and then refuses every caller - or worse, serves every
    caller from an interface the deployment thought was closed - is a failure nobody reads until it
    matters.

    Two of them are the `jwt` posture's: an issuer nobody named, and `forward_bearer` asked for on a
    run with no instance to forward to. The third thing that posture needs - an issuer this machine
    can actually reach - is not checked here, because reading it is a round trip and this function is
    a reader of values. `dhis2w_fhir_serve.auth.open_jwt_verifier` does it while the server starts
    and refuses with the same error type.
    """
    if not stated and not _is_loopback(host):
        raise ServeAuthConfigurationError(
            f"`{host}` is not a loopback interface, and this project's fhir.toml states no `[serve] auth`. "
            "Write the posture down before serving the facade where other hosts can reach it - add one "
            'line under `[serve]` in fhir.toml: `auth = "none"` to serve every caller, `auth = "token"` '
            f'to take a static bearer token out of `{SERVE_TOKENS_VARIABLE}`, `auth = "dhis2"` to have '
            "every caller present the DHIS2 credentials this facade checks against the instance, or "
            '`auth = "jwt"` to take a token from an OpenID Connect issuer named in `[serve.jwt] issuer`. '
            "`--auth` states the same thing for one run."
        )
    if posture is ServeAuth.TOKEN and not read_serve_tokens(environment):
        raise ServeAuthConfigurationError(
            f'`auth = "token"` takes its tokens from the environment variable `{SERVE_TOKENS_VARIABLE}`, '
            "which is unset or empty. Set it to the tokens this deployment accepts, comma-separated, and "
            "serve again. The tokens are secrets and do not belong in fhir.toml, which is a file projects "
            "commit; rotating them is replacing the variable and restarting this process."
        )
    if posture is ServeAuth.DHIS2 and not live:
        raise ServeAuthConfigurationError(
            '`auth = "dhis2"` checks every caller\'s credentials against the DHIS2 instance this run reads, '
            "and this run reads a compiled implementation guide off disk instead - there is no instance to "
            'check anybody against. Serve with `--live`, or state `auth = "token"` or `auth = "none"`.'
        )
    if posture is ServeAuth.JWT:
        _preflight_jwt(jwt if jwt is not None else ServeJwtConfig(), live=live)


def _preflight_jwt(jwt: ServeJwtConfig, *, live: bool) -> None:
    """The two things `auth = "jwt"` needs stated before a socket opens: an issuer, and a place to forward to."""
    if jwt.issuer is None:
        raise ServeAuthConfigurationError(
            '`auth = "jwt"` verifies every caller\'s token against the keys one OpenID Connect issuer '
            "publishes, and this project's fhir.toml names no `[serve.jwt] issuer`. Add the table and the "
            'key - `[serve.jwt]` then `issuer = "https://idp.example.org/realms/health"` - naming the '
            "issuer identifier its own tokens carry as `iss`. This server appends "
            "`/.well-known/openid-configuration` to it and takes the keys from there."
        )
    if jwt.forward_bearer and not live:
        raise ServeAuthConfigurationError(
            "`[serve.jwt] forward_bearer = true` sends each caller's own token on to the DHIS2 instance "
            "this run reads, and this run reads a compiled implementation guide off disk instead - there "
            "is no instance to send anything to. Serve with `--live`, or set `forward_bearer = false`."
        )


def _is_loopback(host: str) -> bool:
    """Whether an address the process would bind only answers this machine.

    A name rather than an address is not loopback here, `localhost` excepted. Resolving a name would
    make the refusal depend on the machine's resolver, and a name that resolves to a loopback address
    today is a deployment decision somebody should still have written down.
    """
    stripped = host.strip().strip("[]")
    if stripped.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(stripped).is_loopback
    except ValueError:
        return False

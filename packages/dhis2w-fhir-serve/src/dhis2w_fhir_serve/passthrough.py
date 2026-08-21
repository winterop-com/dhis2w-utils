"""Reading DHIS2 as the caller: the header a register read forwards, and the reads that forward it.

THE POINT OF THE `dhis2` POSTURE IS NOT THE 401. Checking a caller against `GET /api/me` says who is
asking; it says nothing about what they may see. A facade that authenticates every caller and then
reads the instance as its own configured profile answers every one of them with that profile's
rights - so a deployment whose facade profile is an administrator hands each caller the whole
register, and DHIS2 skips its ownership and access-level model for a superuser without writing the
break-the-glass audit entry that would have recorded it.

So under `dhis2`, on a live run, a register read carries THE CALLER'S OWN `Authorization` HEADER to
the instance, verbatim. DHIS2 then enforces its five gates - authority, sharing, the data-element
bits, the three organisation-unit scopes, and ownership with access levels - against the person who
actually asked, which is the only place those gates can be enforced correctly. This facade computes
no permissions of its own and reimplements none of DHIS2's.

THE HEADER IS OPAQUE. It is read out of the request, put on the outgoing request, and never parsed,
never logged, and never held anywhere a later request can reach. `Basic` and `ApiToken` are what
`dhis2w_fhir_serve.auth` accepts, and this module does not care which arrived - what DHIS2 accepts is
DHIS2's business, and a facade that inspected the credential would be a facade that could get the
inspection wrong.

WHICH READS. Exactly the register reads a caller asks for: the tracked entity read, the identifier
search, the listing and its counts, the enrollment listing, and the entity `/evaluate` names as its
context. `dhis2w_fhir_serve.register.wire` takes a `RegisterReader` rather than a `Dhis2Client`
precisely so that one channel can be swapped per request.

WHICH READS ARE NOT. The startup store build, `/uiconfig`'s instance address, and `d2w fhir forward`'s
drain read and write as the facade's own profile, and that is correct: none of them acts on behalf of
a request. The store is one snapshot of the published guide, shared by every caller and holding no
tracked entity data; the drain is the deployment's own act under the forwarding profile. Those are
the paths `docs/fhir/301-serving.md` still asks for a least-privilege DHIS2 user for.

NOTHING ON THIS PATH IS CACHED. One caller's page is never another caller's page, so there is nothing
to share and the reader keeps nothing between requests. The one cache the `dhis2` posture holds is
`dhis2w_fhir_serve.auth`'s, it is keyed by a hash of the header, and what it holds is a username -
an identity, never a resource.

THE CONNECTION IS POOLED, THE CREDENTIAL IS NOT. Opening a TCP connection and a TLS session per
register read would make the facade slower than the instance it fronts, so one `httpx.AsyncClient`
is held open for the life of the process, pointed at the instance, WITH NO AUTHENTICATION OF ITS OWN.
`CallerCredentialReader` is the per-request pairing of that pool with one caller's header, and the
pool has no credential to fall back to if a request ever arrived without one.

THE FACADE NAMES ITSELF ON THE WAY THROUGH. Every pass-through read carries `X-DHIS2W-Facade`, this
software and its version, as a default header on the pool. It is provenance for whoever reads the
DHIS2 access log - "this arrived through the FHIR facade" - and it is deliberately not the username:
the caller's own header already carries the identity, and a second copy of it in a header nobody
authenticates would be an assertion this server has no business making.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from dhis2w_client.errors import Dhis2ApiError, Dhis2ClientError
from dhis2w_fhir.config import ServeAuth
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from dhis2w_fhir_serve.auth import (
    AUTHORIZATION_HEADER,
    UnauthenticatedError,
    challenge_for,
    request_identity,
    require_authenticated,
)
from dhis2w_fhir_serve.errors import IssueCode, ServeError
from dhis2w_fhir_serve.routes.context import caller_client, live_client, serve_context

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

#: The header every pass-through read carries, naming the software the read arrived through.
FACADE_PROVENANCE_HEADER = "X-DHIS2W-Facade"

#: What a pass-through read asks the instance for, and how long it waits to be answered.
PASS_THROUGH_ACCEPT = "application/json"
PASS_THROUGH_TIMEOUT_SECONDS = 30.0

#: The two DHIS2 verdicts a caller is told verbatim rather than as a facade failure. Every other
#: refusal is this server failing to read the instance, which is what a 502 says. DHIS2 hides what a
#: caller may not see rather than refusing it - an unshared tracked entity is a 404 - so 403 is rare
#: and 401 means the credential stopped working inside the identity cache's window.
PASSED_THROUGH_REFUSALS: dict[int, IssueCode] = {401: "login", 403: "forbidden"}


class UpstreamRefusalError(ServeError):
    """DHIS2 refused the caller's own credentials on a pass-through read, and its verdict is answered as it stands.

    Not an `UpstreamError`: a 502 would say this server could not reach the instance, when the
    instance answered clearly and the answer was about the caller. Inventing a status DHIS2 never
    sent would be worse still, so the status is carried rather than chosen.
    """

    def __init__(self, status_code: int, issue_code: IssueCode, challenge: str | None = None) -> None:
        super().__init__(
            f"the DHIS2 instance behind this server refused this read under the credentials this request "
            f"carried (it answered {status_code})"
        )
        self.status_code = status_code
        self.issue_code = issue_code
        self.challenge = challenge

    def response_headers(self) -> dict[str, str]:
        """The `WWW-Authenticate` challenge a 401 has to carry, and nothing on a 403."""
        return {} if self.challenge is None else {"WWW-Authenticate": self.challenge}


class PassThroughUnavailableError(ServeError):
    """The posture answers the register under each caller's credentials, and this process holds no way to.

    Loud rather than silent, because the silent alternative is reading the instance as the facade's
    own profile - which is the whole thing this posture exists to stop.
    """

    def __init__(self) -> None:
        super().__init__(
            "this server answers the register under each caller's own DHIS2 credentials and holds no "
            "connection to do it over: the runtime was attached without the pass-through client "
            "`open_serve_runtime` opens for the `dhis2` posture"
        )


class RegisterReader(Protocol):
    """What a register read needs of whatever it reads DHIS2 through: one raw GET answering parsed JSON.

    `Dhis2Client` satisfies it as it stands, which is what lets the `none` and `token` postures keep
    reading through the runtime's own connection with nothing in `register.wire` branching on posture.
    """

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path, answering the parsed JSON body."""
        ...


class CallerCredentialReader(BaseModel):
    """One caller's `Authorization` header paired with the process's pooled connection, for one request.

    Built per request and dropped with it. The header is `repr=False` so a model that ends up in a
    log line or a traceback frame prints no credential.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    connection: httpx.AsyncClient
    """The pool this facade holds open against the instance, which carries no credential of its own."""

    authorization: str = Field(repr=False)
    """The caller's header value, verbatim - never parsed, never logged, never held past this request."""

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read one DHIS2 path as the caller, forwarding their header and none of the runtime's.

        The refusals are shaped so every caller of `register.wire` keeps working unchanged: a 404 is
        a `Dhis2ApiError` the read folds into "nothing here", a 400 naming an absent tracked entity
        type is the one the surface folds into an empty answer, and a transport failure is a
        `Dhis2ClientError` the routes answer 502 to. The two verdicts about the CALLER - 401 and 403 -
        leave as themselves.
        """
        try:
            answer = await self.connection.get(path, params=params, headers=self._headers())
        except httpx.HTTPError as error:
            raise Dhis2ClientError(f"the DHIS2 instance could not be read as the caller ({error})") from error
        issue_code = PASSED_THROUGH_REFUSALS.get(answer.status_code)
        if issue_code is not None:
            raise UpstreamRefusalError(
                answer.status_code,
                issue_code,
                challenge_for(ServeAuth.DHIS2) if answer.status_code == 401 else None,
            )
        if answer.status_code >= 400:
            raise Dhis2ApiError(status_code=answer.status_code, message=answer.reason_phrase, body=_error_body(answer))
        return _parsed_body(answer)

    def _headers(self) -> dict[str, str]:
        """What one read carries beyond the pool's own: the caller's credential, and what it wants back."""
        return {"Authorization": self.authorization, "Accept": PASS_THROUGH_ACCEPT}


@asynccontextmanager
async def open_pass_through_client(base_url: str, *, provenance: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Open the connection pass-through reads share, pointed at the instance and holding no credential.

    No `auth=` and no `Authorization` in the default headers, so a request that somehow reached this
    pool without a caller's header would be an anonymous request to DHIS2 rather than a request as
    the facade. The provenance header is a property of the process rather than of a request, so it
    rides on the pool.
    """
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=PASS_THROUGH_TIMEOUT_SECONDS,
        headers={FACADE_PROVENANCE_HEADER: provenance},
    ) as connection:
        yield connection


async def register_reader(request: Request) -> RegisterReader | None:
    """What one register read runs over: the caller's own credentials under `dhis2`, else the runtime's client.

    None is the compiled run, and it is the same None `live_client` answers - a process with no
    instance behind it has nothing to read a register from, whatever posture it serves under.
    """
    runtime_connection = live_client(request)
    if runtime_connection is None:
        return None
    if serve_context(request).settings.auth is not ServeAuth.DHIS2:
        return runtime_connection
    return await caller_reader(request)


async def caller_reader(request: Request) -> CallerCredentialReader:
    """Bind one request's own `Authorization` to the pooled connection, refusing a request that carries none.

    A register read under this posture is answered under the credentials of whoever asked, so a
    request that presented none has nothing to be answered under. That is a 401 rather than a fall
    back to the runtime's client: falling back would answer an anonymous caller with the facade
    profile's rights, which is exactly the read this posture exists to stop.

    `[serve] auth_scope = "write"` leaves reads unguarded, so a register read can be the first thing
    on a request that has established nobody. It establishes them here, through the same check and
    the same brief cache the guarded routes use, rather than refusing a caller who presented perfectly
    good credentials on an address that had not been told to look at them.
    """
    if request_identity(request) is None:
        await require_authenticated(request)
    identity = request_identity(request)
    presented = request.headers.get(AUTHORIZATION_HEADER, "").strip()
    if identity is None or identity.posture is not ServeAuth.DHIS2 or presented == "":
        raise UnauthenticatedError(
            "this server answers the register under the DHIS2 authorization of whoever asks, and this "
            "request presented no credential to answer it under",
            challenge_for(ServeAuth.DHIS2),
        )
    connection = caller_client(request)
    if connection is None:
        raise PassThroughUnavailableError
    return CallerCredentialReader(connection=connection, authorization=presented)


def _error_body(answer: httpx.Response) -> Any:
    """What DHIS2 said about a refusal - its JSON when it sent JSON, its text when it did not.

    The same shape `Dhis2Client` puts on a `Dhis2ApiError`, because the callers reading `body` for an
    `errorCode` are the same callers.
    """
    try:
        return answer.json()
    except ValueError:
        return answer.text


def _parsed_body(answer: httpx.Response) -> dict[str, Any]:
    """One answered body as parsed JSON, matching what `Dhis2Client.get_raw` hands its callers.

    An empty body is an empty object, a JSON value that is not an object rides under `data`, and a
    non-JSON body is a refusal rather than an empty answer - a 200 carrying HTML is a proxy or a
    sign-in page standing in for the API, and reading it as "no results" would hide that entirely.
    """
    if not answer.content.strip():
        return {}
    try:
        parsed = answer.json()
    except ValueError:
        raise Dhis2ApiError(
            status_code=answer.status_code,
            message="expected a JSON body but got non-JSON content "
            "(a proxy or sign-in page may be standing in for the DHIS2 API)",
            body=answer.text[:200],
        ) from None
    return parsed if isinstance(parsed, dict) else {"data": parsed}

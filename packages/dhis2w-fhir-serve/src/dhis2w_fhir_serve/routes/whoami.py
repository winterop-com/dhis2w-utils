"""`GET /facade/whoami` - the one address whose whole answer is who this server just decided the caller is.

WHY AN ADDRESS FOR IT. Every other route on this facade answers a question about the guide or about
the instance, and who is asking is a fact the route needs rather than the fact it reports. A caller
holding a credential has no way to learn whether this server accepts it except by doing something
with it, and under `[serve] auth_scope = "write"` the only thing that would answer is a capture -
which means the first honest verdict on a credential arrives after somebody has filled in a form.
This address is that verdict, on its own, before anything is typed. The capture UI's sign-in panel is
the first caller and every HTTP client is welcome to the same answer.

IT CARRIES THE CHECK IN EVERY SCOPE, and that is the whole of what makes it useful. `write` guards
one route and `all` guards all but `/metadata`; this one is guarded under both, because a route that
answered "nobody" instead of refusing would turn a wrong password into a shrug. So the answer is
either 200 naming a caller or the 401 `dhis2w_fhir_serve.auth` refuses everything else with - the
same OperationOutcome, the same `WWW-Authenticate` challenge, no second vocabulary to read.

IT NAMES A CALLER ONLY WHERE A POSTURE IS CONFIGURED, and under `auth = "none"` it says so in those
words. A server that checks nobody has nobody to name, and one that answered with an anonymous
caller would be inventing an identity to report - so the answer is a 404 that states the posture it
is missing rather than one naming an invented person. It is a route of its own rather than a path
left unmounted, because an unmounted path answers the facade mount's own 404 and says only that
there is nothing here - and `whoami` is a fixed path this project documents rather than one nobody
asked for. `serve_routers` picks which of the two routers is mounted, beside every other mount-time
decision.

WHAT IT NAMES, PER POSTURE. `dhis2` answers the username the instance gave `GET /api/me`; `jwt`
answers the claim `[serve.jwt] username_claim` names, which is the same value a receipt is stamped
with; `token` answers no username at all, because a static token names a deployment rather than a
person, and `name` states that in words rather than inventing one. Nothing else crosses - not the
credential, not the roles the instance holds, not the claims beside the username. This says who, and
who is all it says.
"""

from __future__ import annotations

from dhis2w_fhir.config import ServeAuth
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request

from dhis2w_fhir_serve.auth import RequestIdentity, UnauthenticatedError, challenge_for, request_identity
from dhis2w_fhir_serve.errors import ServeError
from dhis2w_fhir_serve.routes.context import serve_context

#: Where the answer is served from, under the facade API's mount.
WHOAMI_PATH = "/whoami"

#: What this operation is grouped under in the facade API's document.
WHOAMI_TAG = "Caller"

#: What the `token` posture calls its caller, having been handed a deployment's secret and not a person.
TOKEN_CALLER_NAME = "the bearer of one of this deployment's tokens"

router = APIRouter()
refusal_router = APIRouter()


class NoPostureNamesNobodyError(ServeError):
    """`/whoami` was asked of a server running `[serve] auth = "none"`, which establishes no caller.

    A 404 with the reason stated, rather than the read catch-all's "does not serve the resource type
    `whoami`": the address exists in this facade's vocabulary, and what is absent is the posture that
    would give it something to say.
    """

    status_code = 404
    issue_code = "not-supported"

    def __init__(self) -> None:
        """State what is missing: a posture, not a resource type."""
        super().__init__(
            "this server authenticates nobody, so it names nobody: `/whoami` answers a caller only "
            "where `[serve] auth` states a posture"
        )


class AuthenticatedCaller(BaseModel):
    """Who this server established one request to be, under the posture that established it."""

    model_config = ConfigDict(frozen=True)

    posture: ServeAuth
    """Which check ran - `dhis2`, `token`, or `jwt`. Never `none`, which mounts no route here."""

    username: str | None = None
    """The person the credential named: the DHIS2 username under `dhis2`, the claim `[serve.jwt]
    username_claim` names under `jwt`. None under `token`, which names no person."""

    name: str
    """What to call this caller in a sentence - the username where there is one, and `TOKEN_CALLER_NAME`
    where the credential named a deployment rather than anybody."""


@router.get(
    WHOAMI_PATH,
    tags=[WHOAMI_TAG],
    summary="Name the caller",
    description=(
        "Answers who this server established the caller to be, under the posture that established "
        "them. Guarded in every scope, so a credential this server does not accept is refused here "
        "with 401 rather than answered with nobody - which is what makes this the place to check a "
        'credential before doing anything with it. Under `[serve] auth = "none"` the address '
        "answers 404 saying which posture is missing, because a server that checks nobody has "
        "nobody to name."
    ),
    response_description="Who the credential named, and what to call them in a sentence.",
)
async def read_authenticated_caller(request: Request) -> AuthenticatedCaller:
    """Name the caller the authentication check just established, or refuse as that check refuses."""
    identity = request_identity(request)
    if identity is None:
        # Unreachable through a server this package started: this router is mounted only where a
        # posture is configured, and it carries the check in every scope, so a request reaching the
        # handler has an identity. Stated anyway, because an embedding application mounting these
        # routers under a check of its own could reach it - and a 200 naming nobody would be this
        # address answering the one question it exists to answer by giving up on it.
        settings = serve_context(request).settings
        raise UnauthenticatedError(
            "this server established no caller for this request: the routers were mounted under a "
            "check that records no identity",
            challenge_for(settings.auth, settings.jwt.issuer),
        )
    return authenticated_caller(identity)


@refusal_router.get(
    WHOAMI_PATH,
    tags=[WHOAMI_TAG],
    summary="Name the caller",
    description=(
        'This process runs `[serve] auth = "none"` and establishes no caller, so the address '
        "answers 404 naming the posture that is missing rather than an invented identity. A process "
        "started under any other posture answers this address with the caller it established."
    ),
    response_description="Never answered under this posture; the refusal names the missing posture.",
)
async def refuse_to_name_a_caller() -> AuthenticatedCaller:
    """Refuse the address under `auth = "none"`, naming the posture that is missing rather than a caller."""
    raise NoPostureNamesNobodyError


def authenticated_caller(identity: RequestIdentity) -> AuthenticatedCaller:
    """One established identity as this address answers it, naming the person where a person was named."""
    if identity.username is None:
        return AuthenticatedCaller(posture=identity.posture, name=TOKEN_CALLER_NAME)
    return AuthenticatedCaller(posture=identity.posture, username=identity.username, name=identity.username)

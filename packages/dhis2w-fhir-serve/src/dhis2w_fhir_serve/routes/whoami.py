"""`GET /whoami` - the one address whose whole answer is who this server just decided the caller is.

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

IT IS MOUNTED ONLY WHERE A POSTURE IS CONFIGURED. Under `auth = "none"` there is no route here at
all, and a 404 is the honest answer: a server that checks nobody has nobody to name, and one that
answered with an anonymous caller would be inventing an identity to report. `serve_routers` is what
decides that, beside every other mount-time decision.

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
from dhis2w_fhir_serve.routes.context import serve_context

#: Where the answer is served from. One lowercase segment, so no FHIR resource type can collide.
WHOAMI_PATH = "/whoami"

#: What the `token` posture calls its caller, having been handed a deployment's secret and not a person.
TOKEN_CALLER_NAME = "the bearer of one of this deployment's tokens"

router = APIRouter()


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


@router.get(WHOAMI_PATH)
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


def authenticated_caller(identity: RequestIdentity) -> AuthenticatedCaller:
    """One established identity as this address answers it, naming the person where a person was named."""
    if identity.username is None:
        return AuthenticatedCaller(posture=identity.posture, name=TOKEN_CALLER_NAME)
    return AuthenticatedCaller(posture=identity.posture, username=identity.username, name=identity.username)

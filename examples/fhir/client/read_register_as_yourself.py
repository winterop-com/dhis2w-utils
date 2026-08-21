"""Read the register under your own DHIS2 authorization, on a facade running `auth = "dhis2"`.

A facade that authenticates every caller and then reads DHIS2 as its own configured profile answers
all of them with that profile's rights. Under `[serve] auth = "dhis2"` it does not: every register
read carries **your** `Authorization` header to the instance, exactly as it arrived, and DHIS2
applies its own sharing, organisation unit scopes, ownership, and access levels to you.

Three things this file shows, in order:

1. `/metadata` says so before you send a credential. `rest.security.description` under this posture
   states that reads of the register are answered under the caller's own DHIS2 authorization, so a
   client learns the rule from the conformance document rather than from a refusal.
2. A register read with no credential is a 401 - there is nobody to answer as, and answering as the
   facade is the read this posture exists to prevent. The `WWW-Authenticate` header names what to
   present.
3. The same read with your DHIS2 credentials is answered, and what comes back is what that account
   may see. Send another account's credentials and the same URL can answer differently; that is the
   point, and it is DHIS2 deciding, not this server.

What you present is what you would present DHIS2: a username and password as HTTP Basic, or a DHIS2
personal access token as `Authorization: ApiToken <token>`. The facade never parses it, never logs
it, and never holds it past the request.

Usage:
    d2w fhir serve --live --auth dhis2 --port 8123   # in the project directory, in another shell
    uv run python examples/fhir/client/read_register_as_yourself.py

With no facade named in `D2W_FHIR_EXAMPLE_FACADE`, the shared fixture starts one under this posture
and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import base64

import httpx
from _fixture import FixtureError, served_facade
from _runner import run_example
from dhis2w_client import Profile
from dhis2w_core.profile import resolve_profile

FHIR_JSON = "application/fhir+json"
OK = 200
UNAUTHENTICATED = 401

PERSON_RESOURCE_TYPE = "Patient"
"""The resource a person is served as, per the project's published tracked entity type map."""


def caller_authorization(profile: Profile) -> str:
    """The `Authorization` header value one DHIS2 profile would send, which is what a caller sends here.

    Two of the profile's authentication kinds are credentials a person holds and can present to any
    server that speaks to DHIS2. The other two are not: an OAuth2 profile's token is minted for one
    client, and a session cookie is not an `Authorization` header at all.
    """
    if profile.auth == "basic" and profile.username and profile.password:
        encoded = base64.b64encode(f"{profile.username}:{profile.password}".encode()).decode("ascii")
        return f"Basic {encoded}"
    if profile.auth == "pat" and profile.token:
        return f"ApiToken {profile.token}"
    raise FixtureError(
        f"this example presents your own DHIS2 credentials to the facade, and the active profile "
        f"authenticates with `{profile.auth}`, which is not a credential a caller can present. Use a "
        f'profile with `auth = "basic"` or `auth = "pat"`: `d2w profile add local --url '
        f"http://localhost:8080 --auth basic --username admin --password district`"
    )


async def main() -> None:
    """Read the register with no credential, then with your own, against a `dhis2`-posture facade."""
    base_url = served_facade(auth="dhis2")
    authorization = caller_authorization(resolve_profile())
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=60.0) as client:
        # 1. The conformance document states the posture, in every posture. Nothing is inferred.
        capability = (await client.get("/metadata")).raise_for_status().json()
        security = capability["rest"][0]["security"]
        print(f"{base_url} authenticates with: {', '.join(_named(service) for service in security['service'])}")
        print(f"  {security['description']}")

        # 2. No credential, no caller to read as. Note this is a read: the register asks for
        #    credentials even under `auth_scope = "write"`, which leaves reads of the guide open.
        anonymous = await client.get(f"/{PERSON_RESOURCE_TYPE}", params={"_count": 5})
        print(f"\nGET /{PERSON_RESOURCE_TYPE} with no credential -> {anonymous.status_code}")
        if anonymous.status_code == UNAUTHENTICATED:
            print(f"  WWW-Authenticate: {anonymous.headers['WWW-Authenticate']}")
            for issue in anonymous.json().get("issue", []):
                print(f"  {issue['diagnostics']}")

        # 3. The same read, as you. What DHIS2 lets this account see is what this page holds - and
        #    what it does not, it does not: an entity you may not see is a 404, as DHIS2 answers it.
        answered = await client.get(
            f"/{PERSON_RESOURCE_TYPE}", params={"_count": 5}, headers={"Authorization": authorization}
        )
        print(f"\nGET /{PERSON_RESOURCE_TYPE} as yourself -> {answered.status_code}")
        if answered.status_code != OK:
            for issue in answered.json().get("issue", []):
                print(f"  [{issue['code']}] {issue['diagnostics']}")
            return
        page = answered.json()
        print(f"  the register holds {page.get('total', 0)} {PERSON_RESOURCE_TYPE}(s) you may see")
        for entry in page.get("entry", []):
            print(f"    {entry['resource']['id']}")


def _named(service: dict[str, object]) -> str:
    """One scheme `rest.security` names, coded where R4 has a code for it and stated as text where not."""
    return str(service.get("text", "?"))


if __name__ == "__main__":
    run_example(main)

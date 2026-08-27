"""Present a credential to a guarded facade - `BearerToken` on a `token`-posture server, and the 401 without one.

A `FacadeClient` takes one `FacadeCredential` and puts it on every request it makes. Which subclass
you construct is a property of the scheme, not of the posture the server runs under:

- **`BearerToken`** is `Authorization: Bearer <token>`. It is what the `token` posture reads out of
  `D2W_FHIR_SERVE_TOKENS`, and also what the `jwt` posture takes - those two differ only in who
  minted the token, which is the server's business and not the caller's.
- **`UsernamePassword`** is HTTP Basic, and **`PersonalAccessToken`** is DHIS2's own
  `Authorization: ApiToken <token>`. Both are the `dhis2` posture's classes: under it the caller's
  DHIS2 credentials *are* their facade credentials, replayed against `GET /api/me` on the instance
  the facade reads. That posture needs a live instance to check a credential against, so it is not
  what a file that has to run unattended demonstrates - `read_register_as_yourself.py` is that story.

This file uses the `token` posture, which authenticates nobody against anything: it starts a facade
of its own with `--auth token`, hands it a token through the environment, and shows the three states
a caller can be in.

**Which requests are guarded is `[serve] auth_scope`.** The default, `write`, covers the
state-changing surface only - `POST /QuestionnaireResponse` - and leaves reads open, so a client
reads `/metadata` and fills a form before it has a credential and needs one only to submit. `all`
guards everything except `/metadata`, which stays open so a client can always read the posture it
must meet.

Usage:
    d2w fhir serve --auth token --port 8123   # in the project directory, in another shell
    uv run python examples/fhir/client/authenticate_with_the_client.py

The shared fixture starts the guarded facade and stops it at exit - which is what lets this run
unattended. It binds a port the operating system hands out, so nothing else you are running is
disturbed.
"""

from __future__ import annotations

import os

from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir import BearerToken, FacadeClient, FacadeError
from dhis2w_fhir.r4 import CapabilityStatementSecurity

#: The token this example's own facade accepts. A real deployment's token is a long random value
#: nobody committed; this one exists for the length of one process and guards nothing real.
EXAMPLE_TOKEN = "an-example-token-for-one-process"

#: A token this facade was never given - a caller presenting the wrong secret rather than none.
WRONG_TOKEN = "not-the-token-this-facade-holds"

#: Makes the generated draft byte-reproducible, so two runs submit the same answers.
SEED = 20260


async def main() -> None:
    """Read a guarded facade with no credential, submit without one, submit with the wrong one, then with the right."""
    # The `token` posture reads its tokens from the environment and nowhere else - never from
    # fhir.toml, which is a file projects commit. This is set before the fixture starts anything,
    # because the facade reads the variable out of the environment it inherits.
    os.environ["D2W_FHIR_SERVE_TOKENS"] = EXAMPLE_TOKEN
    base_url = served_facade(auth="token")

    # NO CREDENTIAL. Under the default `write` scope the reads stay open, so this client gets the
    # conformance document and a filled draft without presenting anything - and is refused the moment
    # it tries to store something.
    async with FacadeClient(base_url) as anonymous:
        capability = await anonymous.capability()
        rest = next(iter(capability.rest or ()), None)
        print(f"{anonymous.base_url} authenticates with: {stated(rest.security if rest else None)}")

        draft = await anonymous.generate(aggregate_form_id(), seed=SEED)
        print(f"\n$generate with no credential: {len(draft.item or [])} top-level item(s) - reads are open")

        print("\nsubmit with no credential")
        try:
            await anonymous.submit_response(draft)
        except FacadeError as refusal:
            report(refusal)

    # THE WRONG TOKEN. The comparison is constant-time, so the time this refusal takes says nothing
    # about how much of the token was right.
    print(f"\nsubmit with a token this facade does not hold: {WRONG_TOKEN}")
    async with FacadeClient(base_url, auth=BearerToken(token=WRONG_TOKEN)) as impostor:
        try:
            await impostor.submit_response(draft)
        except FacadeError as refusal:
            report(refusal)

    # THE RIGHT TOKEN. One credential, constructed once, put on every request the client makes.
    print("\nsubmit with the token this facade was started with")
    async with FacadeClient(base_url, auth=BearerToken(token=EXAMPLE_TOKEN)) as caller:
        receipt = await caller.submit_response(draft)
        print(f"  accepted: receipt {receipt.response_id}")
        print(f"  the facade says: {receipt.note}")

    # A static token names no person, which is why the receipt above is attributed to nobody. The
    # `dhis2` and `jwt` postures establish an identity and the capture route stamps it onto the
    # receipt; `token` is a deployment secret, not an account.
    print("\nA static token names no person - this receipt records no reporter.")
    print("Not yet sent to DHIS2 - run `d2w fhir forward --import` in the project directory to send it.")


def report(refusal: FacadeError) -> None:
    """One refusal printed the way a capture screen renders it: the status, then what the facade said."""
    print(f"  refused with {refusal.status_code}")
    for issue in refusal.issues:
        print(f"    [{issue.severity}] {issue.code}: {issue.diagnostics}")


def stated(security: CapabilityStatementSecurity | None) -> str:
    """What `rest.security` says this facade takes, which a client reads before it sends anything."""
    services = security.service if security is not None else None
    return ", ".join(str(service.text) for service in services or () if service.text) or "nothing stated"


if __name__ == "__main__":
    run_example(main)

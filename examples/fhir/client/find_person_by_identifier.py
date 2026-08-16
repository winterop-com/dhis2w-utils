"""Find a person already in the DHIS2 register before capturing anything for them.

Capturing a visit needs the tracked entity UID of the person it is about, and a reporter does not
know one - they know a card number, a household code, a national identifier. The register surface is
where one becomes the other: search by the value a person carries, get back the tracked entity the
instance holds it against.

**This surface exists only when the facade runs live.** Everything else a facade serves comes from
the published guide, which is a snapshot on disk, and the guide publishes no people at all - DHIS2
holds them. So `d2w fhir serve --live` keeps one connection to the instance open and answers a
person lookup from the instance per request, while a facade serving a compiled guide answers 404
saying exactly that. It is the one part of a facade whose answer can differ between two requests a
second apart.

**A search is `identifier` and nothing else.** Naming any other parameter is refused with a 400
rather than quietly ignored, and the reason is worth stating: an ignored `family=Smith` would be
answered with the whole register, every row of it presented as a Smith. The two spellings the
parameter takes are FHIR's own:

- `identifier={system}|{value}` says which key the value is - the tracked entity UID itself, or one
  DHIS2 attribute the guide publishes;
- `identifier={value}` names no key, so every key is tried and the matches are folded into one
  answer, each person appearing once however many of their keys matched.

An identifier nobody holds is an empty answer, never a 404: the query was fine, it just matched
nobody.

Usage:
    d2w fhir serve --live --port 8123      # in the project directory, in another shell
    uv run python examples/fhir/client/find_person_by_identifier.py
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from _fixture import served_facade

FHIR_JSON = "application/fhir+json"
OK = 200

PERSON_RESOURCE_TYPE = "Patient"
"""The resource a person is served as. Each DHIS2 tracked entity type is served as whatever the
project's published map takes it onto, and a project tracking people alone serves this and nothing
else - a project that also tracks herds or samples serves those types beside it."""


def described(person: dict[str, Any]) -> str:
    """One person as the register answers for them: the tracked entity UID and every key they hold."""
    keys = ", ".join(f"{token['value']} ({token['system'].rsplit('/', 1)[-1]})" for token in person["identifier"])
    return f"{person['id']}: {keys}"


def keyed_person(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The first person in a page carrying a key beyond their tracked entity UID, or else the first."""
    people = [entry["resource"] for entry in entries]
    return next((person for person in people if len(person["identifier"]) > 1), people[0])


async def search(client: httpx.AsyncClient, identifier: str) -> None:
    """Run one identifier search and print how many people it named."""
    answer = (await client.get(f"/{PERSON_RESOURCE_TYPE}", params={"identifier": identifier})).raise_for_status()
    print(f"  identifier={identifier}")
    print(f"    matched {answer.json().get('total', 0)}")


async def main() -> None:
    """List one person out of the register, then find that same person by each of their keys."""
    async with httpx.AsyncClient(base_url=served_facade(), headers={"Accept": FHIR_JSON}, timeout=60.0) as client:
        # No `identifier` is the listing - a paged walk of everyone the register serves.
        listing = await client.get(f"/{PERSON_RESOURCE_TYPE}", params={"_count": 20})
        if listing.status_code != OK:
            for issue in listing.json().get("issue", []):
                print(f"no register here [{issue['code']}]: {issue['diagnostics']}")
            return
        page = listing.json()
        print(f"the register holds {page.get('total', 0)} {PERSON_RESOURCE_TYPE}(s)")
        if not page.get("entry"):
            print("nobody is registered yet - enrol someone in DHIS2 first")
            return
        person = keyed_person(page["entry"])
        print(f"  {described(person)}")

        # Both token forms, against the same person. A person's tracked entity UID opens their key
        # list, and every DHIS2 attribute the instance declares unique follows it - so the last key
        # is the one a reporter is most likely to be holding, on a card or a register page.
        token = person["identifier"][-1]
        print("\nnaming which key the value is:")
        await search(client, f"{token['system']}|{token['value']}")
        print("\nnaming no key, so every key is tried:")
        await search(client, token["value"])

        # A value nobody holds. The query ran; it named nobody.
        print("\na value nobody holds:")
        await search(client, "no-person-carries-this")

        # Anything but `identifier` is refused, rather than answered with the whole register.
        refused = await client.get(f"/{PERSON_RESOURCE_TYPE}", params={"family": "Kamara"})
        print(f"\nGET /{PERSON_RESOURCE_TYPE}?family=Kamara -> {refused.status_code}")
        for issue in refused.json().get("issue", []):
            print(f"  {issue['diagnostics']}")


if __name__ == "__main__":
    asyncio.run(main())

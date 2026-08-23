"""Say which tracked entity attribute is a person's name, and read one person through that nomination.

DHIS2 has no name field, no sex field, and no date-of-birth field. It has tracked entity attributes,
and which of them mean those things is a decision each instance made for itself - so a served person
carries a name because somebody said which attribute it is, or they carry none at all. The saying is
one table in `fhir.toml`:

```toml
[ips.identity]
name = "w75KJ2mc4zz"          # First name
sex = "cejWyOfXge6"           # Gender

[ips.identity.administrative_gender]
"Male" = "male"
"Female" = "female"
```

This example is the reading half of that table, at the library level: no project, no facade, no
server. It takes a real person off the seeded instance, applies the nominations above, and prints
the FHIR elements they produce. A `d2w fhir serve --live` run over a project holding the same table
answers `GET /Patient/{uid}` with exactly these elements, because it calls the very function called
here.

**Three answers, and the difference between them is the point.**

- A value the nomination names becomes the element: a `name.text`, a `gender`, a `birthDate`.
- A value the gender map does not mention publishes no `gender` at all. The binding on
  `Patient.gender` is required - `male`, `female`, `other`, `unknown` and nothing else - so an
  unmapped value has no code to become, and inventing one would be a guess.
- A nominated birth date the person has no value for keeps the element and states its absence on
  the standard data-absent-reason extension, which is the International Patient Summary guide's own
  worked example. A value that is not a date states the same absence under `error` instead of
  `unknown`, because "nobody recorded one" and "what was recorded is not a date" are different
  facts about a person.

Nothing is replaced: the attribute's own value still rides the served resource as a labelled extra,
so a reader who disagrees with a nomination can still see what DHIS2 holds.

The design behind the table is `docs/fhir/design/ips.md`; what each key means is
[What goes in](../../../docs/fhir/301-what-goes-in.md).

Usage:
    uv run python examples/fhir/client/identity_nominations.py

Requires a DHIS2 profile (`d2w profile list`) and the seeded Child Programme.
"""

from __future__ import annotations

import tomllib
from typing import Any

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env
from dhis2w_fhir.ips import IdentityNominations, ServedIdentity, served_identity
from dhis2w_fhir.r4 import DATA_ABSENT_REASON_EXTENSION_URL

IDENTITY_TABLE = """
name = "w75KJ2mc4zz"
sex = "cejWyOfXge6"

[administrative_gender]
"Male" = "male"
"Female" = "female"
"""
"""The `[ips.identity]` table this example nominates through, parsed as the file would parse it."""

BIRTH_DATE_ATTRIBUTE = "NI0QRzJvQ0k"
"""A nomination the seeded Child Programme holds no value for, so its absence is what gets stated."""

TRACKED_ENTITY_TYPE = "nEenWmSyUEp"
"""The seeded `Person` type, whose registrations the Child Programme enrols."""

PAGE_SIZE = 100
"""Enough of the register to find somebody carrying a sex value; the seed does not give everybody one."""

_ATTRIBUTE_FIELDS = "attribute,value"
_READ_FIELDS = f"trackedEntity,attributes[{_ATTRIBUTE_FIELDS}],enrollments[attributes[{_ATTRIBUTE_FIELDS}]]"
"""The projection a read asks for. The enrollments are named because the endpoint omits them."""


def nominations() -> IdentityNominations:
    """The nominations this example reads through, loaded the way `fhir.toml` loads them."""
    stated = tomllib.loads(IDENTITY_TABLE)
    return IdentityNominations.model_validate({**stated, "birth_date": BIRTH_DATE_ATTRIBUTE})


def values_of(person: dict[str, Any]) -> dict[str, str]:
    """One person's attribute values, keyed by the attribute UID a nomination names them by.

    Entity-level values first, then the ones the enrollments carry. A DHIS2 attribute is collected
    at the tracked entity type or at the program, and a nomination names the attribute rather than
    the level - so a sex recorded on the Child Programme enrollment is still that person's sex.
    """
    held: dict[str, str] = {}
    carried = list(person.get("attributes") or [])
    for enrollment in person.get("enrollments") or []:
        carried.extend(enrollment.get("attributes") or [])
    for attribute in carried:
        if attribute.get("attribute") and attribute.get("value"):
            held.setdefault(attribute["attribute"], attribute["value"])
    return held


def described(identity: ServedIdentity) -> list[str]:
    """The FHIR elements one reading fills, and the absences it states, one line each."""
    lines = [
        f"  name      {identity.name[0].text!r}" if identity.name else "  name      (not stated)",
        f"  gender    {identity.gender!r}" if identity.gender else "  gender    (no mapped value, so no element)",
    ]
    if identity.birth_date is not None:
        lines.append(f"  birthDate {identity.birth_date!r}")
    else:
        reason = _absence_reason(identity)
        lines.append(f"  birthDate absent, stated as data-absent-reason {reason!r} on _birthDate")
    return lines


def _absence_reason(identity: ServedIdentity) -> str | None:
    """The code the `_birthDate` sibling carries, or None where the element states no absence."""
    element = identity.birth_date_element
    for extension in (element.extension or []) if element is not None else []:
        if extension.url == DATA_ABSENT_REASON_EXTENSION_URL:
            return extension.valueCode
    return None


async def main() -> None:
    """Read a page of the register and show what the nominations make of two of the people on it."""
    identity_nominations = nominations()
    print("nominated attributes:", ", ".join(identity_nominations.nominated_attribute_uids()))
    async with open_client(profile_from_env()) as client:
        page = await client.get_raw(
            "/api/tracker/trackedEntities",
            params={
                "trackedEntityType": TRACKED_ENTITY_TYPE,
                "ouMode": "ACCESSIBLE",
                "fields": _READ_FIELDS,
                "pageSize": PAGE_SIZE,
            },
        )
    people = page.get("trackedEntities") or []
    if not people:
        print("the instance holds no tracked entity of the seeded Person type; nothing to read")
        return
    for person in _two_worth_showing(people, identity_nominations):
        held = values_of(person)
        print(f"\n{person['trackedEntity']} holds {len(held)} attribute value(s)")
        for line in described(served_identity(held, identity_nominations)):
            print(line)


def _two_worth_showing(people: list[dict[str, Any]], identity_nominations: IdentityNominations) -> list[dict[str, Any]]:
    """One person the gender map answers for and one it does not, so both readings are on screen."""
    gender_map = identity_nominations.administrative_gender
    mapped = [person for person in people if _sex_of(person, identity_nominations) in gender_map]
    unmapped = [person for person in people if _sex_of(person, identity_nominations) not in gender_map]
    return [*mapped[:1], *unmapped[:1]] or people[:1]


def _sex_of(person: dict[str, Any], identity_nominations: IdentityNominations) -> str | None:
    """The value one person holds for the nominated sex attribute, or None where they hold none."""
    return None if identity_nominations.sex is None else values_of(person).get(identity_nominations.sex)


if __name__ == "__main__":
    run_example(main)

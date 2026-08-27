"""Read `/facade/metadata-health` off a live facade - what the DHIS2 instance holds that the guide cannot carry.

One read, two analyses. The findings are `d2w fhir validate`'s own, reread over the connection the
facade already holds, so a defect named here is named in the same words the report files carry: a
name carrying a character the IG publisher cannot survive, a code no FHIR system will take, an
object carrying no code at all. The translation coverage beside them is the endpoint's own: which
locales this instance carries translations in, how much of the selection each covers, and how each
locale is read on the side of it that is the shorter list.

Plain `application/json` rather than FHIR, on a lowercase hyphenated segment no resource type can
collide with - there is no FHIR shape for "this DHIS2 name has a `<` in it".

LIVE RUNS ONLY, AND THE REFUSAL IS A BODY. A facade serving a compiled guide off disk answers 200
with `available: false` and the reason in words, so a caller reads the body rather than catching -
which is what the branch below does.

Usage:
    uv run python examples/fhir/client/read_metadata_health.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a `--live` facade on
the example project and stops it at exit, which is what lets this run unattended.
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx
from _fixture import served_facade

#: How many findings and objects to print. The whole report can run to thousands of rows on a
#: national instance, and an example is about the shape of the answer rather than the volume of it.
SHOWN = 5


def spellings(name: bool, form_name: bool) -> str:
    """Which of an object's two spellings one translation row is about, in DHIS2's own words."""
    if name and form_name:
        return "name and form name"
    return "form name" if form_name else "name"


async def main() -> None:
    """Read the report and print the strip, the first findings, and the first translation gaps."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": "application/json"}, timeout=600.0) as client:
        health = (await client.get("/facade/metadata-health")).raise_for_status().json()

    if not health["available"]:
        # A compiled run. Not an error and not an empty report - a state, with the server's own
        # sentence saying what to do about it.
        print(health["reason"])
        return

    counts = health["counts"]
    print(f"{health['object_count']} metadata objects read from the instance behind {base_url}")
    print(f"  graded under hostile_names = {health['graded_under']}")
    print(f"  {counts['errors']} error(s), {counts['warnings']} warning(s), {counts['infos']} note(s)")

    for finding in health["findings"][:SHOWN]:
        # `field` is the DHIS2 field to go and change; `cost` is what the grade means for the build.
        print(f"\n{finding['severity']:8} {finding['resource_type']}/{finding['uid']}  {finding['name']}")
        print(f"  {finding['field'] or '-'}: {finding['message']}")
        print(f"  {finding['cost']}")

    translations = health["translations"]
    if not translations["locales"]:
        print("\nNothing in this selection carries a translation - the instance is maintained in one language.")
        return

    # The denominator is every translatable string rather than every object: a data element carries a
    # name and a form name, and a locale holding the first and not the second has done half of it.
    total = translations["object_count"] + translations["form_named_count"]
    print(f"\nTranslations, over {total} translatable string(s):")
    for locale in translations["per_locale"]:
        covered = locale["name_count"] + locale["form_name_count"]
        print(f"\n  {locale['locale']:8} {covered}/{total}  ({locale['standing']})")
        # Each locale is told through whichever side of it is the shorter list. A `sparse` locale -
        # under half the selection - names the objects that carry it and states no absence at all; a
        # `majority` locale names the objects nobody has written the translation for yet. An absent
        # translation is a coverage fact either way, never a finding and never a severity.
        if locale["standing"] == "sparse":
            for carrier in locale["carriers"][:SHOWN]:
                written = spellings(carrier["carries_name"], carrier["carries_form_name"])
                print(f"    carries {written}: {carrier['resource_type']}/{carrier['uid']} {carrier['name']}")
        else:
            for row in locale["missing"][:SHOWN]:
                short = spellings(row["name_untranslated"], row["form_name_untranslated"])
                print(f"    not yet written, {short}: {row['resource_type']}/{row['uid']} {row['name']}")


if __name__ == "__main__":
    asyncio.run(main())

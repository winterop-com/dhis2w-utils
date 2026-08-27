"""Find things on a facade with `FacadeClient` - `canonical_resource_types`, `search`, and `resolve`.

`send_with_the_client.py` next door is the write half of this client. This is the read half: what a
facade publishes, how to ask it for a subset, and how to turn a canonical url into the resource it
names without knowing which type holds it.

Three calls carry the whole story:

- **`canonical_resource_types()`** is read off `/metadata`, not written down here. The facade
  declares a `url` search parameter on a type only when its store actually holds instances of it, so
  a project publishing no ConceptMap never appears in this list and nothing asks it for one.
- **`search(type, query)`** answers a searchset Bundle. `total` is the whole match set and `entry`
  is what this request asked for, so a capped search answers a total larger than the entries it
  carries.
- **`resolve(canonical)`** asks each of those types in turn for one url. `None` is an answer: this
  facade publishes nothing under that canonical.

Usage:
    uv run python examples/fhir/client/search_with_the_client.py [BASE_URL]

BASE_URL defaults to $FHIR_SERVE_URL. With neither, the shared fixture starts a facade on the
example project and stops it at exit - which is what lets this run unattended.
"""

from __future__ import annotations

import os
import sys

from _fixture import aggregate_form_id, form_canonical, person_form_id, served_facade
from _runner import run_example
from dhis2w_fhir import FacadeClient, ResourceQuery
from dhis2w_fhir.r4 import Bundle, JsonResource

#: How many entries each search asks for. Every published form and every registered person has the
#: same shape, so a handful says as much as a hundred and the printout stays readable.
SAMPLE_SIZE = 3

#: A canonical no project publishes, so `resolve` has something to answer `None` about.
ABSENT_CANONICAL = "http://example.org/fhir/no-such-guide/Questionnaire/NotPublished"

#: The resource a person is served as, per the project's published tracked entity type map.
PERSON_RESOURCE_TYPE = "Patient"


async def main() -> None:
    """Walk what a facade publishes, search two kinds of store, and resolve a canonical to its resource."""
    base_url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FHIR_SERVE_URL")) or served_facade()

    async with FacadeClient(base_url) as facade:
        # WHAT THIS FACADE PUBLISHES. Read off the CapabilityStatement rather than assumed, which is
        # why the list is different on a project that publishes different things.
        canonical_types = await facade.canonical_resource_types()
        print(f"{facade.base_url} declares a canonical url on: {', '.join(canonical_types)}")

        # WHY `ResourceQuery` EXISTS. The facade honours a small, fixed set of search parameters and
        # treats the rest two different ways: a store search IGNORES a parameter it does not know,
        # and a register search REFUSES one. A free-form mapping is therefore a quiet way to get the
        # wrong answer on one route and a 400 on the other. This model can spell only what the
        # facade honours, so a mistake is a type error here rather than a surprise on the wire.
        forms = await facade.search("Questionnaire", ResourceQuery(count=SAMPLE_SIZE))
        print(f"\nQuestionnaire?_count={SAMPLE_SIZE}: {forms.total} published, {len(forms.entry or ())} in this answer")
        for identifier, title in named(forms):
            print(f"  {identifier:16} {title}")

        # THE REGISTER, BY TAG. A live facade serves one register per published tracked entity type,
        # and every person it answers carries their type as a `meta.tag`. The tag's code is the
        # DHIS2 tracked entity type uid, which is also the id of the form that registers one.
        tracked_entity_type = person_form_id()
        by_tag = await facade.search(
            PERSON_RESOURCE_TYPE,
            ResourceQuery(tags=(tracked_entity_type,), count=SAMPLE_SIZE),
        )
        print(f"\n{PERSON_RESOURCE_TYPE}?_tag={tracked_entity_type}: {by_tag.total} registered")
        people = named(by_tag)
        for identifier, _ in people:
            print(f"  {identifier}")

        # THE REGISTER, BY IDENTIFIER. `identifier` takes a `system|value` token; a bare value
        # matches any system, which is what a caller holding only a DHIS2 uid has.
        if people:
            uid = people[0][0]
            by_identifier = await facade.search(PERSON_RESOURCE_TYPE, ResourceQuery(identifiers=(uid,)))
            print(f"\n{PERSON_RESOURCE_TYPE}?identifier={uid}: {by_identifier.total} match(es)")

        # A CANONICAL IS NOT AN ADDRESS. It says what a resource is without saying where it lives, so
        # resolving one means asking each declaring type in turn - which is what `resolve` does.
        canonical = form_canonical(aggregate_form_id())
        found = await facade.resolve(canonical)
        print(f"\nresolve({canonical})")
        print(f"  -> {described(found)}")

        # And a canonical this facade publishes nothing under. `None` is the answer, not a refusal:
        # every declaring type was asked and none of them holds it.
        print(f"resolve({ABSENT_CANONICAL})")
        print(f"  -> {described(await facade.resolve(ABSENT_CANONICAL))}")


def named(bundle: Bundle) -> list[tuple[str, str]]:
    """The id and the title of every entry in one searchset, as the document carried them."""
    rows: list[tuple[str, str]] = []
    for entry in bundle.entry or ():
        if entry.resource is None:
            continue
        document = entry.resource.model_extra or {}
        rows.append((str(document.get("id", "-")), str(document.get("title", "-"))))
    return rows


def described(resource: JsonResource | None) -> str:
    """One resolved resource as a line to read, or the sentence a facade publishing none deserves."""
    if resource is None:
        return "nothing - this facade publishes no resource under that canonical"
    document = resource.model_extra or {}
    return f"{resource.resourceType}/{document.get('id', '-')} - {document.get('title', document.get('name', '-'))}"


if __name__ == "__main__":
    run_example(main)

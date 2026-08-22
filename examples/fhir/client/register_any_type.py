"""Walk every register a facade serves, whatever the instance decided to track - one loop, no list of types.

A DHIS2 instance may declare fifty tracked entity types. `[generate.tracked_entity_types]` maps each
onto the FHIR resource type it really is, and a facade over that guide serves one register per
resource - `Patient` for the people, `Device` for the fridges and the vehicles, `Specimen` for the
lab samples. A client that hard-codes `/Patient` sees the people and nothing else.

So this file hard-codes nothing. It reads `/metadata`, takes the register resources off the
conformance document, and walks them. The idiom is three facts, in this order:

1. **`/metadata` is the list.** A register entry declares `read` and `search-type` and a
   `_tag` search parameter. That last one is what distinguishes a register from every other
   resource the facade serves, because `_tag` is how a register is narrowed to one tracked entity
   type - a Questionnaire endpoint has no such thing.
2. **The entry's documentation names the DHIS2 types behind it.** One FHIR resource type is one
   register over the UNION of its tracked entity types, so `/Device` may be two types at once and
   the documentation says which. Nothing else in the exchange states it.
3. **The tag on each resource says which type it actually is.** Every registered resource carries
   `meta.tag` under `{base}/id/tracked-entity-type`, so a page mixing fridges and vehicles is still
   a page where each row says what it is - and `_tag={uid}` asks for one of them alone.

What you see depends on the guide the facade serves. The shared fixture project publishes a
person-tracking selection, so the walk below prints one register: `Patient`, one type behind it,
however many people the instance holds. Point `D2W_FHIR_EXAMPLE_FACADE` at a facade over a guide
that maps several types and the same loop prints several registers, with no line changed - which is
the whole point of writing it this way.

Usage:
    uv run python examples/fhir/client/register_any_type.py

With no facade named in `D2W_FHIR_EXAMPLE_FACADE`, the shared fixture starts a live one and stops it
at exit.
"""

from __future__ import annotations

import httpx
from _fixture import served_facade
from _runner import run_example
from pydantic import BaseModel, ConfigDict

FHIR_JSON = "application/fhir+json"
OK = 200

#: What a register entry declares and no other served resource does: the tracked entity type search.
TAG_SEARCH_PARAMETER = "_tag"

#: How many rows of each register the walk asks for. `_count=0` would ask for the size alone, but a
#: projection-served facade cannot answer that one, so this asks for a small page and reads its total.
PAGE_SIZE = 5


class Register(BaseModel):
    """One register a facade serves: the resource it answers on, and what it says about itself."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    documentation: str

    def tracked_entity_types(self) -> str:
        """The DHIS2 types this register is served over, as the entry's own documentation names them.

        Read out of the sentence rather than out of a field, because R4's `CapabilityStatement` has
        no element for "the upstream objects behind this resource" - the facade states it in the
        documentation, which is where a conformance document puts what it has no element for.
        """
        _, _, stated = self.documentation.partition("publishes as ")
        _, _, listed = stated.partition(": ")
        named, _, _ = listed.partition(". Identity only")
        return named or "not stated"


def registers(capability: dict[str, object]) -> list[Register]:
    """Every register the conformance document declares, in the order it declares them.

    A register is a resource the facade answers `_tag` on. Everything else it serves - Questionnaire,
    ValueSet, ConceptMap, the received QuestionnaireResponses - comes out of the guide it loaded at
    startup and has no tracked entity type to be narrowed by.
    """
    rest = capability.get("rest")
    if not isinstance(rest, list) or not rest:
        return []
    declared = rest[0].get("resource", []) if isinstance(rest[0], dict) else []
    found: list[Register] = []
    for resource in declared:
        if not isinstance(resource, dict):
            continue
        parameters = {parameter.get("name") for parameter in resource.get("searchParam", [])}
        if TAG_SEARCH_PARAMETER not in parameters:
            continue
        found.append(
            Register(
                resource_type=str(resource.get("type", "")),
                documentation=str(resource.get("documentation", "")),
            )
        )
    return found


async def main() -> None:
    """Read the registers off `/metadata` and walk each one, without naming a resource type anywhere."""
    base_url = served_facade()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=60.0) as client:
        capability = (await client.get("/metadata")).raise_for_status().json()
        served = registers(capability)
        if not served:
            print(f"{base_url} serves no register: it holds no DHIS2 connection, or publishes no registration form")
            return

        print(f"{base_url} serves {len(served)} register(s)\n")
        for register in served:
            page = await client.get(f"/{register.resource_type}", params={"_count": PAGE_SIZE})
            print(f"{register.resource_type}")
            print(f"  DHIS2 tracked entity types: {register.tracked_entity_types()}")
            if page.status_code != OK:
                for issue in page.json().get("issue", []):
                    print(f"  [{issue['code']}] {issue['diagnostics']}")
                continue
            body = page.json()
            total = body.get("total")
            print(f"  in the register: {'not stated' if total is None else total}")
            for entry in body.get("entry", []):
                resource = entry.get("resource", {})
                if resource.get("resourceType") == "OperationOutcome":
                    continue
                tags = [tag.get("code") for tag in resource.get("meta", {}).get("tag", [])]
                print(f"    {resource.get('id')}  (tracked entity type {', '.join(tags) or 'not stated'})")
            print()


if __name__ == "__main__":
    run_example(main)

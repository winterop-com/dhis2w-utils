"""TrackedEntityAttribute.favorite (v42 bool) -> favorites (v43 list[str]) + 6 new search fields.

v42 had `favorite: bool` (a per-user "I favourited this" flag). v43
renamed it to `favorites: list[str]` (the set of usernames who
favourited it) AND added six new search-tuning fields:

- blockedSearchOperators (collection of QueryOperator)
- minCharactersToSearch (int)
- preferredSearchOperator (constant)
- skipAnalytics (bool)
- trigramIndexable (bool)
- trigramIndexed (bool)

Reading the v43 wire shape with the v42-typed helper drops the new
fields onto `model_extra`. For typed access, import the v43 model
directly. This example shows both.

Usage:
    uv run python examples/client/v43/tracked_entity_attribute_favorites.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_client.generated.v43.schemas.tracked_entity_attribute import (
    TrackedEntityAttribute as TrackedEntityAttributeV43,
)
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """List one TEA and surface the v42 bool vs v43 list + new fields."""
    async with open_client(profile_from_env()) as client:
        attributes = await client.tracked_entity_attributes.list_all(page_size=1)
        if not attributes:
            print("no tracked-entity attributes on this instance")
            return
        uid = attributes[0].id or ""
        print(f"version={client.version_key} TEA={uid}")

        if client.version_key == "v42":
            attribute = await client.tracked_entity_attributes.get(uid)
            print(f"  v42 favorite={getattr(attribute, 'favorite', None)!r}  (singular bool)")
            return

        raw = await client.get_raw(f"/api/trackedEntityAttributes/{uid}")
        attribute_v43 = TrackedEntityAttributeV43.model_validate(raw)
        print(f"  v43 favorites={attribute_v43.favorites}  (now a list of usernames)")
        print(
            f"  v43 search fields: "
            f"blockedSearchOperators={attribute_v43.blockedSearchOperators} "
            f"minCharactersToSearch={attribute_v43.minCharactersToSearch} "
            f"preferredSearchOperator={attribute_v43.preferredSearchOperator} "
            f"skipAnalytics={attribute_v43.skipAnalytics} "
            f"trigramIndexable={attribute_v43.trigramIndexable} "
            f"trigramIndexed={attribute_v43.trigramIndexed}"
        )


if __name__ == "__main__":
    run_example(main)

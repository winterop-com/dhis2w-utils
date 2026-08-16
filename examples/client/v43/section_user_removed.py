"""Section.user — present in v42, removed entirely in v43 (also Section.favorite, code/id widened).

In v42, `Section.user: Reference | None` carried the section's owner.
v43 removed both `Section.user` and `Section.favorite` outright; the
`code` and `id` fields were also widened from `IDENTIFIER` to `TEXT`
(see `docs/architecture/schema-diff-v42-v43.md`).

The hand-written `client.sections` accessor returns the v42-typed
`Section`, so on v43 wire data the `.user` attribute is always None
(the field simply isn't on the wire). Defensive readers should branch
on `client.version_key`.

Usage:
    uv run python examples/client/v43/section_user_removed.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Read one Section and demonstrate the removed `user` field per version."""
    async with open_client(profile_from_env()) as client:
        sections = await client.sections.list_all(page_size=1)
        if not sections:
            print("no sections on this instance")
            return
        section = sections[0]
        print(f"version={client.version_key} section={section.id} name={section.name!r}")

        user_ref = getattr(section, "user", None)
        if client.version_key == "v42":
            print(f"  v42 section.user={user_ref.id if user_ref else None!r}")
        else:
            # The v42-typed model still has `.user` as an attribute, but on
            # v43 wire data it is never populated — the field was dropped.
            print(f"  v43 section.user={user_ref!r}  (always None — field was removed)")
            print("  v43 section.favorite -> N/A (field also removed)")


if __name__ == "__main__":
    run_example(main)

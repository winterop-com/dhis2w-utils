"""Build a CategoryCombo from a typed `CategoryComboBuildSpec` via the dhis2w-client library.

Demonstrates the one-pass create-or-reuse helper. The spec is built up
in Python (rather than JSON) so consumers see the typed shape; the
helper itself is identical for both forms.

Usage:
    uv run python examples/client/category_combo_build.py
"""

from __future__ import annotations

import asyncio
import os

from dhis2w_client import (
    BasicAuth,
    CategoryComboBuildSpec,
    CategoryOptionSpec,
    CategorySpec,
    Dhis2Client,
    build_category_combo,
)


def _spec() -> CategoryComboBuildSpec:
    return CategoryComboBuildSpec(
        name="ClientDemoSexModality",
        code="CLIENT_DEMO_SEX_MOD",
        categories=[
            CategorySpec(
                name="ClientDemoSex",
                short_name="ClientSex",
                options=[
                    CategoryOptionSpec(name="ClientDemoMale", short_name="ClientM"),
                    CategoryOptionSpec(name="ClientDemoFemale", short_name="ClientF"),
                ],
            ),
            CategorySpec(
                name="ClientDemoModality",
                short_name="ClientMod",
                options=[
                    CategoryOptionSpec(name="ClientDemoInpatient"),
                    CategoryOptionSpec(name="ClientDemoOutpatient"),
                ],
            ),
        ],
    )


async def main() -> None:
    """Connect with whatever the env says + run the builder against a small demo spec."""
    base_url = os.environ.get("DHIS2_URL", "http://localhost:8080")
    username = os.environ.get("DHIS2_USERNAME", "admin")
    password = os.environ.get("DHIS2_PASSWORD", "district")
    async with Dhis2Client(base_url, auth=BasicAuth(username=username, password=password)) as client:
        result = await build_category_combo(client, _spec(), timeout_seconds=30.0)
    print(f"combo:    {result.combo_uid} ({'created' if result.combo_created else 'reused'})")
    print(f"COCs:     {result.coc_count}/{result.expected_coc_count}")
    for entry in result.categories:
        status = "created" if entry.created else "reused"
        new_options = len(entry.created_option_uids)
        appended = len(entry.appended_option_uids)
        print(
            f"  {entry.name}: {entry.uid}  ({status})  options={len(entry.option_uids)} "
            f"(new={new_options}, appended={appended})"
        )


if __name__ == "__main__":
    asyncio.run(main())

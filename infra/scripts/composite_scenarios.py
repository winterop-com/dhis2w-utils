"""Composite write-workflow scenarios — multi-step CLI workflows with setup + cleanup.

Realistic "build a thing out of several objects" tasks (a data set with data elements, a program
with stages) that a capable agent should complete 100% and that small local models tend to stall
on. Each scenario carries:

- a natural-language `goal` (what a model is asked to accomplish — reused by the bridge/matrix runs),
- a deterministic `reference` runner (the oracle): scripted CLI calls that create -> verify ->
  delete, so the workflow is proven and leaves nothing behind.

Writes go to `local_basic` only (never the shared demo). Run the oracle for every scenario:

    uv run python infra/scripts/composite_scenarios.py            # default profile local_basic
    uv run python infra/scripts/composite_scenarios.py --profile local_basic
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

PROFILE_DEFAULT = "local_basic"


def run_cli_json(profile: str, args: list[str]) -> str:
    """Run `d2w --json -p <profile> <args>` and return stdout."""
    completed = subprocess.run(
        ["uv", "run", "d2w", "--json", "-p", profile, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout


def run_cli(profile: str, args: list[str]) -> int:
    """Run `d2w -p <profile> <args>` (no --json) and return the exit code."""
    return subprocess.run(
        ["uv", "run", "d2w", "-p", profile, *args],
        capture_output=True,
        text=True,
        check=False,
    ).returncode


class ScenarioResult(BaseModel):
    """Outcome of running a scenario's reference (oracle) workflow."""

    model_config = ConfigDict(frozen=True)

    key: str
    ok: bool
    detail: str


class Scenario(BaseModel):
    """A composite workflow: a model-facing goal + a deterministic reference runner."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    key: str
    goal: str
    reference: Callable[[str], ScenarioResult]


def _uid(stdout: str) -> str:
    """Pull the created object's UID from a `--json` create response."""
    try:
        return str(json.loads(stdout).get("id", ""))
    except (json.JSONDecodeError, AttributeError):
        return ""


def _count(stdout: str, key: str) -> int:
    """Count items under `key` in a `--json` get response; -1 if the response did not parse."""
    try:
        value = json.loads(stdout).get(key, [])
    except (json.JSONDecodeError, AttributeError):
        return -1
    return len(value) if isinstance(value, list) else -1


def _dataset_with_elements(profile: str) -> ScenarioResult:
    """Create a Monthly data set with two new data elements, verify the count, then delete all."""
    created: list[tuple[str, str]] = []  # (resource, uid), torn down in reverse
    try:
        de_a = _uid(
            run_cli_json(
                profile,
                [
                    "metadata",
                    "data-elements",
                    "create",
                    "--name",
                    "ZZBench DE A",
                    "--short-name",
                    "ZZBench DE A",
                    "--value-type",
                    "INTEGER",
                ],
            )
        )
        created.append(("data-elements", de_a))
        de_b = _uid(
            run_cli_json(
                profile,
                [
                    "metadata",
                    "data-elements",
                    "create",
                    "--name",
                    "ZZBench DE B",
                    "--short-name",
                    "ZZBench DE B",
                    "--value-type",
                    "NUMBER",
                ],
            )
        )
        created.append(("data-elements", de_b))
        data_set = _uid(
            run_cli_json(
                profile,
                [
                    "metadata",
                    "data-sets",
                    "create",
                    "--name",
                    "ZZBench Monthly",
                    "--short-name",
                    "ZZBench Monthly",
                    "--period-type",
                    "Monthly",
                ],
            )
        )
        created.append(("data-sets", data_set))
        run_cli(profile, ["metadata", "data-sets", "add-element", data_set, de_a])
        run_cli(profile, ["metadata", "data-sets", "add-element", data_set, de_b])
        fetched = run_cli_json(
            profile, ["metadata", "get", "data-sets", data_set, "--fields", "dataSetElements[dataElement]"]
        )
        count = _count(fetched, "dataSetElements")
        return ScenarioResult(key="dataset_with_elements", ok=count == 2, detail=f"data set has {count} elements")
    finally:
        _teardown(profile, created)


def _program_with_stages(profile: str) -> ScenarioResult:
    """Create an event program with two stages, verify the count, then delete all."""
    created: list[tuple[str, str]] = []
    try:
        program = _uid(
            run_cli_json(
                profile,
                [
                    "metadata",
                    "programs",
                    "create",
                    "--name",
                    "ZZBench Visit Program",
                    "--short-name",
                    "ZZBench Visit",
                    "--program-type",
                    "WITHOUT_REGISTRATION",
                ],
            )
        )
        created.append(("programs", program))
        stage_1 = _uid(
            run_cli_json(
                profile, ["metadata", "program-stages", "create", "--program", program, "--name", "ZZBench Stage 1"]
            )
        )
        created.append(("program-stages", stage_1))
        stage_2 = _uid(
            run_cli_json(
                profile, ["metadata", "program-stages", "create", "--program", program, "--name", "ZZBench Stage 2"]
            )
        )
        created.append(("program-stages", stage_2))
        fetched = run_cli_json(profile, ["metadata", "get", "programs", program, "--fields", "programStages[id]"])
        count = _count(fetched, "programStages")
        return ScenarioResult(key="program_with_stages", ok=count == 2, detail=f"program has {count} stages")
    finally:
        _teardown(profile, created)


def _teardown(profile: str, created: list[tuple[str, str]]) -> None:
    """Delete created objects in reverse order so leftovers never accumulate on the stack."""
    for resource, uid in reversed(created):
        if uid:
            run_cli(profile, ["metadata", resource, "delete", uid, "-y"])


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="dataset_with_elements",
        goal=(
            "Create a Monthly data set named 'Demo Intake' with two new data elements — one INTEGER, "
            "one NUMBER — attached to it, then confirm the data set has 2 elements."
        ),
        reference=_dataset_with_elements,
    ),
    Scenario(
        key="program_with_stages",
        goal=(
            "Create an event program (WITHOUT_REGISTRATION) named 'Demo Visits' with two program "
            "stages, then confirm the program has 2 stages."
        ),
        reference=_program_with_stages,
    ),
)


def main() -> None:
    """Run the reference (oracle) workflow for every scenario and report PASS/FAIL + cleanup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=PROFILE_DEFAULT, help="Write profile (local_basic only).")
    args = parser.parse_args()
    print(f"composite scenarios (oracle) against profile {args.profile}\n")
    for scenario in SCENARIOS:
        result = scenario.reference(args.profile)
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.key}: {result.detail} (created + verified + cleaned up)")


if __name__ == "__main__":
    main()

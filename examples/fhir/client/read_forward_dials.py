"""The `[forward]` postures a project takes, and the order a run resolves each of them in.

`fhir.toml` carries three dials about data that has already reached DHIS2, and they answer different
questions. `overwrites` is about an **unmarked** submission - a second capture of the same aggregate
tuple, which says nothing about the first and simply replaces it. `corrections` and `withdrawals` are
about a **marked** one - a submission that names the receipt it amends or retracts.

The two marked-submission dials default to `"off"`, because a project that publishes forms and
forwards them is not thereby a project that lets a submitter reach back into what DHIS2 already
holds. Turning one on is a sentence somebody wrote, not a default nobody read.

Every dial resolves in one place - `service.forward_responses` - in one order: what the caller
stated, then what `fhir.toml` says, then the default the key carries. So the posture a run reports is
the posture every surface of that project resolves, and nothing here needs a DHIS2 instance to show
it: this whole example is a config file and the models that read it.

Usage:
    uv run python examples/fhir/client/read_forward_dials.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dhis2w_fhir import CorrectionPosture, ForwardConfig, OverwritePosture, WithdrawalPosture, load_project

_IG_TABLE = """
[ig]
id = "dhis2.fhir.dials"
canonical = "http://example.org/fhir/dials"
name = "Dials"
title = "Dials"
publisher = "Example Organisation"
"""


def project_stating(forward_table: str, directory: Path) -> ForwardConfig:
    """Write one `fhir.toml` with the given `[forward]` table and read its postures back."""
    table = f"\n[forward]\n{forward_table}\n" if forward_table else ""
    (directory / "fhir.toml").write_text(f"{_IG_TABLE}{table}", encoding="utf-8")
    return load_project(directory).config.forward


def resolved(stated: WithdrawalPosture | None, configured: WithdrawalPosture) -> WithdrawalPosture:
    """The posture one run ends up under: what the caller stated, or what the file says.

    The same two lines every dial resolves through, written out here so the order is visible. In the
    product it lives once, in `service.forward_responses`, so the CLI and the MCP tool cannot resolve
    it differently.
    """
    return stated if stated is not None else configured


def main() -> None:
    """Read the three dials off a bare project and off one that states every posture it takes."""
    with tempfile.TemporaryDirectory() as workspace:
        directory = Path(workspace)

        bare = project_stating("", directory)
        print("a project that states no [forward] table at all:")
        print(f"  overwrites  = {bare.overwrites.value:<8}  an unmarked second capture of an aggregate tuple")
        print(f"  corrections = {bare.corrections.value:<8}  a submission naming the receipt it amends")
        print(f"  withdrawals = {bare.withdrawals.value:<8}  a forwarded receipt taken back out of DHIS2")

        stated = project_stating(
            'overwrites = "refuse"\ncorrections = "amend"\nwithdrawals = "retract"',
            directory,
        )
        print("\na project that states all three:")
        print(f"  overwrites  = {stated.overwrites.value}")
        print(f"  corrections = {stated.corrections.value}")
        print(f"  withdrawals = {stated.withdrawals.value}")

        # The vocabulary is part of each decision, so a fourth word is a refusal rather than a guess.
        print("\nthe words each dial takes:")
        print(f"  overwrites  : {', '.join(posture.value for posture in OverwritePosture)}")
        print(f"  corrections : {', '.join(posture.value for posture in CorrectionPosture)}")
        print(f"  withdrawals : {', '.join(posture.value for posture in WithdrawalPosture)}")

        # A flag is one run's decision and the table is the project's, and the run's wins.
        print('\nwhat one run ends up under, given `withdrawals = "retract"` in the file:')
        print(f"  no flag                 -> {resolved(None, stated.withdrawals).value}")
        print(f"  --withdrawals off       -> {resolved(WithdrawalPosture.OFF, stated.withdrawals).value}")

        # `d2w fhir withdraw` is the one command that acts on a posture rather than reporting it: it
        # refuses outright unless the project - or the run - says `retract`.
        print("\n`d2w fhir withdraw` posts nothing at all unless the resolved posture is `retract`.")


if __name__ == "__main__":
    main()

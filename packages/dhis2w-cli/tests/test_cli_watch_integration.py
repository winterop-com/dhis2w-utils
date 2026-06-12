"""End-to-end `--watch` integration tests against the live DHIS2 stack.

Exercises the three CLI surfaces that kick off a background job and stream
notifications to stdout:

- `d2w maintenance refresh analytics --watch`
- `d2w maintenance dataintegrity run --watch`
- `d2w maintenance task watch <type> <uid>` (given a ref from the above)

Every test goes through `CliRunner` and hits the real `/api/system/tasks/`
feed — no respx mocking — so they only run under `@pytest.mark.slow`
(CI's nightly `make test-slow` target; skipped by default).

Each test asserts two invariants:

1. The command exits 0 (the job reaches `completed=true` before the
   CLI's default timeout of 600 s).
2. At least one `[x]`-marked line (the completion notification with the
   `completed=True` flag) appears in stdout — proves the watch loop
   actually streamed notifications, not just blocked on the kickoff.
"""

from __future__ import annotations

import json
import re

import pytest
from dhis2w_cli.main import build_app
from typer.testing import CliRunner

pytestmark = pytest.mark.slow


def _setup_env(monkeypatch: pytest.MonkeyPatch, local_url: str, local_pat: str | None) -> None:
    """Prime the typed env `profile_from_env` reads; skip if the seeded PAT is missing."""
    if not local_pat:
        pytest.skip("DHIS2_PAT not set — run `make dhis2-run` + seed auth")
    monkeypatch.delenv("DHIS2_PROFILE", raising=False)
    monkeypatch.setenv("DHIS2_URL", local_url)
    monkeypatch.setenv("DHIS2_PAT", local_pat)


def _contains_completion_marker(output: str) -> bool:
    """Detect at least one completion-marked notification line in the CLI's stdout.

    The watch renderer writes `[x]` for completed notifications and `[ ]`
    for in-progress ones; a clean run ends with at least one `[x]`.
    """
    return "[x]" in output


def test_analytics_refresh_watch_completes(
    monkeypatch: pytest.MonkeyPatch, local_url: str, local_pat: str | None
) -> None:
    """`d2w maintenance refresh analytics --watch` kicks off + watches to completion."""
    _setup_env(monkeypatch, local_url, local_pat)
    result = CliRunner().invoke(
        build_app(),
        ["maintenance", "refresh", "analytics", "--last-years", "1", "--watch"],
    )
    assert result.exit_code == 0, result.output
    assert _contains_completion_marker(result.output), (
        "expected a [x] completion marker in the watch stream; got:\n" + result.output[-2000:]
    )


def test_maintenance_dataintegrity_run_watch_completes(
    monkeypatch: pytest.MonkeyPatch, local_url: str, local_pat: str | None
) -> None:
    """`d2w maintenance dataintegrity run --watch` kicks off + watches to completion."""
    _setup_env(monkeypatch, local_url, local_pat)
    # Pick the smallest-scope check DHIS2 ships so this runs quickly.
    # `orgunits_invalid_geometry` returns within ~1 s on the seeded fixture.
    result = CliRunner().invoke(
        build_app(),
        [
            "maintenance",
            "dataintegrity",
            "run",
            "orgunits_invalid_geometry",
            "--watch",
        ],
    )
    assert result.exit_code == 0, result.output
    assert _contains_completion_marker(result.output), (
        "expected a [x] completion marker; got:\n" + result.output[-2000:]
    )


def test_maintenance_task_watch_by_explicit_ref(
    monkeypatch: pytest.MonkeyPatch, local_url: str, local_pat: str | None
) -> None:
    """`d2w maintenance task watch <type> <uid>` follows a pre-existing task ref.

    Kicks off a dataintegrity run WITHOUT `--watch` to get the raw
    JobConfigurationWebMessage; extracts `jobType` + `id`; then feeds that
    tuple into `task watch` as if the caller had the UID from a separate
    request.
    """
    _setup_env(monkeypatch, local_url, local_pat)
    runner = CliRunner()

    kickoff = runner.invoke(
        build_app(),
        [
            "--json",
            "maintenance",
            "dataintegrity",
            "run",
            "orgunits_invalid_geometry",
        ],
    )
    assert kickoff.exit_code == 0, kickoff.output
    # `--json` emits the typed WebMessageResponse envelope. `response.jobType`
    # + `response.id` is the ref we want.
    json_body = kickoff.output[kickoff.output.index("{") :]
    envelope = json.loads(json_body)
    response = envelope.get("response") or {}
    job_type = response.get("jobType")
    task_uid = response.get("id")
    assert job_type and task_uid, f"no task ref in envelope: {envelope!r}"
    assert re.match(r"^[A-Za-z0-9]{11}$", task_uid), f"unexpected uid shape: {task_uid}"

    watch = runner.invoke(
        build_app(),
        ["maintenance", "task", "watch", job_type, task_uid, "--interval", "0.5", "--timeout", "120"],
    )
    assert watch.exit_code == 0, watch.output
    assert _contains_completion_marker(watch.output), (
        "task watch must render a [x] completion marker; got:\n" + watch.output[-2000:]
    )

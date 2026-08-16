"""Unit tests for `infra/scripts/verify_examples.py`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rich.console import Console

_SCRIPTS = Path(__file__).resolve().parents[4] / "infra" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verify_examples import (  # noqa: E402 — path-prepend intentional
    SKIP_BY_DEFAULT,
    ExampleResult,
    discover_examples,
    render_summary,
)


def test_discover_examples_returns_cli_client_mcp() -> None:
    """Discovery yields files under every existing surface."""
    paths = discover_examples("v42")
    assert paths, "expected at least one example in the repo"
    surfaces = {p.parent.name for p in paths}
    # The workspace always ships all three surfaces; make the test tolerant
    # in case one is empty on an oddly-pruned checkout.
    assert surfaces.issubset({"cli", "client", "mcp"})
    # _runner.py and other helper underscore-files must be excluded.
    assert all(not p.name.startswith("_") for p in paths)
    assert all(p.suffix in {".sh", ".py"} for p in paths)


def test_discover_examples_includes_the_fhir_group_on_every_major() -> None:
    """`examples/fhir/` is version-agnostic, so every major discovers it."""
    for version_key in ("v41", "v42", "v43"):
        discovered = {p.as_posix() for p in discover_examples(version_key)}
        assert any(path.endswith("examples/fhir/cli/generate.sh") for path in discovered)
        assert any(path.endswith("examples/fhir/client/consume_facade.py") for path in discovered)
        assert any(path.endswith("examples/fhir/mcp/validate.py") for path in discovered)


def test_discover_examples_takes_only_the_active_majors_variants() -> None:
    """A `examples/{surface}/v{N}/` directory belongs to that major's run and to no other."""
    v41 = {p.as_posix() for p in discover_examples("v41")}
    v43 = {p.as_posix() for p in discover_examples("v43")}
    assert any(path.endswith("examples/client/v41/oauth2_cid_field.py") for path in v41)
    assert not any("examples/client/v43/" in path for path in v41)
    assert any(path.endswith("examples/client/v43/removed_resources.py") for path in v43)
    assert not any("examples/client/v41/" in path for path in v43)


def test_skip_list_covers_known_interactive_flows() -> None:
    """The default skip list covers OIDC + browser + external-network examples.

    Skip-list keys are relative to `examples/`, so one set covers the common
    surfaces, the FHIR group, and the per-major variant directories alike.
    """
    assert "cli/profile_oidc_login.sh" in SKIP_BY_DEFAULT
    assert "client/oidc_login.py" in SKIP_BY_DEFAULT
    assert "cli/map_screenshot.sh" in SKIP_BY_DEFAULT
    assert "cli/route_register_and_run.sh" in SKIP_BY_DEFAULT
    assert "fhir/cli/serve.sh" in SKIP_BY_DEFAULT


def test_skip_list_entries_name_files_that_exist() -> None:
    """A skip entry naming a path that is gone would silently stop skipping anything."""
    examples = Path(__file__).resolve().parents[4] / "examples"
    missing = sorted(entry for entry in SKIP_BY_DEFAULT if not (examples / entry).exists())
    assert not missing, f"skip entries with no file: {missing}"


def test_render_summary_returns_zero_when_all_pass(capsys: pytest.CaptureFixture[str]) -> None:
    """All-green results → exit 0, table still renders."""
    results = [
        ExampleResult(path="examples/cli/whoami.sh", surface="cli", status="PASS", seconds=1.0),
        ExampleResult(path="examples/client/doctor.py", surface="client", status="PASS", seconds=0.5),
    ]
    rc = render_summary(results, console=Console(force_terminal=False, width=120))
    assert rc == 0
    captured = capsys.readouterr()
    assert "all green" in captured.out
    assert "TOTAL" in captured.out


def test_render_summary_returns_one_and_prints_tails_on_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """Any FAIL/TIMEOUT → exit 1, stderr tails get streamed."""
    results = [
        ExampleResult(path="examples/cli/pass.sh", surface="cli", status="PASS", seconds=1.0),
        ExampleResult(
            path="examples/cli/fail.sh",
            surface="cli",
            status="FAIL",
            seconds=2.0,
            stderr_tail="ERR: boom on line 3",
        ),
    ]
    rc = render_summary(results, console=Console(force_terminal=False, width=120))
    assert rc == 1
    captured = capsys.readouterr()
    assert "1 failure" in captured.out
    assert "examples/cli/fail.sh" in captured.out
    assert "ERR: boom on line 3" in captured.out


def test_render_summary_counts_every_status() -> None:
    """Per-surface counts add up to the right totals."""
    results = [
        ExampleResult(path="examples/cli/a.sh", surface="cli", status="PASS", seconds=0.1),
        ExampleResult(path="examples/cli/b.sh", surface="cli", status="FAIL", seconds=0.1),
        ExampleResult(path="examples/client/c.py", surface="client", status="PASS", seconds=0.1),
        ExampleResult(path="examples/client/d.py", surface="client", status="TIMEOUT", seconds=180.0),
        ExampleResult(path="examples/mcp/e.py", surface="mcp", status="SKIP", seconds=0.0),
    ]
    rc = render_summary(results, console=Console(force_terminal=False, width=120))
    assert rc == 1  # one FAIL + one TIMEOUT → failure exit


def test_example_result_is_frozen() -> None:
    """ExampleResult is frozen (ConfigDict(frozen=True)) so test fixtures can't mutate."""
    from pydantic import ValidationError  # noqa: PLC0415

    result = ExampleResult(path="x", surface="cli", status="PASS", seconds=1.0)
    with pytest.raises(ValidationError):
        result.status = "FAIL"

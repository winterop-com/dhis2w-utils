"""Run every non-interactive example + summarise PASS / FAIL / TIMEOUT / SKIP.

**Every example must be verified here.** Full execution coverage is the end
state: an example that this suite does not run is an example nobody knows
still works. An entry that genuinely cannot run in a batch pass earns a place
in `SKIP_BY_DEFAULT` with a stated reason, and that reason is the contract —
"needs a human", "blocks forever", "needs external network", not "it is slow
to look at".

Targets every script under:

- `examples/{cli,client,mcp}/` — the version-neutral set, run on whichever
  DHIS2 major the active profile points at.
- `examples/fhir/{cli,client,engine}/` — the FHIR surface. `dhis2w-fhir`,
  `dhis2w-fhir-serve` and `dhis2w-fhir-engine` are not per-version packages,
  so these run on every major from one copy.
- `examples/{cli,client,mcp}/v{N}/` — the variants that exist only for one
  DHIS2 major, run only when that major is the active one.

The active major is resolved exactly like the CLI / MCP runtime resolve their
plugin tree — `dhis2w_core.plugin.resolve_startup_version()`: the active
profile's `version` pin first, then the `DHIS2_VERSION` env var, then `v42`.
So a v41-pinned profile runs the common set plus `examples/client/v41/` and
leaves `examples/client/v43/` alone.

Files starting with `_` are skipped (helper modules like `_runner.py`).
Each example runs via `bash <path>` for `.sh` and `uv run python <path>`
for `.py`, inheriting the parent environment plus `DHIS2_PROFILE` so
profile-driven examples pick the right stack.

Two things the suite arranges before the loop, because a batch pass can afford
them once where a single example cannot:

- **One shared FHIR fixture.** Every `examples/fhir/client/` example stands up a
  scaffolded project and a `d2w fhir serve --live` facade of its own when the
  `D2W_FHIR_EXAMPLE_PROJECT` / `D2W_FHIR_EXAMPLE_FACADE` seams are unset. The
  suite stands one up, exports the seams, and stops the facade after the last
  example — so a pass boots one server rather than a dozen.
- **Environment-conditional skips.** An example reading a real secret or endpoint
  out of the environment runs when every variable it names is set and skips
  naming the missing ones otherwise. An unprovisioned machine is a fact about
  the machine, not a defect in the example.

Usage:
    uv run python infra/scripts/verify_examples.py            # follows the active profile
    DHIS2_VERSION=v43 uv run python infra/scripts/verify_examples.py   # only when no profile pin
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SURFACES = ("cli", "client", "mcp")
VERSION_KEYS = ("v41", "v42", "v43")

# The FHIR group is driven from the command line and from Python, and has no MCP
# examples — so its surfaces are the two shapes of caller plus the evaluation
# engine, which is its own package and its own kind of caller: expressions over
# FHIR-shaped data, with no DHIS2 in the picture.
FHIR_SURFACES = ("cli", "client", "engine")

# Examples that need Chromium (Playwright), a human-clicked OIDC login,
# external network dependencies, or run slow server-side jobs unsuitable
# for a batch pass. Skipped by default; `--include-browser` opts the full
# UI-driven set back in. Every entry states why it cannot be executed, and
# closing one of these gaps is a fix, not a nicety.
# Skip-list keys are paths relative to `examples/`.
SKIP_BY_DEFAULT: frozenset[str] = frozenset(
    {
        # --- UI-driven (opt in via --include-browser) -------------------
        # OIDC: opens a browser tab + runs a local redirect receiver,
        # needs a human to complete the login at the IdP.
        "cli/profile_oidc_login.sh",
        "client/oidc_login.py",
        # OIDC discovery probe: needs a real OIDC IdP at the target URL.
        # DHIS2 is an OIDC *client*, not a provider — pointing the probe
        # at the local DHIS2 always hits its login HTML. Run against
        # Keycloak / Auth0 / Google / etc. directly when needed.
        "cli/profile_oidc_config.sh",
        # Playwright browser workflows: open Chromium, drive UI.
        "cli/map_screenshot.sh",
        "cli/visualization_screenshot.sh",
        "client/oidc_playwright_login.py",
        # --- External network / non-deterministic -----------------------
        # Hits httpbin.org over the public internet.
        "cli/route_register_and_run.sh",
        # Creates a Route pointing at https://example.com/ — external network
        # egress out of the docker DHIS2 instance, not guaranteed in CI.
        "client/routes_run.py",
        # Same Route + external egress as the cli/client siblings.
        "mcp/route_register_and_run.py",
        # --- Slow server-side jobs --------------------------------------
        # Kicks `d2w maintenance refresh analytics --watch`; analytics
        # rebuilds legitimately take several minutes on a populated stack.
        "cli/maintenance.sh",
        # Scaffolds an IG, runs the dockerized SUSHI compile, then starts
        # `d2w fhir serve` as a background job and curls it. The compile
        # alone is minutes on a cold docker image, and the script binds a
        # port — neither belongs in a batch pass.
        "fhir/cli/serve.sh",
        # The same compile and the same bound port to fill the spool the drain
        # reads. The dry run writes nothing to the instance; every other forward
        # story commits, so `d2w fhir forward --import` writes data values.
        "fhir/cli/forward_dry_run.sh",
        "fhir/cli/forward_import.sh",
        # The overwrite and completeness stories carry the same compile, the
        # same bound port, and the same committing writes as forward_import.sh.
        "fhir/cli/forward_overwrites.sh",
        "fhir/cli/forward_completeness.sh",
        # The withdrawal story binds the same port and makes two committing writes
        # of its own: one creates an event in the instance, the other deletes it.
        "fhir/cli/withdraw.sh",
        # Creates three tracked entity types, a tracked entity attribute, three
        # registration programmes, and a tracked entity apiece on the instance,
        # then removes all of it - including a `d2w maintenance cleanup
        # tracked-entities` purge, which hard-removes every soft-deleted tracked
        # entity on the instance and not only this script's. Writes plus a
        # purge is not a batch pass.
        "fhir/cli/registers_many_types.sh",
        # `d2w fhir doctor` runs the whole chain — scaffold, generate,
        # dockerized compile, serve, capture, forward — in one command.
        # Minutes per run, for the same compile reason as its siblings.
        "fhir/cli/doctor_probe.sh",
        # Each doctor story is its own run of that whole chain, and
        # `--all-targets` runs it over every data set and every program.
        "fhir/cli/doctor_all_targets.sh",
        "fhir/cli/doctor_live_oracle.sh",
        "fhir/cli/doctor_report.sh",
        "fhir/cli/doctor_json.sh",
        # Same whole chain, and it needs a project directory holding a guide
        # that was generated and compiled at some earlier point to read.
        "fhir/cli/doctor_drift.sh",
        # Every `examples/fhir/client/` example stands its own fixture up —
        # `_fixture.py` scaffolds a project, builds the translation context off
        # the instance, and starts a `d2w fhir serve --live` facade it stops at
        # exit. So none of them is skipped: what used to need "a facade already
        # listening" or "a project with a spool" now brings its own.
        # --- Fixture gaps in the seed ----------------------------------
        # Outlier detection requires per-program data distributions the
        # 1-year Child Programme sample doesn't have enough volume for —
        # the CLI + library wrap the same endpoint, skip both.
        "cli/analytics_outlier_tracked_entities.sh",
        "client/analytics_outlier_tracked_entities.py",
        "mcp/analytics_outlier_tracked_entities.py",
    },
)

# Per-version skip overrides for examples that only fail on one major.
# Keyed by `v{N}` -> example paths relative to `examples/`.
SKIP_BY_VERSION: dict[str, frozenset[str]] = {
    "v43": frozenset(
        {
            # BUGS.md #36 — v43's full `POST /api/resourceTables/analytics`
            # job aborts with `column "yearly" does not exist` when there's
            # 2024 event data for `lxAQ7Zs9VYR` (Antenatal Care). The
            # `?skipPrograms=` workaround DHIS2 should honour is silently
            # ignored on v43. Analytics tables stay empty, so this example's
            # explicit "did analytics build?" probe correctly raises.
            "client/viz_multiline_by_province.py",
            # Same BUGS.md #36 — v43's event-analytics SQL emitter rejects
            # the 2024 event data the fixture carries. Both run green on
            # v41 and v42, which is why they live in the common set.
            "client/analytics_events_enrollments.py",
            "mcp/analytics_events_enrollments.py",
            # Same BUGS.md #36 one step downstream: the aborted analytics job
            # leaves the tables empty, so every analytics query answers
            # 409 "Dimension is present in query without any valid dimension
            # options: dx". Green on v41 and v42, where the refresh completes.
            "cli/query_eval.sh",
            "cli/query_run.sh",
        }
    ),
}

# Examples that read real secrets or endpoints from the environment. Each entry runs when
# every named variable is set and skips with the missing names stated otherwise, because an
# unprovisioned environment is a fact about the machine rather than a defect in the example.
# `make verify-examples` sources infra/home/credentials/.env.auth first, so a seeded checkout
# provides them all and nothing here is skipped.
SKIP_WHEN_ENVIRONMENT_MISSING: dict[str, tuple[str, ...]] = {
    "client/profile_pat_pure_client.py": ("DHIS2_URL", "DHIS2_PAT"),
    "client/profile_crud.py": ("DHIS2_PAT",),
    # The one FHIR engine example that reads DHIS2: it maps a seeded Child Programme
    # cohort into FHIR and scores a measure over it. Every other example in that
    # directory evaluates over inline data and needs nothing running.
    "fhir/engine/e2e_measure_from_dhis2.py": ("DHIS2_URL", "DHIS2_USERNAME", "DHIS2_PASSWORD"),
    # The `dhis2` posture checks a caller's own DHIS2 credentials against the instance, so the
    # example presents a real one — a caller's, never the facade's profile. The personal access
    # token is the same posture with no password on the wire.
    "fhir/cli/serve_auth_postures.sh": ("DHIS2_USERNAME", "DHIS2_PASSWORD", "DHIS2_PAT"),
}

DEFAULT_PROFILE = "local_basic"
# 300s headroom: some scripts (`options.sh`, `metadata_list_get.sh`,
# `metadata_export_import.sh`) run fine idle but balloon past 180s under
# post-refresh load — analytics table rebuilds + a fully-seeded Sierra
# Leone catalog mean list + export calls are not free. Override with
# `--timeout` when a specific run needs tighter or looser bounds.
DEFAULT_TIMEOUT_SECONDS = 300.0


class ExampleResult(BaseModel):
    """One example run's outcome — path + status + wall-clock."""

    model_config = ConfigDict(frozen=True)

    path: str
    surface: str
    status: str  # PASS / FAIL / TIMEOUT / SKIP
    seconds: float
    stderr_tail: str = ""


def _resolve_version_key() -> tuple[str, str]:
    """Return the active DHIS2 major (`v41|v42|v43`) and a human label for its source.

    Uses `dhis2w_core.plugin.resolve_startup_version()` so the example tree matches
    the plugin tree the example subprocesses load: profile pin first, then
    `DHIS2_VERSION` env, then the `v42` default.
    """
    from dhis2w_core.plugin import resolve_startup_version

    version_key = resolve_startup_version()
    try:
        from dhis2w_core.profile import resolve

        resolved = resolve()
    except Exception:  # noqa: BLE001 — source labelling must not crash the suite
        resolved = None
    if resolved is not None and resolved.profile.version is not None:
        return version_key, f"profile {resolved.name!r} pin"
    env_version = os.environ.get("DHIS2_VERSION", "").strip()
    if env_version:
        return version_key, f"DHIS2_VERSION={env_version!r} env"
    return version_key, "default"


def _examples_root() -> Path:
    """Return the `examples/` directory every example path is stated relative to."""
    return REPO_ROOT / "examples"


def _surface_directories(version_key: str) -> list[Path]:
    """Every directory holding examples for this run: the common set, the FHIR set, this major's variants."""
    root = _examples_root()
    directories = [root / surface for surface in SURFACES]
    directories += [root / "fhir" / surface for surface in FHIR_SURFACES]
    directories += [root / surface / version_key for surface in SURFACES]
    return directories


def discover_examples(version_key: str) -> list[Path]:
    """Return every example file this major runs, sorted by path.

    The common `examples/{cli,client,mcp}/` set and the version-agnostic
    `examples/fhir/` set run on every major. A `examples/{surface}/v{N}/`
    directory holds the examples that exist only for one major, so only the
    active one's variants are picked up — the other majors' variants are not
    skipped, they are not this run's examples at all.
    """
    paths: list[Path] = []
    for directory in _surface_directories(version_key):
        if not directory.exists():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            if entry.suffix in {".sh", ".py"}:
                paths.append(entry)
    return sorted(paths)


def _surface_of(path: Path) -> str:
    """Name the summary row an example belongs under: `cli`, `client`, `mcp`, or `fhir/<surface>`.

    A version-variant directory reports under its surface rather than under the
    major, because what a reader wants counted is how the CLI examples did.
    """
    parts = path.relative_to(_examples_root()).parts
    return f"fhir/{parts[1]}" if parts[0] == "fhir" else parts[0]


def _run_one(path: Path, *, profile: str, timeout_seconds: float) -> ExampleResult:
    """Invoke one example with the given profile + timeout; capture result."""
    surface = _surface_of(path)
    rel = path.relative_to(REPO_ROOT).as_posix()
    env = {**os.environ, "DHIS2_PROFILE": profile}
    cmd: list[str] = ["bash", str(path)] if path.suffix == ".sh" else ["uv", "run", "python", str(path)]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
            cwd=REPO_ROOT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ExampleResult(path=rel, surface=surface, status="TIMEOUT", seconds=time.monotonic() - start)
    elapsed = time.monotonic() - start
    if proc.returncode == 0:
        return ExampleResult(path=rel, surface=surface, status="PASS", seconds=elapsed)
    stderr = proc.stderr.decode(errors="replace").strip()
    stdout = proc.stdout.decode(errors="replace").strip()
    tail = "\n".join((stderr or stdout).splitlines()[-6:])
    return ExampleResult(path=rel, surface=surface, status="FAIL", seconds=elapsed, stderr_tail=tail)


def _stand_up_shared_fhir_fixture(
    examples: list[Path],
    skip: frozenset[str],
    console: Console,
) -> Callable[[], None] | None:
    """Stand the FHIR client examples' shared project and facade up once, for the whole suite.

    Every `examples/fhir/client/` example builds its own fixture when the two seams
    (`D2W_FHIR_EXAMPLE_PROJECT`, `D2W_FHIR_EXAMPLE_FACADE`) are unset - which in a batch pass
    means twelve examples each booting a `d2w fhir serve --live` of their own. This stands one
    up in this process and exports the seams, so every example reuses it, and hands back the
    call that stops the facade and clears the seams again once the loop is done. Seams already
    set are an operator's own fixture and are left alone, and a fixture that cannot build is
    reported plainly - each example then builds its own, which is the behaviour with no shared
    fixture at all. Either way the answer is `None`: there is nothing of this suite's to stop.

    Two postures are deliberately not shared. `served_facade(auth=...)` honours the facade seam
    for the open default posture only, so the two examples about authentication - one asking for
    `token`, one for `dhis2` - each start a guarded facade of their own. A server somebody else
    started has whatever posture they gave it, and asking an open one to prove a credential
    would read as a bug in the feature rather than in the fixture.
    """
    examples_root = _examples_root()
    wanted = any(
        path.relative_to(examples_root).as_posix().startswith("fhir/client/")
        and path.relative_to(examples_root).as_posix() not in skip
        for path in examples
    )
    if not wanted:
        return None
    fixture_directory = examples_root / "fhir" / "client"
    sys.path.insert(0, str(fixture_directory))
    try:
        import _fixture  # noqa: PLC0415

        if os.environ.get(_fixture.PROJECT_ENVIRONMENT_VARIABLE) or os.environ.get(
            _fixture.FACADE_ENVIRONMENT_VARIABLE
        ):
            return None
        project_root = _fixture.example_project()
        _fixture.conversion_context()
        facade = _fixture.served_facade()
        os.environ[_fixture.PROJECT_ENVIRONMENT_VARIABLE] = str(project_root)
        os.environ[_fixture.FACADE_ENVIRONMENT_VARIABLE] = facade
        console.print(f"shared FHIR fixture: project [cyan]{project_root}[/cyan], facade [cyan]{facade}[/cyan]")
    except Exception as error:  # noqa: BLE001 - the fallback is the point: each example builds its own
        console.print(f"[yellow]shared FHIR fixture unavailable ({error}); each example builds its own[/yellow]")
        return None
    finally:
        sys.path.remove(str(fixture_directory))

    def tear_down() -> None:
        """Stop the shared facade and clear the seams, so nothing outlives the loop that started it."""
        _fixture.stop_facades()
        os.environ.pop(_fixture.PROJECT_ENVIRONMENT_VARIABLE, None)
        os.environ.pop(_fixture.FACADE_ENVIRONMENT_VARIABLE, None)

    return tear_down


def run_suite(
    *,
    profile: str = DEFAULT_PROFILE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    include_browser: bool = False,
    extra_skip: frozenset[str] = frozenset(),
    console: Console | None = None,
) -> list[ExampleResult]:
    """Run every discovered example, stream per-example status lines, return results."""
    # Resolve version against the chosen profile (matches the DHIS2_PROFILE each
    # subprocess gets in `_run_one`), so the example tree tracks the profile pin.
    os.environ["DHIS2_PROFILE"] = profile
    version_key, version_source = _resolve_version_key()
    per_version_skip = SKIP_BY_VERSION.get(version_key, frozenset())
    skip = extra_skip | per_version_skip if include_browser else SKIP_BY_DEFAULT | extra_skip | per_version_skip
    console = console or Console()
    examples = discover_examples(version_key)
    console.print(
        f"running [bold]{len(examples)}[/bold] examples "
        f"([bold]{version_key}[/bold] from {version_source}, "
        f"profile=[cyan]{profile}[/cyan], timeout={int(timeout_seconds)}s, "
        f"skip-default={'on' if not include_browser else 'off'})",
    )
    tear_down_shared_fixture = _stand_up_shared_fhir_fixture(examples, skip, console)
    try:
        return _run_every_example(
            examples,
            skip=skip,
            profile=profile,
            timeout_seconds=timeout_seconds,
            console=console,
        )
    finally:
        if tear_down_shared_fixture is not None:
            tear_down_shared_fixture()


def _run_every_example(
    examples: list[Path],
    *,
    skip: frozenset[str],
    profile: str,
    timeout_seconds: float,
    console: Console,
) -> list[ExampleResult]:
    """Run the discovered examples in order, streaming one status line each, and return every outcome."""
    examples_root = _examples_root()
    results: list[ExampleResult] = []
    for path in examples:
        rel = path.relative_to(REPO_ROOT).as_posix()
        # Skip-list entries are relative to `examples/` (e.g.
        # `cli/profile_oidc_login.sh`, `fhir/cli/serve.sh`).
        rel_to_examples = path.relative_to(examples_root).as_posix()
        missing_environment = [
            name for name in SKIP_WHEN_ENVIRONMENT_MISSING.get(rel_to_examples, ()) if not os.environ.get(name)
        ]
        if rel_to_examples in skip:
            result = ExampleResult(path=rel, surface=_surface_of(path), status="SKIP", seconds=0.0)
        elif missing_environment:
            result = ExampleResult(
                path=rel,
                surface=_surface_of(path),
                status="SKIP",
                seconds=0.0,
                stderr_tail=f"environment not set: {', '.join(missing_environment)}",
            )
        else:
            result = _run_one(path, profile=profile, timeout_seconds=timeout_seconds)
        badge = {
            "PASS": "green",
            "FAIL": "red",
            "TIMEOUT": "yellow",
            "SKIP": "dim",
        }[result.status]
        reason = f"  [dim]({result.stderr_tail})[/dim]" if result.status == "SKIP" and result.stderr_tail else ""
        console.print(f"  [{badge}]{result.status:8s}[/{badge}] {result.seconds:6.2f}s  {result.path}{reason}")
        results.append(result)
    return results


def render_summary(results: list[ExampleResult], *, console: Console | None = None) -> int:
    """Print a per-surface summary table + per-failure tails. Return 0 iff every example passed."""
    console = console or Console()
    by_surface: dict[str, dict[str, int]] = {}
    for result in results:
        counts = by_surface.setdefault(result.surface, {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "SKIP": 0})
        counts[result.status] += 1
    table = Table(title=f"example verification summary ({len(results)} total)")
    table.add_column("surface", style="cyan")
    table.add_column("pass", justify="right", style="green")
    table.add_column("fail", justify="right", style="red")
    table.add_column("timeout", justify="right", style="yellow")
    table.add_column("skip", justify="right", style="dim")
    totals = {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "SKIP": 0}
    for surface, counts in sorted(by_surface.items()):
        table.add_row(
            surface,
            str(counts["PASS"]),
            str(counts["FAIL"]),
            str(counts["TIMEOUT"]),
            str(counts["SKIP"]),
        )
        for key in totals:
            totals[key] += counts[key]
    table.add_row(
        "TOTAL",
        str(totals["PASS"]),
        str(totals["FAIL"]),
        str(totals["TIMEOUT"]),
        str(totals["SKIP"]),
        style="bold",
    )
    console.print(table)
    failures = [r for r in results if r.status in {"FAIL", "TIMEOUT"}]
    if failures:
        console.print(f"\n[red bold]{len(failures)} failure(s)[/red bold]:")
        for result in failures:
            console.print(f"  [red]{result.status:8s}[/red] {result.path}")
            if result.stderr_tail:
                for line in result.stderr_tail.splitlines():
                    console.print(f"    [dim]{line}[/dim]")
        return 1
    console.print("[green bold]all green[/green bold]")
    return 0


def main() -> int:
    """CLI entry point — parse args, run suite, emit summary, exit with aggregated status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="DHIS2_PROFILE to pass through")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-example timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--include-browser",
        action="store_true",
        help="Also run OIDC / Playwright / external-network examples that are skipped by default.",
    )
    args = parser.parse_args()
    console = Console()
    results = run_suite(
        profile=args.profile,
        timeout_seconds=args.timeout,
        include_browser=args.include_browser,
        console=console,
    )
    return render_summary(results, console=console)


if __name__ == "__main__":
    sys.exit(main())

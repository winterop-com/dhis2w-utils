"""Run every non-interactive example + summarise PASS / FAIL / TIMEOUT / SKIP.

Targets every script under `examples/v{N}/{cli,client,mcp}/` for the active
DHIS2 major. The major is resolved exactly like the CLI / MCP runtime resolve
their plugin tree — `dhis2w_core.plugin.resolve_startup_version()`: the active
profile's `version` pin first, then the `DHIS2_VERSION` env var, then `v42`.
This keeps the example tree in lock-step with the plugin tree the example
subprocesses actually load, so a v41-pinned profile runs `examples/v41/...`.
Files starting with `_` are skipped (helper modules like `_runner.py`).
Each example runs via `bash <path>` for `.sh` and `uv run python <path>`
for `.py`, inheriting the parent environment plus `DHIS2_PROFILE` so
profile-driven examples pick the right stack.

Known-interactive scripts (OIDC login flows, Playwright browser captures,
external-network ones) are skipped by default because they block on human
input or unreliable dependencies. `--include-browser` opts browser-driven
entries back in.

Per-version split: each major has its own example tree so DHIS2-version-
specific imports (`from dhis2w_client.generated.v{N}.schemas import ...`)
and per-version examples (`v43_*` for v43-only features, etc.) live next
to the version they target. New examples land in the version dir(s) where
they apply; cross-version examples are duplicated, accepted as a
trade-off for in-tree discoverability.

Usage:
    uv run python infra/scripts/verify_examples.py            # follows the active profile
    DHIS2_VERSION=43 uv run python infra/scripts/verify_examples.py   # only when no profile pin
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Examples that need Chromium (Playwright), a human-clicked OIDC login,
# external network dependencies, or run slow server-side jobs unsuitable
# for a batch pass. Skipped by default; `--include-browser` opts the full
# UI-driven set back in.
# Skip-list keys are paths relative to the active version dir
# (`examples/v{N}/`), so the same set works across v41 / v42 / v43.
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
        "cli/dev_pat.sh",
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
# Keyed by `v{N}` -> example paths relative to `examples/v{N}/`.
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
        }
    ),
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


def _version_dir(version_key: str) -> Path:
    """Return `examples/{version_key}/` for the given DHIS2 major."""
    return REPO_ROOT / "examples" / version_key


def discover_examples(version_key: str) -> list[Path]:
    """Return every example file under `examples/{version_key}/{cli,client,mcp}/`, sorted by path.

    Each major has its own discovery pass so version-specific imports + examples
    stay isolated from each other.
    """
    paths: list[Path] = []
    base = _version_dir(version_key)
    if not base.exists():
        return paths
    for subdir in ("cli", "client", "mcp"):
        root = base / subdir
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            if entry.suffix in {".sh", ".py"}:
                paths.append(entry)
    return paths


def _run_one(path: Path, *, profile: str, timeout_seconds: float) -> ExampleResult:
    """Invoke one example with the given profile + timeout; capture result."""
    surface = path.parent.name
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
    version_dir = _version_dir(version_key)
    results: list[ExampleResult] = []
    for path in examples:
        rel = path.relative_to(REPO_ROOT).as_posix()
        # Skip-list entries are relative to the active version dir
        # (e.g. `cli/profile_oidc_login.sh`) so the same set works
        # uniformly across v41 / v42 / v43.
        rel_to_version = path.relative_to(version_dir).as_posix()
        if rel_to_version in skip:
            result = ExampleResult(path=rel, surface=path.parent.name, status="SKIP", seconds=0.0)
        else:
            result = _run_one(path, profile=profile, timeout_seconds=timeout_seconds)
        badge = {
            "PASS": "green",
            "FAIL": "red",
            "TIMEOUT": "yellow",
            "SKIP": "dim",
        }[result.status]
        console.print(f"  [{badge}]{result.status:8s}[/{badge}] {result.seconds:6.2f}s  {result.path}")
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

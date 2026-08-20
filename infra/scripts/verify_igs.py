"""Run every example IG project under `examples/fhir/igs/` + summarise PASS / FAIL / SKIP.

**Every guide in the catalog is verified here.** One project directory under
`examples/fhir/igs/` is one guide, and each is put through the same four steps,
in this order:

1. **refresh** - `d2w fhir init <dir> --refresh` must report nothing to write.
   The committed trees are scaffold-managed, so a scaffold that has moved on
   shows up here as a file the refresh would create, rewrite, or keep.
2. **validate** - `d2w fhir validate` over the instance the project names, run
   with `--no-fail` so the counts are read from the report rather than from the
   exit code. Every guide but the exhibit must carry no error on its own build
   path; the exhibit must carry at least one `template-hostile-name` error.
3. **generate** - `d2w fhir generate`. Every guide but the exhibit must succeed;
   the exhibit must be refused, by design, with a message naming the object.
4. **compile** - the project's own `make sushi`, which is SUSHI in docker. The
   exhibit has no FSH to compile, and skips. Every guide skips when docker is
   not available, with that stated as the reason.

The exhibit is `refused-names`: a selection deliberately carrying DHIS2 names
that abort the IG publisher's last pass. Its refusal is its pass.

Commands run through the workspace `d2w` on this interpreter's own `bin/`
directory, never through `uv run`: each guide is itself a `uv` project, so `uv
run` inside one would resolve that project's own environment instead of the
workspace it is being verified from.

Usage:
    uv run python infra/scripts/verify_igs.py               # every guide
    uv run python infra/scripts/verify_igs.py --only facility-mixed
    uv run python infra/scripts/verify_igs.py --no-compile  # skip the docker step
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Where the catalog lives; one sub-directory holding a `fhir.toml` is one guide.
IGS_ROOT = REPO_ROOT / "examples" / "fhir" / "igs"

#: The guides whose `d2w fhir generate` is expected to be refused, with the reason.
#: An entry here inverts the generate and validate assertions and skips the compile.
REFUSING_PROJECTS: dict[str, str] = {
    "refused-names": (
        "the selection deliberately carries DHIS2 names with '<', which abort the IG publisher's "
        "last pass, so generate refuses the run and there is no FSH to compile"
    ),
}

#: The docker image the scaffolded `make sushi` runs, built by the scaffolded `make setup`.
DOCKER_IMAGE = "fhir-ig"

#: The profile every guide is verified against unless `--profile` names another.
DEFAULT_PROFILE = "local_basic"

#: Per-step ceiling. A cold `make setup` is not counted against it; a SUSHI compile is.
DEFAULT_TIMEOUT_SECONDS = 900.0

#: The step names, in the order every guide runs them.
STEP_NAMES = ("refresh", "validate", "generate", "compile")

#: The Rich style each verdict is printed in, shared by the stream and the table.
_VERDICT_STYLES = {"PASS": "green", "FAIL": "red", "SKIP": "dim"}


class StepOutcome(BaseModel):
    """One step of one guide: what it was, how it went, how long it took, and what it found."""

    model_config = ConfigDict(frozen=True)

    step: str
    status: str
    seconds: float
    detail: str = ""


class IgOutcome(BaseModel):
    """One guide's run: its directory name and the outcome of each step, in order."""

    model_config = ConfigDict(frozen=True)

    slug: str
    steps: list[StepOutcome] = Field(default_factory=list)

    @property
    def status(self) -> str:
        """The guide's verdict: FAIL if any step failed, else PASS.

        A skipped step does not withhold the verdict. The exhibit's compile is skipped because
        its refusal is what it demonstrates, and every compile is skipped where docker is not
        available - in both cases the per-step column says so, and the summary line counts it.
        """
        return "FAIL" if any(step.status == "FAIL" for step in self.steps) else "PASS"

    def verdict_of(self, step_name: str) -> str:
        """The verdict of one named step, or an empty string when the guide never ran it."""
        for step in self.steps:
            if step.step == step_name:
                return step.status
        return ""


class CommandResult(BaseModel):
    """One subprocess invocation: its exit status and both of its streams, decoded."""

    model_config = ConfigDict(frozen=True)

    returncode: int
    stdout: str
    stderr: str

    @property
    def error_line(self) -> str:
        """The first `error:` line the command printed, which is how every `d2w` refusal reads."""
        for line in self.stderr.splitlines():
            if line.startswith("error:"):
                return line
        tail = self.stderr.strip() or self.stdout.strip()
        return tail.splitlines()[-1] if tail else "no output"


def discover_projects() -> list[Path]:
    """Every guide in the catalog, sorted by directory name - a directory holding a `fhir.toml`."""
    if not IGS_ROOT.is_dir():
        return []
    return sorted(entry for entry in IGS_ROOT.iterdir() if (entry / "fhir.toml").is_file())


def resolve_d2w() -> Path:
    """The `d2w` beside this interpreter - the workspace build, whatever directory a step runs in."""
    candidate = Path(sys.executable).with_name("d2w")
    if candidate.is_file():
        return candidate
    fallback = REPO_ROOT / ".venv" / "bin" / "d2w"
    if fallback.is_file():
        return fallback
    found = shutil.which("d2w")
    if found is None:
        raise typer.BadParameter("no `d2w` on this interpreter or on PATH - run `make install` first")
    return Path(found)


def run_command(command: list[str], *, cwd: Path, profile: str, timeout_seconds: float) -> CommandResult:
    """Invoke one command with the profile exported, capturing both streams and never raising."""
    environment = {**os.environ, "DHIS2_PROFILE": profile}
    try:
        completed = subprocess.run(  # noqa: S603 - every argument is built here, none is user text
            command,
            capture_output=True,
            timeout=timeout_seconds,
            env=environment,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=124, stdout="", stderr=f"timed out after {int(timeout_seconds)}s")
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout.decode(errors="replace"),
        stderr=completed.stderr.decode(errors="replace"),
    )


def check_refresh(project: Path, *, d2w: Path, profile: str, timeout_seconds: float) -> StepOutcome:
    """Assert the committed tree is what the current scaffold writes: a refresh has nothing to do."""
    from dhis2w_fhir.scaffold.schemas import ScaffoldReport

    started = time.monotonic()
    result = run_command(
        [str(d2w), "--json", "fhir", "init", str(project), "--refresh"],
        cwd=REPO_ROOT,
        profile=profile,
        timeout_seconds=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        return StepOutcome(step="refresh", status="FAIL", seconds=elapsed, detail=result.error_line)
    report = ScaffoldReport.model_validate_json(result.stdout)
    rewritten = report.created_files + report.refreshed_files + report.extended_files + report.diverged_files
    if rewritten:
        return StepOutcome(
            step="refresh",
            status="FAIL",
            seconds=elapsed,
            detail=f"the scaffold has moved on: {', '.join(sorted(rewritten))}",
        )
    return StepOutcome(
        step="refresh",
        status="PASS",
        seconds=elapsed,
        detail=f"{len(report.unchanged_files)} scaffold files unchanged",
    )


def check_validate(project: Path, *, d2w: Path, profile: str, timeout_seconds: float, refuses: bool) -> StepOutcome:
    """Record what validate found, asserting the build path is clean - or hostile, for the exhibit."""
    from dhis2w_fhir.validation.schemas import FhirValidationReport

    started = time.monotonic()
    result = run_command(
        [str(d2w), "--json", "fhir", "validate", "--no-fail", "--format", "md"],
        cwd=project,
        profile=profile,
        timeout_seconds=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        return StepOutcome(step="validate", status="FAIL", seconds=elapsed, detail=result.error_line)
    report = FhirValidationReport.model_validate_json(result.stdout)
    counts = (
        f"{report.object_count} objects swept, "
        f"{report.selection_error_count} selection error(s), "
        f"{report.selection_warning_count} warning(s), {report.selection_info_count} info(s)"
    )
    hostile = [
        finding
        for finding in report.findings
        if finding.scope == "selection" and finding.severity == "error" and finding.category == "template-hostile-name"
    ]
    if refuses:
        if not hostile:
            return StepOutcome(
                step="validate",
                status="FAIL",
                seconds=elapsed,
                detail=f"expected a template-hostile-name error on the build path; {counts}",
            )
        named = ", ".join(f"{finding.name!r} ({finding.uid})" for finding in hostile)
        return StepOutcome(step="validate", status="PASS", seconds=elapsed, detail=f"{counts}; names {named}")
    if report.selection_error_count:
        offenders = ", ".join(
            f"{finding.category} on {finding.name!r} ({finding.uid})"
            for finding in report.findings
            if finding.scope == "selection" and finding.severity == "error"
        )
        return StepOutcome(step="validate", status="FAIL", seconds=elapsed, detail=offenders)
    return StepOutcome(step="validate", status="PASS", seconds=elapsed, detail=counts)


def check_generate(project: Path, *, d2w: Path, profile: str, timeout_seconds: float, refuses: bool) -> StepOutcome:
    """Generate the guide's source, asserting success - or, for the exhibit, a refusal that names the object."""
    from dhis2w_fhir.service import GenerateFullReport

    started = time.monotonic()
    result = run_command(
        [str(d2w), "--json", "fhir", "generate"],
        cwd=project,
        profile=profile,
        timeout_seconds=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    if refuses:
        if result.returncode == 0:
            return StepOutcome(
                step="generate",
                status="FAIL",
                seconds=elapsed,
                detail="the run was expected to be refused and succeeded instead",
            )
        line = result.error_line
        if "carries '<'" not in line:
            return StepOutcome(
                step="generate",
                status="FAIL",
                seconds=elapsed,
                detail=f"refused for another reason: {line}",
            )
        return StepOutcome(step="generate", status="PASS", seconds=elapsed, detail=line.removeprefix("error: "))
    if result.returncode != 0:
        return StepOutcome(step="generate", status="FAIL", seconds=elapsed, detail=result.error_line)
    report = GenerateFullReport.model_validate_json(result.stdout)
    # Written plus unchanged, because a re-run rewrites nothing and the count of what the guide
    # holds is what a reader wants; the split between the two says only whether this was a re-run.
    files = sum(
        len(getattr(report, field).written_files) + getattr(report, field).unchanged_count
        for field in type(report).model_fields
    )
    return StepOutcome(step="generate", status="PASS", seconds=elapsed, detail=f"{files} files across 7 targets")


def check_compile(project: Path, *, profile: str, timeout_seconds: float, skip_reason: str) -> StepOutcome:
    """Compile the generated FSH with the project's own dockerized SUSHI target."""
    if skip_reason:
        return StepOutcome(step="compile", status="SKIP", seconds=0.0, detail=skip_reason)
    started = time.monotonic()
    result = run_command(
        ["make", "-C", str(project), "sushi"],
        cwd=REPO_ROOT,
        profile=profile,
        timeout_seconds=timeout_seconds,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-4:])
        return StepOutcome(step="compile", status="FAIL", seconds=elapsed, detail=tail)
    exported = next(
        (line.strip() for line in result.stdout.splitlines() if "Exported" in line and "FHIR resources" in line),
        "compiled",
    )
    return StepOutcome(step="compile", status="PASS", seconds=elapsed, detail=exported.removeprefix("info  "))


def prepare_compile(projects: list[Path], *, console: Console, profile: str, compile_enabled: bool) -> str:
    """Return the reason every compile skips, or an empty string once the docker image is ready."""
    if not compile_enabled:
        return "--no-compile was given"
    if shutil.which("docker") is None:
        return "docker is not installed on this machine"
    probe = run_command(
        ["docker", "image", "inspect", DOCKER_IMAGE], cwd=REPO_ROOT, profile=profile, timeout_seconds=60
    )
    if probe.returncode == 0:
        return ""
    if not projects:
        return "there is no project to build the SUSHI image from"
    console.print(f"building the [cyan]{DOCKER_IMAGE}[/cyan] docker image (SUSHI + IG publisher); this runs once")
    built = run_command(["make", "-C", str(projects[0]), "setup"], cwd=REPO_ROOT, profile=profile, timeout_seconds=3600)
    if built.returncode != 0:
        return f"the {DOCKER_IMAGE} docker image could not be built - run `make -C {projects[0]} setup` to see why"
    return ""


def verify_project(
    project: Path,
    *,
    d2w: Path,
    profile: str,
    timeout_seconds: float,
    compile_skip_reason: str,
    console: Console,
) -> IgOutcome:
    """Run every step of one guide in order, streaming a line per step as it finishes."""
    slug = project.name
    refusal_reason = REFUSING_PROJECTS.get(slug, "")
    refuses = bool(refusal_reason)
    steps = [
        check_refresh(project, d2w=d2w, profile=profile, timeout_seconds=timeout_seconds),
        check_validate(project, d2w=d2w, profile=profile, timeout_seconds=timeout_seconds, refuses=refuses),
        check_generate(project, d2w=d2w, profile=profile, timeout_seconds=timeout_seconds, refuses=refuses),
        check_compile(
            project,
            profile=profile,
            timeout_seconds=timeout_seconds,
            skip_reason=refusal_reason or compile_skip_reason,
        ),
    ]
    for step in steps:
        style = _VERDICT_STYLES[step.status]
        detail = f"  [dim]{_one_line(step.detail)}[/dim]" if step.detail else ""
        console.print(
            f"  [{style}]{step.status:4s}[/{style}] {step.seconds:6.2f}s  {slug}/{step.step}{detail}",
            highlight=False,
            soft_wrap=True,
        )
    return IgOutcome(slug=slug, steps=steps)


def _one_line(detail: str, limit: int = 96) -> str:
    """One streamable line of a step's detail; the failure listing below prints the whole of it."""
    collapsed = " ".join(detail.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}..."


def render_summary(outcomes: list[IgOutcome], *, console: Console) -> int:
    """Print the per-guide table and the one summary line. Return 0 iff no step failed."""
    table = Table(title=f"IG catalog verification ({len(outcomes)} guides)")
    table.add_column("guide", style="cyan")
    for step_name in STEP_NAMES:
        table.add_column(step_name, justify="center")
    table.add_column("verdict", justify="center")
    for outcome in outcomes:
        cells = []
        for step_name in STEP_NAMES:
            verdict = outcome.verdict_of(step_name)
            style = _VERDICT_STYLES.get(verdict, "dim")
            cells.append(f"[{style}]{verdict or '-'}[/{style}]")
        style = _VERDICT_STYLES[outcome.status]
        table.add_row(outcome.slug, *cells, f"[{style}]{outcome.status}[/{style}]")
    console.print(table)

    steps = [step for outcome in outcomes for step in outcome.steps]
    passed = sum(1 for step in steps if step.status == "PASS")
    failed = sum(1 for step in steps if step.status == "FAIL")
    skipped = sum(1 for step in steps if step.status == "SKIP")
    console.print(
        f"{len(outcomes)} guides, {len(steps)} steps: {passed} passed, {failed} failed, {skipped} skipped",
        style="bold red" if failed else "bold green",
    )
    if not failed:
        return 0
    console.print(f"\n[red bold]{failed} failing step(s)[/red bold]:")
    for outcome in outcomes:
        for step in outcome.steps:
            if step.status == "FAIL":
                console.print(f"  [red]{outcome.slug}/{step.step}[/red]")
                for line in step.detail.splitlines():
                    console.print(f"    [dim]{line}[/dim]")
    return 1


def main(
    profile: Annotated[str, typer.Option("--profile", help="DHIS2 profile every guide is verified against.")] = (
        DEFAULT_PROFILE
    ),
    timeout_seconds: Annotated[
        float, typer.Option("--timeout", help="Per-step ceiling in seconds; a cold image build is exempt.")
    ] = DEFAULT_TIMEOUT_SECONDS,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Verify one guide by directory name (repeatable); default is all of them."),
    ] = None,
    compile_enabled: Annotated[
        bool, typer.Option("--compile/--no-compile", help="Run each project's dockerized SUSHI compile.")
    ] = True,
) -> None:
    """Verify every example IG project: refresh, validate, generate, and compile each one."""
    console = Console()
    d2w = resolve_d2w()
    projects = discover_projects()
    if only:
        wanted = set(only)
        unknown = sorted(wanted - {project.name for project in projects})
        if unknown:
            raise typer.BadParameter(f"no guide named {', '.join(unknown)} under {IGS_ROOT}")
        projects = [project for project in projects if project.name in wanted]
    if not projects:
        console.print(f"[red]no guide with a fhir.toml under {IGS_ROOT}[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"verifying [bold]{len(projects)}[/bold] guides "
        f"(profile=[cyan]{profile}[/cyan], d2w=[cyan]{d2w}[/cyan], timeout={int(timeout_seconds)}s)"
    )
    compile_skip_reason = prepare_compile(projects, console=console, profile=profile, compile_enabled=compile_enabled)
    outcomes = [
        verify_project(
            project,
            d2w=d2w,
            profile=profile,
            timeout_seconds=timeout_seconds,
            compile_skip_reason=compile_skip_reason,
            console=console,
        )
        for project in projects
    ]
    raise typer.Exit(code=render_summary(outcomes, console=console))


if __name__ == "__main__":
    typer.run(main)

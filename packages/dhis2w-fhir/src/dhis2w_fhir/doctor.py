"""The instance conformance runner behind `d2w fhir doctor`: run the whole toolchain, report what breaks.

Doctor scaffolds a throwaway project against the ambient DHIS2 profile, generates the IG source
from that instance, compiles it when a compiler is on the machine, serves it in process, captures a
synthetic corpus through the served endpoint, drains that corpus at the instance under validate-only
mode, and finally lets the instance judge the served resources object by object. Every phase reports
one typed result, and a failure never stops a phase that does not depend on it.

The direction of judgement is the whole point of the oracle phase: the DHIS2 instance is the
authority and the served output is what is on trial, never the reverse. A mismatch is a fact about
this toolchain against this instance, stated with the field path it was found on.

CLI-only, the way `d2w profile` is. A run writes a project tree, shells out to a compiler, posts a
corpus through an in-process server, and reads a whole instance - a write-heavy orchestration with
no read-only shape an MCP tool could honestly advertise.
"""

from __future__ import annotations

import asyncio
import json
import random
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
from dhis2w_client.errors import Dhis2ClientError
from dhis2w_core.client_context import open_client
from pydantic import BaseModel, ConfigDict

from dhis2w_fhir import service
from dhis2w_fhir.config import FhirProject, UnknownFhirConfigKeyError, load_project, write_fhir_config
from dhis2w_fhir.foundation import CAPTURE_SERVER_READ_RESOURCE_TYPES
from dhis2w_fhir.names import code_or_uid, flatten_whitespace, page_string, pascal
from dhis2w_fhir.scaffold.schemas import DEFAULT_SUSHI_TIMEOUT_SECONDS, InitOptions
from dhis2w_fhir.service import GenerationProfile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dhis2w_client import Dhis2Client
    from dhis2w_core.progress import ProgressReporter

    from dhis2w_fhir.service import ForwardReport


class DoctorPhase(StrEnum):
    """The phases of one doctor run, in the order they execute."""

    CONNECT = "connect"
    SCAFFOLD = "scaffold"
    GENERATE = "generate"
    COMPILE = "compile"
    VALIDATE = "validate"
    SERVE = "serve"
    CAPTURE = "capture"
    FORWARD = "forward"
    ORACLE = "oracle"


class DoctorOutcome(StrEnum):
    """What one phase concluded, which is what the verdict and the exit code are read off."""

    #: The phase ran and found nothing worth acting on.
    PASSED = "pass"

    #: The phase ran and found something that degrades the result without breaking it.
    WARNED = "warn"

    #: The phase ran and found something broken. A run holding one of these exits 1.
    FAILED = "fail"

    #: The phase did not run because this machine or this invocation does not offer what it needs.
    SKIPPED = "skipped"

    #: The phase did not run because an earlier phase it is built on did not produce its input.
    BLOCKED = "blocked"


#: The phases in execution order, and how many steps a run announces.
DOCTOR_PHASE_ORDER: tuple[DoctorPhase, ...] = tuple(DoctorPhase)
DOCTOR_STEPS = len(DOCTOR_PHASE_ORDER)

#: How many oracle samples each family is judged on unless `--samples` says otherwise.
DEFAULT_ORACLE_SAMPLES = 5

#: The seed the oracle draws its per-family sample with. Fixed, so two runs against one unchanged
#: instance judge the same objects and a mismatch is reproducible by re-running the command.
ORACLE_SAMPLE_SEED = 20260101

#: The seed the capture corpus is drawn from, offset by the form's position so no two forms of one
#: run are filled identically. Fixed for the same reason the oracle's is: a refusal has to replay.
CAPTURE_SEED_BASE = 4242

#: The ceiling a `$generate` seed stays under, mirroring the operation's own `integer` input bound.
_CAPTURE_SEED_MODULUS = 1_000_000

#: The order the corpus is captured in, by DHIS2 form kind. It is `FORWARD_TARGET_ORDER`'s reason
#: one step earlier: a tracker registration has to be in the spool before a stage of the same
#: program is generated, because the stage response answers against the enrollment it minted.
_CAPTURE_FORM_KIND_ORDER = ("tracker", "aggregate", "event", "tracker-event")

#: The basename the markdown report of one run is written under, inside the reports directory.
DOCTOR_REPORT_STEM = "fhir-doctor-report"

#: Which ancestor of a sampled assignment the probe publishes the registry from. Level 2 is the
#: first administrative division under the national root on every hierarchy this has been run
#: against, which makes it one district's worth of units: small enough that a conformance check is
#: not a build, deep enough that the forms it selected are assigned somewhere inside it.
PROBE_ROOT_LEVEL = 2

#: How deep the registry is taken when no assignment sits deep enough for a subtree to be chosen -
#: a flat hierarchy, or an instance whose forms are all assigned at the top of it.
PROBE_MAX_LEVEL = 2

#: The IG identity the throwaway project is scaffolded under. It is never published, so the
#: canonical is an example host and the publisher names the command that wrote it.
_PROBE_IG_ID = "dhis2.fhir.doctor"
_PROBE_CANONICAL = "http://example.org/fhir/doctor"
_PROBE_PUBLISHER = "d2w fhir doctor"

#: The prefix the auto-cleaned workspace directory is minted under.
_WORKSPACE_PREFIX = "d2w-fhir-doctor-"

#: The docker image the scaffold's `make setup` builds and `make sushi` runs the compiler out of.
#: Doctor runs it when it is already there and never builds it: pulling a JVM and a node toolchain
#: is a several-minute network operation, which is not something a conformance check may decide to do.
_SUSHI_DOCKER_IMAGE = "fhir-ig"

#: Where SUSHI writes the resources it compiled, relative to the IG directory.
_COMPILED_RESOURCES_RELATIVE_PATH = "fsh-generated/resources"

#: How many findings one phase contributes to the report before the rest are counted rather than named.
_MAX_PHASE_FINDINGS = 20

#: How many characters of a compiler's output the evidence line carries.
_COMPILER_OUTPUT_WIDTH = 400

#: How long the docker probe waits for an answer about whether the compiler image exists.
_DOCKER_PROBE_TIMEOUT_SECONDS = 30

#: How many UIDs one `id:in:[...]` filter carries when the oracle resolves a family against the instance.
_ORACLE_BATCH_SIZE = 100

#: The base URL the in-process capture client addresses the ASGI app under. Nothing binds a socket -
#: httpx needs an absolute base for relative paths and this is the name it uses for one.
_IN_PROCESS_BASE_URL = "http://fhir-doctor.invalid"

#: The read-set every capture server has to hold. `List` is left out: a project publishes one only
#: when a form's DHIS2 organisation-unit assignment narrows the registry, so its absence is a fact
#: about the selection rather than about the store.
_REQUIRED_READ_SET = tuple(
    resource_type for resource_type in CAPTURE_SERVER_READ_RESOURCE_TYPES if resource_type != "List"
)

#: What a run without a compiler is told about the store it is serving instead. The example
#: QuestionnaireResponses a project publishes are authored as FSH, so only a compiler produces them,
#: and `$generate` reads them to decide the optional elements a response of that form carries. The
#: registration form's incident date is the one that costs something: a program collecting one gets
#: no incident date in a generated response, and DHIS2 refuses that enrollment with E1023.
_LIVE_STORE_WITHOUT_EXAMPLES = (
    "the live builders publish no example responses, because a project's examples are authored as "
    "FSH and only a compiler produces them. `$generate` reads those examples to decide the optional "
    "elements it fills in, so a registration form whose DHIS2 program collects an incident date is "
    "generated without one and the forward phase sees DHIS2 refuse the enrollment with E1023. "
    "Install a FSH compiler, or run `make setup && make sushi` in a project, to grade that phase."
)

#: What a caller is told when the serve extra is not installed, in the words `d2w fhir serve` uses.
_SERVE_PACKAGE_MISSING = (
    "the serve, capture, and forward phases need the dhis2w-fhir-serve package. Install it with "
    "`uv add dhis2w-fhir-serve` or `pip install 'dhis2w-cli[serve]'`."
)


class DoctorFinding(BaseModel):
    """One thing a phase found: what object, what is wrong with it, and where on it."""

    model_config = ConfigDict(frozen=True)

    phase: DoctorPhase
    severity: Literal["error", "warning"]
    subject: str
    detail: str
    field_path: str | None = None
    """The path on the served resource a mismatch was found at, for the findings that have one."""


class DoctorPhaseResult(BaseModel):
    """The outcome of one phase: the verdict, the one line it is read by, and what it found."""

    model_config = ConfigDict(frozen=True)

    phase: DoctorPhase
    outcome: DoctorOutcome
    evidence: str
    reason: str | None = None
    """Why a phase did not run, stated on every SKIPPED and BLOCKED result."""

    findings: tuple[DoctorFinding, ...] = ()
    elapsed_seconds: float = 0.0

    @property
    def error_count(self) -> int:
        """How many of this phase's findings are broken rather than merely degraded."""
        return sum(1 for finding in self.findings if finding.severity == "error")


class DoctorOptions(BaseModel):
    """The dials one doctor run is invoked with."""

    model_config = ConfigDict(frozen=True)

    workspace: Path | None = None
    """Where the throwaway project is written. None mints a temporary directory."""

    keep: bool = False
    """Keep a minted temporary workspace instead of removing it when the run ends."""

    all_targets: bool = False
    """Scaffold empty selection tables, which selects every data set and every program."""

    live: bool = False
    """Run the oracle phase, where the instance judges the served resources object by object."""

    samples: int = DEFAULT_ORACLE_SAMPLES
    """How many resources per family the oracle deep-compares against the instance."""


class DoctorReport(BaseModel):
    """Everything one doctor run concluded: what it ran against, where it ran, and what each phase found."""

    model_config = ConfigDict(frozen=True)

    profile_name: str
    profile_origin: str
    base_url: str
    dhis2_version: str | None = None
    version_tree: str | None = None
    """The `v41` / `v42` / `v43` plugin tree the client bound after detecting the instance's version."""

    workspace: Path
    workspace_kept: bool
    generated_at: datetime
    options: DoctorOptions
    phases: tuple[DoctorPhaseResult, ...] = ()

    @property
    def failed_phases(self) -> tuple[DoctorPhaseResult, ...]:
        """Every phase that concluded the toolchain is broken against this instance."""
        return tuple(phase for phase in self.phases if phase.outcome is DoctorOutcome.FAILED)

    @property
    def findings(self) -> tuple[DoctorFinding, ...]:
        """Every finding of the run, in phase order."""
        return tuple(finding for phase in self.phases for finding in phase.findings)

    @property
    def counts_by_outcome(self) -> dict[str, int]:
        """How many phases reached each outcome - the shape the verdict line is written from."""
        counted = Counter(phase.outcome.value for phase in self.phases)
        return {outcome.value: counted.get(outcome.value, 0) for outcome in DoctorOutcome}

    @property
    def verdict_line(self) -> str:
        """The whole run in one line: the verdict word, then how many phases reached each outcome."""
        counts = self.counts_by_outcome
        tail = ", ".join(f"{counts[outcome.value]} {outcome.value}" for outcome in DoctorOutcome)
        verdict = "BROKEN" if self.failed_phases else "USABLE"
        return f"{verdict}: {tail}"


class PhaseOutcome(BaseModel):
    """One phase's verdict before it is recorded: what it concluded, the line it says so on, its findings."""

    model_config = ConfigDict(frozen=True)

    outcome: DoctorOutcome
    evidence: str
    findings: tuple[DoctorFinding, ...] = ()


def grade(phase: DoctorPhase, evidence: str, findings: Sequence[DoctorFinding]) -> PhaseOutcome:
    """Grade one phase off what it found: an error breaks it, a warning degrades it, nothing passes it."""
    if any(finding.severity == "error" for finding in findings):
        outcome = DoctorOutcome.FAILED
    elif findings:
        outcome = DoctorOutcome.WARNED
    else:
        outcome = DoctorOutcome.PASSED
    return PhaseOutcome(outcome=outcome, evidence=evidence, findings=_capped_findings(phase, findings))


def grade_capture(captured: Sequence[_CaptureOutcome]) -> PhaseOutcome:
    """Grade the capture phase: an endpoint refusing what it generated is broken, a form it cannot fill is not."""
    findings = [finding for outcome in captured for finding in outcome.findings]
    generated = sum(1 for outcome in captured if outcome.generated)
    accepted = sum(1 for outcome in captured if outcome.accepted)
    evidence = f"{len(captured):,} form(s), {generated:,} generated, {accepted:,} accepted as 201"
    return grade(DoctorPhase.CAPTURE, evidence, findings)


def grade_forward(report: ForwardReport) -> PhaseOutcome:
    """Grade the forward phase: a DHIS2 rejection is broken, a translator refusal is a note.

    Rejections roll up by cause rather than by response, because DHIS2 names one row per broken rule
    and two hundred responses breaking the same rule are one thing to fix. What a dry run could not
    check is left out of the findings entirely: an event whose enrollment this very run would have
    created is unverifiable rather than refused, and an import is what settles it.
    """
    findings = [
        DoctorFinding(
            phase=DoctorPhase.FORWARD,
            severity="error",
            subject=reason.error_code or "no DHIS2 error code",
            detail=f"{reason.responses} response(s): {reason.reason}",
        )
        for reason in report.rejection_reasons
    ]
    findings.extend(
        DoctorFinding(
            phase=DoctorPhase.FORWARD,
            severity="warning",
            subject=outcome.response_id,
            detail="; ".join(f"{refusal.category}: {refusal.reason}" for refusal in outcome.refusals)
            or "the translator would not read this response whole",
        )
        for outcome in report.refused
    )
    return grade(DoctorPhase.FORWARD, report.counts_line, findings)


def grade_oracle(families: Sequence[_FamilyOutcome]) -> PhaseOutcome:
    """Grade the oracle phase off what the instance said about each family it judged."""
    findings = [finding for family in families for finding in family.findings]
    return grade(DoctorPhase.ORACLE, "; ".join(family.summary for family in families), findings)


def resolve_doctor_profile() -> GenerationProfile:
    """The instance doctor runs against: `d2w -p`, then `DHIS2_PROFILE`, then a nearby project, then the default.

    The same resolution `d2w fhir validate` uses, and for the same reason: doctor's subject is an
    instance rather than a project, and it scaffolds the project it works in, so a `fhir.toml` in
    the working directory is a source of the profile name and nothing else.
    """
    return service.resolve_validation_context().generation


async def run_doctor(
    generation: GenerationProfile,
    options: DoctorOptions,
    *,
    reporter: ProgressReporter | None = None,
) -> DoctorReport:
    """Run every phase against the instance the profile names and report what each one concluded."""
    return await _DoctorRun(generation, options, reporter).execute()


def render_doctor_markdown(report: DoctorReport) -> str:
    """Render one run as the markdown report a handover is read from, phase table first, findings after."""
    lines = [
        "# fhir doctor report",
        "",
        f"- Profile: {report.profile_name} ({report.profile_origin})",
        f"- Instance: {report.base_url}",
        f"- DHIS2 version: {report.dhis2_version or 'not detected'} (plugin tree {report.version_tree or 'not bound'})",
        f"- Workspace: {report.workspace}{'' if report.workspace_kept else ' (removed when the run ended)'}",
        f"- Ran: {report.generated_at.isoformat(timespec='seconds')}",
        f"- Verdict: {report.verdict_line}",
        "",
        "## Phases",
        "",
        "| Phase | Outcome | Evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {phase.phase.value} | {phase.outcome.value} | {_markdown_cell(phase_evidence(phase))} |"
        for phase in report.phases
    )
    lines.append("")
    findings = report.findings
    if findings:
        lines.extend(
            [
                "## Findings",
                "",
                "| Phase | Severity | Subject | Where | What |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            f"| {finding.phase.value} | {finding.severity} | {_markdown_cell(finding.subject)} "
            f"| {_markdown_cell(finding.field_path or '')} | {_markdown_cell(finding.detail)} |"
            for finding in findings
        )
        lines.append("")
    else:
        lines.extend(["## Findings", "", "No phase found anything to report against this instance.", ""])
    return "\n".join(lines)


def phase_evidence(phase: DoctorPhaseResult) -> str:
    """The one line a phase is read by: its evidence, with the reason folded in when it did not run."""
    if phase.reason is None:
        return phase.evidence
    return f"{phase.evidence} ({phase.reason})" if phase.evidence else phase.reason


def _markdown_cell(text: str) -> str:
    """One value as a markdown table cell: pipes escaped, newlines flattened."""
    return " ".join(text.replace("|", "\\|").split())


class _PhaseProgress:
    """Announces the numbered phases of one run to a progress reporter, or to nothing when none was passed."""

    def __init__(self, reporter: ProgressReporter | None, total: int) -> None:
        """Store the reporter to announce to and how many phases the run holds."""
        self._reporter = reporter
        self._total = total
        self._index = 0
        self._label = ""

    def start(self, label: str, caption: str | None = None) -> None:
        """Open the next phase: `label` names it in its completion line, `caption` in the live display."""
        self._index += 1
        self._label = label
        if self._reporter is not None:
            self._reporter.step(self._index, self._total, caption or label)

    def tick(self, caption: str) -> None:
        """Re-caption the phase already running, with no durable line and no move of the counter."""
        if self._reporter is not None:
            self._reporter.step(self._index, self._total, caption)

    def complete(self, summary: str) -> None:
        """Close the phase already running with the one line it is reported by."""
        if self._reporter is not None:
            self._reporter.complete(self._index, self._total, self._label, summary)


class _ServedResource(BaseModel):
    """One resource as doctor reads it off the store, projected away from the server's own types.

    The oracle judges these rather than store entries, so the phases after `serve` depend on nothing
    the `dhis2w-fhir-serve` package defines and an install without the serve extra still type-checks.
    """

    model_config = ConfigDict(frozen=True)

    resource_type: str
    resource_id: str
    identity_system: str | None = None
    """The system of the resource's first identifier, which every builder writes as the DHIS2 UID slice."""

    identity_value: str | None = None
    code_system: str | None = None
    code_value: str | None = None
    title: str | None = None
    name: str | None = None
    form_kind: str | None = None
    """The DHIS2 form kind a Questionnaire publishes, off its own `code`; None on every other type."""

    concept_count: int = 0
    """How many concepts a CodeSystem publishes; zero on every other type."""


class _ServedTypeCount(BaseModel):
    """How many resources of one type the served store holds."""

    model_config = ConfigDict(frozen=True)

    resource_type: str
    count: int


class _InstanceObject(BaseModel):
    """One DHIS2 object as the oracle reads it back: the identity, the name, and the size of its child list."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str
    code: str | None = None
    child_count: int = 0


class _OracleFamily(BaseModel):
    """One family the oracle judges: which served resources it covers, and which DHIS2 collection answers for them."""

    model_config = ConfigDict(frozen=True)

    label: str
    resource_type: str
    identifier_segment: str
    api_path: str
    collection_key: str
    fields: str
    child_key: str | None = None
    """The list field a family's `child_count` is read off, when the family compares sizes at all."""


#: The four families the oracle judges, in the order the report reads them.
_ORACLE_FAMILIES: tuple[_OracleFamily, ...] = (
    _OracleFamily(
        label="organisation units",
        resource_type="Organization",
        identifier_segment="org-unit",
        api_path="/api/organisationUnits",
        collection_key="organisationUnits",
        fields="id,name,code",
    ),
    _OracleFamily(
        label="option sets",
        resource_type="CodeSystem",
        identifier_segment="option-set",
        api_path="/api/optionSets",
        collection_key="optionSets",
        fields="id,name,code,options[id]",
        child_key="options",
    ),
    _OracleFamily(
        label="data sets",
        resource_type="Questionnaire",
        identifier_segment="data-set",
        api_path="/api/dataSets",
        collection_key="dataSets",
        fields="id,name,code",
    ),
    _OracleFamily(
        label="programs",
        resource_type="Questionnaire",
        identifier_segment="program",
        api_path="/api/programs",
        collection_key="programs",
        fields="id,name,code",
    ),
)


#: The DHIS2 program types the probe picks one of each from, as `[generate]` selects them.
_EVENT_PROGRAM_TYPE = "WITHOUT_REGISTRATION"
_TRACKER_PROGRAM_TYPE = "WITH_REGISTRATION"

#: What one probe target is, which is which selection table it lands in.
ProbeTargetKind = Literal["data set", "event program", "tracker program"]


#: The organisation-unit property each probe kind's assignment is filtered on.
_ASSIGNMENT_FILTER_FIELDS: dict[str, str] = {
    "data set": "dataSets.id",
    "event program": "programs.id",
    "tracker program": "programs.id",
}


class _ProbeTarget(BaseModel):
    """One DHIS2 object the probe scaffold selected, and which selection table it lands in."""

    model_config = ConfigDict(frozen=True)

    kind: ProbeTargetKind
    uid: str
    name: str


class _ProbeAssignment(BaseModel):
    """One organisation unit a probe target is assigned to, or the absence of any."""

    model_config = ConfigDict(frozen=True)

    target: _ProbeTarget
    path: str = ""
    level: int = 0


class _ProbeSelection(BaseModel):
    """What one run generates from: the forms it kept, the ones it dropped, and the registry slice."""

    model_config = ConfigDict(frozen=True)

    targets: tuple[_ProbeTarget, ...] = ()
    dropped: tuple[_ProbeTarget, ...] = ()
    root: str | None = None
    max_level: int | None = None
    all_targets: bool = False


#: The selection `--all-targets` scaffolds: empty tables, which is how `fhir.toml` says "everything".
_ALL_TARGETS_SELECTION = _ProbeSelection(all_targets=True)


class _DoctorRun:
    """One doctor run: holds the state the phases hand each other and produces the report."""

    def __init__(
        self, generation: GenerationProfile, options: DoctorOptions, reporter: ProgressReporter | None
    ) -> None:
        """Store what the run was invoked with; nothing is opened or written until `execute` runs."""
        self._generation = generation
        self._options = options
        self._progress = _PhaseProgress(reporter, DOCTOR_STEPS)
        self._results: list[DoctorPhaseResult] = []
        self._workspace = _resolve_workspace(options)
        self._workspace_kept = options.workspace is not None or options.keep
        self._client: Dhis2Client | None = None
        self._project: FhirProject | None = None
        self._served: tuple[_ServedResource, ...] = ()
        self._store_counts: tuple[_ServedTypeCount, ...] = ()
        self._app: Any = None
        self._compiled = False
        self._dhis2_version: str | None = None
        self._version_tree: str | None = None

    async def execute(self) -> DoctorReport:
        """Run every phase in order and assemble the report, removing a minted workspace on every exit path."""
        try:
            async with AsyncExitStack() as stack:
                await self._run_phases(stack)
        finally:
            if not self._workspace_kept:
                shutil.rmtree(self._workspace, ignore_errors=True)
        return DoctorReport(
            profile_name=self._generation.name,
            profile_origin=self._generation.origin,
            base_url=self._generation.profile.base_url,
            dhis2_version=self._dhis2_version,
            version_tree=self._version_tree,
            workspace=self._workspace,
            workspace_kept=self._workspace_kept,
            generated_at=datetime.now(tz=UTC),
            options=self._options,
            phases=tuple(self._results),
        )

    async def _run_phases(self, stack: AsyncExitStack) -> None:
        """Open the client, then run every phase that its predecessors left something to run on."""
        if not await self._connect(stack):
            self._block_rest(DoctorPhase.CONNECT, "the instance never answered, so nothing downstream can run")
            return
        if not await self._scaffold():
            self._block_rest(DoctorPhase.SCAFFOLD, "no project was written, so nothing downstream has a project")
            return
        generated = await self._generate()
        await self._compile(generated=generated)
        await self._validate()
        served = await self._serve(stack) if generated else self._blocked_serve()
        await self._capture(stack, served=served)
        await self._forward(served=served)
        await self._oracle(served=served)

    async def _connect(self, stack: AsyncExitStack) -> bool:
        """Open the client, detect the instance's version, and say which plugin tree bound to it."""
        self._progress.start(DoctorPhase.CONNECT.value, f"connecting to {self._generation.profile.base_url}")
        started = time.perf_counter()
        try:
            self._client = await stack.enter_async_context(open_client(self._generation.profile))
        except (Dhis2ClientError, httpx.HTTPError) as error:
            self._record(
                DoctorPhase.CONNECT,
                DoctorOutcome.FAILED,
                _connection_failure(error),
                started,
            )
            return False
        self._dhis2_version = self._client.raw_version
        self._version_tree = self._client.version_key
        self._record(
            DoctorPhase.CONNECT,
            DoctorOutcome.PASSED,
            f"{self._generation.profile.base_url} is DHIS2 {self._dhis2_version}, "
            f"bound to the {self._version_tree} tree",
            started,
        )
        return True

    async def _scaffold(self) -> bool:
        """Write the throwaway project, selecting a coherent probe unless every target was asked for.

        Coherent means the registry publishes organisation units the selected forms are actually
        assigned to. A probe that picks three forms and then a slice of the hierarchy none of them
        may report in produces a guide nothing can be captured against, and every phase after it
        would then be reporting doctor's own arithmetic rather than the instance's behaviour.
        """
        self._progress.start(DoctorPhase.SCAFFOLD.value, "scaffolding a throwaway project")
        started = time.perf_counter()
        client = self._require_client()
        selection = _ALL_TARGETS_SELECTION
        if not self._options.all_targets:
            self._progress.tick("choosing a representative probe")
            selection = await _probe_selection(client)
        options = _probe_init_options(self._generation.name, selection)
        try:
            report = await service.init_project(self._workspace, options)
            self._project = _apply_registry_root(load_project(self._workspace), selection.root)
        except (OSError, LookupError, ValueError, UnknownFhirConfigKeyError) as error:
            self._record(DoctorPhase.SCAFFOLD, DoctorOutcome.FAILED, str(error), started)
            return False
        self._record(
            DoctorPhase.SCAFFOLD,
            DoctorOutcome.PASSED,
            f"{len(report.created_files)} file(s) into {self._workspace}; {_selection_summary(selection)}",
            started,
        )
        return True

    async def _generate(self) -> bool:
        """Run the full pipeline against the instance, keeping every note the run raised as a finding."""
        self._progress.start(DoctorPhase.GENERATE.value, "generating the IG source from the instance")
        started = time.perf_counter()
        project = self._require_project()
        try:
            report = await service.generate_full(self._generation.profile, project)
        except (Dhis2ClientError, httpx.HTTPError, LookupError, ValueError) as error:
            self._record(DoctorPhase.GENERATE, DoctorOutcome.FAILED, str(error), started)
            return False
        outcomes = [
            report.foundation,
            report.option_sets,
            report.categories,
            report.questionnaires,
            report.examples,
            report.organisation_units,
            report.pages,
        ]
        written = sum(len(outcome.written_files) for outcome in outcomes)
        notes = [note for outcome in outcomes for note in outcome.notes]
        findings = [
            DoctorFinding(
                phase=DoctorPhase.GENERATE,
                severity="warning",
                subject=note.category.value,
                detail=note.message,
            )
            for note in notes
        ]
        evidence = f"{written:,} file(s) across {len(outcomes)} target(s), {len(notes):,} note(s)"
        self._record_graded(DoctorPhase.GENERATE, grade(DoctorPhase.GENERATE, evidence, findings), started)
        return True

    async def _compile(self, *, generated: bool) -> None:
        """Compile the emitted FSH with a real compiler, or state that this machine offers none."""
        self._progress.start(DoctorPhase.COMPILE.value, "compiling the emitted FSH")
        started = time.perf_counter()
        if not generated:
            self._record(
                DoctorPhase.COMPILE,
                DoctorOutcome.BLOCKED,
                "",
                started,
                reason="the generate phase wrote no FSH to compile",
            )
            return
        command = _sushi_command()
        if command is None:
            self._record(
                DoctorPhase.COMPILE,
                DoctorOutcome.SKIPPED,
                "",
                started,
                reason=(
                    "no FSH compiler on this machine - neither `sushi` on PATH nor the "
                    f"`{_SUSHI_DOCKER_IMAGE}` docker image the scaffold's `make setup` builds. "
                    "A compile is evidence, not something every machine can be asked for"
                ),
            )
            return
        project = self._require_project()
        completed = await _run_compiler(command, project.ig_directory)
        compiled_count = len(list((project.ig_directory / _COMPILED_RESOURCES_RELATIVE_PATH).glob("*.json")))
        if completed.exit_code != 0 or compiled_count == 0:
            self._record(
                DoctorPhase.COMPILE,
                DoctorOutcome.FAILED,
                f"{completed.description} exited {completed.exit_code}: {completed.tail}",
                started,
            )
            return
        self._compiled = True
        self._record(
            DoctorPhase.COMPILE,
            DoctorOutcome.PASSED,
            f"{completed.description} compiled {compiled_count:,} resource(s)",
            started,
        )

    async def _validate(self) -> None:
        """Grade the instance's codes for FHIR-safety, folding the scope-aware severity rollup in."""
        self._progress.start(DoctorPhase.VALIDATE.value, "checking the instance's codes")
        started = time.perf_counter()
        project = self._require_project()
        try:
            report = await service.validate_codes(self._generation.profile, project.config.generate)
        except (Dhis2ClientError, httpx.HTTPError, LookupError, ValueError) as error:
            self._record(DoctorPhase.VALIDATE, DoctorOutcome.FAILED, str(error), started)
            return
        findings = _capped_findings(
            DoctorPhase.VALIDATE,
            [
                DoctorFinding(
                    phase=DoctorPhase.VALIDATE,
                    severity="error" if finding.scope == "selection" else "warning",
                    subject=f"{finding.resource_type} {finding.name} ({finding.uid})",
                    detail=f"{finding.category}: {finding.message}",
                )
                for finding in report.findings
                if finding.severity == "error"
            ],
        )
        evidence = (
            f"{report.object_count:,} object(s) swept; "
            f"{report.selection_error_count:,} selection error(s), "
            f"{report.selection_warning_count:,} selection warning(s), "
            f"{report.error_count:,} error(s) and {report.warning_count:,} warning(s) instance-wide"
        )
        if report.selection_error_count:
            outcome = DoctorOutcome.FAILED
        elif report.error_count or report.warning_count:
            outcome = DoctorOutcome.WARNED
        else:
            outcome = DoctorOutcome.PASSED
        self._record(DoctorPhase.VALIDATE, outcome, evidence, started, findings=findings)

    def _blocked_serve(self) -> bool:
        """Record the serve phase as blocked, because generation left no guide to serve."""
        self._progress.start(DoctorPhase.SERVE.value, "building the served store")
        self._record(
            DoctorPhase.SERVE,
            DoctorOutcome.BLOCKED,
            "",
            time.perf_counter(),
            reason="the generate phase wrote no guide to serve",
        )
        return False

    async def _serve(self, stack: AsyncExitStack) -> bool:
        """Build the served store in process - no socket, no subprocess - and verify the capture read-set loads.

        When no compiler ran there is nothing on disk to serve, so the live builders produce the same
        documents SUSHI would have compiled and doctor writes them into `ig/fsh-generated/resources`.
        That leaves one tree for the store, the capture phase, and the forward phase to read, so the
        three agree about what this project publishes however the run reached it.
        """
        self._progress.start(DoctorPhase.SERVE.value, "building the served store")
        started = time.perf_counter()
        project = self._require_project()
        try:
            from dhis2w_fhir_serve import ServeSettings, create_app
        except ImportError:
            self._record(DoctorPhase.SERVE, DoctorOutcome.SKIPPED, "", started, reason=_SERVE_PACKAGE_MISSING)
            return False
        source = "the compiled guide"
        try:
            if not self._compiled:
                materialised = await _materialise_live_store(project)
                source = f"the live builders ({materialised:,} document(s) written to disk)"
            application = create_app(ServeSettings(project_dir=self._workspace, live=False))
            await stack.enter_async_context(application.router.lifespan_context(application))
        except (
            Dhis2ClientError,
            httpx.HTTPError,
            LookupError,
            ValueError,
            OSError,
            UnknownFhirConfigKeyError,
        ) as error:
            self._record(DoctorPhase.SERVE, DoctorOutcome.FAILED, str(error), started)
            return False
        self._app = application
        self._served = _project_store(application.state.context.store)
        self._store_counts = _type_counts(self._served)
        held = {count.resource_type for count in self._store_counts}
        findings = [
            DoctorFinding(
                phase=DoctorPhase.SERVE,
                severity="warning",
                subject=resource_type,
                detail="the served store holds no resource of this type, which a capture client reads",
            )
            for resource_type in _REQUIRED_READ_SET
            if resource_type not in held
        ]
        if not self._compiled:
            findings.append(
                DoctorFinding(
                    phase=DoctorPhase.SERVE,
                    severity="warning",
                    subject="published example responses",
                    detail=_LIVE_STORE_WITHOUT_EXAMPLES,
                )
            )
        counts = ", ".join(f"{count.resource_type} {count.count:,}" for count in self._store_counts)
        evidence = f"{len(self._served):,} resource(s) from {source}: {counts}"
        self._record_graded(DoctorPhase.SERVE, grade(DoctorPhase.SERVE, evidence, findings), started)
        return True

    async def _capture(self, stack: AsyncExitStack, *, served: bool) -> None:
        """Generate one response per published form and post it back, holding the endpoint to its 201 invariant."""
        self._progress.start(DoctorPhase.CAPTURE.value, "capturing a generated corpus")
        started = time.perf_counter()
        if not served:
            self._record(
                DoctorPhase.CAPTURE,
                DoctorOutcome.BLOCKED,
                "",
                started,
                reason="no store was built, so there is no endpoint to capture through",
            )
            return
        forms = _capture_order([resource for resource in self._served if resource.resource_type == "Questionnaire"])
        if not forms:
            self._record(
                DoctorPhase.CAPTURE,
                DoctorOutcome.BLOCKED,
                "",
                started,
                reason="the served store publishes no form to generate a response to",
            )
            return
        transport = httpx.ASGITransport(app=self._app)
        http = await stack.enter_async_context(
            httpx.AsyncClient(transport=transport, base_url=_IN_PROCESS_BASE_URL, timeout=60.0)
        )
        captured: list[_CaptureOutcome] = []
        for index, form in enumerate(forms):
            self._progress.tick(f"capturing ({index + 1:,}/{len(forms):,})")
            captured.append(await _capture_one(http, form, index))
        self._record_graded(DoctorPhase.CAPTURE, grade_capture(captured), started)

    async def _forward(self, *, served: bool) -> None:
        """Drain the captured corpus at the instance under validate-only mode and roll the outcomes up."""
        self._progress.start(DoctorPhase.FORWARD.value, "draining the corpus at the instance")
        started = time.perf_counter()
        if not served:
            self._record(
                DoctorPhase.FORWARD,
                DoctorOutcome.BLOCKED,
                "",
                started,
                reason="nothing was captured, so there is no spool to drain",
            )
            return
        project = self._require_project()
        try:
            report = await service.forward_responses(self._generation.profile, project, import_responses=False)
        except (Dhis2ClientError, httpx.HTTPError, LookupError, ValueError) as error:
            self._record(DoctorPhase.FORWARD, DoctorOutcome.FAILED, str(error), started)
            return
        self._record_graded(DoctorPhase.FORWARD, grade_forward(report), started)

    async def _oracle(self, *, served: bool) -> None:
        """Let the instance judge the served resources: counts per family, then sampled deep-equals."""
        self._progress.start(DoctorPhase.ORACLE.value, "letting the instance judge the served resources")
        started = time.perf_counter()
        if not self._options.live:
            self._record(
                DoctorPhase.ORACLE,
                DoctorOutcome.SKIPPED,
                "",
                started,
                reason="not requested - pass --live to have the instance judge the served resources",
            )
            return
        if not served:
            self._record(
                DoctorPhase.ORACLE,
                DoctorOutcome.BLOCKED,
                "",
                started,
                reason="no store was built, so there is nothing for the instance to judge",
            )
            return
        client = self._require_client()
        project = self._require_project()
        identifier_base = f"{project.config.generate.identifier_system_base}/id"
        families: list[_FamilyOutcome] = []
        for family in _ORACLE_FAMILIES:
            self._progress.tick(f"judging {family.label}")
            families.append(await _judge_family(client, family, self._served, identifier_base, self._options.samples))
        self._record_graded(DoctorPhase.ORACLE, grade_oracle(families), started)

    def _require_client(self) -> Dhis2Client:
        """The connected client, which every phase after `connect` runs with."""
        if self._client is None:
            raise RuntimeError("the doctor run has no client; the connect phase did not complete")
        return self._client

    def _require_project(self) -> FhirProject:
        """The scaffolded project, which every phase after `scaffold` works in."""
        if self._project is None:
            raise RuntimeError("the doctor run has no project; the scaffold phase did not complete")
        return self._project

    def _record(
        self,
        phase: DoctorPhase,
        outcome: DoctorOutcome,
        evidence: str,
        started: float,
        *,
        reason: str | None = None,
        findings: tuple[DoctorFinding, ...] = (),
    ) -> None:
        """Close one phase: keep its result and narrate the line it is reported by."""
        result = DoctorPhaseResult(
            phase=phase,
            outcome=outcome,
            evidence=evidence,
            reason=reason,
            findings=findings,
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )
        self._results.append(result)
        self._progress.complete(f"{outcome.value} - {phase_evidence(result)}")

    def _record_graded(self, phase: DoctorPhase, graded: PhaseOutcome, started: float) -> None:
        """Close one phase off the verdict a grader already reached from what the phase found."""
        self._record(phase, graded.outcome, graded.evidence, started, findings=graded.findings)

    def _block_rest(self, after: DoctorPhase, reason: str) -> None:
        """Record every phase the run never reached as blocked, naming the phase that stopped it."""
        remaining = DOCTOR_PHASE_ORDER[DOCTOR_PHASE_ORDER.index(after) + 1 :]
        for phase in remaining:
            self._progress.start(phase.value)
            self._record(phase, DoctorOutcome.BLOCKED, "", time.perf_counter(), reason=reason)


class _CompilerRun(BaseModel):
    """What one compiler invocation did: which compiler, how it exited, and the tail of what it said."""

    model_config = ConfigDict(frozen=True)

    description: str
    exit_code: int
    tail: str


class _CaptureOutcome(BaseModel):
    """What one form contributed to the capture phase: whether it generated, whether it was accepted, and why not."""

    model_config = ConfigDict(frozen=True)

    generated: bool
    accepted: bool
    findings: tuple[DoctorFinding, ...] = ()


class _FamilyOutcome(BaseModel):
    """What one oracle family concluded: the line it is summarised by, and every mismatch it found."""

    model_config = ConfigDict(frozen=True)

    summary: str
    findings: tuple[DoctorFinding, ...] = ()


def _resolve_workspace(options: DoctorOptions) -> Path:
    """Where the throwaway project is written: the stated directory, or a fresh temporary one."""
    if options.workspace is not None:
        options.workspace.mkdir(parents=True, exist_ok=True)
        return options.workspace.resolve()
    return Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX)).resolve()


def _connection_failure(error: Exception) -> str:
    """One line saying why the instance never answered, in the words the CLI's error funnel uses."""
    if isinstance(error, httpx.HTTPError):
        return f"cannot reach the DHIS2 instance: {error or type(error).__name__}"
    return str(error) or type(error).__name__


async def _probe_targets(client: Dhis2Client) -> list[_ProbeTarget]:
    """Pick one data set, one event program, and one tracker program the instance actually holds.

    The first of each by name, so two runs against one unchanged instance scaffold the same project.
    A kind the instance holds none of contributes nothing and is stated as absent rather than faked.
    """
    data_sets = await client.resources.data_sets.list(fields="id,name", order=["name:asc"], page=1, page_size=1)
    targets = [
        _ProbeTarget(kind="data set", uid=model.id or "", name=model.name or "") for model in data_sets if model.id
    ]
    program_probes: tuple[tuple[str, ProbeTargetKind], ...] = (
        (_EVENT_PROGRAM_TYPE, "event program"),
        (_TRACKER_PROGRAM_TYPE, "tracker program"),
    )
    for program_type, kind in program_probes:
        programs = await client.resources.programs.list(
            fields="id,name",
            filters=[f"programType:eq:{program_type}"],
            order=["name:asc"],
            page=1,
            page_size=1,
        )
        targets.extend(
            _ProbeTarget(kind=kind, uid=model.id or "", name=model.name or "") for model in programs if model.id
        )
    return targets


async def _probe_selection(client: Dhis2Client) -> _ProbeSelection:
    """Choose the probe: three forms, and the slice of the hierarchy those forms may be reported in.

    DHIS2 decides where a form may be captured, through the organisation units it is assigned to, and
    a response naming a unit outside that assignment is one the instance refuses. So the registry
    slice is chosen from the assignments rather than guessed: one assigned unit is sampled, the
    subtree it sits in becomes the published registry, and a form with nothing assigned inside that
    subtree is dropped from the selection with the reason stated rather than published unreportable.
    """
    candidates = await _probe_targets(client)
    if not candidates:
        return _ProbeSelection()
    samples = [await _sample_assignment(client, target) for target in candidates]
    root = _registry_root(samples)
    if root is None:
        assigned = tuple(sample.target for sample in samples if sample.level > 0)
        dropped = tuple(sample.target for sample in samples if sample.level == 0)
        levels = [sample.level for sample in samples if sample.level > 0]
        return _ProbeSelection(
            targets=assigned,
            dropped=dropped,
            max_level=max(levels) if levels else PROBE_MAX_LEVEL,
        )
    kept: list[_ProbeTarget] = []
    dropped_targets: list[_ProbeTarget] = []
    for target in candidates:
        if await _assigned_under(client, target, root):
            kept.append(target)
        else:
            dropped_targets.append(target)
    return _ProbeSelection(targets=tuple(kept), dropped=tuple(dropped_targets), root=root)


async def _sample_assignment(client: Dhis2Client, target: _ProbeTarget) -> _ProbeAssignment:
    """One organisation unit the target is assigned to, shallowest path first, or nothing when it has none."""
    units = await client.resources.organisation_units.list(
        fields="id,path,level",
        filters=[f"{_ASSIGNMENT_FILTER_FIELDS[target.kind]}:eq:{target.uid}"],
        order=["path:asc"],
        page=1,
        page_size=1,
    )
    for unit in units:
        return _ProbeAssignment(target=target, path=unit.path or "", level=unit.level or 0)
    return _ProbeAssignment(target=target)


async def _assigned_under(client: Dhis2Client, target: _ProbeTarget, root: str) -> bool:
    """Whether the target is assigned to any organisation unit inside the published subtree."""
    units = await client.resources.organisation_units.list(
        fields="id",
        filters=[f"{_ASSIGNMENT_FILTER_FIELDS[target.kind]}:eq:{target.uid}", f"path:like:{root}"],
        page=1,
        page_size=1,
    )
    return bool(units)


def _registry_root(samples: Sequence[_ProbeAssignment]) -> str | None:
    """The subtree the registry publishes: the ancestor at the probe's own level of the first deep enough sample.

    None when no sampled unit sits that deep, which is how a flat hierarchy - or an instance whose
    forms are assigned at the top of it - says the registry has to be taken by level instead.
    """
    for sample in samples:
        segments = [segment for segment in sample.path.split("/") if segment]
        if len(segments) >= PROBE_ROOT_LEVEL:
            return segments[PROBE_ROOT_LEVEL - 1]
    return None


def _uids_of_kind(targets: Sequence[_ProbeTarget], kind: ProbeTargetKind) -> list[str]:
    """The UIDs of one probe kind, which is what its selection table is seeded with."""
    return [target.uid for target in targets if target.kind == kind]


def _probe_init_options(profile_name: str, selection: _ProbeSelection) -> InitOptions:
    """The scaffold inputs of one run: the probe's UIDs, or empty tables when every target was asked for."""
    name = pascal(_PROBE_IG_ID)
    return InitOptions(
        ig_id=_PROBE_IG_ID,
        canonical=_PROBE_CANONICAL,
        name=name,
        title=f"{name} Implementation Guide",
        publisher=_PROBE_PUBLISHER,
        profile=profile_name,
        sushi_timeout=DEFAULT_SUSHI_TIMEOUT_SECONDS,
        max_level=selection.max_level,
        data_set_ids=_uids_of_kind(selection.targets, "data set"),
        event_program_ids=_uids_of_kind(selection.targets, "event program"),
        tracker_program_ids=_uids_of_kind(selection.targets, "tracker program"),
    )


def _apply_registry_root(project: FhirProject, root: str | None) -> FhirProject:
    """Point the scaffolded project's registry at the chosen subtree, and read the project back.

    `d2w fhir init` seeds the depth of the registry but not which subtree it is taken from, so the
    root is written into the throwaway project's own `fhir.toml` afterwards. Doctor owns that file
    outright - it wrote it a moment ago into a directory it minted - so rewriting it costs nothing.
    """
    if root is None:
        return project
    generate = project.config.generate
    updated = project.config.model_copy(
        update={
            "generate": generate.model_copy(
                update={"organisation_units": generate.organisation_units.model_copy(update={"root": root})}
            )
        }
    )
    write_fhir_config(project.config_path, updated)
    return load_project(project.project_root)


def _selection_summary(selection: _ProbeSelection) -> str:
    """What the scaffold selected and why, as the evidence line states it."""
    if selection.all_targets:
        return "every data set and every program, at every organisation-unit level"
    if not selection.targets:
        return "no reportable data set and no reportable program - this instance offers the probe none"
    picked = ", ".join(
        f"{target.name} ({target.uid}) as the first {target.kind} by name" for target in selection.targets
    )
    registry = (
        f"organisation units under {selection.root}"
        if selection.root is not None
        else f"organisation units to level {selection.max_level}"
    )
    dropped = (
        ""
        if not selection.dropped
        else "; dropped "
        + ", ".join(
            f"{target.name} ({target.uid}), assigned to no organisation unit this registry publishes"
            for target in selection.dropped
        )
    )
    return f"{picked}; {registry}{dropped}"


def _sushi_command() -> list[str] | None:
    """The compiler this machine offers, in the order the scaffold's Makefile would reach for one.

    A `sushi` on PATH runs directly. Otherwise the scaffold's own docker image runs it, but only when
    that image is already built: building it pulls a JVM and a node toolchain, which is a decision a
    conformance check does not get to make on someone's machine.
    """
    if shutil.which("sushi") is not None:
        return ["sushi", "."]
    docker = shutil.which("docker")
    if docker is None or not _docker_image_present(docker):
        return None
    return [docker, "run", "--rm", "-v", "{ig}:/home/publisher/ig", _SUSHI_DOCKER_IMAGE, "sushi", "."]


def _docker_image_present(docker: str) -> bool:
    """Whether the scaffold's compiler image is already on this machine."""
    try:
        completed = subprocess.run(  # noqa: S603
            [docker, "image", "inspect", _SUSHI_DOCKER_IMAGE],
            capture_output=True,
            check=False,
            timeout=_DOCKER_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


async def _run_compiler(command: Sequence[str], ig_directory: Path) -> _CompilerRun:
    """Run one compiler over the IG directory and keep the tail of what it said."""
    resolved = [part.replace("{ig}", str(ig_directory)) for part in command]
    description = "sushi" if resolved[0].endswith("sushi") else f"docker {_SUSHI_DOCKER_IMAGE} sushi"
    process = await asyncio.create_subprocess_exec(
        *resolved,
        cwd=str(ig_directory),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=DEFAULT_SUSHI_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return _CompilerRun(
            description=description,
            exit_code=124,
            tail=f"no answer within {DEFAULT_SUSHI_TIMEOUT_SECONDS} seconds",
        )
    text = stdout.decode("utf-8", errors="replace").strip()
    return _CompilerRun(
        description=description,
        exit_code=process.returncode if process.returncode is not None else 0,
        tail=text[-_COMPILER_OUTPUT_WIDTH:],
    )


async def _materialise_live_store(project: FhirProject) -> int:
    """Write the documents the live builders produce into the compiled tree, and say how many landed.

    A machine with no FSH compiler still has to serve, capture, and forward against one guide. The
    live builders emit the served read-set as the very documents SUSHI compiles the FSH into, so
    writing them where SUSHI would have written them leaves every later phase reading one tree.

    Only the half SUSHI would have produced is written. The generate run already left the registry,
    the terminology, and their ConceptMaps in `ig/input/resources` as pre-built JSON, and both trees
    load into one store, so writing those again would serve every one of them twice.
    """
    from dhis2w_fhir_serve import ServeSettings  # noqa: PLC0415
    from dhis2w_fhir_serve.live import build_live_store  # noqa: PLC0415

    store = await build_live_store(project, ServeSettings(project_dir=project.project_root, live=True))
    predefined = _predefined_identities(project)
    directory = project.ig_directory / _COMPILED_RESOURCES_RELATIVE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    for entry in store.entries:
        if (entry.resource_type, entry.resource_id) in predefined:
            continue
        destination = directory / f"{entry.resource_type}-{entry.resource_id}.json"
        destination.write_text(json.dumps(entry.body, indent=2), encoding="utf-8")
        written += 1
    return written


def _predefined_identities(project: FhirProject) -> set[tuple[str, str]]:
    """Every `(resourceType, id)` the project already committed as pre-built JSON, which SUSHI never re-emits."""
    directory = project.resources_directory
    if not directory.is_dir():
        return set()
    identities: set[tuple[str, str]] = set()
    for path in directory.rglob("*.json"):
        try:
            body: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(body, dict) and isinstance(body.get("resourceType"), str) and isinstance(body.get("id"), str):
            identities.add((str(body["resourceType"]), str(body["id"])))
    return identities


def _project_store(store: Any) -> tuple[_ServedResource, ...]:
    """Project the served store onto the fields doctor judges, so no server type leaves the serve phase."""
    return tuple(
        _project_entry(entry.resource_type, entry.resource_id, entry.identifiers, entry.body) for entry in store.entries
    )


def _project_entry(
    resource_type: str, resource_id: str, identifiers: Sequence[Any], body: dict[str, Any]
) -> _ServedResource:
    """Project one served resource: its identity slices, its human names, and how many concepts it publishes."""
    identity = identifiers[0] if identifiers else None
    code = identifiers[1] if len(identifiers) > 1 else None
    concepts = body.get("concept")
    title = body.get("title")
    name = body.get("name")
    return _ServedResource(
        resource_type=resource_type,
        resource_id=resource_id,
        identity_system=identity.system if identity is not None else None,
        identity_value=identity.value if identity is not None else None,
        code_system=code.system if code is not None else None,
        code_value=code.value if code is not None else None,
        title=title if isinstance(title, str) else None,
        name=name if isinstance(name, str) else None,
        form_kind=_form_kind(body),
        concept_count=len(concepts) if isinstance(concepts, list) else 0,
    )


def _form_kind(body: dict[str, Any]) -> str | None:
    """The DHIS2 form kind a served Questionnaire publishes, off the D2FormType coding on its own `code`."""
    codings = body.get("code")
    if not isinstance(codings, list):
        return None
    for coding in codings:
        if isinstance(coding, dict) and isinstance(coding.get("code"), str):
            return str(coding["code"])
    return None


def _type_counts(resources: Sequence[_ServedResource]) -> tuple[_ServedTypeCount, ...]:
    """How many resources of each type the store holds, sorted by type."""
    counted = Counter(resource.resource_type for resource in resources)
    return tuple(_ServedTypeCount(resource_type=name, count=count) for name, count in sorted(counted.items()))


def _capture_order(forms: Sequence[_ServedResource]) -> list[_ServedResource]:
    """The order the corpus is captured in: a tracker program's registration form before its stages.

    A generated stage response answers against the tracked entity and the enrollment a spooled
    registration of the same program minted, and the spool is what the operation reads. Capturing a
    stage first would leave it inventing an enrollment no registration of the run ever creates, which
    the instance then refuses - a fact about the order, not about the instance.
    """
    return sorted(
        forms,
        key=lambda form: (
            _CAPTURE_FORM_KIND_ORDER.index(form.form_kind)
            if form.form_kind in _CAPTURE_FORM_KIND_ORDER
            else len(_CAPTURE_FORM_KIND_ORDER),
            form.resource_id,
        ),
    )


async def _capture_one(http: httpx.AsyncClient, form: _ServedResource, index: int) -> _CaptureOutcome:
    """Generate one response to one served form and post it back, grading whatever the endpoint answered."""
    subject = f"Questionnaire/{form.resource_id}"
    seed = (CAPTURE_SEED_BASE + index) % _CAPTURE_SEED_MODULUS
    generated = await http.get(f"/Questionnaire/{form.resource_id}/$generate", params={"seed": str(seed)})
    if generated.status_code != 200:
        return _CaptureOutcome(
            generated=False,
            accepted=False,
            findings=(
                DoctorFinding(
                    phase=DoctorPhase.CAPTURE,
                    severity="warning",
                    subject=subject,
                    detail=f"$generate answered {generated.status_code}: {_outcome_diagnostics(generated)}",
                ),
            ),
        )
    posted = await http.post(
        "/QuestionnaireResponse",
        content=generated.content,
        headers={"Content-Type": "application/fhir+json"},
    )
    if posted.status_code != 201:
        return _CaptureOutcome(
            generated=True,
            accepted=False,
            findings=(
                DoctorFinding(
                    phase=DoctorPhase.CAPTURE,
                    severity="error",
                    subject=subject,
                    detail=(
                        f"the endpoint refused what it had just generated with {posted.status_code}: "
                        f"{_outcome_diagnostics(posted)}"
                    ),
                ),
            ),
        )
    return _CaptureOutcome(generated=True, accepted=True)


def _outcome_diagnostics(response: httpx.Response) -> str:
    """What an OperationOutcome said, or the body as it arrived when it is not one."""
    try:
        body: Any = response.json()
    except ValueError:
        return response.text[:_COMPILER_OUTPUT_WIDTH]
    if not isinstance(body, dict):
        return str(body)[:_COMPILER_OUTPUT_WIDTH]
    issues = body.get("issue")
    if not isinstance(issues, list):
        return str(body)[:_COMPILER_OUTPUT_WIDTH]
    lines = [str(issue.get("diagnostics") or issue.get("code") or "") for issue in issues if isinstance(issue, dict)]
    return "; ".join(line for line in lines if line)[:_COMPILER_OUTPUT_WIDTH]


async def _judge_family(
    client: Dhis2Client,
    family: _OracleFamily,
    served: Sequence[_ServedResource],
    identifier_base: str,
    samples: int,
) -> _FamilyOutcome:
    """Have the instance judge one family: every served UID resolved, then a seeded sample deep-compared."""
    system = f"{identifier_base}/{family.identifier_segment}"
    members = [
        resource
        for resource in served
        if resource.resource_type == family.resource_type and resource.identity_system == system
    ]
    if not members:
        return _FamilyOutcome(summary=f"{family.label}: nothing served")
    # Two resources can name one DHIS2 object - the registry publishes a worked example of its own
    # root unit beside the unit - so the family is judged per object, on the resource of lowest id.
    by_uid: dict[str, _ServedResource] = {}
    for resource in sorted(members, key=lambda item: item.resource_id):
        if resource.identity_value:
            by_uid.setdefault(resource.identity_value, resource)
    resolved = await _resolve_instance_objects(client, family, sorted(by_uid))
    missing = sorted(uid for uid in by_uid if uid not in resolved)
    findings = [
        DoctorFinding(
            phase=DoctorPhase.ORACLE,
            severity="error",
            subject=f"{family.resource_type}/{by_uid[uid].resource_id}",
            detail=f"names DHIS2 {family.label[:-1]} {uid}, which this instance does not hold",
            field_path="identifier[0].value",
        )
        for uid in missing[:_MAX_PHASE_FINDINGS]
    ]
    sampled = _sample_uids(sorted(uid for uid in by_uid if uid in resolved), samples)
    for uid in sampled:
        findings.extend(_compare_resource(family, by_uid[uid], resolved[uid]))
    return _FamilyOutcome(
        summary=(
            f"{family.label}: {len(members):,} resource(s) over {len(by_uid):,} DHIS2 object(s), "
            f"{len(resolved):,} resolved, {len(sampled):,} deep-compared"
        ),
        findings=tuple(findings),
    )


def _sample_uids(uids: Sequence[str], samples: int) -> list[str]:
    """A deterministic sample of one family's UIDs - the same instance yields the same sample every run."""
    if samples <= 0 or not uids:
        return []
    if len(uids) <= samples:
        return list(uids)
    return sorted(random.Random(ORACLE_SAMPLE_SEED).sample(list(uids), samples))  # noqa: S311


async def _resolve_instance_objects(
    client: Dhis2Client, family: _OracleFamily, uids: Sequence[str]
) -> dict[str, _InstanceObject]:
    """Read one family's objects back off the instance, in `id:in:[...]` batches, keyed by UID."""
    resolved: dict[str, _InstanceObject] = {}
    for start in range(0, len(uids), _ORACLE_BATCH_SIZE):
        batch = uids[start : start + _ORACLE_BATCH_SIZE]
        raw = await client.get_raw(
            family.api_path,
            params={"fields": family.fields, "filter": f"id:in:[{','.join(batch)}]", "paging": "false"},
        )
        for entry in _collection(raw, family.collection_key):
            uid = str(entry.get("id") or "")
            if not uid:
                continue
            children = entry.get(family.child_key) if family.child_key else None
            code = entry.get("code")
            resolved[uid] = _InstanceObject(
                uid=uid,
                name=str(entry.get("name") or ""),
                code=code if isinstance(code, str) else None,
                child_count=len(children) if isinstance(children, list) else 0,
            )
    return resolved


def _collection(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """The list one DHIS2 collection endpoint answered with, at the HTTP boundary and nowhere past it."""
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _compare_resource(family: _OracleFamily, served: _ServedResource, instance: _InstanceObject) -> list[DoctorFinding]:
    """Judge one served resource against the DHIS2 object it derives from, naming the field of every mismatch."""
    subject = f"{family.resource_type}/{served.resource_id} <- {family.label[:-1]} {instance.uid}"
    findings: list[DoctorFinding] = []
    findings.extend(_compare_human_name(family, served, instance, subject))
    expected_code = code_or_uid(instance.code, instance.uid)
    if served.code_value is not None and served.code_value != expected_code:
        findings.append(
            DoctorFinding(
                phase=DoctorPhase.ORACLE,
                severity="error",
                subject=subject,
                detail=(
                    f"the instance says the code is {expected_code!r}, the served resource says {served.code_value!r}"
                ),
                field_path="identifier[1].value",
            )
        )
    if family.child_key is not None and served.concept_count != instance.child_count:
        findings.append(
            DoctorFinding(
                phase=DoctorPhase.ORACLE,
                severity="warning",
                subject=subject,
                detail=(
                    f"the instance holds {instance.child_count} {family.child_key}, "
                    f"the served resource publishes {served.concept_count} concept(s)"
                ),
                field_path="concept",
            )
        )
    return findings


def _compare_human_name(
    family: _OracleFamily, served: _ServedResource, instance: _InstanceObject, subject: str
) -> list[DoctorFinding]:
    """Judge the one element each family carries the DHIS2 name on, through that family's own text rules."""
    if family.resource_type == "Organization":
        expected = flatten_whitespace(instance.name)
        actual = served.name
        field_path = "name"
    else:
        # A CodeSystem's title is IG page furniture, so it carries the markup escaping every page
        # title takes; a Questionnaire's title is data and carries the DHIS2 name verbatim.
        escape = page_string if family.resource_type == "CodeSystem" else flatten_whitespace
        expected = escape(instance.name)
        actual = served.title
        field_path = "title"
    if actual is None or actual == expected:
        return []
    return [
        DoctorFinding(
            phase=DoctorPhase.ORACLE,
            severity="error",
            subject=subject,
            detail=f"the instance says the name is {expected!r}, the served resource says {actual!r}",
            field_path=field_path,
        )
    ]


def _capped_findings(phase: DoctorPhase, findings: Sequence[DoctorFinding]) -> tuple[DoctorFinding, ...]:
    """The first findings of one phase, with the remainder counted rather than named."""
    if len(findings) <= _MAX_PHASE_FINDINGS:
        return tuple(findings)
    remaining = len(findings) - _MAX_PHASE_FINDINGS
    tail = DoctorFinding(
        phase=phase,
        severity="warning",
        subject="(more)",
        detail=f"{remaining} further finding(s) of this phase are not listed individually",
    )
    return (*findings[:_MAX_PHASE_FINDINGS], tail)

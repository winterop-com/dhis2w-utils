"""The shared fixture every `examples/fhir/client/` example reads: one project, one context, one facade.

A FHIR example needs three things a reader should never have to assemble by hand - a project to
answer forms from, the translation context those answers are read through, and, for the examples
that send, a facade listening somewhere. This module stands all three up once and hands them to
every example, so each file is about its own one feature instead of about setup.

Three decisions worth knowing, because they are what makes the fixture cheap:

**The project is scaffolded, never generated.** `d2w fhir init` writes `fhir.toml` and the SUSHI
skeleton offline, in milliseconds, and nothing here opens a generated file: the facade runs
`--live` and the translation context is built off the instance. `d2w fhir generate` would write an
IG source tree no example reads, so the fixture does not pay for one.

**The translation context is built live, off the DHIS2 instance.** `fetch_live_artifacts` reads the
instance once and builds the Questionnaires, the terminology, and the published Locations the
translator needs - seconds. The other path, `load_compiled_artifacts`, reads a SUSHI-compiled guide
off disk, which means `make setup && make sushi` inside the project: docker, and minutes. Both
produce the same `CompiledArtifacts`, which is why a live-built form and a compiled one translate
the same; the live one is simply the one an example can afford.

**Both are cached.** The scaffolded project and the built context live in a directory under the
system temporary directory whose name carries a digest of what went into them - the DHIS2 instance
they were built against, the objects selected, and this file's own revision. Change any of those
and the next run builds a new one; change none and twenty-five examples share the first run's work.

Two environment variables let an operator supply their own instead:

- `D2W_FHIR_EXAMPLE_PROJECT` - an existing project root, used as-is. Nothing is scaffolded, and the
  forms are whatever that project's `fhir.toml` selects.
- `D2W_FHIR_EXAMPLE_FACADE` - a base URL already serving. Nothing is started, and nothing is
  stopped at exit.

Everything here raises `FixtureError` with one sentence naming what is missing and how to supply
it. `_runner.run_example` renders that sentence and exits 1, so no example ever answers a missing
DHIS2 instance with a traceback.
"""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from dhis2w_fhir import ConversionContext

PROJECT_ENVIRONMENT_VARIABLE = "D2W_FHIR_EXAMPLE_PROJECT"
"""Name a project root here and the fixture uses it as-is instead of scaffolding one."""

FACADE_ENVIRONMENT_VARIABLE = "D2W_FHIR_EXAMPLE_FACADE"
"""Name a base URL already serving here and the fixture never starts a facade of its own."""

#: Bumped whenever this file changes what it builds, so a stale cache is never read as a fresh one.
_FIXTURE_REVISION = 2

#: The DHIS2 objects the fixture's forms are generated from, one per form kind the capture contract has.
#:
#: Every one is in the seeded Sierra Leone fixture `make dhis2-run` boots. `Child Health` reports on
#: the default attribute category combination and `EPI Stock` on a non-default one, which is what
#: gives the two aggregate examples something different to say.
#:
#: `Child Health` carries a data element the seed names "Vitamin A given to < 5y", which
#: `d2w fhir generate` refuses to write into an IG - a raw `<` in a name takes the IG publisher's
#: build down in its last pass. That refusal is a build-time gate, and this fixture never builds:
#: it scaffolds a project and reads the instance through `fetch_live_artifacts`, which produces the
#: same documents in memory for a translator and a served facade to read. Serving a name is not
#: publishing a page, so the selection stands. `examples/fhir/igs/refused-names/` is the exhibit
#: for what generate does with the same data set.
_DATA_SET_IDS = ("BfMAe6Itzgt", "TuL8IOPzpHh")
_EVENT_PROGRAM_IDS = ("EVTsupVis01",)
_TRACKER_PROGRAM_IDS = ("IpHINAT79UW",)

#: The identity of the guide the fixture scaffolds. The canonical is what every extension url is
#: built from, so it is the one string an example's printed JSON shows over and over.
_IG_ID = "dhis2.fhir.exampledemo"
_IG_CANONICAL = "http://example.org/fhir/example-demo"
_IG_NAME = "ExampleDemo"
_IG_TITLE = "DHIS2 FHIR Example Demo"
_IG_PUBLISHER = "Example Org"

#: How deep the published organisation-unit registry goes. Level 4 is where the seeded instance
#: assigns its data sets and programs, so a response naming a facility names a published Location.
_MAXIMUM_ORGANISATION_UNIT_LEVEL = 4

#: The one district the registry covers, rather than the whole country.
#:
#: This is what makes the fixture affordable. Every organisation unit becomes a `Location` and an
#: `Organization`, and a live facade builds all of them at startup - the seeded instance holds 1334
#: units, and building them takes minutes that every example would wait through. Koinadugu holds 82,
#: including the facility the examples report at, so the registry is a real hierarchy of real units
#: and the wait is seconds. A project publishing a whole country changes one line of `fhir.toml`.
#: Gbenikoro MCHP sits inside it, which is the facility every example that reports somewhere names.
_ORGANISATION_UNIT_ROOT = "qhqAxPSTUXp"

#: The form ids of the five capture models, which under the default `id` naming are the DHIS2 UIDs.
_AGGREGATE_FORM_ID = "BfMAe6Itzgt"
_ATTRIBUTE_OPTION_COMBO_FORM_ID = "TuL8IOPzpHh"
_EVENT_FORM_ID = "EVTsupVis01"
_REGISTRATION_FORM_ID = "IpHINAT79UW"
_STAGE_FORM_ID = "A03MvHHogjR"
_PERSON_FORM_ID = "nEenWmSyUEp"

#: The file the built translation context is cached in, beside the project it was built for.
_CONTEXT_CACHE_FILENAME = "conversion-context.json"

#: The marker a completed scaffold writes, so a half-written cache directory is never reused.
_PROJECT_MARKER_FILENAME = ".fixture-complete"

#: Where a started facade's own output goes, so a failure has something to quote.
_FACADE_LOG_FILENAME = "facade-{auth}.log"

#: The posture a facade runs under unless an example asks for another one.
DEFAULT_FACADE_POSTURE = "none"

#: How long a started facade is given to answer `/metadata` before the fixture calls it a failure.
_FACADE_STARTUP_SECONDS = 180.0

#: How often the fixture asks a starting facade whether it is listening yet.
_FACADE_POLL_SECONDS = 0.5

#: How long a stopping facade is given to exit on its own before it is killed.
_FACADE_SHUTDOWN_SECONDS = 10.0

#: What a facade that is up answers `/metadata` with.
_HTTP_OK = 200

#: Guards the three lazily built singletons against two threads building them twice.
#:
#: Reentrant, because the three build on each other: a facade needs the project, and asking for the
#: project while holding the lock would otherwise be a thread waiting on itself.
_BUILD_LOCK = threading.RLock()

_facade_base_urls: dict[str, str] = {}
_facade_processes: list[subprocess.Popen[bytes]] = []


class FixtureError(RuntimeError):
    """Raised when the fixture cannot stand something up, carrying one sentence a reader can act on."""


def example_project() -> Path:
    """The generated project every example here reads, built once and reused."""
    override = os.environ.get(PROJECT_ENVIRONMENT_VARIABLE, "").strip()
    if override:
        directory = Path(override).expanduser().resolve()
        if not (directory / "fhir.toml").is_file():
            raise FixtureError(
                f"{PROJECT_ENVIRONMENT_VARIABLE} names {directory}, which holds no fhir.toml: "
                f"point it at a project root, or unset it and let the fixture scaffold one"
            )
        return directory
    with _BUILD_LOCK:
        return _scaffolded_project()


def conversion_context() -> ConversionContext:
    """The translation context read off that project - what translate_response needs."""
    from dhis2w_fhir import ConversionContext

    project_root = example_project()
    cache = project_root / _CONTEXT_CACHE_FILENAME
    with _BUILD_LOCK:
        if cache.is_file():
            return ConversionContext.model_validate_json(cache.read_text(encoding="utf-8"))
        context = _run_coroutine(_build_conversion_context(project_root))
        _write_atomically(cache, context.model_dump_json())
        return context


def capture_store() -> Any:
    """The served resource store, built off the instance - what the capture contract is checked against.

    The same store a `--live` facade holds, built here in-process so an example can run the check
    without a server and without a SUSHI compile. `load_compiled_store` reads
    `ig/fsh-generated/resources`, which this fixture deliberately never writes.
    """
    from dhis2w_fhir import load_project
    from dhis2w_fhir_serve.live import build_live_store, open_live_client
    from dhis2w_fhir_serve.settings import ServeSettings

    project_root = example_project()

    async def build() -> Any:
        project = load_project(project_root)
        settings = ServeSettings(project_dir=project_root, live=True)
        async with open_live_client(project, settings) as client:
            return await build_live_store(project, settings, client)

    with _BUILD_LOCK:
        return _run_coroutine(build())


def served_facade(*, auth: str = DEFAULT_FACADE_POSTURE) -> str:
    """Base URL of a facade serving that project, started on first use and stopped at exit.

    `auth` is the `[serve] auth` posture the facade runs under, and one facade is started per
    posture asked for. The default serves every caller, which is what all but one example wants;
    `auth="dhis2"` is the posture that reads the register as whoever asks, so the example about
    that gets a server of its own rather than bending everybody else's.

    An operator-supplied facade answers for the default posture only. A facade somebody else
    started has whatever posture they gave it, and asking a posture-none server to prove
    pass-through would fail in a way that reads as a bug in the feature.
    """
    override = os.environ.get(FACADE_ENVIRONMENT_VARIABLE, "").strip()
    if override and auth == DEFAULT_FACADE_POSTURE:
        return override.rstrip("/")
    with _BUILD_LOCK:
        if auth not in _facade_base_urls:
            _facade_base_urls[auth] = _start_facade(example_project(), auth)
        return _facade_base_urls[auth]


def aggregate_form_id() -> str:
    """The questionnaire id of the aggregate data set form, on the default attribute category combination."""
    return _AGGREGATE_FORM_ID


def attribute_option_combo_form_id() -> str:
    """The questionnaire id of the aggregate data set form whose attribute category combination is not the default."""
    return _ATTRIBUTE_OPTION_COMBO_FORM_ID


def event_form_id() -> str:
    """The questionnaire id of the event program form - a program without registration."""
    return _EVENT_FORM_ID


def registration_form_id() -> str:
    """The questionnaire id of the tracker program's registration form, which enrols the person it creates."""
    return _REGISTRATION_FORM_ID


def stage_form_id() -> str:
    """The questionnaire id of a tracker program stage form - one visit of an enrollment."""
    return _STAGE_FORM_ID


def person_form_id() -> str:
    """The questionnaire id of the tracked entity type form, which creates a person and enrols them in nothing."""
    return _PERSON_FORM_ID


def form_canonical(form_id: str) -> str:
    """The canonical url a response answering that form names, which is what `questionnaire` carries."""
    context = conversion_context()
    for canonical in context.forms:
        if canonical.rsplit("/", 1)[-1] == form_id:
            return canonical
    raise FixtureError(
        f"the fixture project publishes no form {form_id!r}: its forms are "
        f"{', '.join(sorted(canonical.rsplit('/', 1)[-1] for canonical in context.forms))}"
    )


def _scaffolded_project() -> Path:
    """Scaffold the fixture project into its cache directory, or return the one already there."""
    directory = _cache_directory()
    if (directory / _PROJECT_MARKER_FILENAME).is_file():
        return directory
    staging = Path(tempfile.mkdtemp(prefix="d2w-fhir-example-staging-", dir=directory.parent))
    try:
        _run_coroutine(_initialise_project(staging))
        (staging / _PROJECT_MARKER_FILENAME).write_text("", encoding="utf-8")
        try:
            staging.replace(directory)
        except OSError:
            # Another example's process finished its own scaffold first. Theirs is built from the
            # same inputs - that is what the digest in the directory name means - so theirs wins.
            shutil.rmtree(staging, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return directory


async def _initialise_project(directory: Path) -> None:
    """Write the scaffold `d2w fhir init` writes, selecting one form of every kind the contract has."""
    from dhis2w_fhir import FHIR_CONFIG_FILENAME, InitOptions, load_fhir_config, service, write_fhir_config

    await service.init_project(
        directory,
        InitOptions(
            ig_id=_IG_ID,
            canonical=_IG_CANONICAL,
            name=_IG_NAME,
            title=_IG_TITLE,
            publisher=_IG_PUBLISHER,
            max_level=_MAXIMUM_ORGANISATION_UNIT_LEVEL,
            data_set_ids=list(_DATA_SET_IDS),
            event_program_ids=list(_EVENT_PROGRAM_IDS),
            tracker_program_ids=list(_TRACKER_PROGRAM_IDS),
        ),
        force=True,
    )
    # `d2w fhir init` has a flag for the depth but not for the root, so the root is written straight
    # into the scaffolded `fhir.toml` - which is what an operator narrowing a real project edits too.
    config_path = directory / FHIR_CONFIG_FILENAME
    config = load_fhir_config(config_path)
    config.generate.organisation_units.root = _ORGANISATION_UNIT_ROOT
    write_fhir_config(config_path, config)


async def _build_conversion_context(project_root: Path) -> ConversionContext:
    """Read the instance once and assemble the context every response here is translated through."""
    from dhis2w_core.client_context import open_client
    from dhis2w_fhir import ConversionNaming, load_project, service
    from dhis2w_fhir.conversion.artifacts import bound_question_uids, build_project_context

    project = load_project(project_root)
    generation = _resolved_generation_profile(project)
    naming = ConversionNaming.from_config(project.config.generate, project.config.ig.canonical)
    async with open_client(generation.profile) as client:
        artifacts = await service.fetch_live_artifacts(client, project)
        bound = bound_question_uids(artifacts, naming)
        value_types = await _read_value_types(client, bound)
    return build_project_context(project, artifacts, value_types_by_data_element=value_types)


async def _read_value_types(client: Any, bound: Any) -> dict[str, str]:
    """Read the DHIS2 value type of every object the forms ask a question from, so `TRUE_ONLY` reads as itself.

    A Questionnaire states an R4 item type, and `BOOLEAN` and `TRUE_ONLY` share `#boolean` - so the
    value type is the one fact about a question the compiled guide cannot carry, and the caller
    supplies it. A link id names a data element on three form kinds and a tracked entity attribute
    on the other two, which is why both endpoints are read into the one table.
    """
    value_types: dict[str, str] = {}
    if bound.data_element_uids:
        data_elements = await client.resources.data_elements.list(
            fields="id,valueType", filters=[f"id:in:[{','.join(bound.data_element_uids)}]"], paging=False
        )
        for data_element in data_elements:
            if data_element.id and data_element.valueType is not None:
                value_types[data_element.id] = data_element.valueType.value
    if bound.tracked_entity_attribute_uids:
        attributes = await client.resources.tracked_entity_attributes.list(
            fields="id,valueType", filters=[f"id:in:[{','.join(bound.tracked_entity_attribute_uids)}]"], paging=False
        )
        for attribute in attributes:
            if attribute.id and attribute.valueType is not None:
                value_types[attribute.id] = attribute.valueType.value
    return value_types


def _start_facade(project_root: Path, auth: str) -> str:
    """Start `d2w fhir serve --live` on a free port, wait for it to answer, and register its shutdown."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [
        "uv",
        "run",
        "d2w",
        "fhir",
        "serve",
        str(project_root),
        "--live",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-ui",
        "--auth",
        auth,
    ]
    # Both streams go to a file rather than a pipe. A live run narrates every step it takes, and a
    # pipe nobody drains fills its buffer and blocks the server mid-startup - so the log is a file
    # the fixture reads only when it has something to explain.
    log_path = project_root / _FACADE_LOG_FILENAME.format(auth=auth)
    log_handle = log_path.open("wb")
    try:
        process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
    except OSError as error:
        log_handle.close()
        raise FixtureError(
            f"could not start `d2w fhir serve`: {error}. Serving needs the extra - run `uv sync --all-extras` "
            f"in this repository, or `pip install 'dhis2w-cli[serve]'` outside it"
        ) from error
    finally:
        log_handle.close()
    _facade_processes.append(process)
    atexit.register(_stop_facades)
    _await_facade(process, base_url, log_path)
    return base_url


def _await_facade(process: subprocess.Popen[bytes], base_url: str, log_path: Path) -> None:
    """Poll `/metadata` until the facade answers it, or fail naming what the server said instead."""
    deadline = time.monotonic() + _FACADE_STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise FixtureError(
                f"`d2w fhir serve` exited with status {process.returncode} before it listened: "
                f"{_facade_log_tail(log_path)}"
            )
        try:
            response = httpx.get(f"{base_url}/metadata", headers={"Accept": "application/fhir+json"}, timeout=5.0)
        except httpx.HTTPError:
            time.sleep(_FACADE_POLL_SECONDS)
            continue
        if response.status_code == _HTTP_OK:
            return
        time.sleep(_FACADE_POLL_SECONDS)
    _stop_facades()
    raise FixtureError(
        f"`d2w fhir serve` did not answer /metadata within {int(_FACADE_STARTUP_SECONDS)}s. A live run reads "
        f"the whole instance at startup, so a slow DHIS2 is the usual cause; set {FACADE_ENVIRONMENT_VARIABLE} "
        f"to a facade you started yourself to skip this"
    )


def _facade_log_tail(log_path: Path) -> str:
    """The last few lines the facade wrote before it died, which is what says why it did."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "no output"
    return "\n".join(text.splitlines()[-4:]) or "no output"


def _stop_facades() -> None:
    """Stop every facade this process started, by their own process ids and no others."""
    running, _facade_processes[:] = list(_facade_processes), []
    for process in running:
        if process.poll() is not None:
            continue
        process.terminate()
        try:
            process.wait(timeout=_FACADE_SHUTDOWN_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_FACADE_SHUTDOWN_SECONDS)


def _free_port() -> int:
    """Ask the operating system for a port nothing holds, so the fixture never fights another process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _cache_directory() -> Path:
    """Where the scaffolded project and its built context live, named for everything that went into them."""
    digest = hashlib.sha256(
        json.dumps(
            {
                "revision": _FIXTURE_REVISION,
                "instance": _instance_base_url(),
                "canonical": _IG_CANONICAL,
                "data_sets": _DATA_SET_IDS,
                "event_programs": _EVENT_PROGRAM_IDS,
                "tracker_programs": _TRACKER_PROGRAM_IDS,
                "max_level": _MAXIMUM_ORGANISATION_UNIT_LEVEL,
                "root": _ORGANISATION_UNIT_ROOT,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"d2w-fhir-example-{digest}"


def _instance_base_url() -> str:
    """The DHIS2 instance the fixture is built against, which is half of what the cache is keyed by."""
    from dhis2w_client import NoProfileError, UnknownProfileError
    from dhis2w_core.profile import resolve

    try:
        return str(resolve().profile.base_url)
    except (NoProfileError, UnknownProfileError) as error:
        raise FixtureError(
            f"{error} Configure one with `d2w profile add local --url http://localhost:8080 --auth basic "
            f"--username admin --password district --default`, or set DHIS2_URL with DHIS2_PAT"
        ) from error


def _resolved_generation_profile(project: Any) -> Any:
    """Resolve which DHIS2 instance this project reads, failing with the hint rather than the traceback."""
    from dhis2w_client import NoProfileError, UnknownProfileError
    from dhis2w_fhir import service

    try:
        return service.resolve_generation_profile(project)
    except (NoProfileError, UnknownProfileError) as error:
        raise FixtureError(
            f"{error} Configure one with `d2w profile add local --url http://localhost:8080 --auth basic "
            f"--username admin --password district --default`"
        ) from error


def _run_coroutine[RESULT](coroutine: Coroutine[Any, Any, RESULT]) -> RESULT:
    """Run one coroutine to completion whether or not the caller is already inside an event loop.

    The fixture's entry points are plain functions, because an example reads better asking for the
    context than awaiting it. Most examples are async, so `asyncio.run` here would raise inside
    their loop - the work goes to a thread with a loop of its own instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


def _write_atomically(path: Path, text: str) -> None:
    """Write the cache through a temporary sibling, so a killed run never leaves half a file behind."""
    handle, temporary_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".partial")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary_name, path)

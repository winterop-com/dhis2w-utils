"""Tests for the consolidated `generate_full` engine: one fetch per collection and the announced steps.

Mocked (respx); no live stack. The call-count assertions are the point of the consolidation -
seven solo commands read the same collections seven times over, one full run reads each once.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import respx
from dhis2w_core.profile import resolve_profile
from dhis2w_fhir import GenerateFullReport, GenerateReport, InitOptions, UnsupportedProgramError, load_project, service
from dhis2w_fhir.notes import GenerateNote, GenerateNoteCategory
from dhis2w_fhir.service import GenerateSubject, _target_counts

_HOST = "https://dhis2.example"

_OPTION_SETS_PAYLOAD = {
    "optionSets": [
        {
            "id": "Xa1b2c3d4e5",
            "name": "Birth type",
            "options": [
                {"id": "kRRUtYaGett", "code": "NB", "name": "Natural Birth", "sortOrder": 1},
                {"id": "EBE0c8sZazS", "code": "CS", "name": "Scheduled Cesarean", "sortOrder": 2},
            ],
        }
    ]
}

_CATEGORIES_PAYLOAD = {
    "categories": [
        {
            "id": "O5P6e8yu1T6",
            "name": "Sex",
            "categoryOptions": [
                {"id": "TNYQzTHdoxL", "code": "F", "name": "Female"},
                {"id": "apsOixVZlf1", "code": "M", "name": "Male"},
            ],
        }
    ]
}

_ORGANISATION_UNITS_PAYLOAD = {
    "organisationUnits": [
        {"id": "ImspTQPwCqd", "name": "Sierra Leone", "level": 1, "path": "/ImspTQPwCqd", "code": "SL"},
        {
            "id": "O6uvpzGd5pu",
            "name": "Bo",
            "level": 2,
            "path": "/ImspTQPwCqd/O6uvpzGd5pu",
            "parent": {"id": "ImspTQPwCqd"},
            "geometry": {"type": "Point", "coordinates": [-11.7383, 7.9647]},
        },
    ]
}

_DATA_SETS_PAYLOAD = {
    "dataSets": [
        {
            "id": "BfMAe6Itzgt",
            "name": "Child Health",
            "code": "DS_359711",
            "sections": [{"id": "Sec1aaaaaaa", "name": "Immunization", "dataElements": [{"id": "De1aaaaaaaa"}]}],
            "dataSetElements": [
                {
                    "dataElement": {
                        "id": "De1aaaaaaaa",
                        "name": "BCG doses given",
                        "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "optionSet": {"id": "Xa1b2c3d4e5"},
                        "categoryCombo": {"id": "bjDvmb4bfuf", "name": "default", "isDefault": True},
                    }
                }
            ],
        }
    ]
}

_PROGRAMS_PAYLOAD = {
    "programs": [
        {
            "id": "VBqh0ynB2wv",
            "name": "Malaria case registration",
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [
                {
                    "id": "pTo4uMt3xur",
                    "programStageSections": [],
                    "programStageDataElements": [
                        {
                            "compulsory": True,
                            "dataElement": {"id": "qrur9Dvnyt5", "name": "Age in years", "valueType": "INTEGER"},
                        }
                    ],
                }
            ],
        }
    ]
}


class _RecordingReporter:
    """A progress reporter recording the captions and completion lines it is handed.

    `start`, `finish`, and `stop` bound the whole run and belong to the CLI, so a service call to
    any of them fails the test rather than being recorded.
    """

    def __init__(self) -> None:
        """Start with an empty transcript of captions and completion lines."""
        self.captions: list[str] = []
        self.completions: list[str] = []

    def start(self, total: int, *, activity: str = "step") -> None:
        """Fail the test: the run's bounds belong to the CLI, not to the service."""
        raise AssertionError("the fhir service never bounds the run")

    def step(self, index: int, total: int, label: str) -> None:
        """Record one caption as `k/N label`."""
        self.captions.append(f"{index}/{total} {label}")

    def complete(self, index: int, total: int, label: str, summary: str, *, style: str | None = None) -> None:
        """Record one durable completion line as `k/N label: summary`."""
        self.completions.append(f"{index}/{total} {label}: {summary}")

    def finish(self, summary: str) -> None:
        """Fail the test: the run's bounds belong to the CLI, not to the service."""
        raise AssertionError("the fhir service never bounds the run")

    def stop(self) -> None:
        """Fail the test: the run's bounds belong to the CLI, not to the service."""
        raise AssertionError("the fhir service never bounds the run")


async def _scaffold_project(directory: Path) -> None:
    """Scaffold a minimal project so the generate targets have a fhir.toml and an ig tree."""
    options = InitOptions(
        ig_id="dhis2.fhir.full",
        canonical="http://example.org/fhir",
        name="Dhis2FhirFull",
        title="Full IG",
        publisher="Full Org",
    )
    await service.init_project(directory, options)


def _mock_instance(mock_system_info: Callable[..., None], mock_attributes: Callable[..., None]) -> None:
    """Mock every endpoint one full generate run reads."""
    mock_system_info("v42")
    mock_attributes()
    respx.get(f"{_HOST}/api/optionSets", name="optionSets").mock(
        return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD)
    )
    respx.get(f"{_HOST}/api/categories", name="categories").mock(
        return_value=httpx.Response(200, json=_CATEGORIES_PAYLOAD)
    )
    respx.get(f"{_HOST}/api/dataSets", name="dataSets").mock(return_value=httpx.Response(200, json=_DATA_SETS_PAYLOAD))
    respx.get(f"{_HOST}/api/programs", name="programs").mock(return_value=httpx.Response(200, json=_PROGRAMS_PAYLOAD))
    respx.get(f"{_HOST}/api/programRules").mock(return_value=httpx.Response(200, json={"programRules": []}))
    respx.get(f"{_HOST}/api/organisationUnits", name="organisationUnits").mock(
        return_value=httpx.Response(200, json=_ORGANISATION_UNITS_PAYLOAD)
    )


@respx.mock
async def test_generate_full_reads_each_metadata_collection_exactly_once(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """One full run reads every collection once; the seven solo commands read them over and over."""
    _mock_instance(mock_system_info, mock_attributes)
    organisation_units = respx.routes["organisationUnits"]
    await _scaffold_project(tmp_path)

    await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    for name in ("optionSets", "categories"):
        assert respx.routes[name].call_count == 1, name
    # The data sets and the programs are read twice each, and the second read of each is the
    # id-only organisation-unit assignment fetch. It stays a read of its own so the projection
    # sweep is not inflated by thousands of assigned unit ids per container.
    for name in ("dataSets", "programs"):
        assert respx.routes[name].call_count == 2, name
        assert "organisationUnits[id]" in respx.routes[name].calls[1].request.url.params["fields"]
    assert _route_call_count("/api/attributes") == 1
    assert _route_call_count("/api/system/info") == 1
    # Two org-unit reads, and only one of them is the paged hierarchy walk: the examples target
    # also asks the instance for its level-1 root, which is the subject every example is filed under.
    assert organisation_units.call_count == 2
    paged = [call for call in organisation_units.calls if "pageSize" in call.request.url.params]
    assert len(paged) == 1
    assert paged[0].request.url.params["order"] == "path:asc"


def _route_call_count(path: str) -> int:
    """How many recorded calls hit one endpoint - the fixture-owned routes carry no respx name."""
    return sum(1 for call in respx.calls if call.request.url.path == path)


@respx.mock
async def test_generate_full_writes_what_the_solo_targets_write(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The consolidated run leaves the project byte-identical to running every target on its own."""
    _mock_instance(mock_system_info, mock_attributes)
    full_root = tmp_path / "full"
    solo_root = tmp_path / "solo"
    await _scaffold_project(full_root)
    await _scaffold_project(solo_root)
    profile = resolve_profile("probe")

    await service.generate_full(profile, load_project(full_root))
    await service.generate_foundation(load_project(solo_root))
    await service.generate_option_sets(profile, load_project(solo_root))
    await service.generate_categories(profile, load_project(solo_root))
    await service.generate_questionnaires(profile, load_project(solo_root))
    await service.generate_examples(profile, load_project(solo_root))
    await service.generate_organisation_units(profile, load_project(solo_root))
    await service.generate_pages(profile, load_project(solo_root))

    assert _tree(full_root) == _tree(solo_root)


def _tree(root: Path) -> dict[str, bytes]:
    """Every generated file under one project root, keyed by its path relative to that root."""
    return {
        str(path.relative_to(root)): path.read_bytes() for path in sorted((root / "ig").rglob("*")) if path.is_file()
    }


@respx.mock
async def test_generate_full_announces_the_fetch_and_one_step_per_target(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The reporter sees the instance fetch, then the seven targets, each closed by its own summary."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    reporter = _RecordingReporter()

    await service.generate_full(resolve_profile("probe"), load_project(tmp_path), reporter=reporter)

    # Exactly one completion per numbered step, in order, so the counter an animated display
    # advances on completion lands on the run's own length and never past it.
    assert [line.split(" ", 1)[0] for line in reporter.completions] == [f"{index}/8" for index in range(1, 9)]
    assert reporter.completions[0] == (
        "1/8 instance metadata: 2 questionnaire target(s), 1 option set(s), 1 category, 2 organisation unit(s)"
    )
    assert [line.split(": ", 1)[0] for line in reporter.completions[1:]] == [
        "2/8 foundation",
        "3/8 option sets",
        "4/8 categories",
        "5/8 questionnaires",
        "6/8 examples",
        "7/8 organisation units",
        "8/8 pages",
    ]
    assert reporter.completions[1].endswith(" files written, 0 files unchanged")
    # The live captions say what each step is doing while it runs; the shared fetch narrates
    # itself with ticks that neither advance the counter nor print a line of their own.
    assert reporter.captions[0] == "1/8 fetching instance metadata"
    assert "1/8 reading option sets" in reporter.captions
    assert "1/8 organisation units: 2 read across 1 page(s)" in reporter.captions
    assert "2/8 writing ig/input/fsh/foundation" in reporter.captions
    assert "3/8 writing ig/input/resources/terminology and ig/input/resources/concept-maps" in reporter.captions
    assert "4/8 writing ig/input/resources/categories and ig/input/resources/concept-maps" in reporter.captions
    assert "6/8 writing ig/input/fsh/examples" in reporter.captions
    assert "8/8 writing ig/input/pagecontent" in reporter.captions


@respx.mock
async def test_generate_option_sets_announces_a_fetch_and_an_emit_step(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A solo target announces two steps: what it reads, then what it writes, then its outcome."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    reporter = _RecordingReporter()

    await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path), reporter=reporter)

    assert reporter.captions == [
        "1/2 fetching option sets",
        "2/2 writing ig/input/resources/terminology and ig/input/resources/concept-maps",
    ]
    assert reporter.completions == [
        "1/2 instance metadata: 1 option set(s)",
        "2/2 option sets: 1 option set, 5 files written, 0 files unchanged",
    ]


@respx.mock
async def test_validate_codes_announces_the_sweep_and_its_size(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
) -> None:
    """The validate run announces connecting, resolving the selection, sweeping, reading, and building."""
    mock_system_info("v42")
    respx.get(f"{_HOST}/api/optionSets").mock(return_value=httpx.Response(200, json=_OPTION_SETS_PAYLOAD))
    for resource in ("dataSets", "programs", "categories", "organisationUnits"):
        respx.get(f"{_HOST}/api/{resource}").mock(return_value=httpx.Response(200, json={resource: []}))
    respx.get(f"{_HOST}/api/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "dataElements": [{"id": "De1aaaaaaaa", "name": "BCG", "code": "DE1"}],
                "indicators": [{"id": "In1aaaaaaaa", "name": "ANC", "code": "IN1"}],
            },
        )
    )
    reporter = _RecordingReporter()

    context = service.resolve_validation_context()
    await service.validate_codes(resolve_profile("probe"), context.config, reporter=reporter)

    assert reporter.captions == [
        "1/5 connecting",
        "2/5 resolving the configured selection",
        "3/5 sweeping instance metadata (can take a minute on a large instance)",
        "4/5 reading option sets",
        "5/5 building report",
    ]
    assert reporter.completions == [
        "1/5 connecting: https://dhis2.example",
        "2/5 selection: 0 data sets, 0 programs, 0 stages, 0 data elements, 1 option sets, "
        "0 categories, 0 organisation units",
        "3/5 instance sweep: 2 collections, 2 objects",
        "4/5 option sets: 1 read",
        "5/5 findings: 0 finding(s)",
    ]


def test_an_unsupported_program_is_a_lookup_error() -> None:
    """`UnsupportedProgramError` is a `LookupError`, so the CLI funnel renders it as a one-liner."""
    error = service.UnsupportedProgramError("program 'X' (Uid) has programType unknown")

    assert isinstance(error, LookupError)
    assert issubclass(UnsupportedProgramError, LookupError)


def _target_report(*notes: GenerateNote) -> GenerateReport:
    """One per-target report carrying the given notes, everything else at its defaults."""
    return GenerateReport(project_root=Path("/project"), target_directory="somewhere", notes=list(notes))


def _shared_note_report() -> GenerateFullReport:
    """A full run whose questionnaires, examples, and pages all carry the same source note."""
    shared = GenerateNote(category=GenerateNoteCategory.SELECTION_MISMATCH, message="a note three targets share")
    own = GenerateNote(category=GenerateNoteCategory.SKIPPED_QUESTION, message="a note examples alone raised")
    return GenerateFullReport(
        foundation=_target_report(),
        option_sets=_target_report(),
        categories=_target_report(),
        questionnaires=_target_report(shared),
        examples=_target_report(shared, own),
        organisation_units=_target_report(),
        pages=_target_report(shared),
    )


def test_with_distinct_notes_keeps_a_shared_note_on_its_first_target() -> None:
    """A note handed to several targets survives once, on the first target that raised it."""
    report = _shared_note_report()

    distinct = report.with_distinct_notes()

    assert [note.message for note in distinct.questionnaires.notes] == ["a note three targets share"]
    assert [note.message for note in distinct.examples.notes] == ["a note examples alone raised"]
    assert distinct.pages.notes == []


def test_with_distinct_notes_leaves_the_per_target_reports_alone() -> None:
    """The distinct view is a copy: the run's own per-target lists still read as the solo commands' do."""
    report = _shared_note_report()

    report.with_distinct_notes()

    assert len(report.questionnaires.notes) == 1
    assert len(report.examples.notes) == 2
    assert len(report.pages.notes) == 1


def _write_compile(root: Path) -> Path:
    """Put a compiled guide where SUSHI writes one, holding one resource this run did not compile."""
    compiled = root / "ig" / "fsh-generated" / "resources"
    compiled.mkdir(parents=True)
    (compiled / "CodeSystem-d2-os-Age.json").write_text('{"resourceType": "CodeSystem"}', encoding="utf-8")
    return compiled.parent


def _compile_notes(*reports: GenerateReport) -> list[str]:
    """Every note about the compiled guide these target reports carry, in the order the targets ran."""
    return [
        note.message
        for report in reports
        for note in report.notes
        if note.category is GenerateNoteCategory.COMPILE_REMOVED
    ]


def _full_run_compile_notes(report: GenerateFullReport) -> list[str]:
    """The same reading over a whole run: every target of it, in the order the fields declare them."""
    return _compile_notes(*(getattr(report, target) for target in type(report).model_fields))


@respx.mock
async def test_a_generate_that_writes_fsh_removes_the_compile_it_no_longer_matches(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """A first run writes every FSH source, so the compile of the sources before it goes with it."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    compiled = _write_compile(tmp_path)

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert not compiled.exists()
    assert _full_run_compile_notes(report) == [
        "removed ig/fsh-generated: it held SUSHI's compile of FSH sources this run rewrote, and "
        "check-artifacts, serve, forward and `make build` all read that tree. Run `make sushi` in "
        "the project to compile the sources this run wrote."
    ]


@respx.mock
async def test_an_unchanged_regenerate_leaves_the_compile_alone(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The second run over the same instance writes no FSH, so the compile is still the one these sources make."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    await service.generate_full(resolve_profile("probe"), load_project(tmp_path))
    compiled = _write_compile(tmp_path)

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert (compiled / "resources" / "CodeSystem-d2-os-Age.json").is_file()
    assert _full_run_compile_notes(report) == []


@respx.mock
async def test_the_removal_is_reported_once_however_many_targets_rewrote_fsh(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """Four targets of a first run write FSH, and the compile is removed and reported by the first of them."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    _write_compile(tmp_path)

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    assert len(_full_run_compile_notes(report)) == 1
    assert [note.category for note in report.foundation.notes] == [GenerateNoteCategory.COMPILE_REMOVED]


@respx.mock
async def test_a_solo_target_whose_own_sources_changed_removes_the_compile(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """One target is a whole regenerate as far as the compile is concerned: its sources are in it too."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    compiled = _write_compile(tmp_path)

    report = await service.generate_questionnaires(resolve_profile("probe"), load_project(tmp_path))

    assert not compiled.exists()
    assert len(_compile_notes(report)) == 1


@respx.mock
async def test_a_target_that_writes_only_predefined_json_leaves_the_compile_alone(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """The option-set target writes `ig/input/resources`, which is read off disk rather than compiled."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)
    compiled = _write_compile(tmp_path)

    report = await service.generate_option_sets(resolve_profile("probe"), load_project(tmp_path))

    assert report.written_files
    assert (compiled / "resources" / "CodeSystem-d2-os-Age.json").is_file()
    assert _compile_notes(report) == []


def _scaffold_drift_notes(report: GenerateReport) -> list[GenerateNote]:
    """Every note the report carries about the project's own files disagreeing."""
    return [note for note in report.notes if note.category is GenerateNoteCategory.SCAFFOLD_DRIFT]


async def test_a_title_edited_after_scaffolding_is_named_as_scaffold_drift(tmp_path: Path) -> None:
    """fhir.toml states the guide's title and sushi-config carries it, so the run names the refresh that lands it."""
    await _scaffold_project(tmp_path)
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace('title = "Full IG"', 'title = "National IG"'),
        encoding="utf-8",
    )

    report = await service.generate_foundation(load_project(tmp_path))

    notes = _scaffold_drift_notes(report)
    assert len(notes) == 1
    assert "ig/sushi-config.yaml does not carry what fhir.toml states (title, description)" in notes[0].message
    assert "d2w fhir init --refresh" in notes[0].message


async def test_a_project_whose_two_files_agree_raises_no_scaffold_drift(tmp_path: Path) -> None:
    """A project straight off `d2w fhir init` states one identity in both files, so there is nothing to say."""
    await _scaffold_project(tmp_path)

    report = await service.generate_foundation(load_project(tmp_path))

    assert _scaffold_drift_notes(report) == []


@respx.mock
async def test_the_organisation_unit_target_counts_units_apart_from_the_files_they_ship_as(
    probe_profile: None,  # noqa: ARG001
    mock_system_info: Callable[..., None],
    mock_attributes: Callable[..., None],
    tmp_path: Path,
) -> None:
    """One organisation unit ships as an Organization and a Location, so the subject is half the files."""
    _mock_instance(mock_system_info, mock_attributes)
    await _scaffold_project(tmp_path)

    report = await service.generate_full(resolve_profile("probe"), load_project(tmp_path))

    organisation_units = report.organisation_units
    assert organisation_units.organisation_unit_count == 2
    assert organisation_units.subject is not None
    assert organisation_units.subject.label() == "2 organisation units"
    registry_files = [name for name in organisation_units.written_files if name.startswith("registry/")]
    assert len(registry_files) == 2 * organisation_units.organisation_unit_count
    assert len(organisation_units.written_files) > organisation_units.organisation_unit_count


def test_a_target_completion_leads_with_the_subject_it_covers() -> None:
    """A target that knows what it covers says so first, then counts the files it took to publish it."""
    report = GenerateReport(
        project_root=Path("/project"),
        target_directory="organization",
        written_files=["organization/a.fsh", "organization/b.fsh"],
        unchanged_count=1,
        organisation_unit_count=1,
        subject=GenerateSubject(count=1696, noun="organisation unit"),
    )

    assert _target_counts(report) == "1,696 organisation units, 2 files written, 1 file unchanged"


def test_a_target_with_no_subject_reports_files_alone() -> None:
    """The foundation publishes no instance objects, so its line is a file count and nothing else."""
    report = GenerateReport(
        project_root=Path("/project"),
        target_directory="foundation",
        written_files=[f"foundation/{index}.fsh" for index in range(24)],
    )

    assert _target_counts(report) == "24 files written, 0 files unchanged"


def test_every_count_on_one_line_is_grouped_the_same_way() -> None:
    """Subject and files sit on one line, so they are read in one number style."""
    report = GenerateReport(
        project_root=Path("/project"),
        target_directory="organization",
        written_files=[f"registry/{index}.json" for index in range(2667)],
        unchanged_count=1332,
        subject=GenerateSubject(count=1332, noun="organisation unit"),
    )

    assert _target_counts(report) == "1,332 organisation units, 2,667 files written, 1,332 files unchanged"


def test_an_irregular_plural_is_spelled_out() -> None:
    """A subject whose plural an `s` would misspell carries the spelling it is read by."""
    assert GenerateSubject(count=150, noun="category", plural="categories").label() == "150 categories"
    assert GenerateSubject(count=1, noun="category", plural="categories").label() == "1 category"

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
from dhis2w_fhir import InitOptions, UnsupportedProgramError, load_project, service

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

    for name in ("optionSets", "categories", "dataSets", "programs"):
        assert respx.routes[name].call_count == 1, name
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
    assert reporter.completions[1].endswith(" written, 0 unchanged")
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
        "2/2 option sets: 3 written, 0 unchanged",
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

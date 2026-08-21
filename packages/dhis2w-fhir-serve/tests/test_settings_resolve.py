"""What one serve invocation resolves to: a stated dial, then `[serve]`, then the model's own defaults.

The precedence is a table with four rows per dial - stated only, `[serve]` only, both, neither - and
this file walks all four for every dial that has one. It is the whole reason `ServeSettings.resolve`
exists: an embedded facade and `d2w fhir serve` disagreeing about what `[serve]` meant is a
difference nothing would report.

Every profile lookup is stubbed. Resolving one reads the machine's `profiles.toml`, and what this
file is about is the step from a resolved profile to the address the screens link out to, not the
lookup itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from dhis2w_client.profile import NoProfileError, Profile
from dhis2w_fhir.config import (
    BasemapSource,
    FhirProject,
    SearchBackend,
    ServeAuth,
    ServeAuthScope,
    load_fhir_config,
)
from dhis2w_fhir.service import GenerationProfile
from dhis2w_fhir_serve import settings as settings_module
from dhis2w_fhir_serve.auth import SERVE_TOKENS_VARIABLE
from dhis2w_fhir_serve.settings import ServeInvocation, ServeSettings
from dhis2w_fhir_serve.store import CompiledIgMissingError
from pydantic import BaseModel, ConfigDict

PROJECT_HEAD = """
[ig]
id = "dhis2.fhir.example"
canonical = "http://example.org/fhir"
name = "Dhis2FhirExample"
title = "DHIS2 FHIR Example IG"
publisher = "Example Organisation"

[generate.organisation_units]
root = ""
max_level = 0
"""

QUESTIONNAIRE = {
    "resourceType": "Questionnaire",
    "id": "d2-pr-anc-visit-q",
    "url": "http://example.org/fhir/Questionnaire/d2-pr-anc-visit-q",
    "status": "active",
    "title": "ANC Visit",
}

#: The profile a stubbed lookup answers with, and the address it puts on the settings.
INSTANCE_URL = "https://play.example.org/dhis"
PROFILE_NAME = "example"

#: A tile layer no project's table names, so a resolved one can only have come from the argument.
STATED_BASEMAP = "Mirror=https://tiles.example.org/{z}/{x}/{y}.png"
TABLE_BASEMAP_URL = "https://tables.example.org/{z}/{x}/{y}.png"


def _project(tmp_path: Path, serve_table: str = "", *, compiled: bool = True) -> FhirProject:
    """A project whose `[serve]` table is whatever a case states, with a guide on disk unless told otherwise."""
    config_path = tmp_path / "fhir.toml"
    config_path.write_text(PROJECT_HEAD + serve_table, encoding="utf-8")
    if compiled:
        compiled_directory = tmp_path / "ig" / "fsh-generated" / "resources"
        compiled_directory.mkdir(parents=True)
        (compiled_directory / "Questionnaire-d2-pr-anc-visit-q.json").write_text(
            json.dumps(QUESTIONNAIRE), encoding="utf-8"
        )
    return FhirProject(config=load_fhir_config(config_path), config_path=config_path.resolve())


@pytest.fixture(autouse=True)
def no_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve no profile by default, which is the posture of a machine serving a compiled guide alone."""

    def _refuse(project: FhirProject, explicit: str | None = None) -> GenerationProfile:
        raise NoProfileError("no profile is named here")

    monkeypatch.setattr(settings_module, "resolve_generation_profile", _refuse)


@pytest.fixture
def resolved_profile(monkeypatch: pytest.MonkeyPatch) -> GenerationProfile:
    """A machine that does name a profile, and the instance that profile points at."""
    generation = GenerationProfile(
        name=PROFILE_NAME,
        origin="fhir.toml",
        profile=Profile(base_url=INSTANCE_URL, auth="basic", username="admin", password="district"),
    )
    monkeypatch.setattr(settings_module, "resolve_generation_profile", lambda project, explicit=None: generation)
    return generation


class PrecedenceCase(BaseModel):
    """One row of the precedence table: what the project's table says, what the run said, what wins."""

    model_config = ConfigDict(frozen=True)

    dial: str
    """The name the resolved value is read back under, on the invocation or on its settings."""

    table: str
    """The `[serve]` table this case's project carries, empty when the table states nothing."""

    stated: dict[str, Any]
    """The arguments this run states, empty when it states nothing."""

    expected: Any
    """What the dial resolves to."""

    def case_id(self) -> str:
        """Which of the four rows this case is, as the test report names it."""
        if self.table and self.stated:
            return f"{self.dial}-both"
        if self.stated:
            return f"{self.dial}-stated"
        if self.table:
            return f"{self.dial}-table"
        return f"{self.dial}-neither"


#: A `[serve]` table that binds every interface and says who is served, which is the pair a
#: deployment writes together - the address alone is refused.
OPEN_TO_EVERYONE_TABLE = "[serve]\nhost = '0.0.0.0'\nauth = 'none'\n"

#: Every dial with a flag and a table key, over all four ways the two can be stated.
PRECEDENCE_CASES = [
    PrecedenceCase(dial="host", table="", stated={}, expected="127.0.0.1"),
    # Every host case but the default binds an interface other than loopback, which is refused unless
    # the posture is written down - so each of the three states it, which is what a deployment does.
    PrecedenceCase(dial="host", table=OPEN_TO_EVERYONE_TABLE, stated={}, expected="0.0.0.0"),
    PrecedenceCase(dial="host", table="", stated={"host": "10.0.0.1", "auth": ServeAuth.NONE}, expected="10.0.0.1"),
    PrecedenceCase(
        dial="host",
        table=OPEN_TO_EVERYONE_TABLE,
        stated={"host": "10.0.0.1"},
        expected="10.0.0.1",
    ),
    PrecedenceCase(dial="auth", table="", stated={}, expected=ServeAuth.NONE),
    PrecedenceCase(dial="auth", table="[serve]\nauth = 'token'\n", stated={}, expected=ServeAuth.TOKEN),
    PrecedenceCase(dial="auth", table="", stated={"auth": ServeAuth.TOKEN}, expected=ServeAuth.TOKEN),
    PrecedenceCase(
        dial="auth",
        table="[serve]\nauth = 'token'\n",
        stated={"auth": ServeAuth.NONE},
        expected=ServeAuth.NONE,
    ),
    PrecedenceCase(dial="auth_scope", table="", stated={}, expected=ServeAuthScope.WRITE),
    PrecedenceCase(
        dial="auth_scope",
        table="[serve]\nauth_scope = 'all'\n",
        stated={},
        expected=ServeAuthScope.ALL,
    ),
    PrecedenceCase(
        dial="auth_scope",
        table="",
        stated={"auth_scope": ServeAuthScope.ALL},
        expected=ServeAuthScope.ALL,
    ),
    PrecedenceCase(
        dial="auth_scope",
        table="[serve]\nauth_scope = 'all'\n",
        stated={"auth_scope": ServeAuthScope.WRITE},
        expected=ServeAuthScope.WRITE,
    ),
    PrecedenceCase(dial="port", table="", stated={}, expected=8080),
    PrecedenceCase(dial="port", table="[serve]\nport = 9000\n", stated={}, expected=9000),
    PrecedenceCase(dial="port", table="", stated={"port": 7000}, expected=7000),
    PrecedenceCase(dial="port", table="[serve]\nport = 9000\n", stated={"port": 7000}, expected=7000),
    PrecedenceCase(dial="strict_codes", table="", stated={}, expected=False),
    PrecedenceCase(dial="strict_codes", table="[serve]\nstrict_codes = true\n", stated={}, expected=True),
    PrecedenceCase(dial="strict_codes", table="", stated={"strict_codes": True}, expected=True),
    PrecedenceCase(
        dial="strict_codes",
        table="[serve]\nstrict_codes = true\n",
        stated={"strict_codes": False},
        expected=False,
    ),
    PrecedenceCase(dial="ui", table="", stated={}, expected=False),
    PrecedenceCase(dial="ui", table="[serve]\nui = true\n", stated={}, expected=True),
    PrecedenceCase(dial="ui", table="", stated={"ui": True}, expected=True),
    PrecedenceCase(dial="ui", table="[serve]\nui = true\n", stated={"ui": False}, expected=False),
    PrecedenceCase(
        dial="basemaps",
        table="",
        stated={},
        expected=["OpenStreetMap"],
    ),
    PrecedenceCase(
        dial="basemaps",
        table=f"[[serve.basemaps]]\nname = 'Table'\nurl = '{TABLE_BASEMAP_URL}'\n",
        stated={},
        expected=["Table"],
    ),
    PrecedenceCase(dial="basemaps", table="", stated={"basemaps": [STATED_BASEMAP]}, expected=["Mirror"]),
    PrecedenceCase(
        dial="basemaps",
        table=f"[[serve.basemaps]]\nname = 'Table'\nurl = '{TABLE_BASEMAP_URL}'\n",
        stated={"basemaps": [STATED_BASEMAP]},
        expected=["Mirror"],
    ),
]


@pytest.fixture(autouse=True)
def deployment_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `token` posture is refused with its variable unset, so the precedence rows that state one set it.

    The refusal itself is `test_serve_auth.py`'s subject. Here the question is only which of the flag
    and the table wins, and a run that could not start would answer neither.
    """
    monkeypatch.setenv(SERVE_TOKENS_VARIABLE, "a-deployment-token")


def _resolved_dial(invocation: ServeInvocation, dial: str) -> Any:
    """Read one dial back off the invocation: the address is its own, the rest are the settings'."""
    if dial in {"host", "port"}:
        return getattr(invocation, dial)
    if dial == "basemaps":
        return [basemap.name for basemap in invocation.settings.basemaps]
    return getattr(invocation.settings, dial)


@pytest.mark.parametrize(
    "case",
    PRECEDENCE_CASES,
    ids=[case.case_id() for case in PRECEDENCE_CASES],
)
def test_the_precedence_table(tmp_path: Path, case: PrecedenceCase) -> None:
    """A stated dial wins over `[serve]`, `[serve]` wins over the default, and stating nothing takes both."""
    invocation = ServeSettings.resolve(_project(tmp_path, case.table), **case.stated)

    assert _resolved_dial(invocation, case.dial) == case.expected


def test_the_keys_with_no_dial_come_off_the_table(tmp_path: Path) -> None:
    """`capture` and `spool_dir` say what this server offers and where its receipts live: no flag overrides them."""
    invocation = ServeSettings.resolve(_project(tmp_path, "[serve]\ncapture = false\nspool_dir = 'receipts'\n"))

    assert invocation.settings.capture is False
    assert invocation.settings.spool_dir == "receipts"


def test_the_tracked_entities_table_is_carried_across(tmp_path: Path) -> None:
    """The register a run serves is the project's statement, not the invocation's."""
    table = "[serve.tracked_entities]\nenabled = true\nlisting = false\ntracked_entity_types = ['nEenWmSyUEp']\n"

    invocation = ServeSettings.resolve(_project(tmp_path, table))

    assert invocation.settings.tracked_entities.enabled is True
    assert invocation.settings.tracked_entities.listing is False
    assert invocation.settings.tracked_entities.tracked_entity_types == ["nEenWmSyUEp"]


def test_the_search_backend_is_carried_across_and_defaults_to_the_instance(tmp_path: Path) -> None:
    """What answers a register search is the project's statement too, and its default is today's behaviour."""
    stating_table = tmp_path / "stated"
    stating_table.mkdir()
    silent = ServeSettings.resolve(_project(tmp_path))
    stated = ServeSettings.resolve(_project(stating_table, '[serve.search]\nbackend = "dhis2"\n'))

    assert silent.settings.search.backend is SearchBackend.DHIS2
    assert stated.settings.search.backend is SearchBackend.DHIS2


def test_a_live_run_is_a_property_of_the_invocation(tmp_path: Path, resolved_profile: GenerationProfile) -> None:
    """No `[serve]` key answers `live`, and a live run needs no compiled guide on disk."""
    invocation = ServeSettings.resolve(_project(tmp_path, compiled=False), live=True)

    assert invocation.settings.live is True


def test_a_basemap_that_names_nothing_servable_is_refused(tmp_path: Path) -> None:
    """`--basemap none` beside a real layer is a contradiction, and it refuses rather than guessing."""
    with pytest.raises(ValueError, match="serves no layers at all"):
        ServeSettings.resolve(_project(tmp_path), basemaps=["none", STATED_BASEMAP])


def test_a_basemap_saying_none_serves_no_layers(tmp_path: Path) -> None:
    """The air-gapped posture: the only layer the map offers is the None its control always carries."""
    invocation = ServeSettings.resolve(_project(tmp_path), basemaps=["none"])

    assert invocation.settings.basemaps == []


def test_a_bare_template_is_named_after_its_host(tmp_path: Path) -> None:
    """A source this project was handed and knows nothing else about is called what its host is called."""
    invocation = ServeSettings.resolve(_project(tmp_path), basemaps=[TABLE_BASEMAP_URL])

    assert invocation.settings.basemaps == [BasemapSource(name="tables.example.org", url=TABLE_BASEMAP_URL)]


def test_the_resolved_profile_becomes_the_address_the_screens_link_out_to(
    tmp_path: Path, resolved_profile: GenerationProfile
) -> None:
    """The instance's address reaches the settings; the name, the origin, and the credentials stay beside them."""
    invocation = ServeSettings.resolve(_project(tmp_path))

    assert invocation.settings.dhis2_base_url == INSTANCE_URL
    assert invocation.generation == resolved_profile
    assert invocation.settings.model_dump_json().find("district") == -1


def test_a_machine_naming_no_profile_serves_its_guide_offline(tmp_path: Path) -> None:
    """Absence is a posture rather than a failure: no address, so the screens link no identity anywhere."""
    invocation = ServeSettings.resolve(_project(tmp_path))

    assert invocation.generation is None
    assert invocation.settings.dhis2_base_url is None


def test_a_live_run_needs_the_profile_it_reads_through(tmp_path: Path) -> None:
    """A live store has an instance to read, so a machine naming no profile refuses the run."""
    with pytest.raises(NoProfileError):
        ServeSettings.resolve(_project(tmp_path, compiled=False), live=True)


def test_a_named_profile_is_passed_to_the_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The profile one run names is what the lookup is asked for, and what the settings carry."""
    asked: list[str | None] = []

    def _record(project: FhirProject, explicit: str | None = None) -> GenerationProfile:
        asked.append(explicit)
        return GenerationProfile(
            name=PROFILE_NAME, origin="--profile/DHIS2_PROFILE", profile=Profile(base_url=INSTANCE_URL, auth="basic")
        )

    monkeypatch.setattr(settings_module, "resolve_generation_profile", _record)

    invocation = ServeSettings.resolve(_project(tmp_path), profile="probe")

    assert asked == ["probe"]
    assert invocation.settings.profile == "probe"


def test_a_project_that_has_never_been_built_is_refused(tmp_path: Path) -> None:
    """A compiled run with nothing compiled says so in one line, rather than answering every read with a 404."""
    with pytest.raises(CompiledIgMissingError):
        ServeSettings.resolve(_project(tmp_path, compiled=False))


def test_the_resolved_settings_are_read_only(tmp_path: Path) -> None:
    """What a run resolved is settled once: the factory is handed it and never rewrites it."""
    invocation = ServeSettings.resolve(_project(tmp_path))

    with pytest.raises(ValueError, match="frozen"):
        invocation.settings.live = True

"""The `fhir.toml` document: its models plus discovery, load, and save.

A FHIR IG project is any directory holding a `fhir.toml` (scaffolded by
`d2w fhir init`). Discovery walks up from the working directory, mirroring
how `.dhis2/profiles.toml` is found.

The document composes the per-component selection tables, so this module
depends on the components and never the other way round - an emitter
receives its config as a parameter.
"""

from __future__ import annotations

import difflib
import re
import tomllib
import zoneinfo
from pathlib import Path
from typing import Literal

import tomli_w
from dhis2w_core.cli_errors import CliUserError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dhis2w_fhir.i18n import normalize_locale
from dhis2w_fhir.names import NamingSource, strip_trailing_slash
from dhis2w_fhir.r4 import SUBJECT_RESOURCE_TYPES
from dhis2w_fhir.resources.categories.schemas import CategorySelection
from dhis2w_fhir.resources.examples.schemas import ExampleSelection
from dhis2w_fhir.resources.option_sets.schemas import OptionSetSelection
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitSelection
from dhis2w_fhir.resources.questionnaires.schemas import TargetSelection
from dhis2w_fhir.status import IgStatus

FHIR_CONFIG_FILENAME = "fhir.toml"

#: Project directory validation reports land in - regenerable working artifacts, gitignored by the scaffold.
REPORTS_DIRECTORY = "reports"


class NoFhirProjectError(LookupError):
    """Raised when no `fhir.toml` is found walking up from the working directory."""


class UnknownFhirConfigKeyError(CliUserError):
    """Raised when `fhir.toml` names keys the configuration document does not declare."""


class IgConfig(BaseModel):
    """SUSHI IG identity - the `[ig]` table of `fhir.toml`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    canonical: str
    name: str
    title: str
    publisher: str
    status: IgStatus = "draft"

    _normalize_canonical = field_validator("canonical")(strip_trailing_slash)


def _validate_fsh_token(value: str, *, allow_empty: bool) -> str:
    """Require a letter-leading alphanumeric token (it lands in FSH names), optionally empty."""
    if not value:
        if allow_empty:
            return value
        raise ValueError("token must not be empty")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", value):
        raise ValueError("token must be letter-leading alphanumeric (e.g. 'D2', 'Dhis2', 'OU')")
    return value


class NamingConfig(BaseModel):
    """The identity source and the FSH naming tokens - the `[generate.naming]` table of `fhir.toml`.

    `source` picks the identity stem every artifact of an object derives from: the FHIR
    resource id, the canonical URL, the file name, and the FSH name all follow one resolved
    segment. `"id"` (the default) takes the DHIS2 id verbatim; `"code-or-id"` takes the
    object's code when it is usable as a stem and unique in the run, falling back to the id
    with a note; `"code"` requires such a code on every selected object and refuses the run
    otherwise.

    Artifact names merge the prefix and kind tokens and underscore the rest
    (`D2` + `OS` + `_BirthType` + `_CS`); ids join the kebab of each non-empty token
    (`d2-os-birth-type-cs`). `prefix`, `option_set`, `category`, `attribute_option_combo`,
    `data_set`, `program`, and `program_stage` may be empty to drop them;
    `organisation_unit` must stay non-empty or the org-unit artifact names would degenerate
    to bare `_CS`/`_Level_CS`. `attribute_option_combo` names the vocabulary a data
    set's non-default category combo publishes, and it takes a token of its own rather than the
    `COC` the data dictionary uses: `D2COC_CS` is the disaggregation vocabulary a
    question's cells are coded from, while `D2AOC_*_VS` is the vocabulary a response's
    attribute option combo is drawn from, and the two are bound in different places. Future
    group / group-set artifacts follow the same scheme (`OUG`, `OUGS`).
    """

    model_config = ConfigDict(extra="forbid")

    source: NamingSource = "id"
    prefix: str = "D2"
    option_set: str = "OS"
    category: str = "CAT"
    attribute_option_combo: str = "AOC"
    organisation_unit: str = "OU"
    data_set: str = "DS"
    program: str = "PR"
    program_stage: str = "PS"

    @field_validator(
        "prefix", "option_set", "category", "attribute_option_combo", "data_set", "program", "program_stage"
    )
    @classmethod
    def _optional_token(cls, value: str) -> str:
        """Prefix, option_set, category, attribute_option_combo, data_set, program, and program_stage may be empty."""
        return _validate_fsh_token(value, allow_empty=True)

    @field_validator("organisation_unit")
    @classmethod
    def _required_token(cls, value: str) -> str:
        """organisation_unit must be a non-empty FSH-name-safe token."""
        return _validate_fsh_token(value, allow_empty=False)


class GenerateConfig(BaseModel):
    """Generation behaviour - the `[generate]` table of `fhir.toml`.

    The three data-definition tables select the three questionnaire form kinds: `data_sets`
    picks aggregate data sets, `event_programs` picks programs without registration, and
    `tracker_programs` picks programs with registration, one Questionnaire per program stage.

    `timezone` is the IANA zone the instance's zone-less timestamps are wall-clock readings in
    (BUGS.md #62). Naming it turns every emitted `dateTime` into the numeric offset that zone
    was on at that very instant, DST included; leaving it unset keeps the UTC reading.

    `tracked_entity_types` maps a DHIS2 tracked entity type UID onto the FHIR resource type its
    registrations are about. A DHIS2 tracked entity is not always a person - a project tracks
    households, buildings, herds, and equipment as readily as patients - so the type says what it
    is and every form of every program tracking it follows. A type named here is not selected by
    it: selection stays with the three data-definition tables, and a type this table never
    mentions is a `Patient`, which is what keeps a person-tracking project's config empty.
    """

    model_config = ConfigDict(extra="forbid")

    identifier_system_base: str = "http://dhis2.org/fhir"
    concept_code_source: Literal["id", "code"] = "id"
    timezone: str | None = None
    locales: list[str] = Field(default_factory=list)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    option_sets: OptionSetSelection = Field(default_factory=OptionSetSelection)
    categories: CategorySelection = Field(default_factory=CategorySelection)
    organisation_units: OrganisationUnitSelection = Field(default_factory=OrganisationUnitSelection)
    data_sets: TargetSelection = Field(default_factory=TargetSelection)
    event_programs: TargetSelection = Field(default_factory=TargetSelection)
    tracker_programs: TargetSelection = Field(default_factory=TargetSelection)
    tracked_entity_types: dict[str, str] = Field(default_factory=dict)
    examples: ExampleSelection = Field(default_factory=ExampleSelection)

    _normalize_identifier_base = field_validator("identifier_system_base")(strip_trailing_slash)

    @field_validator("tracked_entity_types")
    @classmethod
    def _known_subject_resource_types(cls, value: dict[str, str]) -> dict[str, str]:
        """Require an R4 resource type a tracked entity can be - a typo here mis-types every form of a program."""
        for uid, resource_type in value.items():
            if resource_type not in SUBJECT_RESOURCE_TYPES:
                raise ValueError(
                    f"tracked entity type {uid} is mapped to {resource_type!r}, which is not a FHIR resource "
                    f"type a tracked entity is published as: name one of {', '.join(SUBJECT_RESOURCE_TYPES)}"
                )
        return value

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        """Require an IANA zone name the tz database actually holds - a typo here mis-stamps every timestamp."""
        if value is None:
            return value
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(
                f"unknown IANA time zone {value!r}: name a zone from the tz database "
                "(e.g. 'Asia/Vientiane', 'Europe/Oslo', 'UTC')"
            ) from error
        return value

    @field_validator("locales")
    @classmethod
    def _normalize_locales(cls, value: list[str]) -> list[str]:
        """Accept BCP-47 or DHIS2-style tags and hold them in the BCP-47 form the emitters compare against."""
        return [normalize_locale(locale) for locale in value]


#: The raster tile template the capture UI's map draws under the organisation-unit boundaries.
#:
#: OpenStreetMap's standard tiles, because they need no key, no account, and no contract to try -
#: which is what a capture UI someone runs on a laptop for an afternoon needs. The policy that
#: comes with them is a volunteer-funded service with no SLA, so a deployment that serves this UI
#: to a district office points `[serve] basemap` at its own tile source; the guide says so where
#: the key is documented.
DEFAULT_BASEMAP_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

#: The `[serve] basemap` value that turns the tiles off, leaving the boundaries on a plain canvas.
#:
#: A word rather than an empty string: `basemap = ""` reads like an oversight in a config file,
#: and the whole point of the setting is that the boundary-only map is a deliberate posture - an
#: air-gapped instance, a deployment that may not talk to a tile vendor, a test run that must make
#: no external request.
BASEMAP_DISABLED = "none"


class ServeConfig(BaseModel):
    """How `d2w fhir serve` runs this project - the `[serve]` table of `fhir.toml`.

    Where a project is served from is a property of the project, not of the invocation: a
    developer whose DHIS2 stack already owns 8080 states another port once here and every
    `make serve` and bare `d2w fhir serve` in that project honours it. A command-line flag still
    wins over the table, and the table wins over these defaults.

    `ui` serves the capture UI at `/` alongside the FHIR routes. A project whose whole workflow is
    people filling in forms states it once here and gets the UI from every `make serve`.

    `basemap` is the raster tile template under the capture UI's organisation-unit map. It is the
    one setting here that makes the UI reach an origin other than this server, so it is stated
    rather than assumed: `"none"` turns the tiles off and leaves the boundaries on a plain canvas,
    which is the posture an air-gapped deployment wants and the one the browser test suite runs
    under.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = "127.0.0.1"
    port: int = 8080
    strict_codes: bool = False
    ui: bool = False
    basemap: str = DEFAULT_BASEMAP_TEMPLATE

    @property
    def basemap_template(self) -> str | None:
        """The tile template to draw, or None when the project has turned the basemap off."""
        return None if self.basemap.strip().lower() == BASEMAP_DISABLED else self.basemap


class FhirProjectConfig(BaseModel):
    """The full parsed `fhir.toml` document."""

    model_config = ConfigDict(extra="forbid")

    profile: str | None = None
    ig: IgConfig
    generate: GenerateConfig = Field(default_factory=GenerateConfig)
    serve: ServeConfig = Field(default_factory=ServeConfig)


class FhirProject(BaseModel):
    """A discovered FHIR IG project: parsed config plus where it lives on disk."""

    model_config = ConfigDict(frozen=True)

    config: FhirProjectConfig
    config_path: Path

    @property
    def project_root(self) -> Path:
        """Directory containing `fhir.toml`."""
        return self.config_path.parent

    @property
    def ig_directory(self) -> Path:
        """The SUSHI IG directory (`<project_root>/ig`)."""
        return self.project_root / "ig"

    @property
    def fsh_directory(self) -> Path:
        """The FSH source directory (`<project_root>/ig/input/fsh`)."""
        return self.ig_directory / "input" / "fsh"

    @property
    def resources_directory(self) -> Path:
        """The predefined-resource directory (`<project_root>/ig/input/resources`), loaded without a FSH compile."""
        return self.ig_directory / "input" / "resources"


def find_project_fhir_config(start: Path | None = None) -> Path | None:
    """Walk up from `start` (defaulting to `$PWD`) looking for `fhir.toml`."""
    cwd = start or Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / FHIR_CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


#: How close a declared name must be to the key that was written before it is offered as the one
#: that was meant. `difflib`'s own default: it carries a dropped letter (`max_lvl`), a transposition
#: (`stirct_codes`), and a wrong separator (`max-level`), and turns down a word that merely shares
#: a few characters with a field of the table.
_SUGGESTION_CUTOFF = 0.6


def _config_table_at(location: tuple[int | str, ...]) -> type[BaseModel] | None:
    """The config model one table path names, or None where the path leaves the tree of tables.

    Walked from `FhirProjectConfig` down the declared annotations, so the field names a suggestion
    is drawn from are the very ones that table accepts.
    """
    model: type[BaseModel] = FhirProjectConfig
    for segment in location:
        if not isinstance(segment, str):
            return None
        field = model.model_fields.get(segment)
        if field is None:
            return None
        annotation = field.annotation
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            return None
        model = annotation
    return model


def _unknown_key_diagnostic(location: tuple[int | str, ...]) -> str:
    """One `fhir.toml: unknown key ...` line, with the `did you mean ...?` line under it when one fits."""
    key = str(location[-1])
    table = ".".join(str(segment) for segment in location[:-1])
    where = f"in [{table}]" if table else "at the top level of the file"
    diagnostic = f"fhir.toml: unknown key {key!r} {where}"
    model = _config_table_at(location[:-1])
    if model is None:
        return diagnostic
    matches = difflib.get_close_matches(key, list(model.model_fields), n=1, cutoff=_SUGGESTION_CUTOFF)
    if not matches:
        return diagnostic
    return f"{diagnostic}\n  did you mean {matches[0]!r}?"


def load_fhir_config(path: Path) -> FhirProjectConfig:
    """Parse and validate a `fhir.toml` file, refusing any key the document does not declare.

    Every table declares its full key set, so a misspelled option is a refusal rather than a line
    that sets nothing: the key is named, placed in its table, and matched against the names that
    table accepts, and every unknown key in the file is reported in one pass. A refusal about a
    value rather than a name (a wrong type, a value outside its range) keeps pydantic's own report.
    """
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return FhirProjectConfig.model_validate(raw)
    except ValidationError as error:
        unknown_keys = [item["loc"] for item in error.errors() if item["type"] == "extra_forbidden"]
        if not unknown_keys:
            raise
        # Sorted by location so the diagnostics read as an outline of the document - a table before
        # its sub-tables - rather than in the order the validators happened to reach them.
        ordered = sorted(unknown_keys, key=lambda location: [str(segment) for segment in location])
        raise UnknownFhirConfigKeyError(*(_unknown_key_diagnostic(location) for location in ordered)) from error


def write_fhir_config(path: Path, config: FhirProjectConfig) -> None:
    """Write a `fhir.toml` with default permissions - it is committed project config, not a credential store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config.model_dump(exclude_none=True)), encoding="utf-8")


def load_project(start: Path | None = None) -> FhirProject:
    """Discover and load the nearest FHIR project, raising `NoFhirProjectError` when there is none."""
    path = find_project_fhir_config(start)
    if path is None:
        raise NoFhirProjectError(
            "no fhir.toml found in this directory or any parent. "
            "Run `d2w fhir init [DIRECTORY]` to scaffold a FHIR IG project first."
        )
    return FhirProject(config=load_fhir_config(path), config_path=path.resolve())

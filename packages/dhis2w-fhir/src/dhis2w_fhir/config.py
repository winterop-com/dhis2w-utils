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
from enum import StrEnum
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import tomli_w
from dhis2w_core.cli_errors import CliUserError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from dhis2w_fhir.i18n import normalize_locale
from dhis2w_fhir.ips import IdentityNominations, SectionMappings
from dhis2w_fhir.names import NamingSource, is_dhis2_uid, strip_trailing_slash
from dhis2w_fhir.r4 import SUBJECT_RESOURCE_TYPES
from dhis2w_fhir.resources.categories.schemas import CategorySelection
from dhis2w_fhir.resources.examples.schemas import ExampleSelection
from dhis2w_fhir.resources.option_sets.schemas import OptionSetSelection
from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitSelection
from dhis2w_fhir.resources.questionnaires.schemas import TargetSelection
from dhis2w_fhir.spool import SPOOL_RELATIVE_PATH
from dhis2w_fhir.status import IgStatus

FHIR_CONFIG_FILENAME = "fhir.toml"

#: Project directory validation reports land in - regenerable working artifacts, gitignored by the scaffold.
REPORTS_DIRECTORY = "reports"


class NoFhirProjectError(LookupError):
    """Raised when no `fhir.toml` is found walking up from the working directory."""


class UnknownFhirConfigKeyError(CliUserError):
    """Raised when `fhir.toml` names keys the configuration document does not declare."""


class MalformedFhirConfigError(CliUserError):
    """Raised when `fhir.toml` is not valid TOML, naming the file and where the parser stopped."""


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
    to bare `_CS`/`_Level_CS`. `tracked_entity_type` names the person-only registration form a
    tracked entity type publishes. `attribute_option_combo` names the vocabulary a data
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
    tracked_entity_type: str = "TET"

    @field_validator(
        "prefix",
        "option_set",
        "category",
        "attribute_option_combo",
        "data_set",
        "program",
        "program_stage",
        "tracked_entity_type",
    )
    @classmethod
    def _optional_token(cls, value: str) -> str:
        """Every token but organisation_unit may be empty, which drops it from the composed name."""
        return _validate_fsh_token(value, allow_empty=True)

    @field_validator("organisation_unit")
    @classmethod
    def _required_token(cls, value: str) -> str:
        """organisation_unit must be a non-empty FSH-name-safe token."""
        return _validate_fsh_token(value, allow_empty=False)


class HostileNamePosture(StrEnum):
    """What a generate run does with a DHIS2 name the IG publisher's own build cannot survive."""

    #: Publish every name byte-true and refuse the run when one of the gated names carries '<'. The
    #: name is then changed in DHIS2, or the selection narrowed, before a build is spent on it.
    REFUSE = "refuse"

    #: Publish the wording the rewrite produces - "5 to < 15 years" becomes "5 to under 15 years" -
    #: and note every name the guide states differently from the instance. DHIS2 is never modified,
    #: and every emitted identifier stays exactly as it is.
    SUBSTITUTE = "substitute"


class GenerateConfig(BaseModel):
    """Generation behaviour - the `[generate]` table of `fhir.toml`.

    The four data-definition tables select the questionnaire form kinds: `data_sets` picks
    aggregate data sets, `event_programs` picks programs without registration, `tracker_programs`
    picks programs with registration (one Questionnaire per program stage plus the program's own
    registration form), and `tracked_entity_forms` picks the tracked entity types that publish a
    person-only registration form - a form that creates a person and enrols them in nothing.
    Empty, `tracked_entity_forms` publishes one form per type the selected tracker programs
    track; the other three publish everything of their kind the instance holds.

    `hostile_names` is what the run does with a DHIS2 name carrying `<`, which the IG publisher
    writes into a page it strict-parses and then dies on. Unset, the run asks on a terminal and
    refuses without one, so a script is never left hanging on a question; `"refuse"` answers it
    with today's refusal and `"substitute"` publishes the rewritten wording. `d2w fhir generate
    --substitute-hostile-names` and `--refuse-hostile-names` answer it for one run.

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
    hostile_names: HostileNamePosture | None = None
    timezone: str | None = None
    locales: list[str] = Field(default_factory=list)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    option_sets: OptionSetSelection = Field(default_factory=OptionSetSelection)
    categories: CategorySelection = Field(default_factory=CategorySelection)
    organisation_units: OrganisationUnitSelection = Field(default_factory=OrganisationUnitSelection)
    data_sets: TargetSelection = Field(default_factory=TargetSelection)
    event_programs: TargetSelection = Field(default_factory=TargetSelection)
    tracker_programs: TargetSelection = Field(default_factory=TargetSelection)
    tracked_entity_forms: TargetSelection = Field(default_factory=TargetSelection)
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


#: The raster tile template the capture UI's map offers by default, under the boundaries.
#:
#: OpenStreetMap's standard tiles, because they need no key, no account, and no contract to try -
#: which is what a capture UI someone runs on a laptop for an afternoon needs. The policy that
#: comes with them is a volunteer-funded service with no SLA, so a deployment that serves this UI
#: to a district office states its own tile source in `[serve.basemaps]`; the guide says so where
#: the key is documented.
DEFAULT_BASEMAP_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

#: What that layer is called in the map's layer control.
DEFAULT_BASEMAP_NAME = "OpenStreetMap"

#: The `--basemap` value that serves no layers at all, leaving the boundaries on a plain canvas.
#:
#: A word rather than an empty flag: on the command line the absence of the option means "use the
#: table", so turning the tiles off from there needs something to say. In `fhir.toml` the same
#: posture is the empty list `basemaps = []`, which needs no word.
BASEMAP_DISABLED = "none"


class BasemapSource(BaseModel):
    """One named raster tile source the capture UI's map offers as a layer.

    `name` is what the map's layer control calls it and is the deployment's own word - this
    project never renames a source it was pointed at. `url` is the `{z}/{x}/{y}` template the
    tiles are fetched from, and it is the one thing in the whole UI that reaches an origin other
    than the server the page came from.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    url: str


#: What a project offers when it states no `[serve.basemaps]` at all: OpenStreetMap's standard tiles.
DEFAULT_BASEMAPS = (BasemapSource(name=DEFAULT_BASEMAP_NAME, url=DEFAULT_BASEMAP_TEMPLATE),)


#: What one page of the register listing carries when the client names no `_count`.
DEFAULT_REGISTER_PAGE_SIZE = 20

#: The largest `_count` the register listing honours; a client asking for more is served this many.
DEFAULT_REGISTER_PAGE_SIZE_LIMIT = 100

#: The most periods one data set read may name at once. A read is answered whole - `/api/dataValueSets`
#: offers no cursor - so the periods a request names are what bounds its cost, and twelve of them is a
#: year of monthly reporting, which is the span somebody comparing a form against last year asks for.
DEFAULT_DATA_SET_PERIOD_LIMIT = 12


class DataSetsConfig(BaseModel):
    """What a live run answers about the instance's aggregate data - the `[serve.data_sets]` table.

    The register's sibling, and the same posture: every default offers everything, and the table
    exists for the deployment that wants less. It says what this facade will tell a client about the
    values the instance holds for a data set, which is a decision a project makes once rather than
    one per invocation, so no flag overrides it.

    `responses` is the whole surface: false and `GET /facade/data-sets/{uid}/responses` answers the
    not-supported outcome naming this key, while the guide's own forms, the receipts, and the
    register are served exactly as they were. There is no second `enabled` key beside it, because
    there is no aggregate register for one to take away - a data set's values are the only thing
    this table is about.

    `page_size` is what one page carries when the client names no `_count`, and `page_size_limit` is
    the largest `_count` honoured: a client asking for more is served the limit rather than refused.

    `data_sets` means "the ones the guide publishes" when empty, which is what keeps this table
    absent from a project that publishes what it serves. Naming UIDs restricts the surface to them,
    and a data set outside the list is answered exactly as one the guide publishes no form for.

    `period_limit` is the most periods one read may name. Every read is answered whole, so the
    periods a request names are what bounds its cost; a request naming more is refused with the
    limit and the count it gave.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    responses: bool = True
    page_size: int = DEFAULT_REGISTER_PAGE_SIZE
    page_size_limit: int = DEFAULT_REGISTER_PAGE_SIZE_LIMIT
    data_sets: list[str] = Field(default_factory=list)
    period_limit: int = DEFAULT_DATA_SET_PERIOD_LIMIT

    @field_validator("page_size")
    @classmethod
    def _at_least_one_response_per_page(cls, value: int) -> int:
        """A page carrying no response is a listing that never ends, so the smallest page is one response."""
        if value < 1:
            raise ValueError(f"page_size is {value}: a page carries at least one response")
        return value

    @field_validator("period_limit")
    @classmethod
    def _at_least_one_period_per_read(cls, value: int) -> int:
        """A read naming no period is refused, so a limit below one would refuse every read there is."""
        if value < 1:
            raise ValueError(f"period_limit is {value}: a read names at least one period")
        return value

    @field_validator("data_sets")
    @classmethod
    def _dhis2_data_set_uids(cls, value: list[str]) -> list[str]:
        """The list names DHIS2 data sets by UID - a name or a code here would select nothing, silently."""
        for uid in value:
            if not is_dhis2_uid(uid):
                raise ValueError(
                    f"{uid!r} is not a DHIS2 UID (one letter followed by ten alphanumeric places): "
                    "name the data set by its UID, since names and codes are not unique in DHIS2"
                )
        return value

    @model_validator(mode="after")
    def _limit_holds_the_default(self) -> DataSetsConfig:
        """The limit is the largest page this run serves, so a default above it could never be served."""
        if self.page_size_limit < self.page_size:
            raise ValueError(
                f"page_size_limit is {self.page_size_limit} and page_size is {self.page_size}: the limit is "
                "the largest page this server serves, so it cannot be smaller than the page it serves by default"
            )
        return self


class TrackedEntitiesConfig(BaseModel):
    """The register a live run serves - the `[serve.tracked_entities]` table of `fhir.toml`.

    Tracked entities are the one thing this facade answers from the DHIS2 instance rather than from
    what it published, so what it will say about them is stated here rather than inferred from the
    guide. The table is register-wide: it says the same thing about every FHIR resource the published
    map takes a tracked entity type onto, because whether this process answers about the instance's
    subjects at all is one decision rather than one per resource type.

    `enabled` is the whole register: false and every register route answers the not-supported outcome
    and `/metadata` declares none of its resource types, in a live process exactly as in a compiled
    one. `listing` is the no-parameter search alone - false leaves identifier search untouched and
    refuses only the request that means "everybody", which is the posture for an instance whose
    register is not something a capture client may page through.

    `events` is one entity's own record - the events of its enrollments, each served as the
    QuestionnaireResponse the guide publishes for its program stage. False and the record is refused
    while identity is still served, which is the posture for a deployment that publishes who its
    subjects are and not what was recorded about them.

    `page_size` is what one page carries when the client names no `_count`, and `page_size_limit`
    is the largest `_count` honoured: a client asking for more is served the limit rather than
    refused, which is what FHIR says a server may do with a `_count` it will not meet.

    `tracked_entity_types` and `search_attributes` both mean "the ones the guide publishes" when
    empty, which is what keeps this table absent from a project that publishes what it serves.
    Naming types restricts search and listing alike to them. Naming attributes defines the search
    keys outright - a named attribute is a key whether or not DHIS2 declares it unique or searchable,
    because the operator naming it has said it names a subject here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    listing: bool = True
    events: bool = True
    page_size: int = DEFAULT_REGISTER_PAGE_SIZE
    page_size_limit: int = DEFAULT_REGISTER_PAGE_SIZE_LIMIT
    tracked_entity_types: list[str] = Field(default_factory=list)
    search_attributes: list[str] = Field(default_factory=list)

    @field_validator("page_size")
    @classmethod
    def _at_least_one_subject_per_page(cls, value: int) -> int:
        """A page carrying nobody is a listing that never ends, so the smallest page is one tracked entity."""
        if value < 1:
            raise ValueError(f"page_size is {value}: a page carries at least one tracked entity")
        return value

    @field_validator("tracked_entity_types", "search_attributes")
    @classmethod
    def _dhis2_uids(cls, value: list[str]) -> list[str]:
        """Both lists name DHIS2 objects by UID - a name or a code here would select nothing, silently."""
        for uid in value:
            if not is_dhis2_uid(uid):
                raise ValueError(
                    f"{uid!r} is not a DHIS2 UID (one letter followed by ten alphanumeric places): "
                    "name the object by its UID, since names and codes are not unique in DHIS2"
                )
        return value

    @model_validator(mode="after")
    def _limit_holds_the_default(self) -> TrackedEntitiesConfig:
        """The limit is the largest page this run serves, so a default above it could never be served."""
        if self.page_size_limit < self.page_size:
            raise ValueError(
                f"page_size_limit is {self.page_size_limit} and page_size is {self.page_size}: the limit is "
                "the largest page this server serves, so it cannot be smaller than the page it serves by default"
            )
        return self


class SearchBackend(StrEnum):
    """What answers a register search - the `[serve.search] backend` key.

    Two values ship. `"index"` is the name reserved for the OpenSearch backend of step 6 in
    `docs/fhir/design/projection.md`, and it is deliberately not a member here for the reason
    `ServeAuth` reserves `oauth2` in its own docstring: a value that parses and then has nothing to
    run on is worse than a value the file refuses by name, naming the key it refused.
    """

    #: The DHIS2 instance itself, asked one filtered tracker search per key while the caller waits.
    #: Search is as wide as `filter=<attribute>:eq:<value>` is, and every match is authorized by the
    #: instance on the read that resolves it.
    DHIS2 = "dhis2"

    #: The materialized projection `d2w fhir sync` fills, asked one indexed query however many keys
    #: and types are in scope. Finding is answered from the store and stated as of its cursor; the
    #: record behind a match is still read from the instance under the caller's own credentials, so
    #: what the projection decides is who is on the page and what DHIS2 decides is who may see them.
    #: Needs `[serve.projection] store` to name a store, and the run is refused when it names none.
    PROJECTION = "projection"


class SearchConfig(BaseModel):
    """How a register search is answered - the `[serve.search]` table of `fhir.toml`.

    A register search reaches the instance through one seam, `NameSearchIndex`, and this table says
    which backend sits behind it. `backend = "dhis2"` is the instance itself: the search a live run
    has always run, with the authorization properties it has always had - the matches a search
    discloses are identifiers, and the record behind one is read back under the caller's own
    credentials, so DHIS2 decides per match per caller what may be seen.

    `backend = "projection"` moves the finding half into the store `[serve.projection]` names and
    leaves the disclosing half exactly where it is. A search then costs one indexed query rather
    than one tracker query per key per tracked entity type, it answers a name the exact-match filter
    could never answer, and every answer states the cursor it is as of. What it does not do is hand
    over a record the instance has not authorized: each match is read back live under the caller's
    own credentials, which is the R9 posture of `docs/fhir/design/projection.md` section 6 in full.

    The table has no command-line flag. Which searches this server answers is its contract - it is
    what `/metadata` declares - rather than a property of one invocation, which is the rule
    `[serve.tracked_entities]` follows for the same reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: SearchBackend = SearchBackend.DHIS2


#: Where a project's materialized projection lives when `[serve.projection]` names no other path.
#:
#: Beside the spool, under the project root, because the two are the same kind of thing about this
#: project: what `d2w fhir serve` owns on disk. The spool is what a client sent and the projection is
#: what DHIS2 held, and neither is source - the scaffold gitignores `.serve/` whole.
DEFAULT_PROJECTION_RELATIVE_PATH = ".serve/projection.sqlite"

#: How far back before its own watermark an incremental sync re-reads, in seconds.
#:
#: Five minutes. `updatedAfter` boundary semantics, clock skew between this host and the instance,
#: and transactions in flight at the instant of a poll all drop rows at the edge, so a sync re-polls
#: from `watermark - overlap` and relies on a write being idempotent by resource id
#: (`docs/fhir/design/projection.md` section 5.2, rule 2). The window is a number somebody chose
#: rather than a constant an incident discovers.
DEFAULT_SYNC_OVERLAP_SECONDS = 300


class ProjectionBackend(StrEnum):
    """Which durable store holds this project's materialized projection - `[serve.projection] store`.

    `"postgres"` is the name reserved for the document store of step 7 in
    `docs/fhir/design/projection.md`, and it is deliberately not a member here for the reason
    `SearchBackend` reserves `"index"`: a value that parses and then has nothing to run on is worse
    than a value the file refuses by name.
    """

    #: No projection. The default, and the whole of what makes a facade configured without one behave
    #: exactly as it always did: `d2w fhir sync` refuses and names this key, and every register answer
    #: is read from the instance while the caller waits.
    NONE = "none"

    #: One SQLite file under the project root, over SQLAlchemy and aiosqlite. Needs no service, no
    #: operator, and no port - which is what makes a synced FHIR server something a district office
    #: can run on the machine it already has.
    SQLITE = "sqlite"


class ProjectionConfig(BaseModel):
    """The materialized projection this project holds - the `[serve.projection]` table of `fhir.toml`.

    A projection is a durable copy of the mapped scope of a DHIS2 instance, held as the FHIR
    resources this project's map publishes, filled by `d2w fhir sync` and written by nothing else.
    It is derived, it is rebuildable from zero, and every answer served out of it states the instant
    it is as of. `docs/fhir/design/projection.md` section 4 is the doctrine in seven rules, and the
    first of them is the one this table exists under: DHIS2 stays the record for everything DHIS2
    can hold, and this holds a copy.

    `store` is which backend holds it, and `"none"` - the default - is no projection at all. That is
    not a degraded mode: a facade reading the instance per request is the product, it needs no
    operator, and nothing in this table may make it harder to run
    (`docs/fhir/design/projection.md` R11).

    `path` is where a SQLite projection's one file lives, relative to the project root unless it is
    absolute - the same rule `[serve] spool_dir` follows, because the two are the same kind of
    directory work. Deleting the file is a supported operation: the next `d2w fhir sync` fills it
    from zero, which is what "rebuildable" means when it is not frightening.

    `overlap_seconds` is how far back before its own watermark an incremental run re-reads. A sync
    that polled from exactly its watermark would drop the rows written in the instant it was reading,
    so it re-reads a window and relies on a write being idempotent by resource id.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    store: ProjectionBackend = ProjectionBackend.NONE
    path: str = DEFAULT_PROJECTION_RELATIVE_PATH
    overlap_seconds: int = DEFAULT_SYNC_OVERLAP_SECONDS

    @field_validator("path")
    @classmethod
    def _names_a_file(cls, value: str) -> str:
        """An empty path names nothing, and a project that states one has to mean it."""
        if value.strip() == "":
            raise ValueError(
                "path is empty: name the file the projection lives in, relative to the project root "
                f"or absolute, or leave the key out for {DEFAULT_PROJECTION_RELATIVE_PATH!r}"
            )
        return value

    @field_validator("overlap_seconds")
    @classmethod
    def _not_negative(cls, value: int) -> int:
        """A negative overlap would poll from after the watermark, which is how a sync loses rows silently."""
        if value < 0:
            raise ValueError(
                f"overlap_seconds is {value}: an incremental run re-reads a window BEFORE its own "
                "watermark, so the window is zero or more seconds"
            )
        return value

    def enabled(self) -> bool:
        """Whether this project holds a projection at all, which is the one thing every caller asks first."""
        return self.store is not ProjectionBackend.NONE


class ServeAuth(StrEnum):
    """How the served facade decides who is calling it - the `[serve] auth` posture.

    Four postures ship, and they are a ladder rather than a menu: `none` serves every caller,
    `token` takes a secret this deployment issued, `dhis2` takes the caller's own DHIS2 credentials,
    and `jwt` takes a token an external OpenID Connect issuer minted, validated here against that
    issuer's JWKS. Climbing a rung is editing `[serve] auth` and the table beside it.

    `oauth2` is the name reserved for an authorization server this facade runs itself, and is
    deliberately not a value here: DHIS2 2.43.1's own authorization server 500s for any client the
    API creates (BUGS.md 96), so a project could state it and nothing would answer. A posture that
    parses and then refuses is worse than one that is not offered, so the reservation lives in this
    docstring and in `docs/fhir/301-serving.md` rather than in the enum. A deployment that wants
    tokens from an authorization server today states `jwt` and names the one it already runs.
    """

    #: Every caller is served. The default, and the posture the loopback demo runs in.
    NONE = "none"

    #: A static bearer token out of `D2W_FHIR_SERVE_TOKENS`, compared in constant time.
    TOKEN = "token"

    #: The caller's own DHIS2 credentials, checked against the instance this run reads.
    DHIS2 = "dhis2"

    #: A JWT an external OIDC issuer minted, verified here against that issuer's published keys.
    JWT = "jwt"


class ServeJwtConfig(BaseModel):
    """Which issuer the `jwt` posture trusts, and what one of its tokens means - the `[serve.jwt]` table.

    `issuer` is the OpenID Connect issuer identifier, the value its tokens carry as `iss`. The
    facade reads `{issuer}/.well-known/openid-configuration` once while it starts, takes the
    `jwks_uri` from it, and verifies every token against the keys published there. It is the one
    key the posture cannot run without, and a `jwt` run that names none is refused before the socket
    opens rather than at the first caller.

    `audience` is checked only when it is stated. An issuer that mints tokens for several audiences
    is minting tokens this facade should not accept on another audience's behalf, so a deployment
    sharing an issuer with other services states the value it was registered under. Left out, a
    token this issuer signed is a token this facade takes.

    `username_claim` names the claim whose value becomes the request identity - what a receipt
    records as its submitter. `preferred_username` is the OpenID Connect claim for exactly that, and
    it is the default; a deployment whose issuer puts the DHIS2 username somewhere else names that
    claim instead. A token that carries no such claim is refused: an identity nobody stated is not
    one to invent.

    `forward_bearer` is whether a register read carries the caller's token on to DHIS2. It is false
    by default and it is the honest default: DHIS2 accepts a foreign issuer's JWT only when it was
    configured to trust the same issuer (`oidc.jwt.token.authentication.enabled`), and a facade that
    quietly read the register as its own profile instead would answer every caller with that
    profile's rights. So under `forward_bearer = false` the live register is not answered at all,
    and the refusal says what would make it answerable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str | None = None
    """The OIDC issuer identifier, or None when this project's table states none."""

    audience: str | None = None
    """The `aud` every accepted token must carry, or None to accept whatever this issuer minted."""

    username_claim: str = "preferred_username"
    """The claim whose value names the caller, and becomes the identity a receipt records."""

    forward_bearer: bool = False
    """Whether a register read carries the caller's own token to DHIS2 - see the note above."""

    @field_validator("issuer")
    @classmethod
    def _names_an_issuer(cls, value: str | None) -> str | None:
        """A blank issuer states nothing, and a stated one is the `https://` identifier its tokens carry."""
        if value is None or value.strip() == "":
            return None
        issuer = value.strip().rstrip("/")
        scheme = urlsplit(issuer).scheme
        if scheme not in {"http", "https"}:
            raise ValueError(
                f"{value!r} is not an issuer identifier: name the `https://` URL the issuer publishes as its "
                "own `iss`, which is what this server appends `/.well-known/openid-configuration` to"
            )
        return issuer

    @field_validator("username_claim")
    @classmethod
    def _names_a_claim(cls, value: str) -> str:
        """A blank claim name would read every token as naming nobody, which is a posture nobody asked for."""
        if value.strip() == "":
            raise ValueError(
                "username_claim is empty: name the claim whose value identifies the caller, or leave the "
                "key out for `preferred_username`"
            )
        return value.strip()


class ServeAuthScope(StrEnum):
    """How much of the served surface one `[serve] auth` posture covers."""

    #: The state-changing surface only: `POST /QuestionnaireResponse`. Reads stay open.
    WRITE = "write"

    #: Everything but `/metadata`, which stays open so a client can read the posture it must meet.
    ALL = "all"


class ServeConfig(BaseModel):
    """How `d2w fhir serve` runs this project - the `[serve]` table of `fhir.toml`.

    Where a project is served from is a property of the project, not of the invocation: a
    developer whose DHIS2 stack already owns 8080 states another port once here and every
    `make serve` and bare `d2w fhir serve` in that project honours it. A command-line flag still
    wins over the table, and the table wins over these defaults.

    `ui` serves the capture UI at `/` alongside the FHIR routes. A project whose whole workflow is
    people filling in forms states it once here and gets the UI from every `make serve`.

    `basemaps` names the raster tile layers the capture UI's organisation-unit map offers, in the
    order it offers them; the first is the one the map opens with. The layer control always carries
    a `None` entry beside them, so drawing the boundaries on a plain canvas is a click rather than a
    config change. An empty list is therefore the air-gapped posture in full - the only layer on
    offer is `None`, and the page reaches no origin but this server. It is the one part of this
    table that makes the browser talk to anybody else, which is why it is stated rather than
    inferred.

    `capture` is whether this server receives submissions at all. True - the default - mounts the
    create route, declares `create` on QuestionnaireResponse in `/metadata`, and lets the capture
    screens submit. False is the viewer posture: the guide is published, read, searched, and
    `$generate`d against, and nothing is received. `$generate` stays because it is a read of a
    published form that happens to answer with a draft, and writes nothing here.

    THE RECEIPTS STAY READABLE WITH CAPTURE OFF. `read` and `search-type` on QuestionnaireResponse
    are untouched by this dial, and so is `GET /facade/spool`. The receipts a project already holds are as
    true as they were, and a server that stopped answering for them would make every id it handed
    out at capture time expire on the day somebody edited one line of this file. Only `create` goes.

    `spool_dir` is where the receipt tree lives - `received/`, `forwarded/`, `rejected/`, and the
    `malformed/` holding pen beside them. A relative path is resolved against the project root; an
    absolute one is taken as written. It is a `[serve]` key because the spool belongs to the serve
    surface - this server is what writes it - and `d2w fhir forward` reads the same key rather than
    carrying a spool location of its own, so the process that writes a receipt and the process that
    drains it can never disagree about where it is.

    `[serve.tracked_entities]` is the register: whether the instance's tracked entities are served at
    all, whether they can be listed rather than only searched for, and how a listing is paged. It is
    one of the two parts of this table that say what a live run will tell a client about the instance
    behind it.

    `[serve.data_sets]` is the other: whether a live run answers what the instance holds for a data
    set, which data sets it answers for, how a page is sized, and how many periods one read may name.
    The register says what this facade will tell a client about the instance's subjects, and this
    says what it will tell them about its aggregate values.

    `[serve.search]` is what answers a register search - the instance itself, or the materialized
    projection beside it. It says how a lookup is answered where `[serve.tracked_entities]` says
    what may be looked up.

    `[serve.projection]` is the materialized projection: which store holds a durable copy of the
    mapped scope of the instance, where that store lives, and how far back an incremental sync
    re-reads. `store = "none"` - the default - is no projection at all, which is the posture every
    facade started before this table existed runs in and will keep running in.

    `auth` is who the facade serves, and `auth_scope` is how much of it the posture covers. The key
    is `ServeAuth | None` rather than `ServeAuth` because absence is a third state this table has to
    be able to tell apart: a project that never wrote the key is served on loopback with no
    authentication, and refused on any other interface, so that binding the world is a sentence
    somebody wrote rather than a default nobody read. `auth = "none"` written out is that sentence.

    `[serve.jwt]` is what `auth = "jwt"` runs on: the issuer whose tokens this facade takes, the
    audience it checks when one is stated, the claim that names the caller, and whether a register
    read carries the caller's token on to DHIS2. It is always present as a table of defaults, so a
    `jwt` run that names no issuer is refused by the key's name rather than by a missing section.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = "127.0.0.1"
    port: int = 8080
    auth: ServeAuth | None = None
    """The posture, or None when this project's table states none - see the note above on absence."""

    auth_scope: ServeAuthScope = ServeAuthScope.WRITE
    jwt: ServeJwtConfig = Field(default_factory=ServeJwtConfig)
    """What the `jwt` posture runs on - the `[serve.jwt]` table, defaults when the project writes none."""

    strict_codes: bool = False
    capture: bool = True
    ui: bool = False
    spool_dir: str = SPOOL_RELATIVE_PATH
    basemaps: list[BasemapSource] = Field(default_factory=lambda: list(DEFAULT_BASEMAPS))
    tracked_entities: TrackedEntitiesConfig = Field(default_factory=TrackedEntitiesConfig)
    data_sets: DataSetsConfig = Field(default_factory=DataSetsConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    projection: ProjectionConfig = Field(default_factory=ProjectionConfig)

    @model_validator(mode="after")
    def _a_projection_search_has_a_projection(self) -> ServeConfig:
        """`[serve.search] backend = "projection"` needs a store to search, and this file has to name it.

        Refused here rather than at the first lookup, because a server that starts and then answers
        every search with a failure is a decision nobody reads until somebody meets it - and the two
        keys are three lines apart in the same file.
        """
        if self.search.backend is SearchBackend.PROJECTION and not self.projection.enabled():
            raise ValueError(
                'serve.search.backend is "projection" and serve.projection.store is "none": a search '
                "answered from the materialized projection needs one to read, so state "
                '`[serve.projection] store = "sqlite"` and fill it with `d2w fhir sync`'
            )
        return self

    @field_validator("spool_dir")
    @classmethod
    def _names_a_directory(cls, value: str) -> str:
        """An empty spool directory names nothing, and a project that states one has to mean it."""
        if value.strip() == "":
            raise ValueError(
                "spool_dir is empty: name a directory the receipts live in, relative to the project "
                f"root or absolute, or leave the key out for {SPOOL_RELATIVE_PATH!r}"
            )
        return value


def basemaps_from_options(values: list[str]) -> list[BasemapSource]:
    """Read repeated `--basemap` values as the layers a run offers, or refuse the ones that say nothing.

    Each value is either `Name=https://.../{z}/{x}/{y}.png` or a bare template, whose host becomes
    the layer's name - the honest word for a source this project was handed and knows nothing else
    about. The split is on the first `=` and only when what precedes it is a plain word: a template
    carrying `?api_key=...` is one url, not a name and a url.

    The single value `none` serves no layers, which is the command line's way of saying what
    `basemaps = []` says in the table. Naming it beside a real layer is a contradiction rather than
    a shorthand, so it is refused instead of guessed at.
    """
    disabled = [value for value in values if value.strip().lower() == BASEMAP_DISABLED]
    if disabled and len(values) > 1:
        raise ValueError(
            f"--basemap {BASEMAP_DISABLED} serves no layers at all, so it cannot be combined with "
            f"{len(values) - len(disabled)} other --basemap value(s): pass one or the other"
        )
    if disabled:
        return []
    return [_basemap_from_option(value) for value in values]


class OverwritePosture(StrEnum):
    """What a drain does with an aggregate value a forwarded receipt of this spool already sent."""

    #: Post the value and name it. DHIS2 keeps the newest number for a cell, and this posture is the
    #: toolkit agreeing with that: the instance ends up holding what the newest submission carried,
    #: and the run states every value it replaced, the receipt that sent it before, and when that
    #: receipt arrived - which is the one thing no import summary can say.
    ALLOW = "allow"

    #: Refuse the whole response and leave it in the queue with a record naming every covered value.
    #: The posture for a deployment where forwarded data changes only through a declared correction.
    REFUSE = "refuse"


class CorrectionPosture(StrEnum):
    """Whether this deployment accepts a submission that amends one it already forwarded."""

    #: Amendment is not something this deployment does. A submission that declares itself a
    #: correction is refused, and forwarded data changes only through whatever `overwrites` allows.
    OFF = "off"

    #: A submission carrying `status = "amended"` and naming the receipt it corrects is a correction,
    #: and the identity it lands on is the corrected receipt's rather than its own.
    AMEND = "amend"


class WithdrawalPosture(StrEnum):
    """Whether this deployment retracts from DHIS2 what one of its forwarded receipts landed."""

    #: Nothing this project forwarded is retracted. `d2w fhir withdraw` refuses, naming this key.
    OFF = "off"

    #: A forwarded receipt can be retracted, which deletes the object it landed in DHIS2 and files
    #: the receipt under `withdrawn/`. Terminal: DHIS2 burns the UID, so the receipt never forwards
    #: again - see `docs/fhir/design/data-lifecycle.md`.
    RETRACT = "retract"


class ForwardConfig(BaseModel):
    """How `d2w fhir forward` drains this project's spool - the `[forward]` table of `fhir.toml`.

    `live` is what a project with no compiled guide forwards through. A drain reads the published
    Questionnaires and terminology to translate a receipt against, and a project that has run SUSHI
    has them on disk. A project captured through `d2w fhir serve --live` has never built anything,
    so the same documents are built off the instance instead - one full metadata read per drain,
    where a compiled guide costs a directory listing.

    Left on, that read happens only when there is no compiled guide to read instead; a project that
    builds its IG never pays it. Turned off, a drain against a project with no compiled guide is
    refused and says which two commands produce one - which is the posture for a deployment that
    wants its forwards reading a reviewed, published guide and nothing else.

    `import` is the posture every drain of this project runs in when the command line says nothing.
    False - the default - is a dry run: every payload still goes to the real endpoint under that
    endpoint's own validate-only mode, so DHIS2 decides the answer while nothing is written and no
    receipt moves. True makes the bare `d2w fhir forward` of this project commit, which is what a
    project whose drains are routine states once rather than remembering `--import` every time. The
    field is `import_responses` in Python because `import` is a Python keyword; the key in the file
    is `import`, and the file accepts no other spelling of it.

    `register_completeness` is the second write an aggregate response asks for. An aggregate
    submission reporting itself `completed` marks its data set complete for the very tuple its
    values landed under, once DHIS2 has taken them. True - the default - honours that; false leaves
    the values imported and registers nothing, which is the posture for a deployment where
    completeness is somebody else's decision to record.

    `overwrites` is what a drain does with an aggregate value a forwarded receipt of this spool
    already sent, arriving in a response that declares no correction. `"allow"` - the default -
    posts it and names it: DHIS2 keeps the newest number for a cell, and the toolkit follows the
    platform it writes into rather than inventing a stricter one. `"refuse"` posts no payload
    holding such a value; the response stays in the queue with a record naming every covered value
    and the receipt that sent it, which is the posture for a deployment where forwarded data changes
    only through a declared correction. The dial reaches aggregate values alone - a tracker event
    carries its own DHIS2 identity, so it collides rather than overwriting.

    `corrections` and `withdrawals` are the other half of the same question, and they govern a
    *marked* submission where `overwrites` governs an unmarked one. A correction says which receipt
    it corrects; an overwrite says nothing and is simply a second capture of the same tuple. Both
    default to `"off"`, because a deployment that publishes forms and forwards them is not thereby a
    deployment that lets a submitter reach back into what DHIS2 already holds. `corrections =
    "amend"` accepts a submission that names the receipt it amends and lands on that receipt's own
    DHIS2 identity; `withdrawals = "retract"` is what `d2w fhir withdraw` requires before it deletes
    anything. Withdrawal is terminal - DHIS2 burns the UID it deletes, so the withdrawn receipt can
    never be forwarded again - which is why the capability is stated rather than assumed.

    A flag on the command line wins over all six keys for one run, and either key wins over these
    defaults - the same order `[serve]` states for its own dials.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    live: bool = True
    import_responses: bool = Field(default=False, alias="import")
    register_completeness: bool = True
    overwrites: OverwritePosture = OverwritePosture.ALLOW
    corrections: CorrectionPosture = CorrectionPosture.OFF
    withdrawals: WithdrawalPosture = WithdrawalPosture.OFF


class IpsConfig(BaseModel):
    """What this instance says about a person beyond their identifiers - the `[ips]` tables of `fhir.toml`.

    `[ips.identity]` nominates the tracked entity attribute carrying a person's name, birth date, and
    sex, and maps that sex attribute's values onto R4's `administrative-gender` codes. DHIS2 holds no
    field that means any of those, so the nomination is the instance's own statement or there is
    nothing to publish - `docs/fhir/design/ips.md` section 4 is the argument, and section 9's phase 1
    is what the nomination reaches: the register's own `Patient`.

    `[ips.sections]` nominates which recorded values belong in which section of a patient summary,
    and `[ips.sections.immunizations]` is the one section phase 2 maps. Section 5 is the argument:
    DHIS2 marks no data element as an immunisation, so the section content of a summary is stated or
    it is absent.

    `enabled` is the dial the whole summary surface hangs off, and it is false by default. A patient
    summary is a clinical document about a person, and publishing one is a decision a deployment
    makes rather than a default it inherits: `d2w fhir serve` answers `$summary` on a register whose
    subjects are people only where this key says so, and refuses it by name where it does not
    (R7 in section 8, "Gated and additive"). The register, the record, and everything else this
    facade serves are untouched either way - a summary is a new read over reads that already exist.

    The tables are always present as tables of defaults, for the reason `[serve.jwt]` is: a project
    that nominates nothing is refused by the key's name rather than by a missing section, and its
    register answers exactly what it answered before they existed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    sections: SectionMappings = Field(default_factory=SectionMappings)
    identity: IdentityNominations = Field(default_factory=IdentityNominations)


class FhirProjectConfig(BaseModel):
    """The full parsed `fhir.toml` document."""

    model_config = ConfigDict(extra="forbid")

    profile: str | None = None
    ig: IgConfig
    generate: GenerateConfig = Field(default_factory=GenerateConfig)
    serve: ServeConfig = Field(default_factory=ServeConfig)
    forward: ForwardConfig = Field(default_factory=ForwardConfig)
    ips: IpsConfig = Field(default_factory=IpsConfig)


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
    # The names the file declares, which is the alias wherever a table has one: suggesting the
    # Python field name would answer a misspelling with a second name the file also refuses.
    declared = [field.alias or name for name, field in model.model_fields.items()]
    matches = difflib.get_close_matches(key, declared, n=1, cutoff=_SUGGESTION_CUTOFF)
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
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise MalformedFhirConfigError(f"{path}: not valid TOML - {error}") from error
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
    """Write a `fhir.toml` with default permissions - it is committed project config, not a credential store.

    Written under the keys the file declares rather than the Python field names, so what is written
    is what `load_fhir_config` reads back: `[forward] import` is `import_responses` in Python only
    because the file's own name for it is a keyword there.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config.model_dump(exclude_none=True, by_alias=True)), encoding="utf-8")


def _basemap_from_option(value: str) -> BasemapSource:
    """One `--basemap` value as a named source, naming it after its host when the value names nothing."""
    stated = value.strip()
    if not stated:
        raise ValueError("--basemap was given an empty value: name a tile template, or `none` for no layers")
    name, separator, url = stated.partition("=")
    if separator and _is_plain_name(name):
        return BasemapSource(name=name.strip(), url=url.strip())
    return BasemapSource(name=urlsplit(stated).hostname or stated, url=stated)


def _is_plain_name(candidate: str) -> bool:
    """Whether what precedes the first `=` is a layer's name rather than the head of a url."""
    return candidate.strip() != "" and ":" not in candidate and "/" not in candidate


def load_project(start: Path | None = None) -> FhirProject:
    """Discover and load the nearest FHIR project, raising `NoFhirProjectError` when there is none."""
    path = find_project_fhir_config(start)
    if path is None:
        raise NoFhirProjectError(
            "no fhir.toml found in this directory or any parent. "
            "Run `d2w fhir init [DIRECTORY]` to scaffold a FHIR IG project first."
        )
    return FhirProject(config=load_fhir_config(path), config_path=path.resolve())

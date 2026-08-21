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


class GenerateConfig(BaseModel):
    """Generation behaviour - the `[generate]` table of `fhir.toml`.

    The four data-definition tables select the questionnaire form kinds: `data_sets` picks
    aggregate data sets, `event_programs` picks programs without registration, `tracker_programs`
    picks programs with registration (one Questionnaire per program stage plus the program's own
    registration form), and `tracked_entity_forms` picks the tracked entity types that publish a
    person-only registration form - a form that creates a person and enrols them in nothing.
    Empty, `tracked_entity_forms` publishes one form per type the selected tracker programs
    track; the other three publish everything of their kind the instance holds.

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

    One value ships. `"index"` is the name reserved for the OpenSearch backend of step 6 in
    `docs/fhir/design/projection.md`, and it is deliberately not a member here for the reason
    `ServeAuth` reserves `oauth2` in its own docstring: a value that parses and then has nothing to
    run on is worse than a value the file refuses by name, naming the key it refused.
    """

    #: The DHIS2 instance itself, asked one filtered tracker search per key while the caller waits.
    #: Search is as wide as `filter=<attribute>:eq:<value>` is, and every match is authorized by the
    #: instance on the read that resolves it.
    DHIS2 = "dhis2"


class SearchConfig(BaseModel):
    """How a register search is answered - the `[serve.search]` table of `fhir.toml`.

    A register search reaches the instance through one seam, `NameSearchIndex`, and this table says
    which backend sits behind it. `backend = "dhis2"` is the instance itself: the search a live run
    has always run, with the authorization properties it has always had - the matches a search
    discloses are identifiers, and the record behind one is read back under the caller's own
    credentials, so DHIS2 decides per match per caller what may be seen.

    The table has no command-line flag. Which searches this server answers is its contract - it is
    what `/metadata` declares - rather than a property of one invocation, which is the rule
    `[serve.tracked_entities]` follows for the same reason.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: SearchBackend = SearchBackend.DHIS2


class ServeAuth(StrEnum):
    """How the served facade decides who is calling it - the `[serve] auth` posture.

    Three postures ship. `oauth2` is the name reserved for the fourth and is deliberately not a
    value here: DHIS2 2.43.1's own authorization server 500s for any client the API creates
    (BUGS.md 96), so a project could state it and nothing would answer. A posture that parses and
    then refuses is worse than one that is not offered, so the reservation lives in this docstring
    and in `docs/fhir/301-serving.md` rather than in the enum.
    """

    #: Every caller is served. The default, and the posture the loopback demo runs in.
    NONE = "none"

    #: A static bearer token out of `D2W_FHIR_SERVE_TOKENS`, compared in constant time.
    TOKEN = "token"

    #: The caller's own DHIS2 credentials, checked against the instance this run reads.
    DHIS2 = "dhis2"


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
    are untouched by this dial, and so is `GET /spool`. The receipts a project already holds are as
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
    the one part of this table that says what a live run will tell a client about the instance behind
    it.

    `[serve.search]` is what answers a register search - the instance itself today, and a search
    index when one is configured. It says how a lookup is answered where `[serve.tracked_entities]`
    says what may be looked up.

    `auth` is who the facade serves, and `auth_scope` is how much of it the posture covers. The key
    is `ServeAuth | None` rather than `ServeAuth` because absence is a third state this table has to
    be able to tell apart: a project that never wrote the key is served on loopback with no
    authentication, and refused on any other interface, so that binding the world is a sentence
    somebody wrote rather than a default nobody read. `auth = "none"` written out is that sentence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = "127.0.0.1"
    port: int = 8080
    auth: ServeAuth | None = None
    """The posture, or None when this project's table states none - see the note above on absence."""

    auth_scope: ServeAuthScope = ServeAuthScope.WRITE
    strict_codes: bool = False
    capture: bool = True
    ui: bool = False
    spool_dir: str = SPOOL_RELATIVE_PATH
    basemaps: list[BasemapSource] = Field(default_factory=lambda: list(DEFAULT_BASEMAPS))
    tracked_entities: TrackedEntitiesConfig = Field(default_factory=TrackedEntitiesConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)

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


class FhirProjectConfig(BaseModel):
    """The full parsed `fhir.toml` document."""

    model_config = ConfigDict(extra="forbid")

    profile: str | None = None
    ig: IgConfig
    generate: GenerateConfig = Field(default_factory=GenerateConfig)
    serve: ServeConfig = Field(default_factory=ServeConfig)
    forward: ForwardConfig = Field(default_factory=ForwardConfig)


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

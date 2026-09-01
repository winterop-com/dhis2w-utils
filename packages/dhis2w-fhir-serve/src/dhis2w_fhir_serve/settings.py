"""The settings the FHIR facade app factory is built from, and how one invocation resolves them."""

from __future__ import annotations

from pathlib import Path

from dhis2w_client.profile import NoProfileError
from dhis2w_fhir.config import (
    DEFAULT_BASEMAPS,
    BasemapSource,
    DataSetsConfig,
    FhirProject,
    ProjectionConfig,
    SearchConfig,
    ServeAuth,
    ServeAuthScope,
    ServeJwtConfig,
    TrackedEntitiesConfig,
    basemaps_from_options,
)
from dhis2w_fhir.service import GenerationProfile, resolve_generation_profile
from dhis2w_fhir.spool import SPOOL_RELATIVE_PATH
from pydantic import BaseModel, ConfigDict, Field

from dhis2w_fhir_serve.auth import preflight_auth
from dhis2w_fhir_serve.capture.validate import DEFAULT_STRICT_CODES
from dhis2w_fhir_serve.store import COMPILED_RESOURCES_RELATIVE_PATH, CompiledIgMissingError


class ServeSettings(BaseModel):
    """Everything the app factory needs to build the FHIR facade for one project.

    Host and port stay uvicorn-side: they describe where the process listens, not what
    it serves, so the factory never sees them. `live` selects a store built from a live
    DHIS2 instance over the compiled IG on disk, `profile` names the DHIS2 profile that
    store connects with, and `strict_codes` rejects a received answer whose code is not
    in the served terminology instead of recording a warning.

    `strict_codes` is the runtime source every capture is validated against; the default it
    starts from lives with the capture path, in `capture.validate.DEFAULT_STRICT_CODES`.

    `capture` is whether this process receives submissions. It comes off `[serve] capture` and no
    flag overrides it, for the reason `tracked_entities` states below: it changes what `/metadata`
    declares, which is this server's contract rather than a property of one invocation. False mounts
    a refusal in place of the create route, drops `create` from the QuestionnaireResponse entry, and
    tells the screens not to offer a Submit. Everything else about that resource type stays: the
    receipts already on disk are read, searched, and counted exactly as they were.

    `ui` serves the built capture UI at `/`, same-origin with the FHIR routes it talks to. It is
    off by default: a facade is an endpoint first, and a process answering `/metadata` for a
    scripted client has no reason to also hold a React bundle open.

    `spool_dir` is where the receipt tree lives, off `[serve] spool_dir` - relative to the project
    root unless it is absolute. It is resolved through `dhis2w_fhir.spool.resolve_spool_root`, the
    same function `d2w fhir forward` resolves it through, because the writer and the drainer landing
    on two different directories would be a receipt nothing ever forwards.

    `basemaps` are the raster tile layers the UI's organisation-unit map offers under the
    boundaries, first one first, and an empty list offers none. They live here rather than being
    read from the project at request time for the same reason `strict_codes` does: a flag may
    override the table, so the resolved value is a property of this run.

    `dhis2_base_url` is the address of the instance this run resolved a profile for, and None when
    it resolved none - a compiled guide served on a machine that names no profile is a whole,
    supported posture. It is what the UI links an organisation unit, a form, or a data element out
    to; with no address there are no links, which is the honest rendering of not knowing which of a
    hundred DHIS2 instances a guide was generated from. The profile's NAME and its credentials stay
    here and never reach a browser - see `dhis2w_fhir_serve.routes.uiconfig`.

    `auth` is who this facade serves and `auth_scope` is how much of it the posture covers. Both are
    resolved values rather than the table read back, because a flag may state either - and the
    posture's NAME is the one part of it that crosses to a browser, through `/facade/uiconfig`. No token, no
    password, and no header ever reaches these settings: `dhis2w_fhir_serve.auth.AuthState` holds what
    a check needs, on the application, for exactly that reason.

    `jwt` is what the `jwt` posture runs on, off `[serve.jwt]` with no flag over it: which issuer this
    facade trusts, the audience it insists on where one is stated, the claim that names the caller, and
    whether a register read carries the caller's token on to DHIS2. It is a table of PUBLIC facts and
    that is what makes it safe here - an issuer's identifier is what a client has to be told, not
    something to keep from one. The issuer's keys are not here: they are fetched while the server
    starts and held on `dhis2w_fhir_serve.auth.AuthState`, because they are a live document rather than
    a setting.

    `tracked_entities` is the register this run serves - whether the instance's tracked entities are
    answered for at all, whether they can be listed, and how a listing is paged. It comes off
    `[serve.tracked_entities]` and no flag overrides it, because every value in it says what this
    facade tells a client about the subjects the instance holds, which is a decision the project
    makes once rather than per invocation. Which FHIR resources those subjects are served as is not
    stated here at all: the published `D2TET_CM` says that, and the register reads the artifact.

    `data_sets` is what this run answers about the instance's aggregate data - whether the values
    DHIS2 holds for a data set are served at all, which data sets they are served for, how a page is
    sized, and how many periods one read may name. It comes off `[serve.data_sets]` and no flag
    overrides it, for the reason `tracked_entities` states: what this facade tells a client about the
    instance is its contract rather than a property of one invocation.

    `search` is what answers a register search - the `NameSearchIndex` backend behind every lookup.
    It comes off `[serve.search]` and no flag overrides it, for the reason `tracked_entities` states:
    which searches this server answers is its contract rather than a property of one invocation.

    `projection` is the materialized projection this project holds: which store, where its file is,
    and how far back an incremental sync re-reads. It comes off `[serve.projection]` and no flag
    overrides it either - a projection is a thing on disk that `d2w fhir sync` fills and this process
    reads, so which one a run reads is not a property of the run. `store = "none"` - the default - is
    no projection at all, and a facade configured that way behaves exactly as it always did.
    """

    model_config = ConfigDict(frozen=True)

    project_dir: Path
    live: bool = False
    profile: str | None = None
    auth: ServeAuth = ServeAuth.NONE
    auth_scope: ServeAuthScope = ServeAuthScope.WRITE
    jwt: ServeJwtConfig = Field(default_factory=ServeJwtConfig)
    strict_codes: bool = DEFAULT_STRICT_CODES
    capture: bool = True
    ui: bool = False
    spool_dir: str = SPOOL_RELATIVE_PATH
    basemaps: list[BasemapSource] = Field(default_factory=lambda: list(DEFAULT_BASEMAPS))
    dhis2_base_url: str | None = None
    tracked_entities: TrackedEntitiesConfig = Field(default_factory=TrackedEntitiesConfig)
    data_sets: DataSetsConfig = Field(default_factory=DataSetsConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    projection: ProjectionConfig = Field(default_factory=ProjectionConfig)

    @classmethod
    def resolve(
        cls,
        project: FhirProject,
        *,
        live: bool = False,
        host: str | None = None,
        port: int | None = None,
        strict_codes: bool | None = None,
        ui: bool | None = None,
        basemaps: list[str] | None = None,
        profile: str | None = None,
        auth: ServeAuth | None = None,
        auth_scope: ServeAuthScope | None = None,
    ) -> ServeInvocation:
        """Resolve one invocation of the facade: a stated dial wins, then `[serve]`, then this model's defaults.

        Every argument is what one run stated and None is "stated nothing", which is why the
        booleans are `bool | None` rather than `bool`: `--no-ui` on a project whose table says
        `ui = true` has to be able to say False and be heard. `live` is the exception and takes a
        plain bool, because no `[serve]` key answers it - a live store is a property of the run.

        `basemaps` are the raw `--basemap` strings, read through `basemaps_from_options`; stating
        none leaves the table's layers alone. A value that names nothing servable raises
        `ValueError`, which is the caller's to render - `d2w fhir serve` renders it against the
        flag the value came from.

        Two of `[serve]` have no dial at all and are carried across verbatim: `capture`, which says
        what this server offers rather than what one run does, and `spool_dir`, which says where the
        receipts a previous run wrote already live.

        The profile is resolved here, before anything is built, so a named profile that does not
        exist refuses the run rather than failing under a banner saying the server is starting. A
        machine that names no profile at all resolves to None and serves its compiled guide offline,
        which is a whole posture rather than a degraded one; `live` makes the profile required,
        since a live store has an instance to read. The address it resolved is what the screens link
        an identity out to, and it is the only part of the profile that reaches the settings - the
        name, the origin, and the credentials stay on the invocation, which never leaves the process
        that opened it.

        The compiled guide is checked last, and only when the store is the one on disk: a project
        that has never run SUSHI has nothing to serve, and refusing here says so in one line rather
        than answering every read with a 404.

        THE AUTH POSTURE IS PREFLIGHTED HERE TOO, and for the same reason every other refusal is: a
        server that starts and then cannot honour what it was asked for is a failure nobody reads
        until somebody meets it. Five refusals, in `dhis2w_fhir_serve.auth.preflight_auth`: an
        interface other than loopback while neither this run nor fhir.toml has stated a posture, the
        `token` posture with its environment variable unset, the `dhis2` posture on a run that reads
        a compiled guide and so has no instance to check anybody against, the `jwt` posture with no
        `[serve.jwt] issuer`, and `[serve.jwt] forward_bearer` on a run with no instance to forward
        to. Whether the posture was STATED is what the first of those turns on - `auth = "none"`
        written down is a decision, an absent key is not - so a stated flag counts as much as a
        stated table key, and only the two of them being silent is silence.

        The sixth thing that could stop a `jwt` run - an issuer this machine cannot reach - is a
        round trip, so it is not made here: `open_serve_runtime` reads the issuer while the server
        starts and refuses with the same error type. This function reads values.
        """
        serve_config = project.config.serve
        stated_basemaps = list(basemaps or [])
        # The refusals are ordered as a reader meets them: a value this run stated and cannot mean
        # is answered before a profile is looked up, and both before the guide on disk is counted.
        resolved_basemaps = basemaps_from_options(stated_basemaps) if stated_basemaps else list(serve_config.basemaps)
        resolved_host = host if host is not None else serve_config.host
        resolved_auth = auth if auth is not None else serve_config.auth
        preflight_auth(
            posture=resolved_auth if resolved_auth is not None else ServeAuth.NONE,
            host=resolved_host,
            live=live,
            stated=auth is not None or serve_config.auth is not None,
            jwt=serve_config.jwt,
        )
        generation = _resolved_generation(project, profile, required=live)
        if not live and not any((project.ig_directory / COMPILED_RESOURCES_RELATIVE_PATH).glob("*.json")):
            raise CompiledIgMissingError
        return ServeInvocation(
            settings=cls(
                project_dir=project.project_root,
                live=live,
                profile=profile,
                auth=resolved_auth if resolved_auth is not None else ServeAuth.NONE,
                auth_scope=auth_scope if auth_scope is not None else serve_config.auth_scope,
                strict_codes=strict_codes if strict_codes is not None else serve_config.strict_codes,
                capture=serve_config.capture,
                ui=ui if ui is not None else serve_config.ui,
                spool_dir=serve_config.spool_dir,
                basemaps=resolved_basemaps,
                dhis2_base_url=None if generation is None else generation.profile.base_url,
                tracked_entities=serve_config.tracked_entities,
                data_sets=serve_config.data_sets,
                search=serve_config.search,
                projection=serve_config.projection,
            ),
            host=resolved_host,
            port=port if port is not None else serve_config.port,
            generation=generation,
        )


class ServeInvocation(BaseModel):
    """What one run of the facade resolved to: what it serves, where it listens, and the profile behind it.

    The address is here rather than on `ServeSettings` because it is what the process binds and not
    what the app serves - the factory reads the settings and never asks where the socket is. The
    resolved profile is here for the sharper reason: it carries the credentials the store connects
    with, and the settings are handed to the app and read out again by `/facade/uiconfig`, so a profile on
    them would be a credential one HTTP response away from a browser. What the screens are entitled
    to - the instance's address - is on the settings as `dhis2_base_url`, and the name and the origin
    stay here, where the command that resolved them can say which profile it used.
    """

    model_config = ConfigDict(frozen=True)

    settings: ServeSettings
    host: str
    port: int
    generation: GenerationProfile | None = None


def _resolved_generation(project: FhirProject, profile: str | None, *, required: bool) -> GenerationProfile | None:
    """The DHIS2 instance this run is about, or None when this machine names no profile at all.

    Absence and error are different answers. A machine with no `profiles.toml` anywhere is a
    compiled guide being served on its own, so it resolves to None. A profile that IS named - by
    `d2w -p`, by `DHIS2_PROFILE`, or by fhir.toml - and turns out not to exist is a statement that
    is wrong, and it refuses the run whether or not a live store needed to connect.
    """
    try:
        return resolve_generation_profile(project, profile)
    except NoProfileError:
        if required:
            raise
        return None

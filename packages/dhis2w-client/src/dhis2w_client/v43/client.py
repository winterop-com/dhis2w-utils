"""Async DHIS2 client with pluggable auth and version-aware generated dispatch."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from types import ModuleType, TracebackType
from typing import Any, Self

import httpx
from pydantic import BaseModel

from dhis2w_client._streaming import StreamParams, StreamSink, stream_to_sink
from dhis2w_client.errors import (
    AuthenticationError,
    Dhis2ApiError,
    UnsupportedVersionError,
    VersionPinMismatchError,
    format_unauthorized_message,
)
from dhis2w_client.generated import Dhis2, available_versions, load
from dhis2w_client.generated.v43.oas import SystemInfo as _SystemInfo
from dhis2w_client.v43.analytics_stream import AnalyticsAccessor
from dhis2w_client.v43.apps import AppsAccessor
from dhis2w_client.v43.attribute_values import AttributeValuesAccessor
from dhis2w_client.v43.auth.base import AuthProvider
from dhis2w_client.v43.categories import CategoriesAccessor
from dhis2w_client.v43.category_combos import CategoryCombosAccessor
from dhis2w_client.v43.category_option_combos import CategoryOptionCombosAccessor
from dhis2w_client.v43.category_option_group_sets import CategoryOptionGroupSetsAccessor
from dhis2w_client.v43.category_option_groups import CategoryOptionGroupsAccessor
from dhis2w_client.v43.category_options import CategoryOptionsAccessor
from dhis2w_client.v43.customize import CustomizeAccessor
from dhis2w_client.v43.dashboards import DashboardsAccessor
from dhis2w_client.v43.data_element_group_sets import DataElementGroupSetsAccessor
from dhis2w_client.v43.data_element_groups import DataElementGroupsAccessor
from dhis2w_client.v43.data_elements import DataElementsAccessor
from dhis2w_client.v43.data_sets import DataSetsAccessor
from dhis2w_client.v43.data_values import DataValuesAccessor
from dhis2w_client.v43.datastore import DatastoreAccessor
from dhis2w_client.v43.files import FilesAccessor
from dhis2w_client.v43.indicator_group_sets import IndicatorGroupSetsAccessor
from dhis2w_client.v43.indicator_groups import IndicatorGroupsAccessor
from dhis2w_client.v43.indicators import IndicatorsAccessor
from dhis2w_client.v43.legend_sets import LegendSetsAccessor
from dhis2w_client.v43.maintenance import MaintenanceAccessor
from dhis2w_client.v43.maps import MapsAccessor
from dhis2w_client.v43.messaging import MessagingAccessor
from dhis2w_client.v43.metadata import MetadataAccessor
from dhis2w_client.v43.option_sets import OptionSetsAccessor
from dhis2w_client.v43.organisation_unit_group_sets import OrganisationUnitGroupSetsAccessor
from dhis2w_client.v43.organisation_unit_groups import OrganisationUnitGroupsAccessor
from dhis2w_client.v43.organisation_unit_levels import OrganisationUnitLevelsAccessor
from dhis2w_client.v43.organisation_units import OrganisationUnitsAccessor
from dhis2w_client.v43.predictor_groups import PredictorGroupsAccessor
from dhis2w_client.v43.predictors import PredictorsAccessor
from dhis2w_client.v43.program_indicator_groups import ProgramIndicatorGroupsAccessor
from dhis2w_client.v43.program_indicators import ProgramIndicatorsAccessor
from dhis2w_client.v43.program_rules import ProgramRulesAccessor
from dhis2w_client.v43.program_stages import ProgramStagesAccessor
from dhis2w_client.v43.programs import ProgramsAccessor
from dhis2w_client.v43.retry import RetryPolicy, build_retry_transport
from dhis2w_client.v43.routes import RoutesAccessor
from dhis2w_client.v43.sections import SectionsAccessor
from dhis2w_client.v43.sql_views import SqlViewsAccessor
from dhis2w_client.v43.system import SystemModule
from dhis2w_client.v43.system_cache import SystemCache
from dhis2w_client.v43.tasks import TaskModule
from dhis2w_client.v43.tracked_entity_attributes import TrackedEntityAttributesAccessor
from dhis2w_client.v43.tracked_entity_types import TrackedEntityTypesAccessor
from dhis2w_client.v43.tracker import TrackerAccessor
from dhis2w_client.v43.validation import ValidationAccessor
from dhis2w_client.v43.validation_rule_groups import ValidationRuleGroupsAccessor
from dhis2w_client.v43.validation_rules import ValidationRulesAccessor
from dhis2w_client.v43.visualizations import VisualizationsAccessor

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")
_HTTP_LOG = logging.getLogger("dhis2w_client.http")


class Dhis2Client:
    """Async DHIS2 client pinned to v43 — accessor attributes are v43-typed.

    Independent class (NOT a subclass of v42's `Dhis2Client`). Every accessor
    attribute (`self.metadata`, `self.apps`, etc.) imports from the
    `dhis2w_client.v43.*` hand-written tree, so the static type chain is
    v43-pure end-to-end. `connect()` validates the server is actually v43
    and raises `RuntimeError` otherwise.

    Choose this class when you want v43-typed accessor returns (e.g. for
    code that relies on v43-specific divergence — BUGS.md #34/#35/#38).
    For auto-detection against any v41/v42/v43 server, use the top-level
    `from dhis2w_client import Dhis2Client` — that returns the v42-typed
    baseline with runtime dispatch via
    `dhis2w_client._dispatch.rebind_accessors_for_version`.
    """

    def __init__(
        self,
        base_url: str,
        auth: AuthProvider,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 60.0,
        allow_version_fallback: bool = False,
        version: Dhis2 | None = None,
        allow_version_mismatch: bool = False,
        retry_policy: RetryPolicy | None = None,
        http_limits: httpx.Limits | None = None,
        system_cache_ttl: float | None = 300.0,
        verify: bool | str = True,
        skip_version_probe: bool = False,
        event_hooks: Mapping[str, list[Callable[..., Any]]] | None = None,
    ) -> None:
        """Build a client. Call connect() or use as an async context manager before API calls.

        `version` defaults to `None` — the client auto-detects the server's
        major via `/api/system/info` on `connect()`. Pass `Dhis2.V41` /
        `Dhis2.V42` / `Dhis2.V43` to pin explicitly; `connect()` then checks
        the server's reported major against the pin and raises
        `VersionPinMismatchError` on a mismatch unless
        `allow_version_mismatch=True`.

        `retry_policy` (default: no retries) enables exponential-backoff
        retries on transient failures — connection errors plus the status
        codes listed on `RetryPolicy.retry_statuses` (default 429 / 502 /
        503 / 504). Non-idempotent methods (POST, PATCH) are exempt unless
        the policy sets `retry_non_idempotent=True`. See
        `dhis2w_client.retry.RetryPolicy` for tuning knobs.

        `http_limits` overrides the httpx connection-pool defaults (100
        max connections, 20 keepalive). Raise them for high-concurrency
        batch workflows; lower them to protect a small DHIS2 instance
        from a large `asyncio.gather`. See
        `docs/architecture/client.md` for guidance.

        `system_cache_ttl` (default 300 s) caps how long cached system-level
        reads (`client.system.info()`, the default categoryCombo UID, and
        per-key system settings) stay fresh before the next call refetches.
        Pass `None` to disable the cache entirely. `connect()` primes the
        cache from the info fetch it already performs, so the first
        `client.system.info()` after connect costs zero round-trips.

        `verify` controls TLS certificate verification on every internal
        `httpx.AsyncClient` (the main pool plus the canonical-URL and
        DHIS2-shape probes). Pass `False` to disable verification (only
        safe against self-signed staging boxes) or a path to a custom CA
        bundle. Default `True`.

        `skip_version_probe` (default `False`) opens the HTTP pool without
        the two probes `connect()` normally runs (canonical-URL resolution
        plus `/api/system/info` for version detection). Useful for
        health-checkers that want to *report* on those endpoints rather
        than have them raise, very-low-privilege PATs that can't read
        `/api/system/info`, and tests that inject a mock transport. With
        this flag set, `version_key`, `raw_version`, and `resources` raise
        on access — only `get_raw`, `post_raw`, `get_response`, and
        friends are usable.

        `event_hooks` (default `None`) passes httpx event hooks straight to the
        internal `AsyncClient`; `None` leaves httpx defaults untouched. The
        security audit uses a `request` hook to enforce its read-only allowlist.
        """
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = httpx.Timeout(timeout, connect=connect_timeout)
        self._retry_policy = retry_policy
        self._http_limits = http_limits
        self._http: httpx.AsyncClient | None = None
        self._verify = verify
        self._skip_version_probe = skip_version_probe
        self._event_hooks = event_hooks
        self._version_key: str | None = None
        self._raw_version: str | None = None
        self._generated: ModuleType | None = None
        self._allow_fallback = allow_version_fallback
        self._version = version
        self._allow_version_mismatch = allow_version_mismatch
        self._resources: Any = None
        self._system_cache: SystemCache | None = (
            SystemCache(ttl=system_cache_ttl) if system_cache_ttl is not None else None
        )
        self.system: SystemModule = SystemModule(self)
        self.customize: CustomizeAccessor = CustomizeAccessor(self)
        self.tasks: TaskModule = TaskModule(self)
        self.maintenance: MaintenanceAccessor = MaintenanceAccessor(self)
        self.messaging: MessagingAccessor = MessagingAccessor(self)
        self.metadata: MetadataAccessor = MetadataAccessor(self)
        self.routes: RoutesAccessor = RoutesAccessor(self)
        self.datastore: DatastoreAccessor = DatastoreAccessor(self)
        self.maps: MapsAccessor = MapsAccessor(self)
        self.files: FilesAccessor = FilesAccessor(self)
        self.legend_sets: LegendSetsAccessor = LegendSetsAccessor(self)
        self.validation: ValidationAccessor = ValidationAccessor(self)
        self.attribute_values: AttributeValuesAccessor = AttributeValuesAccessor(self)
        self.option_sets: OptionSetsAccessor = OptionSetsAccessor(self)
        self.organisation_units: OrganisationUnitsAccessor = OrganisationUnitsAccessor(self)
        self.organisation_unit_groups: OrganisationUnitGroupsAccessor = OrganisationUnitGroupsAccessor(self)
        self.organisation_unit_group_sets: OrganisationUnitGroupSetsAccessor = OrganisationUnitGroupSetsAccessor(self)
        self.organisation_unit_levels: OrganisationUnitLevelsAccessor = OrganisationUnitLevelsAccessor(self)
        self.predictors: PredictorsAccessor = PredictorsAccessor(self)
        self.program_rules: ProgramRulesAccessor = ProgramRulesAccessor(self)
        self.sql_views: SqlViewsAccessor = SqlViewsAccessor(self)
        self.visualizations: VisualizationsAccessor = VisualizationsAccessor(self)
        self.dashboards: DashboardsAccessor = DashboardsAccessor(self)
        self.data_values: DataValuesAccessor = DataValuesAccessor(self)
        self.analytics: AnalyticsAccessor = AnalyticsAccessor(self)
        self.tracker: TrackerAccessor = TrackerAccessor(self)
        self.apps: AppsAccessor = AppsAccessor(self)
        self.data_elements: DataElementsAccessor = DataElementsAccessor(self)
        self.data_element_groups: DataElementGroupsAccessor = DataElementGroupsAccessor(self)
        self.data_element_group_sets: DataElementGroupSetsAccessor = DataElementGroupSetsAccessor(self)
        self.indicators: IndicatorsAccessor = IndicatorsAccessor(self)
        self.indicator_groups: IndicatorGroupsAccessor = IndicatorGroupsAccessor(self)
        self.indicator_group_sets: IndicatorGroupSetsAccessor = IndicatorGroupSetsAccessor(self)
        self.program_indicators: ProgramIndicatorsAccessor = ProgramIndicatorsAccessor(self)
        self.program_indicator_groups: ProgramIndicatorGroupsAccessor = ProgramIndicatorGroupsAccessor(self)
        self.category_options: CategoryOptionsAccessor = CategoryOptionsAccessor(self)
        self.category_option_groups: CategoryOptionGroupsAccessor = CategoryOptionGroupsAccessor(self)
        self.category_option_group_sets: CategoryOptionGroupSetsAccessor = CategoryOptionGroupSetsAccessor(self)
        self.categories: CategoriesAccessor = CategoriesAccessor(self)
        self.category_combos: CategoryCombosAccessor = CategoryCombosAccessor(self)
        self.category_option_combos: CategoryOptionCombosAccessor = CategoryOptionCombosAccessor(self)
        self.data_sets: DataSetsAccessor = DataSetsAccessor(self)
        self.sections: SectionsAccessor = SectionsAccessor(self)
        self.validation_rules: ValidationRulesAccessor = ValidationRulesAccessor(self)
        self.validation_rule_groups: ValidationRuleGroupsAccessor = ValidationRuleGroupsAccessor(self)
        self.predictor_groups: PredictorGroupsAccessor = PredictorGroupsAccessor(self)
        self.tracked_entity_attributes: TrackedEntityAttributesAccessor = TrackedEntityAttributesAccessor(self)
        self.tracked_entity_types: TrackedEntityTypesAccessor = TrackedEntityTypesAccessor(self)
        self.programs: ProgramsAccessor = ProgramsAccessor(self)
        self.program_stages: ProgramStagesAccessor = ProgramStagesAccessor(self)

    @property
    def base_url(self) -> str:
        """Root URL of the connected DHIS2 instance."""
        return self._base_url

    @property
    def version_key(self) -> str:
        """Return the generated-client version key (e.g. "v42"); requires connect()."""
        if self._version_key is None:
            raise RuntimeError("Dhis2Client is not connected; call connect() first")
        return self._version_key

    @property
    def raw_version(self) -> str:
        """Return the raw version string reported by the server (e.g. "2.42.0")."""
        if self._raw_version is None:
            raise RuntimeError("Dhis2Client is not connected; call connect() first")
        return self._raw_version

    @property
    def resources(self) -> Any:
        """Return the version-bound generated `Resources` accessor; requires connect()."""
        if self._resources is None:
            raise RuntimeError("Dhis2Client is not connected; call connect() first")
        return self._resources

    @property
    def system_cache(self) -> SystemCache | None:
        """Per-client TTL cache for system-level reads; `None` when caching is disabled."""
        return self._system_cache

    async def __aenter__(self) -> Self:
        """Open the HTTP pool and run version discovery."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the HTTP pool."""
        await self.close()

    async def connect(self) -> None:
        """Open the HTTP pool and bind the generated module matching the remote version.

        With `skip_version_probe=True`, skips canonical-URL resolution and
        the `/api/system/info` round-trip — leaves `version_key`,
        `raw_version`, and `resources` unset (they raise on access) and
        returns once the pool is open.
        """
        if not self._skip_version_probe:
            resolved = await self._resolve_canonical_base_url(self._base_url, verify=self._verify)
            if resolved != self._base_url:
                self._base_url = resolved
        if self._http is None:
            kwargs: dict[str, Any] = {
                "base_url": self._base_url,
                "timeout": self._timeout,
                "verify": self._verify,
            }
            if self._retry_policy is not None:
                # httpx ignores the client-level `verify`/`limits` kwargs whenever an
                # explicit transport is supplied, so fold both into the inner transport
                # the retry wrapper drives. Otherwise a retry policy would silently drop
                # `verify=False` / a custom CA bundle (TLS failure on every call) and
                # ignore `http_limits`.
                pool_limits = (
                    self._http_limits
                    if self._http_limits is not None
                    else httpx.Limits(max_connections=100, max_keepalive_connections=20)
                )
                inner_transport = httpx.AsyncHTTPTransport(verify=self._verify, limits=pool_limits)
                kwargs["transport"] = build_retry_transport(self._retry_policy, inner=inner_transport)
            if self._http_limits is not None:
                kwargs["limits"] = self._http_limits
            if self._event_hooks is not None:
                kwargs["event_hooks"] = self._event_hooks
            self._http = httpx.AsyncClient(**kwargs)
        if self._skip_version_probe:
            return
        try:
            info = await self.get_raw("/api/system/info")
            self._raw_version = str(info.get("version", ""))
            if self._version is not None:
                # Caller asserted a version — verify the server's reported version
                # matches the pinned major. A v43 pin against a v42 server would
                # silently round-trip renamed/added fields wrong, so fail loud
                # unless the caller explicitly opts into the mismatch.
                if not self._allow_version_mismatch:
                    self._assert_reported_version_matches_pin(self._raw_version, self._version)
                self._version_key = self._version.value
            else:
                self._version_key = self._pick_version_key(self._raw_version)
            self._generated = load(self._version_key)
            if self._version_key != "v43":
                raise RuntimeError(
                    f"dhis2w_client.v43.client.Dhis2Client connected to a {self._raw_version!r} "
                    f"server (version_key={self._version_key!r}); v43 accessors will misbehave "
                    "against a non-v43 instance. Use dhis2w_client.Dhis2Client (the top-level "
                    "v42 entry point) for auto-dispatching accessors per server version."
                )
            # Prime the system cache with the info we already fetched so
            # `client.system.info()` right after connect is a free in-process read.
            if self._system_cache is not None:
                self._system_cache.set("info", _SystemInfo.model_validate(info))
            resources_cls = getattr(self._generated, "Resources", None)
            if resources_cls is not None:
                self._resources = resources_cls(self)
        except BaseException:
            # Any probe failure (bad auth, version-pin mismatch, non-JSON body, or the
            # wrong-server RuntimeError above) leaves the pool open, and __aexit__ never
            # runs because __aenter__ raised. Close the pool before re-raising so
            # connect() never leaks an AsyncClient.
            await self.close()
            raise

    @staticmethod
    async def _resolve_canonical_base_url(base_url: str, *, verify: bool | str = True) -> str:
        """Follow redirects (without auth) to find the canonical DHIS2 base URL.

        httpx strips Authorization headers on cross-host redirects as a security
        measure (it won't leak credentials to a host the user didn't target).
        DHIS2 `play.*` instances redirect `play.dhis2.org/dev` ->
        `play.im.dhis2.org/dev`, so every authenticated call would silently
        drop the Authorization header and get a 401.

        Resolve the chain once, unauthenticated, so subsequent requests go
        directly to the resolved host with credentials preserved.

        Cross-origin redirects are validated against `/api/system/info` on the
        candidate host before being adopted — DHIS2 always returns JSON for
        that endpoint regardless of auth state (200 with `version` field when
        anon-accessible, 401 with a JSON error envelope otherwise), while
        an SSO IdP or unrelated host returns HTML or a 404. Without this
        probe, an SSO-protected deployment whose root redirects to an IdP
        login page would leave subsequent `/api/*` calls pointed at the IdP.
        """
        candidate = base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=10.0),
                follow_redirects=True,
                verify=verify,
            ) as probe:
                response = await probe.get(f"{candidate}/")
        except Exception:  # noqa: BLE001 — probe is best-effort; fall back to original URL
            return candidate
        final = str(response.url).rstrip("/")
        # Strip common DHIS2 login-page trailing paths so we land on the root.
        for suffix in ("/dhis-web-login", "/login", "/dhis-web-commons/security/login.action"):
            if final.endswith(suffix):
                final = final[: -len(suffix)].rstrip("/")
                break
        if Dhis2Client._same_origin(candidate, final):
            return final
        if await Dhis2Client._probe_looks_like_dhis2(final, verify=verify):
            return final
        return candidate

    @staticmethod
    def _same_origin(left: str, right: str) -> bool:
        """Return True if two URLs share scheme + host + port."""
        a = httpx.URL(left)
        b = httpx.URL(right)
        return (a.scheme, a.host, a.port) == (b.scheme, b.host, b.port)

    @staticmethod
    async def _probe_looks_like_dhis2(base_url: str, *, verify: bool | str = True) -> bool:
        """Return True if `<base_url>/api/system/info` responds DHIS2-shaped.

        DHIS2 returns JSON on `/api/system/info` regardless of auth state.
        An SSO IdP or other host returns HTML / a 404, so the content-type
        check rejects them. Used to validate cross-origin redirect targets
        before adopting them as the canonical base URL.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=5.0),
                follow_redirects=False,
                verify=verify,
            ) as probe:
                response = await probe.get(
                    f"{base_url}/api/system/info",
                    headers={"Accept": "application/json"},
                )
        except Exception:  # noqa: BLE001 — probe is best-effort
            return False
        content_type = response.headers.get("content-type", "").lower()
        return "json" in content_type

    async def close(self) -> None:
        """Close the underlying HTTP pool."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @staticmethod
    def _assert_reported_version_matches_pin(reported: str, pinned: Dhis2) -> None:
        """Raise `VersionPinMismatchError` if the reported server version's major doesn't match the pin.

        Skipped when the server didn't report a parseable version string — in
        that case the caller's explicit pin is the only signal available, so
        we trust it rather than blocking on an unhelpful 'server didn't report
        version' error.
        """
        match = _VERSION_RE.match(reported)
        if not match:
            return
        reported_key = f"v{int(match.group(2))}"
        if reported_key != pinned.value:
            raise VersionPinMismatchError(pinned=pinned.value, reported=reported)

    def _pick_version_key(self, version_str: str) -> str:
        """Select a generated module version key for the reported DHIS2 version."""
        match = _VERSION_RE.match(version_str)
        available = list(available_versions())
        if not match:
            raise UnsupportedVersionError(version=version_str or "unknown", available=available)
        minor = int(match.group(2))
        requested = f"v{minor}"
        if requested in available:
            return requested
        if not self._allow_fallback:
            raise UnsupportedVersionError(version=version_str, available=available)
        lower = [k for k in available if int(k[1:]) <= minor]
        if not lower:
            raise UnsupportedVersionError(version=version_str, available=available)
        return max(lower, key=lambda k: int(k[1:]))

    async def get_raw(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Raw GET returning parsed JSON; used internally and as an escape hatch."""
        response = await self._request("GET", path, params=params)
        return self._parse_json(response)

    async def get_response(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """No-raise GET returning the raw `httpx.Response`; escape hatch for caller-side status logic.

        Skips the 4xx/5xx raise block in `_request` so callers can inspect
        status / headers / non-JSON bodies themselves. The auth header is
        still applied. Use when:

        - A 4xx / 5xx is a *fact you want to report* (health-checkers).
        - You need the raw `Content-Type` (SSO / proxy-page detection).
        - You're calling a reverse-proxied route under
          `/api/routes/<code>/run/...` where a 502 means "DHIS2 reached,
          downstream didn't" rather than "API error".
        """
        return await self._request(
            "GET",
            path,
            params=params,
            extra_headers=extra_headers,
            raise_for_status=False,
        )

    async def stream(
        self,
        method: str,
        path: str,
        sink: StreamSink,
        *,
        params: StreamParams | None = None,
        extra_headers: dict[str, str] | None = None,
        chunk_size: int = 64 * 1024,
    ) -> int:
        """Stream a response body straight to `sink` without buffering; return bytes written.

        The generic streaming primitive: `method`/`path` name any endpoint and
        `sink` is where its body lands -- a `pathlib.Path`, a file-like object
        with `.write(bytes)` (sync or async), or a callable taking each bytes
        chunk. Runs on the shared pool with fresh auth, so retry / pool-tuning /
        TLS config all apply.

        Use it to stream a large export straight to storage, e.g.
        `await client.stream("GET", "/api/dataValueSets.json", sink, params=...)`
        or an analytics pivot to a non-Path sink. `AnalyticsAccessor.stream_to`
        is the Path-only convenience over this.

        `params` forwards DHIS2's repeated-key shape (a mapping with list values
        or a list of 2-tuples). Raises `AuthenticationError` on 401 and
        `Dhis2ApiError` on any other 4xx / 5xx.
        """
        return await stream_to_sink(
            self,
            method,
            path,
            sink,
            params=params,
            extra_headers=extra_headers,
            chunk_size=chunk_size,
        )

    async def get[T: BaseModel](
        self,
        path: str,
        model: type[T],
        params: dict[str, Any] | None = None,
    ) -> T:
        """Typed GET returning an instance of `model` parsed from JSON."""
        raw = await self.get_raw(path, params=params)
        return model.model_validate(raw)

    async def post[T: BaseModel](
        self,
        path: str,
        body: Any,
        *,
        model: type[T],
        params: dict[str, Any] | None = None,
    ) -> T:
        """Typed POST returning an instance of `model` parsed from JSON.

        Used most often with `model=WebMessageResponse` to parse
        `/api/metadata` envelopes into the typed summary shape without
        a trailing `WebMessageResponse.model_validate(raw)` at the
        call site.
        """
        raw = await self.post_raw(path, body, params=params)
        return model.model_validate(raw)

    async def put[T: BaseModel](
        self,
        path: str,
        body: Any,
        *,
        model: type[T],
        params: dict[str, Any] | None = None,
    ) -> T:
        """Typed PUT returning an instance of `model` parsed from JSON."""
        raw = await self.put_raw(path, body, params=params)
        return model.model_validate(raw)

    async def patch[T: BaseModel](
        self,
        path: str,
        body: Any,
        *,
        model: type[T],
        params: dict[str, Any] | None = None,
        content_type: str = "application/json-patch+json",
    ) -> T:
        """Typed PATCH returning an instance of `model` parsed from JSON.

        Used with `model=WebMessageResponse` for metadata patches so the
        call site doesn't need a trailing `WebMessageResponse.model_validate(raw)`.
        """
        raw = await self.patch_raw(path, body, params=params, content_type=content_type)
        return model.model_validate(raw)

    async def delete[T: BaseModel](
        self,
        path: str,
        *,
        model: type[T],
        params: dict[str, Any] | None = None,
    ) -> T:
        """Typed DELETE returning an instance of `model` parsed from JSON.

        Most callers use `model=WebMessageResponse` since DHIS2 deletes
        return the standard envelope.
        """
        raw = await self.delete_raw(path, params=params)
        return model.model_validate(raw)

    async def post_raw(self, path: str, body: Any = None, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Raw POST returning parsed JSON."""
        response = await self._request("POST", path, params=params, json=body)
        return self._parse_json(response)

    async def put_raw(self, path: str, body: Any = None, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Raw PUT returning parsed JSON."""
        response = await self._request("PUT", path, params=params, json=body)
        return self._parse_json(response)

    async def delete_raw(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Raw DELETE returning parsed JSON (or empty dict)."""
        response = await self._request("DELETE", path, params=params)
        return self._parse_json(response)

    async def patch_raw(
        self,
        path: str,
        body: Any,
        *,
        params: dict[str, Any] | None = None,
        content_type: str = "application/json-patch+json",
    ) -> dict[str, Any]:
        """Raw PATCH returning parsed JSON. Defaults to JSON Patch (RFC 6902) content type."""
        response = await self._request(
            "PATCH",
            path,
            params=params,
            json=body,
            extra_headers={"Content-Type": content_type},
        )
        return self._parse_json(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: httpx._types.RequestContent | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        extra_headers: dict[str, str] | None = None,
        raise_for_status: bool = True,
    ) -> httpx.Response:
        """Dispatch a request through the shared pool with fresh auth headers.

        With `raise_for_status=False`, returns the raw response on any
        status code. Used by `get_response()` so callers can do their own
        content-negotiation / status-based handling — health-checkers in
        particular want a 502 from a reverse-proxied route to surface as
        a fact, not an exception.
        """
        if self._http is None:
            raise RuntimeError("Dhis2Client is not connected; call connect() first")
        headers = await self._auth.headers()
        if extra_headers:
            headers = {**headers, **extra_headers}
        t0 = time.monotonic()
        response = await self._http.request(
            method,
            path,
            params=params,
            json=json,
            content=content,
            files=files,
            headers=headers,
        )
        if _HTTP_LOG.isEnabledFor(logging.DEBUG):
            elapsed_ms = (time.monotonic() - t0) * 1000
            _HTTP_LOG.debug(
                "%s %s -> %d (%d bytes, %.0fms)",
                method,
                str(response.request.url),
                response.status_code,
                len(response.content),
                elapsed_ms,
            )
        if raise_for_status:
            if response.status_code == 401:
                raise AuthenticationError(
                    format_unauthorized_message(method, path, response.headers.get("WWW-Authenticate"))
                )
            if response.status_code >= 400:
                body: Any
                try:
                    body = response.json()
                except ValueError:
                    body = response.text
                raise Dhis2ApiError(status_code=response.status_code, message=response.reason_phrase, body=body)
        return response

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        """Parse a successful response body into a dict (wrapping non-dict JSON under "data").

        An empty body maps to `{}` — DHIS2 DELETEs and some 204-style
        endpoints return nothing. A *non-empty* body that isn't JSON raises
        `Dhis2ApiError` with a snippet: a 200 with an HTML body is almost
        always a proxy or SSO login page standing in for the API, and
        silently returning `{}` would mask it.
        """
        if not response.content.strip():
            return {}
        try:
            parsed = response.json()
        except ValueError:
            snippet = response.text.strip()[:200]
            raise Dhis2ApiError(
                status_code=response.status_code,
                message="expected a JSON body but got non-JSON content "
                "(a proxy or SSO login page may be intercepting API calls)",
                body=snippet,
            ) from None
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}

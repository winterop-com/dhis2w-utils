"""Typed accessors for /api/system/info and /api/me (non-metadata system endpoints).

`SystemInfo` re-exports from `generated/v42/oas` — OpenAPI ships the full
shape (46 fields including `buildTime`, `databaseInfo`, analytics-table
timings, memory info). `Me` stays hand-written because `/api/me` isn't in
the OpenAPI spec under that name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator

from dhis2w_client.errors import Dhis2ApiError
from dhis2w_client.generated.v42.oas import SystemInfo
from dhis2w_client.v42.calendars import DhisCalendar

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client


class DisplayRef(BaseModel):
    """Minimal DHIS2 object reference carrying id + displayName for CLI rendering."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    displayName: str | None = None


def _coerce_refs(value: Any) -> Any:
    """Coerce a DHIS2 ref list to `list[DisplayRef]`, lifting bare-UID strings to `{id}` refs.

    `/api/me` returns `programs` as a flat list of UID strings in v42 even
    when `fields=programs[id,displayName]` is requested (see
    `user.service.current_user` for the server-side workaround). Accept both
    shapes here so direct `client.system.me()` calls don't blow up on the
    bare-string case.
    """
    if not isinstance(value, list):
        return value
    return [{"id": entry} if isinstance(entry, str) else entry for entry in value]


class Me(BaseModel):
    """Shape of `/api/me` for the authenticated user (common fields; unknown preserved).

    Hand-written: `/api/me` doesn't appear in the OpenAPI spec as a component
    schema, so the emitter can't generate it. This is a stable-enough subset
    of the real response — `extra="allow"` preserves anything else DHIS2 ships.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    username: str | None = None
    displayName: str | None = None
    email: str | None = None
    firstName: str | None = None
    surname: str | None = None
    lastLogin: str | None = None
    created: str | None = None
    authorities: list[str] | None = None
    organisationUnits: list[DisplayRef] | None = None
    dataViewOrganisationUnits: list[DisplayRef] | None = None
    teiSearchOrganisationUnits: list[DisplayRef] | None = None
    userGroups: list[DisplayRef] | None = None
    userRoles: list[DisplayRef] | None = None
    programs: list[DisplayRef] | None = None
    disabled: bool | None = None
    externalAuth: bool | None = None
    twoFactorType: str | None = None
    passwordLastUpdated: str | None = None

    @field_validator(
        "organisationUnits",
        "dataViewOrganisationUnits",
        "teiSearchOrganisationUnits",
        "userGroups",
        "userRoles",
        "programs",
        mode="before",
    )
    @classmethod
    def _coerce_ref_lists(cls, value: Any) -> Any:
        """Accept bare UID strings as well as `{id, displayName}` dicts on every ref-list field."""
        return _coerce_refs(value)


class SystemModule:
    """Accessor bound to a `Dhis2Client` exposing system-level endpoints.

    `info()`, `default_category_combo_uid()`, and `setting()` read through
    the client's `SystemCache` (5-minute TTL by default — see
    `Dhis2Client(system_cache_ttl=...)`). Pass `use_cache=False` to force a
    fresh fetch; call `invalidate_cache()` when you know the upstream
    changed (settings update through another process, default category
    combo renamed via Admin, etc.).
    """

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def info(self, *, use_cache: bool = True) -> SystemInfo:
        """Fetch `/api/system/info` and return a typed `SystemInfo` (cached by default)."""
        cache = self._client.system_cache
        if cache is None or not use_cache:
            return await self._client.get("/api/system/info", model=SystemInfo)
        return await cache.get_or_fetch(
            "info",
            lambda: self._client.get("/api/system/info", model=SystemInfo),
        )

    async def me(self) -> Me:
        """Fetch `/api/me` and return the typed authenticated user profile.

        Not cached — `/api/me` is per-authenticated-user state and the
        typical use case (scripts impersonating a specific user) benefits
        from fresh reads.
        """
        return await self._client.get("/api/me", model=Me)

    async def default_category_combo_uid(self, *, use_cache: bool = True) -> str:
        """Return the UID of the DHIS2 default category combo (cached by default).

        DHIS2 stamps every data element / data set with a categoryCombo; the
        built-in `default` combo is what every unspecified reference points
        at. Fetching it once per script is a small but real bootstrap cost.
        """
        cache = self._client.system_cache
        if cache is None or not use_cache:
            return await self._fetch_default_category_combo_uid()
        return await cache.get_or_fetch(
            "default_category_combo_uid",
            self._fetch_default_category_combo_uid,
        )

    async def _fetch_default_category_combo_uid(self) -> str:
        """Look up the default categoryCombo UID via `/api/categoryCombos?filter=name:eq:default`."""
        raw = await self._client.get_raw(
            "/api/categoryCombos",
            params={"filter": "name:eq:default", "fields": "id", "paging": "false"},
        )
        combos = raw.get("categoryCombos") or []
        if not combos or not isinstance(combos, list):
            raise RuntimeError(
                "DHIS2 returned no categoryCombo named 'default' — "
                "every DHIS2 instance ships one; check the base URL + auth.",
            )
        first = combos[0]
        if not isinstance(first, dict) or "id" not in first:
            raise RuntimeError(f"malformed categoryCombos response: {raw!r}")
        return str(first["id"])

    async def calendar(self, *, use_cache: bool = True) -> str:
        """Return the active DHIS2 calendar name (the `keyCalendar` setting).

        DHIS2 ships nine calendar implementations — see `DhisCalendar` for the
        canonical set. The server default is `iso8601`, so when the setting is
        unset this returns `iso8601`. Cached per the same TTL as other system
        reads; pass `use_cache=False` to force a fresh fetch.
        """
        value = await self.setting("keyCalendar", use_cache=use_cache)
        return value or DhisCalendar.ISO8601.value

    async def set_calendar(self, calendar: DhisCalendar | str) -> None:
        """Write `keyCalendar` so the server uses the named calendar going forward.

        Accepts either a `DhisCalendar` member or a raw string for forward
        compatibility with calendars that may ship after this client. The
        change takes effect on the next request that resolves periods —
        rarely something a script needs to do, hence no convenience wrappers
        per calendar.
        """
        await self.set_setting("keyCalendar", str(calendar))

    async def setting(self, key: str, *, use_cache: bool = True) -> str | None:
        """Fetch `/api/systemSettings/{key}` and return its value (cached per key by default).

        DHIS2 returns a plain value when `Accept: text/plain` or a
        `{key: value}` envelope on JSON. This helper requests the JSON
        shape + pulls the value. Returns `None` when the key is unset.
        """
        cache = self._client.system_cache
        cache_key = f"setting:{key}"
        if cache is None or not use_cache:
            return await self._fetch_setting(key)
        return await cache.get_or_fetch(cache_key, lambda: self._fetch_setting(key))

    async def _fetch_setting(self, key: str) -> str | None:
        """Read one system setting via `/api/systemSettings/{key}`; returns `None` when absent."""
        try:
            raw = await self._client.get_raw(f"/api/systemSettings/{key}")
        except Dhis2ApiError as exc:
            # Only "key absent" is treated as None; auth / network / other server
            # errors propagate so callers don't silently see "unset" for what's
            # really a broken connection.
            if exc.status_code == 404:
                return None
            raise
        if not raw:
            return None
        value = raw.get(key)
        if value is None:
            return None
        return str(value)

    async def set_setting(self, key: str, value: str | None) -> None:
        """Write one system setting via `/api/systemSettings/{key}` (or DELETE when value is None).

        DHIS2's systemSettings endpoint takes the new value as a
        `text/plain` body on POST. Passing `None` sends a DELETE instead
        so the key reverts to whatever hard-coded default the server
        ships with. Invalidates the in-memory cache entry for `key`.
        """
        if value is None:
            await self._client._request("DELETE", f"/api/systemSettings/{key}")  # noqa: SLF001
        else:
            await self._client._request(  # noqa: SLF001
                "POST",
                f"/api/systemSettings/{key}",
                content=value.encode("utf-8"),
                extra_headers={"Content-Type": "text/plain"},
            )
        self.invalidate_cache(key=f"setting:{key}")

    def invalidate_cache(self, *, key: str | None = None) -> None:
        """Drop one cache key (e.g. `"info"`, `"setting:keyFlag"`) or every cached value."""
        cache = self._client.system_cache
        if cache is None:
            return
        cache.invalidate(key)


__all__ = ["DhisCalendar", "DisplayRef", "Me", "SystemInfo", "SystemModule"]

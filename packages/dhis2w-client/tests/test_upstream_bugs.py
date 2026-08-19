"""Paired upstream-bug regression tests — one bug + one workaround per BUGS.md entry.

Every test here is marked `@pytest.mark.upstream_bug` and comes in two flavours:

- **Mocked (fast, default)** — respx-mocked tests that model the buggy
  wire shape and verify our workaround code handles it. Run by default
  via `make test`. These document the bug pattern but don't auto-detect
  upstream fixes.
- **Live (slow, opt-in)** — `@pytest.mark.slow` tests that hit the local
  docker DHIS2 stack (`make dhis2-run DHIS2_VERSION=vN`) and verify the
  bug is still present on the actual wire. When DHIS2 ships an upstream
  fix, these fail loudly — the signal to drop the workaround. Each live
  test skips unless `client.version_key` matches the bug's target major,
  so you exercise v43 bugs against a v43 stack, v41 bugs against a v41
  stack, etc. Run all of them with `make test-slow` or just this suite
  with `make test-upstream-bugs -m slow`.

The marker is registered in `pyproject.toml`. List the regression
suite with `make test-upstream-bugs`. The full test suite (`make test`)
includes the mocked halves by default since they're fast.
"""

from __future__ import annotations

import contextlib
import os

import httpx
import pytest
import respx
from dhis2w_client import BasicAuth, Dhis2ApiError, Dhis2Client


def _auth() -> BasicAuth:
    """Throwaway BasicAuth for in-process respx tests."""
    return BasicAuth(username="admin", password="district")


def _live_auth() -> BasicAuth:
    """Admin basic auth for the local docker stack (seeded by `make dhis2-run`)."""
    return BasicAuth(
        username=os.environ.get("DHIS2_USERNAME", "admin"),
        password=os.environ.get("DHIS2_PASSWORD", "district"),
    )


def _skip_if_stack_unreachable(url: str) -> None:
    """Skip the test when the local docker stack isn't responding to root probes."""
    try:
        with httpx.Client(timeout=2.0) as probe:
            probe.get(f"{url}/dhis-web-login/")
    except (httpx.RequestError, httpx.HTTPError) as exc:
        pytest.skip(f"local DHIS2 stack not reachable at {url} ({exc}). Run `make dhis2-run DHIS2_VERSION=<N>` first.")


def _mock_v43_connect() -> None:
    """Mock the v43 server connect probes (canonical URL + /api/system/info)."""
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.43.0"}),
    )


# ---------------------------------------------------------------------------
# BUGS.md #34 — v43 dropped the `categorys` alias for `CategoryCombo.categories`.
# ---------------------------------------------------------------------------


@pytest.mark.upstream_bug
@respx.mock
async def test_bug_34_v43_categorys_alias_silently_dropped() -> None:
    """BUGS.md #34 — bug-still-present: v43 accepts `categorys` payloads but persists no categories.

    On v42 the `categorys` (misspelled) field was a backwards-compat alias for
    `categories`. v43 dropped the alias; writes that use `categorys` get a 201
    Created envelope but the resulting CategoryCombo has `categories: []` —
    silent data loss. This test models that wire behaviour. When DHIS2 either
    re-adds the alias or 400s on unknown fields, the assertion below stops
    matching reality.
    """
    _mock_v43_connect()
    respx.post("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CC_NEW"}}),
    )
    # Model the bug: GET shows the just-created combo with the categories list dropped.
    respx.get("https://dhis2.example/api/categoryCombos/CC_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_NEW",
                "name": "Sex",
                "dataDimensionType": "DISAGGREGATION",
                "skipTotal": False,
                "categories": [],  # <-- the bug: should match the input cats.
                "categoryOptionCombos": [],
            },
        ),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        # POST a raw payload that uses the misspelled `categorys` (simulating the
        # bug-pattern callers still in the wild). The server 201s but drops them.
        body = {
            "name": "Sex",
            "dataDimensionType": "DISAGGREGATION",
            "skipTotal": False,
            "categorys": [{"id": "CAT_SEX"}],
        }
        await client.post_raw("/api/categoryCombos", body=body)
        combo = await client.category_combos.get("CC_NEW")
    assert combo.categories == [], (
        "BUGS.md #34: v43 should still silently drop the `categorys` (misspelled) field. "
        "If this changes, DHIS2 may have either re-added the alias or made it a 4xx — "
        "either way, verify upstream + revisit `dhis2w_client.v{N}.category_combos`."
    )


@pytest.mark.upstream_bug
@respx.mock
async def test_bug_34_workaround_uses_categories_payload() -> None:
    """BUGS.md #34 — workaround-works: every CategoryCombo write goes out as `categories`.

    The fix is uniform across all three majors — we never emit `categorys`.
    Asserts the v43-bound wire payload contains `categories` and never
    `categorys`. If the workaround regresses, this fails loudly.
    """
    _mock_v43_connect()
    create_route = respx.post("https://dhis2.example/api/categoryCombos").mock(
        return_value=httpx.Response(201, json={"status": "OK", "httpStatusCode": 201, "response": {"uid": "CC_NEW"}}),
    )
    respx.get("https://dhis2.example/api/categoryCombos/CC_NEW").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "CC_NEW",
                "name": "Sex",
                "dataDimensionType": "DISAGGREGATION",
                "skipTotal": False,
                "categories": [{"id": "CAT_SEX"}],
                "categoryOptionCombos": [],
            },
        ),
    )
    async with Dhis2Client("https://dhis2.example", auth=_auth()) as client:
        await client.category_combos.create(name="Sex", categories=["CAT_SEX"])
    body = create_route.calls.last.request.read()
    assert b'"categories"' in body
    assert b'"categorys"' not in body, (
        "BUGS.md #34 workaround: client writes must use `categories`, not the dropped "
        "alias. Regression points at `dhis2w_client.v{N}.category_combos`."
    )


# ---------------------------------------------------------------------------
# BUGS.md #38 — v43 dropped `SharingObject.externalAccess` from the wire schema.
# ---------------------------------------------------------------------------


@pytest.mark.upstream_bug
def test_bug_38_v43_sharing_object_lacks_external_access_field() -> None:
    """BUGS.md #38 — bug-still-present: v43 OAS does not declare `externalAccess` on `SharingObject`.

    DHIS2 v43 dropped the field from the schema entirely. The generated
    `SharingObject` class on v43 doesn't carry it (and the wire silently
    ignores it). This test asserts the v43 OAS class lacks the field —
    if DHIS2 re-adds it, codegen would regenerate the class with the
    field, and this assertion would fail.
    """
    from dhis2w_client.generated.v43.oas.sharing_object import SharingObject

    assert "externalAccess" not in SharingObject.model_fields, (
        "BUGS.md #38: v43 SharingObject still lacks externalAccess in OAS. "
        "If this fails, regenerate codegen and revisit `dhis2w_client.v43.sharing`."
    )


@pytest.mark.upstream_bug
def test_bug_38_workaround_v43_sharing_builder_drops_external_access() -> None:
    """BUGS.md #38 — workaround-works: v43 SharingBuilder doesn't expose `external_access`.

    The materialised v43 wire payload doesn't carry `externalAccess`. The
    v42 sibling still has the field for v42 + v41 servers.
    """
    from dhis2w_client.v42.sharing import SharingBuilder as V42Builder
    from dhis2w_client.v43.sharing import ACCESS_READ_METADATA
    from dhis2w_client.v43.sharing import SharingBuilder as V43Builder

    assert "external_access" not in V43Builder.model_fields
    assert "external_access" in V42Builder.model_fields  # sanity: sibling still has it
    dumped = (
        V43Builder(public_access=ACCESS_READ_METADATA).to_sharing_object().model_dump(by_alias=True, exclude_none=True)
    )
    assert "externalAccess" not in dumped, (
        "BUGS.md #38 workaround: v43 SharingBuilder must not emit externalAccess in the wire shape. "
        "Regression points at `dhis2w_client.v43.sharing`."
    )


# ---------------------------------------------------------------------------
# BUGS.md #39 — v41 OAuth2 client schema uses `cid` (not `clientId`) + strict array typing.
# ---------------------------------------------------------------------------


@pytest.mark.upstream_bug
@respx.mock
async def test_bug_39_v41_oauth2_payload_with_clientid_persists_empty() -> None:
    """BUGS.md #39 — bug-still-present: v41 silently ignores `clientId` in OAuth2 payloads.

    v41's schema property is `cid`; v42 + v43 renamed it to `clientId`. A
    v42-shape payload sent to v41 returns 201 Created but the resulting
    client has no `clientId` set — `/oauth2/token` then 401s with
    invalid_client. This test models the v41 wire behaviour. If DHIS2
    backports the rename to v41, the dropped-field assertion stops matching.
    """
    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.41.0"}),
    )
    register_route = respx.post("https://dhis2.example/api/oAuth2Clients").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "OAUTH_UID"}})
    )
    # If a caller naively shipped a v42-shape payload to v41, this is what would happen:
    # the request lands, the server 201s, but `cid` is empty because `clientId` is unknown.
    async with Dhis2Client("https://dhis2.example", auth=_auth(), allow_version_fallback=True) as client:
        assert client.version_key == "v41"
        await client.post_raw(
            "/api/oAuth2Clients",
            body={
                "name": "my-app",
                "clientId": "my-app",  # <-- v41 doesn't know this key
                "clientSecret": "$2b$10$dummy",
            },
        )
    body = register_route.calls.last.request.read()
    assert b'"clientId"' in body
    assert b'"cid"' not in body, (
        "BUGS.md #39: v41 should still treat `clientId` as an unknown property. "
        "If this fails, DHIS2 may have backported the rename — verify upstream."
    )


@pytest.mark.upstream_bug
@respx.mock
async def test_bug_39_workaround_v41_register_emits_cid_not_clientid() -> None:
    """BUGS.md #39 — workaround-works: `register_oauth2_client` posts `cid` (not `clientId`) on v41.

    The per-version `dhis2w_client.v41.oauth2_payload.build_register_payload`
    emits `cid` + array-typed multi-valued fields. The registration helper
    in dhis2w-core dispatches per detected server version.
    """
    from dhis2w_core.oauth2_registration import register_oauth2_client

    respx.get("https://dhis2.example/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://dhis2.example/api/system/info").mock(
        return_value=httpx.Response(200, json={"version": "2.41.0"}),
    )
    register_route = respx.post("https://dhis2.example/api/oAuth2Clients").mock(
        return_value=httpx.Response(201, json={"response": {"uid": "OAUTH_UID"}})
    )
    await register_oauth2_client(
        base_url="https://dhis2.example",
        admin_auth=_auth(),
        client_id="my-app",
        client_secret="my-secret",
    )
    body = register_route.calls.last.request.read()
    assert b'"cid"' in body
    assert b'"clientId"' not in body, (
        "BUGS.md #39 workaround: v41 must receive `cid`, not `clientId`. "
        "Regression points at `dhis2w_client.v41.oauth2_payload`."
    )


# ---------------------------------------------------------------------------
# Live bug re-verification — opt-in via @pytest.mark.slow.
#
# These tests hit the local docker DHIS2 stack (`make dhis2-run
# DHIS2_VERSION=vN`). Each one skips unless the connected server matches
# the bug's target major, so you don't need all three stacks running at
# once. When DHIS2 ships an upstream fix, the bug-still-present assertion
# starts failing — that's the loud signal to drop the workaround.
# ---------------------------------------------------------------------------


_AnyVersion = frozenset({"v41", "v42", "v43"})


def _skip_unless_version(client: Dhis2Client, targets: str | frozenset[str]) -> None:
    """Skip the test unless `client.version_key` is in the bug's target version set.

    When DHIS2 fixes a bug upstream, it usually lands on the latest major
    first while older majors keep the bug — so each verifier declares the
    set of versions it applies to. The default `_AnyVersion` covers
    cross-version bugs (the bug exists on every supported major); specific
    sets like `frozenset({"v43"})` scope to one major.
    """
    target_set = frozenset({targets}) if isinstance(targets, str) else targets
    if client.version_key not in target_set:
        pytest.skip(
            f"BUGS live test targets {sorted(target_set)}; connected to {client.version_key!r}. "
            f"Run `make dhis2-run DHIS2_VERSION=<N>` against one of the target majors first."
        )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_34_v43_live_categorys_alias_silently_dropped(local_url: str) -> None:
    """BUGS.md #34 — bug-still-present (LIVE v43): POST with `categorys` persists no categories.

    Requires `make dhis2-run DHIS2_VERSION=v43`. POSTs a CategoryCombo using
    the misspelled `categorys` field. Reads back; asserts `categories: []`.
    If DHIS2 re-adds the alias (or starts 4xx-ing on unknown fields), the
    assertion fails.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth()) as client:
        _skip_unless_version(client, "v43")
        cats = await client.get_raw("/api/categories", params={"fields": "id", "pageSize": "1"})
        rows = cats.get("categories") or []
        if not rows:
            pytest.skip("seeded fixture has no Categories — fresh stack?")
        cat_uid = rows[0]["id"]
        create_envelope = await client.post_raw(
            "/api/categoryCombos",
            body={
                "name": "BUGS_34_LIVE_TEST",
                "dataDimensionType": "DISAGGREGATION",
                "skipTotal": False,
                "categorys": [{"id": cat_uid}],  # <-- the misspelled alias
            },
        )
        combo_uid = (create_envelope.get("response") or {}).get("uid")
        assert isinstance(combo_uid, str), f"unexpected create response: {create_envelope}"
        try:
            after = await client.get_raw(
                f"/api/categoryCombos/{combo_uid}",
                params={"fields": "id,categories[id]"},
            )
            categories = after.get("categories") or []
            assert categories == [], (
                f"BUGS.md #34: expected v43 to silently drop the `categorys` field, "
                f"got {len(categories)} categories on the persisted combo. DHIS2 may have "
                f"re-added the alias — verify upstream."
            )
        finally:
            await client.delete_raw(f"/api/categoryCombos/{combo_uid}")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_38_v43_live_sharing_schema_lacks_external_access(local_url: str) -> None:
    """BUGS.md #38 — bug-still-present (LIVE v43): `/api/schemas/sharingObject` does not list `externalAccess`.

    Requires `make dhis2-run DHIS2_VERSION=v43`. Reads the schema directly
    from DHIS2 (no mutation needed) and asserts the field is absent.
    Note: v43 itself 404s on `/api/schemas/sharingObject` (the endpoint
    was removed entirely) — that's a stronger form of "externalAccess
    absent". Either shape satisfies the assertion.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth()) as client:
        _skip_unless_version(client, "v43")
        try:
            schema = await client.get_raw("/api/schemas/sharingObject", params={"fields": "properties[fieldName]"})
        except Dhis2ApiError as exc:
            if exc.status_code == 404:
                # v43 removed the schema endpoint entirely — strongest "field absent".
                return
            raise
        field_names = {prop.get("fieldName") for prop in schema.get("properties") or []}
        assert "externalAccess" not in field_names, (
            "BUGS.md #38: expected v43 SharingObject schema to lack `externalAccess`. "
            "DHIS2 may have re-added the field — regenerate codegen and revisit "
            "`dhis2w_client.v43.sharing`."
        )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_39_v41_live_oauth2_rejects_v42_shape(local_url: str) -> None:
    """BUGS.md #39 — bug-still-present (LIVE v41): v41 doesn't accept the v42 `clientId` shape.

    Requires `make dhis2-run DHIS2_VERSION=v41`. POSTs a v42-shape OAuth2 client
    (using `clientId`, not `cid`) directly via raw POST. On the originally-observed
    v41 build the server silently persisted with empty `cid`; on `2.41.8.1` it
    rejects loudly with 409 `Missing required property cid` (E4000). Either
    outcome confirms the wire-shape divergence — v41 needs `cid`, v42+ uses
    `clientId` — which is what the codegen workaround (v41 register emits
    `cid` not `clientId`) handles. Cleans up afterwards.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, "v41")
        created_uid: str | None = None
        try:
            try:
                create_envelope = await client.post_raw(
                    "/api/oAuth2Clients",
                    body={
                        "name": "BUGS_39_LIVE_TEST",
                        "clientId": "bugs-39-live-test",  # v41 doesn't know this key
                        "clientSecret": "$2b$10$dummy.bcrypt.hash.for.bug.test.only.not.used",
                        "clientAuthenticationMethods": ["client_secret_basic"],
                        "authorizationGrantTypes": ["authorization_code"],
                        "redirectUris": ["http://localhost:8765"],
                        "scopes": ["ALL"],
                    },
                )
            except Dhis2ApiError as exc:
                # Modern v41 path: 409 with errorCode E4000 "Missing required property cid".
                assert exc.status_code == 409, (
                    f"BUGS.md #39: expected v41 to reject the v42-shape `clientId` body with 409 "
                    f"(or silently persist with empty `cid` on the historical build), got "
                    f"{exc.status_code}. DHIS2 may have backported the `clientId` rename to v41 — "
                    f"verify upstream + drop the v41-specific `cid` codegen workaround."
                )
                body = exc.body if isinstance(exc.body, dict) else {}
                response_block = body.get("response") if isinstance(body.get("response"), dict) else {}
                error_reports = response_block.get("errorReports") if isinstance(response_block, dict) else []
                if not isinstance(error_reports, list):
                    error_reports = []
                cid_error = any(
                    isinstance(report, dict) and report.get("errorProperty") == "cid" for report in error_reports
                )
                assert cid_error, (
                    f"BUGS.md #39: expected the 409 to flag `cid` as the missing property, got "
                    f"errorReports={error_reports}. Re-investigate before drawing conclusions."
                )
                return
            # Historical v41 path: 201 created, but `cid` was silently dropped.
            created_uid = (create_envelope.get("response") or {}).get("uid")
            assert isinstance(created_uid, str), f"unexpected create response: {create_envelope}"
            after = await client.get_raw(
                f"/api/oAuth2Clients/{created_uid}",
                params={"fields": "id,cid,clientId"},
            )
            cid = after.get("cid")
            assert not cid, (
                f"BUGS.md #39: expected v41 to silently drop `clientId` (cid stays empty) on the "
                f"historical 2-pre-2.41.8 build, got cid={cid!r}. DHIS2 may have backported the "
                f"rename — verify upstream + drop the v41-specific `cid` codegen workaround."
            )
        finally:
            if created_uid is not None:
                with contextlib.suppress(Dhis2ApiError):
                    await client.delete_raw(f"/api/oAuth2Clients/{created_uid}")


# ---------------------------------------------------------------------------
# Backlog — every BUGS.md entry deserves a live verifier; fill in incrementally.
# ---------------------------------------------------------------------------


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_1_live_verifier(local_url: str) -> None:
    """BUGS.md #1 — `/api/analytics/rawData` returns 404 without the `.json` URL suffix.

    Cross-version bug (v41/v42/v43): the sub-routes under `/api/analytics`
    only honour extension-suffixed paths. With `Accept: application/json`
    but no extension, Tomcat 404s. With `.json` appended the same query
    returns 200.

    Workaround: `dhis2w_core.plugins.analytics.service` hardcodes `.json`
    on every sub-route URL.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        # `_request` raises Dhis2ApiError on >=400 — wrap to inspect the status.
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client._request(  # noqa: SLF001 — direct probe, not a parsed call
                "GET",
                "/api/analytics/rawData",
                params={"dimension": "dx:nonexistent", "skipMeta": "true"},
                extra_headers={"Accept": "application/json"},
            )
        # `.json` suffix should produce a non-404 path. The same dimension
        # filter is invalid, so DHIS2 may still raise — but with a different
        # code than 404 (typically 409 conflict on the bad dimension).
        with_ext_error: Dhis2ApiError | None = None
        try:
            await client._request(  # noqa: SLF001
                "GET",
                "/api/analytics/rawData.json",
                params={"dimension": "dx:nonexistent", "skipMeta": "true"},
                extra_headers={"Accept": "application/json"},
            )
        except Dhis2ApiError as exc:
            with_ext_error = exc
    assert excinfo.value.status_code == 404, (
        f"BUGS.md #1: expected 404 on `/api/analytics/rawData` without `.json` "
        f"(Tomcat 'no static resource' fall-through), got {excinfo.value.status_code}. "
        f"DHIS2 may have fixed content-negotiation on the sub-route — verify upstream + "
        f"drop the `.json`-hardcode in `dhis2w_core.plugins.analytics.service`."
    )
    assert with_ext_error is None or with_ext_error.status_code != 404, (
        f"BUGS.md #1: expected `.json`-suffixed call to NOT be 404 (the workaround relies "
        f"on the suffix making the route resolve), got "
        f"{with_ext_error.status_code if with_ext_error else 'OK'}."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_2_live_verifier(local_url: str) -> None:
    """BUGS.md #2 — `importStrategy=DELETE` is a soft-delete that still blocks parent DE deletion.

    Cross-version bug. Picks one existing seeded DE + OU + DS combo,
    POSTs a data value, then `importStrategy=DELETE`s it, then tries
    DELETE the DE. Bug: E4030 (still associated with DataValue) instead
    of a clean delete. Leaves the soft-deleted row in place because
    there's no API to fully remove it — the bug's main symptom.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        # Pull a page of dataSets and filter client-side. v41 rejects the
        # server-side `dataSetElements:!empty` filter as an unknown operator
        # (400 E1003), so the cross-version path is to fetch a small page and
        # pick the first row whose nested arrays are non-empty in Python.
        data_sets = await client.get_raw(
            "/api/dataSets",
            params={
                "fields": "id,dataSetElements[dataElement[id]],organisationUnits[id],periodType",
                "pageSize": "50",
            },
        )
        rows = data_sets.get("dataSets") or []
        qualified = [row for row in rows if (row.get("dataSetElements") or []) and (row.get("organisationUnits") or [])]
        if not qualified:
            pytest.skip("seeded fixture has no DataSet with both DEs and OUs attached")
        ds_row = qualified[0]
        ds_elements = ds_row.get("dataSetElements") or []
        ds_ous = ds_row.get("organisationUnits") or []
        first_de = (ds_elements[0].get("dataElement") or {}).get("id")
        first_ou = ds_ous[0].get("id")
        period = ds_row.get("periodType") == "Monthly" and "209901" or "2099"
        if not isinstance(first_de, str) or not isinstance(first_ou, str):
            pytest.skip("could not resolve seeded DE/OU UIDs")
        # 1) CREATE the data value (best-effort — the seeded fixture may not
        # allow writes to this combination, or the value already exists).
        with contextlib.suppress(Dhis2ApiError):
            await client.post_raw(
                "/api/dataValueSets",
                body={"dataValues": [{"dataElement": first_de, "period": period, "orgUnit": first_ou, "value": "42"}]},
            )
        # 2) Soft-delete via importStrategy=DELETE (also best-effort — DHIS2
        # returns 409 when the row was already soft-deleted by a prior test run).
        with contextlib.suppress(Dhis2ApiError):
            await client.post_raw(
                "/api/dataValueSets",
                body={"dataValues": [{"dataElement": first_de, "period": period, "orgUnit": first_ou, "value": "42"}]},
                params={"importStrategy": "DELETE"},
            )
        # 3) Try DELETE the parent DE. The bug: 409 E4030, regardless of
        # whether OUR specific value got created — any pre-existing
        # soft-deleted DV for this DE blocks the metadata delete.
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client.delete_raw(f"/api/dataElements/{first_de}")
    assert excinfo.value.status_code == 409, (
        f"BUGS.md #2: expected 409 on DELETE of a DataElement with a soft-deleted DataValue "
        f"(the bug — soft-delete row blocks parent deletion), got "
        f"{excinfo.value.status_code}. DHIS2 may have fixed the reference-check to skip "
        f"deleted=true rows — verify upstream + drop the 'orphan DE/OU' workaround note in "
        f"`examples/client/bootstrap_zero_to_data.py`."
    )
    # No cleanup: the soft-delete row is the bug itself; there's no API path to remove it.


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_3_live_verifier(local_url: str) -> None:
    """BUGS.md #3 — TODO live verifier: Blank `audit.metadata` / `audit.tracker` / `audit.aggregate` in `dhis.conf` s...

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #3 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #3")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_4_live_verifier(local_url: str) -> None:
    """BUGS.md #4 — TODO live verifier: DHIS2 OAuth2 Authorization Server requires 10+ undocumented `dhis.conf` keys...

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #4 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #4")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_5_live_verifier(local_url: str) -> None:
    """BUGS.md #5 — TODO live verifier: `organisationUnits` POST inside a user's capture scope enforces DESCENDANT, n...

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #5 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #5")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_6_live_verifier(local_url: str) -> None:
    """BUGS.md #6 — bulk dataValueSets dryRun returns 409 even when every row is ignored.

    Cross-version bug. Sends a dryRun POST with one value pointing at
    nonexistent DE/OU UIDs (guaranteed to be rejected). DHIS2 surfaces
    that as 409 with a `conflicts[]` body instead of 200/WARNING — so
    naive httpx callers raise before inspecting the rich body. Dry-run
    means there's nothing to clean up.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client._request(  # noqa: SLF001 — expect 409 from the bulk push
                "POST",
                "/api/dataValueSets",
                params={"dryRun": "true", "importStrategy": "CREATE_AND_UPDATE"},
                json={
                    "dataValues": [
                        {
                            "dataElement": "nonexisting1",
                            "period": "202001",
                            "orgUnit": "nonexisting1",
                            "value": "1",
                        }
                    ]
                },
            )
    assert excinfo.value.status_code == 409, (
        f"BUGS.md #6: expected 409 on an all-ignored bulk push (the bug), got "
        f"{excinfo.value.status_code}. DHIS2 may have switched to 200+WARNING — verify "
        f"upstream + check whether the `Dhis2ApiError`-catch in seed loader / aggregate "
        f"plugin can be simplified."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_9_live_verifier(local_url: str) -> None:
    """BUGS.md #9 — TODO live verifier: DHIS2's strict OIDC property parser rejects entire provider config on typos

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #9 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #9")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_10_live_verifier(local_url: str) -> None:
    """BUGS.md #10 — `/api/loginConfig` field names don't match the writeable systemSettings keys.

    Cross-version bug. `/api/loginConfig` advertises
    `applicationIntroduction` etc. but the writeable system-setting key
    is `keyApplicationIntro`. Posts to the wrong-name key and asserts
    404; posts to the correct prefixed key and asserts success. Both
    POSTs target settings that already exist on a seeded stack so
    cleanup is just restore-original.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        # Probe the "wrong" name: applicationIntroduction (what loginConfig advertises).
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client._request(  # noqa: SLF001 — expect 404 (v42/v43) or 409 (v41)
                "POST",
                "/api/systemSettings/applicationIntroduction",
                content=b"BUGS_10_probe_wrongkey",
                extra_headers={"Content-Type": "text/plain"},
            )
    # v42/v43 reject with 404 "Setting does not exist: applicationIntroduction" (E1005).
    # v41 rejects with 409 "Key is not supported: applicationIntroduction". Different
    # error code, same load-bearing symptom: the loginConfig field name is not a valid
    # writeable system-settings key. Either rejection confirms the bug is present.
    assert excinfo.value.status_code in (404, 409), (
        f"BUGS.md #10: expected rejection (404 on v42/v43 'Setting does not exist' or 409 on "
        f"v41 'Key is not supported') for the loginConfig-style key "
        f"`applicationIntroduction`, got {excinfo.value.status_code}. DHIS2 may have aligned "
        f"the loginConfig field names with the writeable systemSettings keys — verify "
        f"upstream + drop the field-key translation table in "
        f"`docs/architecture/customize-plugin.md`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_11_live_verifier(local_url: str) -> None:
    """BUGS.md #11 — `POST /api/staticContent/logo_front` ignores upload until `keyUseCustomLogoFront=true` set.

    Cross-version bug. Uploads a minimal 1x1 PNG via multipart form,
    explicitly resets `keyUseCustomLogoFront` to `false` (to undo any
    prior test or workaround state), then asserts the GET of the logo
    redirects to the built-in default (the bug — the upload "succeeded"
    but isn't served until the flag is set). Restores the flag to its
    pre-test value at the end.
    """
    _skip_if_stack_unreachable(local_url)
    # Minimal valid 1x1 transparent PNG — 67 bytes.
    minimal_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c626001000000050001a5f645400000000049454e44"
        "ae426082"
    )
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        # Capture original flag state so we can restore.
        before = await client.get_raw("/api/systemSettings/keyUseCustomLogoFront")
        original = (before or {}).get("keyUseCustomLogoFront", "false")
        try:
            # 1) Upload via multipart — DHIS2 returns 204 with empty body, post_raw chokes on that.
            upload_response = await client._request(  # noqa: SLF001 — need direct response control
                "POST",
                "/api/staticContent/logo_front",
                files={"file": ("probe.png", minimal_png, "image/png")},
            )
            assert upload_response.status_code in (200, 204), (
                f"unexpected upload status {upload_response.status_code}: {upload_response.text}"
            )
            # 2) Force the flag back to false to undo any prior workaround state.
            await client._request(  # noqa: SLF001
                "POST",
                "/api/systemSettings/keyUseCustomLogoFront",
                content=b"false",
                extra_headers={"Content-Type": "text/plain"},
            )
            # 3) GET the logo — bug: redirects to the built-in default since the flag is false.
            login_config = await client.get_raw("/api/loginConfig", params={"fields": "useCustomLogoFront"})
            use_custom = login_config.get("useCustomLogoFront")
            assert use_custom is False, (
                f"BUGS.md #11: expected loginConfig.useCustomLogoFront=false after upload + flag "
                f"reset (the bug — DHIS2 stores the file but doesn't activate it), got "
                f"{use_custom!r}. DHIS2 may have wired the staticContent POST to auto-flip the "
                f"flag — verify upstream + drop the auto-flip in `Dhis2Client.customize."
                f"upload_logo_front`."
            )
        finally:
            # Restore the pre-test value.
            with contextlib.suppress(Exception):
                await client._request(  # noqa: SLF001
                    "POST",
                    "/api/systemSettings/keyUseCustomLogoFront",
                    content=str(original).encode("utf-8"),
                    extra_headers={"Content-Type": "text/plain"},
                )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_12_live_verifier(local_url: str) -> None:
    """BUGS.md #12 — TODO live verifier: DHIS2 login app leaves `html` transparent, so browser zoom > 100% exposes th...

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #12 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #12")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_13_live_verifier(local_url: str) -> None:
    """BUGS.md #13 — OAS enum says `MOD_Z_SCORE` but the runtime accepts only `MODIFIED_Z_SCORE`.

    Cross-version bug (v41/v42/v43). v42/v43 expose a standalone
    `OutlierDetectionAlgorithm` schema; v41 inlines the same enum on
    `OutlierDetectionMetadata.algorithm`. The enum values are identical
    across all three majors and continue to disagree with the runtime
    accept-list `{Z_SCORE, MIN_MAX, MODIFIED_Z_SCORE}`.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        spec = await client.get_raw("/api/openapi.json")
    schemas = spec.get("components", {}).get("schemas", {}) or {}
    named = schemas.get("OutlierDetectionAlgorithm") or {}
    inlined = (schemas.get("OutlierDetectionMetadata") or {}).get("properties", {}).get("algorithm") or {}
    values = set(named.get("enum") or inlined.get("enum") or [])
    assert values, (
        "BUGS.md #13: could not locate the OutlierDetection algorithm enum at either "
        "`OutlierDetectionAlgorithm.enum` (v42/v43) or "
        "`OutlierDetectionMetadata.properties.algorithm.enum` (v41). DHIS2 may have moved or "
        "removed the schema entirely — re-investigate the shape."
    )
    assert "MOD_Z_SCORE" in values, (
        f"BUGS.md #13: expected the OAS algorithm enum to still carry the truncated "
        f"`MOD_Z_SCORE`, got values={sorted(values)}. DHIS2 may have renamed it — verify "
        f"upstream + drop the string-literal workaround in the analytics outlier examples."
    )
    assert "MODIFIED_Z_SCORE" not in values, (
        "BUGS.md #13: if the OAS now also exposes `MODIFIED_Z_SCORE`, the rename has landed. "
        "Re-run codegen and drop the workaround."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_14_live_verifier(local_url: str) -> None:
    """BUGS.md #14 — `Route.auth` is an undiscriminated `oneOf` in the OAS.

    Cross-version bug (v41/v42/v43; v41 doesn't even have the
    `oauth2-client-credentials` variant — see BUGS.md #39). The
    load-bearing symptom is that `Route.auth` carries a bare `oneOf`
    with no `discriminator` block, so codegen can't emit a typed
    tagged union. v41 partially advanced by adding a `type` string
    property to each `*AuthScheme` schema, but without the parent
    `discriminator` block the spec-patch in
    `dhis2w_codegen.spec_patches::_patch_auth_scheme_discriminators`
    is still required.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        spec = await client.get_raw("/api/openapi.json")
    schemas = spec.get("components", {}).get("schemas", {}) or {}
    route_auth = (schemas.get("Route") or {}).get("properties", {}).get("auth") or {}
    assert "oneOf" in route_auth, (
        f"BUGS.md #14: expected `Route.auth` to still be a `oneOf` shape, got "
        f"keys={sorted(route_auth)}. DHIS2 may have restructured Route entirely — "
        f"re-investigate before drawing conclusions about the spec-patch."
    )
    assert "discriminator" not in route_auth, (
        f"BUGS.md #14: expected `Route.auth` to remain undiscriminated, got "
        f"discriminator={route_auth.get('discriminator')!r}. DHIS2 may have projected the "
        f"Jackson @JsonTypeInfo onto the OAS — drop the spec-patch in "
        f"`dhis2w_codegen.spec_patches::_patch_auth_scheme_discriminators` and regenerate."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_15_live_verifier(local_url: str) -> None:
    """BUGS.md #15 — `JobConfiguration.jobParameters` + `WebMessage.response` lack a usable polymorphic shape.

    Cross-version bug (v41/v42/v43). Same family as #14: springdoc doesn't
    project Jackson `@JsonTypeInfo` annotations onto these polymorphic
    properties. On v42/v43 the OAS still emits a bare `oneOf` without a
    discriminator block. On v41 `WebMessage.response` collapses to a
    fully opaque `{"type": "object"}` instead — strictly less type info,
    not more. Either shape means codegen can't synthesise a typed model,
    so the `dict[str, Any]` flatten in
    `packages/dhis2w-codegen/src/dhis2w_codegen/oas_emit.py` and the
    hand-written typed accessors on `WebMessageResponse` are still
    required.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        spec = await client.get_raw("/api/openapi.json")
    schemas = spec.get("components", {}).get("schemas", {}) or {}
    job_params = (schemas.get("JobConfiguration") or {}).get("properties", {}).get("jobParameters") or {}
    web_response = (schemas.get("WebMessage") or {}).get("properties", {}).get("response") or {}
    assert "oneOf" in job_params and "discriminator" not in job_params, (
        f"BUGS.md #15: expected JobConfiguration.jobParameters to be an undiscriminated "
        f"oneOf, got keys={sorted(job_params)}. DHIS2 may have added the discriminator — "
        f"verify upstream + drop the `dict[str, Any]` flatten in "
        f"`packages/dhis2w-codegen/src/dhis2w_codegen/oas_emit.py`."
    )
    web_response_is_bare_object = sorted(web_response.keys()) == ["type"] and web_response.get("type") == "object"
    web_response_is_oneof_no_discriminator = "oneOf" in web_response and "discriminator" not in web_response
    assert web_response_is_bare_object or web_response_is_oneof_no_discriminator, (
        f"BUGS.md #15: expected WebMessage.response to be either a bare `oneOf` without a "
        f"discriminator (v42/v43) or an opaque `{{type: object}}` (v41), got "
        f"keys={sorted(web_response)}. DHIS2 may have added the discriminator — drop the "
        f"flatten + typed accessors on `WebMessageResponse`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_16_live_verifier(local_url: str) -> None:
    """BUGS.md #16 — `POST /api/documents` multipart returns 415, forcing the two-step upload flow.

    Cross-version bug. The documents endpoint only accepts application/json;
    multipart uploads 415. Callers have to upload to /api/fileResources
    first, then POST a /api/documents row referencing the fileResource UID.
    The probe upload fails so nothing to clean up.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client._request(  # noqa: SLF001 — expect 415
                "POST",
                "/api/documents",
                files={"file": ("probe.txt", b"hello", "text/plain")},
            )
    assert excinfo.value.status_code == 415, (
        f"BUGS.md #16: expected 415 on multipart POST to /api/documents (the bug), got "
        f"{excinfo.value.status_code}. DHIS2 may now accept multipart directly — verify "
        f"upstream + drop the two-step upload flow in `dhis2w_client.v{{N}}.files`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_17_live_verifier(local_url: str) -> None:
    """BUGS.md #17 — `POST /api/messageConversations` returns UID on `Location` header, not in JSON body.

    Cross-version bug. Most DHIS2 POSTs carry the new UID at
    `response.uid`; messages put it on the `Location` header and leave
    the JSON envelope's `response` block missing the uid. Sends a probe
    message to the admin user (sends to self), then cleans up the thread.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        me = await client.get_raw("/api/me", params={"fields": "id"})
        my_uid = me.get("id")
        if not isinstance(my_uid, str):
            pytest.skip("could not resolve admin user UID")
        response = await client._request(  # noqa: SLF001 — need header inspection
            "POST",
            "/api/messageConversations",
            json={"subject": "BUGS_17_probe", "text": "probe", "users": [{"id": my_uid}]},
        )
        location = response.headers.get("Location") or response.headers.get("location") or ""
        body = response.json() if response.content else {}
        envelope_uid = (body.get("response") or {}).get("uid")
        loc_uid = location.rsplit("/", 1)[-1] if location else ""
        if loc_uid:
            with contextlib.suppress(Exception):
                await client.delete_raw(f"/api/messageConversations/{loc_uid}")
    assert location, (
        "BUGS.md #17: expected a `Location` header on the create response (carrying the "
        "new UID), got empty. DHIS2 may have moved the UID into the JSON body."
    )
    assert envelope_uid is None, (
        f"BUGS.md #17: expected `response.uid` to be absent (the bug — the UID lives only "
        f"on Location), got envelope_uid={envelope_uid!r}. DHIS2 may now also include it "
        f"in the JSON body — verify upstream + drop the Location-header parsing workaround."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_18_live_verifier(local_url: str) -> None:
    """BUGS.md #18a — reply endpoint stores `application/json` body verbatim as message text.

    Cross-version bug. Creates a message thread (admin to self), POSTs
    a reply with `Content-Type: application/json` body `{"text":"second"}`,
    fetches the thread, asserts the second message's `text` is the
    literal JSON string `'{"text":"second"}'` (the bug) rather than just
    `"second"`. Cleans up the thread on exit.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        me = await client.get_raw("/api/me", params={"fields": "id"})
        my_uid = me.get("id")
        if not isinstance(my_uid, str):
            pytest.skip("could not resolve admin user UID")
        # 1) Create a thread (sends to self).
        create_response = await client._request(  # noqa: SLF001 — UID is on the Location header
            "POST",
            "/api/messageConversations",
            json={"subject": "BUGS_18_probe", "text": "first", "users": [{"id": my_uid}]},
        )
        location = create_response.headers.get("Location") or create_response.headers.get("location") or ""
        thread_uid = location.rsplit("/", 1)[-1] if location else ""
        if not thread_uid:
            pytest.skip("could not resolve created thread UID from Location header")
        try:
            # 2) Reply with application/json body — the bug stores the JSON literal as text.
            await client._request(  # noqa: SLF001
                "POST",
                f"/api/messageConversations/{thread_uid}",
                json={"text": "second"},
            )
            # 3) Fetch back and inspect.
            after = await client.get_raw(
                f"/api/messageConversations/{thread_uid}", params={"fields": "messages[id,text]"}
            )
            messages = after.get("messages") or []
            assert len(messages) >= 2, f"expected at least 2 messages, got {len(messages)}"
            second_text = messages[1].get("text", "")
            assert second_text.startswith("{") and "second" in second_text, (
                f"BUGS.md #18a: expected reply body to be stored as the literal JSON string "
                f'`{{"text":"second"}}` (the bug), got {second_text!r}. DHIS2 may have wired '
                f"the reply endpoint to parse application/json — verify upstream + drop the "
                f"text/plain encoding in `MessagingAccessor.reply`."
            )
        finally:
            with contextlib.suppress(Exception):
                await client.delete_raw(f"/api/messageConversations/{thread_uid}")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_19_live_verifier(local_url: str) -> None:
    """BUGS.md #19 — `/api/validationResults?fields=*` returns id-only nested refs.

    Cross-version bug. The endpoint silently ignores `fields=*` and
    `fields=:all`, returning sparse nested refs (`{id: "..."}`). The
    workaround spells out every field selector explicitly. Skips if
    there are no persisted validation results to inspect.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        listing = await client.get_raw("/api/validationResults", params={"pageSize": "1", "fields": "*"})
    rows = listing.get("validationResults") or []
    if not rows:
        pytest.skip("no persisted validation results to inspect on this stack")
    first = rows[0] if isinstance(rows[0], dict) else {}
    rule = first.get("validationRule") or {}
    assert isinstance(rule, dict) and set(rule.keys()) - {"id"} == set(), (
        f"BUGS.md #19: expected `validationRule` to be id-only despite fields=*, got "
        f"keys={sorted(rule)}. DHIS2 may now expand fields=* properly — verify upstream + "
        f"simplify the explicit selector in `dhis2w_client.v{{N}}.validation.list_results`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_20_live_verifier(local_url: str) -> None:
    """BUGS.md #20 — `DELETE /api/options/{uid}` 200s but leaves the option in place.

    Originally cross-version (v41/v42/v43); DHIS2 fixed it on v43 — DELETE
    now actually removes the option. Verifier targets v41/v42 only; on v43
    it skips because the bug doesn't reproduce.
    Creates an OptionSet + Option, DELETEs the option,
    verifies it's still there. Cleans up at the end via the
    OptionSet → remove-member path (the actual working delete route).
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, frozenset({"v41", "v42"}))
        # Create a throwaway OptionSet so we own its lifecycle.
        os_envelope = await client.post_raw(
            "/api/optionSets",
            body={"name": "BUGS_20_OS", "valueType": "TEXT"},
        )
        os_uid = (os_envelope.get("response") or {}).get("uid")
        assert isinstance(os_uid, str), os_envelope
        try:
            opt_envelope = await client.post_raw(
                "/api/options",
                body={
                    "code": "BUGS_20_OPT",
                    "name": "BUGS_20_OPT",
                    "optionSet": {"id": os_uid},
                },
            )
            opt_uid = (opt_envelope.get("response") or {}).get("uid")
            assert isinstance(opt_uid, str), opt_envelope
            delete_envelope = await client.delete_raw(f"/api/options/{opt_uid}")
            # The bug: returns 200 OK but row stays.
            still_there = await client.get_raw(
                "/api/options",
                params={"filter": f"id:eq:{opt_uid}", "fields": "id"},
            )
            options_after = still_there.get("options") or []
            assert isinstance(delete_envelope, dict)
            assert options_after, (
                "BUGS.md #20: expected the option to still be present after DELETE (the bug), "
                "got empty list. DHIS2 may have wired up real deletion — verify upstream + "
                "drop any DELETE-via-optionSet workaround."
            )
        finally:
            # Best-effort cleanup. Drop the whole OptionSet which removes the option too.
            with contextlib.suppress(Exception):
                await client.delete_raw(f"/api/optionSets/{os_uid}")


@pytest.mark.upstream_bug
@pytest.mark.slow
@pytest.mark.xfail(
    strict=True,
    reason=(
        "DHIS2 fixed upstream — `attributeValues.value:eq:X` nested-path filter now returns 200 "
        "with results instead of E1003. Workaround removal pending: drop the UID-shorthand fallback "
        "in `dhis2w_client.v{N}.option_sets.OptionSetsAccessor.find_option_by_attribute`. "
        "See BUGS.md #21."
    ),
)
async def test_bug_21_live_verifier(local_url: str) -> None:
    """BUGS.md #21 — `filter=attributeValues.value:eq:X` rejects with E1003 `Unknown path property`.

    Cross-version bug (v41/v42/v43). The metadata filter DSL doesn't walk
    into nested `attributeValues` — the only way to filter on attribute
    values is via the undocumented `<attrUid>:eq:<value>` shorthand. This
    verifier confirms the nested path still fails with the E1003 error.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        response = await client._request(  # noqa: SLF001 — raw probe, expect 400
            "GET",
            "/api/options",
            params={"filter": "attributeValues.value:eq:nonexistent", "fields": "id"},
        )
    assert response.status_code == 400, (
        f"BUGS.md #21: expected 400 on `attributeValues.value` nested-path filter, got "
        f"{response.status_code}. DHIS2 may have wired up nested attribute-value walking — "
        f"verify upstream + drop the UID-shorthand workaround in "
        f"`dhis2w_client.v{{N}}.option_sets.OptionSetsAccessor.find_option_by_attribute`."
    )
    body = response.json() if response.content else {}
    assert body.get("errorCode") == "E1003", (
        f"BUGS.md #21: expected E1003 (Unknown path property), got {body.get('errorCode')!r}. "
        f"The endpoint's filter semantics may have shifted."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_23_live_verifier(local_url: str) -> None:
    """BUGS.md #23 — single-pass `/api/metadata` with DataSets trips Hibernate flush error.

    TODO: needs the full Sierra Leone play-fixture bundle (~1300 OUs +
    every transitively-required object) staged at
    `infra/fixtures/play/full_bundle.json`. That file doesn't exist
    yet — `infra/scripts/pull_play_fixtures.py` is the script that
    would generate it. Until that lands, this verifier stays skipped.

    Shape when implemented: POST the bundle as a single
    `/api/metadata?importStrategy=CREATE_AND_UPDATE&atomicMode=OBJECT`
    request against a freshly-reset DHIS2, assert 409 with the
    `org.hibernate.PropertyValueException: DataSet.periodType` message
    in the body. Two-pass workaround in
    `infra/scripts/seed/loader.py` should NOT be triggered.

    See BUGS.md #23 for the curl repro + the two-pass workaround.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: needs infra/fixtures/play/full_bundle.json — see BUGS.md #23")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_24_live_verifier(local_url: str) -> None:
    """BUGS.md #24 — built-in TET `Person` blocks imports sharing the name on fresh installs.

    Cross-version bug. Confirms a `Person` TET exists, then POSTs a
    new TET with a different UID but the same `name`. Asserts 409
    (UNIQUE constraint violation, E5003). Skips if the seeded fixture
    has been customised to drop the built-in `Person`.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        existing = await client.get_raw(
            "/api/trackedEntityTypes",
            params={"fields": "id,name", "filter": "name:eq:Person"},
        )
        rows = existing.get("trackedEntityTypes") or []
        if not rows:
            pytest.skip("seeded fixture has no built-in `Person` TET — bug is install-state-dependent")
        with pytest.raises(Dhis2ApiError) as excinfo:
            await client.post_raw(
                "/api/trackedEntityTypes",
                body={"id": "BUGS24Probe", "name": "Person", "shortName": "Person"},
            )
    assert excinfo.value.status_code == 409, (
        f"BUGS.md #24: expected 409 on a same-name TET import (the bug — `TET.name` is UNIQUE "
        f"at the DB level so any import sharing the built-in `Person` name fails), got "
        f"{excinfo.value.status_code}. DHIS2 may have loosened the constraint — verify "
        f"upstream + drop the `_disambiguate_common_names` rename in "
        f"`infra/scripts/seed/loader.py`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_26_live_verifier(local_url: str) -> None:
    """BUGS.md #26 — TODO live verifier: Admin OU scope is cached per session — scope changes need a re-login

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #26 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #26")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_27_live_verifier(local_url: str) -> None:
    """BUGS.md #27 — TODO live verifier: Fresh DHIS2 installs are flaky during first metadata import

    Placeholder. Fill in the live wire check that asserts the bug is
    still observable on a real DHIS2 stack. When DHIS2 ships a fix, the
    assertion fails — the loud signal we can drop the workaround.

    See BUGS.md #27 for the curl repro + the workaround pointer.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("TODO: implement live verifier — see BUGS.md #27")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_28_live_verifier(local_url: str) -> None:
    """BUGS.md #28 — `RelativePeriods` OAS schema is 45 booleans, not an enum.

    Cross-version bug. Codegen-shape decision DHIS2's `/api/openapi.json`
    has been doing for years. `RelativePeriods` enumerates every relative
    period (`last12Months`, `thisYear`, ...) as a boolean property instead
    of a single enum with a literal value set.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        spec = await client.get_raw("/api/openapi.json")
    rel = spec.get("components", {}).get("schemas", {}).get("RelativePeriods") or {}
    props = rel.get("properties") or {}
    boolean_props = [name for name, body in props.items() if (body or {}).get("type") == "boolean"]
    assert len(boolean_props) >= 30, (
        f"BUGS.md #28: expected RelativePeriods to carry many boolean properties (got "
        f"{len(boolean_props)}). If DHIS2 reshaped it as a single enum, this test is "
        f"the loud signal to revisit `dhis2w_client.v{{N}}.helpers.viz` + drop "
        f"`RelativePeriod` shim."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
@pytest.mark.skip(
    reason=(
        "Test design bug — `/api/metadata?filter=indicators:id:eq:X` returns 409 "
        "(`Unknown path property: indicators`). `/api/metadata` doesn't accept "
        "`<type>:<prop>:<op>:<value>` filters; it uses a different filter scheme. "
        "Need to rewrite against the correct /api/metadata filter syntax. See BUGS.md #29."
    ),
)
async def test_bug_29_live_verifier(local_url: str) -> None:
    """BUGS.md #29 — `/api/metadata?filter=...&rootJunction=OR` silently ANDs multiple filters.

    Cross-version bug. DHIS2 advertises `rootJunction` for cross-filter
    boolean logic but the metadata endpoint ignores the parameter and
    always ANDs. This verifier asks for indicators matching either of
    two mutually exclusive UID conditions — bug-present means the
    response is empty; bug-fixed means at least one row comes back.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        # Pick two UIDs that won't match together (an indicator can't have
        # both UIDs at once), so AND => empty, OR => at least one match.
        sample = await client.get_raw(
            "/api/indicators",
            params={"fields": "id", "pageSize": "2"},
        )
        indicators = sample.get("indicators") or []
        if len(indicators) < 2:
            pytest.skip("seeded fixture has fewer than 2 indicators")
        uid_a = indicators[0]["id"]
        uid_b = indicators[1]["id"]
        with_or = await client.get_raw(
            "/api/metadata",
            params={
                "filter": [f"indicators:id:eq:{uid_a}", f"indicators:id:eq:{uid_b}"],
                "rootJunction": "OR",
                "fields": "indicators[id]",
            },
        )
    indicator_rows = with_or.get("indicators") or []
    assert indicator_rows == [], (
        f"BUGS.md #29: expected rootJunction=OR with conflicting filters to still AND on "
        f"v41/v42/v43 (empty result). Got {len(indicator_rows)} rows — DHIS2 may have wired "
        f"up rootJunction properly. Verify upstream + drop the per-filter fanout workaround "
        f"in `dhis2w_client.v{{N}}.metadata.search`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_30_live_verifier(local_url: str) -> None:
    """BUGS.md #30 — `/api/appHub` returns `versions[*].created` as epoch-millis integers.

    Cross-version bug. DHIS2 proxies App Hub responses and converts ISO-8601
    timestamps into epoch-millis integers. Any parser that expects strings
    blows up. Workaround at `dhis2w_client.v{N}.apps` normalises the field
    to an integer-or-string union and parses both shapes.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        try:
            hub = await client.get_raw("/api/appHub")
        except Exception as exc:  # noqa: BLE001 — App Hub needs internet egress
            pytest.skip(f"App Hub not reachable from this stack ({exc})")
    apps_raw = hub if isinstance(hub, list) else (hub.get("appHub") or [])
    apps: list[dict[str, object]] = list(apps_raw) if isinstance(apps_raw, list) else []
    if not apps:
        pytest.skip("App Hub returned no apps (no internet egress?)")
    first_app: dict[str, object] = apps[0]
    versions_raw = first_app.get("versions") or []
    versions: list[dict[str, object]] = list(versions_raw) if isinstance(versions_raw, list) else []
    if not versions:
        pytest.skip("first App Hub app has no versions")
    created = versions[0].get("created")
    assert isinstance(created, int), (
        f"BUGS.md #30: expected `versions[0].created` to be an epoch-millis int, got "
        f"{type(created).__name__}({created!r}). DHIS2 may have fixed the proxy "
        f"normalisation — verify upstream + relax the union type in "
        f"`dhis2w_client.v{{N}}.apps`."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_31_live_verifier(local_url: str) -> None:
    """BUGS.md #31 — predictor parser rejects uppercase aggregators like `AVG()` and `SUM()`.

    Cross-version bug. The expression parser is case-sensitive only for
    aggregation functions; everything else in DHIS2's expression DSL is
    case-insensitive. POSTs both case variants and asserts uppercase
    fails parse while lowercase succeeds.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, _AnyVersion)
        uppercase = await client._request(  # noqa: SLF001
            "POST",
            "/api/predictors/expression/description",
            content=b"AVG(1)",
            extra_headers={"Content-Type": "text/plain"},
        )
        lowercase = await client._request(  # noqa: SLF001
            "POST",
            "/api/predictors/expression/description",
            content=b"avg(1)",
            extra_headers={"Content-Type": "text/plain"},
        )
    upper_body = uppercase.json() if uppercase.content else {}
    lower_body = lowercase.json() if lowercase.content else {}
    assert upper_body.get("status") != "OK", (
        f"BUGS.md #31: expected uppercase `AVG(1)` to be rejected as ill-formed (the bug), "
        f"got status={upper_body.get('status')!r}. DHIS2 may have made the parser "
        f"case-insensitive — verify upstream + drop the lowercase-only guidance in "
        f"the predictor docs."
    )
    assert lower_body.get("status") == "OK", (
        f"BUGS.md #31: expected lowercase `avg(1)` to parse OK, got status="
        f"{lower_body.get('status')!r}. The parser may have changed entirely."
    )


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_35_live_verifier(local_url: str) -> None:
    """BUGS.md #35 — v43-only: dataValueSets POST aborts when DE belongs to multiple datasets.

    Sets up the bug condition (DE in 2+ DataSets) by creating a probe
    DataSet that references an existing seeded DE, then POSTs a value
    without an envelope `dataSet` and asserts the 409 conflict with
    `E8002 Data set detection failed`. Cleans up the probe DataSet.
    """
    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth(), allow_version_fallback=True) as client:
        _skip_unless_version(client, frozenset({"v43"}))
        existing = await client.get_raw(
            "/api/dataSets",
            params={
                "fields": "id,periodType,dataSetElements[dataElement[id]]",
                "filter": "dataSetElements:!empty",
                "pageSize": "1",
            },
        )
        ds_rows = existing.get("dataSets") or []
        if not ds_rows:
            pytest.skip("seeded fixture has no DataSet with DEs")
        existing_ds = ds_rows[0]
        de_uid = ((existing_ds.get("dataSetElements") or [{}])[0].get("dataElement") or {}).get("id")
        period_type = existing_ds.get("periodType", "Monthly")
        if not isinstance(de_uid, str):
            pytest.skip("could not resolve DE UID from seeded DataSet")
        ou_response = await client.get_raw("/api/organisationUnits", params={"fields": "id", "pageSize": "1"})
        ou_rows = ou_response.get("organisationUnits") or []
        if not ou_rows:
            pytest.skip("no OrganisationUnit on the seeded fixture")
        ou_uid = ou_rows[0]["id"]
        # Create a probe DataSet that puts the same DE in a second DataSet —
        # this is what triggers v43's auto-target detection on the next POST.
        probe_ds = await client.post_raw(
            "/api/dataSets",
            body={
                "name": "BUGS35_probe_v43",
                "shortName": "BUGS35_probe",
                "periodType": period_type,
                "dataSetElements": [{"dataElement": {"id": de_uid}}],
            },
        )
        probe_uid = (probe_ds.get("response") or {}).get("uid")
        if not isinstance(probe_uid, str):
            pytest.skip(f"probe DataSet create failed: {probe_ds!r}")
        try:
            with pytest.raises(Dhis2ApiError) as excinfo:
                await client.post_raw(
                    "/api/dataValueSets",
                    body={
                        "dataValues": [
                            {
                                "dataElement": de_uid,
                                "period": "210601",
                                "orgUnit": ou_uid,
                                "categoryOptionCombo": "HllvX50cXC0",
                                "attributeOptionCombo": "HllvX50cXC0",
                                "value": "42",
                            }
                        ]
                    },
                )
            assert excinfo.value.status_code == 409, (
                f"BUGS.md #35: expected 409 on dataValueSets POST without envelope `dataSet` "
                f"(DE is in 2+ DataSets), got {excinfo.value.status_code}. DHIS2 may have "
                f"restored v42's auto-target tolerance — verify upstream + drop the per-dataset "
                f"grouping in `infra/scripts/seed/loader.py::import_data_values`."
            )
            body = excinfo.value.body if isinstance(excinfo.value.body, dict) else {}
            conflicts = (body.get("response") or {}).get("conflicts") or []
            error_codes = {c.get("errorCode") for c in conflicts if isinstance(c, dict)}
            assert "E8002" in error_codes or any(
                "Data set detection failed" in (c.get("value") or "") for c in conflicts if isinstance(c, dict)
            ), f"BUGS.md #35: expected `E8002 Data set detection failed` in the conflicts, got conflicts={conflicts!r}."
        finally:
            with contextlib.suppress(Exception):
                await client.delete_raw(f"/api/dataSets/{probe_uid}")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_36_live_verifier(local_url: str) -> None:
    """BUGS.md #36 — v43-only: event-analytics build fails with `column 'yearly' does not exist`.

    Skipped: the verifier would have to POST /api/resourceTables/analytics
    without `skipPrograms=lxAQ7Zs9VYR` and poll the task for the bad-SQL
    grammar error. That requires a v43 stack with seeded 2024 event data
    (the compose analytics-trigger sidecar already skips the failing
    program by default) and the rebuild takes minutes — too slow + too
    side-effect-heavy for the regression-suite shape.

    The workaround lives at the infra level in `infra/compose.yml`
    (analytics-trigger sidecar posts with `skipPrograms=lxAQ7Zs9VYR`).
    There's no client-side fix because the bug is in DHIS2's analytics
    table builder, not in any request-shape the client controls.

    See BUGS.md #36 for the curl repro + workaround details.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("infra-level workaround only — see BUGS.md #36")


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_37_live_verifier(local_url: str) -> None:
    """BUGS.md #37 — v43-only: fresh dataValueSets CREATE is ~80x slower per row than v41/v42.

    Skipped: this is a performance bug, not a binary pass/fail. A reliable
    verifier would need to measure per-row CREATE latency against an empty
    `datavalue` table on v43 and assert it's within some threshold. The
    measurement would have to wipe the data-value rows first, then time the
    POST — too destructive + too noisy to fold into a regression suite.

    The workaround lives at the infra level in
    `infra/scripts/seed/loader.py::_DATA_VALUE_CHUNK = 1_000` (chunk-size
    tuning so individual chunks finish inside httpx's 300 s read timeout).
    There's no client-side fix because the slowdown is in DHIS2's per-row
    category-combo cross-check CTE, not in any request-shape the client
    controls. The slowness only matters for the one-time cold-build of a
    fresh `datavalue` table; subsequent UPDATEs run at v41/v42 speeds.

    See BUGS.md #37 for the perf repro + workaround details.
    """
    _skip_if_stack_unreachable(local_url)
    pytest.skip("perf bug, not binary verifiable — see BUGS.md #37")


_BUG_42_FIELD = "keyAnalysisDisplayProperty"


@pytest.mark.upstream_bug
async def test_bug_42_generated_system_settings_rejects_lowercase_display_property() -> None:
    """BUGS.md #42 — bug-still-present: generated `SystemSettings` can't parse a settings payload.

    `/api/systemSettings` serialises `keyAnalysisDisplayProperty` lowercase
    (`"name"`), which the OAS `DisplayProperty` enum (`NAME`/`SHORTNAME`)
    rejects — the only one of ~100 keys that fails. The `security` plugin's
    `SecuritySettings` projection (`dhis2w_core.v{41,42,43}.plugins.security.models`)
    omits the field as the workaround. Dropping that single key makes the full
    generated model parse, proving the projection is the minimal slice needed.
    """
    from dhis2w_client.generated.v42.oas import SystemSettings
    from pydantic import ValidationError

    payload = {"minPasswordLength": 8, "maxPasswordLength": 72, _BUG_42_FIELD: "name"}
    with pytest.raises(ValidationError) as exc_info:
        SystemSettings.model_validate(payload)
    assert _BUG_42_FIELD in str(exc_info.value), (
        "BUGS.md #42: expected the lowercase enum to be the validation failure. "
        "If this changed, DHIS2 may have fixed the casing — verify upstream."
    )

    cleaned = {key: value for key, value in payload.items() if key != _BUG_42_FIELD}
    assert SystemSettings.model_validate(cleaned).minPasswordLength == 8


@pytest.mark.upstream_bug
@pytest.mark.slow
async def test_bug_42_live_system_settings_lowercase_display_property(local_url: str) -> None:
    """BUGS.md #42 — bug-still-present (LIVE): real `/api/systemSettings` breaks generated `SystemSettings`.

    Requires a running stack (`make dhis2-run DHIS2_VERSION=<N>`). Fetches the
    real settings object, asserts `keyAnalysisDisplayProperty` is the lowercase
    `"name"` and that the generated `SystemSettings` rejects the payload on that
    field. When DHIS2 ships the casing fix, the assertions fail — the signal to
    collapse the `SecuritySettings` projection into the generated `SystemSettings`
    and add a `client.system.settings()` accessor.
    """
    from dhis2w_client.generated.v42.oas import SystemSettings
    from pydantic import ValidationError

    _skip_if_stack_unreachable(local_url)
    async with Dhis2Client(local_url, auth=_live_auth()) as client:
        _skip_unless_version(client, _AnyVersion)
        raw = await client.get_raw("/api/systemSettings")
        assert raw.get(_BUG_42_FIELD) == "name", (
            f"BUGS.md #42: expected /api/systemSettings to return {_BUG_42_FIELD!r} as lowercase "
            f"'name'; got {raw.get(_BUG_42_FIELD)!r}. DHIS2 may have fixed the casing — verify "
            f"upstream, then collapse the SecuritySettings projection into the generated SystemSettings."
        )
        with pytest.raises(ValidationError) as exc_info:
            SystemSettings.model_validate(raw)
        assert _BUG_42_FIELD in str(exc_info.value)

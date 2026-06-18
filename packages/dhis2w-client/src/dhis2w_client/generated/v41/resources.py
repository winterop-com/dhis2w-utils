"""Generated DHIS2 v41 resource accessors. Do not edit by hand."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dhis2w_client.v41.json_patch import JsonPatchOp, JsonPatchOpAdapter

if TYPE_CHECKING:
    # Accessor `__init__` annotations only. Importing the client at runtime would
    # form a cycle: client -> generated.v41.oas -> resources -> client.
    # With `from __future__ import annotations`, the annotation stays a string.
    from dhis2w_client.v41.client import Dhis2Client

from .schemas.aggregate_data_exchange import AggregateDataExchange
from .schemas.analytics_table_hook import AnalyticsTableHook
from .schemas.api_token import ApiToken
from .schemas.attribute import Attribute
from .schemas.category import Category
from .schemas.category_combo import CategoryCombo
from .schemas.category_option import CategoryOption
from .schemas.category_option_combo import CategoryOptionCombo
from .schemas.category_option_group import CategoryOptionGroup
from .schemas.category_option_group_set import CategoryOptionGroupSet
from .schemas.constant import Constant
from .schemas.dashboard import Dashboard
from .schemas.data_approval_level import DataApprovalLevel
from .schemas.data_approval_workflow import DataApprovalWorkflow
from .schemas.data_element import DataElement
from .schemas.data_element_group import DataElementGroup
from .schemas.data_element_group_set import DataElementGroupSet
from .schemas.data_entry_form import DataEntryForm
from .schemas.data_set import DataSet
from .schemas.data_set_notification_template import DataSetNotificationTemplate
from .schemas.document import Document
from .schemas.event_chart import EventChart
from .schemas.event_filter import EventFilter
from .schemas.event_hook import EventHook
from .schemas.event_report import EventReport
from .schemas.event_visualization import EventVisualization
from .schemas.expression_dimension_item import ExpressionDimensionItem
from .schemas.external_map_layer import ExternalMapLayer
from .schemas.indicator import Indicator
from .schemas.indicator_group import IndicatorGroup
from .schemas.indicator_group_set import IndicatorGroupSet
from .schemas.indicator_type import IndicatorType
from .schemas.job_configuration import JobConfiguration
from .schemas.legend_set import LegendSet
from .schemas.map import Map
from .schemas.map_view import MapView
from .schemas.o_auth2_client import OAuth2Client
from .schemas.option import Option
from .schemas.option_group import OptionGroup
from .schemas.option_group_set import OptionGroupSet
from .schemas.option_set import OptionSet
from .schemas.organisation_unit import OrganisationUnit
from .schemas.organisation_unit_group import OrganisationUnitGroup
from .schemas.organisation_unit_group_set import OrganisationUnitGroupSet
from .schemas.organisation_unit_level import OrganisationUnitLevel
from .schemas.predictor import Predictor
from .schemas.predictor_group import PredictorGroup
from .schemas.program import Program
from .schemas.program_indicator import ProgramIndicator
from .schemas.program_indicator_group import ProgramIndicatorGroup
from .schemas.program_notification_template import ProgramNotificationTemplate
from .schemas.program_rule import ProgramRule
from .schemas.program_rule_action import ProgramRuleAction
from .schemas.program_rule_variable import ProgramRuleVariable
from .schemas.program_section import ProgramSection
from .schemas.program_stage import ProgramStage
from .schemas.program_stage_section import ProgramStageSection
from .schemas.program_stage_working_list import ProgramStageWorkingList
from .schemas.push_analysis import PushAnalysis
from .schemas.relationship_type import RelationshipType
from .schemas.report import Report
from .schemas.route import Route
from .schemas.s_m_s_command import SMSCommand
from .schemas.section import Section
from .schemas.sql_view import SqlView
from .schemas.tracked_entity_attribute import TrackedEntityAttribute
from .schemas.tracked_entity_filter import TrackedEntityFilter
from .schemas.tracked_entity_type import TrackedEntityType
from .schemas.user import User
from .schemas.user_group import UserGroup
from .schemas.user_role import UserRole
from .schemas.validation_notification_template import ValidationNotificationTemplate
from .schemas.validation_rule import ValidationRule
from .schemas.validation_rule_group import ValidationRuleGroup
from .schemas.visualization import Visualization


def _serialise_patch_ops(ops: Sequence[JsonPatchOp | dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise a heterogeneous list of JSON Patch ops into the RFC 6902 wire shape.

    Accepts raw dicts (validated through `JsonPatchOpAdapter`) and already-typed
    op instances interchangeably, so callers can mix `AddOp(path="/x", value=1)`
    with `{"op": "replace", "path": "/y", "value": 2}` in the same list.
    """
    wire: list[dict[str, Any]] = []
    for op in ops:
        typed = JsonPatchOpAdapter.validate_python(op) if isinstance(op, dict) else op
        wire.append(typed.model_dump(exclude_none=True, by_alias=True, mode="json"))
    return wire


def _build_write_params(
    *,
    merge_mode: str | None,
    import_strategy: str | None,
    skip_sharing: bool | None,
    skip_translation: bool | None,
) -> dict[str, Any] | None:
    """Build the /api/<resource> query-param dict for POST / PUT writes.

    DHIS2 accepts a small set of per-call flags on create + update:
    - `mergeMode=REPLACE` forces nested-list replacement (Program PTEA
      list needs this — otherwise DHIS2 silently merges additively).
    - `importStrategy` — `CREATE` / `CREATE_AND_UPDATE` / `UPDATE` / `DELETE`.
    - `skipSharing` / `skipTranslation` — skip those subsystems on import.
    Returns `None` when no flag is set so httpx omits the query string.
    """
    params: dict[str, Any] = {}
    if merge_mode is not None:
        params["mergeMode"] = merge_mode
    if import_strategy is not None:
        params["importStrategy"] = import_strategy
    if skip_sharing is not None:
        params["skipSharing"] = "true" if skip_sharing else "false"
    if skip_translation is not None:
        params["skipTranslation"] = "true" if skip_translation else "false"
    return params or None


def _build_list_params(
    *,
    fields: str | None,
    filters: Sequence[str] | None,
    root_junction: str | None,
    order: Sequence[str] | None,
    page: int | None,
    page_size: int | None,
    paging: bool | None,
    translate: bool | None,
    locale: str | None,
) -> dict[str, Any]:
    """Build the /api/<resource> query-param dict.

    Repeated params (`filter`, `order`) are emitted as list values — httpx
    flattens `{"filter": ["a", "b"]}` into `?filter=a&filter=b`.
    """
    params: dict[str, Any] = {}
    if fields is not None:
        params["fields"] = fields
    if filters:
        params["filter"] = filters
    if root_junction is not None:
        params["rootJunction"] = root_junction
    if order:
        params["order"] = order
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    if paging is not None:
        params["paging"] = "true" if paging else "false"
    if translate is not None:
        params["translate"] = "true" if translate else "false"
    if locale is not None:
        params["locale"] = locale
    return params


class _AggregateDataExchangeResource:
    """CRUD accessor for the `aggregateDataExchanges` collection on DHIS2 v41."""

    _path = "/api/aggregateDataExchanges"
    _plural_key = "aggregateDataExchanges"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> AggregateDataExchange:
        """Fetch a single AggregateDataExchange by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=AggregateDataExchange, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[AggregateDataExchange]:
        """List aggregateDataExchanges as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [AggregateDataExchange.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: AggregateDataExchange,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new AggregateDataExchange; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: AggregateDataExchange,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing AggregateDataExchange; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("AggregateDataExchange.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a AggregateDataExchange by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/aggregateDataExchanges/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a AggregateDataExchange (`PATCH /api/aggregateDataExchanges/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[AggregateDataExchange | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many AggregateDataExchanges in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the AggregateDataExchange from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _AnalyticsTableHookResource:
    """CRUD accessor for the `analyticsTableHooks` collection on DHIS2 v41."""

    _path = "/api/analyticsTableHooks"
    _plural_key = "analyticsTableHooks"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> AnalyticsTableHook:
        """Fetch a single AnalyticsTableHook by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=AnalyticsTableHook, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[AnalyticsTableHook]:
        """List analyticsTableHooks as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [AnalyticsTableHook.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: AnalyticsTableHook,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new AnalyticsTableHook; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: AnalyticsTableHook,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing AnalyticsTableHook; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("AnalyticsTableHook.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a AnalyticsTableHook by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/analyticsTableHooks/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a AnalyticsTableHook (`PATCH /api/analyticsTableHooks/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[AnalyticsTableHook | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many AnalyticsTableHooks in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the AnalyticsTableHook from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ApiTokenResource:
    """CRUD accessor for the `apiToken` collection on DHIS2 v41."""

    _path = "/api/apiToken"
    _plural_key = "apiToken"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ApiToken:
        """Fetch a single ApiToken by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ApiToken, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ApiToken]:
        """List apiToken as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ApiToken.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ApiToken,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ApiToken; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ApiToken,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ApiToken; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ApiToken.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ApiToken by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/apiToken/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ApiToken (`PATCH /api/apiToken/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ApiToken | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ApiTokens in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ApiToken from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _AttributeResource:
    """CRUD accessor for the `attributes` collection on DHIS2 v41."""

    _path = "/api/attributes"
    _plural_key = "attributes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Attribute:
        """Fetch a single Attribute by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Attribute, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Attribute]:
        """List attributes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Attribute.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Attribute,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Attribute; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Attribute,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Attribute; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Attribute.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Attribute by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/attributes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Attribute (`PATCH /api/attributes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Attribute | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Attributes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Attribute from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryResource:
    """CRUD accessor for the `categories` collection on DHIS2 v41."""

    _path = "/api/categories"
    _plural_key = "categories"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Category:
        """Fetch a single Category by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Category, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Category]:
        """List categories as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Category.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Category,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Category; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Category,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Category; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Category.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Category by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categories/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Category (`PATCH /api/categories/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Category | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Categorys in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Category from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryComboResource:
    """CRUD accessor for the `categoryCombos` collection on DHIS2 v41."""

    _path = "/api/categoryCombos"
    _plural_key = "categoryCombos"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> CategoryCombo:
        """Fetch a single CategoryCombo by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=CategoryCombo, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[CategoryCombo]:
        """List categoryCombos as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [CategoryCombo.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: CategoryCombo,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new CategoryCombo; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: CategoryCombo,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing CategoryCombo; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("CategoryCombo.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a CategoryCombo by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categoryCombos/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a CategoryCombo (`PATCH /api/categoryCombos/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[CategoryCombo | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many CategoryCombos in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the CategoryCombo from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryOptionResource:
    """CRUD accessor for the `categoryOptions` collection on DHIS2 v41."""

    _path = "/api/categoryOptions"
    _plural_key = "categoryOptions"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> CategoryOption:
        """Fetch a single CategoryOption by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=CategoryOption, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[CategoryOption]:
        """List categoryOptions as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [CategoryOption.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: CategoryOption,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new CategoryOption; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: CategoryOption,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing CategoryOption; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("CategoryOption.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a CategoryOption by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categoryOptions/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a CategoryOption (`PATCH /api/categoryOptions/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[CategoryOption | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many CategoryOptions in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the CategoryOption from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryOptionComboResource:
    """CRUD accessor for the `categoryOptionCombos` collection on DHIS2 v41."""

    _path = "/api/categoryOptionCombos"
    _plural_key = "categoryOptionCombos"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> CategoryOptionCombo:
        """Fetch a single CategoryOptionCombo by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=CategoryOptionCombo, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[CategoryOptionCombo]:
        """List categoryOptionCombos as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [CategoryOptionCombo.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: CategoryOptionCombo,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new CategoryOptionCombo; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: CategoryOptionCombo,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing CategoryOptionCombo; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("CategoryOptionCombo.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a CategoryOptionCombo by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categoryOptionCombos/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a CategoryOptionCombo (`PATCH /api/categoryOptionCombos/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[CategoryOptionCombo | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many CategoryOptionCombos in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the CategoryOptionCombo from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryOptionGroupResource:
    """CRUD accessor for the `categoryOptionGroups` collection on DHIS2 v41."""

    _path = "/api/categoryOptionGroups"
    _plural_key = "categoryOptionGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> CategoryOptionGroup:
        """Fetch a single CategoryOptionGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=CategoryOptionGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[CategoryOptionGroup]:
        """List categoryOptionGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [CategoryOptionGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: CategoryOptionGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new CategoryOptionGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: CategoryOptionGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing CategoryOptionGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("CategoryOptionGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a CategoryOptionGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categoryOptionGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a CategoryOptionGroup (`PATCH /api/categoryOptionGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[CategoryOptionGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many CategoryOptionGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the CategoryOptionGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _CategoryOptionGroupSetResource:
    """CRUD accessor for the `categoryOptionGroupSets` collection on DHIS2 v41."""

    _path = "/api/categoryOptionGroupSets"
    _plural_key = "categoryOptionGroupSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> CategoryOptionGroupSet:
        """Fetch a single CategoryOptionGroupSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=CategoryOptionGroupSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[CategoryOptionGroupSet]:
        """List categoryOptionGroupSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [CategoryOptionGroupSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: CategoryOptionGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new CategoryOptionGroupSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: CategoryOptionGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing CategoryOptionGroupSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("CategoryOptionGroupSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a CategoryOptionGroupSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/categoryOptionGroupSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a CategoryOptionGroupSet (`PATCH /api/categoryOptionGroupSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[CategoryOptionGroupSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many CategoryOptionGroupSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the CategoryOptionGroupSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ConstantResource:
    """CRUD accessor for the `constants` collection on DHIS2 v41."""

    _path = "/api/constants"
    _plural_key = "constants"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Constant:
        """Fetch a single Constant by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Constant, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Constant]:
        """List constants as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Constant.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Constant,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Constant; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Constant,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Constant; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Constant.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Constant by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/constants/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Constant (`PATCH /api/constants/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Constant | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Constants in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Constant from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DashboardResource:
    """CRUD accessor for the `dashboards` collection on DHIS2 v41."""

    _path = "/api/dashboards"
    _plural_key = "dashboards"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Dashboard:
        """Fetch a single Dashboard by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Dashboard, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Dashboard]:
        """List dashboards as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Dashboard.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Dashboard,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Dashboard; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Dashboard,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Dashboard; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Dashboard.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Dashboard by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dashboards/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Dashboard (`PATCH /api/dashboards/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Dashboard | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Dashboards in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Dashboard from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataApprovalLevelResource:
    """CRUD accessor for the `dataApprovalLevels` collection on DHIS2 v41."""

    _path = "/api/dataApprovalLevels"
    _plural_key = "dataApprovalLevels"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataApprovalLevel:
        """Fetch a single DataApprovalLevel by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataApprovalLevel, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataApprovalLevel]:
        """List dataApprovalLevels as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataApprovalLevel.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataApprovalLevel,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataApprovalLevel; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataApprovalLevel,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataApprovalLevel; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataApprovalLevel.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataApprovalLevel by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataApprovalLevels/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataApprovalLevel (`PATCH /api/dataApprovalLevels/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataApprovalLevel | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataApprovalLevels in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataApprovalLevel from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataApprovalWorkflowResource:
    """CRUD accessor for the `dataApprovalWorkflows` collection on DHIS2 v41."""

    _path = "/api/dataApprovalWorkflows"
    _plural_key = "dataApprovalWorkflows"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataApprovalWorkflow:
        """Fetch a single DataApprovalWorkflow by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataApprovalWorkflow, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataApprovalWorkflow]:
        """List dataApprovalWorkflows as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataApprovalWorkflow.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataApprovalWorkflow,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataApprovalWorkflow; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataApprovalWorkflow,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataApprovalWorkflow; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataApprovalWorkflow.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataApprovalWorkflow by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataApprovalWorkflows/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataApprovalWorkflow (`PATCH /api/dataApprovalWorkflows/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataApprovalWorkflow | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataApprovalWorkflows in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataApprovalWorkflow from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataElementResource:
    """CRUD accessor for the `dataElements` collection on DHIS2 v41."""

    _path = "/api/dataElements"
    _plural_key = "dataElements"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataElement:
        """Fetch a single DataElement by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataElement, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataElement]:
        """List dataElements as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataElement.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataElement,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataElement; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataElement,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataElement; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataElement.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataElement by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataElements/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataElement (`PATCH /api/dataElements/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataElement | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataElements in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataElement from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataElementGroupResource:
    """CRUD accessor for the `dataElementGroups` collection on DHIS2 v41."""

    _path = "/api/dataElementGroups"
    _plural_key = "dataElementGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataElementGroup:
        """Fetch a single DataElementGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataElementGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataElementGroup]:
        """List dataElementGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataElementGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataElementGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataElementGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataElementGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataElementGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataElementGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataElementGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataElementGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataElementGroup (`PATCH /api/dataElementGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataElementGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataElementGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataElementGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataElementGroupSetResource:
    """CRUD accessor for the `dataElementGroupSets` collection on DHIS2 v41."""

    _path = "/api/dataElementGroupSets"
    _plural_key = "dataElementGroupSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataElementGroupSet:
        """Fetch a single DataElementGroupSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataElementGroupSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataElementGroupSet]:
        """List dataElementGroupSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataElementGroupSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataElementGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataElementGroupSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataElementGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataElementGroupSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataElementGroupSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataElementGroupSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataElementGroupSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataElementGroupSet (`PATCH /api/dataElementGroupSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataElementGroupSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataElementGroupSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataElementGroupSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataEntryFormResource:
    """CRUD accessor for the `dataEntryForms` collection on DHIS2 v41."""

    _path = "/api/dataEntryForms"
    _plural_key = "dataEntryForms"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataEntryForm:
        """Fetch a single DataEntryForm by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataEntryForm, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataEntryForm]:
        """List dataEntryForms as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataEntryForm.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataEntryForm,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataEntryForm; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataEntryForm,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataEntryForm; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataEntryForm.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataEntryForm by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataEntryForms/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataEntryForm (`PATCH /api/dataEntryForms/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataEntryForm | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataEntryForms in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataEntryForm from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataSetResource:
    """CRUD accessor for the `dataSets` collection on DHIS2 v41."""

    _path = "/api/dataSets"
    _plural_key = "dataSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataSet:
        """Fetch a single DataSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataSet]:
        """List dataSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataSet (`PATCH /api/dataSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DataSetNotificationTemplateResource:
    """CRUD accessor for the `dataSetNotificationTemplates` collection on DHIS2 v41."""

    _path = "/api/dataSetNotificationTemplates"
    _plural_key = "dataSetNotificationTemplates"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> DataSetNotificationTemplate:
        """Fetch a single DataSetNotificationTemplate by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=DataSetNotificationTemplate, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[DataSetNotificationTemplate]:
        """List dataSetNotificationTemplates as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [DataSetNotificationTemplate.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: DataSetNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new DataSetNotificationTemplate; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: DataSetNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing DataSetNotificationTemplate; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("DataSetNotificationTemplate.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a DataSetNotificationTemplate by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/dataSetNotificationTemplates/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a DataSetNotificationTemplate (`PATCH /api/dataSetNotificationTemplates/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[DataSetNotificationTemplate | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many DataSetNotificationTemplates in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the DataSetNotificationTemplate from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _DocumentResource:
    """CRUD accessor for the `documents` collection on DHIS2 v41."""

    _path = "/api/documents"
    _plural_key = "documents"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Document:
        """Fetch a single Document by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Document, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Document]:
        """List documents as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Document.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Document,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Document; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Document,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Document; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Document.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Document by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/documents/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Document (`PATCH /api/documents/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Document | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Documents in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Document from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _EventChartResource:
    """CRUD accessor for the `eventCharts` collection on DHIS2 v41."""

    _path = "/api/eventCharts"
    _plural_key = "eventCharts"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> EventChart:
        """Fetch a single EventChart by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=EventChart, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[EventChart]:
        """List eventCharts as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [EventChart.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: EventChart,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new EventChart; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: EventChart,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing EventChart; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("EventChart.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a EventChart by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/eventCharts/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a EventChart (`PATCH /api/eventCharts/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[EventChart | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many EventCharts in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the EventChart from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _EventFilterResource:
    """CRUD accessor for the `eventFilters` collection on DHIS2 v41."""

    _path = "/api/eventFilters"
    _plural_key = "eventFilters"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> EventFilter:
        """Fetch a single EventFilter by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=EventFilter, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[EventFilter]:
        """List eventFilters as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [EventFilter.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: EventFilter,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new EventFilter; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: EventFilter,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing EventFilter; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("EventFilter.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a EventFilter by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/eventFilters/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a EventFilter (`PATCH /api/eventFilters/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[EventFilter | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many EventFilters in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the EventFilter from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _EventHookResource:
    """CRUD accessor for the `eventHooks` collection on DHIS2 v41."""

    _path = "/api/eventHooks"
    _plural_key = "eventHooks"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> EventHook:
        """Fetch a single EventHook by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=EventHook, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[EventHook]:
        """List eventHooks as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [EventHook.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: EventHook,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new EventHook; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: EventHook,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing EventHook; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("EventHook.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a EventHook by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/eventHooks/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a EventHook (`PATCH /api/eventHooks/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[EventHook | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many EventHooks in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the EventHook from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _EventReportResource:
    """CRUD accessor for the `eventReports` collection on DHIS2 v41."""

    _path = "/api/eventReports"
    _plural_key = "eventReports"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> EventReport:
        """Fetch a single EventReport by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=EventReport, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[EventReport]:
        """List eventReports as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [EventReport.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: EventReport,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new EventReport; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: EventReport,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing EventReport; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("EventReport.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a EventReport by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/eventReports/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a EventReport (`PATCH /api/eventReports/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[EventReport | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many EventReports in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the EventReport from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _EventVisualizationResource:
    """CRUD accessor for the `eventVisualizations` collection on DHIS2 v41."""

    _path = "/api/eventVisualizations"
    _plural_key = "eventVisualizations"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> EventVisualization:
        """Fetch a single EventVisualization by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=EventVisualization, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[EventVisualization]:
        """List eventVisualizations as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [EventVisualization.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: EventVisualization,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new EventVisualization; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: EventVisualization,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing EventVisualization; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("EventVisualization.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a EventVisualization by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/eventVisualizations/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a EventVisualization (`PATCH /api/eventVisualizations/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[EventVisualization | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many EventVisualizations in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the EventVisualization from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ExpressionDimensionItemResource:
    """CRUD accessor for the `expressionDimensionItems` collection on DHIS2 v41."""

    _path = "/api/expressionDimensionItems"
    _plural_key = "expressionDimensionItems"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ExpressionDimensionItem:
        """Fetch a single ExpressionDimensionItem by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ExpressionDimensionItem, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ExpressionDimensionItem]:
        """List expressionDimensionItems as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ExpressionDimensionItem.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ExpressionDimensionItem,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ExpressionDimensionItem; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ExpressionDimensionItem,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ExpressionDimensionItem; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ExpressionDimensionItem.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ExpressionDimensionItem by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/expressionDimensionItems/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ExpressionDimensionItem (`PATCH /api/expressionDimensionItems/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ExpressionDimensionItem | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ExpressionDimensionItems in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ExpressionDimensionItem from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ExternalMapLayerResource:
    """CRUD accessor for the `externalMapLayers` collection on DHIS2 v41."""

    _path = "/api/externalMapLayers"
    _plural_key = "externalMapLayers"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ExternalMapLayer:
        """Fetch a single ExternalMapLayer by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ExternalMapLayer, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ExternalMapLayer]:
        """List externalMapLayers as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ExternalMapLayer.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ExternalMapLayer,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ExternalMapLayer; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ExternalMapLayer,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ExternalMapLayer; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ExternalMapLayer.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ExternalMapLayer by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/externalMapLayers/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ExternalMapLayer (`PATCH /api/externalMapLayers/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ExternalMapLayer | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ExternalMapLayers in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ExternalMapLayer from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _IndicatorResource:
    """CRUD accessor for the `indicators` collection on DHIS2 v41."""

    _path = "/api/indicators"
    _plural_key = "indicators"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Indicator:
        """Fetch a single Indicator by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Indicator, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Indicator]:
        """List indicators as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Indicator.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Indicator,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Indicator; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Indicator,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Indicator; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Indicator.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Indicator by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/indicators/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Indicator (`PATCH /api/indicators/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Indicator | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Indicators in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Indicator from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _IndicatorGroupResource:
    """CRUD accessor for the `indicatorGroups` collection on DHIS2 v41."""

    _path = "/api/indicatorGroups"
    _plural_key = "indicatorGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> IndicatorGroup:
        """Fetch a single IndicatorGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=IndicatorGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[IndicatorGroup]:
        """List indicatorGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [IndicatorGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: IndicatorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new IndicatorGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: IndicatorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing IndicatorGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("IndicatorGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a IndicatorGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/indicatorGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a IndicatorGroup (`PATCH /api/indicatorGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[IndicatorGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many IndicatorGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the IndicatorGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _IndicatorGroupSetResource:
    """CRUD accessor for the `indicatorGroupSets` collection on DHIS2 v41."""

    _path = "/api/indicatorGroupSets"
    _plural_key = "indicatorGroupSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> IndicatorGroupSet:
        """Fetch a single IndicatorGroupSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=IndicatorGroupSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[IndicatorGroupSet]:
        """List indicatorGroupSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [IndicatorGroupSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: IndicatorGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new IndicatorGroupSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: IndicatorGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing IndicatorGroupSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("IndicatorGroupSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a IndicatorGroupSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/indicatorGroupSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a IndicatorGroupSet (`PATCH /api/indicatorGroupSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[IndicatorGroupSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many IndicatorGroupSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the IndicatorGroupSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _IndicatorTypeResource:
    """CRUD accessor for the `indicatorTypes` collection on DHIS2 v41."""

    _path = "/api/indicatorTypes"
    _plural_key = "indicatorTypes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> IndicatorType:
        """Fetch a single IndicatorType by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=IndicatorType, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[IndicatorType]:
        """List indicatorTypes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [IndicatorType.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: IndicatorType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new IndicatorType; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: IndicatorType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing IndicatorType; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("IndicatorType.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a IndicatorType by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/indicatorTypes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a IndicatorType (`PATCH /api/indicatorTypes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[IndicatorType | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many IndicatorTypes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the IndicatorType from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _JobConfigurationResource:
    """CRUD accessor for the `jobConfigurations` collection on DHIS2 v41."""

    _path = "/api/jobConfigurations"
    _plural_key = "jobConfigurations"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> JobConfiguration:
        """Fetch a single JobConfiguration by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=JobConfiguration, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[JobConfiguration]:
        """List jobConfigurations as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [JobConfiguration.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: JobConfiguration,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new JobConfiguration; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: JobConfiguration,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing JobConfiguration; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("JobConfiguration.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a JobConfiguration by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/jobConfigurations/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a JobConfiguration (`PATCH /api/jobConfigurations/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[JobConfiguration | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many JobConfigurations in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the JobConfiguration from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _LegendSetResource:
    """CRUD accessor for the `legendSets` collection on DHIS2 v41."""

    _path = "/api/legendSets"
    _plural_key = "legendSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> LegendSet:
        """Fetch a single LegendSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=LegendSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[LegendSet]:
        """List legendSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [LegendSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: LegendSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new LegendSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: LegendSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing LegendSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("LegendSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a LegendSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/legendSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a LegendSet (`PATCH /api/legendSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[LegendSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many LegendSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the LegendSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _MapResource:
    """CRUD accessor for the `maps` collection on DHIS2 v41."""

    _path = "/api/maps"
    _plural_key = "maps"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Map:
        """Fetch a single Map by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Map, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Map]:
        """List maps as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Map.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Map,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Map; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Map,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Map; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Map.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Map by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/maps/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Map (`PATCH /api/maps/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Map | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Maps in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Map from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _MapViewResource:
    """CRUD accessor for the `mapViews` collection on DHIS2 v41."""

    _path = "/api/mapViews"
    _plural_key = "mapViews"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> MapView:
        """Fetch a single MapView by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=MapView, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[MapView]:
        """List mapViews as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [MapView.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: MapView,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new MapView; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: MapView,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing MapView; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("MapView.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a MapView by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/mapViews/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a MapView (`PATCH /api/mapViews/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[MapView | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many MapViews in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the MapView from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OAuth2ClientResource:
    """CRUD accessor for the `oAuth2Clients` collection on DHIS2 v41."""

    _path = "/api/oAuth2Clients"
    _plural_key = "oAuth2Clients"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OAuth2Client:
        """Fetch a single OAuth2Client by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OAuth2Client, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OAuth2Client]:
        """List oAuth2Clients as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OAuth2Client.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OAuth2Client,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OAuth2Client; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OAuth2Client,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OAuth2Client; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OAuth2Client.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OAuth2Client by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/oAuth2Clients/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OAuth2Client (`PATCH /api/oAuth2Clients/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OAuth2Client | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OAuth2Clients in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OAuth2Client from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OptionResource:
    """CRUD accessor for the `options` collection on DHIS2 v41."""

    _path = "/api/options"
    _plural_key = "options"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Option:
        """Fetch a single Option by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Option, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Option]:
        """List options as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Option.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Option,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Option; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Option,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Option; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Option.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Option by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/options/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Option (`PATCH /api/options/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Option | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Options in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Option from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OptionGroupResource:
    """CRUD accessor for the `optionGroups` collection on DHIS2 v41."""

    _path = "/api/optionGroups"
    _plural_key = "optionGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OptionGroup:
        """Fetch a single OptionGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OptionGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OptionGroup]:
        """List optionGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OptionGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OptionGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OptionGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OptionGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OptionGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OptionGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OptionGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/optionGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OptionGroup (`PATCH /api/optionGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OptionGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OptionGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OptionGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OptionGroupSetResource:
    """CRUD accessor for the `optionGroupSets` collection on DHIS2 v41."""

    _path = "/api/optionGroupSets"
    _plural_key = "optionGroupSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OptionGroupSet:
        """Fetch a single OptionGroupSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OptionGroupSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OptionGroupSet]:
        """List optionGroupSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OptionGroupSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OptionGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OptionGroupSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OptionGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OptionGroupSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OptionGroupSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OptionGroupSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/optionGroupSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OptionGroupSet (`PATCH /api/optionGroupSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OptionGroupSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OptionGroupSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OptionGroupSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OptionSetResource:
    """CRUD accessor for the `optionSets` collection on DHIS2 v41."""

    _path = "/api/optionSets"
    _plural_key = "optionSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OptionSet:
        """Fetch a single OptionSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OptionSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OptionSet]:
        """List optionSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OptionSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OptionSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OptionSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OptionSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OptionSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OptionSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OptionSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/optionSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OptionSet (`PATCH /api/optionSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OptionSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OptionSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OptionSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OrganisationUnitResource:
    """CRUD accessor for the `organisationUnits` collection on DHIS2 v41."""

    _path = "/api/organisationUnits"
    _plural_key = "organisationUnits"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OrganisationUnit:
        """Fetch a single OrganisationUnit by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OrganisationUnit, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OrganisationUnit]:
        """List organisationUnits as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OrganisationUnit.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OrganisationUnit,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OrganisationUnit; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OrganisationUnit,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OrganisationUnit; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OrganisationUnit.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OrganisationUnit by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/organisationUnits/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OrganisationUnit (`PATCH /api/organisationUnits/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OrganisationUnit | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OrganisationUnits in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OrganisationUnit from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OrganisationUnitGroupResource:
    """CRUD accessor for the `organisationUnitGroups` collection on DHIS2 v41."""

    _path = "/api/organisationUnitGroups"
    _plural_key = "organisationUnitGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OrganisationUnitGroup:
        """Fetch a single OrganisationUnitGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OrganisationUnitGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OrganisationUnitGroup]:
        """List organisationUnitGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OrganisationUnitGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OrganisationUnitGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OrganisationUnitGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OrganisationUnitGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OrganisationUnitGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OrganisationUnitGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OrganisationUnitGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/organisationUnitGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OrganisationUnitGroup (`PATCH /api/organisationUnitGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OrganisationUnitGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OrganisationUnitGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OrganisationUnitGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OrganisationUnitGroupSetResource:
    """CRUD accessor for the `organisationUnitGroupSets` collection on DHIS2 v41."""

    _path = "/api/organisationUnitGroupSets"
    _plural_key = "organisationUnitGroupSets"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OrganisationUnitGroupSet:
        """Fetch a single OrganisationUnitGroupSet by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OrganisationUnitGroupSet, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OrganisationUnitGroupSet]:
        """List organisationUnitGroupSets as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OrganisationUnitGroupSet.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OrganisationUnitGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OrganisationUnitGroupSet; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OrganisationUnitGroupSet,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OrganisationUnitGroupSet; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OrganisationUnitGroupSet.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OrganisationUnitGroupSet by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/organisationUnitGroupSets/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OrganisationUnitGroupSet (`PATCH /api/organisationUnitGroupSets/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OrganisationUnitGroupSet | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OrganisationUnitGroupSets in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OrganisationUnitGroupSet from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _OrganisationUnitLevelResource:
    """CRUD accessor for the `organisationUnitLevels` collection on DHIS2 v41."""

    _path = "/api/organisationUnitLevels"
    _plural_key = "organisationUnitLevels"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> OrganisationUnitLevel:
        """Fetch a single OrganisationUnitLevel by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=OrganisationUnitLevel, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[OrganisationUnitLevel]:
        """List organisationUnitLevels as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [OrganisationUnitLevel.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: OrganisationUnitLevel,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new OrganisationUnitLevel; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: OrganisationUnitLevel,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing OrganisationUnitLevel; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("OrganisationUnitLevel.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a OrganisationUnitLevel by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/organisationUnitLevels/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a OrganisationUnitLevel (`PATCH /api/organisationUnitLevels/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[OrganisationUnitLevel | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many OrganisationUnitLevels in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the OrganisationUnitLevel from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _PredictorResource:
    """CRUD accessor for the `predictors` collection on DHIS2 v41."""

    _path = "/api/predictors"
    _plural_key = "predictors"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Predictor:
        """Fetch a single Predictor by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Predictor, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Predictor]:
        """List predictors as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Predictor.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Predictor,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Predictor; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Predictor,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Predictor; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Predictor.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Predictor by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/predictors/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Predictor (`PATCH /api/predictors/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Predictor | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Predictors in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Predictor from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _PredictorGroupResource:
    """CRUD accessor for the `predictorGroups` collection on DHIS2 v41."""

    _path = "/api/predictorGroups"
    _plural_key = "predictorGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> PredictorGroup:
        """Fetch a single PredictorGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=PredictorGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[PredictorGroup]:
        """List predictorGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [PredictorGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: PredictorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new PredictorGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: PredictorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing PredictorGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("PredictorGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a PredictorGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/predictorGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a PredictorGroup (`PATCH /api/predictorGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[PredictorGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many PredictorGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the PredictorGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramResource:
    """CRUD accessor for the `programs` collection on DHIS2 v41."""

    _path = "/api/programs"
    _plural_key = "programs"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Program:
        """Fetch a single Program by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Program, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Program]:
        """List programs as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Program.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Program,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Program; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Program,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Program; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Program.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Program by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programs/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Program (`PATCH /api/programs/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Program | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Programs in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Program from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramIndicatorResource:
    """CRUD accessor for the `programIndicators` collection on DHIS2 v41."""

    _path = "/api/programIndicators"
    _plural_key = "programIndicators"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramIndicator:
        """Fetch a single ProgramIndicator by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramIndicator, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramIndicator]:
        """List programIndicators as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramIndicator.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramIndicator,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramIndicator; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramIndicator,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramIndicator; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramIndicator.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramIndicator by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programIndicators/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramIndicator (`PATCH /api/programIndicators/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramIndicator | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramIndicators in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramIndicator from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramIndicatorGroupResource:
    """CRUD accessor for the `programIndicatorGroups` collection on DHIS2 v41."""

    _path = "/api/programIndicatorGroups"
    _plural_key = "programIndicatorGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramIndicatorGroup:
        """Fetch a single ProgramIndicatorGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramIndicatorGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramIndicatorGroup]:
        """List programIndicatorGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramIndicatorGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramIndicatorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramIndicatorGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramIndicatorGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramIndicatorGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramIndicatorGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramIndicatorGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programIndicatorGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramIndicatorGroup (`PATCH /api/programIndicatorGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramIndicatorGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramIndicatorGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramIndicatorGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramNotificationTemplateResource:
    """CRUD accessor for the `programNotificationTemplates` collection on DHIS2 v41."""

    _path = "/api/programNotificationTemplates"
    _plural_key = "programNotificationTemplates"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramNotificationTemplate:
        """Fetch a single ProgramNotificationTemplate by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramNotificationTemplate, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramNotificationTemplate]:
        """List programNotificationTemplates as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramNotificationTemplate.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramNotificationTemplate; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramNotificationTemplate; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramNotificationTemplate.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramNotificationTemplate by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programNotificationTemplates/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramNotificationTemplate (`PATCH /api/programNotificationTemplates/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramNotificationTemplate | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramNotificationTemplates in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramNotificationTemplate from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramRuleResource:
    """CRUD accessor for the `programRules` collection on DHIS2 v41."""

    _path = "/api/programRules"
    _plural_key = "programRules"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramRule:
        """Fetch a single ProgramRule by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramRule, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramRule]:
        """List programRules as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramRule.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramRule,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramRule; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramRule,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramRule; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramRule.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramRule by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programRules/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramRule (`PATCH /api/programRules/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramRule | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramRules in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramRule from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramRuleActionResource:
    """CRUD accessor for the `programRuleActions` collection on DHIS2 v41."""

    _path = "/api/programRuleActions"
    _plural_key = "programRuleActions"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramRuleAction:
        """Fetch a single ProgramRuleAction by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramRuleAction, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramRuleAction]:
        """List programRuleActions as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramRuleAction.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramRuleAction,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramRuleAction; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramRuleAction,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramRuleAction; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramRuleAction.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramRuleAction by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programRuleActions/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramRuleAction (`PATCH /api/programRuleActions/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramRuleAction | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramRuleActions in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramRuleAction from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramRuleVariableResource:
    """CRUD accessor for the `programRuleVariables` collection on DHIS2 v41."""

    _path = "/api/programRuleVariables"
    _plural_key = "programRuleVariables"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramRuleVariable:
        """Fetch a single ProgramRuleVariable by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramRuleVariable, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramRuleVariable]:
        """List programRuleVariables as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramRuleVariable.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramRuleVariable,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramRuleVariable; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramRuleVariable,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramRuleVariable; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramRuleVariable.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramRuleVariable by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programRuleVariables/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramRuleVariable (`PATCH /api/programRuleVariables/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramRuleVariable | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramRuleVariables in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramRuleVariable from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramSectionResource:
    """CRUD accessor for the `programSections` collection on DHIS2 v41."""

    _path = "/api/programSections"
    _plural_key = "programSections"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramSection:
        """Fetch a single ProgramSection by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramSection, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramSection]:
        """List programSections as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramSection.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramSection,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramSection; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramSection,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramSection; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramSection.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramSection by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programSections/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramSection (`PATCH /api/programSections/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramSection | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramSections in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramSection from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramStageResource:
    """CRUD accessor for the `programStages` collection on DHIS2 v41."""

    _path = "/api/programStages"
    _plural_key = "programStages"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramStage:
        """Fetch a single ProgramStage by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramStage, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramStage]:
        """List programStages as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramStage.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramStage,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramStage; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramStage,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramStage; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramStage.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramStage by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programStages/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramStage (`PATCH /api/programStages/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramStage | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramStages in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramStage from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramStageSectionResource:
    """CRUD accessor for the `programStageSections` collection on DHIS2 v41."""

    _path = "/api/programStageSections"
    _plural_key = "programStageSections"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramStageSection:
        """Fetch a single ProgramStageSection by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramStageSection, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramStageSection]:
        """List programStageSections as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramStageSection.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramStageSection,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramStageSection; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramStageSection,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramStageSection; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramStageSection.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramStageSection by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programStageSections/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramStageSection (`PATCH /api/programStageSections/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramStageSection | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramStageSections in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramStageSection from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ProgramStageWorkingListResource:
    """CRUD accessor for the `programStageWorkingLists` collection on DHIS2 v41."""

    _path = "/api/programStageWorkingLists"
    _plural_key = "programStageWorkingLists"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ProgramStageWorkingList:
        """Fetch a single ProgramStageWorkingList by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ProgramStageWorkingList, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ProgramStageWorkingList]:
        """List programStageWorkingLists as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ProgramStageWorkingList.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ProgramStageWorkingList,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ProgramStageWorkingList; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ProgramStageWorkingList,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ProgramStageWorkingList; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ProgramStageWorkingList.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ProgramStageWorkingList by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/programStageWorkingLists/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ProgramStageWorkingList (`PATCH /api/programStageWorkingLists/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ProgramStageWorkingList | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ProgramStageWorkingLists in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ProgramStageWorkingList from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _PushAnalysisResource:
    """CRUD accessor for the `pushAnalysis` collection on DHIS2 v41."""

    _path = "/api/pushAnalysis"
    _plural_key = "pushAnalysis"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> PushAnalysis:
        """Fetch a single PushAnalysis by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=PushAnalysis, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[PushAnalysis]:
        """List pushAnalysis as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [PushAnalysis.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: PushAnalysis,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new PushAnalysis; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: PushAnalysis,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing PushAnalysis; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("PushAnalysis.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a PushAnalysis by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/pushAnalysis/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a PushAnalysis (`PATCH /api/pushAnalysis/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[PushAnalysis | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many PushAnalysiss in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the PushAnalysis from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _RelationshipTypeResource:
    """CRUD accessor for the `relationshipTypes` collection on DHIS2 v41."""

    _path = "/api/relationshipTypes"
    _plural_key = "relationshipTypes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> RelationshipType:
        """Fetch a single RelationshipType by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=RelationshipType, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[RelationshipType]:
        """List relationshipTypes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [RelationshipType.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: RelationshipType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new RelationshipType; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: RelationshipType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing RelationshipType; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("RelationshipType.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a RelationshipType by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/relationshipTypes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a RelationshipType (`PATCH /api/relationshipTypes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[RelationshipType | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many RelationshipTypes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the RelationshipType from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ReportResource:
    """CRUD accessor for the `reports` collection on DHIS2 v41."""

    _path = "/api/reports"
    _plural_key = "reports"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Report:
        """Fetch a single Report by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Report, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Report]:
        """List reports as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Report.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Report,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Report; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Report,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Report; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Report.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Report by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/reports/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Report (`PATCH /api/reports/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Report | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Reports in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Report from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _RouteResource:
    """CRUD accessor for the `routes` collection on DHIS2 v41."""

    _path = "/api/routes"
    _plural_key = "routes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Route:
        """Fetch a single Route by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Route, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Route]:
        """List routes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Route.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Route,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Route; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Route,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Route; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Route.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Route by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/routes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Route (`PATCH /api/routes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Route | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Routes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Route from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _SMSCommandResource:
    """CRUD accessor for the `smsCommands` collection on DHIS2 v41."""

    _path = "/api/smsCommands"
    _plural_key = "smsCommands"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> SMSCommand:
        """Fetch a single SMSCommand by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=SMSCommand, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[SMSCommand]:
        """List smsCommands as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [SMSCommand.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: SMSCommand,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new SMSCommand; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: SMSCommand,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing SMSCommand; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("SMSCommand.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a SMSCommand by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/smsCommands/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a SMSCommand (`PATCH /api/smsCommands/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[SMSCommand | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many SMSCommands in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the SMSCommand from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _SectionResource:
    """CRUD accessor for the `sections` collection on DHIS2 v41."""

    _path = "/api/sections"
    _plural_key = "sections"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Section:
        """Fetch a single Section by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Section, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Section]:
        """List sections as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Section.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Section,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Section; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Section,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Section; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Section.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Section by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/sections/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Section (`PATCH /api/sections/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Section | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Sections in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Section from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _SqlViewResource:
    """CRUD accessor for the `sqlViews` collection on DHIS2 v41."""

    _path = "/api/sqlViews"
    _plural_key = "sqlViews"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> SqlView:
        """Fetch a single SqlView by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=SqlView, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[SqlView]:
        """List sqlViews as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [SqlView.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: SqlView,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new SqlView; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: SqlView,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing SqlView; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("SqlView.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a SqlView by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/sqlViews/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a SqlView (`PATCH /api/sqlViews/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[SqlView | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many SqlViews in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the SqlView from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _TrackedEntityAttributeResource:
    """CRUD accessor for the `trackedEntityAttributes` collection on DHIS2 v41."""

    _path = "/api/trackedEntityAttributes"
    _plural_key = "trackedEntityAttributes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> TrackedEntityAttribute:
        """Fetch a single TrackedEntityAttribute by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=TrackedEntityAttribute, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[TrackedEntityAttribute]:
        """List trackedEntityAttributes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [TrackedEntityAttribute.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: TrackedEntityAttribute,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new TrackedEntityAttribute; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: TrackedEntityAttribute,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing TrackedEntityAttribute; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("TrackedEntityAttribute.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a TrackedEntityAttribute by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/trackedEntityAttributes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a TrackedEntityAttribute (`PATCH /api/trackedEntityAttributes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[TrackedEntityAttribute | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many TrackedEntityAttributes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the TrackedEntityAttribute from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _TrackedEntityFilterResource:
    """CRUD accessor for the `trackedEntityInstanceFilters` collection on DHIS2 v41."""

    _path = "/api/trackedEntityInstanceFilters"
    _plural_key = "trackedEntityInstanceFilters"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> TrackedEntityFilter:
        """Fetch a single TrackedEntityFilter by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=TrackedEntityFilter, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[TrackedEntityFilter]:
        """List trackedEntityInstanceFilters as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [TrackedEntityFilter.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: TrackedEntityFilter,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new TrackedEntityFilter; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: TrackedEntityFilter,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing TrackedEntityFilter; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("TrackedEntityFilter.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a TrackedEntityFilter by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/trackedEntityInstanceFilters/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a TrackedEntityFilter (`PATCH /api/trackedEntityInstanceFilters/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[TrackedEntityFilter | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many TrackedEntityFilters in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the TrackedEntityFilter from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _TrackedEntityTypeResource:
    """CRUD accessor for the `trackedEntityTypes` collection on DHIS2 v41."""

    _path = "/api/trackedEntityTypes"
    _plural_key = "trackedEntityTypes"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> TrackedEntityType:
        """Fetch a single TrackedEntityType by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=TrackedEntityType, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[TrackedEntityType]:
        """List trackedEntityTypes as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [TrackedEntityType.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: TrackedEntityType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new TrackedEntityType; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: TrackedEntityType,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing TrackedEntityType; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("TrackedEntityType.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a TrackedEntityType by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/trackedEntityTypes/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a TrackedEntityType (`PATCH /api/trackedEntityTypes/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[TrackedEntityType | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many TrackedEntityTypes in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the TrackedEntityType from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _UserResource:
    """CRUD accessor for the `users` collection on DHIS2 v41."""

    _path = "/api/users"
    _plural_key = "users"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> User:
        """Fetch a single User by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=User, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[User]:
        """List users as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [User.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: User,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new User; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: User,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing User; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("User.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a User by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/users/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a User (`PATCH /api/users/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[User | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Users in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the User from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _UserGroupResource:
    """CRUD accessor for the `userGroups` collection on DHIS2 v41."""

    _path = "/api/userGroups"
    _plural_key = "userGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> UserGroup:
        """Fetch a single UserGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=UserGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[UserGroup]:
        """List userGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [UserGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: UserGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new UserGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: UserGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing UserGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("UserGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a UserGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/userGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a UserGroup (`PATCH /api/userGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[UserGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many UserGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the UserGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _UserRoleResource:
    """CRUD accessor for the `userRoles` collection on DHIS2 v41."""

    _path = "/api/userRoles"
    _plural_key = "userRoles"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> UserRole:
        """Fetch a single UserRole by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=UserRole, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[UserRole]:
        """List userRoles as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [UserRole.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: UserRole,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new UserRole; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: UserRole,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing UserRole; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("UserRole.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a UserRole by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/userRoles/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a UserRole (`PATCH /api/userRoles/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[UserRole | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many UserRoles in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the UserRole from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ValidationNotificationTemplateResource:
    """CRUD accessor for the `validationNotificationTemplates` collection on DHIS2 v41."""

    _path = "/api/validationNotificationTemplates"
    _plural_key = "validationNotificationTemplates"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ValidationNotificationTemplate:
        """Fetch a single ValidationNotificationTemplate by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ValidationNotificationTemplate, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ValidationNotificationTemplate]:
        """List validationNotificationTemplates as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ValidationNotificationTemplate.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ValidationNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ValidationNotificationTemplate; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ValidationNotificationTemplate,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ValidationNotificationTemplate; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ValidationNotificationTemplate.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ValidationNotificationTemplate by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/validationNotificationTemplates/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ValidationNotificationTemplate (`PATCH /api/validationNotificationTemplates/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ValidationNotificationTemplate | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ValidationNotificationTemplates in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ValidationNotificationTemplate from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ValidationRuleResource:
    """CRUD accessor for the `validationRules` collection on DHIS2 v41."""

    _path = "/api/validationRules"
    _plural_key = "validationRules"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ValidationRule:
        """Fetch a single ValidationRule by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ValidationRule, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ValidationRule]:
        """List validationRules as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ValidationRule.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ValidationRule,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ValidationRule; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ValidationRule,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ValidationRule; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ValidationRule.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ValidationRule by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/validationRules/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ValidationRule (`PATCH /api/validationRules/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ValidationRule | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ValidationRules in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ValidationRule from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _ValidationRuleGroupResource:
    """CRUD accessor for the `validationRuleGroups` collection on DHIS2 v41."""

    _path = "/api/validationRuleGroups"
    _plural_key = "validationRuleGroups"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> ValidationRuleGroup:
        """Fetch a single ValidationRuleGroup by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=ValidationRuleGroup, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[ValidationRuleGroup]:
        """List validationRuleGroups as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [ValidationRuleGroup.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: ValidationRuleGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new ValidationRuleGroup; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: ValidationRuleGroup,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing ValidationRuleGroup; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("ValidationRuleGroup.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a ValidationRuleGroup by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/validationRuleGroups/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a ValidationRuleGroup (`PATCH /api/validationRuleGroups/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[ValidationRuleGroup | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many ValidationRuleGroups in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the ValidationRuleGroup from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class _VisualizationResource:
    """CRUD accessor for the `visualizations` collection on DHIS2 v41."""

    _path = "/api/visualizations"
    _plural_key = "visualizations"

    def __init__(self, client: Dhis2Client) -> None:
        """Bind the resource accessor to the sharing client."""
        self._client = client

    async def get(self, uid: str, *, fields: str | None = None) -> Visualization:
        """Fetch a single Visualization by its UID."""
        params = {"fields": fields} if fields else None
        return await self._client.get(f"{self._path}/{uid}", model=Visualization, params=params)

    async def list(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> list[Visualization]:
        """List visualizations as typed schemas.

        Every DHIS2 /api/<resource> query parameter is forwarded. `filters`
        and `order` may repeat (sent as `?filter=a&filter=b`). `root_junction`
        is `"AND"` (default) or `"OR"`.

        Paging defaults:
          - `paging=True` when `page` or `page_size` is set (honours the bounds).
          - `paging=False` otherwise (returns the full catalog in one response).
          - Pass `paging` explicitly to override either default.
        """
        effective_paging = paging if paging is not None else (page is not None or page_size is not None)
        raw = await self.list_raw(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=effective_paging,
            translate=translate,
            locale=locale,
        )
        items = raw.get(self._plural_key)
        if not isinstance(items, list):
            return []
        return [Visualization.model_validate(item) for item in items]

    async def list_raw(
        self,
        *,
        fields: str | None = None,
        filters: Sequence[str] | None = None,
        root_junction: str | None = None,
        order: Sequence[str] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        paging: bool | None = None,
        translate: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Raw list response — includes the `pager` block when paging is on."""
        params = _build_list_params(
            fields=fields,
            filters=filters,
            root_junction=root_junction,
            order=order,
            page=page,
            page_size=page_size,
            paging=paging,
            translate=translate,
            locale=locale,
        )
        return await self._client.get_raw(self._path, params=params)

    async def create(
        self,
        item: Visualization,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """POST a new Visualization; returns the raw DHIS2 import-summary payload.

        Optional write flags forwarded to DHIS2 as query params:
        `mergeMode`, `importStrategy`, `skipSharing`, `skipTranslation`.
        """
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.post_raw(self._path, payload, params=params)

    async def update(
        self,
        item: Visualization,
        *,
        merge_mode: str | None = None,
        import_strategy: str | None = None,
        skip_sharing: bool | None = None,
        skip_translation: bool | None = None,
    ) -> dict[str, Any]:
        """PUT-replace an existing Visualization; reads `item.id` for the URL.

        Pass `merge_mode="REPLACE"` to force nested-list replacement — DHIS2
        v42's default PUT behaviour merges nested lists additively, so
        omitted items aren't removed without the flag.
        """
        uid = getattr(item, "id", None)
        if not uid:
            raise ValueError("Visualization.id is required for update")
        payload = item.model_dump(by_alias=True, exclude_none=True, mode="json")
        params = _build_write_params(
            merge_mode=merge_mode,
            import_strategy=import_strategy,
            skip_sharing=skip_sharing,
            skip_translation=skip_translation,
        )
        return await self._client.put_raw(f"{self._path}/{uid}", payload, params=params)

    async def delete(self, uid: str) -> dict[str, Any]:
        """DELETE a Visualization by UID."""
        return await self._client.delete_raw(f"{self._path}/{uid}")

    async def add_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """POST a per-item collection-member shortcut.

        DHIS2 exposes `POST /api/visualizations/{parent_uid}/<collection>/<item_uid>`
        for most collection fields (e.g. `organisationUnits`, `indicators`,
        `dataElements` on their respective parents). Use this to link a
        simple ref without round-tripping the parent object.

        For join tables with extra flags (DataSet.dataSetElements carries
        `categoryCombo`, TrackedEntityType.trackedEntityTypeAttributes
        carries `mandatory`/`searchable`), the per-item endpoint only
        accepts a bare `{id}` ref — reach for the hand-written accessor
        on the specific resource when you need the flags.
        """
        return await self._client.post_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def remove_collection_item(
        self,
        parent_uid: str,
        collection: str,
        item_uid: str,
    ) -> dict[str, Any]:
        """DELETE a per-item collection-member shortcut.

        Mirrors `add_collection_item`. Drops the member from the parent's
        collection without round-tripping the parent object.
        """
        return await self._client.delete_raw(f"{self._path}/{parent_uid}/{collection}/{item_uid}")

    async def patch(self, uid: str, ops: Sequence[JsonPatchOp | dict[str, Any]]) -> dict[str, Any]:
        """Apply an RFC 6902 JSON Patch to a Visualization (`PATCH /api/visualizations/{uid}`).

        Accepts typed `JsonPatchOp` variants (`AddOp`, `ReplaceOp`, `RemoveOp`,
        `MoveOp`, `CopyOp`, `TestOp`) or raw `{op, path, ...}` dicts; mixed
        lists are fine — dicts go through `JsonPatchOpAdapter` for validation.
        Returns the raw DHIS2 response (typically a `WebMessage` envelope).
        """
        body = _serialise_patch_ops(ops)
        return await self._client.patch_raw(f"{self._path}/{uid}", body)

    async def save_bulk(
        self,
        items: Sequence[Visualization | dict[str, Any]],
        *,
        import_strategy: str = "CREATE_AND_UPDATE",
        atomic_mode: str = "NONE",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """POST many Visualizations in one request via `/api/metadata`.

        Faster than N `create()` / `update()` round-trips. `import_strategy`
        picks the semantics DHIS2 applies per object: `CREATE` /
        `CREATE_AND_UPDATE` (default) / `UPDATE` / `DELETE`. `atomic_mode=ALL`
        rolls the whole bundle back on any conflict (default `NONE` lets
        partial failures through — per-object conflicts surface on the
        `WebMessage` envelope's `typeReports`). `dry_run=True` runs
        validation + preheat but commits nothing.

        Empty `items` short-circuits with a no-op envelope (no HTTP call).
        Any pydantic model (including the Visualization from a
        sibling generated tree — e.g. v42 callers feeding a v43 client)
        dumps via `model_dump`; bare dicts pass through unchanged.
        """
        if not items:
            return {"status": "OK", "message": "no items supplied"}
        payload = {
            self._plural_key: [
                item.model_dump(by_alias=True, exclude_none=True, mode="json") if isinstance(item, BaseModel) else item
                for item in items
            ],
        }
        params: dict[str, Any] = {"importStrategy": import_strategy, "atomicMode": atomic_mode}
        if dry_run:
            params["importMode"] = "VALIDATE"
        return await self._client.post_raw("/api/metadata", payload, params=params)


class Resources:
    """All generated resource accessors bundled for Dhis2Client."""

    def __init__(self, client: Dhis2Client) -> None:
        """Instantiate every resource accessor for `client`."""
        self.aggregate_data_exchanges: _AggregateDataExchangeResource = _AggregateDataExchangeResource(client)
        self.analytics_table_hooks: _AnalyticsTableHookResource = _AnalyticsTableHookResource(client)
        self.api_token: _ApiTokenResource = _ApiTokenResource(client)
        self.attributes: _AttributeResource = _AttributeResource(client)
        self.categories: _CategoryResource = _CategoryResource(client)
        self.category_combos: _CategoryComboResource = _CategoryComboResource(client)
        self.category_options: _CategoryOptionResource = _CategoryOptionResource(client)
        self.category_option_combos: _CategoryOptionComboResource = _CategoryOptionComboResource(client)
        self.category_option_groups: _CategoryOptionGroupResource = _CategoryOptionGroupResource(client)
        self.category_option_group_sets: _CategoryOptionGroupSetResource = _CategoryOptionGroupSetResource(client)
        self.constants: _ConstantResource = _ConstantResource(client)
        self.dashboards: _DashboardResource = _DashboardResource(client)
        self.data_approval_levels: _DataApprovalLevelResource = _DataApprovalLevelResource(client)
        self.data_approval_workflows: _DataApprovalWorkflowResource = _DataApprovalWorkflowResource(client)
        self.data_elements: _DataElementResource = _DataElementResource(client)
        self.data_element_groups: _DataElementGroupResource = _DataElementGroupResource(client)
        self.data_element_group_sets: _DataElementGroupSetResource = _DataElementGroupSetResource(client)
        self.data_entry_forms: _DataEntryFormResource = _DataEntryFormResource(client)
        self.data_sets: _DataSetResource = _DataSetResource(client)
        self.data_set_notification_templates: _DataSetNotificationTemplateResource = (
            _DataSetNotificationTemplateResource(client)
        )
        self.documents: _DocumentResource = _DocumentResource(client)
        self.event_charts: _EventChartResource = _EventChartResource(client)
        self.event_filters: _EventFilterResource = _EventFilterResource(client)
        self.event_hooks: _EventHookResource = _EventHookResource(client)
        self.event_reports: _EventReportResource = _EventReportResource(client)
        self.event_visualizations: _EventVisualizationResource = _EventVisualizationResource(client)
        self.expression_dimension_items: _ExpressionDimensionItemResource = _ExpressionDimensionItemResource(client)
        self.external_map_layers: _ExternalMapLayerResource = _ExternalMapLayerResource(client)
        self.indicators: _IndicatorResource = _IndicatorResource(client)
        self.indicator_groups: _IndicatorGroupResource = _IndicatorGroupResource(client)
        self.indicator_group_sets: _IndicatorGroupSetResource = _IndicatorGroupSetResource(client)
        self.indicator_types: _IndicatorTypeResource = _IndicatorTypeResource(client)
        self.job_configurations: _JobConfigurationResource = _JobConfigurationResource(client)
        self.legend_sets: _LegendSetResource = _LegendSetResource(client)
        self.maps: _MapResource = _MapResource(client)
        self.map_views: _MapViewResource = _MapViewResource(client)
        self.o_auth2_clients: _OAuth2ClientResource = _OAuth2ClientResource(client)
        self.options: _OptionResource = _OptionResource(client)
        self.option_groups: _OptionGroupResource = _OptionGroupResource(client)
        self.option_group_sets: _OptionGroupSetResource = _OptionGroupSetResource(client)
        self.option_sets: _OptionSetResource = _OptionSetResource(client)
        self.organisation_units: _OrganisationUnitResource = _OrganisationUnitResource(client)
        self.organisation_unit_groups: _OrganisationUnitGroupResource = _OrganisationUnitGroupResource(client)
        self.organisation_unit_group_sets: _OrganisationUnitGroupSetResource = _OrganisationUnitGroupSetResource(client)
        self.organisation_unit_levels: _OrganisationUnitLevelResource = _OrganisationUnitLevelResource(client)
        self.predictors: _PredictorResource = _PredictorResource(client)
        self.predictor_groups: _PredictorGroupResource = _PredictorGroupResource(client)
        self.programs: _ProgramResource = _ProgramResource(client)
        self.program_indicators: _ProgramIndicatorResource = _ProgramIndicatorResource(client)
        self.program_indicator_groups: _ProgramIndicatorGroupResource = _ProgramIndicatorGroupResource(client)
        self.program_notification_templates: _ProgramNotificationTemplateResource = (
            _ProgramNotificationTemplateResource(client)
        )
        self.program_rules: _ProgramRuleResource = _ProgramRuleResource(client)
        self.program_rule_actions: _ProgramRuleActionResource = _ProgramRuleActionResource(client)
        self.program_rule_variables: _ProgramRuleVariableResource = _ProgramRuleVariableResource(client)
        self.program_sections: _ProgramSectionResource = _ProgramSectionResource(client)
        self.program_stages: _ProgramStageResource = _ProgramStageResource(client)
        self.program_stage_sections: _ProgramStageSectionResource = _ProgramStageSectionResource(client)
        self.program_stage_working_lists: _ProgramStageWorkingListResource = _ProgramStageWorkingListResource(client)
        self.push_analysis: _PushAnalysisResource = _PushAnalysisResource(client)
        self.relationship_types: _RelationshipTypeResource = _RelationshipTypeResource(client)
        self.reports: _ReportResource = _ReportResource(client)
        self.routes: _RouteResource = _RouteResource(client)
        self.sms_commands: _SMSCommandResource = _SMSCommandResource(client)
        self.sections: _SectionResource = _SectionResource(client)
        self.sql_views: _SqlViewResource = _SqlViewResource(client)
        self.tracked_entity_attributes: _TrackedEntityAttributeResource = _TrackedEntityAttributeResource(client)
        self.tracked_entity_instance_filters: _TrackedEntityFilterResource = _TrackedEntityFilterResource(client)
        self.tracked_entity_types: _TrackedEntityTypeResource = _TrackedEntityTypeResource(client)
        self.users: _UserResource = _UserResource(client)
        self.user_groups: _UserGroupResource = _UserGroupResource(client)
        self.user_roles: _UserRoleResource = _UserRoleResource(client)
        self.validation_notification_templates: _ValidationNotificationTemplateResource = (
            _ValidationNotificationTemplateResource(client)
        )
        self.validation_rules: _ValidationRuleResource = _ValidationRuleResource(client)
        self.validation_rule_groups: _ValidationRuleGroupResource = _ValidationRuleGroupResource(client)
        self.visualizations: _VisualizationResource = _VisualizationResource(client)

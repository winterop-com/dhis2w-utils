"""PredictorGroup authoring — `Dhis2Client.predictor_groups`.

`PredictorGroup`s collect Predictors so `d2w maintenance predictors
run --group <uid>` exercises a coherent subset in one pass. Mirrors
the IndicatorGroup / ValidationRuleGroup CRUD + per-item membership
pattern.

Running a group lives on `PredictorsAccessor.run_group` (kept for
backward compatibility with existing callers); the group accessor
focuses on the authoring verbs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dhis2w_client.generated.v41.schemas import Predictor, PredictorGroup

if TYPE_CHECKING:
    from dhis2w_client.v41.client import Dhis2Client
from dhis2w_client.v41.envelopes import WebMessageResponse

_GROUP_FIELDS: str = "id,name,shortName,code,description,predictors[id,name,code]"
_MEMBER_FIELDS: str = "id,name,shortName,code,periodType,output[id,name,code]"


class PredictorGroupsAccessor:
    """`Dhis2Client.predictor_groups` — CRUD + membership over `/api/predictorGroups`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_all(self) -> list[PredictorGroup]:
        """Return every PredictorGroup."""
        return cast(
            list[PredictorGroup],
            await self._client.resources.predictor_groups.list(
                fields=_GROUP_FIELDS,
                paging=False,
            ),
        )

    async def get(self, uid: str) -> PredictorGroup:
        """Fetch one group by UID with its `predictors` refs populated."""
        return await self._client.get(
            f"/api/predictorGroups/{uid}", model=PredictorGroup, params={"fields": _GROUP_FIELDS}
        )

    async def list_members(
        self,
        uid: str,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> list[Predictor]:
        """Page through Predictors belonging to one group."""
        return cast(
            list[Predictor],
            await self._client.resources.predictors.list(
                fields=_MEMBER_FIELDS,
                filters=[f"predictorGroups.id:eq:{uid}"],
                order=["name:asc"],
                page=page,
                page_size=page_size,
            ),
        )

    async def create(
        self,
        *,
        name: str,
        short_name: str | None = None,
        uid: str | None = None,
        code: str | None = None,
        description: str | None = None,
    ) -> PredictorGroup:
        """Create an empty PredictorGroup; add members afterwards via `add_members`."""
        payload: dict[str, Any] = {"name": name}
        if short_name:
            payload["shortName"] = short_name
        if uid:
            payload["id"] = uid
        if code:
            payload["code"] = code
        if description:
            payload["description"] = description
        envelope = await self._client.post("/api/predictorGroups", payload, model=WebMessageResponse)
        created_uid = envelope.created_uid or uid
        if not created_uid:
            raise RuntimeError("predictor-group create did not return a uid")
        return await self.get(created_uid)

    async def update(self, group: PredictorGroup) -> PredictorGroup:
        """PUT an edited PredictorGroup back. `group.id` must be set."""
        if not group.id:
            raise ValueError("update requires group.id to be set")
        body = group.model_dump(by_alias=True, exclude_none=True, mode="json")
        await self._client.put_raw(f"/api/predictorGroups/{group.id}", body=body)
        return await self.get(group.id)

    async def add_members(self, uid: str, *, predictor_uids: list[str]) -> PredictorGroup:
        """Add Predictors to the group via the per-item POST shortcut."""
        for predictor_uid in predictor_uids:
            await self._client.resources.predictor_groups.add_collection_item(uid, "predictors", predictor_uid)
        return await self.get(uid)

    async def remove_members(self, uid: str, *, predictor_uids: list[str]) -> PredictorGroup:
        """Drop Predictors from the group via the per-item DELETE shortcut."""
        for predictor_uid in predictor_uids:
            await self._client.resources.predictor_groups.remove_collection_item(uid, "predictors", predictor_uid)
        return await self.get(uid)

    async def delete(self, uid: str) -> None:
        """Delete the grouping row — member predictors stay."""
        if not uid:
            raise ValueError("delete requires a non-empty uid")
        await self._client.resources.predictor_groups.delete(uid)


__all__ = [
    "PredictorGroup",
    "PredictorGroupsAccessor",
]

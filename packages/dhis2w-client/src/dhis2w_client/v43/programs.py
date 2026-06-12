"""Program authoring — `Dhis2Client.programs`.

A DHIS2 `Program` is the tracker container: it binds a
`TrackedEntityType` (for `WITH_REGISTRATION` programs), a set of
`TrackedEntityAttribute`s shown on the enrollment form, and the
`OrganisationUnit`s that can capture enrollments or events. Programs
come in two flavours:

- **WITH_REGISTRATION** — tracker programs. Need a `trackedEntityType`
  and register individual TEIs before capturing events.
- **WITHOUT_REGISTRATION** — event programs. Capture anonymous events
  directly; no TET required.

This module is the authoring flip side of the existing tracker-write
plugin (`d2w tracker register / enroll / add-event`). The leaf half
(TET + TEA) lives in `tracked_entity_types.py` /
`tracked_entity_attributes.py`; the inner layer (ProgramStage + PSDE)
ships in a follow-up.

Surface:
- `create(...)` — named kwargs over the minimal required subset
  (`name`, `short_name`, `program_type`) plus the refs + common knobs.
  For `WITH_REGISTRATION`, `tracked_entity_type_uid` is required.
- `add_attribute(program_uid, tea_uid, ...)` — wire a TEA into the
  enrollment form via the `programTrackedEntityAttributes[]` join
  table.
- `add_organisation_unit(program_uid, ou_uid)` — scope the program
  to an OU. Tracker writes need at least one OU in scope to register.
- `rename(uid, ...)` / `delete(uid)` — standard pathways.
- `set_labels(uid, ...)` — v43-only: customise the `enrollmentsLabel`
  / `eventsLabel` / `programStagesLabel` UI strings (Capture / Tracker
  Capture apps).
- `set_change_log_enabled(uid, enabled)` — v43-only: flip the
  `enableChangeLog` server-side audit toggle.
- `set_enrollment_category_combo(uid, cc_uid)` — v43-only: set the
  `enrollmentCategoryCombo` alt-CC applied at enrollment time.

The three v43-only setters are deliberately split — they address
unrelated concerns (UI text vs behavioural audit toggle vs data-model
ref) that happen to land on the same v43 schema delta.

No `*Spec` builder — continues the spec-audit data point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dhis2w_client.generated.v43.enums import ProgramType
from dhis2w_client.generated.v43.schemas import Program

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client
from dhis2w_client.v43.envelopes import WebMessageResponse

_PROGRAM_FIELDS: str = (
    "id,name,shortName,code,formName,description,"
    "programType,trackedEntityType[id,name],"
    "categoryCombo[id,name],"
    "displayFrontPageList,displayIncidentDate,"
    "enrollmentDateLabel,incidentDateLabel,featureType,"
    "onlyEnrollOnce,selectEnrollmentDatesInFuture,selectIncidentDatesInFuture,"
    "expiryDays,expiryPeriodType,"
    "minAttributesRequiredToSearch,maxTeiCountToReturn,"
    "useFirstStageDuringRegistration,"
    # v43-only configuration surface: enableChangeLog gates the change-log
    # endpoints; enrollmentsLabel / eventsLabel / programStagesLabel
    # override UI terminology; enrollmentCategoryCombo carries the optional
    # alt-cc applied at enrollment.
    "enableChangeLog,enrollmentsLabel,eventsLabel,programStagesLabel,"
    "enrollmentCategoryCombo[id,name],"
    "programTrackedEntityAttributes["
    "trackedEntityAttribute[id,name,valueType],mandatory,searchable,displayInList,"
    "sortOrder,allowFutureDate,renderOptionsAsRadio"
    "],"
    "organisationUnits[id,name],"
    "programStages[id,name,sortOrder]"
)


class ProgramsAccessor:
    """`Dhis2Client.programs` — CRUD + attribute + OU linkage over `/api/programs`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_all(
        self,
        *,
        program_type: ProgramType | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[Program]:
        """Page through Programs, optionally filtered by programType."""
        filters: list[str] | None = None
        if program_type is not None:
            value = program_type.value if isinstance(program_type, ProgramType) else program_type
            filters = [f"programType:eq:{value}"]
        return cast(
            list[Program],
            await self._client.resources.programs.list(
                fields=_PROGRAM_FIELDS,
                filters=filters,
                page=page,
                page_size=page_size,
            ),
        )

    async def get(self, uid: str) -> Program:
        """Fetch one Program with its PTEAs, OUs, and ProgramStage refs inline."""
        return await self._client.get(f"/api/programs/{uid}", model=Program, params={"fields": _PROGRAM_FIELDS})

    async def create(
        self,
        *,
        name: str,
        short_name: str,
        program_type: ProgramType | str = ProgramType.WITH_REGISTRATION,
        tracked_entity_type_uid: str | None = None,
        category_combo_uid: str | None = None,
        description: str | None = None,
        code: str | None = None,
        form_name: str | None = None,
        display_incident_date: bool | None = None,
        enrollment_date_label: str | None = None,
        incident_date_label: str | None = None,
        feature_type: str | None = None,
        only_enroll_once: bool | None = None,
        select_enrollment_dates_in_future: bool | None = None,
        select_incident_dates_in_future: bool | None = None,
        expiry_days: int | None = None,
        min_attributes_required_to_search: int | None = None,
        max_tei_count_to_return: int | None = None,
        use_first_stage_during_registration: bool | None = None,
        uid: str | None = None,
    ) -> Program:
        """Create a Program.

        `program_type=WITH_REGISTRATION` (default) requires
        `tracked_entity_type_uid`; pass `WITHOUT_REGISTRATION` for an
        event program that skips TEI registration.
        `category_combo_uid` defaults to the instance-wide default
        combo (DHIS2 rejects programs without a CC ref).
        `display_incident_date` + `incident_date_label` govern whether
        the enrollment form captures an incident date distinct from
        the enrollment date (required by some case-management flows).
        """
        resolved_type = program_type.value if isinstance(program_type, ProgramType) else program_type
        if resolved_type == "WITH_REGISTRATION" and not tracked_entity_type_uid:
            raise ValueError("WITH_REGISTRATION programs require tracked_entity_type_uid")
        default_combo = category_combo_uid or await self._client.system.default_category_combo_uid()
        payload: dict[str, Any] = {
            "name": name,
            "shortName": short_name,
            "programType": resolved_type,
            "categoryCombo": {"id": default_combo},
        }
        if tracked_entity_type_uid:
            payload["trackedEntityType"] = {"id": tracked_entity_type_uid}
        if uid:
            payload["id"] = uid
        if code:
            payload["code"] = code
        if form_name:
            payload["formName"] = form_name
        if description:
            payload["description"] = description
        if display_incident_date is not None:
            payload["displayIncidentDate"] = display_incident_date
        if enrollment_date_label:
            payload["enrollmentDateLabel"] = enrollment_date_label
        if incident_date_label:
            payload["incidentDateLabel"] = incident_date_label
        if feature_type:
            payload["featureType"] = feature_type
        if only_enroll_once is not None:
            payload["onlyEnrollOnce"] = only_enroll_once
        if select_enrollment_dates_in_future is not None:
            payload["selectEnrollmentDatesInFuture"] = select_enrollment_dates_in_future
        if select_incident_dates_in_future is not None:
            payload["selectIncidentDatesInFuture"] = select_incident_dates_in_future
        if expiry_days is not None:
            payload["expiryDays"] = expiry_days
        if min_attributes_required_to_search is not None:
            payload["minAttributesRequiredToSearch"] = min_attributes_required_to_search
        if max_tei_count_to_return is not None:
            payload["maxTeiCountToReturn"] = max_tei_count_to_return
        if use_first_stage_during_registration is not None:
            payload["useFirstStageDuringRegistration"] = use_first_stage_during_registration
        envelope = await self._client.post("/api/programs", payload, model=WebMessageResponse)
        created_uid = envelope.created_uid or uid
        if not created_uid:
            raise RuntimeError("program create did not return a uid")
        return await self.get(created_uid)

    async def update(self, program: Program) -> Program:
        """PUT an edited Program back. `program.id` must be set.

        DHIS2 v42's Program PUT importer treats nested-list updates
        additively without `mergeMode=REPLACE` — items omitted from a
        list aren't removed. The accessor always passes the flag so
        `add_attribute` / `remove_attribute` behave symmetrically.
        """
        if not program.id:
            raise ValueError("update requires program.id to be set")
        body = program.model_dump(by_alias=True, exclude_none=True, mode="json")
        _strip_self_ref_from_ptea(body)
        await self._client.put_raw(f"/api/programs/{program.id}", body=body, params={"mergeMode": "REPLACE"})
        return await self.get(program.id)

    async def rename(
        self,
        uid: str,
        *,
        name: str | None = None,
        short_name: str | None = None,
        form_name: str | None = None,
        description: str | None = None,
    ) -> Program:
        """Partial-update shortcut — read, mutate the label fields, PUT."""
        if name is None and short_name is None and form_name is None and description is None:
            raise ValueError("rename requires at least one of name / short_name / form_name / description")
        current = await self.get(uid)
        if name is not None:
            current.name = name
        if short_name is not None:
            current.shortName = short_name
        if form_name is not None:
            current.formName = form_name
        if description is not None:
            current.description = description
        return await self.update(current)

    async def set_labels(
        self,
        uid: str,
        *,
        enrollments_label: str | None = None,
        events_label: str | None = None,
        program_stages_label: str | None = None,
    ) -> Program:
        """Set the v43-only UI label overrides on a Program.

        DHIS2 2.43 lets each Program override the default "Enrollments" /
        "Events" / "Program stages" UI terminology shown in the Capture and
        Tracker Capture apps. Useful for domain-native vocabulary — e.g.
        "Visits", "Encounters", "Care stages".

        None-valued kwargs are left untouched on the program; pass only the
        labels you want to change. DHIS2 enforces 2-255 chars per label.
        Returns the re-fetched Program.
        """
        if enrollments_label is None and events_label is None and program_stages_label is None:
            raise ValueError(
                "set_labels requires at least one of enrollments_label / events_label / program_stages_label"
            )
        return await self._partial_program_put(
            uid,
            {
                "enrollmentsLabel": enrollments_label,
                "eventsLabel": events_label,
                "programStagesLabel": program_stages_label,
            },
        )

    async def set_change_log_enabled(self, uid: str, enabled: bool) -> Program:
        """Toggle the v43-only `enableChangeLog` server-side audit flag on a Program.

        When `True`, DHIS2 records enrollment + event change-logs surfaced via
        `/api/tracker/enrollments/{uid}/changeLogs`,
        `/api/tracker/events/{event}/changeLogs`, and the matching tracker
        export endpoints. Default off. Behavioural switch — orthogonal to
        the UI label overrides set by `set_labels`. Returns the re-fetched
        Program.
        """
        return await self._partial_program_put(uid, {"enableChangeLog": enabled})

    async def set_enrollment_category_combo(self, uid: str, category_combo_uid: str) -> Program:
        """Set the v43-only `enrollmentCategoryCombo` reference on a Program.

        An alternative CategoryCombo applied specifically at enrollment time,
        distinct from the Program's regular `categoryCombo`. Lets programs
        carry one disaggregation for the Program-level metadata and a
        different one for enrollment-time data capture. Returns the
        re-fetched Program.
        """
        if not category_combo_uid:
            raise ValueError("set_enrollment_category_combo requires a non-empty category_combo_uid")
        return await self._partial_program_put(uid, {"enrollmentCategoryCombo": {"id": category_combo_uid}})

    async def _partial_program_put(self, uid: str, fields: dict[str, Any]) -> Program:
        """Read-modify-write helper for the v43 partial-update accessors.

        Drops `None`-valued entries so callers can pass an "intent" dict
        without filtering; PTEA self-refs are stripped to avoid the
        DHIS2 import conflict. `mergeMode=REPLACE` is always set so
        existing PUT semantics on nested lists hold.
        """
        current = await self.get(uid)
        raw = current.model_dump(by_alias=True, exclude_none=True, mode="json")
        _strip_self_ref_from_ptea(raw)
        for key, value in fields.items():
            if value is not None:
                raw[key] = value
        await self._client.put_raw(f"/api/programs/{uid}", body=raw, params={"mergeMode": "REPLACE"})
        return await self.get(uid)

    async def add_attribute(
        self,
        program_uid: str,
        attribute_uid: str,
        *,
        mandatory: bool = False,
        searchable: bool = False,
        display_in_list: bool = True,
        sort_order: int | None = None,
        allow_future_date: bool = False,
        render_options_as_radio: bool = False,
    ) -> Program:
        """Wire a TrackedEntityAttribute into the Program's enrollment form.

        The PTEA join table carries the enrollment-form flags
        (`mandatory`, `searchable`, `displayInList`, `sortOrder`,
        `allowFutureDate`, `renderOptionsAsRadio`). Idempotent when
        the TEA is already linked — the existing PTEA is left alone.
        """
        current = await self.get(program_uid)
        raw = current.model_dump(by_alias=True, exclude_none=True, mode="json")
        _strip_self_ref_from_ptea(raw)
        existing = raw.get("programTrackedEntityAttributes") or []
        if any(
            (entry.get("trackedEntityAttribute") or {}).get("id") == attribute_uid
            for entry in existing
            if isinstance(entry, dict)
        ):
            return current
        new_entry: dict[str, Any] = {
            "trackedEntityAttribute": {"id": attribute_uid},
            "mandatory": mandatory,
            "searchable": searchable,
            "displayInList": display_in_list,
            "allowFutureDate": allow_future_date,
            "renderOptionsAsRadio": render_options_as_radio,
        }
        if sort_order is not None:
            new_entry["sortOrder"] = sort_order
        existing.append(new_entry)
        raw["programTrackedEntityAttributes"] = existing
        await self._client.put_raw(f"/api/programs/{program_uid}", body=raw, params={"mergeMode": "REPLACE"})
        return await self.get(program_uid)

    async def remove_attribute(self, program_uid: str, attribute_uid: str) -> Program:
        """Drop a TrackedEntityAttribute from the Program's enrollment form."""
        current = await self.get(program_uid)
        raw = current.model_dump(by_alias=True, exclude_none=True, mode="json")
        _strip_self_ref_from_ptea(raw)
        existing = raw.get("programTrackedEntityAttributes") or []
        filtered = [
            entry
            for entry in existing
            if isinstance(entry, dict) and (entry.get("trackedEntityAttribute") or {}).get("id") != attribute_uid
        ]
        if len(filtered) == len(existing):
            return current
        raw["programTrackedEntityAttributes"] = filtered
        await self._client.put_raw(f"/api/programs/{program_uid}", body=raw, params={"mergeMode": "REPLACE"})
        return await self.get(program_uid)

    async def add_organisation_unit(self, program_uid: str, organisation_unit_uid: str) -> Program:
        """Scope the Program to an additional OrganisationUnit via the per-item POST shortcut."""
        await self._client.resources.programs.add_collection_item(
            program_uid,
            "organisationUnits",
            organisation_unit_uid,
        )
        return await self.get(program_uid)

    async def remove_organisation_unit(self, program_uid: str, organisation_unit_uid: str) -> Program:
        """Drop an OrganisationUnit from the Program scope via the per-item DELETE shortcut."""
        await self._client.resources.programs.remove_collection_item(
            program_uid,
            "organisationUnits",
            organisation_unit_uid,
        )
        return await self.get(program_uid)

    async def delete(self, uid: str) -> None:
        """Delete a Program — DHIS2 rejects deletes on programs with enrolled TEIs or saved events."""
        if not uid:
            raise ValueError("delete requires a non-empty uid")
        await self._client.resources.programs.delete(uid)


def _strip_self_ref_from_ptea(payload: dict[str, Any]) -> None:
    """Drop the self-referencing `program` field from each PTEA entry.

    DHIS2's `/api/programs/{uid}` read embeds
    `programTrackedEntityAttributes[].program = {id: <parent>}`; its
    importer rejects the PUT with a self-reference conflict when that
    field is round-tripped. Mirrors the DataSet + DataSetElement and
    TrackedEntityType + TETA workarounds.
    """
    entries = payload.get("programTrackedEntityAttributes")
    if not isinstance(entries, list):
        return
    cleaned: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            cleaned.append({k: v for k, v in entry.items() if k != "program"})
    payload["programTrackedEntityAttributes"] = cleaned


__all__ = [
    "Program",
    "ProgramsAccessor",
]

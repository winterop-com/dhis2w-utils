"""Integration-grade helpers for DHIS2 ProgramRule workflows.

`/api/programRules` + `/api/programRuleVariables` + `/api/programRuleActions`
ship the tracker-side business-logic surface. Generic CRUD works via the
generated `client.resources.program_rules` accessor (and the other two).
This accessor layers the **authoring + debugging** helpers that generic
CRUD doesn't provide:

- `list_all(program_uid=None)` — rules for a program (or every rule)
  sorted by priority + with actions resolved inline. One round-trip.
- `get_rule(uid)` — one rule with its actions.
- `variables_for(program_uid)` — every variable in scope for a program,
  with source-type + the referenced DE / TEA surfaced on a typed model.
- `actions_for(rule_uid)` — the actions that fire for one rule.
- `validate_expression(expression)` — parse-check via the shared
  `/api/expressions/description` path used by validation rules +
  predictors (reuses `client.validation.describe_expression`).

Two DHIS2 wire quirks worked around under the hood:

- POST bodies use `programRuleVariableSourceType` (not `sourceType`
  per `/api/schemas`). The generated model with `extra="allow"`
  accepts either, but GETs only surface the wire name, so this
  accessor asks for it by name in fields selectors.
- `fields=*` silently omits `programRuleVariableSourceType`. Every
  list/get call here names the field explicitly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dhis2w_client.generated.v43.schemas import (
    ProgramRule,
    ProgramRuleAction,
    ProgramRuleVariable,
)
from dhis2w_client.v43._collection import parse_collection

if TYPE_CHECKING:
    from dhis2w_client.v43.client import Dhis2Client
    from dhis2w_client.v43.validation import ExpressionContext, ExpressionDescription


# Explicit fields selectors — DHIS2's `fields=*` quirk means the
# source-type property drops off generic selectors. Name every property
# we want to surface so the typed models populate correctly.
_VARIABLE_FIELDS: str = (
    "id,name,programRuleVariableSourceType,useCodeForOptionSet,valueType,"
    "program[id,name],dataElement[id,name,code],attribute[id,name,code],"
    "programStage[id,name]"
)
_ACTION_FIELDS: str = (
    "id,programRuleActionType,content,data,"
    "programRule[id,name],dataElement[id,name,code],attribute[id,name,code],"
    "programStage[id,name],programStageSection[id,name]"
)
_RULE_FIELDS: str = (
    "id,name,description,priority,condition,"
    "program[id,name],programStage[id,name],"
    f"programRuleActions[{_ACTION_FIELDS}]"
)


class ProgramRulesAccessor:
    """`Dhis2Client.program_rules` — author + debug helpers over DHIS2 program rules."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client — reuses its auth + HTTP pool for every request."""
        self._client = client

    async def list_all(self, program_uid: str | None = None) -> list[ProgramRule]:
        """List every ProgramRule (optionally scoped to one program) ordered by priority.

        Fields selector pulls actions inline so callers get the full shape in
        one round-trip — tracker integrations typically want every rule's
        triggering conditions + effects at once. Paging off for small sets
        (DHIS2 rule catalogues rarely exceed a few hundred entries per
        program).
        """
        filters: list[str] | None = None
        if program_uid is not None:
            filters = [f"program.id:eq:{program_uid}"]
        return cast(
            list[ProgramRule],
            await self._client.resources.program_rules.list(
                fields=_RULE_FIELDS,
                filters=filters,
                order=["priority:asc"],
                paging=False,
            ),
        )

    async def get_rule(self, rule_uid: str) -> ProgramRule:
        """Fetch one ProgramRule with actions resolved inline."""
        raw = await self._client.get_raw(
            f"/api/programRules/{rule_uid}",
            params={"fields": _RULE_FIELDS},
        )
        return ProgramRule.model_validate(raw)

    async def variables_for(self, program_uid: str) -> list[ProgramRuleVariable]:
        """Every `ProgramRuleVariable` in scope for a program, sorted by name.

        Expression authors typically need this first when debugging a rule —
        "what values can my condition reference?" The typed model populates
        `programRuleVariableSourceType` explicitly, because `fields=*`
        omits it.
        """
        raw = await self._client.get_raw(
            "/api/programRuleVariables",
            params={
                "filter": f"program.id:eq:{program_uid}",
                "fields": _VARIABLE_FIELDS,
                "order": "name:asc",
                "paging": "false",
            },
        )
        return parse_collection(raw, "programRuleVariables", ProgramRuleVariable)

    async def actions_for(self, rule_uid: str) -> list[ProgramRuleAction]:
        """Every `ProgramRuleAction` attached to one rule.

        Fetches the rule with `programRuleActions[...]` inline and returns
        that collection. A direct filter on `/api/programRuleActions` would
        be cleaner but DHIS2 strips the `programRule` back-reference from
        action responses (same one-way-ownership pattern documented
        in BUGS.md #22c), so the rule-forward path is the only
        reliable route.
        """
        rule = await self.get_rule(rule_uid)
        actions = rule.programRuleActions or []
        validated: list[ProgramRuleAction] = []
        for entry in actions:
            if isinstance(entry, ProgramRuleAction):
                validated.append(entry)
            elif isinstance(entry, dict):
                validated.append(ProgramRuleAction.model_validate(entry))
        return validated

    async def validate_expression(
        self,
        expression: str,
        *,
        context: ExpressionContext = "program-indicator",
    ) -> ExpressionDescription:
        """Parse-check a program-rule condition via `/api/.../expression/description`.

        DHIS2 exposes one validator per expression family (validation-rule /
        indicator / predictor / program-indicator). Program-rule conditions
        use the `program-indicator` grammar — same `#{UID}` / `A{TEA}` /
        `V{current_date}` / `d2:fn(...)` shape. Delegates to
        `client.validation.describe_expression` so every context routes
        through the same plumbing.
        """
        return await self._client.validation.describe_expression(expression, context=context)

    async def where_de_is_used(self, data_element_uid: str) -> list[ProgramRule]:
        """Find every ProgramRule whose actions reference a specific DataElement.

        Useful for impact analysis before editing a DE — "what rules break
        if I rename / remove this?" DHIS2 strips the `programRule`
        back-reference from `/api/programRuleActions` responses (one-way
        ownership), so a direct filter like `dataElement.id:eq:X` can't
        map back to owning rules. This walks every rule with actions inline
        and filters client-side.
        """
        every_rule = await self.list_all()
        matches: list[ProgramRule] = []
        for rule in every_rule:
            for action in rule.programRuleActions or []:
                target_de = _extract_target_de_uid(action)
                if target_de == data_element_uid:
                    matches.append(rule)
                    break
        return matches


def _extract_target_de_uid(action: Any) -> str | None:
    """Pull `dataElement.id` off a ProgramRuleAction (dict or typed model)."""
    if isinstance(action, dict):
        de = action.get("dataElement")
        if isinstance(de, dict):
            uid = de.get("id")
            return uid if isinstance(uid, str) else None
        return None
    de = getattr(action, "dataElement", None)
    if de is None:
        return None
    uid = getattr(de, "id", None)
    return uid if isinstance(uid, str) else None


__all__ = ["ProgramRulesAccessor"]

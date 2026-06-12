"""ValidationRule authoring — `Dhis2Client.validation_rules`.

`ValidationRule`s compare two DHIS2 expressions (`leftSide` vs
`rightSide`) against a configurable operator and fire violations when
the comparison fails for a given period + organisation unit. They
drive `d2w maintenance validation run`; DHIS2 ships dozens of
built-in rules for aggregate data-quality checks.

This module adds the authoring primitives — run lives on
`Dhis2Client.validation.run_analysis(...)`:

- `create(...)` — named kwargs over the minimal required subset
  (`name`, `short_name`, `left_expression`, `operator`,
  `right_expression`) plus common knobs (`period_type`,
  `importance`, `missing_value_strategy`, `description`).
- `update(rule)` / `rename(uid, ...)` — standard edit pathways.
- `delete(uid)` — drops the rule and any outstanding results.

`leftSide` / `rightSide` are `Expression` sub-objects on the wire;
we build them from the string + strategy here so callers don't have
to assemble the payload manually.

No `*Spec` builder — continues the spec-audit data point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dhis2w_client.generated.v42.enums import Importance, MissingValueStrategy, Operator
from dhis2w_client.generated.v42.schemas import ValidationRule
from dhis2w_client.v42.envelopes import WebMessageResponse
from dhis2w_client.v42.periods import PeriodType

if TYPE_CHECKING:
    from dhis2w_client.v42.client import Dhis2Client


_VR_FIELDS: str = (
    "id,name,shortName,code,description,"
    "periodType,importance,operator,"
    "leftSide[expression,description,missingValueStrategy,slidingWindow],"
    "rightSide[expression,description,missingValueStrategy,slidingWindow],"
    "validationRuleGroups[id,name]"
)


class ValidationRulesAccessor:
    """`Dhis2Client.validation_rules` — CRUD helpers over `/api/validationRules`."""

    def __init__(self, client: Dhis2Client) -> None:
        """Bind to the sharing client."""
        self._client = client

    async def list_all(
        self,
        *,
        period_type: PeriodType | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ValidationRule]:
        """Page through ValidationRules, optionally filtered by periodType."""
        filters: list[str] | None = None
        if period_type is not None:
            value = period_type.value if isinstance(period_type, PeriodType) else period_type
            filters = [f"periodType:eq:{value}"]
        return cast(
            list[ValidationRule],
            await self._client.resources.validation_rules.list(
                fields=_VR_FIELDS,
                filters=filters,
                page=page,
                page_size=page_size,
            ),
        )

    async def get(self, uid: str) -> ValidationRule:
        """Fetch one ValidationRule with both expression sides + group refs inline."""
        return await self._client.get(
            f"/api/validationRules/{uid}", model=ValidationRule, params={"fields": _VR_FIELDS}
        )

    async def create(
        self,
        *,
        name: str,
        short_name: str,
        left_expression: str,
        operator: Operator | str,
        right_expression: str,
        period_type: PeriodType | str = PeriodType.MONTHLY,
        importance: Importance | str = Importance.MEDIUM,
        missing_value_strategy: MissingValueStrategy | str = MissingValueStrategy.SKIP_IF_ALL_VALUES_MISSING,
        left_description: str | None = None,
        right_description: str | None = None,
        description: str | None = None,
        code: str | None = None,
        organisation_unit_levels: list[int] | None = None,
        uid: str | None = None,
    ) -> ValidationRule:
        """Create a ValidationRule.

        `left_expression` / `right_expression` use DHIS2's aggregate
        expression syntax (`#{<DE_UID>.<CC_UID>}` for disaggregated
        DEs, `#{<DE_UID>}` for default-combo DEs). `operator` picks the
        comparison — `EQUAL_TO`, `LESS_THAN_OR_EQUAL_TO`, etc. The
        `missing_value_strategy` default skips rows where every ref is
        null so blank cells don't count as a violation.

        `organisation_unit_levels` scopes the rule to specific depths —
        pass `[4]` to restrict it to facility-level OUs.
        """
        payload: dict[str, Any] = {
            "name": name,
            "shortName": short_name,
            "periodType": period_type.value if isinstance(period_type, PeriodType) else period_type,
            "importance": importance.value if isinstance(importance, Importance) else importance,
            "operator": operator.value if isinstance(operator, Operator) else operator,
            "leftSide": _expression(
                expression=left_expression,
                description=left_description or (description and f"leftSide: {description}") or None,
                strategy=missing_value_strategy,
            ),
            "rightSide": _expression(
                expression=right_expression,
                description=right_description or (description and f"rightSide: {description}") or None,
                strategy=missing_value_strategy,
            ),
        }
        if uid:
            payload["id"] = uid
        if code:
            payload["code"] = code
        if description:
            payload["description"] = description
        if organisation_unit_levels:
            payload["organisationUnitLevels"] = list(organisation_unit_levels)
        envelope = await self._client.post("/api/validationRules", payload, model=WebMessageResponse)
        created_uid = envelope.created_uid or uid
        if not created_uid:
            raise RuntimeError("validation-rule create did not return a uid")
        return await self.get(created_uid)

    async def update(self, rule: ValidationRule) -> ValidationRule:
        """PUT an edited ValidationRule back. `rule.id` must be set."""
        if not rule.id:
            raise ValueError("update requires rule.id to be set")
        body = rule.model_dump(by_alias=True, exclude_none=True, mode="json")
        await self._client.put_raw(f"/api/validationRules/{rule.id}", body=body)
        return await self.get(rule.id)

    async def rename(
        self,
        uid: str,
        *,
        name: str | None = None,
        short_name: str | None = None,
        description: str | None = None,
    ) -> ValidationRule:
        """Partial-update shortcut — read, mutate the label fields, PUT."""
        if name is None and short_name is None and description is None:
            raise ValueError("rename requires at least one of name / short_name / description")
        current = await self.get(uid)
        if name is not None:
            current.name = name
        if short_name is not None:
            current.shortName = short_name
        if description is not None:
            current.description = description
        return await self.update(current)

    async def delete(self, uid: str) -> None:
        """Delete a ValidationRule — DHIS2 removes any outstanding results it had raised."""
        if not uid:
            raise ValueError("delete requires a non-empty uid")
        await self._client.resources.validation_rules.delete(uid)


def _expression(
    *,
    expression: str,
    description: str | None,
    strategy: MissingValueStrategy | str,
) -> dict[str, Any]:
    """Build a DHIS2 `Expression` sub-object as a plain dict (typed `Any` on the schema)."""
    side: dict[str, Any] = {
        "expression": expression,
        "missingValueStrategy": strategy.value if isinstance(strategy, MissingValueStrategy) else strategy,
        "slidingWindow": False,
    }
    if description:
        side["description"] = description
    return side


__all__ = [
    "ValidationRule",
    "ValidationRulesAccessor",
]

"""ProgramRule authoring + debugging helpers — `client.program_rules` end-to-end.

Covers every method on `ProgramRulesAccessor`:

1. `list_all(program_uid)` — rules for a program sorted by priority,
   with actions resolved inline.
2. `get_rule(uid)` — single rule fetch.
3. `variables_for(program_uid)` — variables in scope for expression
   authoring. Surfaces `programRuleVariableSourceType` even though
   DHIS2's `fields=*` drops it.
4. `actions_for(rule_uid)` — per-rule action list. Uses the rule-forward
   reference (action→rule back-ref is server-stripped; BUGS.md #22c).
5. `where_de_is_used(de_uid)` — impact analysis before renaming a DE.
6. `validate_expression(expr, context)` — parse-check via DHIS2's
   shared expression-description endpoint.

Usage:
    uv run python examples/client/program_rules.py
"""

from __future__ import annotations

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

CHILD_PROGRAM = "IpHINAT79UW"


async def main() -> None:
    """Walk every ProgramRulesAccessor method against the seeded Child Programme."""
    async with open_client(profile_from_env()) as client:
        rules = await client.program_rules.list_all(program_uid=CHILD_PROGRAM)
        print(f"[list_all] {len(rules)} rules on {CHILD_PROGRAM}:")
        for rule in rules:
            actions = rule.programRuleActions or []
            print(f"  pri={rule.priority}  {rule.name!r}  actions={len(actions)}")

        if rules:
            uid = rules[0].id or ""
            single = await client.program_rules.get_rule(uid)
            print(f"\n[get_rule] {single.id}  cond={single.condition!r}")

        variables = await client.program_rules.variables_for(CHILD_PROGRAM)
        print(f"\n[variables_for] {len(variables)} variables:")
        for var in variables:
            extras = getattr(var, "model_extra", None) or {}
            src = extras.get("programRuleVariableSourceType", "-")
            target = (
                (var.dataElement.id if var.dataElement else None)
                or (
                    extras.get("trackedEntityAttribute", {}).get("id")
                    if isinstance(extras.get("trackedEntityAttribute"), dict)
                    else None
                )
                or "-"
            )
            print(f"  {var.name}  src={src}  target={target}")

        if rules:
            uid = rules[0].id or ""
            actions = await client.program_rules.actions_for(uid)
            print(f"\n[actions_for {uid}] {len(actions)} actions")

        rules_using_de = await client.program_rules.where_de_is_used("fClA2Erf6IO")
        print(f"\n[where_de_is_used fClA2Erf6IO] {len(rules_using_de)} rules reference it:")
        for rule in rules_using_de:
            print(f"  {rule.id}  pri={rule.priority}  {rule.name!r}")

        # Validation note: `#{variableName}` shorthand trips the stricter
        # program-indicator parser (see CLI help). A simple numeric expression
        # round-trips cleanly through the generic validator.
        result = await client.program_rules.validate_expression("1 + 1 > 0", context="generic")
        print(f"\n[validate_expression generic] valid={result.valid}  status={result.status}")


if __name__ == "__main__":
    run_example(main)

# Program rules

`client.program_rules` — read-side accessor over `/api/programRules` plus its companion endpoints for variable resolution + expression validation. Program rules drive conditional UI behaviour in DHIS2 Tracker Capture (hide / show fields, set values, assign warnings, validate input).

```python
async with Dhis2Client(...) as client:
    rules = await client.program_rules.list_for_program("Lt6P15ps7f6")
    one = await client.program_rules.get(rule_uid)

    # Resolve the variables a program rule expression can reference.
    vars_ = await client.program_rules.list_variables_for_program("Lt6P15ps7f6")

    # Parse-check an expression before saving.
    description = await client.program_rules.validate_expression(
        "#{age} > 1 && #{sex} == 'M'",
    )

    # Reverse-reference: which rules reference a given DataElement?
    using = await client.program_rules.where_data_element_is_used("dataEl0001U")
```

CRUD on the rules themselves stays on the generic metadata surface (`client.resources.program_rules`). This accessor focuses on the read + analysis surface that downstream tooling (rule diffing, dependency analysis, expression validators) needs.

Worked example: [`examples/client/program_rules.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/client/program_rules.py).

::: dhis2w_client.v42.program_rules

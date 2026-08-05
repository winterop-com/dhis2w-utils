# FHIR IG generation (`dhis2w_fhir`)

`dhis2w_fhir` is the package behind [`d2w fhir`](../guides/fhir-ig.md): the `fhir.toml`
document, the emitters that turn DHIS2 metadata into an Implementation Guide - FSH for the
definitional artifacts, R4 JSON for the organisation-unit registry - and the DHIS2 period
grammar they share. It mounts onto the CLI and the MCP server through the
`dhis2.plugins` entry point, and every component symbol re-exports from the top-level
package, so `from dhis2w_fhir import GenerateConfig, parse_period` keeps working however
the components are arranged internally. The R4 resource models are the one exception: they
live in `dhis2w_fhir.r4`, which is FHIR's own vocabulary rather than part of the plugin
surface.

## When to reach for it

- Read or write a project's `fhir.toml` from Python (`load_project`, `load_fhir_config`,
  `find_project_fhir_config`, `write_fhir_config`).
- Parse a DHIS2 ISO period into its type and date range, or walk backwards from a date
  (`parse_period`, `recent_periods`, `PERIOD_TYPE_DEFINITIONS`).
- Build FSH artifacts without the CLI (`build_foundation_artifacts`,
  `build_option_set_artifacts`, `build_questionnaire_artifacts`, `build_page_artifacts`)
  and sync them to disk (`sync_artifacts`).
- Build or read the registry's R4 documents (`dhis2w_fhir.r4.Organization`,
  `dhis2w_fhir.r4.Location`) and sync them to disk (`sync_json_artifacts`).

## Worked example — parse a period, then walk backwards

```python
import datetime

from dhis2w_fhir import parse_period, recent_periods

parse_period("2024BiW2")
# PeriodValue(iso='2024BiW2', period_type='BiWeekly',
#             start_date=date(2024, 1, 15), end_date=date(2024, 1, 28))

recent_periods("Monthly", 3, datetime.date(2026, 8, 2))
# ['202607', '202606', '202605']
```

## Reference

### Periods

::: dhis2w_fhir.period

### Project configuration

::: dhis2w_fhir.config

### FHIR R4 resource schemas

The models the pre-built registry JSON is serialised from. Every one is frozen,
alias-aware, and closed to unknown keys, so
`Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key.

::: dhis2w_fhir.r4.schemas

### Package surface

The names below re-export from `dhis2w_fhir` itself; the guide's
[generate targets](../guides/fhir-ig.md#generate-targets) section covers what each emitter
produces.

::: dhis2w_fhir
    options:
      members: false

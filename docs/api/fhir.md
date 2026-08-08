# FHIR IG generation (`dhis2w_fhir`)

`dhis2w_fhir` is the package behind [`d2w fhir`](../guides/fhir-ig.md): the `fhir.toml`
document, the emitters that turn DHIS2 metadata into an Implementation Guide - FSH for the
definitional artifacts, pre-built R4 JSON for the organisation-unit registry, the
option-set terminology, and the category terminology - and the DHIS2 period grammar they
share. It mounts onto the CLI
and the MCP server through the `dhis2.plugins` entry point, and every component symbol
re-exports from the top-level package, so
`from dhis2w_fhir import GenerateConfig, parse_period` keeps working however
the components are arranged internally. The R4 resource models are the one exception: they
live in `dhis2w_fhir.r4`, which is FHIR's own vocabulary rather than part of the plugin
surface.

## When to reach for it

- Read or write a project's `fhir.toml` from Python (`load_project`, `load_fhir_config`,
  `find_project_fhir_config`, `write_fhir_config`).
- Parse a DHIS2 ISO period into its type and date range, or walk backwards from a date
  (`parse_period`, `recent_periods`, `PERIOD_TYPE_DEFINITIONS`).
- Carry DHIS2 attribute values onto a generated resource (`AttributeValueIn`,
  `AttributeCodeIndex`, `resolve_attribute_code_index`, `attribute_value_extensions`).
- Build FSH artifacts without the CLI (`build_foundation_artifacts`,
  `build_questionnaire_artifacts`, `build_page_artifacts`) and sync them to disk
  (`sync_artifacts`).
- Build the pre-built R4 documents - the registry (`dhis2w_fhir.r4.Organization`,
  `dhis2w_fhir.r4.Location`), the option-set terminology
  (`build_option_set_artifacts`), and the category terminology
  (`build_category_artifacts`), the last two on `dhis2w_fhir.r4.CodeSystem` and
  `dhis2w_fhir.r4.ValueSet` - and sync them to disk (`sync_json_artifacts`), one
  owned directory per source.
- Map an option set's generated concept codes back to the DHIS2 option UID and
  option code (`build_option_set_concept_maps` for the `dhis2w_fhir.r4.ConceptMap`
  models, `build_option_set_concept_map_artifacts` for the JSON files that land in
  `CONCEPT_MAP_DIRECTORY`).

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

### DHIS2 attribute values

The projection every generated resource carries its DHIS2 attribute values on, plus
the `uid -> code` index a generate run resolves once against `/api/attributes` and
every emitter joins against. DHIS2 sends an attribute value as an attribute UID and a
string, so the code is a lookup rather than part of the value.

::: dhis2w_fhir.attributes

### Generate notes

What a generate target has to say about a run, as a model rather than a sentence. A
`GenerateNote` carries the kind of decision it records (`GenerateNoteCategory`) beside
the human text, and `echoes_validate` says whether the kind only restates a finding
[`d2w fhir validate`](../guides/fhir-ig.md#validation) reports on the instance - which is
what lets a bare run count those apart from what generation itself found.

::: dhis2w_fhir.notes

### FHIR R4 resource schemas

The models every pre-built JSON document is serialised from - `Organization` and
`Location` for the registry, `CodeSystem` and `ValueSet` for the option-set and
category terminology, `ConceptMap` for both families' mappings back to DHIS2.
Every one is frozen, alias-aware, and closed to unknown keys, so
`Model.model_validate(payload).model_dump_json(exclude_none=True, by_alias=True)`
reproduces the input document key for key.

::: dhis2w_fhir.r4.schemas

### Conversion: QuestionnaireResponse to DHIS2

The inverse of the emitters, and the reference implementation
[`docs/project/fhir-conversion.md`](../project/fhir-conversion.md) holds the later published
StructureMaps against. A caller assembles a `ConversionContext` once from the compiled IG
artifacts - the served Questionnaires, the option-set CodeSystems and their ConceptMaps, the
ValueSets binding the two, and the published Locations - and then translates each captured
response into the DHIS2 import payload its form kind reports: a `DataValueSet` for a data set,
a `TrackerEvent` for an event program or a tracker program stage. A response the translator
cannot read whole answers with typed refusals naming the link id and the reason, never with a
partial payload.

`conversion.artifacts` is where a project's own files become those models: it reads the
compiled `ig/fsh-generated/resources` merged with the predefined `ig/input/resources` tree -
the same two trees `d2w fhir serve` serves - and `build_project_context` assembles the context
from them plus the project's `[generate]` naming, identifier base, and timezone.

::: dhis2w_fhir.conversion.schemas

::: dhis2w_fhir.conversion.context

::: dhis2w_fhir.conversion.artifacts

::: dhis2w_fhir.conversion.values

::: dhis2w_fhir.conversion.payloads

::: dhis2w_fhir.conversion.translator

### The capture spool

Where `d2w fhir serve` writes a receipt and where `d2w fhir forward` moves it next. The
layout is duplicated rather than imported - `dhis2w-fhir` is a dependency of
`dhis2w-fhir-serve`, so the arrow only points one way and the forwarder reads the files
directly under the same conventions.

::: dhis2w_fhir.spool

### Package surface

The names below re-export from `dhis2w_fhir` itself; the guide's
[generate targets](../guides/fhir-ig.md#generate-targets) section covers what each emitter
produces.

::: dhis2w_fhir
    options:
      members: false

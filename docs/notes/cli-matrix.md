# CLI command x model matrix

`HIT` = model formed the right command path; `RUN` = read executed (exit 0); `miss` = neither.

> **Read `miss` with care.** Each task is auto-derived from a command's one-line help, then the
> model must pick that exact command among ~200 metadata siblings. A `miss` is usually that
> ambiguity — the model ran a plausible neighbour — not an inability to use the command. The
> structural proof that every command works is the deterministic `--help` guard
> (`test_every_command_renders_help`); this grid measures *discoverability under a vague goal*.

## metadata
| command | gemma-4-12b-qat |
| --- | --- |
| `metadata attribute delete` | miss |
| `metadata attribute find` | miss |
| `metadata attribute get` | miss |
| `metadata attribute set` | miss |
| `metadata category-option-groups get` | miss |
| `metadata category-options create` | HIT |
| `metadata category-options delete` | HIT |
| `metadata category-options get` | miss |
| `metadata category-options rename` | miss |
| `metadata category-options set-validity` | miss |
| `metadata dashboard add-item` | miss |
| `metadata dashboard get` | miss |
| `metadata dashboard remove-item` | miss |
| `metadata data-element-group-sets add-groups` | miss |
| `metadata data-element-group-sets create` | HIT |
| `metadata data-element-group-sets delete` | miss |
| `metadata data-element-group-sets get` | miss |
| `metadata data-element-group-sets remove-groups` | miss |
| `metadata data-element-groups add-members` | miss |
| `metadata data-element-groups create` | HIT |
| `metadata data-element-groups delete` | HIT |
| `metadata data-element-groups get` | miss |
| `metadata data-element-groups members` | miss |
| `metadata data-element-groups remove-members` | miss |
| `metadata data-elements create` | HIT |
| `metadata data-elements delete` | miss |
| `metadata data-elements get` | miss |
| `metadata data-elements rename` | miss |
| `metadata data-elements set-legend-sets` | miss |
| `metadata diff` | miss |
| `metadata diff-profiles` | miss |
| `metadata export` | HIT |
| `metadata get` | HIT |
| `metadata import` | miss |
| `metadata indicator-group-sets add-groups` | miss |
| `metadata indicator-group-sets create` | HIT |
| `metadata indicator-group-sets delete` | miss |
| `metadata indicator-group-sets get` | miss |
| `metadata indicator-group-sets remove-groups` | miss |
| `metadata indicator-groups add-members` | miss |
| `metadata indicator-groups create` | miss |
| `metadata indicator-groups delete` | miss |
| `metadata indicator-groups get` | miss |
| `metadata indicator-groups members` | miss |
| `metadata indicator-groups remove-members` | miss |
| `metadata indicators create` | miss |
| `metadata indicators delete` | miss |
| `metadata indicators get` | miss |
| `metadata indicators rename` | miss |
| `metadata indicators set-legend-sets` | miss |
| `metadata indicators validate-expression` | miss |
| `metadata list` | RUN |
| `metadata ls` | miss |
| `metadata map clone` | miss |
| `metadata map create` | miss |
| `metadata map delete` | miss |
| `metadata map get` | miss |
| `metadata merge` | miss |
| `metadata merge-bundle` | miss |
| `metadata options attribute find` | miss |
| `metadata options attribute get` | miss |
| `metadata options attribute set` | miss |
| `metadata options create` | miss |
| `metadata options delete` | miss |
| `metadata options find` | miss |
| `metadata options get` | miss |
| `metadata options sync` | miss |
| `metadata patch` | miss |
| `metadata program-indicator-groups add-members` | miss |
| `metadata program-indicator-groups create` | miss |
| `metadata program-indicator-groups delete` | miss |
| `metadata program-indicator-groups get` | miss |
| `metadata program-indicator-groups members` | miss |
| `metadata program-indicator-groups remove-members` | miss |
| `metadata program-indicators create` | miss |
| `metadata program-indicators delete` | miss |
| `metadata program-indicators get` | miss |
| `metadata program-indicators rename` | miss |
| `metadata program-indicators set-legend-sets` | miss |
| `metadata program-indicators validate-expression` | miss |
| `metadata program-rule get` | miss |
| `metadata program-rule validate-expression` | miss |
| `metadata program-rule vars-for` | miss |
| `metadata program-rule where-de-is-used` | miss |
| `metadata rename` | miss |
| `metadata retag` | miss |
| `metadata search` | miss |
| `metadata share` | miss |
| `metadata sql-view adhoc` | miss |
| `metadata sql-view execute` | miss |
| `metadata sql-view get` | miss |
| `metadata sql-view refresh` | miss |
| `metadata type list` | RUN |
| `metadata type ls` | miss |
| `metadata usage` | miss |
| `metadata viz clone` | miss |
| `metadata viz create` | miss |
| `metadata viz delete` | miss |
| `metadata viz get` | miss |

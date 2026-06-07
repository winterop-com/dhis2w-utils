# CLI command x model matrix

`HIT` = model formed the right command path; `RUN` = read executed (exit 0); `miss` = neither.

> **Read `miss` with care.** Each task is auto-derived from a command's one-line help, then the
> model must pick that exact command among ~200 metadata siblings. A `miss` is usually that
> ambiguity — the model ran a plausible neighbour — not an inability to use the command. The
> structural proof that every command works is the deterministic `--help` guard
> (`test_every_command_renders_help`); this grid measures *discoverability under a vague goal*.

## metadata
| command | gemma-4-12b-qat | gemma-4-12b | gemma-4-26b-a4b-qat | gemma-4-e4b | qwen2.5-7b-instruct | qwen3.5-4b |
| --- | --- | --- | --- | --- | --- | --- |
| `metadata attribute delete` | miss | miss | miss | miss | miss | miss |
| `metadata attribute find` | miss | miss | miss | miss | miss | miss |
| `metadata attribute get` | miss | miss | miss | miss | miss | miss |
| `metadata attribute set` | miss | miss | miss | miss | miss | miss |
| `metadata categories add-option` | miss | miss | miss | miss | miss | miss |
| `metadata categories create` | miss | miss | miss | miss | miss | miss |
| `metadata categories delete` | miss | miss | miss | miss | miss | miss |
| `metadata categories get` | miss | miss | miss | miss | miss | miss |
| `metadata categories remove-option` | miss | miss | miss | miss | miss | miss |
| `metadata categories rename` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos add-category` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos build` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos create` | HIT | miss | miss | miss | miss | miss |
| `metadata category-combos delete` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos get` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos remove-category` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos rename` | miss | miss | miss | miss | miss | miss |
| `metadata category-combos wait-for-cocs` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-combos get` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-combos list-for-combo` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-group-sets add-groups` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-group-sets create` | HIT | HIT | miss | miss | miss | miss |
| `metadata category-option-group-sets delete` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-group-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-group-sets remove-groups` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-groups create` | HIT | HIT | miss | miss | miss | HIT |
| `metadata category-option-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata category-option-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata category-options create` | HIT | HIT | miss | miss | miss | miss |
| `metadata category-options delete` | HIT | miss | miss | miss | miss | miss |
| `metadata category-options get` | miss | miss | miss | miss | miss | miss |
| `metadata category-options rename` | miss | miss | miss | miss | miss | miss |
| `metadata category-options set-validity` | miss | miss | miss | miss | miss | miss |
| `metadata dashboard add-item` | miss | miss | miss | miss | miss | miss |
| `metadata dashboard get` | miss | miss | miss | miss | miss | miss |
| `metadata dashboard remove-item` | miss | HIT | miss | miss | miss | HIT |
| `metadata data-element-group-sets add-groups` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-group-sets create` | HIT | HIT | HIT | miss | miss | HIT |
| `metadata data-element-group-sets delete` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-group-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-group-sets remove-groups` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-groups create` | HIT | HIT | HIT | HIT | miss | HIT |
| `metadata data-element-groups delete` | HIT | miss | miss | miss | miss | miss |
| `metadata data-element-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata data-element-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata data-elements create` | HIT | HIT | HIT | miss | miss | HIT |
| `metadata data-elements delete` | miss | miss | miss | miss | miss | miss |
| `metadata data-elements get` | miss | miss | miss | miss | miss | miss |
| `metadata data-elements rename` | miss | miss | HIT | miss | miss | miss |
| `metadata data-elements set-legend-sets` | miss | miss | miss | miss | miss | miss |
| `metadata data-sets add-element` | miss | miss | miss | miss | miss | miss |
| `metadata data-sets create` | miss | miss | miss | miss | miss | miss |
| `metadata data-sets delete` | miss | HIT | miss | miss | miss | miss |
| `metadata data-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata data-sets remove-element` | miss | miss | miss | miss | miss | miss |
| `metadata data-sets rename` | miss | miss | miss | miss | miss | miss |
| `metadata diff` | miss | miss | miss | miss | miss | miss |
| `metadata diff-profiles` | miss | miss | miss | miss | miss | miss |
| `metadata export` | HIT | RUN | RUN | HIT | RUN | HIT |
| `metadata get` | HIT | HIT | RUN | HIT | HIT | miss |
| `metadata import` | miss | miss | HIT | miss | HIT | miss |
| `metadata indicator-group-sets add-groups` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-group-sets create` | HIT | HIT | miss | miss | miss | HIT |
| `metadata indicator-group-sets delete` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-group-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-group-sets remove-groups` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-groups create` | miss | HIT | miss | miss | miss | HIT |
| `metadata indicator-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata indicator-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata indicators create` | miss | miss | miss | miss | miss | miss |
| `metadata indicators delete` | miss | miss | miss | miss | miss | miss |
| `metadata indicators get` | miss | miss | miss | miss | miss | miss |
| `metadata indicators rename` | miss | miss | miss | miss | miss | miss |
| `metadata indicators set-legend-sets` | miss | miss | miss | miss | miss | miss |
| `metadata indicators validate-expression` | miss | HIT | miss | miss | miss | miss |
| `metadata legend-sets clone` | miss | miss | miss | miss | miss | miss |
| `metadata legend-sets create` | HIT | HIT | miss | miss | miss | miss |
| `metadata legend-sets delete` | miss | miss | miss | miss | miss | miss |
| `metadata legend-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata list` | RUN | RUN | RUN | RUN | RUN | RUN |
| `metadata ls` | miss | miss | miss | miss | miss | miss |
| `metadata map clone` | miss | miss | miss | miss | miss | miss |
| `metadata map create` | miss | miss | miss | miss | miss | miss |
| `metadata map delete` | miss | miss | miss | miss | miss | miss |
| `metadata map get` | miss | miss | miss | miss | miss | miss |
| `metadata merge` | miss | miss | miss | miss | miss | miss |
| `metadata merge-bundle` | miss | miss | miss | miss | miss | miss |
| `metadata options attribute find` | miss | miss | miss | miss | miss | miss |
| `metadata options attribute get` | miss | miss | miss | miss | miss | miss |
| `metadata options attribute set` | miss | miss | miss | miss | miss | miss |
| `metadata options create` | miss | HIT | miss | miss | miss | miss |
| `metadata options delete` | miss | miss | miss | miss | miss | miss |
| `metadata options find` | miss | miss | miss | miss | miss | miss |
| `metadata options get` | miss | miss | miss | miss | miss | miss |
| `metadata options sync` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-group-sets add-groups` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-group-sets create` | HIT | HIT | miss | miss | miss | HIT |
| `metadata organisation-unit-group-sets delete` | miss | miss | miss | miss | miss | HIT |
| `metadata organisation-unit-group-sets get` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-group-sets remove-groups` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-groups create` | HIT | HIT | miss | miss | miss | HIT |
| `metadata organisation-unit-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-levels get` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-unit-levels rename` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-units create` | HIT | miss | miss | miss | miss | miss |
| `metadata organisation-units delete` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-units get` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-units move` | miss | miss | miss | miss | miss | miss |
| `metadata organisation-units tree` | miss | miss | miss | miss | miss | miss |
| `metadata patch` | miss | miss | miss | miss | HIT | miss |
| `metadata predictor-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata predictor-groups create` | HIT | HIT | miss | miss | miss | HIT |
| `metadata predictor-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata predictor-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata predictor-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata predictor-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata predictors create` | miss | miss | miss | miss | miss | miss |
| `metadata predictors delete` | miss | miss | miss | miss | miss | miss |
| `metadata predictors get` | miss | miss | miss | miss | miss | miss |
| `metadata predictors rename` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicator-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicator-groups create` | miss | HIT | miss | miss | miss | miss |
| `metadata program-indicator-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicator-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicator-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicator-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators create` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators delete` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators get` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators rename` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators set-legend-sets` | miss | miss | miss | miss | miss | miss |
| `metadata program-indicators validate-expression` | miss | miss | miss | miss | miss | miss |
| `metadata program-rule get` | miss | miss | miss | miss | miss | miss |
| `metadata program-rule validate-expression` | miss | miss | miss | miss | miss | miss |
| `metadata program-rule vars-for` | miss | miss | miss | miss | miss | miss |
| `metadata program-rule where-de-is-used` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages add-element` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages create` | miss | HIT | miss | miss | miss | miss |
| `metadata program-stages delete` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages get` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages remove-element` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages rename` | miss | miss | miss | miss | miss | miss |
| `metadata program-stages reorder` | miss | miss | miss | miss | miss | miss |
| `metadata programs add-attribute` | miss | HIT | miss | miss | miss | miss |
| `metadata programs add-to-ou` | miss | miss | miss | miss | miss | miss |
| `metadata programs create` | miss | miss | miss | miss | miss | miss |
| `metadata programs delete` | miss | HIT | miss | miss | miss | miss |
| `metadata programs get` | miss | miss | miss | miss | miss | miss |
| `metadata programs remove-attribute` | miss | miss | miss | miss | miss | miss |
| `metadata programs remove-from-ou` | miss | miss | miss | miss | miss | miss |
| `metadata programs rename` | miss | miss | miss | miss | miss | miss |
| `metadata rename` | miss | miss | miss | miss | miss | miss |
| `metadata retag` | miss | miss | miss | miss | miss | miss |
| `metadata search` | miss | RUN | RUN | miss | RUN | miss |
| `metadata sections add-element` | miss | miss | miss | miss | miss | miss |
| `metadata sections create` | miss | miss | miss | miss | miss | miss |
| `metadata sections delete` | miss | miss | miss | miss | miss | miss |
| `metadata sections get` | miss | miss | miss | miss | miss | miss |
| `metadata sections remove-element` | miss | miss | miss | miss | miss | miss |
| `metadata sections rename` | miss | miss | miss | miss | miss | miss |
| `metadata sections reorder` | miss | miss | miss | miss | miss | miss |
| `metadata share` | miss | miss | miss | miss | HIT | miss |
| `metadata sql-view adhoc` | miss | miss | miss | miss | miss | miss |
| `metadata sql-view execute` | miss | miss | miss | miss | miss | miss |
| `metadata sql-view get` | miss | miss | miss | miss | miss | miss |
| `metadata sql-view refresh` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-attributes create` | HIT | miss | miss | HIT | HIT | HIT |
| `metadata tracked-entity-attributes delete` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-attributes get` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-attributes rename` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types add-attribute` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types create` | HIT | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types delete` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types get` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types remove-attribute` | miss | miss | miss | miss | miss | miss |
| `metadata tracked-entity-types rename` | miss | miss | miss | miss | miss | miss |
| `metadata type list` | RUN | RUN | RUN | RUN | RUN | RUN |
| `metadata type ls` | miss | miss | miss | miss | miss | miss |
| `metadata usage` | miss | miss | miss | miss | HIT | RUN |
| `metadata validation-rule-groups add-members` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rule-groups create` | miss | HIT | miss | miss | miss | HIT |
| `metadata validation-rule-groups delete` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rule-groups get` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rule-groups members` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rule-groups remove-members` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rules create` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rules delete` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rules get` | miss | miss | miss | miss | miss | miss |
| `metadata validation-rules rename` | miss | miss | miss | miss | miss | miss |
| `metadata viz clone` | miss | miss | miss | miss | miss | miss |
| `metadata viz create` | miss | miss | miss | miss | miss | miss |
| `metadata viz delete` | miss | miss | miss | miss | miss | miss |
| `metadata viz get` | miss | miss | miss | miss | miss | miss |

# CLI command x model matrix

`HIT` = model formed the right command path; `RUN` = read executed (exit 0); `miss` = neither.

> **Read `miss` with care.** Each task is auto-derived from a command's one-line help, then the
> model must pick that exact command among ~200 metadata siblings. A `miss` is usually that
> ambiguity — the model ran a plausible neighbour — not an inability to use the command. The
> structural proof that every command works is the deterministic `--help` guard
> (`test_every_command_renders_help`); this grid measures *discoverability under a vague goal*.

## metadata
| command | gemma-4-12b | gemma-4-12b-qat |
| --- | --- | --- |
| `metadata attribute delete` | miss | miss |
| `metadata attribute find` | miss | miss |
| `metadata attribute get` | miss | miss |
| `metadata attribute set` | miss | miss |
| `metadata categories add-option` | miss | miss |
| `metadata categories create` | miss | miss |
| `metadata categories delete` | miss | miss |
| `metadata categories get` | miss | miss |
| `metadata categories remove-option` | miss | miss |
| `metadata categories rename` | miss | miss |
| `metadata category-combos add-category` | miss | miss |
| `metadata category-combos build` | miss | miss |
| `metadata category-combos create` | miss | HIT |
| `metadata category-combos delete` | miss | miss |
| `metadata category-combos get` | miss | miss |
| `metadata category-combos remove-category` | miss | miss |
| `metadata category-combos rename` | miss | miss |
| `metadata category-combos wait-for-cocs` | miss | miss |
| `metadata category-option-combos get` | miss | miss |
| `metadata category-option-combos list-for-combo` | miss | miss |
| `metadata category-option-group-sets add-groups` | miss | miss |
| `metadata category-option-group-sets create` | HIT | HIT |
| `metadata category-option-group-sets delete` | miss | miss |
| `metadata category-option-group-sets get` | miss | miss |
| `metadata category-option-group-sets remove-groups` | miss | miss |
| `metadata category-option-groups add-members` | miss | miss |
| `metadata category-option-groups create` | HIT | HIT |
| `metadata category-option-groups delete` | miss | miss |
| `metadata category-option-groups get` | miss | miss |
| `metadata category-option-groups members` | miss | miss |
| `metadata category-option-groups remove-members` | miss | miss |
| `metadata category-options create` | HIT | HIT |
| `metadata category-options delete` | miss | HIT |
| `metadata category-options get` | miss | miss |
| `metadata category-options rename` | miss | miss |
| `metadata category-options set-validity` | miss | miss |
| `metadata dashboard add-item` | miss | miss |
| `metadata dashboard get` | miss | miss |
| `metadata dashboard remove-item` | HIT | miss |
| `metadata data-element-group-sets add-groups` | miss | miss |
| `metadata data-element-group-sets create` | HIT | HIT |
| `metadata data-element-group-sets delete` | miss | miss |
| `metadata data-element-group-sets get` | miss | miss |
| `metadata data-element-group-sets remove-groups` | miss | miss |
| `metadata data-element-groups add-members` | miss | miss |
| `metadata data-element-groups create` | HIT | HIT |
| `metadata data-element-groups delete` | miss | HIT |
| `metadata data-element-groups get` | miss | miss |
| `metadata data-element-groups members` | miss | miss |
| `metadata data-element-groups remove-members` | miss | miss |
| `metadata data-elements create` | HIT | HIT |
| `metadata data-elements delete` | miss | miss |
| `metadata data-elements get` | miss | miss |
| `metadata data-elements rename` | miss | miss |
| `metadata data-elements set-legend-sets` | miss | miss |
| `metadata data-sets add-element` | miss | miss |
| `metadata data-sets create` | miss | miss |
| `metadata data-sets delete` | HIT | miss |
| `metadata data-sets get` | miss | miss |
| `metadata data-sets remove-element` | miss | miss |
| `metadata data-sets rename` | miss | miss |
| `metadata diff` | miss | miss |
| `metadata diff-profiles` | miss | miss |
| `metadata export` | RUN | HIT |
| `metadata get` | HIT | HIT |
| `metadata import` | miss | miss |
| `metadata indicator-group-sets add-groups` | miss | miss |
| `metadata indicator-group-sets create` | HIT | HIT |
| `metadata indicator-group-sets delete` | miss | miss |
| `metadata indicator-group-sets get` | miss | miss |
| `metadata indicator-group-sets remove-groups` | miss | miss |
| `metadata indicator-groups add-members` | miss | miss |
| `metadata indicator-groups create` | HIT | miss |
| `metadata indicator-groups delete` | miss | miss |
| `metadata indicator-groups get` | miss | miss |
| `metadata indicator-groups members` | miss | miss |
| `metadata indicator-groups remove-members` | miss | miss |
| `metadata indicators create` | miss | miss |
| `metadata indicators delete` | miss | miss |
| `metadata indicators get` | miss | miss |
| `metadata indicators rename` | miss | miss |
| `metadata indicators set-legend-sets` | miss | miss |
| `metadata indicators validate-expression` | HIT | miss |
| `metadata legend-sets clone` | - | miss |
| `metadata legend-sets create` | - | HIT |
| `metadata legend-sets delete` | - | miss |
| `metadata legend-sets get` | - | miss |
| `metadata list` | RUN | RUN |
| `metadata ls` | miss | miss |
| `metadata map clone` | miss | miss |
| `metadata map create` | miss | miss |
| `metadata map delete` | miss | miss |
| `metadata map get` | miss | miss |
| `metadata merge` | miss | miss |
| `metadata merge-bundle` | miss | miss |
| `metadata options attribute find` | miss | miss |
| `metadata options attribute get` | miss | miss |
| `metadata options attribute set` | miss | miss |
| `metadata options create` | HIT | miss |
| `metadata options delete` | miss | miss |
| `metadata options find` | miss | miss |
| `metadata options get` | miss | miss |
| `metadata options sync` | miss | miss |
| `metadata organisation-unit-group-sets add-groups` | - | miss |
| `metadata organisation-unit-group-sets create` | - | HIT |
| `metadata organisation-unit-group-sets delete` | - | miss |
| `metadata organisation-unit-group-sets get` | - | miss |
| `metadata organisation-unit-group-sets remove-groups` | - | miss |
| `metadata organisation-unit-groups add-members` | - | miss |
| `metadata organisation-unit-groups create` | - | HIT |
| `metadata organisation-unit-groups delete` | - | miss |
| `metadata organisation-unit-groups get` | - | miss |
| `metadata organisation-unit-groups members` | - | miss |
| `metadata organisation-unit-groups remove-members` | - | miss |
| `metadata organisation-unit-levels get` | - | miss |
| `metadata organisation-unit-levels rename` | - | miss |
| `metadata organisation-units create` | - | HIT |
| `metadata organisation-units delete` | - | miss |
| `metadata organisation-units get` | - | miss |
| `metadata organisation-units move` | - | miss |
| `metadata organisation-units tree` | - | miss |
| `metadata patch` | miss | miss |
| `metadata predictor-groups add-members` | miss | miss |
| `metadata predictor-groups create` | HIT | HIT |
| `metadata predictor-groups delete` | miss | miss |
| `metadata predictor-groups get` | miss | miss |
| `metadata predictor-groups members` | miss | miss |
| `metadata predictor-groups remove-members` | miss | miss |
| `metadata predictors create` | miss | miss |
| `metadata predictors delete` | miss | miss |
| `metadata predictors get` | miss | miss |
| `metadata predictors rename` | miss | miss |
| `metadata program-indicator-groups add-members` | miss | miss |
| `metadata program-indicator-groups create` | HIT | miss |
| `metadata program-indicator-groups delete` | miss | miss |
| `metadata program-indicator-groups get` | miss | miss |
| `metadata program-indicator-groups members` | miss | miss |
| `metadata program-indicator-groups remove-members` | miss | miss |
| `metadata program-indicators create` | miss | miss |
| `metadata program-indicators delete` | miss | miss |
| `metadata program-indicators get` | miss | miss |
| `metadata program-indicators rename` | miss | miss |
| `metadata program-indicators set-legend-sets` | miss | miss |
| `metadata program-indicators validate-expression` | miss | miss |
| `metadata program-rule get` | miss | miss |
| `metadata program-rule validate-expression` | miss | miss |
| `metadata program-rule vars-for` | miss | miss |
| `metadata program-rule where-de-is-used` | miss | miss |
| `metadata program-stages add-element` | miss | miss |
| `metadata program-stages create` | HIT | miss |
| `metadata program-stages delete` | - | miss |
| `metadata program-stages get` | miss | miss |
| `metadata program-stages remove-element` | miss | miss |
| `metadata program-stages rename` | miss | miss |
| `metadata program-stages reorder` | miss | miss |
| `metadata programs add-attribute` | HIT | miss |
| `metadata programs add-to-ou` | miss | miss |
| `metadata programs create` | miss | miss |
| `metadata programs delete` | HIT | miss |
| `metadata programs get` | miss | miss |
| `metadata programs remove-attribute` | miss | miss |
| `metadata programs remove-from-ou` | miss | miss |
| `metadata programs rename` | miss | miss |
| `metadata rename` | miss | miss |
| `metadata retag` | miss | miss |
| `metadata search` | RUN | miss |
| `metadata sections add-element` | miss | miss |
| `metadata sections create` | miss | miss |
| `metadata sections delete` | miss | miss |
| `metadata sections get` | miss | miss |
| `metadata sections remove-element` | miss | miss |
| `metadata sections rename` | miss | miss |
| `metadata sections reorder` | miss | miss |
| `metadata share` | miss | miss |
| `metadata sql-view adhoc` | miss | miss |
| `metadata sql-view execute` | miss | miss |
| `metadata sql-view get` | miss | miss |
| `metadata sql-view refresh` | miss | miss |
| `metadata tracked-entity-attributes create` | miss | HIT |
| `metadata tracked-entity-attributes delete` | miss | miss |
| `metadata tracked-entity-attributes get` | miss | miss |
| `metadata tracked-entity-attributes rename` | miss | miss |
| `metadata tracked-entity-types add-attribute` | miss | miss |
| `metadata tracked-entity-types create` | miss | HIT |
| `metadata tracked-entity-types delete` | miss | miss |
| `metadata tracked-entity-types get` | miss | miss |
| `metadata tracked-entity-types remove-attribute` | miss | miss |
| `metadata tracked-entity-types rename` | miss | miss |
| `metadata type list` | RUN | RUN |
| `metadata type ls` | miss | miss |
| `metadata usage` | miss | miss |
| `metadata validation-rule-groups add-members` | miss | miss |
| `metadata validation-rule-groups create` | HIT | miss |
| `metadata validation-rule-groups delete` | miss | miss |
| `metadata validation-rule-groups get` | miss | miss |
| `metadata validation-rule-groups members` | miss | miss |
| `metadata validation-rule-groups remove-members` | miss | miss |
| `metadata validation-rules create` | miss | miss |
| `metadata validation-rules delete` | miss | miss |
| `metadata validation-rules get` | miss | miss |
| `metadata validation-rules rename` | miss | miss |
| `metadata viz clone` | miss | miss |
| `metadata viz create` | miss | miss |
| `metadata viz delete` | miss | miss |
| `metadata viz get` | miss | miss |

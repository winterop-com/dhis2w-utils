"""Per-version accessor binding for `Dhis2Client`.

`Dhis2Client.__init__` (in `dhis2w_client.v42.client`) wires v42 accessor
instances onto `self.X` as a default. When `connect()` detects the live
server is v41 or v43, it calls `rebind_accessors_for_version()` from
this module to swap each accessor with the matching class from the
`dhis2w_client.v{N}.<module>` tree. The result is that a Dhis2Client
talking to a v43 server uses the v43 hand-written code path, not the
v42 default — even though the class itself is the v42 `Dhis2Client`.
"""

from __future__ import annotations

import importlib
from typing import Any

_ACCESSOR_BINDINGS: list[tuple[str, str, str]] = [
    # (attribute_name, module_name, class_name) — kept in sync with the
    # bindings in v{41,42,43}/client.py:__init__. When a new accessor is
    # added there, add a row here too.
    ("system", "system", "SystemModule"),
    ("customize", "customize", "CustomizeAccessor"),
    ("tasks", "tasks", "TaskModule"),
    ("maintenance", "maintenance", "MaintenanceAccessor"),
    ("messaging", "messaging", "MessagingAccessor"),
    ("metadata", "metadata", "MetadataAccessor"),
    ("maps", "maps", "MapsAccessor"),
    ("files", "files", "FilesAccessor"),
    ("legend_sets", "legend_sets", "LegendSetsAccessor"),
    ("validation", "validation", "ValidationAccessor"),
    ("attribute_values", "attribute_values", "AttributeValuesAccessor"),
    ("option_sets", "option_sets", "OptionSetsAccessor"),
    ("organisation_units", "organisation_units", "OrganisationUnitsAccessor"),
    ("organisation_unit_groups", "organisation_unit_groups", "OrganisationUnitGroupsAccessor"),
    ("organisation_unit_group_sets", "organisation_unit_group_sets", "OrganisationUnitGroupSetsAccessor"),
    ("organisation_unit_levels", "organisation_unit_levels", "OrganisationUnitLevelsAccessor"),
    ("predictors", "predictors", "PredictorsAccessor"),
    ("program_rules", "program_rules", "ProgramRulesAccessor"),
    ("sql_views", "sql_views", "SqlViewsAccessor"),
    ("visualizations", "visualizations", "VisualizationsAccessor"),
    ("dashboards", "dashboards", "DashboardsAccessor"),
    ("data_values", "data_values", "DataValuesAccessor"),
    ("analytics", "analytics_stream", "AnalyticsAccessor"),
    ("tracker", "tracker", "TrackerAccessor"),
    ("apps", "apps", "AppsAccessor"),
    ("routes", "routes", "RoutesAccessor"),
    ("datastore", "datastore", "DatastoreAccessor"),
    ("data_elements", "data_elements", "DataElementsAccessor"),
    ("data_element_groups", "data_element_groups", "DataElementGroupsAccessor"),
    ("data_element_group_sets", "data_element_group_sets", "DataElementGroupSetsAccessor"),
    ("indicators", "indicators", "IndicatorsAccessor"),
    ("indicator_groups", "indicator_groups", "IndicatorGroupsAccessor"),
    ("indicator_group_sets", "indicator_group_sets", "IndicatorGroupSetsAccessor"),
    ("program_indicators", "program_indicators", "ProgramIndicatorsAccessor"),
    ("program_indicator_groups", "program_indicator_groups", "ProgramIndicatorGroupsAccessor"),
    ("category_options", "category_options", "CategoryOptionsAccessor"),
    ("category_option_groups", "category_option_groups", "CategoryOptionGroupsAccessor"),
    ("category_option_group_sets", "category_option_group_sets", "CategoryOptionGroupSetsAccessor"),
    ("categories", "categories", "CategoriesAccessor"),
    ("category_combos", "category_combos", "CategoryCombosAccessor"),
    ("category_option_combos", "category_option_combos", "CategoryOptionCombosAccessor"),
    ("data_sets", "data_sets", "DataSetsAccessor"),
    ("sections", "sections", "SectionsAccessor"),
    ("validation_rules", "validation_rules", "ValidationRulesAccessor"),
    ("validation_rule_groups", "validation_rule_groups", "ValidationRuleGroupsAccessor"),
    ("predictor_groups", "predictor_groups", "PredictorGroupsAccessor"),
    ("tracked_entity_attributes", "tracked_entity_attributes", "TrackedEntityAttributesAccessor"),
    ("tracked_entity_types", "tracked_entity_types", "TrackedEntityTypesAccessor"),
    ("programs", "programs", "ProgramsAccessor"),
    ("program_stages", "program_stages", "ProgramStagesAccessor"),
]


def rebind_accessors_for_version(client: Any, version_key: str) -> None:
    """Swap each accessor on `client` to the matching class from `v{version_key}/`.

    `__init__` binds the v42 defaults; this runs from `connect()` once the
    actual server version is known. v42 servers are a no-op (the defaults
    already match). Unknown version keys fall through silently and keep
    the v42 defaults.

    `client` is typed as `Any` because all three `dhis2w_client.v{N}.client.Dhis2Client`
    classes call this — mypy treats them as unrelated. At runtime the
    function only needs duck-typed attribute access (`setattr`).
    """
    if version_key not in ("v41", "v43"):
        return
    for attr_name, module_name, class_name in _ACCESSOR_BINDINGS:
        module = importlib.import_module(f"dhis2w_client.{version_key}.{module_name}")
        cls = getattr(module, class_name)
        setattr(client, attr_name, cls(client))

"""Sierra Leone immunization seed — reads `infra/fixtures/play/` via typed models.

Every metadata section is rehydrated into its generated pydantic model
(`OrganisationUnit`, `DataElement`, `Visualization`, …) before it leaves
this module, so `make dhis2-build-e2e-dump` exercises the client's
validation layer on ~200 real DHIS2 resources in addition to the API
round-trips the importer runs server-side.

Orchestration:

1. `load_metadata()` — read `metadata.json` + merge `geometry.geojson` +
   read `organisation_units.json`. Produces a `dict[section, list[Any]]`
   keyed by DHIS2 resource name.
2. `import_metadata_bundle(client, bundle)` — POST to `/api/metadata` in
   a single request. DHIS2's importer handles the dependency graph.
3. `import_data_values(client)` — stream the gzipped aggregate data
   values via `client.data_values.stream`.
4. `import_tracker(client)` — POST the tracker payload.
"""

from __future__ import annotations

from .event_program import build_event_program
from .fhir_attributes import seed_fhir_attributes
from .loader import (
    FIXTURE_DIR,
    SIERRA_LEONE_ROOT_UID,
    assign_admin_to_sierra_leone,
    attach_admin_to_datasets_and_programs,
    import_core_metadata,
    import_data_values,
    import_deferred_metadata,
    import_metadata_bundle,
    import_ou_tree,
    import_post_viz_metadata,
    import_tracker,
    load_metadata,
    seed_play,
)
from .maps import build_dashboard_maps
from .visualizations import build_dashboard_visualizations
from .workspace_fixtures import build_workspace_fixtures

__all__ = [
    "FIXTURE_DIR",
    "SIERRA_LEONE_ROOT_UID",
    "assign_admin_to_sierra_leone",
    "attach_admin_to_datasets_and_programs",
    "build_dashboard_maps",
    "build_dashboard_visualizations",
    "build_event_program",
    "build_workspace_fixtures",
    "import_core_metadata",
    "import_data_values",
    "import_deferred_metadata",
    "import_metadata_bundle",
    "import_ou_tree",
    "import_post_viz_metadata",
    "import_tracker",
    "load_metadata",
    "seed_fhir_attributes",
    "seed_play",
]

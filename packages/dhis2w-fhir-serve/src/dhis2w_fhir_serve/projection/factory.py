"""Which backend a register search runs through, chosen once per read from `[serve.search] backend`.

The dispatch is a `match` over the config enum rather than a registry, for the reason
`docs/fhir/design/projection.md` section 7 gives for following `AuthProvider`: a backend that a
deployment has not installed should be a refusal the operator reads at the config key that asked for
it, not an import error from inside a request. One value ships, so today the match has one arm and
`fhir.toml` refuses every other word by name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.config import SearchBackend

from dhis2w_fhir_serve.projection.dhis2_names import Dhis2NameSearchIndex

if TYPE_CHECKING:
    from dhis2w_fhir_serve.passthrough import RegisterReader
    from dhis2w_fhir_serve.projection.base import NameSearchIndex


def build_name_search_index(backend: SearchBackend, *, reader: RegisterReader) -> NameSearchIndex:
    """Build the index one register search runs through, over the DHIS2 connection that search reads."""
    match backend:
        case SearchBackend.DHIS2:
            return Dhis2NameSearchIndex(reader=reader)

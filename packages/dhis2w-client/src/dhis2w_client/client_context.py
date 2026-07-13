"""Top-level `open_client` shim — re-exports the v42 helpers.

`Profile` lives at the top level (`dhis2w_client.profile`) because it is
version-agnostic. The `open_client` and `build_auth_provider` helpers bind
to a specific `Dhis2Client` class, so each lives under `v{41,42,43}/`; this
top-level module mirrors v42 for the PyPI-stable surface.
"""

from __future__ import annotations

from dhis2w_client.v42.client_context import build_auth_provider, open_client

__all__ = ["build_auth_provider", "open_client"]

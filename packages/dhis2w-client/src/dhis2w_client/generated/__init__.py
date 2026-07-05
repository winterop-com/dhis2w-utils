"""Version-scoped generated clients. Populated by `d2w codegen`."""

from __future__ import annotations

import importlib
import re
from enum import StrEnum
from pathlib import Path
from types import ModuleType

_VERSION_KEY_RE = re.compile(r"^v\d+$")


class Dhis2(StrEnum):
    """DHIS2 major version that `dhis2w-client` has a generated client for.

    Members mirror the directory names under `dhis2w_client/generated/`. Use as a
    typed hint when you want to pin the client to a specific version instead of
    letting it auto-detect via `/api/system/info`:

        from dhis2w_client import Dhis2, Dhis2Client
        async with Dhis2Client(url, auth=auth, version=Dhis2.V42) as client:
            ...
    """

    V41 = "v41"
    V42 = "v42"
    V43 = "v43"


def available_versions() -> tuple[str, ...]:
    r"""Return the version keys that have been populated by codegen.

    Walks the `generated/` folder, imports each `v\d+` subpackage, and returns
    only the ones whose `__init__.py` set `GENERATED = True`.
    """
    here = Path(__file__).parent
    ready: list[str] = []
    for child in sorted(here.iterdir()):
        if not child.is_dir() or not _VERSION_KEY_RE.match(child.name):
            continue
        try:
            module = importlib.import_module(f"dhis2w_client.generated.{child.name}")
        except ImportError:
            continue
        if getattr(module, "GENERATED", False):
            ready.append(child.name)
    return tuple(ready)


def load(version_key: str) -> ModuleType:
    """Import a specific generated version module."""
    return importlib.import_module(f"dhis2w_client.generated.{version_key}")

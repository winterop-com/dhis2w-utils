"""Entry-point helper for `examples/client/*.py` — handles NoProfileError cleanly."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from dhis2w_client import NoProfileError, UnknownProfileError

_PROFILE_HINT = (
    "hint: configure a profile first:\n"
    "  d2w profile add local --url http://localhost:8080 --auth basic \\\n"
    "      --username admin --password district --default\n"
    "  d2w profile list\n"
    "Or set DHIS2_URL + DHIS2_PAT (or DHIS2_USERNAME + DHIS2_PASSWORD) directly."
)


def run_example(main: Callable[[], Coroutine[Any, Any, Any]]) -> None:
    """Run `main()` under asyncio; render a friendly hint on NoProfileError.

    Mirrors the hint the CLI prints — keeps examples short (no boilerplate
    try/except in every file) and makes first-time failures self-documenting.
    """
    try:
        asyncio.run(main())
    except (NoProfileError, UnknownProfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(_PROFILE_HINT, file=sys.stderr)
        sys.exit(1)

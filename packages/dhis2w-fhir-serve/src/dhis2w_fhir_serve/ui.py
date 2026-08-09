"""The capture UI: a built React bundle, served same-origin off the facade itself.

THE BUNDLE MOUNTS IN TWO PIECES, AND THE ORDER OF THE TWO IS THE WHOLE DESIGN.

Starlette matches routes in registration order, and the facade's read routes are catch-alls:
`/{resource_type}` claims every one-segment path and `/{resource_type}/{resource_id}` claims every
two-segment one. So a naive single mount at `/` placed last serves the shell and nothing else -
`/assets/index-<hash>.js` is a two-segment path, the read route claims it first, and the browser
gets a FHIR OperationOutcome saying `assets` is not a resource type this server serves. The page
loads white with a 404 in the console and nothing anywhere says why.

Hence:

- `mount_ui_assets` registers `/assets` BEFORE the read catch-alls. It is a fixed path, exactly
  like `/metadata` and `/ConceptMap/$translate`, and belongs with them.
- `mount_ui_shell` registers `/` AFTER everything, because it matches whatever is left.

That is also why the vite build must keep every emitted file under `assets/`: a root-level file
would be a one-segment path and the search catch-all would claim it. There is no `public/`
directory in the frontend for exactly this reason.

A missing bundle is a refusal rather than a blank page. `--ui` on a checkout that has never run
`make build-frontend` has no `index.html` to serve, and mounting an empty directory would answer
404 for the shell and 200 for nothing. So the mount raises while the app is being built, naming
the command that fixes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

#: Where the built bundle lives inside the installed package - the vite `build.outDir`.
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"

#: The file whose presence means a bundle was actually built, rather than the directory existing.
INDEX_FILENAME = "index.html"

#: Where vite emits every hashed asset, and the path they are served from.
ASSETS_DIRECTORY_NAME = "assets"
ASSETS_MOUNT_PATH = f"/{ASSETS_DIRECTORY_NAME}"

#: The mount names, so either route can be found by name in a test or a debug dump.
UI_ASSETS_MOUNT_NAME = "ui-assets"
UI_SHELL_MOUNT_NAME = "ui"


class UiBundleMissingError(LookupError):
    """No built UI to serve, rendered by the CLI error funnel as one line naming the fix."""

    def __init__(self) -> None:
        """Carry the refusal naming the directory that is empty and the command that fills it."""
        super().__init__(
            f"`--ui` needs a built frontend at {STATIC_DIRECTORY}, and there is none. "
            "Build it with `make build-frontend` (an installed wheel ships it already)."
        )


class UiStaticFiles(StaticFiles):
    """Static files with a cache policy stated rather than inferred.

    Vite emits content-hashed asset names, so an asset is immutable: its name changes whenever its
    bytes do. `index.html` names the current hashes and must therefore never be cached - a stale
    shell references filenames a rebuild deleted, and the page renders blank. Starlette sends only
    ETag and Last-Modified, and RFC 9111 lets a browser apply heuristic freshness in the absence of
    Cache-Control, so the policy is written down here instead of left to the client's guess.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Answer one static file, marking the shell revalidate-always and every asset immutable."""
        response = await super().get_response(path, scope)
        media_type: Any = getattr(response, "media_type", None)
        if isinstance(media_type, str) and media_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def ui_bundle_present() -> bool:
    """Whether a built bundle is installed beside this module."""
    return (STATIC_DIRECTORY / INDEX_FILENAME).is_file()


def mount_ui_assets(app: FastAPI) -> None:
    """Mount the hashed asset tree at `/assets`, ahead of the read catch-alls.

    Registered with the fixed-path routers rather than after them: `/assets/<file>` is a
    two-segment path, and `/{resource_type}/{resource_id}` would claim it first.
    """
    _require_bundle()
    app.mount(
        ASSETS_MOUNT_PATH,
        UiStaticFiles(directory=STATIC_DIRECTORY / ASSETS_DIRECTORY_NAME),
        name=UI_ASSETS_MOUNT_NAME,
    )


def mount_ui_shell(app: FastAPI) -> None:
    """Mount the shell at `/`, after every FHIR route, so it claims only what is left.

    `html=True` serves `index.html` for `/`. It is also the 404 fallback under this mount, which
    is harmless here precisely because the UI is hash-routed: the browser never asks the server
    for `/responses`, so the fallback is not being used to fake a client-side route table.
    """
    _require_bundle()
    app.mount("/", UiStaticFiles(directory=STATIC_DIRECTORY, html=True), name=UI_SHELL_MOUNT_NAME)


def _require_bundle() -> None:
    """Refuse to mount anything when no bundle was ever built."""
    if not ui_bundle_present():
        raise UiBundleMissingError

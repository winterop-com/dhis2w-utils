"""The stated import surface, asserted: what the package publishes, what the reference renders, and the UI.

Three things drift apart on their own and are pinned together here. A name in `__all__` that does not
import is a broken promise; a module the API reference renders that the package exports nothing from
sends a reader who followed the docs to an import that does not exist; and a name published for the
React bundle's sake would make the doctrine's one exception - see `docs/fhir/design/library.md` R8 -
a sentence in a design paper rather than something a reviewer can check.

The rule the last of those leaves behind is short enough to read: if a name exists so the capture UI
can work, it is not on the library surface. `UiBundleMissingError` is the exception, and it is
exactly one: `create_app` raises it while building, so a caller of `create_app` catches it by name.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
from types import ModuleType

import dhis2w_fhir_serve
import pytest

PACKAGE_NAME = "dhis2w_fhir_serve"

#: The API reference page for this package, and the directive mkdocstrings renders a module with.
REFERENCE_PAGE = Path(__file__).resolve().parents[3] / "docs" / "fhir" / "api-dhis2w-fhir-serve.md"
RENDER_DIRECTIVE = re.compile(rf"^:::\s+({PACKAGE_NAME}[\w.]*)\s*$", re.MULTILINE)

#: The modules that exist so the built React bundle can work.
UI_MODULES = frozenset({f"{PACKAGE_NAME}.ui", f"{PACKAGE_NAME}.routes.uiconfig"})

#: The one name from those modules the surface keeps, because `create_app` raises it while building.
UI_EXCEPTION = "UiBundleMissingError"

#: Every name the UI modules publish that the surface does not - R8's list, stated so it can be checked.
WITHDRAWN_UI_NAMES = (
    "STATIC_DIRECTORY",
    "UiStaticFiles",
    "mount_ui_assets",
    "mount_ui_shell",
    "ui_bundle_present",
    "UiConfig",
    "BasemapLayer",
    "RegisterUiConfig",
    "RegisteredTypeUiConfig",
    "TrackedEntitiesUiConfig",
    "basemap_layers",
    "public_instance_url",
    "tracked_entities_config",
    "UI_CONFIG_PATH",
    "OPENSTREETMAP_ATTRIBUTION",
)

needs_reference_page = pytest.mark.skipif(
    not REFERENCE_PAGE.exists(), reason="the API reference page is in the checkout, not in the installed package"
)


def _rendered_modules() -> tuple[str, ...]:
    """Every module the API reference page renders, in the order the page renders them."""
    return tuple(RENDER_DIRECTIVE.findall(REFERENCE_PAGE.read_text(encoding="utf-8")))


def _defining_module(name: str) -> str | None:
    """Where one exported name is defined, or None for a value that is not a class or a function."""
    exported = getattr(dhis2w_fhir_serve, name)
    if not (inspect.isclass(exported) or inspect.isroutine(exported)):
        return None
    return getattr(exported, "__module__", None)


def test_every_exported_name_imports() -> None:
    """A name in `__all__` that does not resolve is a promise the package cannot keep."""
    missing = [name for name in dhis2w_fhir_serve.__all__ if not hasattr(dhis2w_fhir_serve, name)]

    assert missing == []


def test_the_surface_names_each_capability_once() -> None:
    """One entry per name: a duplicate is two people publishing the same thing and neither noticing."""
    published = list(dhis2w_fhir_serve.__all__)

    assert sorted(set(published)) == sorted(published)


@needs_reference_page
def test_every_module_the_reference_renders_imports() -> None:
    """A `:::` line naming a module that does not import renders an empty page and says nothing about it."""
    rendered: list[ModuleType] = [importlib.import_module(module) for module in _rendered_modules()]

    assert rendered != []


@needs_reference_page
def test_every_published_name_comes_from_a_module_the_reference_renders() -> None:
    """A published capability the reference says nothing about is one a reader can only find by grepping."""
    rendered = set(_rendered_modules())
    unrendered = {
        name: module
        for name in dhis2w_fhir_serve.__all__
        if name != UI_EXCEPTION
        for module in [_defining_module(name)]
        if module is not None and module not in rendered
    }

    assert unrendered == {}


@needs_reference_page
def test_every_module_stating_its_own_surface_has_it_published() -> None:
    """A module that declares `__all__` has said what it publishes; the package re-exports exactly that."""
    published = set(dhis2w_fhir_serve.__all__)
    withheld = {
        module: [name for name in stated if name not in published]
        for module in _rendered_modules()
        if module != PACKAGE_NAME
        for stated in [getattr(importlib.import_module(module), "__all__", ())]
        if stated
    }

    assert {module: names for module, names in withheld.items() if names} == {}


@needs_reference_page
def test_the_reference_renders_no_module_that_exists_for_the_browser() -> None:
    """The UI is reached by running the server with `settings.ui`, which is the supported door and the only one."""
    assert UI_MODULES & set(_rendered_modules()) == frozenset()


def test_no_name_that_exists_for_the_capture_ui_is_published() -> None:
    """R8's list, checked by name: the mounts, the static files, and the `/uiconfig` document all stay off."""
    published = set(dhis2w_fhir_serve.__all__)

    assert [name for name in WITHDRAWN_UI_NAMES if name in published] == []


def test_the_one_ui_name_the_surface_keeps_is_the_refusal() -> None:
    """`create_app` raises it while building, so an embedder calling `create_app` can catch it by name."""
    from_ui = {name for name in dhis2w_fhir_serve.__all__ if _defining_module(name) in UI_MODULES}

    assert from_ui == {UI_EXCEPTION}


def test_the_projection_seams_are_importable_in_one_import() -> None:
    """What somebody putting another backend behind a register search needs: the Protocols and the factory."""
    from dhis2w_fhir_serve import (
        Dhis2NameSearchIndex,
        NameMatch,
        NameMatches,
        NameQuery,
        NameSearchIndex,
        ProjectionStore,
        build_name_search_index,
    )

    assert isinstance(Dhis2NameSearchIndex, type)
    assert {NameMatch, NameMatches, NameQuery} != set()
    assert {NameSearchIndex, ProjectionStore} != set()
    assert callable(build_name_search_index)


def test_the_composition_contract_is_importable_in_one_import() -> None:
    """What an embedding application needs: a runtime, the state, the routers, and the error handlers."""
    from dhis2w_fhir_serve import (
        ServeRouters,
        ServeRuntime,
        ServeSettings,
        attach_serve_runtime,
        live_client,
        open_serve_runtime,
        register_error_handlers,
        require_json_is_acceptable,
        serve_context,
        serve_routers,
    )

    assert ServeSettings.resolve is not None
    assert {ServeRouters, ServeRuntime} != set()
    assert all(
        callable(name)
        for name in (
            attach_serve_runtime,
            live_client,
            open_serve_runtime,
            register_error_handlers,
            require_json_is_acceptable,
            serve_context,
            serve_routers,
        )
    )

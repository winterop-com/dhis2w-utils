"""Tests for the stated import surface of `dhis2w_fhir` - what the package says it exports, and what the docs render.

The package docstring calls `from dhis2w_fhir import ...` the one stable surface, and
`docs/fhir/api-dhis2w-fhir.md` renders a list of modules as the reference for it. Those two claims
can drift apart silently - a module reaching the API reference while none of its names reach
`__all__` leaves a reader following the docs onto an `ImportError`. This asserts they agree.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import dhis2w_fhir
import pytest

#: The API reference page whose rendered modules this surface is measured against.
_API_REFERENCE = Path(__file__).resolve().parents[3] / "docs" / "fhir" / "api-dhis2w-fhir.md"

#: One mkdocstrings directive as the page writes it, e.g. `::: dhis2w_fhir.doctor`.
_RENDER_DIRECTIVE = re.compile(r"^:::\s+(dhis2w_fhir[\w.]*)\s*$", re.MULTILINE)

#: The rendered modules that declare no `__all__` of their own, and are therefore read whole off the
#: page rather than name by name. Each is a schema or configuration module whose classes a reader
#: reaches through the module path the page itself names; the package re-exports the ones a caller
#: builds with. Listing them here is what makes adding another one a deliberate act rather than a
#: quiet way around this test.
_RENDERED_WITHOUT_A_DECLARED_SURFACE = frozenset(
    {
        "dhis2w_fhir.attributes",
        "dhis2w_fhir.config",
        "dhis2w_fhir.notes",
    }
)

#: The rendered modules whose `__all__` re-exports another package's names rather than declaring this
#: one's. `dhis2w_fhir.r4.schemas` is the capture-facing facade over `dhis2w_fhir_engine.r4.resources`,
#: so its surface answers to the engine and is checked by `test_fhir_r4_facade.py`, not to
#: `dhis2w_fhir.__all__` - the package root states capabilities, not the whole R4 resource vocabulary.
_RENDERED_FACADES = frozenset({"dhis2w_fhir.r4.schemas"})

#: The capabilities the library paper names as reachable in one import. Each is a name a caller
#: writes down, not a module path it has to learn.
_PUBLISHED_CAPABILITIES = (
    "generate_foundation",
    "generate_option_sets",
    "generate_categories",
    "generate_questionnaires",
    "generate_examples",
    "generate_organisation_units",
    "generate_pages",
    "generate_full",
    "BuildAbortingCodeError",
    "BuildAbortingNameError",
    "init_project",
    "refresh_project",
    "read_project_scaffold_state",
    "validate_codes",
    "resolve_validation_context",
    "resolve_validation_scope",
    "resolve_code_source",
    "build_aborting_code",
    "build_aborting_name",
    "display_code",
    "run_doctor",
    "DoctorOptions",
    "DoctorReport",
    "CaptureOutcome",
    "FamilyOutcome",
    "resolve_doctor_profile",
    "render_doctor_markdown",
    "phase_evidence",
    "grade",
    "grade_capture",
    "grade_forward",
    "grade_oracle",
    "record_refusal",
    "read_refusal_record",
    "ForwardRefusalRecord",
    "RefusalReason",
    "SPOOL_RELATIVE_PATH",
)


def _rendered_modules() -> list[str]:
    """Every module the API reference renders, in the order the page renders them."""
    return list(_RENDER_DIRECTIVE.findall(_API_REFERENCE.read_text(encoding="utf-8")))


def test_the_api_reference_renders_modules_this_test_can_read() -> None:
    """The page really is the source of the list - an empty parse would make every assertion below vacuous."""
    rendered = _rendered_modules()
    assert _API_REFERENCE.is_file()
    assert len(rendered) > 1
    assert "dhis2w_fhir" in rendered


@pytest.mark.parametrize("name", sorted(dhis2w_fhir.__all__))
def test_every_stated_name_imports(name: str) -> None:
    """Each name the package states it exports resolves to something - a stale `__all__` entry is an ImportError."""
    assert getattr(dhis2w_fhir, name, None) is not None


@pytest.mark.parametrize("module_name", sorted(set(_rendered_modules()) - {"dhis2w_fhir"}))
def test_every_rendered_module_has_its_surface_on_the_package(module_name: str) -> None:
    """A module the API reference renders exports its names through the package root, or declares none at all."""
    if module_name in _RENDERED_FACADES:
        return
    module = importlib.import_module(module_name)
    declared = getattr(module, "__all__", None)
    if declared is None:
        assert module_name in _RENDERED_WITHOUT_A_DECLARED_SURFACE, (
            f"{module_name} is rendered in the API reference and declares no __all__: either give it one, "
            f"or state here why it is read whole"
        )
        return
    missing = sorted(set(declared) - set(dhis2w_fhir.__all__))
    assert not missing, f"{module_name} exports names the package does not: {missing}"


@pytest.mark.parametrize("name", _PUBLISHED_CAPABILITIES)
def test_each_published_capability_is_one_import_away(name: str) -> None:
    """The capabilities the library paper names are reachable as `from dhis2w_fhir import <name>`."""
    assert name in dhis2w_fhir.__all__
    assert getattr(dhis2w_fhir, name, None) is not None


def test_the_stated_surface_is_a_list_a_reader_can_scan() -> None:
    """One entry per name, in the case-insensitive order the file keeps them, so a new export has one place to go."""
    stated = list(dhis2w_fhir.__all__)
    assert len(stated) == len(set(stated)), "the stated surface repeats a name"
    assert stated == sorted(stated, key=lambda name: (name.lower(), name))

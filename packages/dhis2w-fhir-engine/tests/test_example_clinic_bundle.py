"""Pins `examples/fhir/engine/clinic.json` to the module that writes it.

The Python examples in `examples/fhir/engine/` read the Bundle from `_bundle.clinic_bundle()`; the
command-line examples and the two 501 guides read it from `clinic.json` beside them. They are one
Bundle told twice, and a reader who runs both is entitled to the same four children, three doses and
two weights out of each. This test is what makes that entitlement true.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_EXAMPLES_DIRECTORY = Path(__file__).resolve().parents[3] / "examples" / "fhir" / "engine"
_BUNDLE_MODULE_PATH = _EXAMPLES_DIRECTORY / "_bundle.py"
_BUNDLE_FILE_PATH = _EXAMPLES_DIRECTORY / "clinic.json"

_JSON_INDENT = 2
"""The indent `clinic.json` is written at, and the only formatting choice the two sources share."""


def _load_bundle_module() -> ModuleType:
    """Import `examples/fhir/engine/_bundle.py` by path - it sits outside every installed package."""
    specification = importlib.util.spec_from_file_location("clinic_bundle_example", _BUNDLE_MODULE_PATH)
    if specification is None or specification.loader is None:
        pytest.fail(f"cannot import the example bundle module at {_BUNDLE_MODULE_PATH}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _canonical_json(bundle: dict[str, Any]) -> str:
    """Render a Bundle the way `clinic.json` is written: two-space indent, document key order, trailing newline."""
    return json.dumps(bundle, indent=_JSON_INDENT, ensure_ascii=False) + "\n"


@pytest.fixture(scope="module")
def bundle_module() -> ModuleType:
    """The example module that builds the clinic Bundle in Python."""
    return _load_bundle_module()


def test_both_example_sources_exist() -> None:
    """Neither half of the pair has been moved out from under the other."""
    assert _BUNDLE_MODULE_PATH.is_file(), f"{_BUNDLE_MODULE_PATH} is gone"
    assert _BUNDLE_FILE_PATH.is_file(), f"{_BUNDLE_FILE_PATH} is gone"


def test_clinic_json_is_the_module_bundle(bundle_module: ModuleType) -> None:
    """`clinic.json` is byte for byte what `clinic_bundle()` renders, so the two examples read one Bundle.

    Byte equality rather than value equality, because the file is committed and read by eye as well as
    by the engine: re-running the render is the whole fix when this fails.
    """
    expected = _canonical_json(bundle_module.clinic_bundle())
    actual = _BUNDLE_FILE_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        f"{_BUNDLE_FILE_PATH} has drifted from clinic_bundle() in {_BUNDLE_MODULE_PATH}. "
        f"Write it out again with json.dumps(clinic_bundle(), indent={_JSON_INDENT}) plus a trailing newline."
    )


def test_one_patient_is_the_first_entry(bundle_module: ModuleType) -> None:
    """`one_patient()` is the first child of the same Bundle, not a second copy of one."""
    bundle = bundle_module.clinic_bundle()
    assert bundle["entry"][0]["resource"] == bundle_module.one_patient()

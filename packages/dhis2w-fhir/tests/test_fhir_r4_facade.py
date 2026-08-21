"""Tests that `dhis2w_fhir.r4` is a facade over the engine's models and not a second copy of them.

`dhis2w_fhir_engine.r4.resources` defines the R4 resource models; `dhis2w_fhir.r4` is the import path
capture code reads them from. A facade only holds if every name is the engine's own class object -
two classes of the same shape would validate the same documents and still fail an `isinstance` check,
which is exactly the failure a reader would never think to look for. So identity is what is asserted.
"""

from __future__ import annotations

import dhis2w_fhir.r4 as capture_surface
import dhis2w_fhir.r4.schemas as facade
import dhis2w_fhir_engine.r4.resources as engine_resources
import pytest
from dhis2w_fhir.r4 import Patient
from dhis2w_fhir_engine.r4.resources import Patient as EnginePatient

#: The names `dhis2w_fhir.r4` owns rather than re-exports: the R4 primitive checks are this package's.
_PRIMITIVE_NAMES = frozenset(
    {
        "FHIR_DATE_PATTERN",
        "FHIR_DATE_TIME_PATTERN",
        "FHIR_TIME_PATTERN",
        "is_calendar_date",
        "is_fhir_date",
        "is_fhir_date_time",
        "is_fhir_time",
        "seconds_precision",
        "zoned_date_time",
    }
)


def test_the_facade_states_a_surface_to_check() -> None:
    """An empty or missing `__all__` would make every assertion below vacuous."""
    assert len(facade.__all__) > 50
    assert "Patient" in facade.__all__
    assert "QuestionnaireResponse" in facade.__all__


@pytest.mark.parametrize("name", sorted(facade.__all__))
def test_every_name_the_facade_states_is_the_engine_s_own_object(name: str) -> None:
    assert getattr(facade, name) is getattr(engine_resources, name)


@pytest.mark.parametrize("name", sorted(facade.__all__))
def test_every_name_the_facade_states_arrives_under_the_package_path(name: str) -> None:
    assert getattr(capture_surface, name) is getattr(engine_resources, name)
    assert name in capture_surface.__all__


@pytest.mark.parametrize("name", sorted(_PRIMITIVE_NAMES))
def test_the_primitive_checks_stay_this_package_s_own(name: str) -> None:
    assert name in capture_surface.__all__
    assert not hasattr(engine_resources, name)


def test_a_model_built_through_the_facade_is_an_instance_of_the_engine_class() -> None:
    assert Patient is EnginePatient
    assert isinstance(Patient(id="Kj9HgT4mQpz"), EnginePatient)
    assert Patient.__module__ == "dhis2w_fhir_engine.r4.resources"

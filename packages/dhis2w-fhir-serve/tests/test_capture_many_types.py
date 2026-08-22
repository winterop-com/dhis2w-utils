"""Capturing for six tracked entity types: `$generate` types every subject, and every response lands.

The capture half of the many-types contract. `[generate.tracked_entity_types]` is one line per type,
and the whole of what a running facade does with that line is read it off the compiled form: a
registration form declares `subjectType`, and `$generate` types the subject it mints from that and
from nothing else. Two types published as the same FHIR resource are two forms declaring the same
`subjectType`, which is why nothing here needs a special case for them.

What each claim below is:

- **`$generate` follows the map, per form.** The subject of a generated registration response is a
  reference of the resource the type is published as, identified by tracked entity UID.
- **Every one of them posts back 201.** The capture contract is one implementation over every subject
  type; a `Device` registration is accepted on the same terms a `Patient` one is.
- **Every one of them translates to DHIS2 carrying its own tracked entity type.** The forward leg
  reads the type off the form's `{base}/id/tracked-entity-type` identifier rather than off
  `subject.type`, so the DHIS2 payload names the right type even for the two that share a resource.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from dhis2w_fhir.config import FhirProject
from dhis2w_fhir.conversion import ConversionNaming, build_conversion_context, translate_response
from dhis2w_fhir.r4 import Questionnaire, QuestionnaireResponse
from dhis2w_fhir_serve.app import create_app
from dhis2w_fhir_serve.settings import ServeSettings
from dhis2w_fhir_serve.store import load_compiled_store
from fastapi import FastAPI
from fixture_many_types import (
    MANY_TRACKED_ENTITY_TYPES,
    FixtureTrackedEntityType,
    build_many_types_project,
)

#: The system a subject is identified under, whichever resource the subject is.
TRACKED_ENTITY_SYSTEM = "http://dhis2.org/fhir/id/tracked-entity"

FHIR_JSON = {"Content-Type": "application/fhir+json"}


@pytest.fixture
def many_types_project(tmp_path: Path) -> FhirProject:
    """The capture guide with six tracked entity types published over five FHIR resource types."""
    return build_many_types_project(tmp_path / "project")


@pytest.fixture
async def many_types_capture_client(many_types_project: FhirProject) -> AsyncIterator[httpx.AsyncClient]:
    """The compiled facade over that guide - no instance behind it, because capture needs none."""
    app: FastAPI = create_app(ServeSettings(project_dir=many_types_project.project_root))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://serve.test") as http:
            yield http


async def _generate(client: httpx.AsyncClient, published: FixtureTrackedEntityType) -> dict[str, Any]:
    """Fill one type's registration form through the operation a capture client invokes."""
    answer = await client.get(f"/Questionnaire/{published.uid}/$generate", params={"seed": 7})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert isinstance(body, dict)
    return body


@pytest.mark.parametrize("published", MANY_TRACKED_ENTITY_TYPES, ids=lambda published: published.uid)
async def test_a_generated_registration_is_typed_by_the_form_its_type_publishes(
    many_types_capture_client: httpx.AsyncClient, published: FixtureTrackedEntityType
) -> None:
    """QR subject typing follows the map: the generated subject is the resource the type is served as."""
    generated = await _generate(many_types_capture_client, published)

    subject = generated["subject"]
    assert subject["type"] == published.resource_type
    assert subject["identifier"]["system"] == TRACKED_ENTITY_SYSTEM
    assert subject["identifier"]["value"]


@pytest.mark.parametrize("published", MANY_TRACKED_ENTITY_TYPES, ids=lambda published: published.uid)
async def test_a_generated_registration_of_any_type_posts_back_201(
    many_types_capture_client: httpx.AsyncClient, published: FixtureTrackedEntityType
) -> None:
    """One capture implementation over every subject type: a fridge is received as a person is."""
    generated = await _generate(many_types_capture_client, published)

    posted = await many_types_capture_client.post("/QuestionnaireResponse", json=generated, headers=FHIR_JSON)

    assert posted.status_code == 201, posted.text
    assert "Location" in posted.headers


@pytest.mark.parametrize("published", MANY_TRACKED_ENTITY_TYPES, ids=lambda published: published.uid)
async def test_a_generated_registration_of_any_type_translates_to_its_own_dhis2_type(
    many_types_capture_client: httpx.AsyncClient,
    many_types_project: FhirProject,
    published: FixtureTrackedEntityType,
) -> None:
    """The forward leg reads the type off the form, so the two `Device` types stay two DHIS2 types."""
    generated = await _generate(many_types_capture_client, published)
    store = load_compiled_store(many_types_project)
    context = build_conversion_context(
        ConversionNaming.from_config(many_types_project.config.generate, many_types_project.config.ig.canonical),
        [Questionnaire.model_validate(entry.body) for entry in store.entries if entry.resource_type == "Questionnaire"],
    )

    result = translate_response(QuestionnaireResponse.model_validate(generated), context)

    assert result.refusals == (), result.refusals
    assert result.tracked_entity is not None
    assert result.tracked_entity.trackedEntityType == published.uid
    assert result.tracked_entity.trackedEntity == generated["subject"]["identifier"]["value"]

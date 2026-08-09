"""The live store: the resources the facade serves, built off a DHIS2 instance instead of a compiled IG.

`--live` is the mode with no build step in front of it - point the server at a project and an
instance, and it answers with the documents `d2w fhir generate` would have written and SUSHI
would have compiled. One connected client reads the whole instance side of the build, the JSON
builders turn that into resources, and the client is closed before the first request arrives:
the store is a snapshot of the instance at startup, exactly as the compiled store is a snapshot
of the last build.

What the store holds is the served read-set and nothing else. The foundation artifacts -
StructureDefinitions, the extensions, the IG's `kind #requirements` CapabilityStatement - are
authored as FSH and only exist as JSON once SUSHI has compiled them, and no FSH compiler runs in
this process. That costs the live store nothing: a capture server reads Questionnaire, CodeSystem,
ValueSet, Location, and Organization (`CAPTURE_SERVER_READ_RESOURCE_TYPES`), every one of which
comes out of a JSON builder here. Both ConceptMap families - option sets and categories - ride
along with the terminology they map, so a live store serves the same reads, searches, and
`$translate` answers over the maps that a compiled one does. The IG's own CapabilityStatement is
still named by `/metadata`, which `instantiates` it by canonical - a URL derived from config,
needing no artifact to state.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from dhis2w_core.client_context import open_client
from dhis2w_fhir import (
    build_category_artifacts,
    build_category_concept_map_artifacts,
    build_data_dictionary_documents,
    build_option_set_artifacts,
    build_option_set_concept_map_artifacts,
    build_organisation_unit_instances,
    build_questionnaire_documents,
)
from dhis2w_fhir.service import fetch_live_ig_inputs, resolve_generation_profile
from dhis2w_fhir.writer import JsonBuild

from dhis2w_fhir_serve.log import LOGGER_NAME
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, StoreEntry

if TYPE_CHECKING:
    from dhis2w_fhir.config import FhirProject
    from dhis2w_fhir.r4 import CodeSystem, Questionnaire, ValueSet

    from dhis2w_fhir_serve.settings import ServeSettings

#: What a live entry names as its source, where a compiled entry names the file it was read from.
LIVE_SOURCE = "live"

logger = logging.getLogger(LOGGER_NAME)


async def build_live_store(project: FhirProject, settings: ServeSettings) -> ResourceStore:
    """Build the store the facade serves from one DHIS2 instance, over a single client held for the fetch.

    The builders come in two shapes and both land in the same store. The questionnaires and the
    data dictionary are returned as R4 models, so they are dumped to their wire documents here.
    The option sets, the categories, the ConceptMaps of both, and the registry are returned as the
    serialised JSON artifacts the generate targets write to disk, so their documents are read
    back out of that exact text - what the facade serves live is then byte-identical to what the
    project would have committed, with no second serialisation path to drift from it.
    """
    generation = resolve_generation_profile(project, settings.profile)
    logger.info(
        "live store: reading %s as profile %s (from %s)",
        generation.profile.base_url,
        generation.name,
        generation.origin,
    )
    config = project.config.generate
    canonical = project.config.ig.canonical
    ig_status = project.config.ig.status
    async with open_client(generation.profile) as client:
        inputs = await fetch_live_ig_inputs(client, config)
    questionnaires = build_questionnaire_documents(
        inputs.sources,
        config,
        canonical,
        ig_status=ig_status,
        option_set_plan=inputs.option_set_plan,
        attribute_codes=inputs.attribute_codes,
    )
    data_dictionary = build_data_dictionary_documents(inputs.sources, config, canonical, ig_status=ig_status)
    json_builds: tuple[JsonBuild, ...] = (
        build_option_set_artifacts(
            inputs.option_sets, config, canonical, ig_status=ig_status, attribute_codes=inputs.attribute_codes
        ),
        JsonBuild(
            artifacts=build_option_set_concept_map_artifacts(inputs.option_sets, config, canonical, ig_status=ig_status)
        ),
        build_category_artifacts(
            inputs.categories, config, canonical, ig_status=ig_status, attribute_codes=inputs.attribute_codes
        ),
        JsonBuild(
            artifacts=build_category_concept_map_artifacts(inputs.categories, config, canonical, ig_status=ig_status)
        ),
        build_organisation_unit_instances(
            inputs.organisation_units, config, canonical, attribute_codes=inputs.attribute_codes
        ),
    )
    documents: list[CodeSystem | Questionnaire | ValueSet] = [
        *questionnaires.questionnaires,
        *data_dictionary.code_systems,
        *data_dictionary.value_sets,
    ]
    entries = [
        *(_entry(_document(resource)) for resource in documents),
        *(_entry(json.loads(artifact.content)) for build in json_builds for artifact in build.artifacts),
    ]
    for note in [*inputs.notes, *questionnaires.notes, *(note for build in json_builds for note in build.notes)]:
        logger.info("live store: %s", note.message)
    return ResourceStore(entries=tuple(entries))


def _document(resource: CodeSystem | Questionnaire | ValueSet) -> dict[str, Any]:
    """One built resource as the wire document the facade serves, aliases applied and absent elements dropped."""
    return resource.model_dump(mode="json", by_alias=True, exclude_none=True)


def _entry(body: dict[str, Any]) -> StoreEntry:
    """Index one built document the way the compiled loader indexes a file, marked as built live.

    A built document always carries its `resourceType` and its `id` - every builder sets both on
    a typed model - so the read is direct rather than the compiled loader's defensive parse of
    whatever a project committed by hand.
    """
    canonical_url = body.get("url")
    return StoreEntry(
        resource_type=str(body["resourceType"]),
        resource_id=str(body["id"]),
        canonical_url=canonical_url if isinstance(canonical_url, str) else None,
        identifiers=_identifier_tokens(body.get("identifier")),
        source=LIVE_SOURCE,
        body=body,
    )


def _identifier_tokens(raw: Any) -> tuple[IdentifierToken, ...]:
    """The `system|value` tokens one built document is searchable by; every builder emits a list."""
    if not isinstance(raw, list):
        return ()
    return tuple(
        IdentifierToken(system=entry.get("system"), value=entry["value"])
        for entry in raw
        if isinstance(entry, dict) and isinstance(entry.get("value"), str)
    )

"""The live store: the resources the facade serves, built off a DHIS2 instance instead of a compiled IG.

`--live` is the mode with no build step in front of it - point the server at a project and an
instance, and it answers with the documents `d2w fhir generate` would have written and SUSHI
would have compiled. One connected client reads the whole instance side of the build and the JSON
builders turn that into resources: the store is a snapshot of the instance at startup, exactly as
the compiled store is a snapshot of the last build, and no read of it ever touches DHIS2 again.

That one client stays open for the life of the process, because the register is answered from the
instance per request rather than from the store - see `dhis2w_fhir_serve.register`. The caller owns
it through `open_live_client`, so the store build and the register routes share one connection and
one profile resolution.

What the store holds is the served read-set and nothing else. The definitional artifacts -
StructureDefinitions, the extensions, the IG's `kind #requirements` CapabilityStatement - are
authored as FSH and only exist as JSON once SUSHI has compiled them, and no FSH compiler runs in
this process. That costs the live store nothing: a capture server reads Questionnaire, CodeSystem,
ValueSet, Location, and Organization (`CAPTURE_SERVER_READ_RESOURCE_TYPES`), every one of which
comes out of a JSON builder here - the foundation terminology included. The form-type and
period-type pairs backing the D2FormType and D2Period bindings, and the organisation-unit level and
whole-selection pairs, are declared inside FSH files a live run never compiles, so each has a JSON
twin that renders the same Python vocabulary the template renders: a client resolving a served
form's form-type code system gets the code system, not a 404. All four ConceptMap families -
option sets, categories, the attribute option combos an aggregate form is keyed by, and the
resource type each tracked entity type is registered as - ride along with the terminology they map,
so a live store serves the same reads, searches, and `$translate` answers over the maps that a
compiled one does. The IG's own CapabilityStatement is still named by
`/metadata`, which `instantiates` it by canonical - a URL derived from config, needing no artifact
to state.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from dhis2w_core.client_context import open_client
from dhis2w_fhir import (
    build_category_artifacts,
    build_category_concept_map_artifacts,
    build_data_dictionary_documents,
    build_foundation_terminology_documents,
    build_option_set_artifacts,
    build_option_set_concept_map_artifacts,
    build_organisation_unit_instances,
    build_organisation_unit_level_terminology_documents,
    build_organisation_unit_terminology_documents,
    build_questionnaire_documents,
)
from dhis2w_fhir.config import HostileNamePosture
from dhis2w_fhir.hostile_names import HostileNameGate
from dhis2w_fhir.resources.attribute_combos import (
    build_attribute_combo_artifacts,
    build_attribute_combo_concept_map_artifacts,
)
from dhis2w_fhir.resources.categories.decomposition import build_category_decomposition
from dhis2w_fhir.resources.questionnaires.assignments import build_assignment_artifacts
from dhis2w_fhir.service import fetch_live_ig_inputs, resolve_generation_profile
from dhis2w_fhir.writer import JsonBuild

from dhis2w_fhir_serve.log import LOGGER_NAME
from dhis2w_fhir_serve.store import IdentifierToken, ResourceStore, StoreEntry

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from dhis2w_client import Dhis2Client
    from dhis2w_fhir.config import FhirProject, GenerateConfig
    from dhis2w_fhir.r4 import CodeSystem, ConceptMap, Questionnaire, ValueSet
    from dhis2w_fhir.resources.organisation_units import OrganisationUnitTerminologyBuild
    from dhis2w_fhir.resources.organisation_units.schemas import OrganisationUnitIn
    from dhis2w_fhir.status import IgStatus

    from dhis2w_fhir_serve.settings import ServeSettings

#: What a live entry names as its source, where a compiled entry names the file it was read from.
LIVE_SOURCE = "live"

logger = logging.getLogger(LOGGER_NAME)


@asynccontextmanager
async def open_live_client(project: FhirProject, settings: ServeSettings) -> AsyncGenerator[Dhis2Client]:
    """Open the DHIS2 client a live run reads through, named by the profile the project resolves.

    The server holds this open for the whole process rather than closing it after the store is
    built: the register answers from the instance per request, so a live facade has one connection to
    DHIS2 for its lifetime and closes it when the lifespan unwinds.
    """
    generation = resolve_generation_profile(project, settings.profile)
    logger.info(
        "live store: reading %s as profile %s (from %s)",
        generation.profile.base_url,
        generation.name,
        generation.origin,
    )
    async with open_client(generation.profile) as client:
        yield client


async def build_live_store(project: FhirProject, settings: ServeSettings, client: Dhis2Client) -> ResourceStore:
    """Build the store the facade serves from one DHIS2 instance, over the client the caller holds open.

    The builders come in two shapes and both land in the same store. The questionnaires and the
    data dictionary are returned as R4 models, so they are dumped to their wire documents here.
    The option sets, the categories, the ConceptMaps of both, and the registry are returned as the
    serialised JSON artifacts the generate targets write to disk, so their documents are read
    back out of that exact text - what the facade serves live is then byte-identical to what the
    project would have committed, with no second serialisation path to drift from it.

    The names and codes go through the same screening a generate run of this project would put them
    through, for the same reason the serialisation does: one project means one set of names, and a
    UID a compiled guide publishes as "Mortality under 5 years" is not one a live facade may serve
    as something else. `_serving_gate` is which screening that is.
    """
    config = project.config.generate
    canonical = project.config.ig.canonical
    ig_status = project.config.ig.status
    inputs = await fetch_live_ig_inputs(client, config, gate=_serving_gate(config))
    assignments = build_assignment_artifacts(
        inputs.sources,
        inputs.assignments,
        config,
        published=inputs.organisation_unit_stems,
        stem_plan=inputs.questionnaire_stems,
    )
    decomposition = build_category_decomposition(inputs.sources, inputs.categories, config, canonical)
    attribute_combos = build_attribute_combo_artifacts(
        inputs.sources, config, canonical, ig_status=ig_status, decomposition=decomposition
    )
    questionnaires = build_questionnaire_documents(
        inputs.sources,
        config,
        canonical,
        ig_status=ig_status,
        option_set_plan=inputs.option_set_plan,
        attribute_codes=inputs.attribute_codes,
        assignments=assignments.plan,
        attribute_combos=attribute_combos.plan,
    )
    data_dictionary = build_data_dictionary_documents(
        inputs.sources, config, canonical, ig_status=ig_status, decomposition=decomposition
    )
    foundation_terminology = build_foundation_terminology_documents(config, canonical, ig_status=ig_status)
    organisation_unit_terminology = _organisation_unit_terminology(
        inputs.organisation_units, config, canonical, ig_status
    )
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
        assignments,
        attribute_combos,
        JsonBuild(
            artifacts=build_attribute_combo_concept_map_artifacts(
                inputs.sources, config, canonical, ig_status=ig_status
            )
        ),
    )
    documents: list[CodeSystem | ConceptMap | Questionnaire | ValueSet] = [
        *questionnaires.questionnaires,
        *data_dictionary.code_systems,
        *data_dictionary.value_sets,
        *data_dictionary.concept_maps,
        *foundation_terminology.code_systems,
        *foundation_terminology.value_sets,
        *[code_system for build in organisation_unit_terminology for code_system in build.code_systems],
        *[value_set for build in organisation_unit_terminology for value_set in build.value_sets],
    ]
    entries = [
        *(_entry(_document(resource)) for resource in documents),
        *(_entry(json.loads(artifact.content)) for build in json_builds for artifact in build.artifacts),
    ]
    for note in [*inputs.notes, *questionnaires.notes, *(note for build in json_builds for note in build.notes)]:
        logger.info("live store: %s", note.message)
    return ResourceStore(entries=tuple(entries))


def _serving_gate(config: GenerateConfig) -> HostileNameGate | None:
    """The screening a live serve reads DHIS2's names and codes through, from `[generate] hostile_names`.

    SUBSTITUTE IS THE ONE POSTURE THAT CHANGES A SERVED DOCUMENT, and it changes it into exactly what
    a generate run of this project would have published: the rewritten name on the resource title,
    the concept display and the question label, the rewritten code on every published concept with
    the DHIS2 code beside it as a `dhis2-code` property. A person who learned a form's name from the
    guide finds that form on the live facade under the name they learned.

    UNDER EVERY OTHER POSTURE A LIVE SERVE IS BYTE-TRUE AND REFUSES NOTHING. `refuse` is an answer
    about what a build may publish - write nothing, and change the name in DHIS2 before an hour of
    build time is spent on it - and serving is not building: there is no page to strict-parse and no
    hour to lose, so a name carrying `<` is served exactly as the instance holds it. An unset posture
    is byte-true for the same reason, and asks nobody: a server has no one at a terminal to ask.
    """
    if config.hostile_names is not HostileNamePosture.SUBSTITUTE:
        return None
    return HostileNameGate(posture=HostileNamePosture.SUBSTITUTE)


def _organisation_unit_terminology(
    organisation_units: list[OrganisationUnitIn], config: GenerateConfig, canonical: str, ig_status: IgStatus
) -> tuple[OrganisationUnitTerminologyBuild, ...]:
    """The organisation-unit vocabularies this selection publishes, on the conditions the FSH target publishes them.

    The level pair rides on there being a selection at all, since it is the vocabulary every
    published Location states its level from. The whole-selection pair is the one
    `[generate.organisation_units] terminology` turns on, so a project that leaves it off serves
    no organisation-unit code list, exactly as its compiled guide holds none.
    """
    if not organisation_units:
        return ()
    builds = [
        build_organisation_unit_level_terminology_documents(
            [organisation_unit.level for organisation_unit in organisation_units],
            config,
            canonical,
            ig_status=ig_status,
        )
    ]
    if config.organisation_units.terminology:
        builds.append(
            build_organisation_unit_terminology_documents(organisation_units, config, canonical, ig_status=ig_status)
        )
    return tuple(builds)


def _document(resource: CodeSystem | ConceptMap | Questionnaire | ValueSet) -> dict[str, Any]:
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

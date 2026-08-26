"""`$summary` - one person's International Patient Summary, assembled from the register and the record.

THE OPERATION ALREADY HAD A NAME BEFORE THIS PROJECT EXISTED. The IPS publishes
`OperationDefinition/summary` on `Patient`, at instance level (`[base]/Patient/[id]/$summary`) and at
type level (`[base]/Patient/$summary`, where "the requestor SHALL provide an identifier"), and the
IPS Server CapabilityStatement declares exactly that one operation on exactly that one resource. So
a client that speaks IPS reaches this without learning a route this project invented, which is R6 in
`docs/fhir/design/ips.md` section 8.

**IT IS SCOPED TO THE PEOPLE.** The register serves nine FHIR resource types over whatever tracked
entity types a project maps onto them, and `$summary` on a `Specimen` or a `Location` is not a
narrower patient summary - it is a document nobody has defined. So the operation is answered on the
register resources R4 gives a person (`register.projection.PERSON_RESOURCE_TYPES`) and refused by
name on the rest, with the refusal saying which resource this register serves.

**NOTHING NEW IS READ.** The subject is the very resource `GET /{RegisterType}/{uid}` answers with,
and the doses come out of the record projection `GET /tracked-entities/{uid}/events` runs on. A
summary is a second reading of reads that already exist and not a third way into DHIS2.

That is two reads of the tracked entity's own address rather than one, and deliberately: each
surface states the DHIS2 projection it needs in its own module - the register asks for the
attributes, the record asks for the enrollments and their data values - and merging them here would
make one surface's read depend on the other's field list. Both are entity-scoped and both carry the
credentials of whoever asked, which is the whole of what R3 requires.

**THE GATES, IN THE ORDER THEY COST SOMETHING.** `[ips] enabled` first, because a project that
publishes no summary publishes none however the process was started and a refusal costs no round
trip. Then the register's own gates, which decide whether there is a person to be about. Then
`[serve.tracked_entities] events`, and only where a clinical section is mapped: a summary whose
sections are all empty reads no record, so refusing it for the record's sake would refuse a request
that was never going to make one.

**THE TYPE-LEVEL FORM RESOLVES THROUGH THE REGISTER'S OWN IDENTIFIER SEARCH.** `?identifier=` is the
same token grammar `GET /Patient?identifier=` answers - a system-qualified token naming one key, or
a bare value tried against every key - so a client that can find somebody can summarise them without
learning a second search. An identifier several people hold is refused rather than answered: a
summary is about one person, and handing back the first match would be this server picking which
one.

**THE CAVEAT RIDES TWICE.** The document says what it is and is not in `Composition.text`, and the
response says the same sentence in a header beside it - the two-place idiom
`dhis2w_fhir_serve.projection.serving` argues for the projection's as-of instant, for the same
reason. `dhis2w_fhir.summary` is where the sentence is written and why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_client.errors import Dhis2ClientError
from dhis2w_fhir.summary import build_patient_summary
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from dhis2w_fhir_serve.capability import SOFTWARE_NAME
from dhis2w_fhir_serve.errors import (
    FHIR_JSON_MEDIA_TYPE,
    BadOperationError,
    NotFoundError,
    RecordDisabledError,
    SummaryDisabledError,
    SummaryNotSupportedForSubjectError,
    UnsupportedSearchParameterError,
    UpstreamError,
)
from dhis2w_fhir_serve.history.projection import RecordProjection
from dhis2w_fhir_serve.history.wire import fetch_tracked_entity_record
from dhis2w_fhir_serve.register.projection import PERSON_RESOURCE_TYPES, registered_entity_for
from dhis2w_fhir_serve.register.wire import upstream_refusal_text
from dhis2w_fhir_serve.routes.capture import capture_state
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.routes.negotiation import FORMAT_PARAMETER
from dhis2w_fhir_serve.routes.read import alternatives, identifier_token
from dhis2w_fhir_serve.routes.register import (
    RegisterLookup,
    matching_entities,
    register_lookup,
    registered_tracked_entity,
)
from dhis2w_fhir_serve.spool import current_instant
from dhis2w_fhir_serve.summary import SummaryDoses, recorded_doses

if TYPE_CHECKING:
    from dhis2w_client.generated.v42.oas import TrackerTrackedEntity

#: Where the operation is answered, in both of the forms the IPS defines it in.
INSTANCE_SUMMARY_PATH = "/{resource_type}/{tracked_entity_uid}/$summary"
TYPE_SUMMARY_PATH = "/{resource_type}/$summary"

#: The one parameter the type-level form answers, which the IPS says a requestor SHALL provide.
IDENTIFIER_PARAMETER = "identifier"

#: The header the caveat rides beside the response, for whoever reads responses rather than resources.
SUMMARY_CAVEAT_HEADER = "X-DHIS2W-Summary-Caveat"

#: The DHIS2 namespace a dose's `Immunization.vaccineCode` is coded from - the data element the dose
#: was recorded against, under the very system the published section map maps out of.
DATA_ELEMENT_IDENTIFIER_SEGMENT = "data-element"

router = APIRouter()


@router.get(INSTANCE_SUMMARY_PATH)
async def read_patient_summary(request: Request, resource_type: str, tracked_entity_uid: str) -> Response:
    """Assemble the summary of one person, named by their DHIS2 tracked entity UID."""
    lookup = await _summary_lookup(request, resource_type)
    entity = await registered_tracked_entity(lookup, tracked_entity_uid)
    if entity is None:
        raise NotFoundError(resource_type, tracked_entity_uid)
    return await _summary_response(request, lookup, resource_type, entity)


@router.get(TYPE_SUMMARY_PATH)
async def search_patient_summary(request: Request, resource_type: str) -> Response:
    """Assemble the summary of the one person an identifier names, refusing a value that names several."""
    lookup = await _summary_lookup(request, resource_type)
    tokens = [
        identifier_token(IDENTIFIER_PARAMETER, value)
        for name, raw in request.query_params.multi_items()
        if name == IDENTIFIER_PARAMETER
        for value in alternatives(name, raw)
    ]
    _require_answerable_parameters(request, resource_type)
    if not tokens:
        raise BadOperationError(
            f"`$summary` on `{resource_type}` names no person: state `identifier={{system}}|{{value}}`, or "
            f"`identifier={{value}}` to look under every key this register searches, or ask for one person "
            f"at `{resource_type}/{{uid}}/$summary`"
        )
    try:
        found = await matching_entities(lookup, resource_type, tokens)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity search: {upstream_refusal_text(error)}"
        ) from error
    if not found:
        raise NotFoundError(resource_type, ", ".join(token.value for token in tokens))
    if len(found) > 1:
        named = ", ".join(entity.trackedEntity or "" for entity in found)
        raise BadOperationError(
            f"that identifier names {len(found)} people on this instance ({named}), and a summary is about "
            f"one: ask for the one you mean at `{resource_type}/{{uid}}/$summary`"
        )
    return await _summary_response(request, lookup, resource_type, found[0])


async def _summary_lookup(request: Request, resource_type: str) -> RegisterLookup:
    """What a summary runs against, refusing every way this process assembles none of it.

    The project's own word comes first and the resource's person-hood comes second, because both are
    settled before the instance is asked anything. `register_lookup` is the third and carries the
    register's own gates - live mode, a published subject type, a resource this register serves -
    since a summary is a document about somebody the register serves and about nobody else.
    """
    if not serve_context(request).project.config.ips.enabled:
        raise SummaryDisabledError(resource_type)
    if resource_type not in PERSON_RESOURCE_TYPES:
        raise SummaryNotSupportedForSubjectError(resource_type, PERSON_RESOURCE_TYPES)
    return await register_lookup(request, resource_type)


def _require_answerable_parameters(request: Request, resource_type: str) -> None:
    """Refuse a type-level summary naming a parameter this operation cannot apply to it.

    The operation takes one input and answers one document, so a `_count` or a `_tag` would be a
    narrowing this server cannot perform - and a request answered as though it had been applied
    would hand back a summary of somebody the caller did not ask about.

    `_format` is passed over: it names the format the document comes back in, which the negotiation
    settled before this ran, and it asks the operation for nothing.
    """
    for name in request.query_params:
        if name not in (IDENTIFIER_PARAMETER, FORMAT_PARAMETER):
            raise UnsupportedSearchParameterError(resource_type, name, (IDENTIFIER_PARAMETER,))


async def _summary_response(
    request: Request, lookup: RegisterLookup, resource_type: str, entity: TrackerTrackedEntity
) -> Response:
    """Assemble and serialise one person's summary, with the caveat stated in it and beside it.

    `server_version` is imported here rather than at module scope: the runtime module builds the
    application these routers are mounted on, so importing it from a route module's body would close
    the cycle `dhis2w_fhir_serve.routes` already imports its routers inside a function to avoid.
    """
    from dhis2w_fhir_serve.runtime import server_version

    context = serve_context(request)
    sections = context.project.config.ips.sections
    subject = registered_entity_for(entity, lookup.surface.index, resource_type)
    doses = await _doses(request, lookup, resource_type, entity.trackedEntity or "")
    summary = build_patient_summary(
        subject,
        doses.doses,
        vaccine_code_system=(
            f"{context.project.config.generate.identifier_system_base}/id/{DATA_ELEMENT_IDENTIFIER_SEGMENT}"
        ),
        assembled_at=current_instant(),
        author_display=f"{SOFTWARE_NAME} {server_version()}",
        immunizations_mapped=sections.immunizations.maps_anything(),
        unpublished_stage_uids=doses.unpublished_stage_uids,
    )
    return Response(
        content=summary.bundle.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
        headers={SUMMARY_CAVEAT_HEADER: summary.caveat},
    )


async def _doses(request: Request, lookup: RegisterLookup, resource_type: str, tracked_entity_uid: str) -> SummaryDoses:
    """Read this person's doses out of their record, or nothing where no clinical section is mapped.

    A summary with no mapped section reads no record at all, which is why the record's own gate is
    checked here rather than beside the others: refusing a request for the record's sake when the
    request was never going to make one would be a refusal about nothing.
    """
    context = serve_context(request)
    immunizations = context.project.config.ips.sections.immunizations
    if not immunizations.maps_anything():
        return SummaryDoses()
    if not lookup.surface.serves_events():
        raise RecordDisabledError(resource_type)
    try:
        record = await fetch_tracked_entity_record(lookup.reader, tracked_entity_uid)
    except Dhis2ClientError as error:
        raise UpstreamError(
            f"the DHIS2 instance did not answer the tracked entity read: {upstream_refusal_text(error)}"
        ) from error
    if record is None:
        raise NotFoundError(resource_type, tracked_entity_uid)
    return recorded_doses(record, _projection(request), immunizations)


def _projection(request: Request) -> RecordProjection:
    """The very projection the record surface runs on, so one value is typed one way in both answers."""
    context = serve_context(request)
    state = capture_state(request)
    return RecordProjection(
        naming=state.naming,
        store=context.store,
        indexes=state.indexes,
        timezone=context.project.config.generate.timezone,
    )

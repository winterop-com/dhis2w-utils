"""`GET /ConceptMap/$translate` - the type-level operation over the ConceptMaps the project publishes.

One ConceptMap per option set takes the generated concept codes back to the DHIS2 option UID and,
where the option carries one, the DHIS2 option code. This operation is what makes that readable
over the wire: hand it a concept and it answers with every DHIS2 identifier the maps state for it.

The maps are served as documents too - ConceptMap is in `SERVED_READ_RESOURCE_TYPES`, so
`GET /ConceptMap/<id>` answers the published map verbatim. The two are complementary: a read hands
over the whole mapping table for a person or a UI to look at, and this operation answers the one
question a forwarder has, without its caller walking groups and elements.

The path is fixed, so this router mounts ahead of the read catch-alls: `/{resource_type}/{resource_id}`
matches `/ConceptMap/$translate` just as happily and would answer it as a read of a resource named
`$translate`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhis2w_fhir.r4 import Coding, Parameters, ParametersParameter
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import Response

from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, BadSearchError
from dhis2w_fhir_serve.routes.context import serve_context

if TYPE_CHECKING:
    from dhis2w_fhir.r4 import ConceptMap

#: The path the operation is served at; `capability.py` declares it by the name R4 gives it.
TRANSLATE_PATH = "/ConceptMap/$translate"

router = APIRouter()


class TranslateRequest(BaseModel):
    """The concept one `$translate` call asks about, and the target system it will accept an answer in."""

    model_config = ConfigDict(frozen=True)

    system: str
    code: str
    target_system: str | None = None


class TranslationMatch(BaseModel):
    """One mapping the served maps state for the asked-about concept, as a `match` parameter reports it."""

    model_config = ConfigDict(frozen=True)

    system: str | None = None
    code: str
    display: str | None = None
    equivalence: str | None = None
    source: str | None = None


def parse_translate_request(params: QueryParams) -> TranslateRequest:
    """Read the query into the concept to translate, refusing a call that names no `system` or no `code`.

    R4 spells the target parameter `targetsystem`, all lower case, and real clients send
    `targetSystem` about as often - both are read here, the lower-case spelling first, so a client
    that sends either is answered rather than silently given every group of a matching source.
    """
    system = _required(params, "system")
    code = _required(params, "code")
    target_system = params.get("targetsystem") or params.get("targetSystem")
    return TranslateRequest(system=system, code=code, target_system=target_system or None)


@router.get(TRANSLATE_PATH)
async def translate_concept(request: Request) -> Response:
    """Answer with the DHIS2 identifiers the served ConceptMaps state for one concept."""
    context = serve_context(request)
    translate = parse_translate_request(request.query_params)
    matches = find_translations(context.store.concept_maps(), translate)
    return _parameters_response(_translate_parameters(matches, translate))


def find_translations(
    concept_maps: tuple[ConceptMap, ...], translate: TranslateRequest
) -> tuple[TranslationMatch, ...]:
    """Every mapping the maps state for the asked-about concept, in the order the maps were loaded.

    A group matches on its `source`, and on its `target` too when the call named one. A target
    carrying no code maps the concept onto nothing statable and is passed over.
    """
    found: list[TranslationMatch] = []
    for concept_map in concept_maps:
        for group in concept_map.group or []:
            if group.source != translate.system:
                continue
            if translate.target_system is not None and group.target != translate.target_system:
                continue
            for element in group.element or []:
                if element.code != translate.code:
                    continue
                found.extend(
                    TranslationMatch(
                        system=group.target,
                        code=target.code,
                        display=target.display or element.display,
                        equivalence=target.equivalence,
                        source=concept_map.url,
                    )
                    for target in element.target or []
                    if target.code is not None
                )
    return tuple(found)


def _required(params: QueryParams, name: str) -> str:
    """One parameter the operation cannot run without, refused as a bad request when it is absent or empty."""
    value = params.get(name)
    if not value:
        raise BadSearchError(f"`$translate` needs a `{name}` parameter")
    return value


def _translate_parameters(matches: tuple[TranslationMatch, ...], translate: TranslateRequest) -> Parameters:
    """The R4 output shape: `result`, a `message` when nothing was found, and one `match` per mapping."""
    parameters = [ParametersParameter(name="result", valueBoolean=bool(matches))]
    if not matches:
        parameters.append(ParametersParameter(name="message", valueString=_not_found_message(translate)))
    parameters.extend(_match_parameter(match) for match in matches)
    return Parameters(parameter=parameters)


def _not_found_message(translate: TranslateRequest) -> str:
    """Say what was not found: the code system, or the code within it."""
    into = f" into `{translate.target_system}`" if translate.target_system is not None else ""
    return (
        f"no ConceptMap served here maps `{translate.code}` from `{translate.system}`{into}; "
        "the code system, the code, or the target system is not one this server holds a mapping for"
    )


def _match_parameter(match: TranslationMatch) -> ParametersParameter:
    """One `match` parameter: how close the mapping is, the concept it lands on, and the map it came from."""
    parts = [
        ParametersParameter(name="equivalence", valueCode=match.equivalence),
        ParametersParameter(
            name="concept", valueCoding=Coding(system=match.system, code=match.code, display=match.display)
        ),
    ]
    if match.source is not None:
        parts.append(ParametersParameter(name="source", valueUri=match.source))
    return ParametersParameter(name="match", part=parts)


def _parameters_response(parameters: Parameters) -> Response:
    """Serialise the operation body the way every other FHIR document leaves this server."""
    return Response(
        content=parameters.model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )

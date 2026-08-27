"""What a FHIR route answers in, and the one request it cannot answer at all.

This server serves `application/fhir+json` and nothing else. `/metadata` says so - `format` names
`json` alone - and a client that asked for XML is entitled to be told that rather than handed a
JSON body it will fail to parse under a media type it declared it could not read. So a request
whose `Accept` rules JSON out is refused with 406 before the route runs.

THE TEST IS DELIBERATELY MINIMAL: does any media range in the header admit JSON? `*/*`,
`application/*`, `application/json`, `application/fhir+json`, and every other `application/…+json`
do; `application/fhir+xml` alone does not. Quality values are read past rather than ranked, because
ranking matters only where a server has several formats to choose between and this one has one -
a header naming XML first and `*/*` last is a client that will take what it is given.

An absent or empty `Accept` is a client with no opinion, and R4 answers those in the server's own
format. That is the case a `curl` with no flags and every liveness probe sends, so it is never the
case a refusal falls on.

A browser is the client the header test falls on hardest: it asks for `text/html` and it is the
client most likely to be following a link somebody pasted. R4 gives that client `_format`, and this
server reads it as the override the specification makes it. `_format=json`,
`_format=application/json`, and `_format=application/fhir+json` - in any casing - make JSON
acceptable whatever `Accept` said, so a FHIR query is a URL that can be linked, mailed, and opened.
A `_format` naming anything else is refused even where `Accept` would have admitted JSON: the client
named the format it wants, and this server has only the one. An absent or blank `_format` says
nothing, and the header decides alone.

This applies to the FHIR surface, and to one route outside it. The facade API under `/facade` answers
plain `application/json` about this facade rather than resources out of it, `/cds-services` answers
plain JSON to an EHR, and the UI mounts serve a browser whose `Accept` is about HTML - none of those
is a FHIR interaction to negotiate. The exception is the tracked entity record at
`/facade/tracked-entities/{uid}/events`, which answers a FHIR Bundle from a facade-owned address and
carries this check as its own mount-time requirement - see `dhis2w_fhir_serve.routes.ServeRouters`.
"""

from __future__ import annotations

from starlette.requests import Request

from dhis2w_fhir_serve.errors import NotAcceptableError, UnsupportedFormatError

#: The header the negotiation reads, and the suffix every FHIR-flavoured JSON media type ends in.
ACCEPT_HEADER = "accept"
JSON_MEDIA_TYPE_SUFFIX = "+json"

#: R4's override for `Accept`, which every route screening its query parameters passes over.
FORMAT_PARAMETER = "_format"

#: The spellings of `_format` that ask for the one format this server answers in.
JSON_FORMAT_VALUES = frozenset({"json", "application/json", "application/fhir+json"})

#: The media ranges that admit anything, JSON included, whatever else the header goes on to name.
_WILDCARD_MEDIA_RANGES = frozenset({"*", "*/*", "application/*"})

#: The type half of every JSON media type this server could answer under.
_JSON_MEDIA_TYPE_PREFIX = "application"
_JSON_MEDIA_SUBTYPE = "json"


def accepts_json(accept: str | None) -> bool:
    """Whether one `Accept` header admits a JSON body - an absent or empty one always does."""
    if accept is None or not accept.strip():
        return True
    for stated in accept.split(","):
        media_range = stated.split(";")[0].strip().lower()
        if media_range in _WILDCARD_MEDIA_RANGES:
            return True
        media_type, _, subtype = media_range.partition("/")
        if media_type != _JSON_MEDIA_TYPE_PREFIX:
            continue
        if subtype == _JSON_MEDIA_SUBTYPE or subtype.endswith(JSON_MEDIA_TYPE_SUFFIX):
            return True
    return False


def format_asks_for_json(stated_format: str) -> bool:
    """Whether one `_format` value names the format this server answers in - casing is not read.

    A space is read as the `+` it was: `?_format=application/fhir+json` is how the media type is
    written everywhere a reader meets it, and a query string decodes an unescaped `+` to a space.
    Refusing the spelling every FHIR document uses would make the parameter unusable by hand.
    """
    return stated_format.strip().lower().replace(" ", "+") in JSON_FORMAT_VALUES


async def require_json_is_acceptable(request: Request) -> None:
    """Refuse a FHIR interaction that asks for a format this server does not answer in.

    `_format` is read first because R4 makes it the override: a value naming JSON settles the
    negotiation on its own, and a value naming anything else is refused whatever the header says.
    """
    stated_format = request.query_params.get(FORMAT_PARAMETER)
    if stated_format is not None and stated_format.strip():
        if not format_asks_for_json(stated_format):
            raise UnsupportedFormatError(stated_format)
        return
    accept = request.headers.get(ACCEPT_HEADER)
    if not accepts_json(accept):
        raise NotAcceptableError(accept or "")

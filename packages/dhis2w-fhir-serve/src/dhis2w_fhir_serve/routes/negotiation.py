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

This applies to the FHIR surface only. `/spool`, `/uiconfig`, and the enrollment listing answer
plain `application/json` about this facade rather than resources out of it, and the UI mounts serve
a browser whose `Accept` is about HTML - none of the three is a FHIR interaction to negotiate.
"""

from __future__ import annotations

from starlette.requests import Request

from dhis2w_fhir_serve.errors import NotAcceptableError

#: The header the negotiation reads, and the suffix every FHIR-flavoured JSON media type ends in.
ACCEPT_HEADER = "accept"
JSON_MEDIA_TYPE_SUFFIX = "+json"

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


async def require_json_is_acceptable(request: Request) -> None:
    """Refuse a FHIR interaction whose `Accept` rules out the one format this server answers in."""
    accept = request.headers.get(ACCEPT_HEADER)
    if not accepts_json(accept):
        raise NotAcceptableError(accept or "")

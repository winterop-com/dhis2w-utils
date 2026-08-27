"""A typed async client for a `d2w fhir serve` facade: read it, fill a form, submit a capture, evaluate an expression.

This client is hand-written against the routes `dhis2w_fhir_serve.routes` mounts. The base URL is a
FHIR endpoint whose contract is the CapabilityStatement at `/metadata` and which publishes no OpenAPI
document at all, so a generated client was never on offer for the surface most of these methods read.
The facade's own API under `/facade` does publish one, at `/facade/openapi.json` - it is the contract
to read when writing against those endpoints directly, and `evaluate` below is this client's one
method that calls them. Every method here answers a model rather than a parsed document, and every
refusal arrives as a `FacadeError` carrying the `OperationOutcome` the facade stated its reason in.

WHAT THIS IS FOR. An integrator holding a filled form wants three lines, not a request builder:
construct a `FacadeClient`, hand `submit_response` the document, read the receipt id off what comes
back. `generate` and `read_response` close that loop, so a caller can prove a form is answerable
before writing a line of form-filling code - `$generate` output is postable at the same server,
unchanged, which is the invariant that operation exists for.

THE ID IS NOT IN THE BODY. R4 says a `create` answers an `OperationOutcome`, so the identity of an
accepted submission is the last segment of the `Location` header and the body is the server saying
what it did. `CaptureReceipt` carries both, which is why `submit_response` answers a receipt rather
than the `OperationOutcome` on its own: a caller reading only the body would find no id on any
capture the facade ever accepts.

A RECEIPT IS NOT A DHIS2 WRITE. A 201 means the facade understood the submission, checked it against
the published form, and wrote it to disk durably. Nothing has reached DHIS2 - `d2w fhir forward` is
what drains the queue into an instance, and until it runs the receipt is a promise about bytes the
facade is holding.

THE EVALUATION SHAPES ARE MIRRORED, NOT IMPORTED. `POST /facade/evaluate` is the facade's own endpoint
and its request and response models are defined in `dhis2w_fhir_serve.evaluation` and
`dhis2w_fhir_serve.routes.evaluate`, which this package cannot import: `dhis2w-fhir-serve` depends on
`dhis2w-fhir`, so the arrow points one way only. `EvaluationRequest`, `EvaluationOutcome`, and the
three context shapes below mirror those definitions field for field, and those two modules are the
source of truth for them.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from enum import StrEnum
from types import TracebackType
from typing import Annotated, Any, Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from dhis2w_fhir.r4 import (
    DEFAULT_SUBJECT_RESOURCE_TYPE,
    Bundle,
    CapabilityStatement,
    FhirBase,
    JsonResource,
    OperationOutcome,
    OperationOutcomeIssue,
    QuestionnaireResponse,
    json_resource,
)

__all__ = [
    "BASIC_SCHEME",
    "BEARER_SCHEME",
    "DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME",
    "FACADE_API_PATH",
    "FHIR_JSON_MEDIA_TYPE",
    "BearerToken",
    "CaptureReceipt",
    "DiagnosticKind",
    "EvaluationContext",
    "EvaluationDiagnostic",
    "EvaluationLanguage",
    "EvaluationOutcome",
    "EvaluationRequest",
    "EvaluationResult",
    "FacadeClient",
    "FacadeCredential",
    "FacadeError",
    "InlineResourceContext",
    "PersonalAccessToken",
    "RegisteredEntityContext",
    "ResourceQuery",
    "StoredResourceContext",
    "UsernamePassword",
]

#: What the facade answers every FHIR route with, and the only media type its capture route reads.
FHIR_JSON_MEDIA_TYPE = "application/fhir+json"

#: What the facade's own routes under the mount below answer, which is not FHIR.
JSON_MEDIA_TYPE = "application/json"

#: Where the facade's own API is mounted, beside the FHIR base URL this client otherwise reads.
#:
#: The FHIR surface is at the base URL and its contract is `/metadata`; the receipts, the settings,
#: the caller, the evaluator, and the vocabularies are a different API under this prefix, described
#: by its own OpenAPI document at `{base}/facade/openapi.json`. `dhis2w_fhir_serve.routes` spells the
#: same string as the path its sub-application is mounted at.
FACADE_API_PATH = "/facade"

#: The `Authorization` scheme the `token` and `jwt` postures take, spelled as `dhis2w_fhir_serve.auth` spells it.
BEARER_SCHEME = "Bearer"

#: The scheme the `dhis2` posture takes for a username and a password.
#:
#: That posture CHALLENGES with `xBasic` rather than `Basic`, deliberately - a browser meeting a
#: `Basic` challenge on a `fetch` opens its own credential dialog and never hands the response back
#: to the page. The scheme a caller SENDS is untouched, so this is what goes on the request.
BASIC_SCHEME = "Basic"

#: The scheme the `dhis2` posture takes for a DHIS2 personal access token, which is DHIS2's own spelling.
DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME = "ApiToken"

#: The resource type a capture is submitted as and a receipt is read back from.
_QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE = "QuestionnaireResponse"

#: The resource type a form is published as, which is what `$generate` is invoked on.
_QUESTIONNAIRE_RESOURCE_TYPE = "Questionnaire"

#: The search parameter a canonical url is looked up by, on every conformance type the facade serves.
_CANONICAL_SEARCH_PARAMETER = "url"

#: The severity the facade states its "stored response {id}" line at, which is the one issue that is not a warning.
_INFORMATION_SEVERITY = "information"

#: The lowest status code that is a refusal rather than an answer.
_FIRST_REFUSAL_STATUS = 400


class FacadeCredential(BaseModel):
    """What a caller presents to a guarded facade, as the one `Authorization` value it becomes.

    The facade runs under one of four postures - `none`, `token`, `dhis2`, `jwt` - and three of them
    read a credential. A subclass exists per scheme rather than per posture, because `token` and
    `jwt` both take a bearer token and differ only in who minted it, which is the server's business
    and not the caller's.
    """

    model_config = ConfigDict(frozen=True)

    def authorization(self) -> str:
        """The `Authorization` header value this credential becomes."""
        raise NotImplementedError


class BearerToken(FacadeCredential):
    """A token the `token` posture holds in `D2W_FHIR_SERVE_TOKENS`, or one the `jwt` posture's issuer minted."""

    token: str

    def authorization(self) -> str:
        """`Bearer <token>`."""
        return f"{BEARER_SCHEME} {self.token}"


class UsernamePassword(FacadeCredential):
    """DHIS2 credentials the `dhis2` posture replays against `GET /api/me` on the instance it reads."""

    username: str
    password: str

    def authorization(self) -> str:
        """`Basic <base64 of username:password>`."""
        encoded = base64.b64encode(f"{self.username}:{self.password}".encode()).decode("ascii")
        return f"{BASIC_SCHEME} {encoded}"


class PersonalAccessToken(FacadeCredential):
    """A DHIS2 personal access token, which the `dhis2` posture replays exactly as `dhis2w-client` sends it."""

    token: str

    def authorization(self) -> str:
        """`ApiToken <token>`."""
        return f"{DHIS2_PERSONAL_ACCESS_TOKEN_SCHEME} {self.token}"


class FacadeError(Exception):
    """Raised when the facade refuses a request, carrying the `OperationOutcome` it refused with.

    Every refusal this facade makes renders as an `OperationOutcome` - `register_error_handlers`
    wires that for the whole application, so a 404 on a resource and a 400 on a search parameter
    arrive in the same shape. A capture refused at 400 or 422 carries one issue per thing wrong with
    the submission, which is why `issues` is a tuple and not one value.

    A connection that never reached the facade is not this: httpx's own `TransportError` passes
    through untouched, because a server that did not answer stated no outcome to carry.
    """

    def __init__(
        self,
        status_code: int,
        method: str,
        url: str,
        outcome: OperationOutcome | None,
        body_text: str,
    ) -> None:
        """Capture the status, the request that drew it, and the outcome the facade answered with."""
        self.status_code = status_code
        self.method = method
        self.url = url
        self.outcome = outcome
        self.body_text = body_text
        stated = self.diagnostics or body_text.strip() or "no body"
        super().__init__(f"{method} {url} was refused with {status_code}: {stated}")

    @property
    def issues(self) -> tuple[OperationOutcomeIssue, ...]:
        """Every issue the refusal named, empty when the body carried no `OperationOutcome`."""
        if self.outcome is None or self.outcome.issue is None:
            return ()
        return tuple(self.outcome.issue)

    @property
    def diagnostics(self) -> str:
        """Every issue's own words, joined - what to print when one line has to say why."""
        return "; ".join(issue.diagnostics for issue in self.issues if issue.diagnostics)


class CaptureReceipt(BaseModel):
    """What an accepted submission answers: where the receipt lives, and what the facade noted about it.

    `response_id` is the last segment of `Location` rather than anything in the body, because the
    body is an `OperationOutcome` and carries no id. `note` is the server's own "stored response
    {id}; a stored response is the submission as received" line, and `warnings` is every other issue
    the answer carried - a submission can be accepted and still have something worth saying about it.
    """

    model_config = ConfigDict(frozen=True)

    response_id: str
    """The id the receipt is served from, which `read_response` reads it back by."""

    location: str
    """The absolute url the facade said the receipt lives at, verbatim from the `Location` header."""

    note: str | None = None
    """The informational issue the facade always answers with, saying what it stored."""

    warnings: tuple[OperationOutcomeIssue, ...] = ()
    """Everything else the answer carried - accepted, and worth reading."""

    outcome: OperationOutcome
    """The whole answer, for a caller that wants the issues in the order they were stated."""


class ResourceQuery(BaseModel):
    """The search parameters this facade answers, named rather than spelled.

    The facade honours a small, fixed set and treats the rest two different ways: a store search
    IGNORES a parameter it does not know, and a register search REFUSES one. So a free-form mapping
    of query parameters is a quiet way to get the wrong answer on one route and a 400 on the other,
    and this model can only express something the facade actually reads.

    Not every parameter answers on every type. `_id`, `url`, and `identifier` answer on the eleven
    conformance types; `QuestionnaireResponse` answers `_id` and `questionnaire` and is paged;
    the live register types answer `identifier`, `_tag`, `d2-attribute`, and `_content`.

    Several values in one field are sent comma-separated, which is how the facade spells OR within
    one parameter. A value carrying a comma of its own cannot be expressed that way.
    """

    model_config = ConfigDict(frozen=True)

    ids: tuple[str, ...] = ()
    """`_id` - the resource ids to match."""

    urls: tuple[str, ...] = ()
    """`url` - the canonical urls to match, on the conformance types that declare it."""

    identifiers: tuple[str, ...] = ()
    """`identifier` - `system|value` tokens; a bare value matches any system."""

    questionnaire: str | None = None
    """`questionnaire` - the form canonical a receipt answers, matched exactly."""

    tags: tuple[str, ...] = ()
    """`_tag` - a register search's tag filter."""

    attribute_filters: tuple[str, ...] = ()
    """`d2-attribute` - a register search's DHIS2 tracked entity attribute filter."""

    text: str | None = None
    """`_content` - free-text search, answerable only where the projection backend is configured."""

    count: int | None = None
    """`_count` - a cap on the entries returned, not a page size; `Bundle.total` stays the whole set."""

    page: str | None = None
    """`page` - an opaque cursor the server minted; compose one only by following a Bundle's `next` link."""

    def to_query_parameters(self) -> tuple[tuple[str, str], ...]:
        """This query as the parameter pairs the facade reads, omitting everything left unset."""
        pairs: list[tuple[str, str]] = []
        for name, values in (
            ("_id", self.ids),
            (_CANONICAL_SEARCH_PARAMETER, self.urls),
            ("identifier", self.identifiers),
            ("_tag", self.tags),
            ("d2-attribute", self.attribute_filters),
        ):
            if values:
                pairs.append((name, ",".join(values)))
        for name, value in (("questionnaire", self.questionnaire), ("_content", self.text), ("page", self.page)):
            if value is not None:
                pairs.append((name, value))
        if self.count is not None:
            pairs.append(("_count", str(self.count)))
        return tuple(pairs)


class EvaluationLanguage(StrEnum):
    """Which of the three languages a source is written in - mirrors `dhis2w_fhir_serve.evaluation`."""

    FHIRPATH = "fhirpath"
    CQL = "cql"
    ELM = "elm"


class DiagnosticKind(StrEnum):
    """Whether the source never parsed, or parsed and then refused to run."""

    PARSE = "parse"
    EVALUATION = "evaluation"


class StoredResourceContext(BaseModel):
    """Evaluate over a resource the facade already holds, named by type and id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["stored"] = "stored"
    resource_type: str
    resource_id: str


class InlineResourceContext(BaseModel):
    """Evaluate over a resource carried in the request itself - the expression is checked against exactly it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["inline"] = "inline"
    resource: JsonResource

    @classmethod
    def over(cls, resource: FhirBase | Mapping[str, Any]) -> InlineResourceContext:
        """Evaluate over this resource, whether the caller holds a typed R4 model or a parsed document.

        The field itself is a `JsonResource`, because that is what goes on the wire. This is the
        constructor a caller reaches for: an integrator holding a `QuestionnaireResponse` and one
        holding the document they just parsed are both one call from an evaluation.
        """
        if isinstance(resource, FhirBase):
            return cls(resource=json_resource(resource))
        return cls(resource=JsonResource.model_validate(dict(resource)))


class RegisteredEntityContext(BaseModel):
    """Evaluate over a person the live register holds, named by their DHIS2 tracked entity uid."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["registered"] = "registered"
    resource_type: str = DEFAULT_SUBJECT_RESOURCE_TYPE
    tracked_entity_uid: str


EvaluationContext = Annotated[
    StoredResourceContext | InlineResourceContext | RegisteredEntityContext,
    Field(discriminator="kind"),
]
"""What an evaluation runs over, discriminated on `kind` exactly as the facade discriminates it."""


class EvaluationRequest(BaseModel):
    """One evaluation as a caller asks for it - mirrors `dhis2w_fhir_serve.routes.evaluate.EvaluationRequest`."""

    model_config = ConfigDict(frozen=True)

    language: EvaluationLanguage
    source: str
    """The FHIRPath expression, the CQL library text, or the ELM library as JSON."""

    expression_name: str | None = None
    """Which define to answer. Omitted, a CQL or ELM library answers every define it declares."""

    context: EvaluationContext | None = None
    """The resource to evaluate over. Omitted, the expression runs over no resource at all."""


class EvaluationDiagnostic(BaseModel):
    """One thing that stopped the run, at the position the parser stated one."""

    model_config = ConfigDict(frozen=True)

    kind: DiagnosticKind
    message: str
    line: int | None = None
    column: int | None = None
    """The column on that line, counted from one."""

    expression_name: str | None = None
    """The define this diagnostic is about, for a name the library does not declare."""


class EvaluationResult(BaseModel):
    """What one expression or one define answered, as JSON.

    `values` is always a collection, because FHIRPath answers collections and a CQL define answering
    a single value is that value carried as one. An empty collection is an answer - the expression
    matched nothing - and is not the same state as a refusal.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """The define this row answers, or `expression` for a FHIRPath collection."""

    values: tuple[JsonValue, ...] = ()
    refusal: str | None = None
    """Why this one define answered nothing, when the rest of the library still answered."""


class EvaluationOutcome(BaseModel):
    """One evaluation, whole: what it answered, what it declares, and what stopped it.

    A source that will not parse is a 200 carrying a diagnostic, never a refusal - which is why
    `evaluate` answers this rather than raising on a bad expression. `FacadeError` is reserved for a
    request the facade cannot serve at all: a stored resource it does not hold, a register it does
    not publish.
    """

    model_config = ConfigDict(frozen=True)

    language: EvaluationLanguage
    results: tuple[EvaluationResult, ...] = ()
    diagnostics: tuple[EvaluationDiagnostic, ...] = ()
    definitions: tuple[str, ...] = ()
    """Every define the library declares, in declaration order - empty for FHIRPath, which has none."""


class FacadeClient:
    """A typed async client for one `d2w fhir serve` facade.

    Use it as an async context manager and it owns its connection pool; hand it an
    `httpx.AsyncClient` and it borrows that one, leaving it open at exit - which is what a caller
    pooling several clients, or a test driving the application in-process, wants.

    Every request carries `Accept: application/fhir+json`, except `POST /facade/evaluate`, which is
    on the facade's own API rather than the FHIR surface and answers plain JSON. Every non-2xx raises
    `FacadeError`.
    """

    def __init__(
        self,
        base_url: str,
        *,
        auth: FacadeCredential | None = None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Point a client at a facade, optionally with a credential and a pool to borrow."""
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = timeout
        self._borrowed_http_client = http_client
        self._http_client = http_client
        self._capability: CapabilityStatement | None = None

    @property
    def base_url(self) -> str:
        """The facade this client talks to, without a trailing slash."""
        return self._base_url

    async def __aenter__(self) -> Self:
        """Open the connection pool, unless one was handed in."""
        self._open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the pool this client opened."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the pool this client opened; a pool the caller supplied is left for the caller to close."""
        if self._borrowed_http_client is not None or self._http_client is None:
            return
        await self._http_client.aclose()
        self._http_client = None

    async def capability(self, *, refresh: bool = False) -> CapabilityStatement:
        """The facade's `/metadata` - its only contract, read once and held unless `refresh` asks again."""
        if self._capability is None or refresh:
            answered = await self._request("GET", "/metadata")
            self._capability = CapabilityStatement.model_validate(answered.json())
        return self._capability

    async def read(self, resource_type: str, resource_id: str) -> JsonResource:
        """One resource by type and id, carried as the document the facade served.

        A stored resource is answered verbatim, so which keys it has is the document's business
        rather than this client's - `JsonResource` keeps every one of them. `read_response` is the
        typed path for the one type a caller reads back most.
        """
        answered = await self._request("GET", f"/{resource_type}/{resource_id}")
        return JsonResource.model_validate(answered.json())

    async def read_response(self, response_id: str) -> QuestionnaireResponse:
        """One receipt by id - the submission exactly as it arrived, not a view of anything DHIS2 holds."""
        answered = await self._request("GET", f"/{_QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}/{response_id}")
        return QuestionnaireResponse.model_validate(answered.json())

    async def search(self, resource_type: str, query: ResourceQuery | None = None) -> Bundle:
        """One searchset Bundle for a resource type.

        `Bundle.total` is the whole match set and `entry` is what this request asked for, so a
        capped search answers a total larger than the entries it carries.
        """
        parameters = (query or ResourceQuery()).to_query_parameters()
        answered = await self._request("GET", f"/{resource_type}", params=parameters)
        return Bundle.model_validate(answered.json())

    async def resolve(self, canonical: str) -> JsonResource | None:
        """The one resource a canonical url names, looked for across every type that declares `url`.

        A canonical says what a resource is without saying where it lives, so resolving one means
        asking each type in turn. `None` is an answer: this facade publishes nothing under that url.
        """
        for resource_type in await self.canonical_resource_types():
            bundle = await self.search(resource_type, ResourceQuery(urls=(canonical,), count=1))
            for entry in bundle.entry or ():
                if entry.resource is not None:
                    return entry.resource
        return None

    async def canonical_resource_types(self) -> tuple[str, ...]:
        """Every resource type this facade's `/metadata` declares a `url` search parameter on.

        Read off the CapabilityStatement rather than hard-coded, because the facade lists a type only
        when its store actually holds instances of it - a project publishing no ConceptMap does not
        declare one, and `resolve` should not ask.
        """
        capability = await self.capability()
        declared: list[str] = []
        for rest in capability.rest or ():
            for resource in rest.resource or ():
                searches_by_canonical = any(
                    parameter.name == _CANONICAL_SEARCH_PARAMETER for parameter in resource.searchParam or ()
                )
                if resource.type is not None and searches_by_canonical:
                    declared.append(resource.type)
        return tuple(declared)

    async def generate(self, questionnaire_id: str, *, seed: int | None = None) -> QuestionnaireResponse:
        """A filled draft answering one published form, against that form's own rules.

        `seed` makes the draft byte-reproducible. What comes back is postable to `submit_response`
        unchanged, which is the invariant this operation exists for.
        """
        parameters = (("seed", str(seed)),) if seed is not None else None
        path = f"/{_QUESTIONNAIRE_RESOURCE_TYPE}/{questionnaire_id}/$generate"
        answered = await self._request("GET", path, params=parameters)
        return QuestionnaireResponse.model_validate(answered.json())

    async def submit_response(
        self,
        questionnaire_response: QuestionnaireResponse | Mapping[str, Any],
    ) -> CaptureReceipt:
        """Submit one filled form and answer the receipt the facade handed back.

        Takes a model or a parsed document, because an integrator holding either should be one call
        away. A submission the facade will not accept raises `FacadeError` carrying one issue per
        thing wrong with it, which is what a capture screen renders.
        """
        answered = await self._request(
            "POST",
            f"/{_QUESTIONNAIRE_RESPONSE_RESOURCE_TYPE}",
            content_type=FHIR_JSON_MEDIA_TYPE,
            content=_capture_payload(questionnaire_response),
        )
        return _receipt(answered)

    async def evaluate(
        self,
        language: EvaluationLanguage | str,
        source: str,
        *,
        expression_name: str | None = None,
        context: StoredResourceContext | InlineResourceContext | RegisteredEntityContext | None = None,
    ) -> EvaluationOutcome:
        """Evaluate one FHIRPath expression, CQL library, or compiled ELM library against this facade.

        A source that will not parse answers an outcome carrying the line and column the parser
        stopped on - it does not raise. `FacadeError` means the facade could not serve the request
        at all, which is a different thing from an expression it could not run.
        """
        request = EvaluationRequest(
            language=EvaluationLanguage(language),
            source=source,
            expression_name=expression_name,
            context=context,
        )
        answered = await self._request(
            "POST",
            f"{FACADE_API_PATH}/evaluate",
            accept=JSON_MEDIA_TYPE,
            content_type=JSON_MEDIA_TYPE,
            content=request.model_dump_json(exclude_none=True).encode(),
        )
        return EvaluationOutcome.model_validate(answered.json())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        accept: str = FHIR_JSON_MEDIA_TYPE,
        content_type: str | None = None,
        params: tuple[tuple[str, str], ...] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        """One request against the facade, raising `FacadeError` on anything that is not an answer."""
        http_client = self._open()
        answered = await http_client.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers(accept, content_type),
            params=params,
            content=content,
        )
        if answered.status_code >= _FIRST_REFUSAL_STATUS:
            raise _refusal(method, f"{self._base_url}{path}", answered)
        return answered

    def _headers(self, accept: str, content_type: str | None) -> dict[str, str]:
        """The headers every request carries: what it accepts, what it sends, and who is sending it."""
        headers = {"Accept": accept}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if self._auth is not None:
            headers["Authorization"] = self._auth.authorization()
        return headers

    def _open(self) -> httpx.AsyncClient:
        """The pool to send on, opened on first use when the caller supplied none."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client


def _capture_payload(questionnaire_response: QuestionnaireResponse | Mapping[str, Any]) -> bytes:
    """One submission as the bytes the facade reads, whether the caller held a model or a parsed document."""
    if isinstance(questionnaire_response, QuestionnaireResponse):
        return questionnaire_response.model_dump_json(exclude_none=True, by_alias=True).encode()
    return json.dumps(dict(questionnaire_response)).encode()


def _receipt(answered: httpx.Response) -> CaptureReceipt:
    """Read an accepted capture's answer: the id off the header, the note and the warnings off the body."""
    outcome = OperationOutcome.model_validate(answered.json())
    issues = tuple(outcome.issue or ())
    location = answered.headers.get("location", "")
    note = next((issue.diagnostics for issue in issues if issue.severity == _INFORMATION_SEVERITY), None)
    return CaptureReceipt(
        response_id=location.rsplit("/", 1)[-1],
        location=location,
        note=note,
        warnings=tuple(issue for issue in issues if issue.severity != _INFORMATION_SEVERITY),
        outcome=outcome,
    )


def _refusal(method: str, url: str, answered: httpx.Response) -> FacadeError:
    """Build the error one refusal becomes, parsing the OperationOutcome the facade stated it in."""
    return FacadeError(answered.status_code, method, url, _parse_outcome(answered), answered.text)


def _parse_outcome(answered: httpx.Response) -> OperationOutcome | None:
    """The `OperationOutcome` a refusal carried, or None when the body was not one.

    The facade answers one for every refusal it makes itself, but a proxy in front of it, or a
    gateway that never reached it, answers whatever it answers - so this never assumes the shape.
    """
    try:
        body = answered.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("resourceType") != "OperationOutcome":
        return None
    try:
        return OperationOutcome.model_validate(body)
    except ValidationError:
        return None

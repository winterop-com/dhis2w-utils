"""`POST /$evaluate` - the same evaluation as `/facade/evaluate`, answered as the `Parameters` resource FHIR asks for.

THE ADDRESS IS SYSTEM-LEVEL, because what is evaluated is not one resource type's business. FHIR
spells an operation at the service base `[base]/$op`, and this one runs over whatever the request
names as its context - a published Questionnaire, a posted Bundle, one tracked entity of the
register - so no resource type owns it. It rides one segment beginning with `$`, which no PascalCase
resource type can shadow, and mounts ahead of the read catch-alls for the reason
`dhis2w_fhir_serve.routes.translate` states: `/{resource_type}` matches `/$evaluate` just as happily.

THE ANSWER FOLLOWS THE CQL-ON-FHIR CONVENTION. Clinical Reasoning's `Library/$evaluate` and the
CPG-on-FHIR `$cql` operation both answer one `Parameters` whose parameters are the defines the
library declared, and both take the source and the data to run it over as parameters in. This is
that shape over this facade's three languages: one parameter per define, named by the define;
`value[x]` where the define answered one primitive; `resource` where it answered a FHIR resource;
one `part` per value where it answered several; and an `OperationOutcome` part where it refused.
What stopped the whole run - an expression that would not parse, a define the library does not
declare - is the `outcome` parameter, an OperationOutcome whose issue carries the line and column
the parser stopped on.

A DEFINE THAT MATCHED NOTHING IS ABSENT, and that is FHIR's own answer rather than a fact thrown
away. FHIR has no empty collection: a value is present or the element is not there, which
`dhis2w_fhir_engine.r4.resources` states as the rule every model here is built on. `POST /facade/evaluate`
keeps the distinction between "matched nothing" and "was not run", because its own shape can carry
it; this one cannot, and inventing a spelling for it would be this server writing FHIR nobody else
reads.

PARAMETERS IN IS CANONICAL, AND THE PLAIN JSON BODY IS ALSO READ. An operation's input is a
`Parameters` resource and that is what this address documents, but the same body `/facade/evaluate` takes is
accepted here too - the two endpoints run the same evaluation over the same three contexts, and
making a caller rewrite a body to change which shape comes back would be a difference about nothing.
Which one arrived is decided by `resourceType`, and nothing else about the request changes.

A BAD EXPRESSION IS 200 HERE TOO. `dhis2w_fhir_serve.routes.evaluate` argues that posture in full: a
request this facade cannot serve at all is an OperationOutcome with a 4xx status, and everything a
person's typing can do wrong is an answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dhis2w_fhir.r4 import (
    JsonResource,
    OperationOutcome,
    OperationOutcomeIssue,
    Parameters,
    ParametersParameter,
    json_resource,
)
from fastapi import APIRouter
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from dhis2w_fhir_serve.errors import FHIR_JSON_MEDIA_TYPE, BadOperationError, IssueCode
from dhis2w_fhir_serve.evaluation import DiagnosticKind, EvaluationLanguage, EvaluationOutcome, evaluate_source
from dhis2w_fhir_serve.routes.evaluate import (
    EvaluationContext,
    EvaluationRequest,
    InlineResourceContext,
    RegisteredEntityContext,
    StoredResourceContext,
    evaluation_subject,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import JsonValue

    from dhis2w_fhir_serve.evaluation import EvaluationDiagnostic, EvaluationResult

#: Where the operation is answered. `capability.py` declares it as a system-level `rest.operation`.
EVALUATE_OPERATION_PATH = "/$evaluate"

#: The resource type an operation's input arrives as, which is what tells the two bodies apart.
PARAMETERS_RESOURCE_TYPE = "Parameters"

#: The input parameters, named the way the `/facade/evaluate` body names its fields.
LANGUAGE_PARAMETER = "language"
SOURCE_PARAMETER = "source"
EXPRESSION_PARAMETER = "expression"
CONTEXT_PARAMETER = "context"

#: The parts of the `context` parameter: which kind of context it is, and the one resource it names.
KIND_PART = "kind"
RESOURCE_TYPE_PART = "resourceType"
RESOURCE_ID_PART = "resourceId"
RESOURCE_PART = "resource"
TRACKED_ENTITY_UID_PART = "trackedEntityUid"

#: What one value of a define answering several is named, since only the define itself has a name.
VALUE_PART = "value"

#: What an OperationOutcome rides under, both as a define's refusal and as the whole run's diagnostics.
OUTCOME_PARAMETER = "outcome"

#: The R4 issue codes the two diagnostic kinds are stated as: source that would not parse is invalid
#: content, and a library that parsed and then refused is a processing issue.
PARSE_ISSUE_CODE: IssueCode = "invalid"
EVALUATION_ISSUE_CODE: IssueCode = "processing"

router = APIRouter()


@router.post(EVALUATE_OPERATION_PATH)
async def evaluate_operation(request: Request) -> Response:
    """Evaluate one source over one resource, answering the defines as a `Parameters` resource.

    The evaluation runs off the event loop for the reason `POST /facade/evaluate` does: parsing a grammar
    and walking an expression tree is blocking, CPU-bound work, and a facade doing it inline would
    stall every other request it is serving.
    """
    asked = await _asked(request)
    subject = await evaluation_subject(request, asked.context)
    outcome = await run_in_threadpool(evaluate_source, asked.language, asked.source, subject, asked.expression_name)
    return Response(
        content=evaluation_parameters(outcome).model_dump_json(exclude_none=True, by_alias=True),
        media_type=FHIR_JSON_MEDIA_TYPE,
    )


def evaluation_ask(parameters: Parameters) -> EvaluationRequest:
    """Read one `Parameters` input into the evaluation it asks for, refusing a body that names none.

    `language` and `source` are required, because an evaluation with neither is not a narrower
    question - it is no question. `expression` names one define, and `context` names the one resource
    the expression may reach; both are optional and both mean here exactly what they mean in the
    `/facade/evaluate` body.
    """
    stated = parameters.parameter or []
    language = _language(_text(stated, LANGUAGE_PARAMETER))
    source = _text(stated, SOURCE_PARAMETER)
    if source is None:
        raise BadOperationError(f"`$evaluate` needs a `{SOURCE_PARAMETER}` parameter carrying the source to evaluate")
    return EvaluationRequest(
        language=language,
        source=source,
        expression_name=_text(stated, EXPRESSION_PARAMETER),
        context=_context(_named(stated, CONTEXT_PARAMETER)),
    )


def evaluation_parameters(outcome: EvaluationOutcome) -> Parameters:
    """One evaluation as the `Parameters` a FHIR client reads: a parameter per define, and the outcome.

    A define that matched nothing carries no parameter, because FHIR has no empty collection. A
    define that refused carries its own OperationOutcome, so the rest of the library still answers.
    """
    answered = [stated for result in outcome.results if (stated := _result_parameter(result)) is not None]
    if outcome.diagnostics:
        answered.append(
            ParametersParameter(
                name=OUTCOME_PARAMETER,
                resource=json_resource(
                    OperationOutcome(issue=[_diagnostic_issue(diagnostic) for diagnostic in outcome.diagnostics])
                ),
            )
        )
    return Parameters(parameter=answered or None)


async def _asked(request: Request) -> EvaluationRequest:
    """The evaluation this request asks for, read from whichever of the two bodies arrived.

    The posted document never leaves this function: it is a `Parameters` or it is a `/facade/evaluate`
    request, and either way it is a model before anything else is done with it.
    """
    try:
        posted = await request.json()
    except ValueError as error:
        raise BadOperationError(f"`$evaluate` takes a JSON body, and this one did not parse: {error}") from error
    if not isinstance(posted, dict):
        raise BadOperationError(
            "`$evaluate` takes a Parameters resource naming `language` and `source`, or the same JSON body "
            "`POST /facade/evaluate` takes"
        )
    body: dict[str, Any] = posted
    try:
        if body.get("resourceType") == PARAMETERS_RESOURCE_TYPE:
            return evaluation_ask(Parameters.model_validate(body))
        return EvaluationRequest.model_validate(body)
    except ValidationError as error:
        raise BadOperationError(_unreadable(error)) from error


def _unreadable(error: ValidationError) -> str:
    """Say which part of a body this operation could not read, in one sentence rather than a stack of them."""
    first = error.errors()[0]
    where = ".".join(str(part) for part in first["loc"]) or "the body"
    return (
        f"`$evaluate` could not read this request at `{where}`: {first['msg']}. Post a Parameters resource "
        f"naming `{LANGUAGE_PARAMETER}` and `{SOURCE_PARAMETER}`, or the same JSON body `POST /facade/evaluate` takes"
    )


def _named(parameters: Sequence[ParametersParameter], name: str) -> ParametersParameter | None:
    """The first parameter of that name, or nothing - repeats are the caller's, and the first one wins."""
    return next((parameter for parameter in parameters if parameter.name == name), None)


def _text(parameters: Sequence[ParametersParameter], name: str) -> str | None:
    """One string-valued parameter, read as `valueString` or as `valueCode` - clients send both."""
    found = _named(parameters, name)
    if found is None:
        return None
    return found.valueString or found.valueCode


def _language(stated: str | None) -> EvaluationLanguage:
    """The language the source is written in, refusing a request that names none or names an unknown one."""
    named = ", ".join(f"`{language.value}`" for language in EvaluationLanguage)
    if stated is None:
        raise BadOperationError(f"`$evaluate` needs a `{LANGUAGE_PARAMETER}` parameter naming one of {named}")
    try:
        return EvaluationLanguage(stated)
    except ValueError as error:
        raise BadOperationError(f"`{stated}` is not a language this server evaluates; it evaluates {named}") from error


def _context(parameter: ParametersParameter | None) -> EvaluationContext | None:
    """The one resource an expression may reach, read from the `context` parameter's own parts.

    Three kinds and no fourth, refused by name the way the `/facade/evaluate` body's discriminated union
    refuses one: a request naming a kind this server does not offer never reaches the engine.
    """
    if parameter is None:
        return None
    parts = parameter.part or []
    kind = _text(parts, KIND_PART)
    if kind == "stored":
        return StoredResourceContext(
            resource_type=_required_part(parts, RESOURCE_TYPE_PART, kind),
            resource_id=_required_part(parts, RESOURCE_ID_PART, kind),
        )
    if kind == "inline":
        return InlineResourceContext(resource=_inline_resource(parts))
    if kind == "registered":
        return _registered_context(parts)
    named = ", ".join(f"`{offered}`" for offered in ("stored", "inline", "registered"))
    stated = "no kind" if kind is None else f"`{kind}`"
    raise BadOperationError(f"a `{CONTEXT_PARAMETER}` parameter names {stated}; this server offers {named}")


def _registered_context(parts: Sequence[ParametersParameter]) -> RegisteredEntityContext:
    """One tracked entity of the register, at the resource type the request named or the default one."""
    resource_type = _text(parts, RESOURCE_TYPE_PART)
    uid = _required_part(parts, TRACKED_ENTITY_UID_PART, "registered")
    if resource_type is None:
        return RegisteredEntityContext(tracked_entity_uid=uid)
    return RegisteredEntityContext(resource_type=resource_type, tracked_entity_uid=uid)


def _inline_resource(parts: Sequence[ParametersParameter]) -> dict[str, Any]:
    """The resource a request carried inline, as the FHIR-shaped JSON the engine evaluates over."""
    found = _named(parts, RESOURCE_PART)
    if found is None or found.resource is None:
        raise BadOperationError(
            f"an `inline` `{CONTEXT_PARAMETER}` needs a `{RESOURCE_PART}` part carrying the resource to evaluate over"
        )
    carried: dict[str, Any] = found.resource.model_dump(mode="json", exclude_none=True, by_alias=True)
    return carried


def _required_part(parts: Sequence[ParametersParameter], name: str, kind: str) -> str:
    """One part a context kind cannot be resolved without, refused as a bad request when it is absent."""
    stated = _text(parts, name)
    if not stated:
        raise BadOperationError(f"a `{kind}` `{CONTEXT_PARAMETER}` needs a `{name}` part")
    return stated


def _result_parameter(result: EvaluationResult) -> ParametersParameter | None:
    """One define as the parameter it answers with, or nothing where it matched nothing.

    One value rides the parameter itself - `value[x]` for a primitive, `resource` for a resource -
    because a client asking for one define wants the answer, not a wrapper around it. Several values
    ride one `part` apiece, since a parameter states one value and a define may answer a collection.
    """
    if result.refusal is not None:
        return ParametersParameter(name=result.name, part=[_refusal_part(result.refusal)])
    answers = [stated for value in result.values for stated in _parameters_for(VALUE_PART, value)]
    if not answers:
        return None
    if len(answers) == 1:
        return answers[0].model_copy(update={"name": result.name})
    return ParametersParameter(name=result.name, part=answers)


def _parameters_for(name: str, value: JsonValue) -> list[ParametersParameter]:
    """One evaluated value as the parameters that state it, which is a list because FHIR repeats names.

    A resource rides `resource`, an object nests one part per key it states, a list repeats the name
    once per item, and a primitive takes the `value[x]` its JSON type names. Anything that states
    nothing at all - a null, an empty list, an object whose every key is null - contributes no
    parameter, because a parameter carrying neither a value nor a part is not a parameter.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [stated for item in value for stated in _parameters_for(name, item)]
    if isinstance(value, dict):
        if "resourceType" in value:
            return [ParametersParameter(name=name, resource=JsonResource.model_validate(value))]
        parts = [stated for key, item in value.items() for stated in _parameters_for(str(key), item)]
        return [ParametersParameter(name=name, part=parts)] if parts else []
    return [_primitive(name, value)]


def _primitive(name: str, value: bool | int | float | str) -> ParametersParameter:
    """One JSON scalar as the `value[x]` R4 spells it with - `bool` before `int`, since it is one."""
    if isinstance(value, bool):
        return ParametersParameter(name=name, valueBoolean=value)
    if isinstance(value, int):
        return ParametersParameter(name=name, valueInteger=value)
    if isinstance(value, float):
        return ParametersParameter(name=name, valueDecimal=value)
    return ParametersParameter(name=name, valueString=value)


def _refusal_part(refusal: str) -> ParametersParameter:
    """One define's refusal, as the OperationOutcome part that keeps it beside the defines that answered."""
    return ParametersParameter(
        name=OUTCOME_PARAMETER,
        resource=json_resource(
            OperationOutcome(
                issue=[OperationOutcomeIssue(severity="error", code=EVALUATION_ISSUE_CODE, diagnostics=refusal)]
            )
        ),
    )


def _diagnostic_issue(diagnostic: EvaluationDiagnostic) -> OperationOutcomeIssue:
    """One thing that stopped the run, as an issue carrying the position the parser stated for it."""
    code = PARSE_ISSUE_CODE if diagnostic.kind is DiagnosticKind.PARSE else EVALUATION_ISSUE_CODE
    return OperationOutcomeIssue(severity="error", code=code, diagnostics=_diagnostic_text(diagnostic))


def _diagnostic_text(diagnostic: EvaluationDiagnostic) -> str:
    """What the diagnostic says, with the line and column spliced in where the parser stated one.

    The position is in the text because R4 has nowhere better for it: `issue.expression` is a
    FHIRPath into a resource, and where a CQL parser stopped is not that. Columns are counted from
    one, as `dhis2w_fhir_serve.evaluation` states.
    """
    if diagnostic.line is None or diagnostic.column is None:
        return diagnostic.message
    return f"line {diagnostic.line}, column {diagnostic.column}: {diagnostic.message}"

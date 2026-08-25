"""Running one FHIRPath expression, CQL library, or ELM library over one resource, and saying what happened.

This is the whole of what the facade knows about `dhis2w_fhir_engine`. The router above it decides
which resource the expression runs over and answers HTTP; this module takes that resource as
FHIR-shaped JSON, hands it to the engine, and turns whatever comes back - a collection, a value per
define, a parse failure, a refusal - into one typed answer. Nothing here imports FastAPI, so a
caller with a loaded store evaluates the same expression the endpoint evaluates, with no server
running.

THE SANDBOX IS CLOSED, AND THAT IS A PROPERTY OF THE CALLS THIS MODULE MAKES. The engine can read
libraries off disk - `CQLEvaluator(library_paths=...)` searches directories, and `ELMEvaluator.load`
treats a string that names an existing file as a file to open. Neither door is opened here: no
library path is ever passed, and ELM is parsed to a dict by this module before the engine is given
it, so a `source` naming `/etc/passwd` is JSON that will not parse rather than a file that will. The
only data an expression can reach is the resource the caller supplied. `FHIRHelpers 4.0.1` resolves
without any of that, because the engine carries it in memory.

A BAD EXPRESSION IS AN ANSWER, NOT A FAILURE. Every way a user-supplied expression can go wrong ends
in a diagnostic rather than an exception leaving this module: an expression that will not parse, a
library whose define refuses at evaluation time, a define asked for that the library does not
declare. That is why the running functions catch `Exception` rather than the engine's own error
class - the source is a person's typing, and a construct the evaluator half-supports must read as
"this expression did not work" rather than as a server that failed.

WHERE A REFUSAL LANDS, STATED ONCE. A refusal that belongs to one named define rides that define's
own row, in `EvaluationResult.refusal`, so the library's other defines still answer. A refusal that
stopped the whole run - nothing parsed, no library compiled, the named define does not exist - is a
diagnostic, because there is no row for it to ride.

COLUMNS ARE COUNTED FROM ONE. ANTLR reports the column of a syntax error counting from zero, which
is right for a parser and wrong for a person counting characters along a line. `EvaluationDiagnostic`
states the line as ANTLR gives it and the column one higher, so "line 2, column 14" names the
fourteenth character.

A PARSE MESSAGE NAMES WHAT WENT WRONG, NOT EVERY TOKEN THAT WOULD HAVE BEEN RIGHT. ANTLR ends a
mismatched-input message with the whole set it expected instead - dozens of quoted operators and
lexer rule names in capitals. A positioned diagnostic already points at the character, so that tail
is dropped and the naming half is kept.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any

from dhis2w_fhir_engine import CQLEvaluator, ELMEvaluator, FHIRPathEvaluator, unwrap_primitives
from dhis2w_fhir_engine.r4 import BundleDataSource
from pydantic import BaseModel, ConfigDict, JsonValue

#: What one FHIRPath collection is named in the results, since the expression has no define name.
FHIRPATH_RESULT_NAME = "expression"

#: The key `ELMEvaluator.evaluate_all_definitions` collects its per-define failures under.
ELM_ERRORS_KEY = "_errors"

#: How the engine's ANTLR listeners spell a syntax error, in both grammars: `line {line}:{column}`.
_SYNTAX_ERROR_PATTERN = re.compile(r"Syntax error at line (\d+):(\d+):\s*(.*)", re.DOTALL)

#: ANTLR's every-token-that-would-have-parsed tail: ` expecting {'+', '-', IDENTIFIER, ...}`.
_EXPECTED_TOKEN_SET_PATTERN = re.compile(r"\s*expecting\s*\{.*\}\s*$", re.DOTALL)

#: An empty collection Bundle, which is what a CQL retrieve reads when the caller supplied no data.
_EMPTY_BUNDLE: dict[str, Any] = {"resourceType": "Bundle", "type": "collection", "entry": []}

#: The resource type whose entries a CQL retrieve reads through rather than evaluating over.
_BUNDLE_RESOURCE_TYPE = "Bundle"


class EvaluationLanguage(StrEnum):
    """Which of the three languages a source is written in.

    They differ in what `source` holds and in what an answer looks like. `fhirpath` is one
    expression answering one collection; `cql` is a library whose every define answers a value;
    `elm` is that same library already compiled, as the JSON another compiler emitted.
    """

    FHIRPATH = "fhirpath"
    CQL = "cql"
    ELM = "elm"


class DiagnosticKind(StrEnum):
    """Whether the source never parsed, or parsed and then refused to run."""

    PARSE = "parse"
    EVALUATION = "evaluation"


class EvaluationDiagnostic(BaseModel):
    """One thing that stopped the run, at the position it happened where the parser stated one."""

    model_config = ConfigDict(frozen=True)

    kind: DiagnosticKind
    message: str
    """What the engine said, verbatim - including the token set a parser named as expected."""

    line: int | None = None
    """The line the parser stopped on, counted from one, or None for a refusal with no position."""

    column: int | None = None
    """The column on that line, counted from one - one higher than the zero-based column ANTLR gives."""

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

    Results and diagnostics are not exclusive. A library whose second define refuses still answers
    for its first, and a run that answered nothing at all carries the diagnostic saying why.
    """

    model_config = ConfigDict(frozen=True)

    language: EvaluationLanguage
    results: tuple[EvaluationResult, ...] = ()
    diagnostics: tuple[EvaluationDiagnostic, ...] = ()
    definitions: tuple[str, ...] = ()
    """Every define the library declares, in declaration order - empty for FHIRPath, which has none."""


def evaluate_source(
    language: EvaluationLanguage,
    source: str,
    subject: dict[str, Any] | None = None,
    expression_name: str | None = None,
) -> EvaluationOutcome:
    """Run one source in one language over one resource, answering results and diagnostics.

    `subject` is FHIR-shaped JSON because that is the engine's own argument type - it evaluates over
    documents rather than over models, and a model here would be one this facade parsed and the
    engine immediately re-read. A Bundle is used as the data a CQL retrieve reads through; any other
    resource is both the context resource and the one-entry collection a retrieve sees, so
    `[Patient]` answers over a Patient that was handed in on its own.

    `expression_name` narrows a CQL or ELM run to one define. FHIRPath has no defines and ignores it.

    This is blocking, CPU-bound work - parsing a grammar and walking a tree - so an async caller runs
    it off the event loop.
    """
    if language is EvaluationLanguage.FHIRPATH:
        return _run_fhirpath(source, subject)
    if language is EvaluationLanguage.CQL:
        return _run_cql(source, subject, expression_name)
    return _run_elm(source, subject, expression_name)


def json_safe(value: Any) -> JsonValue:
    """One evaluation result as JSON a browser can render, whatever Python object the engine answered.

    The engine answers in its own vocabulary - `CQLCode` and `CQLInterval` are Pydantic models,
    a date literal is a `datetime.date`, a decimal is a `Decimal` - and none of those cross HTTP as
    themselves. Anything with no JSON spelling of its own is rendered as the text `str()` gives it,
    which is the engine's own word for the value rather than a shape invented here.

    A float that is not finite is rendered as text for the same reason: `NaN` and `Infinity` are
    things JSON cannot say, and a body carrying them is a body a strict parser refuses.
    """
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, BaseModel):
        dumped: JsonValue = value.model_dump(mode="json", exclude_none=True)
        return dumped
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [json_safe(item) for item in value]
    return str(value)


def syntax_diagnostic(error: BaseException) -> EvaluationDiagnostic:
    """Read one engine exception as the diagnostic it is: a parse failure with a position, or a refusal.

    The position is looked for through the whole `__cause__` chain, because the FHIRPath evaluator
    wraps its listener's syntax error in a second exception naming the expression - so the line and
    column are one link down rather than on the exception the caller caught.
    """
    walked: BaseException | None = error
    while walked is not None:
        found = _SYNTAX_ERROR_PATTERN.search(str(walked))
        if found is not None:
            return EvaluationDiagnostic(
                kind=DiagnosticKind.PARSE,
                message=_without_expected_token_set(found.group(3)),
                line=int(found.group(1)),
                column=int(found.group(2)) + 1,
            )
        walked = walked.__cause__
    return EvaluationDiagnostic(kind=DiagnosticKind.EVALUATION, message=str(error))


def _without_expected_token_set(message: str) -> str:
    """One parse message without ANTLR's list of every token that would have parsed there.

    A positioned diagnostic already points at the character that went wrong, and the reader is
    looking at their own source beside it. The token set adds nothing they can act on and a lot they
    have to read past: three wrapped lines of quoted operators and lexer rule names in capitals,
    which is the parser generator's vocabulary rather than the language's. What stays is the half
    that names the problem - "mismatched input '<EOF>'", "no viable alternative at input '[Patient'".
    """
    return _EXPECTED_TOKEN_SET_PATTERN.sub("", message.strip()).strip()


def _run_fhirpath(source: str, subject: dict[str, Any] | None) -> EvaluationOutcome:
    """Evaluate one FHIRPath expression, answering the collection it matched."""
    try:
        matched = FHIRPathEvaluator().evaluate(source, subject)
    except Exception as error:  # A person's expression must never leave here as a server failure.
        return EvaluationOutcome(language=EvaluationLanguage.FHIRPATH, diagnostics=(syntax_diagnostic(error),))
    return EvaluationOutcome(
        language=EvaluationLanguage.FHIRPATH,
        results=(EvaluationResult(name=FHIRPATH_RESULT_NAME, values=_collection(unwrap_primitives(matched))),),
    )


def _run_cql(source: str, subject: dict[str, Any] | None, expression_name: str | None) -> EvaluationOutcome:
    """Compile one CQL library over the supplied data and evaluate its defines - one, or all of them."""
    evaluator = CQLEvaluator(data_source=BundleDataSource(_retrievable(subject)))
    try:
        library = evaluator.compile(source)
    except Exception as error:  # A library that does not compile is a diagnostic, not a 500.
        return EvaluationOutcome(language=EvaluationLanguage.CQL, diagnostics=(syntax_diagnostic(error),))
    declared = tuple(library.definitions)
    context_resource = _context_resource(subject)
    if expression_name is not None:
        return _one_define(
            EvaluationLanguage.CQL,
            expression_name,
            declared,
            lambda name: evaluator.evaluate_definition(name, resource=context_resource),
        )
    try:
        answered = evaluator.evaluate_all_definitions(resource=context_resource)
    except Exception as error:  # The whole library refusing is a diagnostic, not a server failure.
        return EvaluationOutcome(
            language=EvaluationLanguage.CQL, definitions=declared, diagnostics=(syntax_diagnostic(error),)
        )
    return EvaluationOutcome(language=EvaluationLanguage.CQL, definitions=declared, results=_rows(answered, declared))


def _run_elm(source: str, subject: dict[str, Any] | None, expression_name: str | None) -> EvaluationOutcome:
    """Load one ELM library from the JSON it was handed as, and evaluate its defines - one, or all of them.

    The JSON is parsed here rather than by the engine, which is what keeps the sandbox closed:
    `ELMEvaluator.load` opens a string that names an existing file, and a dict names nothing.
    """
    try:
        document = json.loads(source)
    except json.JSONDecodeError as error:
        return EvaluationOutcome(
            language=EvaluationLanguage.ELM,
            diagnostics=(
                EvaluationDiagnostic(
                    kind=DiagnosticKind.PARSE, message=error.msg, line=error.lineno, column=error.colno
                ),
            ),
        )
    if not isinstance(document, dict):
        return EvaluationOutcome(
            language=EvaluationLanguage.ELM,
            diagnostics=(
                EvaluationDiagnostic(
                    kind=DiagnosticKind.PARSE, message="an ELM library is a JSON object holding a `library` element"
                ),
            ),
        )
    evaluator = ELMEvaluator(data_source=BundleDataSource(_retrievable(subject)))
    try:
        library = evaluator.load(document)
    except Exception as error:  # An ELM document the loader will not read is a diagnostic.
        return EvaluationOutcome(language=EvaluationLanguage.ELM, diagnostics=(syntax_diagnostic(error),))
    declared = tuple(definition.name for definition in library.get_definitions())
    context_resource = _context_resource(subject)
    if expression_name is not None:
        return _one_define(
            EvaluationLanguage.ELM,
            expression_name,
            declared,
            lambda name: evaluator.evaluate_definition(name, resource=context_resource),
        )
    try:
        answered = evaluator.evaluate_all_definitions(resource=context_resource)
    except Exception as error:  # The whole library refusing is a diagnostic, not a server failure.
        return EvaluationOutcome(
            language=EvaluationLanguage.ELM, definitions=declared, diagnostics=(syntax_diagnostic(error),)
        )
    return EvaluationOutcome(
        language=EvaluationLanguage.ELM, definitions=declared, results=_elm_rows(answered, declared)
    )


def _one_define(
    language: EvaluationLanguage,
    expression_name: str,
    declared: tuple[str, ...],
    evaluate: Callable[[str], Any],
) -> EvaluationOutcome:
    """Evaluate the one define a caller named, or say that the library declares no such name.

    A name the library does not declare is a diagnostic rather than an empty row: an empty row would
    read as a define that answered nothing, which is a different and much more misleading fact.
    """
    if expression_name not in declared:
        return EvaluationOutcome(
            language=language,
            definitions=declared,
            diagnostics=(
                EvaluationDiagnostic(
                    kind=DiagnosticKind.EVALUATION,
                    message=f"this library declares no define named `{expression_name}`",
                    expression_name=expression_name,
                ),
            ),
        )
    try:
        answered = evaluate(expression_name)
    except Exception as error:  # One define refusing is that define's own answer, not the run's.
        return EvaluationOutcome(
            language=language,
            definitions=declared,
            results=(EvaluationResult(name=expression_name, refusal=str(error)),),
        )
    return EvaluationOutcome(
        language=language,
        definitions=declared,
        results=(EvaluationResult(name=expression_name, values=_collection(answered)),),
    )


def _rows(answered: dict[str, Any], declared: tuple[str, ...]) -> tuple[EvaluationResult, ...]:
    """One row per define, in declaration order, with a refused define carrying its own message.

    `CQLEvaluator.evaluate_all_definitions` answers a refusal by putting the exception in the
    dictionary rather than raising it, so a value that is an exception is this run's way of saying
    that one define did not work.
    """
    rows: list[EvaluationResult] = []
    for name in declared:
        if name not in answered:
            continue
        value = answered[name]
        if isinstance(value, BaseException):
            rows.append(EvaluationResult(name=name, refusal=str(value)))
            continue
        rows.append(EvaluationResult(name=name, values=_collection(value)))
    return tuple(rows)


def _elm_rows(answered: dict[str, Any], declared: tuple[str, ...]) -> tuple[EvaluationResult, ...]:
    """One row per ELM define, reading the per-define failures the evaluator collects under one key."""
    refusals = answered.get(ELM_ERRORS_KEY)
    stated = refusals if isinstance(refusals, dict) else {}
    rows: list[EvaluationResult] = []
    for name in declared:
        if name in stated:
            rows.append(EvaluationResult(name=name, refusal=str(stated[name])))
            continue
        if name not in answered:
            continue
        rows.append(EvaluationResult(name=name, values=_collection(answered[name])))
    return tuple(rows)


def _collection(value: Any) -> tuple[JsonValue, ...]:
    """One answer as the collection the results carry: a list stays a collection, a value becomes one of."""
    unwrapped = unwrap_primitives(value)
    if isinstance(unwrapped, list):
        return tuple(json_safe(item) for item in unwrapped)
    if unwrapped is None:
        return ()
    return (json_safe(unwrapped),)


def _retrievable(subject: dict[str, Any] | None) -> dict[str, Any]:
    """The Bundle a CQL retrieve reads through: the one handed in, the one resource wrapped, or nothing.

    A caller who supplied a single Patient means `[Patient]` to find it, so the resource is wrapped
    rather than left out - a retrieve over an empty data source is what "no context" means, and it
    would be a strange answer to a request that named one.
    """
    if subject is None:
        return _EMPTY_BUNDLE
    if subject.get("resourceType") == _BUNDLE_RESOURCE_TYPE:
        return subject
    return {"resourceType": _BUNDLE_RESOURCE_TYPE, "type": "collection", "entry": [{"resource": subject}]}


def _context_resource(subject: dict[str, Any] | None) -> dict[str, Any] | None:
    """The resource a define evaluates in the context of, which a Bundle is not - it is the data source."""
    if subject is None or subject.get("resourceType") == _BUNDLE_RESOURCE_TYPE:
        return None
    return subject

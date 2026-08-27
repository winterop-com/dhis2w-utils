"""`GET /facade/terminology/validate-code` and `/facade/terminology/lookup` - asking this guide's vocabularies.

THIS SERVES ONE PROJECT'S VOCABULARIES AND IS NOT A TERMINOLOGY SERVER. It answers about the
CodeSystems and ValueSets this facade publishes - the option sets its forms bind, the dictionaries
its questions are coded through - and about nothing else. A SNOMED CT or LOINC code is answered
"this server publishes no code system under that url", which is true and is more useful than a
guess. `dhis2w_fhir_serve.terminology` states the whole of what is and is not known here.

WHY GET, AND WHY NOT `$validate-code`. R4 spells these as operations on the resource that holds the
vocabulary - `ValueSet/$validate-code` and `CodeSystem/$lookup` - and both answer a `Parameters`
resource. Neither is implemented here, because implementing them properly means implementing
`$expand` behind them and answering for the external systems a real IG composes, which this facade
cannot do and should not appear to. Two honestly-named plain reads say what they are: this server
knows its own codes. They are GETs because they read, which also gives them HEAD parity from the
mount sweep, and they are served under the facade API's own mount rather than at the FHIR base -
`/spool`'s shape for `/spool`'s reasons, at `/spool`'s address. A FHIR base that answered
`/terminology/lookup` would be claiming a path FHIR has no interaction for.

THE STATE IS BUILT BY THE FIRST QUESTION, not by the lifespan, exactly as the capture state is:
a facade nobody asks a terminology question of never pays to parse every ValueSet it serves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from starlette.requests import Request

from dhis2w_fhir_serve.errors import BadOperationError
from dhis2w_fhir_serve.routes.context import serve_context
from dhis2w_fhir_serve.terminology import LookedUpCode, TerminologyState, ValidatedCode, load_terminology

#: Where the terminology state is held on the app, built by the first question that needs it.
TERMINOLOGY_STATE_ATTRIBUTE = "terminology"

#: The two paths this surface answers, under the facade API's mount.
VALIDATE_CODE_PATH = "/terminology/validate-code"
CODE_LOOKUP_PATH = "/terminology/lookup"

#: What these two operations are grouped under in the facade API's document.
TERMINOLOGY_TAG = "Terminology"

router = APIRouter()


@router.get(
    VALIDATE_CODE_PATH,
    tags=[TERMINOLOGY_TAG],
    summary="Check a code against this guide",
    description=(
        "Answers whether one code is a member of one value set this guide publishes, or - naming a "
        "system alone - whether it is a code of one system this guide publishes. Naming a value set "
        "asks the membership question and is what a form binding is checked against; naming neither "
        "is refused, because a check with nothing to check against would answer false about every "
        "code there is.\n\n"
        "This serves one project's vocabularies and is not a terminology server. A SNOMED CT or "
        "LOINC code is answered `this server publishes no code system under that url`, which is true "
        "and more useful than a guess."
    ),
    response_description="Whether the code holds, and what this server knows about the vocabulary it was checked in.",
)
async def validate_code(
    request: Request,
    code: Annotated[str, Query(description="The code to check.")],
    system: Annotated[str | None, Query(description="The code system the code is stated in.")] = None,
    valueset: Annotated[str | None, Query(description="The canonical of the value set to check.")] = None,
) -> ValidatedCode:
    """Answer whether one code is in one published value set, or is a code of one published system.

    Naming a value set asks the membership question and is what a form binding is checked against.
    Naming a system alone asks the weaker one this server can still answer honestly: is this a code
    the guide publishes at all. Naming neither is refused rather than answered, because a check with
    nothing to check against would answer false about every code there is.
    """
    if system is None and valueset is None:
        raise BadOperationError("name a `system` or a `valueset` to check the code against")
    return terminology_state(request).validate_code(code, system=system, valueset=valueset)


@router.get(
    CODE_LOOKUP_PATH,
    tags=[TERMINOLOGY_TAG],
    summary="Look one code up in a published system",
    description=(
        "Answers what one code is called in one code system this guide publishes, and what that "
        "system states about it.\n\n"
        "A code the guide does not publish answers 200 with `found` false and the reason - the same "
        "posture `$translate` takes to a concept its maps say nothing about. The question was well "
        "formed and this is the answer to it."
    ),
    response_description="What the published system calls the code, or why this server knows nothing about it.",
)
async def look_up_code(
    request: Request,
    system: Annotated[str, Query(description="The code system to look the code up in.")],
    code: Annotated[str, Query(description="The code to look up.")],
) -> LookedUpCode:
    """Answer what one code is called in one published system, and what that system states about it.

    A code the guide does not publish answers 200 with `found` false and the reason - the same
    posture `$translate` takes to a concept its maps say nothing about. The question was well formed
    and this is the answer to it.
    """
    return terminology_state(request).look_up(system, code)


def terminology_state(request: Request) -> TerminologyState:
    """The served vocabularies of this app, loaded from the store the first time one is asked about."""
    held: TerminologyState | None = getattr(request.app.state, TERMINOLOGY_STATE_ATTRIBUTE, None)
    if held is not None:
        return held
    state = load_terminology(serve_context(request).store)
    setattr(request.app.state, TERMINOLOGY_STATE_ATTRIBUTE, state)
    return state

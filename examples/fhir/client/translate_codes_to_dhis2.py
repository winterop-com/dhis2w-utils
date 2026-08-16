"""A published concept code read back to the DHIS2 identifier it stands for - offline, and over `$translate`.

Every other example here reads a whole response. This one reads a single answer, in the
direction that trips people up: a coded answer arrives as a code the *guide* publishes, and
DHIS2 stores an option of an option set. Those are two spellings of one thing, and the guide
publishes the mapping between them twice over:

- inside the option set's `CodeSystem`, where each concept carries the complementary DHIS2
  identifier as a property (`dhis2-id`, `dhis2-code`);
- as a `ConceptMap` per option set, whose groups map the concept code onto
  `{base}/id/option` (the DHIS2 UID) and `{base}/id/option-code` (the DHIS2 code).

Two ways to read it, and they answer the same question:

**Offline**, the translation context folds the CodeSystem and its ConceptMap into one option
table per terminology, and `resolve_option` is the read. This is what a forward does - every
answer of every response resolves through the table already in memory, and the answer cannot
drift from what the drain will do, because it *is* what the drain does.

**Over the wire**, a served facade answers `GET /ConceptMap/$translate` off the published maps.
This is for a client that holds no guide: a capture UI showing what a code means, or an
integration checking one concept before it builds a submission. One HTTP call per concept.

The dial in the middle is `coded_answer_mode`. Strict accepts the concept code the CodeSystem
publishes and nothing else. Lenient then tries the DHIS2 option UID and the DHIS2 option code,
because a client that sent either still named exactly one option - and every fall-back is noted
on the result, so a lenient run says what it accepted.

What DHIS2 finally stores is the option's own code, falling back to its UID where the option
carries no code. That is the value in the data value, not the concept code.

Usage:
    d2w fhir serve --port 8123          # optional, in the project directory, in another shell
    uv run python examples/fhir/client/translate_codes_to_dhis2.py

Runs whole without a facade: the `$translate` half then says so and the offline half still runs.
"""

from __future__ import annotations

import httpx
from _fixture import conversion_context, served_facade, stage_form_id
from dhis2w_fhir import ConversionContext, ConversionNaming
from dhis2w_fhir.conversion import CodedAnswerMode, FormSpec, OptionTable, QuestionSpec, resolve_option

#: How long one `$translate` call waits before this example gives up on the facade.
FACADE_TIMEOUT_SECONDS = 10.0

#: What the served operation answers in, and the media type it answers under.
FHIR_JSON = "application/fhir+json"

#: A code no served terminology holds, for the third resolution below.
UNKNOWN_CODE = "not-a-published-code"


def _form(context: ConversionContext, form_id: str) -> FormSpec:
    """The published form one Questionnaire id names, as the translator reads it."""
    for canonical, form in context.forms.items():
        if canonical.rsplit("/", 1)[-1] == form_id:
            return form
    raise LookupError(f"the project publishes no Questionnaire `{form_id}`")


def _coded_question(context: ConversionContext, form: FormSpec) -> tuple[QuestionSpec, OptionTable] | None:
    """The first question of the form that binds a terminology the context carries, with that terminology."""
    for question in form.questions.values():
        table = context.option_tables.get(question.option_system or "")
        if table is not None and table.entries:
            return question, table
    return None


def _print_option_table(table: OptionTable, naming: ConversionNaming) -> None:
    """Print what one served terminology says about each option, in all three spellings it answers to."""
    print(f"CodeSystem {table.system}")
    print("  the concept code is what the guide publishes; the ConceptMap carries it onto two DHIS2 namespaces:")
    print(f"    {naming.option_uid_system:42} the DHIS2 option UID")
    print(f"    {naming.option_code_system:42} the DHIS2 option code\n")
    print(f"  {'concept code':16} {'option UID':16} {'option code':22} stored in the data value")
    for entry in table.entries[:5]:
        print(f"  {entry.concept_code:16} {entry.option_uid:16} {entry.option_code or '-':22} {entry.wire_value}")
    if len(table.entries) > 5:
        print(f"  ... and {len(table.entries) - 5} more option(s)")
    print()


def _print_resolution(table: OptionTable, code: str, mode: CodedAnswerMode) -> None:
    """Resolve one received code against the served table and say what happened to it."""
    lookup = resolve_option(table, code, mode)
    if lookup.ambiguous_option_uids:
        print(f"  {mode:8} {code:22} ambiguous: {', '.join(lookup.ambiguous_option_uids)}")
        return
    if lookup.option is None:
        print(f"  {mode:8} {code:22} no option of this terminology - refused as `unresolvable-coding`")
        return
    resolved = lookup.option
    fallback = "" if resolved.matched_contract_spelling else "  (a fall-back the contract does not ask for)"
    print(f"  {mode:8} {code:22} matched by {resolved.matched_by:13} -> stores `{resolved.entry.wire_value}`{fallback}")


def _translate_over_the_wire(base_url: str, system: str, code: str, target_system: str) -> None:
    """Ask a running facade what one concept maps onto, through R4's own `$translate` operation."""
    try:
        answer = httpx.get(
            f"{base_url}/ConceptMap/$translate",
            params={"system": system, "code": code, "targetsystem": target_system},
            headers={"Accept": FHIR_JSON},
            timeout=FACADE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        print(f"  no facade answering at {base_url} ({type(error).__name__})")
        print("  start one with `d2w fhir serve --port 8123` in the project directory to see this half")
        return
    body = answer.raise_for_status().json()
    for parameter in body.get("parameter", []):
        if parameter.get("name") == "result":
            print(f"  result: {parameter.get('valueBoolean')}")
        if parameter.get("name") == "message":
            print(f"  message: {parameter.get('valueString')}")
        if parameter.get("name") != "match":
            continue
        for part in parameter.get("part", []):
            if part.get("name") == "concept":
                concept = part.get("valueCoding", {})
                print(f"  match: {concept.get('code')} in {concept.get('system')}")
            if part.get("name") == "source":
                print(f"    stated by ConceptMap {part.get('valueUri')}")


def main() -> None:
    """Read one published concept back to its DHIS2 identifiers, offline and then over the wire."""
    context = conversion_context()
    form = _form(context, stage_form_id())
    bound = _coded_question(context, form)
    if bound is None:
        print(f"{form.canonical} binds no terminology this context carries")
        return
    question, table = bound
    entry = table.entries[0]

    print(f"form: {form.canonical}")
    print(f"question {question.link_id} is answered from one option set, as a `valueCoding`\n")
    _print_option_table(table, context.naming)

    # The offline read: three codes for one option, against both settings of the dial.
    print("resolve_option, which is the read every forwarded answer goes through:")
    _print_resolution(table, entry.concept_code, CodedAnswerMode.STRICT)
    _print_resolution(table, entry.concept_code, CodedAnswerMode.LENIENT)
    if entry.option_code is not None and entry.option_code != entry.concept_code:
        _print_resolution(table, entry.option_code, CodedAnswerMode.STRICT)
        _print_resolution(table, entry.option_code, CodedAnswerMode.LENIENT)
    _print_resolution(table, UNKNOWN_CODE, CodedAnswerMode.LENIENT)
    print()

    # The served read: the same question asked of a facade, which holds the ConceptMaps as documents.
    base_url = served_facade()
    print(f"GET {base_url}/ConceptMap/$translate for the same concept, into the DHIS2 option code:")
    _translate_over_the_wire(base_url, table.system, entry.concept_code, context.naming.option_code_system)
    print("\nand into the DHIS2 option UID:")
    _translate_over_the_wire(base_url, table.system, entry.concept_code, context.naming.option_uid_system)

    print("\nwhich to use: a forwarder translating whole responses reads the table it already holds,")
    print("so its answer is the one the drain will act on. `$translate` is for a client that holds no")
    print("guide and wants one concept's DHIS2 identifier - one call, no build, no metadata read.")


if __name__ == "__main__":
    main()

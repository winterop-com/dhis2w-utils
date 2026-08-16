"""Read a published form and list what it asks: every question's key, its type, and how groups nest.

A DHIS2 data set is a grid - sections down the page, a data element per row, and one cell per
category option combo across. A generated form is that grid as a FHIR `Questionnaire`, and a
`Questionnaire` is a tree of `item`s. Two kinds of item live in that tree:

* an item of type `group` asks nothing - it is a section, or a data element whose cells hang under
  it - and it exists to nest the items below it;
* every other item is a question, and its `linkId` is the key an answer is filed under.

The link id is the whole point of reading a form. A plain question's link id is the DHIS2 data
element UID (on a registration form it is the tracked entity attribute UID). A disaggregated
cell's is `<dataElement>.<categoryOptionCombo>` - the very pair a DHIS2 data value is keyed by -
so the dot is not decoration, it is the disaggregation. Answering a form means posting values
against these keys, and nothing else identifies a cell.

`required` is DHIS2's compulsory data element operand, at the grain DHIS2 states it: an operand
naming a data element alone marks the whole question, one also naming a category option combo
marks that single cell.

Usage:
    uv run python examples/fhir/client/read_form_questions.py

Reads the aggregate form the example fixture publishes, from the facade the fixture serves.
"""

from __future__ import annotations

import httpx
from _fixture import aggregate_form_id, served_facade
from _runner import run_example
from dhis2w_fhir.r4 import Questionnaire, QuestionnaireItem
from pydantic import BaseModel

FHIR_JSON = "application/fhir+json"

#: The item types that carry no answer of their own and exist only to nest the items below them.
STRUCTURAL_ITEM_TYPES = ("group", "display")

#: The separator a disaggregated cell's link id joins its data element and category option combo with.
CELL_LINK_ID_SEPARATOR = "."

#: How many lines of the tree to print before summarising the rest - a national data set is long.
PRINTED_LINES = 24


class FormLine(BaseModel):
    """One item of the form's tree, flattened to the single line it prints as."""

    depth: int
    link_id: str
    text: str
    answerable: bool
    marks: tuple[str, ...] = ()

    def rendered(self) -> str:
        """The line as it prints: indented by nesting depth, key first, then what the form says about it."""
        indent = "  " * self.depth
        marks = f"   [{', '.join(self.marks)}]" if self.marks else ""
        return f"{indent}{self.link_id:34} {self.text}{marks}"


def _read_item(item: QuestionnaireItem, depth: int, lines: list[FormLine]) -> None:
    """Flatten one item and everything under it into `lines`, deepest last, in the order the form asks."""
    structural = item.type in STRUCTURAL_ITEM_TYPES
    marks: list[str] = [item.type or "unknown type"]
    if structural:
        # A group's link id keys nothing on a response - it names the section or the data element
        # the questions below it belong to, and DHIS2 stores no value against it.
        marks.append("nests, answers nothing")
    if item.required:
        marks.append("required")
    if item.repeats:
        marks.append("repeats")
    if item.readOnly:
        marks.append("read-only - DHIS2 fills this in itself")
    if CELL_LINK_ID_SEPARATOR in (item.linkId or ""):
        marks.append("one disaggregated cell")
    lines.append(
        FormLine(
            depth=depth,
            link_id=item.linkId or "-",
            text=item.text or "-",
            answerable=not structural,
            marks=tuple(marks),
        )
    )
    for child in item.item or []:
        _read_item(child, depth + 1, lines)


async def main() -> None:
    """Read one published form and print what it asks, keyed by the link id each answer is filed under."""
    base_url = served_facade()
    form_id = aggregate_form_id()
    async with httpx.AsyncClient(base_url=base_url, headers={"Accept": FHIR_JSON}, timeout=30.0) as client:
        body = (await client.get(f"/Questionnaire/{form_id}")).raise_for_status().json()

    # The served document validated into the same model the generator wrote it from, so every field
    # below is a typed attribute rather than a dictionary lookup that may or may not be there.
    form = Questionnaire.model_validate(body)
    print(f"{form.title} ({form.id})")
    print(f"  {form.description}")
    print(f"  status {form.status}, reported about a {', '.join(form.subjectType or ['-'])}")
    print()

    lines: list[FormLine] = []
    for item in form.item or []:
        _read_item(item, 1, lines)
    for line in lines[:PRINTED_LINES]:
        print(line.rendered())
    if len(lines) > PRINTED_LINES:
        print(f"  ... and {len(lines) - PRINTED_LINES} more line(s) of the same tree")

    answerable = [line for line in lines if line.answerable]
    print()
    print(f"{len(lines) - len(answerable)} group(s) nesting {len(answerable)} answerable question(s)")
    print(f"{sum(1 for line in answerable if 'required' in line.marks)} of those question(s) are compulsory in DHIS2")
    print("Every answer a response carries names one of those question link ids - a group's link id keys nothing.")


if __name__ == "__main__":
    run_example(main)

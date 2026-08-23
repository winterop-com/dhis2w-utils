"""Filtering the register by what a record holds: `d2-attribute={attributeUid}|{value}`.

**`identifier` answers the keys and this answers everything else.** A value of an attribute DHIS2
declares unique names one person, and `identifier` is FHIR's own parameter for that. A value of an
attribute DHIS2 declares nothing about describes a lot of people - sex, district of residence,
whether consent was given - and no FHIR parameter names it, because FHIR has no element for it: the
value rides the `D2TrackedEntityAttributeValue` extension, which is exactly where a facade puts what
the standard states no place for (`register.projection`). So the parameter is this server's own, it
is spelled with the `d2-` prefix every DHIS2-specific thing here is spelled with, and it names the
attribute in its own value rather than inventing one parameter per attribute an instance happens to
hold.

**IT ANSWERS EQUALITY AND NOTHING ELSE, AND EVERY DECLARATION OF IT SAYS SO.** No prefix, no
substring, no range, no `:missing`, no ordering. `d2-attribute=cejWyOfXge6|Female` finds whoever
holds exactly that value under exactly that attribute. A filter that looks like search and matches
only exact values is a trap unless it says which it is, so `/metadata` says it in the search
parameter's documentation, `/uiconfig` says it beside the attributes it declares, and the serving
guide says it in prose. A caller wanting "starts with" wants `_content`, which is the substring
search a projection-served register answers.

**EQUALITY IGNORES CASE, BECAUSE DHIS2'S OWN `eq` DOES.** `filter=<uid>:eq:Female` and
`filter=<uid>:eq:female` answer the same 243 people on a 2.43 instance (BUGS.md 109), so an operator
this server called equality would otherwise mean two different things depending on which backend
answered it. The projection matches the folded value for that reason - the column is already indexed
folded, because `_content` needed it first - and the two backends agree on every value in the
register rather than on the ones that happen to be typed the way they were stored.

**THE GRAMMAR IS `identifier`'S, READ ONE PLACE FURTHER LEFT.** `{system}|{value}` is R4's token
form and `routes.read.identifier_token` already parses it; here the system slot carries the DHIS2
tracked entity attribute UID rather than a URI, because the attribute is what the value belongs to
and the UID is what the instance and this guide both name it by. A token naming no attribute is
refused rather than searched across all of them: `identifier` may look everywhere because a key names
somebody wherever it is held, and a bare `Female` looked for everywhere would match a district called
Female as readily as a sex.

**ONE OCCURRENCE IS ONE PAIR AND OCCURRENCES NARROW.** `d2-attribute=A|x&d2-attribute=B|y` is whoever
holds both, which is what R4 says two instances of one parameter mean. A comma is NOT an alternative
here, and this is the one place this server departs from R4's token grammar deliberately: a DHIS2
attribute value is free text an instance chose, `Smith, John` is a value somebody actually holds, and
splitting it would make the person holding it unfindable by the value they hold. So the value is
taken whole, and the declarations say so.

**WHICH ATTRIBUTES ARE FILTERABLE IS THE GUIDE'S ANSWER AND NOT A DIAL.** The attributes a register
filters on are the ones the published registration forms ask of the tracked entity types it is served
over - the same set whose values the register already serves on every resource it hands back. There
is no `[serve.tracked_entities] filter_attributes` key, and the reason is the reason
`search_attributes` HAS one: that table restricts what values NAME a subject, which is a decision
about identity an operator can only make themselves, while this filters on values the same response
already carries in full. A dial narrowing it would let an operator hide a filter over data the
server hands over anyway, which is a setting that reads like a control and is not one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from dhis2w_fhir_serve.errors import BadSearchError, UnknownFilterAttributeError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from dhis2w_fhir.foundation.tracked_entity_attribute_values import TrackedEntityAttributeValueIn

    from dhis2w_fhir_serve.register.index import PublishedAttribute

#: The search parameter one attribute-value equality arrives on, and the separator inside its value.
ATTRIBUTE_FILTER_PARAMETER = "d2-attribute"
ATTRIBUTE_FILTER_SEPARATOR = "|"

#: The tracker filter operator this equality goes on the wire as.
#:
#: Lowercase because that is how `/api/tracker/trackedEntities` documents it; the endpoint accepts
#: either casing, and sending the documented one keeps a request log readable against the API's docs.
ATTRIBUTE_FILTER_OPERATOR = "eq"


class AttributeFilter(BaseModel):
    """One `{attributeUid}|{value}` equality a register search is narrowed by."""

    model_config = ConfigDict(frozen=True)

    attribute_uid: str
    value: str

    def wire_expression(self) -> str:
        """This equality as `/api/tracker/trackedEntities` takes it on a `filter=` parameter."""
        return f"{self.attribute_uid}:{ATTRIBUTE_FILTER_OPERATOR}:{self.value}"

    def folded_value(self) -> str:
        """The value as an index holding folded text matches it - see this module's note on case."""
        return self.value.casefold()


def requested_attribute_filters(
    query_items: Iterable[tuple[str, str]],
    *,
    resource_type: str,
    declared: Sequence[PublishedAttribute],
) -> tuple[AttributeFilter, ...]:
    """Read every value filter one request names, refusing a malformed one and an undeclared attribute.

    Both refusals are 400s and both name what would have worked, because there is no reading of
    either that a client should discover by getting back a page of everybody: a token with no
    attribute in it is a query this server cannot place, and an attribute this register does not
    filter on is a query nothing could ever satisfy.
    """
    filterable = {attribute.attribute_uid for attribute in declared}
    filters: list[AttributeFilter] = []
    for name, raw in query_items:
        if name != ATTRIBUTE_FILTER_PARAMETER:
            continue
        attribute_uid, separator, value = raw.partition(ATTRIBUTE_FILTER_SEPARATOR)
        if not separator or not attribute_uid or not value:
            raise BadSearchError(
                f"`{ATTRIBUTE_FILTER_PARAMETER}` was given `{raw}`, which names no attribute and value: "
                f"the filter is `{ATTRIBUTE_FILTER_PARAMETER}=<trackedEntityAttributeUid>"
                f"{ATTRIBUTE_FILTER_SEPARATOR}<value>`, and it matches that value exactly"
            )
        if attribute_uid not in filterable:
            raise UnknownFilterAttributeError(
                resource_type, ATTRIBUTE_FILTER_PARAMETER, attribute_uid, tuple(sorted(filterable))
            )
        filters.append(AttributeFilter(attribute_uid=attribute_uid, value=value))
    return tuple(filters)


def holds_every_filter(values: Sequence[TrackedEntityAttributeValueIn], filters: Sequence[AttributeFilter]) -> bool:
    """Whether one entity's own attribute values satisfy every filter, folded as DHIS2's `eq` folds.

    Read off the entity rather than asked of anything, and it is asked at the one place a search
    already has the record in hand: an identifier search resolves each match live before it hands it
    over, so the values are there, and the alternative is a second query per attribute per type to
    learn what this one already knows. The listing cannot work this way - a page has to be narrowed
    where it is counted, or paging over a filtered register would hand out short pages - so the
    listing narrows at the instance and at the projection instead.
    """
    held: dict[str, set[str]] = {}
    for attribute_value in values:
        held.setdefault(attribute_value.attribute_uid, set()).add(attribute_value.value.casefold())
    return all(filter_.folded_value() in held.get(filter_.attribute_uid, set()) for filter_ in filters)


def wire_filters(filters: Sequence[AttributeFilter]) -> list[str]:
    """Every filter as the tracker endpoint takes them - one `filter=` parameter apiece, ANDed there.

    Repeated rather than comma-joined: both are ANDed by 2.42 and 2.43 alike, and the repeated form
    is the one whose values may contain a comma without the endpoint reading it as a separator.
    """
    return [filter_.wire_expression() for filter_ in filters]

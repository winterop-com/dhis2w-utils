# Aggregate read-back on the FHIR facade

A live facade answers "what does DHIS2 hold for this form, this period, this
organisation unit" by reading `/api/dataValueSets` per request under the
caller's own credentials, and serving the answer as the `QuestionnaireResponse`
the data set's own published form describes - the same document a client posts a
capture in. It is the aggregate half of the data leg; the tracker half is
`GET /facade/tracked-entities/{uid}/events`. With both served, an aggregate
client captures a form through the guide and reads it back through the guide
without ever speaking the DHIS2 API.

This note states the addresses, the bounds, the dial, and the reasoning behind
each. [Endpoint naming](endpoint-naming.md) is the rule set it is placed by.

## The addresses

```
GET /facade/data-sets/{dataSetUid}/responses?orgUnit=&period=
GET /facade/data-sets/{dataSetUid}/responses/{responseId}
```

The document is not a FHIR interaction - R4 declares nothing at a DHIS2 data
set's address - so by endpoint-naming rule 2 it is under `/facade` whatever media
type it answers, exactly as the tracked entity record is. The data set is the
path subject the way the tracked entity is, and `responses` names what is served
rather than the wire shape it was read out of: the facade answers forms, and one
form is many data values. Rule 3 (flat hyphenated noun) holds; rule 4 (a prefix
only when a family exists) is earned by the pair collection plus item.
`data-sets` is the same segment the guide already uses for the identifier system
(`{base}/id/data-set`) and for the questionnaire directory, so one spelling
covers all three.

Two addresses that were considered and are not served.
`/facade/data-value-sets?dataSet=` mirrors the DHIS2 endpoint, names the wire
shape rather than the answer, and demotes the data set to a query parameter,
losing the "one thing's record" shape the tracker precedent set.
`GET /QuestionnaireResponse?questionnaire=` at the base URL merges two documents:
`QuestionnaireResponse/{id}` already answers the spool, where a resource of that
id is a receipt of what a client submitted rather than what DHIS2 now holds.

The response id is the three reporting keys, joined by a hyphen:

```
{orgUnit}-{period}-{attributeOptionCombo}
```

with `default` in the third place where the values named no attribute option combo
at all - DHIS2 usually exports the default combination's own UID, and where it
does, that UID is what the id carries.
No DHIS2 UID and no DHIS2 ISO period carries a hyphen, so an id splits back into
exactly the three keys it was built from - which is why the item read takes no
parameters at all: the id names the read. It is the same spelling the published
example corpus mints its instance ids from, so a served document and a published
example carry one id shape.

## The parameters

`orgUnit` is required. `period` is required and repeats. Both are bounds rather
than permissions: a read missing either is every organisation unit that reports
the data set, for every period it collects, in one answer. The refusal names both
and comes before any round trip.

`period` repeats because a client comparing this month against last month is the
first customer, and repeated `period=` is how `/api/dataValueSets` takes several.
`[serve.data_sets] period_limit` bounds the count - twelve by default, a year of
monthly reporting - and a request above it is refused with both the count it gave
and the limit, because splitting the read is the client's move and it cannot make
it without knowing both numbers. `startDate`/`endDate` are not served: a range is
the same unbounded read with a friendlier spelling.

`attributeOptionCombo` narrows the answer to the values filed under one combo. It
is applied to the grouped answer here rather than sent to the instance: the read
is already bounded by the data set, the unit, and the periods, so narrowing it
further at the instance saves nothing - and a filter the instance did not apply
would answer every combo to a client that asked for one, silently.

`_count`, `page`, and `_format` are the remaining three. Anything else is refused
rather than ignored, for the register's own reason: a parameter this surface
cannot apply, ignored, answers a narrower question with the whole selection, and
a client that asked about one clinic reads the answer as being about it.

## Scoping and credentials

There is no scoping rule here, and the required parameters must not be read as
one. The tracked entity record is entity-scoped because an event read by its own
UID would let a caller walk from a person they may see to an event about a person
they may not. An aggregate value's only subject is an organisation unit, so there
is no such walk.

The rights are DHIS2's and stay there. Under `[serve] auth = "dhis2"` the read
carries the caller's `Authorization` header verbatim through a `RegisterReader`,
and DHIS2 enforces sharing on the data set, on the category options behind both
the category option combos and the attribute option combos, and the organisation
unit against the caller's data view scope. Those refusals do not all look like
the register's: an unshared tracked entity is a 404, while an organisation unit
outside the caller's scope is a refusal carrying a message. DHIS2's verdict is
forwarded through `UpstreamRefusalError` and nothing is invented. Under the `jwt`
posture the read rides `[serve.jwt] forward_bearer` and is refused with 501 when
it is false; there is never a fall back to the facade's own profile.

`children=true` - descending the unit's subtree - is not served. It multiplies an
already unpaged read, and the roadmap already flags the generate path's full-tree
reads as a cost worth watching.

## The dial

```toml
[serve.data_sets]
responses = true         # false serves the forms and not the values reported against them
page_size = 20
page_size_limit = 100
data_sets = []           # empty means the data sets the guide publishes
period_limit = 12        # the most periods one read may name
```

`[serve.data_sets]` is the register's sibling and takes the same posture: every
default offers everything, and the table exists for the deployment that wants
less. The gating is single rather than double - there is no aggregate register
for a second `enabled` key to take away. A compiled guide answers
`NotServedFromCompiledIgError` naming the surface and `responses = false` answers
the disabled refusal naming the key, both before the instance is asked anything.

A data set outside a stated `data_sets` list is answered exactly as one the guide
publishes no form for: a 404 naming the data set. A refusal that named the key
instead would tell every caller which data sets the instance holds.

Three table names were considered and rejected. A key on
`[serve.tracked_entities]` is about neither tracked entities nor the register,
and that table is documented as register-wide. `[serve.aggregate]` names a DHIS2
concept rather than the object the route addresses. `[generate.data_sets]`
already fixes the spelling this table uses.

## Pagination, ordering, and the total

`/api/dataValueSets` has no cursor and no offset. It has `limit`, which truncates
silently and therefore cannot page - a client walking pages would be handed the
same truncated head every time and never told. So the bounded selection is read
whole and this server pages the ordered result, which is what the record already
does with its nested event read. That is why `Bundle.total` can be honest here:
it is every document this caller may see, counted under their own credentials. It
is only safe because `orgUnit` and `period` bound the read, which is the honest
argument for requiring them.

The order is the reporting key itself - `(orgUnit, period, attributeOptionCombo)`
ascending. An aggregate form has no instant, only a period, and a total order is
what makes two reads of an unchanged period answer the same bytes (BUGS.md 108 is
why an order is stated rather than passed on). The generate path's "richest group
first" is an example-picking heuristic and stays there, on top of the shared
grouping rather than inside it.

## What the code is

**The join key.** `CaptureNaming.data_set_identifier_system` is `{base}/id/data-set`,
mirroring `program_stage_identifier_system`. A form is found by the DHIS2 data set
UID it carries under that system - never by a name and never by a canonical this
server composed, because what a form is called follows `[generate.naming] source`
and what it is about does not.

**The grouping is shared.** `dhis2w_fhir.grouping.group_data_values` turns one
`DataValueSet` into the forms it reports, and both consumers read it: the examples
target that publishes a corpus, and the facade that serves a document. The rule is
subtle enough to be worth writing once - a value's own period, organisation unit,
and attribute option combo first, **the envelope's behind it**, and the period the
caller asked for behind that. `dhis2w_fhir.overwrite.aggregate_cells` reads the
same envelope the same way round, for the same reason.

**The wire read.** `history/data_values.py` sends the data set, the one
organisation unit, and the periods the request named, and nothing that would widen
it. The answer is validated into the generated `DataValueSet` rather than walked
as a raw body.

**The projection.** `history/aggregate.py` is a sibling of the record's
projection rather than a branch inside it: `RecordProjection` is keyed on tracked
entity and program stage end to end, while an aggregate document has a `Location`
subject, period and attribute-option-combo extensions, and cell link ids. What
the two genuinely share is the typing of a stored value into an answer, and that
lives in `history/answers.py`, which both read - so one form can never type a
value one way for a tracker event and another for an aggregate cell.

Three aggregate-specific details:

- **Cell link ids come from the index.** A disaggregated question's link id is
  `<dataElement>.<categoryOptionCombo>`, and the capture index already holds those
  two UIDs separately on every question - so a value is matched on the pair and
  the index supplies the link id. Re-splitting a link id on the separator would be
  the projection deciding the emitter's spelling a second time.
- **One D2Period spelling.** `capture/naming.period_extension` builds the
  extension, and both `$generate` and this read call it, so a draft and a served
  document date themselves identically.
- **The profile is claimed only where the document is whole.** `meta.profile`
  names the aggregate response profile when the period parsed, the organisation
  unit is present, and - on a data set the guide publishes a combo vocabulary for -
  the attribute option combo resolved. Otherwise the document is served without
  claiming it, which is the same rule the record and the example corpus follow.

**The status.** Every served form carries `completed`, which is what the capture
contract's status means for an aggregate response and what the example corpus and
`$generate` both carry. Whether DHIS2 holds a complete-data-set registration for
the form is a different fact, read at a different endpoint, and this read does not
ask for it.

**The contract.** `routes/data_sets.py` mounts in `ServeRouters.facade` and in
`negotiated`, so a client that takes no JSON is refused before it runs. The facade
OpenAPI document at `/facade/openapi.json` is this surface's contract; the
CapabilityStatement names the address in one sentence on the QuestionnaireResponse
entry, in prose, and declares nothing at it.

**The refusal order** is the record's, copied: the project's own word first
(`responses = false`), then the connection (a compiled guide, a posture that
forwards nothing, a request carrying no credential), then the parameters, then the
published form, and only then the instance. A request this server will not answer
costs it no round trip.

## The load-bearing test

`packages/dhis2w-fhir-serve/tests/test_data_set_round_trip.py` is the feature's
actual claim, and it runs both legs against each other: the golden aggregate
submission is posted to `POST /QuestionnaireResponse`, the real `forward_responses`
drains the spool against a mocked instance, the envelope it posts to
`/api/dataValueSets` is captured off the wire, that same envelope is served back
as the export this read consumes, and the link ids and typed answers are compared
cell for cell. Nothing between the two legs is hand-written.

## See also

- [Endpoint naming](endpoint-naming.md) - the rules this address is placed by.
- [Serve the guide](../201-serve.md) - the surface from an operator's side.
- [Consume the FHIR API](../401-consume-the-fhir-api.md) - the surface from a
  client's side.
- [The conversion layer](conversion.md) - the other direction, QuestionnaireResponse
  to DHIS2.

"""The history surface: one tracked entity's own record over time, read from the instance per request.

The register answers who somebody is. This answers what has happened to them - every event of every
enrollment the entity holds, each carried as the QuestionnaireResponse the guide already publishes
for its program stage. Identity and record are the two halves of the output leg, and this is the
second one.

Two modules split the work. `wire` is the DHIS2 read: one entity-scoped request, the events nested
under the enrollments they belong to, ordered here rather than trusted to arrive ordered.
`projection` turns each of those events into the document the capture contract states for it, reading
the served form the event's stage published - so the shape a client reads back is the shape a client
would post.

WHY THIS IS NOT A SECOND SHAPE. A DHIS2 tracker event captured through this facade travels as a
`D2TrackerEventResponse`, and the instance-sourced example corpus is built by projecting real events
into exactly that shape (`dhis2w_fhir.resources.examples.documents`). Serving the record in any other
shape would mean this project published two readings of one event and left a client to reconcile
them. Whether a DHIS2 event is additionally an `Encounter`, or its values additionally `Observation`s,
is the SDC `$extract` line that
[the enrollment resource](https://winterop-com.github.io/dhis2w-utils/fhir/design/enrollment-resource/)
leaves open, and `$extract` runs over a QuestionnaireResponse - so the form-faithful document is the
substrate that line needs rather than a rival to it.

WHAT DECIDES WHETHER IT IS SERVED. `[serve.tracked_entities] enabled` is the register and this with
it; `[serve.tracked_entities] events` is this alone, for the deployment that publishes who its
subjects are and not what was recorded about them.
"""

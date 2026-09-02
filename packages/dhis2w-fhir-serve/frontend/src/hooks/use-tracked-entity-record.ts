import { useFhirResource } from '@/hooks/use-fhir-resource'
import { usePatientEnrollments, type PatientEnrollmentsState } from '@/hooks/use-patient-enrollments'
import { useTrackedEntityEvents, type TrackedEntityEventsState } from '@/hooks/use-tracked-entity-events'
import { useTrackedEntityNaming, type TrackedEntityNaming } from '@/hooks/use-tracked-entity-naming'
import type { Patient } from '@/lib/fhir'
import {
    patientLeadValue,
    patientProjection,
    trackedEntityTypeLabel,
    type PatientProjection,
    type PublishedName,
} from '@/lib/patients'
import { registerWords, subjectOfTypeName, type RegisterWords } from '@/lib/uiconfig'
import { countedNoun } from '@/lib/utils'

/** Everything this server answers about one tracked entity, and the words to say it in. */
export interface TrackedEntityRecordState {
    /** The served projection, or null while the read is in flight and after one that failed. */
    person: PatientProjection | null
    /** The served document itself, kept so a reader can check the projection against what arrived. */
    resource: Patient | null
    loading: boolean
    error: string | null
    /** The HTTP status the read answered with, so a 404 reads as "not held" rather than as a fault. */
    status: number | null
    /** The tracked entity type's published name, or DHIS2's uid in the face that says so. */
    type: PublishedName | null
    /** What one of these is called, in the instance's own word for the type. */
    words: RegisterWords
    /** What names this record: a unique attribute value, or the uid where the instance holds none. */
    heading: string
    enrollments: PatientEnrollmentsState
    events: TrackedEntityEventsState
    /** Whether this run answers what the entity has been through, which decides whether it is read at all. */
    eventsOffered: boolean
    naming: TrackedEntityNaming
}

/**
 * The four reads one tracked entity takes, in one place.
 *
 * WHY A HOOK RATHER THAN A PAGE. The same record is read twice in this app - as its own page, which
 * is what a link somebody was sent opens, and in the sheet a register row opens over the listing -
 * and the two must not drift into two readings of one subject. The reads, the naming, and the words
 * the copy is written in are decided here; what each caller adds is its own heading and, on the
 * page, the summary line.
 *
 * NO SUMMARY LINE HERE, deliberately: there is one bar and the sheet opens over a listing that is
 * already speaking to it. The page states its own; the sheet leaves the listing's line alone.
 *
 * THE UIDS ARE JOINED TO NAMES THROUGH THE GUIDE, not through the instance. An attribute uid becomes
 * "National identifier" because `D2TEA_CS` published that name, and a tracked entity type uid becomes
 * "Person" because a registration form was generated from that type and titled with its name.
 * Anything this project never published keeps the spelling DHIS2 sent, in the mono face that says so.
 *
 * WHAT THE RUN DOES NOT ANSWER IS NOT ASKED FOR. `[serve.tracked_entities] events = false` is a
 * deployment saying who somebody is and declining what they have been through, so `eventsOffered`
 * false reads three of the four rather than sending a request whose answer is a refusal - and the
 * sections drawn from this leave the events out entirely. Which reads happen and which surfaces
 * exist are then the one decision, taken here, rather than two that can disagree.
 */
export function useTrackedEntityRecord(
    resourceType: string,
    trackedEntityUid: string,
    /** Whether this run answers one entity's own events - `lib/uiconfig.trackedEntityRecordOffered`. */
    eventsOffered: boolean,
): TrackedEntityRecordState {
    const { resource, loading, error, status } = useFhirResource<Patient>(resourceType, trackedEntityUid)
    const enrollments = usePatientEnrollments(trackedEntityUid)
    const events = useTrackedEntityEvents(eventsOffered ? trackedEntityUid : null)
    const naming = useTrackedEntityNaming()
    const person = resource === null ? null : patientProjection(resource)
    const type = trackedEntityTypeLabel(naming.types, person?.trackedEntityTypeUid ?? null)
    // WHAT THIS RECORD IS CALLED FOLLOWS ITS TRACKED ENTITY TYPE, which the badge beside the heading
    // states. The resource in the route is the projection this guide takes the type onto - a register
    // served as `Patient` routinely carries a Focus area beside the people - so wording from it puts
    // "this person" over a village. A type the guide published no name for keeps DHIS2's own word for
    // the family; see `lib/uiconfig.subjectOfTypeName`.
    const words = registerWords(
        subjectOfTypeName(type !== null && !type.isMachineSpelling ? type.text : null),
    )
    return {
        person,
        resource,
        loading,
        error,
        status,
        type,
        words,
        heading: person === null ? trackedEntityUid : patientLeadValue(person),
        enrollments,
        events,
        eventsOffered,
        naming,
    }
}

/**
 * What the bar under the record says this instance holds about the subject, or nothing.
 *
 * A COUNT IS STATED ONLY ONCE IT IS KNOWN. A read still in flight has no count, and a bar that
 * counted the empty array it is holding meanwhile would state "0 enrollments - 0 events" beneath a
 * screenful of rows, then correct itself a moment later - so a line with a read still in flight is
 * no line, and the bar keeps saying nothing until every half of it can be said.
 *
 * A HALF THIS RUN DOES NOT ANSWER IS NOT A NOUGHT. `[serve.tracked_entities] events = false` takes
 * the events section off the record, and "0 events" beside it would be this bar counting a surface
 * the server never offered. The same holds for a read the server refused: the section says what
 * went wrong, and a count of nothing is not what happened.
 */
export function trackedEntityRecordSummary(
    record: Pick<TrackedEntityRecordState, 'enrollments' | 'events' | 'eventsOffered'>,
): string | null {
    if (record.enrollments.loading) return null
    if (record.eventsOffered && record.events.loading) return null
    const counted: string[] = []
    if (record.enrollments.error === null) {
        counted.push(countedNoun(record.enrollments.enrollments.length, 'enrollment'))
    }
    if (record.eventsOffered && record.events.error === null) {
        // The events count is of what the record's first page carries when the instance stated no
        // total - the section itself says so where that matters, and a bar cannot carry the caveat.
        counted.push(countedNoun(record.events.total ?? record.events.events.length, 'event'))
    }
    return counted.length === 0 ? null : counted.join(' - ')
}

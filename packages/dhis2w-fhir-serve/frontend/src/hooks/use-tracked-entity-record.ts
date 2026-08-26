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
 */
export function useTrackedEntityRecord(
    resourceType: string,
    trackedEntityUid: string,
): TrackedEntityRecordState {
    const { resource, loading, error, status } = useFhirResource<Patient>(resourceType, trackedEntityUid)
    const enrollments = usePatientEnrollments(trackedEntityUid)
    const events = useTrackedEntityEvents(trackedEntityUid)
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
        naming,
    }
}

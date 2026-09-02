import { describe, expect, it } from 'vitest'

import {
    NO_ENROLLMENTS_ANSWERED,
    patientEnrollmentsState,
    type PatientEnrollmentsState,
} from '@/hooks/use-patient-enrollments'
import {
    NO_EVENTS_ANSWERED,
    trackedEntityEventsState,
    type TrackedEntityEvent,
    type TrackedEntityEventsState,
} from '@/hooks/use-tracked-entity-events'
import { trackedEntityRecordSummary } from '@/hooks/use-tracked-entity-record'
import type { PatientEnrollment } from '@/lib/patients'

/** The entity every state here is read for. */
const PERSON_UID = 'TeiPerson01'

/** One enrollment, in the shape the facade's own enrollment listing answers with. */
const ENROLLMENT: PatientEnrollment = {
    enrollment_uid: 'EnrAncActive',
    program_uid: 'ProgAnc0001',
    program_name: 'Antenatal care',
    status: 'ACTIVE',
    active: true,
    enrolled_at: '2026-01-05T00:00:00Z',
    organisation_unit_uid: 'DiszpKrYNg8',
    organisation_unit_name: 'Ngelehun CHC',
}

/** One event, in the shape a served QuestionnaireResponse is read into. */
const EVENT: TrackedEntityEvent = {
    eventUid: 'EvtAncVis01',
    formId: 'anc-visit',
    occurredAt: '2026-02-14T00:00:00Z',
    enrollmentUid: 'EnrAncActive',
    items: [],
}

/** The enrollments as they read once the answer for this person has landed. */
function enrollmentsRead(enrollments: PatientEnrollment[]): PatientEnrollmentsState {
    return patientEnrollmentsState(
        { trackedEntityUid: PERSON_UID, error: null, enrollments },
        PERSON_UID,
    )
}

/** The events as they read once the answer for this person has landed. */
function eventsRead(events: TrackedEntityEvent[], total: number | null = null): TrackedEntityEventsState {
    return trackedEntityEventsState({ trackedEntityUid: PERSON_UID, error: null, events, total }, PERSON_UID)
}

/**
 * A read that has not landed is in flight, not empty.
 *
 * WHY THIS IS UNDER TEST. An effect runs after the render that starts it, so a hook whose state
 * began settled hands its first paint a settled nought - and every consumer counting or wording what
 * it is handed then states a fact about the entity that is false: "0 enrollments - 0 events" beneath
 * three visible rows, or "This DHIS2 instance holds no event for this person" a moment before three
 * of them appear. Nothing crashes, so nothing else catches it.
 */
describe('what a read that has not landed reads as', () => {
    it('is in flight before the first answer, rather than an answer of none', () => {
        const enrollments = patientEnrollmentsState(NO_ENROLLMENTS_ANSWERED, PERSON_UID)
        expect(enrollments.loading).toBe(true)
        expect(enrollments.enrollments).toEqual([])

        const events = trackedEntityEventsState(NO_EVENTS_ANSWERED, PERSON_UID)
        expect(events.loading).toBe(true)
        expect(events.events).toEqual([])
        expect(events.total).toBeNull()
    })

    it('is in flight while the held answer is another entity, which is what a changed uid leaves', () => {
        const enrollments = patientEnrollmentsState(
            { trackedEntityUid: 'TeiPerson02', error: null, enrollments: [ENROLLMENT] },
            PERSON_UID,
        )
        expect(enrollments.loading).toBe(true)
        // Never the other entity's answer under this one's uid, which is the fact a stale render states.
        expect(enrollments.enrollments).toEqual([])

        const events = trackedEntityEventsState(
            { trackedEntityUid: 'TeiPerson02', error: null, events: [EVENT], total: 1 },
            PERSON_UID,
        )
        expect(events.loading).toBe(true)
        expect(events.events).toEqual([])
    })

    it('settles once the answer for the entity being asked about has landed', () => {
        const enrollments = enrollmentsRead([ENROLLMENT])
        expect(enrollments.loading).toBe(false)
        expect(enrollments.enrollments).toEqual([ENROLLMENT])

        const events = eventsRead([EVENT], 3)
        expect(events.loading).toBe(false)
        expect(events.events).toEqual([EVENT])
        expect(events.total).toBe(3)
    })

    it('settles empty for a read the server refused, so the refusal is what is drawn', () => {
        const enrollments = patientEnrollmentsState(
            { trackedEntityUid: PERSON_UID, error: 'This server does not answer for enrollments.', enrollments: [] },
            PERSON_UID,
        )
        expect(enrollments.loading).toBe(false)
        expect(enrollments.error).toBe('This server does not answer for enrollments.')
    })
})

/**
 * Asking about nobody, which is not a read in flight.
 *
 * The pickers hand these hooks a null uid before anyone has chosen, and the record hands the events
 * hook one on a run that answers no record. There is no request to wait for in either case, so a
 * caller drawing what it is handed must not spin - a panel reading "Reading this person's
 * enrollments" beside no person is worse than the empty panel it replaced.
 */
describe('what asking about nobody reads as', () => {
    it('is settled and empty for a null uid, so nothing drawn from it spins', () => {
        const enrollments = patientEnrollmentsState(NO_ENROLLMENTS_ANSWERED, null)
        expect(enrollments.loading).toBe(false)
        expect(enrollments.enrollments).toEqual([])

        const events = trackedEntityEventsState(NO_EVENTS_ANSWERED, null)
        expect(events.loading).toBe(false)
        expect(events.events).toEqual([])
    })

    it('reads an empty uid as the same nobody, which is what an unresolved route holds', () => {
        expect(patientEnrollmentsState(NO_ENROLLMENTS_ANSWERED, '').loading).toBe(false)
        expect(trackedEntityEventsState(NO_EVENTS_ANSWERED, '').loading).toBe(false)
    })

    it('drops an answer read for somebody when the question turns to nobody', () => {
        const held = { trackedEntityUid: PERSON_UID, error: null, enrollments: [ENROLLMENT] }
        const enrollments = patientEnrollmentsState(held, null)
        expect(enrollments.loading).toBe(false)
        expect(enrollments.enrollments).toEqual([])
    })
})

/**
 * The line under the record, which counts only what it knows.
 *
 * The bar is one line for the whole window and nothing overwrites it until the next page publishes
 * one, so a count stated early stands on screen as a claim about this subject. It says nothing until
 * every half of it can be said, and it never counts a surface this run does not answer for.
 */
describe('the summary line under one record', () => {
    it('says nothing while a read it would count is still in flight', () => {
        expect(
            trackedEntityRecordSummary({
                enrollments: patientEnrollmentsState(NO_ENROLLMENTS_ANSWERED, PERSON_UID),
                events: eventsRead([EVENT]),
                eventsOffered: true,
            }),
        ).toBeNull()
        expect(
            trackedEntityRecordSummary({
                enrollments: enrollmentsRead([ENROLLMENT]),
                events: trackedEntityEventsState(NO_EVENTS_ANSWERED, PERSON_UID),
                eventsOffered: true,
            }),
        ).toBeNull()
    })

    it('counts both halves once both are known', () => {
        expect(
            trackedEntityRecordSummary({
                enrollments: enrollmentsRead([ENROLLMENT]),
                events: eventsRead([EVENT], 3),
                eventsOffered: true,
            }),
        ).toBe('1 enrollment - 3 events')
    })

    it('counts the page it holds where the instance stated no total', () => {
        expect(
            trackedEntityRecordSummary({
                enrollments: enrollmentsRead([]),
                events: eventsRead([EVENT]),
                eventsOffered: true,
            }),
        ).toBe('0 enrollments - 1 event')
    })

    it('omits the events where this run answers none, rather than counting them as nought', () => {
        const line = trackedEntityRecordSummary({
            enrollments: enrollmentsRead([ENROLLMENT]),
            events: trackedEntityEventsState(NO_EVENTS_ANSWERED, null),
            eventsOffered: false,
        })
        expect(line).toBe('1 enrollment')
        expect(line).not.toContain('event')
    })

    it('states the enrollments without waiting on a read this run never makes', () => {
        // The events hook is handed nobody on a run answering no record, so it is settled from the
        // start - and a line that waited on it would wait for a request nothing sent.
        expect(
            trackedEntityRecordSummary({
                enrollments: enrollmentsRead([ENROLLMENT, ENROLLMENT]),
                events: trackedEntityEventsState(NO_EVENTS_ANSWERED, null),
                eventsOffered: false,
            }),
        ).toBe('2 enrollments')
    })

    it('leaves out a half the server refused, which is a failure rather than a count of none', () => {
        expect(
            trackedEntityRecordSummary({
                enrollments: enrollmentsRead([ENROLLMENT]),
                events: trackedEntityEventsState(
                    { trackedEntityUid: PERSON_UID, error: 'Read refused.', events: [], total: null },
                    PERSON_UID,
                ),
                eventsOffered: true,
            }),
        ).toBe('1 enrollment')
    })

    it('says nothing at all when neither half can be stated', () => {
        const refused = { trackedEntityUid: PERSON_UID, error: 'Read refused.', enrollments: [] }
        expect(
            trackedEntityRecordSummary({
                enrollments: patientEnrollmentsState(refused, PERSON_UID),
                events: trackedEntityEventsState(
                    { trackedEntityUid: PERSON_UID, error: 'Read refused.', events: [], total: null },
                    PERSON_UID,
                ),
                eventsOffered: true,
            }),
        ).toBeNull()
    })
})

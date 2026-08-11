import { describe, expect, it } from 'vitest'

import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import {
    defaultEnrollmentOption,
    enrollmentOptionOf,
    registrationFormForProgram,
    registrationReceiptsFor,
    reloadedEnrollment,
    type EnrollmentOption,
} from '@/lib/enrollments'
import { bundleResources, type Bundle, type Questionnaire, type QuestionnaireResponse } from '@/lib/fhir'
import type { SpoolResponseSummary } from '@/lib/spool'

/**
 * The join a stage form makes to the registrations of its program, over real served shapes.
 *
 * The bundle fixture is the capture project's own `/Questionnaire` answer - it holds the
 * `PsAncVisit1` stage form whose program identifier names `PrAncCare01`, and the `EVTsupVis01`
 * event form that carries a program identifier without being a registration. The registration
 * form itself is written here in the shape `fixture_project.py` publishes it, because the bundle
 * was harvested before the fixture grew one; the identifiers are the wire contract either way.
 */

const servedForms = bundleResources(questionnaireBundleFixture as unknown as Bundle<Questionnaire>)

/** The registration form of `PrAncCare01`, as the fixture project publishes it. */
const registrationForm: Questionnaire = {
    resourceType: 'Questionnaire',
    id: 'PrAncCare01',
    url: 'http://localhost:8080/fhir/Questionnaire/PrAncCare01',
    title: 'Antenatal care',
    status: 'draft',
    subjectType: ['Patient'],
    extension: [{ url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' }],
    identifier: [
        { system: 'http://dhis2.org/fhir/id/program', value: 'PrAncCare01' },
        { system: 'http://dhis2.org/fhir/id/program-code', value: 'PR_ANC' },
        { system: 'http://dhis2.org/fhir/id/tracked-entity-type', value: 'TetPerson01' },
    ],
}

/** One spool row in the listing's shape, with everything a test does not care about defaulted. */
function summaryOf(overrides: Partial<SpoolResponseSummary>): SpoolResponseSummary {
    return {
        response_id: 'receipt-1',
        received_at: '2026-08-09T10:00:00Z',
        lifecycle: 'received',
        form_kind: 'tracker',
        questionnaire: registrationForm.url ?? '',
        questionnaire_id: 'PrAncCare01',
        answer_count: 3,
        warnings: [],
        tracked_entity: 'TeMinted001',
        tracker_enrollment: 'EnMinted001',
        ...overrides,
    }
}

/** One stored registration response, carrying the pair and the dates the way the profile writes them. */
function storedRegistration(overrides: {
    trackedEntity?: string
    enrollment?: string
    enrolledAt?: string
}): QuestionnaireResponse {
    return {
        resourceType: 'QuestionnaireResponse',
        status: 'completed',
        subject: {
            type: 'Patient',
            identifier: {
                system: 'http://dhis2.org/fhir/id/tracked-entity',
                value: overrides.trackedEntity ?? 'TeStored001',
            },
        },
        extension: [
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment',
                valueIdentifier: {
                    system: 'http://dhis2.org/fhir/id/tracker-enrollment',
                    value: overrides.enrollment ?? 'EnStored001',
                },
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                valueDateTime: overrides.enrolledAt ?? '2026-08-01T08:00:00Z',
            },
        ],
    }
}

/** One offerable option, with everything a test does not care about defaulted. */
function optionOf(overrides: Partial<EnrollmentOption>): EnrollmentOption {
    return {
        responseId: 'receipt-1',
        enrollment: 'EnMinted001',
        trackedEntity: 'TeMinted001',
        enrolledAt: '2026-08-01T08:00:00Z',
        lifecycle: 'received',
        receivedAt: '2026-08-09T10:00:00Z',
        ...overrides,
    }
}

describe('finding the registration form of a program', () => {
    const forms = [...servedForms, registrationForm]

    it('finds it by the shared program identifier', () => {
        expect(registrationFormForProgram(forms, 'PrAncCare01')).toBe(registrationForm)
    })

    it('does not mistake a stage form of the program for it', () => {
        // PsAncVisit1 carries `{base}/id/program|PrAncCare01` as a grouping identifier, but its
        // kind is tracker-event - without the registration form in the set there is no match.
        expect(registrationFormForProgram(servedForms, 'PrAncCare01')).toBeNull()
    })

    it('does not mistake an event program for a registration', () => {
        // EVTsupVis01 carries `{base}/id/program|EVTsupVis01` as its own identity, because an
        // event form IS its program - but its kind is `event`, and it registers nobody.
        expect(registrationFormForProgram(forms, 'EVTsupVis01')).toBeNull()
    })

    it('answers null for a program nothing serves', () => {
        expect(registrationFormForProgram(forms, 'IpHINAT79UW')).toBeNull()
    })
})

describe('the registration receipts of one form', () => {
    it('matches on the canonical the receipt names', () => {
        const mine = summaryOf({ response_id: 'mine' })
        const other = summaryOf({
            response_id: 'other',
            questionnaire: 'http://localhost:8080/fhir/Questionnaire/ZzYYXq4fJie',
            questionnaire_id: 'ZzYYXq4fJie',
        })

        expect(registrationReceiptsFor([mine, other], registrationForm)).toEqual([mine])
    })

    it('falls back to the served id when the canonical differs', () => {
        const relabelled = summaryOf({ questionnaire: 'http://elsewhere.example/fhir/Questionnaire/PrAncCare01' })

        expect(registrationReceiptsFor([relabelled], registrationForm)).toEqual([relabelled])
    })

    it('drops rejected receipts, whose pair names nothing and never will', () => {
        const rejected = summaryOf({ response_id: 'refused', lifecycle: 'rejected' })
        const received = summaryOf({ response_id: 'kept' })

        expect(registrationReceiptsFor([rejected, received], registrationForm)).toEqual([received])
    })

    it('keeps the listing order, which is newest first', () => {
        const newest = summaryOf({ response_id: 'newest', received_at: '2026-08-09T12:00:00Z' })
        const oldest = summaryOf({ response_id: 'oldest', received_at: '2026-08-08T12:00:00Z' })

        expect(registrationReceiptsFor([newest, oldest], registrationForm).map((row) => row.response_id)).toEqual([
            'newest',
            'oldest',
        ])
    })
})

describe('one receipt as an offerable enrollment', () => {
    it('takes the pair from the spool row and the date from the stored resource', () => {
        const option = enrollmentOptionOf(summaryOf({}), storedRegistration({}))

        expect(option).toEqual(
            optionOf({ enrollment: 'EnMinted001', trackedEntity: 'TeMinted001', enrolledAt: '2026-08-01T08:00:00Z' }),
        )
    })

    it('lets the spool derivation win where both sources answer', () => {
        // Two spellings of one fact is how a page contradicts itself: the spool's is what the
        // Responses listing shows, so it is what the option says too.
        const option = enrollmentOptionOf(
            summaryOf({}),
            storedRegistration({ trackedEntity: 'TeStoredOther', enrollment: 'EnStoredOther' }),
        )

        expect(option?.enrollment).toBe('EnMinted001')
        expect(option?.trackedEntity).toBe('TeMinted001')
    })

    it('fills the pair from the stored resource when the listing could not derive it', () => {
        const option = enrollmentOptionOf(
            summaryOf({ tracked_entity: null, tracker_enrollment: null }),
            storedRegistration({ trackedEntity: 'TeStored001', enrollment: 'EnStored001' }),
        )

        expect(option?.enrollment).toBe('EnStored001')
        expect(option?.trackedEntity).toBe('TeStored001')
    })

    it('degrades to a dateless option when the stored resource could not be read', () => {
        const option = enrollmentOptionOf(summaryOf({}), null)

        expect(option?.enrolledAt).toBeNull()
        expect(option?.enrollment).toBe('EnMinted001')
    })

    it('is no option at all without a whole pair', () => {
        expect(enrollmentOptionOf(summaryOf({ tracked_entity: null, tracker_enrollment: null }), null)).toBeNull()
        expect(
            enrollmentOptionOf(summaryOf({ tracker_enrollment: null }), storedRegistration({ enrollment: '' })),
        ).toBeNull()
    })
})

describe('the default enrollment', () => {
    it('is the newest forwarded pair - the one a submission is known to land against', () => {
        const options = [
            optionOf({ responseId: 'newest-received', lifecycle: 'received' }),
            optionOf({ responseId: 'newest-forwarded', enrollment: 'EnFwd000001', lifecycle: 'forwarded' }),
            optionOf({ responseId: 'older-forwarded', enrollment: 'EnFwd000002', lifecycle: 'forwarded' }),
        ]

        expect(defaultEnrollmentOption(options)?.responseId).toBe('newest-forwarded')
    })

    it('is nothing when no registration has been forwarded, so the page states what the draft answers for', () => {
        expect(defaultEnrollmentOption([optionOf({ lifecycle: 'received' })])).toBeNull()
        expect(defaultEnrollmentOption([])).toBeNull()
    })
})

describe('the selection after the offer reloads', () => {
    it('defaults when nothing was chosen', () => {
        const forwarded = optionOf({ lifecycle: 'forwarded' })

        expect(reloadedEnrollment(null, [forwarded])).toBe(forwarded)
    })

    it('re-reads a choice so its lifecycle catches up with a forwarder run', () => {
        const before = optionOf({ enrollment: 'EnMinted001', lifecycle: 'received' })
        const after = optionOf({ enrollment: 'EnMinted001', lifecycle: 'forwarded' })

        expect(reloadedEnrollment(before, [after])).toBe(after)
    })

    it('keeps a choice that vanished from the offer rather than replacing it behind the person', () => {
        const chosen = optionOf({ enrollment: 'EnMinted001' })
        const unrelated = optionOf({ enrollment: 'EnOther0001', lifecycle: 'forwarded' })

        expect(reloadedEnrollment(chosen, [unrelated])).toBe(chosen)
    })
})

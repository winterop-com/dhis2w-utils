import { describe, expect, it } from 'vitest'

import attributeCodeSystemFixture from '@/lib/__fixtures__/codesystem-d2-aoc-idcDPkDtepR-cs.json'
import generateAggregateFixture from '@/lib/__fixtures__/generate-BfMAe6Itzgt.json'
import generateEventFixture from '@/lib/__fixtures__/generate-EVTsupVis01.json'
import generateTemporalFixture from '@/lib/__fixtures__/generate-PrTemporal1.json'
import generateTrackerFixture from '@/lib/__fixtures__/generate-ZzYYXq4fJie.json'
import temporalQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrTemporal1.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import attributeComboResponseFixture from '@/lib/__fixtures__/response-TuL8IOPzpHh.json'
import {
    bundleResources,
    generateSeedOf,
    type Bundle,
    type CodeSystem,
    type Questionnaire,
    type QuestionnaireResponse,
} from '@/lib/fhir'
import { dateLabelsOf, DEFAULT_DATE_LABELS, flattenQuestionnaire, type ProgramRule } from '@/lib/questionnaire'
import {
    attributeOptionComboFact,
    formLabel,
    joinAnswersToQuestions,
    mergeContextFacts,
    namedCaptureWarning,
    programRuleUidOf,
    rejectionRuleName,
    trackerContextFacts,
} from '@/lib/receipt'
import { formatInstant, type SpoolResponseSummary } from '@/lib/spool'

/**
 * The receipt page's reading of a stored capture, against captures a real server produced.
 *
 * The fixtures are the same ones the fill side is tested with: `GET /Questionnaire/{id}/$generate`
 * responses harvested verbatim from an in-process `d2w fhir serve` over the committed goldens,
 * and the Questionnaires those responses answer. That pairing is the whole point of this suite -
 * the join is between two documents the server really serves, so a shape that drifts on either
 * side fails here rather than on the page.
 */

const questionnaires = new Map(
    bundleResources(questionnaireBundleFixture as unknown as Bundle<Questionnaire>).map((questionnaire) => [
        questionnaire.id ?? '',
        questionnaire,
    ]),
)

const attributeComboResponse = attributeComboResponseFixture as unknown as QuestionnaireResponse
const attributeCodeSystem = attributeCodeSystemFixture as unknown as CodeSystem
const generateAggregate = generateAggregateFixture as unknown as QuestionnaireResponse

/** One served form by its DHIS2 uid, failing loudly rather than testing against undefined. */
function servedForm(id: string): Questionnaire {
    const questionnaire = questionnaires.get(id)
    if (questionnaire === undefined) throw new Error(`the fixture bundle serves no Questionnaire ${id}`)
    return questionnaire
}

const aggregateResponse = generateAggregateFixture as unknown as QuestionnaireResponse
const eventResponse = generateEventFixture as unknown as QuestionnaireResponse
const trackerResponse = generateTrackerFixture as unknown as QuestionnaireResponse
const temporalResponse = generateTemporalFixture as unknown as QuestionnaireResponse
const temporalQuestionnaire = temporalQuestionnaireFixture as unknown as Questionnaire

/** The rows one receipt joins to, against the form it answers. */
function rowsFor(questionnaire: Questionnaire, response: QuestionnaireResponse) {
    return joinAnswersToQuestions(flattenQuestionnaire(questionnaire), response)
}

describe('joining a receipt to the form it answers', () => {
    it('gives every answered question its text, in the order the form asks them', () => {
        const rows = rowsFor(servedForm('EVTsupVis01'), eventResponse)

        expect(rows.map((row) => row.linkId)).toEqual(['s46m5MS0hxu', 'YtbsuPPo010'])
        expect(rows[0]?.text).toBe('BCG doses given')
        expect(rows[0]?.values).toEqual([{ kind: 'text', text: '404' }])
        expect(rows.every((row) => row.known)).toBe(true)
    })

    it('carries the enclosing groups, which is what makes a disaggregated cell readable', () => {
        const rows = rowsFor(servedForm('BfMAe6Itzgt'), aggregateResponse)

        // `Fixed, <1y` is the whole question text of a category option combo cell, and it means
        // nothing without the data element group above it.
        const cell = rows.find((row) => row.linkId === 's46m5MS0hxu.Prlt0C1RF0s')
        expect(cell?.text).toBe('Fixed, <1y')
        expect(cell?.groupPath).toEqual(['Immunization', 'BCG doses given'])
        expect(cell?.values).toEqual([{ kind: 'text', text: '331' }])
    })

    it('omits the questions the receipt left unanswered', () => {
        const questionnaire = servedForm('BfMAe6Itzgt')
        const spec = flattenQuestionnaire(questionnaire)
        const rows = joinAnswersToQuestions(spec, {
            resourceType: 'QuestionnaireResponse',
            status: 'completed',
            item: [
                {
                    linkId: 'Y2rk0vzgvAx',
                    item: [{ linkId: 's46m5MS0hxu', item: [{ linkId: 's46m5MS0hxu.Prlt0C1RF0s', answer: [{ valueInteger: 12 }] }] }],
                },
            ],
        })

        // The form asks 128 questions; this receipt answers one, and a table of 127 empty rows
        // would bury it.
        expect(spec.questionLinkIds.length).toBeGreaterThan(1)
        expect(rows).toHaveLength(1)
        expect(rows[0]?.linkId).toBe('s46m5MS0hxu.Prlt0C1RF0s')
    })

    it('keeps both halves of a coded answer', () => {
        const rows = rowsFor(servedForm('ZzYYXq4fJie'), trackerResponse)

        const coded = rows.find((row) => row.linkId === 'X8zyunlgUfM')
        expect(coded?.values).toEqual([
            {
                kind: 'coding',
                display: 'Mixed',
                code: 'odMfnhhpjUj',
                system: 'http://localhost:8080/fhir/CodeSystem/d2-os-x31y45jvIQL-cs',
            },
        ])
    })

    it('reads a boolean as the yes or no the form asked for', () => {
        const rows = rowsFor(servedForm('ZzYYXq4fJie'), trackerResponse)

        expect(rows.find((row) => row.linkId === 'FqlgKAG8HOu')?.values).toEqual([
            { kind: 'text', text: 'No' },
        ])
        expect(rows.find((row) => row.linkId === 'rxBfISxXS2U')?.values).toEqual([
            { kind: 'text', text: 'Yes' },
        ])
    })

    it('keeps every answer of a repeating question, in the order they were given', () => {
        const rows = rowsFor(temporalQuestionnaire, temporalResponse)

        const repeats = rows.find((row) => row.linkId === 'DeSymptoms01')
        expect(repeats?.values.length).toBeGreaterThan(1)
        expect(repeats?.values.every((value) => value.kind === 'coding')).toBe(true)
    })

    it('shows dates, times, and urls as the literals the receipt states', () => {
        const rows = rowsFor(temporalQuestionnaire, temporalResponse)
        const value = (linkId: string) => rows.find((row) => row.linkId === linkId)?.values

        expect(value('DeVisitDate1')).toEqual([{ kind: 'text', text: '2026-07-23' }])
        expect(value('DeVisitTime1')).toEqual([{ kind: 'text', text: '20:00:00' }])
        expect(value('DeVisitStamp')).toEqual([{ kind: 'text', text: '2026-07-12T02:00:00Z' }])
        expect(value('DeVisitLink1')).toEqual([
            { kind: 'text', text: 'https://example.invalid/DeVisitLink1' },
        ])
    })

    it('keeps an organisation-unit answer`s reference and its unit id apart', () => {
        const rows = rowsFor(temporalQuestionnaire, temporalResponse)
        const value = rows.find((row) => row.linkId === 'DeVisitUnit1')?.values

        // A `$generate` skeleton names the unit and nothing else, so `display` is null and the
        // receipt page is what looks the name up. The unit id is the DHIS2 uid the forwarder
        // writes, which is why it is carried on its own rather than only inside the reference.
        expect(value).toEqual([
            {
                kind: 'reference',
                display: null,
                reference: 'Location/DiszpKrYNg8',
                unitId: 'DiszpKrYNg8',
            },
        ])
    })

    it('carries the display a capture client wrote, so a receipt reads as a place', () => {
        const answered: QuestionnaireResponse = {
            resourceType: 'QuestionnaireResponse',
            status: 'completed',
            item: [
                {
                    linkId: 'DeVisitUnit1',
                    answer: [
                        {
                            valueReference: {
                                reference: 'Location/DiszpKrYNg8',
                                display: 'Ngelehun CHC',
                            },
                        },
                    ],
                },
            ],
        }
        const rows = rowsFor(temporalQuestionnaire, answered)

        expect(rows[0].values).toEqual([
            {
                kind: 'reference',
                display: 'Ngelehun CHC',
                reference: 'Location/DiszpKrYNg8',
                unitId: 'DiszpKrYNg8',
            },
        ])
    })
})

describe('a receipt whose form is no longer served', () => {
    it('degrades to link ids and values rather than to nothing', () => {
        const rows = joinAnswersToQuestions(null, trackerResponse)

        expect(rows.length).toBeGreaterThan(0)
        expect(rows.every((row) => !row.known)).toBe(true)
        expect(rows.every((row) => row.text === null)).toBe(true)
        expect(rows.find((row) => row.linkId === 'X8zyunlgUfM')?.values).toEqual([
            {
                kind: 'coding',
                display: 'Mixed',
                code: 'odMfnhhpjUj',
                system: 'http://localhost:8080/fhir/CodeSystem/d2-os-x31y45jvIQL-cs',
            },
        ])
    })

    it('keeps the nesting a stored aggregate receipt carries', () => {
        const rows = joinAnswersToQuestions(null, aggregateResponse)

        // With no form there are no texts, so the path is the enclosing link ids - still the
        // difference between a readable cell and four hundred rows called `Fixed, <1y`.
        const cell = rows.find((row) => row.linkId === 's46m5MS0hxu.Prlt0C1RF0s')
        expect(cell?.groupPath).toEqual(['Y2rk0vzgvAx', 's46m5MS0hxu'])
    })

    it('still shows an answer to a question the rebuilt form has dropped', () => {
        const rows = joinAnswersToQuestions(flattenQuestionnaire(servedForm('EVTsupVis01')), {
            resourceType: 'QuestionnaireResponse',
            status: 'completed',
            item: [
                { linkId: 's46m5MS0hxu', answer: [{ valueInteger: 1 }] },
                { linkId: 'DeRemoved001', answer: [{ valueString: 'answered before the rebuild' }] },
            ],
        })

        // The known questions come first, in the form's order; what the form no longer asks is
        // last and says so, because a receipt is a record and a rebuild cannot edit it.
        expect(rows.map((row) => row.linkId)).toEqual(['s46m5MS0hxu', 'DeRemoved001'])
        expect(rows[0]?.known).toBe(true)
        expect(rows[1]?.known).toBe(false)
        expect(rows[1]?.values).toEqual([{ kind: 'text', text: 'answered before the rebuild' }])
    })
})

describe('the seed a generated receipt states', () => {
    it('reads the seed off the identifier the operation writes', () => {
        // Every `$generate` fixture carries one, which is the operation's reproducibility
        // promise surviving the post into the stored receipt.
        expect(generateSeedOf(aggregateResponse)).toBe('7')
        expect(generateSeedOf(trackerResponse)).toBe('7')
    })

    it('states none for a receipt a client filled in itself', () => {
        expect(
            generateSeedOf({ resourceType: 'QuestionnaireResponse', status: 'completed' }),
        ).toBeNull()
        expect(
            generateSeedOf({
                resourceType: 'QuestionnaireResponse',
                status: 'completed',
                identifier: { system: 'http://example.invalid/id/something-else', value: '7' },
            }),
        ).toBeNull()
    })
})

/** One listing row, with only the fields the label rule reads. */
function summary(overrides: Partial<SpoolResponseSummary> = {}): SpoolResponseSummary {
    return {
        response_id: 'abc123',
        received_at: '2026-08-09T09:30:00Z',
        lifecycle: 'received',
        form_kind: 'aggregate',
        questionnaire: 'http://localhost:8080/fhir/Questionnaire/BfMAe6Itzgt',
        questionnaire_id: 'BfMAe6Itzgt',
        answer_count: 12,
        warnings: [],
        ...overrides,
    }
}

describe('a rejection naming a program rule', () => {
    /** The two rules the served antenatal visit stage lists, as `programRulesOf` reads them. */
    const RULES: ProgramRule[] = [
        {
            ruleUid: 'PrRuleHb001',
            name: 'The haemoglobin value cannot be above 99',
            description: null,
            condition: '#{DeAncVisNo1} > 99',
            action: 'SHOWERROR',
        },
        {
            ruleUid: 'PrRuleOrd01',
            name: 'A visit is filed in the order it happened',
            description: null,
            condition: 'd2:hasValue(#{DeAncVisNo1})',
            action: 'SHOWWARNING',
        },
    ]

    it('reads the rule uid out of the sentence DHIS2 writes it into', () => {
        // The message shape is the live `E1300` repro in docs/fhir/design/dhis2-fidelity.md.
        const issue = {
            error_code: 'E1300',
            subject: null,
            message:
                'Generated by ProgramRule (`PrRuleHb001`) - `The haemoglobin value cannot be above 99  (vANAXwtLwcT)`.',
        }

        expect(programRuleUidOf(issue)).toBe('PrRuleHb001')
        expect(rejectionRuleName(issue, RULES)).toBe('The haemoglobin value cannot be above 99')
    })

    it('reads a subject the form vouches for as a rule of its own', () => {
        const issue = { error_code: 'E1300', subject: 'PrRuleOrd01', message: 'a rule was broken' }

        expect(rejectionRuleName(issue, RULES)).toBe('A visit is filed in the order it happened')
    })

    it('never mistakes the data element an E1300 is about for the rule that refused it', () => {
        // `vANAXwtLwcT` is the data element the rule read, and it is uid-shaped like every rule uid.
        const issue = { error_code: 'E1300', subject: 'vANAXwtLwcT', message: 'a rule was broken' }

        expect(rejectionRuleName(issue, RULES)).toBeNull()
    })

    it('names nothing for a rule the served form does not list', () => {
        const issue = {
            error_code: 'E1300',
            subject: null,
            message: 'Generated by ProgramRule (`PrRuleZzz01`) - `a rule added since the capture`.',
        }

        expect(programRuleUidOf(issue)).toBe('PrRuleZzz01')
        expect(rejectionRuleName(issue, RULES)).toBeNull()
    })

    it('reads no rule off a row about anything else', () => {
        const enrollment = {
            error_code: 'E1023',
            subject: 'PrRuleHb001',
            message: 'Generated by ProgramRule (`PrRuleHb001`)',
        }

        expect(programRuleUidOf(enrollment)).toBeNull()
        expect(rejectionRuleName(enrollment, RULES)).toBeNull()
    })

    it('names nothing when the message states no rule', () => {
        expect(programRuleUidOf({ error_code: 'E1300', subject: 'vANAXwtLwcT', message: 'no rule named' })).toBeNull()
        expect(programRuleUidOf({ error_code: 'E1300' })).toBeNull()
    })
})

describe('naming the form a receipt answered', () => {
    it('prefers the served title', () => {
        expect(formLabel(summary(), servedForm('BfMAe6Itzgt'))).toBe('Child Health')
    })

    it('falls back to the id when the form is no longer served', () => {
        expect(formLabel(summary(), undefined)).toBe('BfMAe6Itzgt')
    })

    it('falls back to the canonical when the spool states no id either', () => {
        expect(formLabel(summary({ questionnaire_id: null }), undefined)).toBe('BfMAe6Itzgt')
    })

    it('spells a title holding markup characters the way the server sent it', () => {
        expect(
            formLabel(summary(), {
                resourceType: 'Questionnaire',
                status: 'active',
                title: 'Weight < 5kg & under',
            }),
        ).toBe('Weight < 5kg & under')
    })
})

/**
 * The combo fact, read off a stored receipt the way the receipt page reads it.
 *
 * The response is the emitter's published example for the golden aggregate form whose data set
 * rides a non-default category combo, and the CodeSystem is the vocabulary it names - so the
 * resolution below goes through the same two documents a served facade would hand the page.
 */
describe('the attribute option combo on a receipt', () => {
    it('names the combo by the vocabulary title and resolves the display through it', () => {
        expect(attributeOptionComboFact(attributeComboResponse, attributeCodeSystem)).toEqual({
            label: 'Reporting for Project',
            value: 'Provide access to primary health care (BqblOcSwGey)',
            mono: false,
        })
    })

    it('falls back to the display the receipt itself carries when the vocabulary is gone', () => {
        expect(attributeOptionComboFact(attributeComboResponse, null)).toEqual({
            label: 'Attribute option combo',
            value: 'Provide access to primary health care (BqblOcSwGey)',
            mono: false,
        })
    })

    it('degrades to system and code when nothing can name the concept', () => {
        const bare: QuestionnaireResponse = {
            resourceType: 'QuestionnaireResponse',
            status: 'completed',
            extension: [
                {
                    url: 'http://localhost:8080/fhir/StructureDefinition/d2-attribute-option-combo',
                    valueCoding: { system: 'http://example.org/CodeSystem/gone', code: 'BqblOcSwGey' },
                },
            ],
        }

        expect(attributeOptionComboFact(bare, null)).toEqual({
            label: 'Attribute option combo',
            value: 'http://example.org/CodeSystem/gone | BqblOcSwGey',
            mono: true,
        })
    })

    it('answers nothing for a receipt on the default combo, which states no extension', () => {
        expect(attributeOptionComboFact(generateAggregate, attributeCodeSystem)).toBeNull()
    })
})

/**
 * The tracker context a receipt carries, and the merge that keeps one fact one row.
 *
 * The two dates exist nowhere but on the stored resource - the spool has no column for either -
 * so a registration receipt would otherwise say who was enrolled and never when. The two uids do
 * exist in both places, which is the whole reason the merge is not a concatenation: the grid is
 * keyed by label, and a receipt that stated its enrollment twice would be rendering the same fact
 * as two.
 */
describe('the tracker context on a receipt', () => {
    /** A registration receipt as the profile requires it: minted identities, both dates. */
    const registration: QuestionnaireResponse = {
        resourceType: 'QuestionnaireResponse',
        status: 'completed',
        subject: {
            type: 'Patient',
            identifier: { system: 'http://dhis2.org/fhir/id/tracked-entity', value: 'wJt3Qy1PxLd' },
        },
        extension: [
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-tracker-enrollment',
                valueIdentifier: {
                    system: 'http://dhis2.org/fhir/id/tracker-enrollment',
                    value: 'Qm4bTnPzKdE',
                },
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-enrolled-at',
                valueDateTime: '2026-07-21T04:00:00Z',
            },
            {
                url: 'http://localhost:8080/fhir/StructureDefinition/d2-incident-at',
                valueDateTime: '2026-07-14T04:00:00Z',
            },
            { url: 'http://localhost:8080/fhir/StructureDefinition/d2-form-type', valueCode: 'tracker' },
        ],
    }

    it('states all four facts a registration files, identities mono and dates as prose', () => {
        expect(trackerContextFacts(registration)).toEqual([
            { label: 'Tracked entity', value: 'wJt3Qy1PxLd', mono: true },
            { label: 'Enrollment', value: 'Qm4bTnPzKdE', mono: true },
            // Read against the same formatter rather than a literal, so the assertion does not
            // depend on the timezone the suite happens to run in.
            {
                label: DEFAULT_DATE_LABELS.enrollmentDate,
                value: formatInstant('2026-07-21T04:00:00Z'),
                mono: false,
            },
            {
                label: DEFAULT_DATE_LABELS.incidentDate,
                value: formatInstant('2026-07-14T04:00:00Z'),
                mono: false,
            },
        ])
    })

    it('labels the dates with the words the form the receipt answered uses for them', () => {
        // The one rule the fill side follows, read from the same function: a programme that renames
        // its dates has them renamed on the receipt too, rather than in one place out of two.
        const labelled = dateLabelsOf({
            resourceType: 'Questionnaire',
            status: 'active',
            extension: [
                {
                    url: 'http://localhost:8080/fhir/StructureDefinition/d2-date-labels',
                    extension: [
                        { url: 'enrollmentDate', valueString: 'Date first seen' },
                        { url: 'incidentDate', valueString: 'Date of last menstrual period' },
                    ],
                },
            ],
        })

        expect(trackerContextFacts(registration, labelled).map((fact) => fact.label)).toEqual([
            'Tracked entity',
            'Enrollment',
            'Date first seen',
            'Date of last menstrual period',
        ])
    })

    it('renders the dates rather than repeating the stored instant', () => {
        const enrolled = trackerContextFacts(registration).find(
            (fact) => fact.label === DEFAULT_DATE_LABELS.enrollmentDate,
        )
        expect(enrolled?.value).not.toBe('2026-07-21T04:00:00Z')
    })

    it('leaves out the incident date a program that displays none never files', () => {
        const withoutIncident = {
            ...registration,
            extension: registration.extension?.filter(
                (candidate) => !candidate.url.endsWith('d2-incident-at'),
            ),
        }
        expect(trackerContextFacts(withoutIncident).map((fact) => fact.label)).toEqual([
            'Tracked entity',
            'Enrollment',
            DEFAULT_DATE_LABELS.enrollmentDate,
        ])
    })

    it('states the two identities a real stage receipt carries, and no dates', () => {
        expect(trackerContextFacts(trackerResponse)).toEqual([
            { label: 'Tracked entity', value: 'zPde0IgxLd6', mono: true },
            { label: 'Enrollment', value: 'GncfBAepfJB', mono: true },
        ])
    })

    it('answers nothing at all for an aggregate receipt', () => {
        expect(trackerContextFacts(generateAggregate)).toEqual([])
    })
})

describe('merging the sources of capture context', () => {
    it('keeps the first statement of a label and drops the repeat', () => {
        const spool = [
            { label: 'Organisation unit', value: 'Ngelehun CHC (DiszpKrYNg8)', mono: false },
            { label: 'Enrollment', value: 'Qm4bTnPzKdE', mono: true },
        ]
        const resource = [
            { label: 'Enrollment', value: 'Qm4bTnPzKdE', mono: true },
            { label: 'Enrolled at', value: 'Jul 21, 2026', mono: false },
        ]

        expect(mergeContextFacts(spool, resource)).toEqual([
            { label: 'Organisation unit', value: 'Ngelehun CHC (DiszpKrYNg8)', mono: false },
            // The spool's, because the page has already resolved it further than the resource can.
            { label: 'Enrollment', value: 'Qm4bTnPzKdE', mono: true },
            { label: 'Enrolled at', value: 'Jul 21, 2026', mono: false },
        ])
    })

    it('keeps every label exactly once, which is what the grid keys on', () => {
        const merged = mergeContextFacts(
            [{ label: 'Enrollment', value: 'one', mono: true }],
            [{ label: 'Enrollment', value: 'two', mono: true }],
            [{ label: 'Enrollment', value: 'three', mono: true }],
        )
        expect(merged).toEqual([{ label: 'Enrollment', value: 'one', mono: true }])
    })

    it('answers an empty list when nothing states anything', () => {
        expect(mergeContextFacts([], [])).toEqual([])
        expect(mergeContextFacts()).toEqual([])
    })
})

/**
 * A capture warning read in the form's words rather than in the validator's.
 *
 * The validator quotes link ids because a link id is the only handle it has. The person reading the
 * receipt knows the question, so the served form is asked what each quoted id is called - and the
 * uid comes back out as a chip rather than being dropped, because it is the string to search DHIS2
 * with.
 */
describe('a capture warning', () => {
    const questions = new Map([
        ['eMyVanycQSC', 'Date of birth'],
        ['GQY2lXrypjO', 'MCH Weight (g)'],
    ])

    it('says the question where the served form knows the link id, and keeps the uid beside it', () => {
        const named = namedCaptureWarning(
            '`eMyVanycQSC` is required by the form and was not answered',
            questions,
        )
        expect(named.text).toBe('Date of birth is required by the form and was not answered')
        expect(named.linkIds).toEqual(['eMyVanycQSC'])
    })

    it('names every link id one sentence quotes, in the order it quoted them', () => {
        const named = namedCaptureWarning('`GQY2lXrypjO` and `eMyVanycQSC` disagree', questions)
        expect(named.text).toBe('MCH Weight (g) and Date of birth disagree')
        expect(named.linkIds).toEqual(['GQY2lXrypjO', 'eMyVanycQSC'])
    })

    it('leaves a link id the form no longer states exactly as the validator wrote it', () => {
        // A guide recompiled since the capture is ordinary, and a name this UI cannot vouch for
        // would be worse than the uid the validator quoted.
        const named = namedCaptureWarning('`NoSuchLink` is required by the form', questions)
        expect(named.text).toBe('`NoSuchLink` is required by the form')
        expect(named.linkIds).toEqual([])
    })

    it('leaves every other marked spelling marked, so paths and elements keep the mono face', () => {
        const named = namedCaptureWarning(
            'The element `QuestionnaireResponse.item` states nothing',
            questions,
        )
        expect(named.text).toBe('The element `QuestionnaireResponse.item` states nothing')
    })
})


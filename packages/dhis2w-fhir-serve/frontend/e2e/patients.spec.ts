import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * People, in and out: registering one without a program, and answering for one the instance holds.
 *
 * TWO HALVES, AND ONLY ONE OF THEM CAN RUN AGAINST THE REAL SERVER. The person-only form is served
 * by the fixture project itself, so registering a person with no enrollment is walked end to end
 * against the real `d2w fhir serve --ui` like every other capture spec. Finding a person cannot be:
 * `GET /Patient` is answered from a DHIS2 instance at request time, the fixture server serves a
 * compiled guide and holds no instance, and standing a DHIS2 up for a browser suite would make an
 * offline test suite depend on somebody else's database.
 *
 * SO THE COMPILED CASE IS ITSELF A TEST, and it comes first. A compiled `/metadata` declares no
 * `Patient`, and the whole contract of the picker is that it offers the instance option exactly
 * when the conformance document says a search would be answered. That claim is provable here
 * against the real server and nothing else in this file is.
 *
 * THE LIVE CASE FULFILS THREE ROUTES AND NOTHING ELSE, on the idiom uiconfig.spec.ts established:
 * `/metadata` is fetched from the real server and the Patient entry a live process would have
 * declared is pushed onto it, so every other page in the app still reads the real document; and
 * `/Patient` and `/patients/{uid}/enrollments` answer the shapes
 * `dhis2w_fhir_serve.patients.projection` and `routes.enrollments` emit, which the pytest suite
 * over those routes is what pins. What is under test here is the browser: the search, the choice,
 * the questions it takes away, and the marker the submission carries. The submission itself goes to
 * the real server, and the receipt is read back off the real spool.
 */

const FHIR_JSON = 'application/fhir+json'

/** The fixture project's own canonical and identifier base - the systems its resources are published under. */
const CANONICAL = 'http://localhost:8080/fhir'
const IDENTIFIER_BASE = 'http://dhis2.org/fhir'

/** The three forms this file drives: a registration, its stage, and the person-only form. */
const REGISTRATION_FORM = 'PrAncCare01'
const STAGE_FORM = 'PsAncVisit1'
const PERSON_FORM = 'TetPerson01'

/** The person the fulfilled instance holds, and the identifier value that finds them. */
const PERSON_UID = 'TeiPerson01'
const NATIONAL_ID = '19850312-4471'

/** Their two enrollments: one in the stage form's own program, one in a program it is not. */
const COMPLETED_ENROLLMENT = 'EnrAnc00001'
const OTHER_PROGRAM_ENROLLMENT = 'EnrChild001'

/** The Patient entry a live process over a project publishing a registration form declares. */
const PATIENT_CAPABILITY = {
    type: 'Patient',
    documentation: 'One DHIS2 tracked entity per Patient, read from the instance at request time.',
    interaction: [{ code: 'read' }, { code: 'search-type' }],
    searchParam: [{ name: 'identifier', type: 'token' }],
}

/** One person as `dhis2w_fhir_serve.patients.projection` publishes them: identity, and nothing else. */
const PATIENT = {
    resourceType: 'Patient',
    id: PERSON_UID,
    meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetPerson01' }] },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: PERSON_UID },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaNationId`, value: NATIONAL_ID },
    ],
    extension: [
        {
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaBirthDat' },
                { url: 'attributeCode', valueString: 'TEA_BIRTH_DATE' },
                { url: 'value', valueString: '1985-03-12' },
            ],
        },
    ],
}

/**
 * What that person is enrolled in.
 *
 * The one in this stage's own program is COMPLETED on purpose: DHIS2 accepts events into a
 * completed enrollment with no error and no warning (BUGS.md 70), so the warning the UI states is
 * the only place anyone is told, and a spec that only ever met ACTIVE enrollments would never see
 * it. The second is in another program, and is what proves the picker narrows.
 */
const ENROLLMENTS = {
    tracked_entity_uid: PERSON_UID,
    enrollments: [
        {
            enrollment_uid: COMPLETED_ENROLLMENT,
            program_uid: REGISTRATION_FORM,
            program_name: 'Antenatal care',
            status: 'COMPLETED',
            active: false,
            enrolled_at: '2026-02-01T00:00:00Z',
            organisation_unit_uid: 'DiszpKrYNg8',
            organisation_unit_name: 'Ngelehun CHC',
        },
        {
            enrollment_uid: OTHER_PROGRAM_ENROLLMENT,
            program_uid: 'IpHINAT79UW',
            program_name: null,
            status: 'ACTIVE',
            active: true,
            enrolled_at: '2026-05-14T00:00:00Z',
            organisation_unit_uid: 'O6uvpzGd5pu',
            organisation_unit_name: 'Bo',
        },
    ],
}

/**
 * Make this server look like a live one to the browser, and to the browser alone.
 *
 * `/metadata` is the real document with the Patient entry a live run would have added, so nothing
 * else the app reads off the conformance document changes. The two instance routes answer the
 * shapes the Python side emits. Everything else - the forms, `$generate`, the POST, the spool -
 * still goes to the real server.
 */
async function serveALiveInstance(page: Page): Promise<void> {
    await page.route('**/metadata', async (route) => {
        const response = await route.fetch()
        const document = (await response.json()) as { rest?: { resource?: unknown[] }[] }
        document.rest?.[0]?.resource?.push(PATIENT_CAPABILITY)
        await route.fulfill({ status: 200, contentType: FHIR_JSON, body: JSON.stringify(document) })
    })
    await page.route(
        (url) => url.pathname === '/Patient',
        (route) => {
            const identifier = new URL(route.request().url()).searchParams.get('identifier') ?? ''
            const matches = identifier === NATIONAL_ID || identifier === PERSON_UID
            return route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify({
                    resourceType: 'Bundle',
                    type: 'searchset',
                    total: matches ? 1 : 0,
                    entry: matches ? [{ resource: PATIENT, search: { mode: 'match' } }] : [],
                }),
            })
        },
    )
    await page.route('**/patients/*/enrollments', (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENROLLMENTS) }),
    )
}

/** Find the person, then choose them - the two gestures both pickers share. */
async function findAndChoose(page: Page): Promise<void> {
    await page.getByLabel('Identifier value').fill(NATIONAL_ID)
    const result = page.getByRole('button', { name: `Choose the person identified by ${NATIONAL_ID}` })
    await expect(result).toBeVisible()
    await result.click()
}

/** The parts of a stored receipt this file grades - the envelope, and which questions rode it. */
interface StoredReceipt {
    subject?: { identifier?: { value?: string } }
    extension?: { url: string; valueBoolean?: boolean; valueIdentifier?: { value?: string } }[]
    item?: { linkId: string }[]
}

/** The newest stored receipt answering one form, read off the real spool and then read back whole. */
async function newestReceipt(request: APIRequestContext, questionnaireId: string): Promise<StoredReceipt> {
    const listing = await request.get('/spool', { headers: { Accept: 'application/json' } })
    expect(listing.status(), await listing.text()).toBe(200)
    const spool = (await listing.json()) as {
        responses: { response_id: string; questionnaire_id?: string | null; received_at: string }[]
    }
    const rows = spool.responses.filter((row) => row.questionnaire_id === questionnaireId)
    expect(rows.length, `no receipt for ${questionnaireId}`).toBeGreaterThan(0)
    const newest = rows.toSorted((left, right) => right.received_at.localeCompare(left.received_at))[0]
    const stored = await request.get(`/QuestionnaireResponse/${newest.response_id}`, {
        headers: { Accept: FHIR_JSON },
    })
    expect(stored.status(), await stored.text()).toBe(200)
    return (await stored.json()) as StoredReceipt
}

/**
 * The compiled case, against the real server: the instance option is not offered at all.
 *
 * Not a disabled control and not a control that appears and then fails - nothing, with the reason
 * stated. A compiled facade holds no connection to a DHIS2 instance, `/metadata` says so ahead of
 * any request, and the picker is built on that statement rather than on a refusal.
 */
test.describe('a server that serves a compiled guide', () => {
    test('offers a new person and nothing else, and says why', async ({ page }) => {
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${REGISTRATION_FORM}`)
        await opened

        await expect(page.getByRole('radio', { name: 'New person' })).toBeChecked()
        await expect(page.getByRole('radio', { name: 'Find in this DHIS2 instance' })).toHaveCount(0)
        await expect(
            page.getByText(
                'This server answers from a compiled guide, so it holds no connection to a DHIS2 instance',
            ),
        ).toBeVisible()

        // And every question is asked, because no person has been chosen.
        await expect(page.getByLabel('National id')).toBeEnabled()
    })

    test('offers a stage form the spool receipts alone, with no source to choose between', async ({ page }) => {
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${STAGE_FORM}`)
        await opened

        await expect(page.getByLabel('Answering for')).toBeVisible()
        await expect(page.getByRole('radio', { name: 'Enrollments in this DHIS2 instance' })).toHaveCount(0)
        await expect(page.getByRole('radio', { name: 'Registrations captured on this server' })).toHaveCount(0)
    })
})

/**
 * Registering a person who is already in the instance - the whole flow.
 *
 * The submission that comes out of it is a different document from an ordinary registration in
 * three ways, and all three are asserted off the receipt the real server stored: the subject is the
 * person's real uid, the `D2SubjectExists` marker is on it, and no entity-level answer rides it.
 */
test.describe('a registration answering for a person the instance already holds', () => {
    test('finds them, locks what DHIS2 already holds, and marks the submission', async ({ page, request }) => {
        await serveALiveInstance(page)
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${REGISTRATION_FORM}`)
        await opened

        // Before anything is chosen this is an ordinary registration: every question is asked.
        await expect(page.getByLabel('National id')).toBeEnabled()

        await page.getByRole('radio', { name: 'Find in this DHIS2 instance' }).check()
        await expect(
            page.getByText('Searches the identifier values this DHIS2 instance holds'),
        ).toBeVisible()
        await findAndChoose(page)

        // The three questions DHIS2 writes onto the person are unanswerable, with the reason said.
        await expect(page.getByLabel('National id')).toBeDisabled()
        await expect(page.getByLabel('Date of birth')).toBeDisabled()
        await expect(
            page.getByText("This DHIS2 instance already holds this person's record"),
        ).toBeVisible()
        await expect(
            page.getByText('Not asked for a person this DHIS2 instance already holds').first(),
        ).toBeVisible()
        // The one question the program asks that the type does not collect still is.
        await expect(page.getByLabel('Household size')).toBeEnabled()

        // Their enrollments, as this instance holds them - and the warning the completed one earns,
        // because DHIS2 will take events into it and never say a word about that.
        const enrollments = page.getByTestId('patient-enrollments')
        await expect(enrollments).toContainText('Antenatal care')
        await expect(enrollments).toContainText('Completed')
        await expect(
            page.getByText('DHIS2 accepts new events into a completed enrollment without complaint'),
        ).toBeVisible()

        await page.getByLabel('Household size').fill('4')
        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        // The stored document, read back off the real spool: the three things that changed.
        const receipt = await newestReceipt(request, REGISTRATION_FORM)
        expect(receipt.subject?.identifier?.value).toBe(PERSON_UID)
        expect(receipt.extension?.some((extension) => extension.url.endsWith('/d2-subject-exists'))).toBe(true)
        expect(receipt.item?.map((item) => item.linkId)).toEqual(['TeaHousehld'])
    })

    test('goes back to a new person, and the questions come back with it', async ({ page }) => {
        await serveALiveInstance(page)
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${REGISTRATION_FORM}`)
        await opened

        await page.getByRole('radio', { name: 'Find in this DHIS2 instance' }).check()
        await findAndChoose(page)
        await expect(page.getByLabel('National id')).toBeDisabled()

        await page.getByRole('radio', { name: 'New person' }).check()
        await expect(page.getByLabel('National id')).toBeEnabled()
        await expect(page.getByTestId('patient-enrollments')).toHaveCount(0)
    })

    test('says so plainly when the instance holds nobody under what was typed', async ({ page }) => {
        await serveALiveInstance(page)
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${REGISTRATION_FORM}`)
        await opened

        await page.getByRole('radio', { name: 'Find in this DHIS2 instance' }).check()
        await page.getByLabel('Identifier value').fill('nobody-holds-this')

        await expect(
            page.getByText('This DHIS2 instance holds nobody under that identifier value.'),
        ).toBeVisible()
    })
})

/**
 * A stage form answering for an enrollment DHIS2 already holds.
 *
 * The spool source is the default and stays it; this is the addition. What it proves beyond the
 * search is the narrowing: the person's enrollment in another program is not offered, because DHIS2
 * refuses an event filed against one.
 */
test.describe('a stage form finding its enrollment in the instance', () => {
    test('offers this program’s enrollments only, warns on the completed one, and submits with it', async ({
        page,
        request,
    }) => {
        await serveALiveInstance(page)
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${STAGE_FORM}`)
        await opened

        await page.getByRole('radio', { name: 'Enrollments in this DHIS2 instance' }).check()
        await findAndChoose(page)

        const offered = page.getByTestId('instance-enrollments')
        await expect(offered).toContainText(COMPLETED_ENROLLMENT)
        // The other program's enrollment is not offered at all - not offered and refused later.
        await expect(offered).not.toContainText(OTHER_PROGRAM_ENROLLMENT)
        await expect(page.getByText('This enrollment is completed.')).toBeVisible()

        await page.getByRole('button', { name: `Answer for the enrollment ${COMPLETED_ENROLLMENT}` }).click()
        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()

        // The stored stage receipt names the instance's own pair, on both halves.
        const receipt = await newestReceipt(request, STAGE_FORM)
        expect(receipt.subject?.identifier?.value).toBe(PERSON_UID)
        expect(
            receipt.extension?.find((extension) => extension.url.endsWith('/d2-tracker-enrollment'))?.valueIdentifier
                ?.value,
        ).toBe(COMPLETED_ENROLLMENT)
    })
})

/**
 * The person-only form, captured against the real server.
 *
 * The kind whose whole submission is a person: a subject, an organisation unit, an `authored`
 * instant, and the attributes the tracked entity type collects. No enrollment anywhere - which is
 * what the receipt is checked for, because the absence is the point of the kind.
 */
test.describe('a person-only registration form', () => {
    test('opens with no enrollment to state, submits, and its receipt files no enrollment', async ({
        page,
        request,
    }) => {
        await page.goto('/#/forms')
        await page.getByTestId('forms-people').getByRole('row').filter({ hasText: 'Person' }).first().click()
        await expect(page).toHaveURL(new RegExp(`#/forms/${PERSON_FORM}$`))

        await expect(page.getByText('Person registration')).toBeVisible()
        // Nothing about an enrollment, because this form enrols nobody: no "Answering for" picker,
        // and none of the read-only enrollment facts a tracker registration states.
        await expect(page.getByLabel('Answering for')).toHaveCount(0)
        await expect(page.getByRole('heading', { name: 'Enrollment', exact: true })).toHaveCount(0)
        // The organisation unit is still asked, because DHIS2 files the person under one.
        await expect(page.getByText('The organisation unit this person is registered at')).toBeVisible()

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()
        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        const listed = page.getByRole('row').filter({ hasText: 'Person registration' }).first()
        await expect(listed).toBeVisible()
        await listed.click()

        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
        await expect(page.getByText('Tracked entity', { exact: true })).toBeVisible()
        await expect(page.getByText('Organisation unit', { exact: true })).toBeVisible()
        await expect(page.getByText('Enrolled at', { exact: true })).toHaveCount(0)

        const receipt = await newestReceipt(request, PERSON_FORM)
        expect(receipt.subject?.identifier?.value).toBeTruthy()
        expect(receipt.extension?.some((extension) => extension.url.endsWith('/d2-tracker-enrollment'))).toBe(false)
    })
})

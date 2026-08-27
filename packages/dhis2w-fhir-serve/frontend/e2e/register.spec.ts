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
 * `/Patient` and `/facade/tracked-entities/{uid}/enrollments` answer the shapes
 * `dhis2w_fhir_serve.register.projection` and `routes.enrollments` emit, which the pytest suite
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

/** A second person, so that "the listing pages" is a claim with two pages behind it. */
const SECOND_PERSON_UID = 'TeiPerson02'
const SECOND_NATIONAL_ID = '19910704-2210'

/** The DHIS2 instance the browse page pretends this server resolved a profile for. */
const INSTANCE = 'https://dhis2.test/instance'

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

/** One person as `dhis2w_fhir_serve.register.projection` publishes them: identity, and nothing else. */
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
        // Two more values than a row shows, so which ones it shows is a choice rather than an
        // accident of order: the guide's `D2TEA_CS` marks the date of birth and the sex as
        // belonging in a listing, and the household size as not.
        {
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaHousehld' },
                { url: 'value', valueString: '4' },
            ],
        },
        {
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaSex00001' },
                { url: 'attributeCode', valueString: 'TEA_SEX' },
                { url: 'value', valueString: 'OpFemale001' },
            ],
        },
    ],
}

/**
 * The second person, holding one unique value and one attribute the type collects rather than names.
 *
 * `TeaHousehld` carries no `attributeCode`, because DHIS2 requires no code on a tracked entity
 * attribute - so this is also the case where the guide's own dictionary is the only thing that can
 * name the attribute at all.
 */
const SECOND_PATIENT = {
    resourceType: 'Patient',
    id: SECOND_PERSON_UID,
    meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetPerson01' }] },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: SECOND_PERSON_UID },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaNationId`, value: SECOND_NATIONAL_ID },
    ],
    extension: [
        {
            url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
            extension: [
                { url: 'attributeId', valueString: 'TeaHousehld' },
                { url: 'value', valueString: '6' },
            ],
        },
    ],
}

/** Everyone the fulfilled instance holds, one per page - the order the listing pages through. */
const PEOPLE = [PATIENT, SECOND_PATIENT]

/**
 * One tracked entity of a type this guide publishes as something other than a person.
 *
 * The projection is the same projection - the tracked entity uid, the values of the attributes DHIS2
 * declares unique, the rest as extensions - because `dhis2w_fhir_serve.register.projection` states
 * nothing a `Specimen` defines. There is no `Specimen.type` here and no `collection`, and that
 * absence is the point: DHIS2 holds no such field, so this server invents none.
 */
const SPECIMEN_UID = 'TeiSample01'
const LAB_REFERENCE = 'LAB-2026-0042'
const SPECIMEN = {
    resourceType: 'Specimen',
    id: SPECIMEN_UID,
    meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetSample01' }] },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: SPECIMEN_UID },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaLabRef01`, value: LAB_REFERENCE },
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
        (url) => url.pathname === '/Patient' || url.pathname.startsWith('/Patient/'),
        (route) => {
            const url = new URL(route.request().url())
            if (url.pathname !== '/Patient') {
                const uid = decodeURIComponent(url.pathname.slice('/Patient/'.length))
                const held = PEOPLE.find((candidate) => candidate.id === uid)
                return held === undefined
                    ? route.fulfill({
                          status: 404,
                          contentType: FHIR_JSON,
                          body: JSON.stringify({
                              resourceType: 'OperationOutcome',
                              issue: [
                                  {
                                      severity: 'error',
                                      code: 'not-found',
                                      diagnostics: `This DHIS2 instance holds no tracked entity ${uid}.`,
                                  },
                              ],
                          }),
                      })
                    : route.fulfill({ status: 200, contentType: FHIR_JSON, body: JSON.stringify(held) })
            }
            const identifier = url.searchParams.get('identifier')
            if (identifier !== null) {
                const found = PEOPLE.filter(
                    (candidate) =>
                        candidate.id === identifier ||
                        candidate.identifier.some((value) => value.value === identifier),
                )
                return route.fulfill({
                    status: 200,
                    contentType: FHIR_JSON,
                    body: JSON.stringify({
                        resourceType: 'Bundle',
                        type: 'searchset',
                        total: found.length,
                        entry: found.map((resource) => ({ resource, search: { mode: 'match' } })),
                    }),
                })
            }
            return route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify(listingPage(url.searchParams.get('page'))),
            })
        },
    )
    await page.route('**/tracked-entities/*/enrollments', (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ENROLLMENTS) }),
    )
    await page.route('**/tracked-entities/*/events**', (route) =>
        route.fulfill({ status: 200, contentType: FHIR_JSON, body: JSON.stringify(EVENTS) }),
    )
}

/** When the one event this person's record holds happened, as DHIS2 dates it. */
const EVENT_AT = '2026-02-14T00:00:00Z'

/**
 * What one person has been through, as `GET /facade/tracked-entities/{uid}/events` answers it.
 *
 * One QuestionnaireResponse per DHIS2 event, carrying the stage form it answered and the date -
 * which are the two facts the record renders. The answers ride along in the real shape and are not
 * shown: a listing of visits is not a stack of filled-in forms.
 */
const EVENTS = {
    resourceType: 'Bundle',
    type: 'searchset',
    total: 1,
    link: [{ relation: 'self', url: `/facade/tracked-entities/${PERSON_UID}/events?_count=20` }],
    entry: [
        {
            resource: {
                resourceType: 'QuestionnaireResponse',
                id: 'EvtAncVis01',
                questionnaire: `${CANONICAL}/Questionnaire/${STAGE_FORM}`,
                status: 'completed',
                authored: EVENT_AT,
                subject: {
                    type: 'Patient',
                    identifier: { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: PERSON_UID },
                },
                extension: [
                    {
                        url: `${CANONICAL}/StructureDefinition/d2-tracker-enrollment`,
                        valueIdentifier: {
                            system: `${IDENTIFIER_BASE}/id/tracker-enrollment`,
                            value: COMPLETED_ENROLLMENT,
                        },
                    },
                ],
            },
            search: { mode: 'match' },
        },
    ],
}

/**
 * One page of the listing, keyed on the opaque token the previous page's link carried.
 *
 * One person per page, which is what makes both directions provable in two clicks. The tokens are
 * deliberately not offsets: what the UI has to get right is that it echoes whatever it was handed,
 * and a token that looked like an index would let a wrong implementation pass by computing one.
 */
function listingPage(token: string | null): unknown {
    const onSecond = token === 'a-token-the-server-minted'
    const resource = onSecond ? SECOND_PATIENT : PATIENT
    return {
        resourceType: 'Bundle',
        type: 'searchset',
        total: PEOPLE.length,
        link: onSecond
            ? [
                  { relation: 'self', url: '/Patient?_count=25&page=a-token-the-server-minted' },
                  { relation: 'previous', url: '/Patient?_count=25&page=another-one-entirely' },
              ]
            : [
                  { relation: 'self', url: '/Patient?_count=25' },
                  { relation: 'next', url: '/Patient?_count=25&page=a-token-the-server-minted' },
              ],
        entry: [{ resource, search: { mode: 'match' } }],
    }
}

/** The register a project tracking only people serves: one resource, one type, named Person. */
const PEOPLE_REGISTER = { resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Person' }] }

/**
 * What the register is called on a run serving that one type, and on one serving two.
 *
 * The instance's own name for the type, which is what the people running the server say - never
 * "Patients", which is the FHIR resource this project projects a person onto rather than the
 * subject. Two types have no single name, so that run is led to by the register itself.
 */
const ONE_TYPE_TITLE = 'Person'
const REGISTER_TITLE = 'Tracked entities'

/** The register's entry, found by where it leads - the one thing about it no naming rule changes. */
const REGISTER_NAV_LINK = 'a[href="#/tracked-entities"]'

/** The second register the fixture project publishes - a type this guide takes onto Specimen. */
const SPECIMEN_REGISTER = { resource: 'Specimen', types: [{ uid: 'TetSample01', name: 'Specimen batch' }] }

/**
 * The register a project taking two tracked entity types onto ONE FHIR resource publishes.
 *
 * One resource is one register over the union of the types the published map takes onto it, and this
 * is the run where that matters: `/Patient` answers about people and about specimen batches alike,
 * and `_tag` is how a caller asks it about one of them. The names are the instance's own, which is
 * what the chips read; the sections are still one per resource, so this run has one section.
 */
const UNION_REGISTER = {
    resource: 'Patient',
    types: [
        { uid: 'TetPerson01', name: 'Person' },
        { uid: 'TetSample01', name: 'Specimen batch' },
    ],
}

/** A tracked entity of that second type, served under the same resource as the people beside it. */
const UNION_SPECIMEN_UID = 'TeiSample02'
const UNION_LAB_REFERENCE = 'LAB-2026-0043'
const UNION_SPECIMEN = {
    resourceType: 'Patient',
    id: UNION_SPECIMEN_UID,
    meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetSample01' }] },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: UNION_SPECIMEN_UID },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaLabRef01`, value: UNION_LAB_REFERENCE },
    ],
}

/**
 * Answer `/Patient` as a register over two tracked entity types does, `_tag` and all.
 *
 * Registered after `serveALiveInstance`, so it takes the route over: Playwright matches the most
 * recently added handler first. The narrowing is done here rather than asserted on the request alone
 * because the page has to be shown to change - a `_tag` that reached the server and narrowed nothing
 * would pass a request-only assertion.
 */
async function serveAUnionRegister(page: Page): Promise<void> {
    const held = [PATIENT, UNION_SPECIMEN]
    await page.route(
        (url) => url.pathname === '/Patient',
        (route) => {
            const url = new URL(route.request().url())
            const tags = url.searchParams.getAll('_tag')
            const identifier = url.searchParams.get('identifier')
            const matching = held.filter(
                (candidate) =>
                    (tags.length === 0 || tags.includes(candidate.meta.tag[0].code)) &&
                    (identifier === null ||
                        candidate.id === identifier ||
                        candidate.identifier.some((value) => value.value === identifier)),
            )
            return route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify({
                    resourceType: 'Bundle',
                    type: 'searchset',
                    total: matching.length,
                    link: [{ relation: 'self', url: '/Patient?_count=25' }],
                    entry: matching.map((resource) => ({ resource, search: { mode: 'match' } })),
                }),
            })
        },
    )
}

/**
 * Answer `/facade/uiconfig` with what this run offers about the instance's tracked entities.
 *
 * Fulfilled for the same reason uiconfig.spec.ts fulfils it: the suite drives ONE server process,
 * and "a run that offers no register" and "a run that offers one" cannot both be true of it. The
 * endpoint only ever reported how the process was started, so starting it differently is what is
 * being simulated here. What the server really answers is held by the pytest suite over the route.
 *
 * `registers` defaults to the people-only shape, because that is the deployment every test here was
 * written against and the one whose screens must not change a word.
 */
async function serveRegisterSettings(
    page: Page,
    tracked_entities: { enabled: boolean; listing: boolean; registers?: unknown[] } | null,
): Promise<void> {
    const stated =
        tracked_entities === null
            ? null
            : { registers: [PEOPLE_REGISTER], ...tracked_entities }
    await page.route('**/uiconfig', (route) =>
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ basemaps: [], dhis2_base_url: INSTANCE, tracked_entities: stated }),
        }),
    )
}

/** Answer `/Specimen` the way the register does for a type published as something other than a person. */
async function serveSpecimens(page: Page): Promise<void> {
    await page.route(
        (url) => url.pathname === '/Specimen',
        (route) =>
            route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify({
                    resourceType: 'Bundle',
                    type: 'searchset',
                    total: 1,
                    link: [{ relation: 'self', url: '/Specimen?_count=25' }],
                    entry: [{ resource: SPECIMEN, search: { mode: 'match' } }],
                }),
            }),
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
    const listing = await request.get('/facade/spool', { headers: { Accept: 'application/json' } })
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
 * stated. A compiled facade publishes no search over any register, `/metadata` says so ahead of
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
            page.getByText("This server publishes no search over this form's register"),
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
        // The reason is written about the record rather than about a person, because the register
        // decides the word and a project registering focus areas holds no people at all.
        await expect(
            page.getByText('This DHIS2 instance already holds this record'),
        ).toBeVisible()
        await expect(
            page.getByText('Not asked for a record this DHIS2 instance already holds').first(),
        ).toBeVisible()
        // The one question the program asks that the type does not collect still is.
        await expect(page.getByLabel('Household size')).toBeEnabled()

        // Their enrollments, as this instance holds them - and the warning the completed one earns,
        // because DHIS2 will take events into it and never say a word about that.
        const enrollments = page.getByTestId('patient-enrollments')
        await expect(enrollments).toContainText('Antenatal care')
        await expect(enrollments).toContainText('Completed')
        await expect(
            page.getByText('This DHIS2 instance accepts new events into a completed enrollment'),
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
        await page.getByTestId('forms-people').getByRole('link').filter({ hasText: 'Person' }).first().click()
        await expect(page).toHaveURL(new RegExp(`#/forms/${PERSON_FORM}$`))

        // The form first, then what it says it is. The listing this click came from carries the same
        // "Registration" badge on every person-only card, so reading the kind before the form has
        // actually taken the screen reads the listing behind it rather than the form in front.
        await expect(page.getByRole('button', { name: 'Fill with test data' })).toBeVisible()
        await expect(page.getByText('Registration', { exact: true })).toBeVisible()
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

        // Exact text, not a substring: the kind badge reads "Registration", and a substring match
        // would take the "Tracker registration" row this file captures a few tests earlier.
        const listed = page
            .getByRole('row')
            .filter({ has: page.getByText('Registration', { exact: true }) })
            .first()
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

/**
 * Browsing the people the instance holds - the one page in this app that reads somebody's database.
 *
 * THE SETTINGS ARE FULFILLED AND THE GUIDE IS REAL, which is the split that makes these claims
 * worth making. `/facade/uiconfig` and the person routes answer here, because the fixture server holds no
 * DHIS2 instance; everything the page joins those answers to is read from the real server - the
 * published `D2TEA_CS` is what turns `TeaBirthDat` into "Date of birth", and the real person-only
 * form is what turns `TetPerson01` into "Person". So a naming join that broke against what the
 * emitter really publishes fails here rather than passing against a fixture of itself.
 */
test.describe('the people this DHIS2 instance holds', () => {
    test('is not in the navigation at all on a run that states nothing about people', async ({ page }) => {
        await serveRegisterSettings(page, null)

        // Waited for rather than assumed: an entry that is absent because the settings have not
        // landed yet would make this assertion true of a page that was about to draw one.
        const stated = page.waitForResponse((response) => response.url().includes('/uiconfig'))
        await page.goto('/')
        await stated
        await expect(page.getByRole('link', { name: 'Forms' }).first()).toBeVisible()
        // Found by where it leads rather than by what it is called: what this run would have named
        // the entry is another test's subject, and a project publishing a form titled for its type
        // has that word on the page for reasons that are nothing to do with the register.
        await expect(page.locator(REGISTER_NAV_LINK)).toHaveCount(0)

        // And a link somebody kept from a run that did offer it is answered where it was opened,
        // in this server's own words - the refusal `GET /Patient` really states on this process,
        // read off the real server rather than composed in the browser.
        await page.goto('/#/tracked-entities')
        await expect(page).toHaveURL(/#\/tracked-entities$/)
        await expect(page.getByTestId('register-not-served')).toContainText(
            'This facade serves a compiled implementation guide',
        )
    })

    test('answers a link to one record with the same refusal, rather than an empty page', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: false, listing: false })

        await page.goto(`/#/tracked-entities/Patient/${PERSON_UID}`)
        await expect(page.getByTestId('register-not-served')).toContainText(
            'holds no register to search',
        )
    })

    test('is not in the navigation on a run that states it offers no people', async ({ page }) => {
        // The ordinary compiled case, stated rather than left out: the same outcome, and the one
        // the server really answers with.
        await serveRegisterSettings(page, { enabled: false, listing: false })

        const stated = page.waitForResponse((response) => response.url().includes('/uiconfig'))
        await page.goto('/')
        await stated
        await expect(page.getByRole('link', { name: 'Forms' }).first()).toBeVisible()
        await expect(page.locator(REGISTER_NAV_LINK)).toHaveCount(0)
    })

    test('pages through everyone, forwards and back, on the links the server stated', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/')
        await page.getByRole('link', { name: ONE_TYPE_TITLE }).first().click()
        await expect(page).toHaveURL(/#\/tracked-entities$/)

        const listing = page.getByTestId('patient-listing')
        const first = listing.getByRole('row').filter({ hasText: NATIONAL_ID })
        await expect(first).toBeVisible()
        // The join through the published guide, in the header: the dictionary is what turns
        // `TeaBirthDat` into "Date of birth", and that name is nowhere in what the instance
        // answered. The cell under it holds the value alone, because the column already said what
        // the value is a value of.
        await expect(listing.getByRole('columnheader', { name: 'Date of birth' })).toBeVisible()
        await expect(first).toContainText('1985-03-12')
        await expect(first).toContainText(PERSON_UID)
        // Stated once. The summary bar at the foot of the window is where this page's count lives,
        // and the section repeating it three lines above the bar was one sentence stacked on itself.
        await expect(page.getByTestId('status-bar-summary')).toContainText(
            'Showing 1 of 2 people this DHIS2 instance holds as tracked entities.',
        )
        await expect(
            page
                .getByTestId('page-content')
                .getByText('Showing 1 of 2 people this DHIS2 instance holds as tracked entities.'),
        ).toHaveCount(0)

        const previous = page.getByRole('button', { name: 'Previous' })
        const next = page.getByRole('button', { name: 'Next' })
        // Disabled because the server stated no link that way, not because a count was computed.
        await expect(previous).toBeDisabled()
        await expect(next).toBeEnabled()

        await next.click()
        const second = listing.getByRole('row').filter({ hasText: SECOND_NATIONAL_ID })
        await expect(second).toBeVisible()
        // The attribute DHIS2 left uncoded is still named, because the guide published a name for it.
        await expect(listing.getByRole('columnheader', { name: 'Household size' })).toBeVisible()
        await expect(second).toContainText('6')
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toHaveCount(0)
        await expect(previous).toBeEnabled()
        await expect(next).toBeDisabled()

        await previous.click()
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: SECOND_NATIONAL_ID })).toHaveCount(0)
    })

    test('narrows to whoever holds the identifier value that was typed', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')
        const listing = page.getByTestId('patient-listing')
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()

        await page.getByLabel('Identifier value').fill(SECOND_NATIONAL_ID)

        // The table is the one surface for people on this page, so a search replaces the page of
        // everyone rather than appearing beside it.
        await expect(listing.getByRole('row').filter({ hasText: SECOND_NATIONAL_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toHaveCount(0)
        await expect(page.getByRole('button', { name: 'Next' })).toHaveCount(0)

        await page.getByLabel('Identifier value').fill('')
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()
    })

    test('opens one person in full, with what the instance holds and what it has them in', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto(`/#/tracked-entities/Patient/${PERSON_UID}`)

        // Headed by the value that names them, because there is no name to head it with.
        await expect(page.getByRole('heading', { name: NATIONAL_ID })).toBeVisible()

        // The way back is labelled with the heading of the page it returns to - this instance's own
        // name for the type it serves - rather than with the FHIR resource the projection uses.
        await expect(page.getByRole('link', { name: 'Person' }).last()).toBeVisible()
        await expect(page.getByRole('link', { name: /patients/i })).toHaveCount(0)

        const identifiers = page.getByRole('table').first()
        await expect(identifiers).toContainText('National identifier')
        await expect(identifiers).toContainText(NATIONAL_ID)

        const attributes = page.getByRole('table').nth(1)
        await expect(attributes).toContainText('Date of birth')
        await expect(attributes).toContainText('1985-03-12')

        // Their enrollments, and the warning the completed one earns - DHIS2 takes events into it
        // and says nothing, so this sentence is the only place anybody is told.
        const enrollments = page.getByTestId('patient-enrollments')
        await expect(enrollments).toContainText('Antenatal care')
        await expect(enrollments).toContainText('Completed')
        await expect(
            page.getByText('This DHIS2 instance accepts new events into a completed enrollment'),
        ).toBeVisible()

        // And what they have been through, which is the third thing this server answers about one
        // subject: one row per DHIS2 event, named by the published title of the stage form it
        // answered - the uid the response carries is nowhere near a name on its own.
        const events = page.getByTestId('tracked-entity-events')
        await expect(events).toContainText('ANC follow-up - ANC visit')
        await expect(events).toContainText('EvtAncVis01')

        // The way into the instance: Capture's enrollment dashboard, which is the screen that opens
        // a person - and it needs the program and the enrollment, which this listing states.
        const link = page.getByRole('link', {
            name: `Open the enrollment ${COMPLETED_ENROLLMENT} in this DHIS2 instance's Capture app`,
        })
        await expect(link).toHaveAttribute(
            'href',
            `${INSTANCE}/dhis-web-capture/index.html#/enrollment` +
                `?teiId=${PERSON_UID}&programId=${REGISTRATION_FORM}&orgUnitId=DiszpKrYNg8&enrollmentId=${COMPLETED_ENROLLMENT}`,
        )
        await expect(link).toHaveAttribute('target', '_blank')
        await expect(link).toHaveAttribute('rel', 'noreferrer noopener')
    })

    test('a row answers over the listing, and Esc gives the listing back', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')
        const row = page.getByTestId('patient-listing').getByRole('row').filter({ hasText: NATIONAL_ID })
        await row.click()

        // The address says which quick view is open, so a reload or a sent link opens on the same
        // record - and shutting it gives the bare listing address back.
        await expect(page).toHaveURL(/#\/tracked-entities\?open=Patient%3ATeiPerson01$/)
        const sheet = page.getByTestId('tracked-entity-sheet')
        // Headed by the value that names them, with the instance's own word for what they are.
        await expect(sheet.getByRole('heading', { name: NATIONAL_ID })).toBeVisible()
        await expect(sheet).toContainText('Person')
        // The same record the page shows, read through the same sections.
        await expect(sheet).toContainText('National identifier')
        await expect(page.getByTestId('patient-enrollments')).toContainText('Antenatal care')
        await expect(page.getByTestId('tracked-entity-events')).toContainText('ANC follow-up - ANC visit')

        await page.keyboard.press('Escape')
        await expect(sheet).toHaveCount(0)
        await expect(page).toHaveURL(/#\/tracked-entities$/)
        await expect(row).toBeFocused()
    })

    test('the quick view carries the served document, as the receipt panel does', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')
        await page.getByTestId('patient-listing').getByRole('row').filter({ hasText: NATIONAL_ID }).click()

        // The document behind the reading, at the foot of the panel - the same control the receipt
        // panel carries, named for the resource this register is answered from.
        const sheet = page.getByTestId('tracked-entity-sheet')
        await sheet.getByRole('button', { name: 'Raw Patient' }).click()
        await expect(page.getByTestId('raw-patient')).toContainText('"resourceType": "Patient"')
    })

    test('Back shuts the quick view and leaves the listing where it was', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')
        await page.getByTestId('patient-listing').getByRole('row').filter({ hasText: NATIONAL_ID }).click()
        await expect(page).toHaveURL(/#\/tracked-entities\?open=Patient%3ATeiPerson01$/)

        // Opening a quick view is a place a reader went, so the browser's own way back out of it
        // works - and because the whole state is in the address, the listing comes back with it.
        await page.goBack()

        await expect(page.getByTestId('tracked-entity-sheet')).toHaveCount(0)
        await expect(page).toHaveURL(/#\/tracked-entities$/)
        await expect(page.getByTestId('patient-listing')).toContainText(NATIONAL_ID)
    })

    test('a keyboard user opens the same quick view, and it carries the way to the record', async ({
        page,
    }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')
        await page.getByTestId('patient-listing').getByRole('row').filter({ hasText: NATIONAL_ID }).focus()
        await page.keyboard.press('Enter')

        await expect(page.getByTestId('tracked-entity-sheet')).toBeVisible()
        // A record is a thing somebody links to, so the sheet carries the way to its own address -
        // opened in its own tab, keeping the listing and the reader's place. Asserted off the
        // link itself rather than followed: this spec's server is a per-page mock, and a fresh tab
        // would open against nothing.
        const fullPageLink = page.getByRole('link', { name: 'Open the full page' })
        await expect(fullPageLink).toHaveAttribute(
            'href',
            new RegExp(`#/tracked-entities/Patient/${PERSON_UID}$`),
        )
        await expect(fullPageLink).toHaveAttribute('target', '_blank')
    })

    test('keeps the search and asks for no listing at all when this run declines one', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: false })
        await serveALiveInstance(page)

        const listingReads: string[] = []
        page.on('request', (request) => {
            const url = new URL(request.url())
            if (url.pathname === '/Patient' && !url.searchParams.has('identifier')) {
                listingReads.push(request.url())
            }
        })

        await page.goto('/#/tracked-entities')
        await expect(page.getByLabel('Identifier value')).toBeVisible()
        await expect(
            page.getByText('This server answers a search for one person and does not list everyone'),
        ).toBeVisible()
        await expect(page.getByTestId('patient-listing')).toHaveCount(0)

        // The search still reaches the instance, and the listing was never asked for - not asked
        // and hidden, which is what makes the setting a gate rather than a style.
        await page.getByLabel('Identifier value').fill(NATIONAL_ID)
        await expect(page.getByTestId('patient-listing').getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()
        expect(listingReads, listingReads.join('\n')).toEqual([])
    })
    test('is named for the one type it serves, in the rail and on the page alike', async ({
        page,
    }) => {
        // NAME THE ACTUAL SUBJECT. A run serving one tracked entity type is led to by the instance's
        // own name for it, and headed by the same - one name from one rule, so the header bar and the
        // page cannot disagree. There is no section heading over the single table, because it would
        // repeat the page title; and the description still says these are people, which is a fact
        // about the resource served rather than about its name.
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')

        await expect(page.getByRole('link', { name: ONE_TYPE_TITLE }).first()).toBeVisible()
        await expect(page.getByRole('heading', { name: ONE_TYPE_TITLE, level: 2 })).toBeVisible()
        await expect(
            page.getByText('The people this DHIS2 instance holds.', {
                exact: false,
            }),
        ).toBeVisible()
        // Never the FHIR resource this project projects a person onto, and never DHIS2's word for
        // the whole family while this run tracks one member of it.
        await expect(page.getByRole('link', { name: 'Patients' })).toHaveCount(0)
        await expect(page.getByRole('heading', { name: REGISTER_TITLE })).toHaveCount(0)

        // And nothing to choose between: one type is not a filter, and a row that stated the type
        // would state the page's own title once per person.
        await expect(page.getByTestId('register-type-filter')).toHaveCount(0)
        await expect(page.getByTestId('patient-listing')).not.toContainText('Tracked entity type')
    })

    test('offers the types a union register serves, and narrows the whole page to one', async ({ page }) => {
        // ONE RESOURCE IS ONE REGISTER OVER THE UNION OF ITS TRACKED ENTITY TYPES. The chips are the
        // server's own declaration of that union - `/facade/uiconfig` names the types and `/metadata`
        // documents the same set under `_tag` - and choosing one narrows the listing, the search, and
        // the address alike, because they are three views of one register rather than three filters.
        await serveRegisterSettings(page, { enabled: true, listing: true, registers: [UNION_REGISTER] })
        await serveALiveInstance(page)
        await serveAUnionRegister(page)

        await page.goto('/#/tracked-entities')

        const filter = page.getByTestId('register-type-filter')
        const listing = page.getByTestId('patient-listing')
        await expect(filter.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true')
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: UNION_LAB_REFERENCE })).toBeVisible()
        // Two types on screen, so every row says which it is - joined through the person-only forms
        // the real guide publishes, not through anything the instance answered.
        await expect(listing.getByRole('columnheader', { name: 'Tracked entity type' })).toBeVisible()
        await expect(listing).toContainText('Specimen batch')

        const narrowed = page.waitForRequest(
            (request) => new URL(request.url()).searchParams.get('_tag') === 'TetSample01',
        )
        await filter.getByRole('button', { name: 'Specimen batch' }).click()
        await narrowed

        // A narrowed register is a link somebody can be sent, beside whatever is being searched for.
        await expect(page).toHaveURL(/type=TetSample01/)
        await expect(filter.getByRole('button', { name: 'Specimen batch' })).toHaveAttribute(
            'aria-pressed',
            'true',
        )
        await expect(listing.getByRole('row').filter({ hasText: UNION_LAB_REFERENCE })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toHaveCount(0)
        // One type on every row now, and the chip above the table already says which - so the column
        // that would repeat it is not drawn.
        await expect(listing.getByRole('columnheader', { name: 'Tracked entity type' })).toHaveCount(0)

        // The search rides the narrowing too: it answers about the same register, and an answer
        // about a type the table is not showing would disagree with the page it is on.
        const searched = page.waitForRequest((request) => {
            const parameters = new URL(request.url()).searchParams
            return parameters.get('identifier') === UNION_LAB_REFERENCE && parameters.get('_tag') === 'TetSample01'
        })
        await page.getByLabel('Identifier value').fill(UNION_LAB_REFERENCE)
        await searched
        await expect(listing.getByRole('row').filter({ hasText: UNION_LAB_REFERENCE })).toBeVisible()
    })

    test('opens on the type the address named, and lets go of it again', async ({ page }) => {
        await serveRegisterSettings(page, { enabled: true, listing: true, registers: [UNION_REGISTER] })
        await serveALiveInstance(page)
        await serveAUnionRegister(page)

        await page.goto('/#/tracked-entities?type=TetPerson01')

        const filter = page.getByTestId('register-type-filter')
        const listing = page.getByTestId('patient-listing')
        await expect(filter.getByRole('button', { name: 'Person' })).toHaveAttribute('aria-pressed', 'true')
        await expect(listing.getByRole('row').filter({ hasText: NATIONAL_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: UNION_LAB_REFERENCE })).toHaveCount(0)

        await filter.getByRole('button', { name: 'All' }).click()
        await expect(listing.getByRole('row').filter({ hasText: UNION_LAB_REFERENCE })).toBeVisible()
        await expect(page).not.toHaveURL(/type=/)
    })

    test('becomes the register the instance actually holds when a type is not a person', async ({
        page,
    }) => {
        // Two resources, one page: the navigation entry stops claiming everything here is a person,
        // and each section is titled by the names the instance holds for the types riding it -
        // never by the FHIR resource type, which is this project's projection rather than DHIS2's
        // word for the thing.
        await serveRegisterSettings(page, {
            enabled: true,
            listing: true,
            registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER],
        })
        await serveALiveInstance(page)
        await serveSpecimens(page)

        await page.goto('/#/tracked-entities')

        await expect(page.getByRole('link', { name: REGISTER_TITLE }).first()).toBeVisible()
        await expect(page.getByRole('link', { name: 'Patients' })).toHaveCount(0)
        // One type's name cannot stand for two, so the page is the register - and the sections
        // inside it are where each type is named.
        await expect(page.getByRole('heading', { name: REGISTER_TITLE, level: 2 })).toBeVisible()
        await expect(page.getByRole('heading', { name: 'Person', level: 2 })).toBeVisible()
        await expect(page.getByRole('heading', { name: 'Specimen batch', level: 2 })).toBeVisible()
        // The Specimen section holds the row the Specimen route answered, with its own identifier
        // value - so the two sections are two reads rather than one listing shown twice.
        await expect(page.getByText(LAB_REFERENCE)).toBeVisible()
        await expect(page.getByText(NATIONAL_ID).first()).toBeVisible()
    })

    test('gives every attribute a column, in the order DHIS2 states it wants them listed', async ({ page }) => {
        // ONE COLUMN PER ATTRIBUTE, NAMED ONCE. The names come off the published `D2TEA_CS`, the
        // cells hold the values alone, and nothing on a row is hidden behind a phrase nobody can act
        // on. WHICH ORDER IS DHIS2'S CHOICE: an administrator marks the attributes that let a clerk
        // recognise somebody, so those lead - and it is the order that decides which columns survive
        // the cap on a record holding more attributes than a table can hold side by side.
        await serveRegisterSettings(page, { enabled: true, listing: true })
        await serveALiveInstance(page)

        await page.goto('/#/tracked-entities')

        const listing = page.getByTestId('patient-listing')
        const row = listing.getByRole('row').filter({ hasText: NATIONAL_ID })
        await expect(row).toBeVisible()
        // The whole header, in order: the identifier values these people hold, the uid, and then the
        // two marked attributes ahead of the one the instance states no preference about. No
        // "Tracked entity type" column, because this run serves one type and every row would repeat
        // it.
        expect(await listing.getByRole('columnheader').allTextContents()).toEqual([
            'Identifier values',
            'Tracked entity',
            'Date of birth',
            'Sex',
            'Household size',
        ])
        await expect(row).toContainText('1985-03-12')
        await expect(row).not.toContainText('and 1 more')

        // The record keeps showing everything: a table capped at what can be read side by side is
        // not a claim that the rest is not held. Scoped to the sheet, because the listing's own
        // column headers carry these names too - and they are the columns, not the values.
        await row.click()
        const sheet = page.getByTestId('tracked-entity-sheet')
        await expect(sheet.getByRole('heading', { name: 'Attribute values' })).toBeVisible()
        await expect(sheet.getByText('Household size')).toBeVisible()
        await expect(sheet.getByText('Date of birth')).toBeVisible()
    })

    test('opens a specimen batch under its own resource, and says nothing about person-hood', async ({
        page,
    }) => {
        await serveRegisterSettings(page, {
            enabled: true,
            listing: true,
            registers: [PEOPLE_REGISTER, SPECIMEN_REGISTER],
        })
        await serveALiveInstance(page)
        await serveSpecimens(page)
        await page.route(
            (url) => url.pathname === `/Specimen/${SPECIMEN_UID}`,
            (route) =>
                route.fulfill({ status: 200, contentType: FHIR_JSON, body: JSON.stringify(SPECIMEN) }),
        )

        await page.goto(`/#/tracked-entities/Specimen/${SPECIMEN_UID}`)

        await expect(page.getByRole('heading', { name: LAB_REFERENCE, level: 2 })).toBeVisible()
        // Two types ride this run, so the listing is headed "Tracked entities" and the link back
        // to it says the same thing. Never "patients": this row is a specimen batch.
        await expect(page.getByRole('link', { name: 'Tracked entities' }).last()).toBeVisible()
        // Worded from the tracked entity type the badge above already states - the instance's own
        // name for it - rather than from the resource in the route, which is the projection.
        await expect(
            page.getByText('which are what name this Specimen batch', { exact: false }),
        ).toBeVisible()
        // The page never calls it a person, which is the whole reason the copy follows the type.
        await expect(page.getByText('name this person', { exact: false })).toHaveCount(0)
    })
})

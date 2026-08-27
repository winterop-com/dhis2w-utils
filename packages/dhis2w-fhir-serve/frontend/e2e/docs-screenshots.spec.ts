import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * The screenshot producer for `docs/fhir/201-capture-ui.md` - NOT a test.
 *
 * SKIPPED BY DEFAULT. This file asserts nothing the other specs do not already
 * prove; its whole output is the PNGs under `docs/img/fhir/`, and CI has no
 * business rewriting documentation images on every run. To re-shoot them:
 *
 *     cd packages/dhis2w-fhir-serve/frontend
 *     pnpm build                                # the bundle `--ui` serves
 *     DOCS_SCREENSHOTS=1 pnpm exec playwright test e2e/docs-screenshots.spec.ts
 *
 * Run it exactly like that - alone, not as part of the full suite. The fixture
 * builder empties the spool when the webServer starts, this file posts a known
 * set of receipts from fixed `$generate` seeds, and the Overview's counts are
 * therefore the same on every shoot. Ran inside the full suite, the other
 * specs' receipts would be in the counts too. (`reuseExistingServer` applies:
 * kill any leftover server on 8377 first, or its old spool is what you shoot.)
 *
 * WHAT IT SHOOTS is every page the app routes to and the sub-states the docs
 * page describes in prose: the Overview, the forms list, an aggregate form in
 * both shapes a disaggregated run is drawn in, the reporting-period listbox
 * open, the Responses table, a receipt as a sheet and as its own page, the
 * register, the organisation-unit hierarchy, Terminology and one code system,
 * Evaluate answering, the Playground after a send, the Server page unfolded,
 * the palette, the settings dialog, and one page each in the dark ground and
 * in the DHIS2 theme.
 *
 * ORDER MATTERS, because the spool is one mutable thing this file writes to.
 * The Overview shot posts the receipts every later spool-reading shot counts on,
 * and the receipt shots post one more. Tests run in declaration order under a
 * single worker (`playwright.config.ts` sets `fullyParallel: false`), so the
 * counts on screen are the counts stated here.
 *
 * DETERMINISM. Every drawn answer comes from a stated seed: the form pages type
 * one into the **Seed** box before pressing **Fill with test data**, so the same
 * shoot draws the same numbers rather than whatever `$generate` felt like. The
 * one thing that does move is the calendar - an aggregate form offers the recent
 * periods of its data set's period type, so the reporting period reads as the
 * month the shoot was taken in. That is a date in frame by design: the control's
 * whole point is that it counts back from now.
 */

const here = path.dirname(fileURLToPath(import.meta.url))

/** Where the docs page reads the images from. This directory is owned by the docs, not the suite. */
const screenshotDirectory = path.resolve(here, '../../../../docs/img/fhir')

/** The everyday aggregate form - the quick-entry card the Overview leads with. */
const AGGREGATE_FORM = 'BfMAe6Itzgt'

/** The aggregate form whose data set rides a non-default category combo, so both pickers render. */
const ATTRIBUTE_COMBO_FORM = 'TuL8IOPzpHh'

/** The data-element dictionary - the longest code system this guide publishes, at 70 concepts. */
const DATA_ELEMENT_CODE_SYSTEM = 'd2-de-cs'

/** The district the organisation-unit shot selects: a level-2 unit with a boundary, forms, and children. */
const DISTRICT = 'O6uvpzGd5pu'

const FHIR_JSON = 'application/fhir+json'

/** One viewport for every shot, so the docs images line up beside each other. */
const VIEWPORT = { width: 1280, height: 860 }

/** Write one image under the name the docs page embeds it by. */
async function shoot(page: Page, slug: string): Promise<void> {
    await page.screenshot({
        path: path.join(screenshotDirectory, `capture-ui-${slug}.png`),
        animations: 'disabled',
    })
}

/** Fill one form server-side and post the answer back, returning the receipt id. */
async function generateAndPost(request: APIRequestContext, questionnaireId: string, seed: number): Promise<string> {
    const generated = await request.get(`/Questionnaire/${questionnaireId}/$generate?seed=${String(seed)}`, {
        headers: { Accept: FHIR_JSON },
    })
    expect(generated.status(), await generated.text()).toBe(200)
    const posted = await request.post('/QuestionnaireResponse', {
        headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
        data: await generated.json(),
    })
    expect(posted.status(), await posted.text()).toBe(201)
    return (posted.headers()['location'] ?? '').split('/').pop() ?? ''
}

/**
 * Open a form and wait for the draft, rather than racing it.
 *
 * `$generate` answers the capture context as well as the questions, so a shot taken before it lands
 * is a shot of an unanswered organisation-unit picker.
 */
async function openForm(page: Page, questionnaireId: string): Promise<void> {
    const drafted = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${questionnaireId}`)
    await drafted
}

/** Fill a form from a stated seed, so the numbers in the shot are the same numbers next time. */
async function fillFromSeed(page: Page, seed: number): Promise<void> {
    await page.getByLabel('Seed').fill(String(seed))
    await page.getByRole('button', { name: 'Fill with test data' }).click()
    await expect(page.getByText('Filled with test data')).toBeVisible()
}

// ---------------------------------------------------------------------------
// The register, which this server does not serve and the docs page describes.
//
// A compiled guide has no DHIS2 instance behind it, so the fixture project
// states `tracked_entities.enabled = false` and the app correctly offers no
// register at all. The page is still a page of this UI, so the shots below put
// a live instance in front of the browser and nothing else: `/facade/uiconfig` says a
// register is served, `/metadata` gains the Patient entry a live run adds, and
// `/Patient` answers the projection. Everything else on screen is the real
// server. The people are this producer's own fixture, and deliberately the same
// identities `register.spec.ts` proves the page against.
// ---------------------------------------------------------------------------

const CANONICAL = 'http://localhost:8080/fhir'
const IDENTIFIER_BASE = 'http://dhis2.org/fhir'
const INSTANCE = 'https://dhis2.test/instance'

const PERSON_UID = 'TeiPerson01'
const NATIONAL_ID = '19850312-4471'
const SECOND_PERSON_UID = 'TeiPerson02'
const SECOND_NATIONAL_ID = '19910704-2210'

/** What a live run adds to the conformance document, which is how the app knows there is a register. */
const PATIENT_CAPABILITY = {
    type: 'Patient',
    documentation: 'One DHIS2 tracked entity per Patient, read from the instance at request time.',
    interaction: [{ code: 'read' }, { code: 'search-type' }],
    searchParam: [{ name: 'identifier', type: 'token' }],
}

/** One attribute value as the projection publishes it. */
function attributeValue(attributeId: string, value: string, attributeCode?: string): unknown {
    const stated = [{ url: 'attributeId', valueString: attributeId }]
    if (attributeCode !== undefined) stated.push({ url: 'attributeCode', valueString: attributeCode })
    stated.push({ url: 'value', valueString: value })
    return { url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`, extension: stated }
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
        attributeValue('TeaBirthDat', '1985-03-12', 'TEA_BIRTH_DATE'),
        attributeValue('TeaHousehld', '4'),
        attributeValue('TeaSex00001', 'OpFemale001', 'TEA_SEX'),
    ],
}

/** The second person, holding one unique value and one attribute the type collects rather than names. */
const SECOND_PATIENT = {
    resourceType: 'Patient',
    id: SECOND_PERSON_UID,
    meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetPerson01' }] },
    identifier: [
        { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: SECOND_PERSON_UID },
        { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaNationId`, value: SECOND_NATIONAL_ID },
    ],
    extension: [attributeValue('TeaBirthDat', '1991-07-04', 'TEA_BIRTH_DATE'), attributeValue('TeaHousehld', '6')],
}

const PEOPLE = [PATIENT, SECOND_PATIENT]

/** What one person is enrolled in, as `GET /facade/tracked-entities/{uid}/enrollments` answers it. */
const ENROLLMENTS = {
    tracked_entity_uid: PERSON_UID,
    enrollments: [
        {
            enrollment_uid: 'EnrAnc00001',
            program_uid: 'PrAncCare01',
            program_name: 'Antenatal care',
            status: 'COMPLETED',
            active: false,
            enrolled_at: '2026-02-01T00:00:00Z',
            organisation_unit_uid: 'DiszpKrYNg8',
            organisation_unit_name: 'Ngelehun CHC',
        },
        {
            enrollment_uid: 'EnrChild001',
            program_uid: 'IpHINAT79UW',
            program_name: null,
            status: 'ACTIVE',
            active: true,
            enrolled_at: '2026-05-14T00:00:00Z',
            organisation_unit_uid: DISTRICT,
            organisation_unit_name: 'Bo',
        },
    ],
}

/** What one person has been through, as `GET /facade/tracked-entities/{uid}/events` answers it. */
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
                questionnaire: `${CANONICAL}/Questionnaire/PsAncVisit1`,
                status: 'completed',
                authored: '2026-02-14T00:00:00Z',
                subject: {
                    type: 'Patient',
                    identifier: { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: PERSON_UID },
                },
                extension: [
                    {
                        url: `${CANONICAL}/StructureDefinition/d2-tracker-enrollment`,
                        valueIdentifier: {
                            system: `${IDENTIFIER_BASE}/id/tracker-enrollment`,
                            value: 'EnrAnc00001',
                        },
                    },
                ],
            },
            search: { mode: 'match' },
        },
    ],
}

/**
 * Make this server look like a live one to the browser, and to the browser alone.
 *
 * Both people land on one page here rather than one each: the docs shot is about what a row states,
 * and `register.spec.ts` is where the paging tokens are proved.
 */
async function serveALiveRegister(page: Page): Promise<void> {
    await page.route('**/uiconfig', (route) =>
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                capture: true,
                auth: { posture: 'none', scope: 'write', issuer: null },
                basemaps: [],
                dhis2_base_url: INSTANCE,
                tracked_entities: {
                    enabled: true,
                    listing: true,
                    registers: [{ resource: 'Patient', types: [{ uid: 'TetPerson01', name: 'Person' }] }],
                },
            }),
        }),
    )
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
                return route.fulfill({
                    status: held === undefined ? 404 : 200,
                    contentType: FHIR_JSON,
                    body: JSON.stringify(held ?? { resourceType: 'OperationOutcome', issue: [] }),
                })
            }
            return route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify({
                    resourceType: 'Bundle',
                    type: 'searchset',
                    total: PEOPLE.length,
                    link: [{ relation: 'self', url: '/Patient?_count=25' }],
                    entry: PEOPLE.map((resource) => ({ resource, search: { mode: 'match' } })),
                }),
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

test.describe('docs screenshots', () => {
    test.skip(
        process.env.DOCS_SCREENSHOTS !== '1',
        'screenshot producer, not a test - run DOCS_SCREENSHOTS=1 pnpm exec playwright test e2e/docs-screenshots.spec.ts',
    )

    test.use({ viewport: VIEWPORT })

    test('the Overview, with the spool pulse counting something', async ({ page, request }) => {
        // Three receipts from fixed seeds: enough for the pulse to read as a pulse,
        // and the same three on every standalone shoot. Every later shot that reads
        // the spool counts on these being the first three in it.
        await generateAndPost(request, AGGREGATE_FORM, 9001)
        await generateAndPost(request, AGGREGATE_FORM, 9002)
        await generateAndPost(request, ATTRIBUTE_COMBO_FORM, 9003)

        await page.goto('/')
        await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
        await expect(page.getByTestId('spool-received-count')).toHaveText('3')

        await shoot(page, 'overview')
    })

    test('the forms list', async ({ page }) => {
        await page.goto('/#/forms')
        await expect(page.getByRole('heading', { name: 'Forms', level: 2 })).toBeVisible()
        await expect(page.getByRole('heading', { name: 'Tracker programs' })).toBeVisible()

        await shoot(page, 'forms')
    })

    test('a disaggregated run as a table, with the totals column adding up', async ({ page }) => {
        await openForm(page, AGGREGATE_FORM)
        await fillFromSeed(page, 9101)

        // The Immunization run: fifteen data elements cut by four category option
        // combos, which is the widest cut this app still draws as a table.
        const immunization = page.getByRole('table').filter({ hasText: 'BCG doses given' })
        await expect(immunization).toBeVisible()
        await expect(page.getByText('Disaggregated by Location Fixed/Outreach and EPI/nutrition age').first()).toBeVisible()
        await immunization.scrollIntoViewIfNeeded()

        await shoot(page, 'form-grid')
    })

    test('the same run shown as rows, each element banded with what it adds up to', async ({ page }) => {
        await openForm(page, AGGREGATE_FORM)
        await fillFromSeed(page, 9101)

        const immunization = page.getByRole('table').filter({ hasText: 'BCG doses given' })
        await expect(immunization).toBeVisible()
        // One switch per run, named for what pressing it does next.
        await page.getByRole('button', { name: 'Show as rows' }).first().click()
        await expect(page.getByRole('button', { name: 'Show as columns' }).first()).toBeVisible()

        const band = page.getByText('BCG doses given', { exact: true }).first()
        await band.scrollIntoViewIfNeeded()

        await shoot(page, 'form-rows')
    })

    test('the aggregate form filled with test data, both pickers visible', async ({ page }) => {
        await openForm(page, ATTRIBUTE_COMBO_FORM)

        await expect(page.getByLabel('Reporting from')).toBeVisible()
        await expect(page.getByLabel('Reporting for Project')).toBeVisible()
        await fillFromSeed(page, 9102)

        await shoot(page, 'form-fill')
    })

    test('the reporting period listbox, open on the periods the data set reports in', async ({ page }) => {
        await openForm(page, AGGREGATE_FORM)
        // Seeded for the organisation unit beside it rather than for the answers:
        // an unseeded draw picks a different unit every shoot, and the control the
        // shot is about sits next to the one that would move.
        await fillFromSeed(page, 9103)

        await page.getByLabel('Reporting period').click()
        await expect(page.getByRole('option', { name: 'Other period' })).toBeVisible()

        await shoot(page, 'reporting-period')
    })

    test('one receipt, opened at its own route', async ({ page, request }) => {
        const receiptId = await generateAndPost(request, ATTRIBUTE_COMBO_FORM, 9004)

        await page.goto(`/#/responses/${receiptId}`)
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()

        await shoot(page, 'receipt')
    })

    test('the Responses table, with the lifecycle filters over it', async ({ page }) => {
        await page.goto('/#/responses')
        await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
        // The four this file posted, and nothing else, on a spool that started empty.
        await expect(page.getByRole('row')).toHaveCount(5)

        await shoot(page, 'responses')
    })

    test('a receipt as a sheet over the table it was opened from', async ({ page }) => {
        await page.goto('/#/responses')
        await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()

        await page.getByRole('row').nth(1).click()
        const sheet = page.getByTestId('receipt-sheet')
        await expect(sheet.getByRole('heading', { name: 'Answers' })).toBeVisible()

        await shoot(page, 'receipt-sheet')
    })

    test('the organisation unit hierarchy, the map, and one unit selected', async ({ page }) => {
        await page.goto(`/#/organisation-units?unit=${DISTRICT}`)
        await expect(page.getByRole('heading', { name: 'Organisation units', level: 2 })).toBeVisible()
        // The map paints asynchronously; a shot taken before it says so is a shot of an empty canvas.
        await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
        await expect(page.getByRole('heading', { name: 'Bo', level: 3 })).toBeVisible()

        await shoot(page, 'organisation-units')
    })

    test('the terminology listing', async ({ page }) => {
        await page.goto('/#/terminology')
        await expect(page.getByRole('heading', { name: 'Terminology', level: 2 })).toBeVisible()

        await shoot(page, 'terminology')
    })

    test('one code system, with the concepts under it', async ({ page }) => {
        await page.goto(`/#/terminology/CodeSystem/${DATA_ELEMENT_CODE_SYSTEM}`)
        await expect(page.getByTestId('status-bar-summary')).toContainText(/Showing \d+ of 70 concepts/)

        await shoot(page, 'code-system')
    })

    test('Evaluate, with a worked example loaded and answered', async ({ page }) => {
        await page.goto('/#/evaluate')
        await expect(page.getByRole('heading', { name: 'Evaluate', level: 2 })).toBeVisible()

        await page
            .getByTestId('evaluate-examples')
            .getByRole('button', { name: 'The given names on a Patient' })
            .click()
        await expect(page.getByTestId('evaluate-source')).toContainText('Patient.name.given')
        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()
        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toContainText('2 matches')
        // The answer is under the context editor, which is taller than the viewport:
        // a shot framed on the expression alone is a shot of a screen that answered
        // nothing.
        await answer.scrollIntoViewIfNeeded()

        await shoot(page, 'evaluate')
    })

    test('the Playground, after sending the conformance request', async ({ page }) => {
        await page.goto('/#/playground')
        await expect(page.getByRole('heading', { name: 'Playground' })).toBeVisible()

        await expect(page.getByTestId('playground-path')).toHaveValue('/metadata')
        await expect(page.getByTestId('playground-parameters')).toContainText('This path answers')
        await page.getByTestId('playground-send').click()
        await expect(page.getByTestId('playground-response-body')).toContainText('"CapabilityStatement"')

        await shoot(page, 'playground')
    })

    test('the Server page, with one resource type unfolded', async ({ page }) => {
        await page.goto('/#/server')
        await expect(page.getByRole('heading', { name: 'Server', level: 2 })).toBeVisible()

        await page.getByRole('button', { name: 'Questionnaire', exact: true }).click()
        await expect(page.getByText('The DHIS2 identifiers the resource carries', { exact: false })).toBeVisible()

        await shoot(page, 'server')
    })

    test('the command palette over the page it was opened on', async ({ page }) => {
        await page.goto('/#/forms')
        await expect(page.getByRole('heading', { name: 'Forms', level: 2 })).toBeVisible()

        await page.getByRole('button', { name: 'Command palette' }).click()
        await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()

        await shoot(page, 'palette')
    })

    test('the settings dialog, open on Appearance', async ({ page }) => {
        await page.goto('/')
        await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()

        await page.getByRole('complementary').getByRole('button', { name: 'Settings' }).click()
        const dialog = page.getByRole('dialog', { name: 'Settings' })
        await expect(dialog.getByRole('heading', { name: 'Appearance' })).toBeVisible()

        await shoot(page, 'settings')
    })

    test('the register, listing the people this instance holds', async ({ page }) => {
        await serveALiveRegister(page)

        await page.goto('/#/tracked-entities')
        await expect(page.getByRole('heading', { name: 'Person', level: 2 })).toBeVisible()
        await expect(page.getByTestId('patient-listing')).toContainText(NATIONAL_ID)

        await shoot(page, 'register')
    })

    test('one person in the register, with their attributes and enrollments', async ({ page }) => {
        await serveALiveRegister(page)

        await page.goto(`/#/tracked-entities/Patient/${PERSON_UID}`)
        await expect(page.getByRole('heading', { name: NATIONAL_ID })).toBeVisible()
        await expect(page.getByTestId('patient-enrollments')).toContainText('Antenatal care')

        await shoot(page, 'register-person')
    })

    test('the dark ground, on the table whose colours are facts', async ({ page }) => {
        // next-themes opens on the system preference and this browser holds no stored
        // choice, so emulating the media query is the whole of what the setting does.
        await page.emulateMedia({ colorScheme: 'dark' })

        await page.goto('/#/responses')
        await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
        await expect(page.locator('html')).toHaveClass(/dark/)

        await shoot(page, 'dark')
    })

    test('the DHIS2 theme, repainting the map as well as the chrome', async ({ page }) => {
        // The theme is applied before the first paint by an inline script reading this
        // key, so storing it up front is what keeps a reload from flashing the default.
        await page.addInitScript(() => localStorage.setItem('d2w-fhir.theme', 'dhis2'))

        await page.goto(`/#/organisation-units?unit=${DISTRICT}`)
        await expect(page.locator('html')).toHaveAttribute('data-theme', 'dhis2')
        await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
        await expect(page.getByRole('heading', { name: 'Bo', level: 3 })).toBeVisible()

        await shoot(page, 'theme-dhis2')
    })
})

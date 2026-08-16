import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The screenshot producer for `docs/fhir/201-capture-ui.md` - NOT a test.
 *
 * SKIPPED BY DEFAULT. This file asserts nothing the other specs do not already
 * prove; its whole output is four PNGs under `docs/img/fhir/`, and CI has no
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
 * WHAT IT SHOOTS is pinned by the docs page: the Overview, the forms list, the
 * aggregate form filled with test data (both pickers visible), and one receipt
 * detail. All four are aggregate-form or non-form pages, so the shots do not
 * move when the tracker capture surface does.
 */

const here = path.dirname(fileURLToPath(import.meta.url))

/** Where the docs page reads the images from. This directory is owned by the docs, not the suite. */
const screenshotDirectory = path.resolve(here, '../../../../docs/img/fhir')

/** The everyday aggregate form - the quick-entry card the Overview leads with. */
const AGGREGATE_FORM = 'BfMAe6Itzgt'

/** The aggregate form whose data set rides a non-default category combo, so both pickers render. */
const ATTRIBUTE_COMBO_FORM = 'TuL8IOPzpHh'

const FHIR_JSON = 'application/fhir+json'

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

test.describe('docs screenshots', () => {
    test.skip(
        process.env.DOCS_SCREENSHOTS !== '1',
        'screenshot producer, not a test - run DOCS_SCREENSHOTS=1 pnpm exec playwright test e2e/docs-screenshots.spec.ts',
    )

    // One viewport for all four, so the docs images line up beside each other.
    test.use({ viewport: { width: 1280, height: 860 } })

    test('the Overview, with the spool pulse counting something', async ({ page, request }) => {
        // Three receipts from fixed seeds: enough for the pulse to read as a pulse,
        // and the same three on every standalone shoot.
        await generateAndPost(request, AGGREGATE_FORM, 9001)
        await generateAndPost(request, AGGREGATE_FORM, 9002)
        await generateAndPost(request, ATTRIBUTE_COMBO_FORM, 9003)

        await page.goto('/')
        await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
        await expect(page.getByTestId('spool-received-count')).toHaveText('3')

        await page.screenshot({
            path: path.join(screenshotDirectory, 'capture-ui-overview.png'),
            animations: 'disabled',
        })
    })

    test('the forms list', async ({ page }) => {
        await page.goto('/#/forms')
        await expect(page.getByRole('heading', { name: 'Forms', level: 2 })).toBeVisible()
        await expect(page.getByRole('heading', { name: 'Tracker programs' })).toBeVisible()

        await page.screenshot({
            path: path.join(screenshotDirectory, 'capture-ui-forms.png'),
            animations: 'disabled',
        })
    })

    test('the aggregate form filled with test data, both pickers visible', async ({ page }) => {
        // The skeleton read is awaited rather than raced: `$generate` answers the
        // pickers too, and a shot of an unanswered picker is a shot of a race.
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${ATTRIBUTE_COMBO_FORM}`)
        await opened

        await expect(page.getByLabel('Reporting from')).toBeVisible()
        await expect(page.getByLabel('Reporting for Project')).toBeVisible()
        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        await page.screenshot({
            path: path.join(screenshotDirectory, 'capture-ui-form-fill.png'),
            animations: 'disabled',
        })
    })

    test('one receipt, opened at its own route', async ({ page, request }) => {
        const receiptId = await generateAndPost(request, ATTRIBUTE_COMBO_FORM, 9004)

        await page.goto(`/#/responses/${receiptId}`)
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()

        await page.screenshot({
            path: path.join(screenshotDirectory, 'capture-ui-receipt.png'),
            animations: 'disabled',
        })
    })
})

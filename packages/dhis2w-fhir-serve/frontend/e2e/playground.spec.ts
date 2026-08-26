import { expect, test, type Page } from '@playwright/test'

/**
 * The Playground, driven end to end against the real `d2w fhir serve --ui`.
 *
 * NOTHING HERE IS FULFILLED, and on this screen that matters more than anywhere else in the suite:
 * the whole claim of the page is that what comes back is what this server answers, so a mocked
 * response would prove that of the mock. Every request these cases send is answered by the process
 * playwright.config.ts starts, over the fixture guide the Python suite uses.
 *
 * THE PRESETS ARE CLICKED BY THEIR ID rather than by their words. A row's label is an address and
 * its line is prose, and prose is free to be reworded by a copy pass - `data-preset` is the row's
 * own identity and is what these cases name.
 */

/** The path box, which is what a preset fills and what Send reads. */
function pathBox(page: Page) {
    return page.getByTestId('playground-path')
}

/** One preset row, by the id `lib/playground` builds it under. */
function preset(page: Page, id: string) {
    return page.locator(`[data-preset="${id}"]`)
}

test.describe('the playground', () => {
    test('is in the navigation, and sends the read every page starts from', async ({ page }) => {
        await page.goto('/')

        await page.locator('a[href="#/playground"]').first().click()
        await expect(page.getByRole('heading', { name: 'Playground' })).toBeVisible()

        // The builder opens on `/metadata`, which is the one read every run answers.
        await expect(pathBox(page)).toHaveValue('/metadata')
        await page.getByTestId('playground-send').click()

        const response = page.getByTestId('playground-response')
        await expect(response).toBeVisible()
        await expect(response.getByText('200', { exact: false }).first()).toBeVisible()
        await expect(page.getByTestId('playground-response-body')).toContainText('"CapabilityStatement"')
    })

    test('fills the builder from a preset, and never sends it by itself', async ({ page }) => {
        await page.goto('/#/playground')

        await preset(page, 'search:Questionnaire').click()
        await expect(pathBox(page)).toHaveValue('/Questionnaire')
        await expect(page.getByLabel('Parameter 1 name')).toHaveValue('_count')
        await expect(page.getByLabel('Parameter 1 value')).toHaveValue('5')
        // Choosing a row is not sending it: half of what this screen teaches is what an address is
        // made of, and a row that fired on click would answer before it had been read.
        await expect(page.getByTestId('playground-response')).toHaveCount(0)

        await page.getByTestId('playground-send').click()
        await expect(page.getByTestId('playground-response-body')).toContainText('"searchset"')
    })

    test('posts the declared $evaluate operation and reads the Parameters back', async ({ page }) => {
        await page.goto('/#/playground')

        await preset(page, 'operation:evaluate').click()
        await expect(pathBox(page)).toHaveValue('/$evaluate')
        await expect(page.getByTestId('playground-method')).toContainText('POST')
        await expect(page.getByTestId('playground-body')).toContainText('Patient.name.given')

        await page.getByTestId('playground-send').click()
        // The operation answers the FHIR shape - one parameter per define - over the Patient the
        // body carries, so it runs against any served guide.
        await expect(page.getByTestId('playground-response-body')).toContainText('"Parameters"')
        await expect(page.getByTestId('playground-response-body')).toContainText('Ada')
    })

    test('offers the current request as a curl command', async ({ page }) => {
        await page.goto('/#/playground')

        await expect(page.getByRole('button', { name: 'Copy as curl' })).toBeVisible()
    })

    test('opens a GET at an address that asks for JSON in the URL', async ({ page }) => {
        await page.goto('/#/playground')

        const link = page.getByRole('link', { name: 'Open in a new tab' })
        await expect(link).toHaveAttribute('href', /\/metadata\?_format=json$/)

        // A POST is not a link: there is nowhere for a browser navigation to put the body.
        await preset(page, 'operation:evaluate').click()
        await expect(page.getByRole('link', { name: 'Open in a new tab' })).toHaveCount(0)
    })

    test('remembers what it sent, and puts a chosen row back in the builder', async ({ page }) => {
        await page.goto('/#/playground')

        await preset(page, 'search:Questionnaire').click()
        await page.getByTestId('playground-send').click()
        await expect(page.getByTestId('playground-response-body')).toContainText('"searchset"')

        const history = page.getByTestId('playground-history')
        await expect(history).toContainText('/Questionnaire?_count=5')

        // Something else in the builder, and then the row puts the whole request back - the query
        // rows included, which is the half a path alone would lose.
        await pathBox(page).fill('/metadata')
        await history.getByRole('button').first().click()
        await expect(pathBox(page)).toHaveValue('/Questionnaire')
        await expect(page.getByLabel('Parameter 1 value')).toHaveValue('5')
    })

    test('renders a refusal as the document it is, under the status the server gave it', async ({ page }) => {
        await page.goto('/#/playground')

        await pathBox(page).fill('/Questionnaire/nothing-is-served-under-this-id')
        await page.getByTestId('playground-send').click()

        // The error IS the answer here: an OperationOutcome in the same box a searchset lands in.
        await expect(page.getByTestId('playground-response')).toContainText('404')
        await expect(page.getByTestId('playground-response-body')).toContainText('"OperationOutcome"')
    })
})

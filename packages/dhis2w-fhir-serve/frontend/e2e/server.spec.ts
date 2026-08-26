import { expect, test } from '@playwright/test'

/**
 * Server: the CapabilityStatement rendered, which is this facade's whole contract.
 *
 * There is no OpenAPI document to fall back on - `create_app` switches it off on
 * purpose - so what this page shows is the only machine-readable statement of
 * what the process can do. The operations are conditional on what the store
 * holds, which is why they are asserted rather than assumed: `$generate` is
 * declared only when there are Questionnaires, and the fixture project has them.
 */

test('renders the served conformance document', async ({ page }) => {
    await page.goto('/#/server')

    await expect(page.getByRole('heading', { name: 'Server', level: 2 })).toBeVisible()
    await expect(page.getByText('d2w fhir serve').first()).toBeVisible()
    await expect(page.getByText('4.0.1')).toBeVisible()
})

test('declares $generate on Questionnaire', async ({ page }) => {
    await page.goto('/#/server')

    const row = page.getByRole('row').filter({ hasText: '$generate' })
    await expect(row).toHaveCount(1)
    await expect(row.getByText('Questionnaire', { exact: true })).toBeVisible()
    await expect(row).toContainText('synthetic QuestionnaireResponse')
})

test('states the interactions and search parameters per resource type', async ({ page }) => {
    await page.goto('/#/server')

    // Matched on the type cell rather than on the row's text: the operations
    // table above names QuestionnaireResponse in `$generate`'s documentation, and
    // a text filter would find that row first.
    const responses = page
        .getByRole('row')
        .filter({ has: page.getByRole('cell', { name: 'QuestionnaireResponse', exact: true }) })

    await expect(responses).toHaveCount(1)
    await expect(responses).toContainText('create')
    await expect(responses).toContainText('search-type')
    await expect(responses).toContainText('questionnaire')
})

test("a type's row unfolds into its parameters' contracts, and holds them back until asked", async ({ page }) => {
    // The names are ambient and the prose waits: nine types each stating every
    // parameter's paragraph was a page nobody could scan, so the paragraph is
    // behind the type's own chevron.
    await page.goto('/#/server')

    const identifierContract = page.getByText('The DHIS2 identifiers the resource carries', { exact: false })
    await expect(page.getByRole('button', { name: 'Questionnaire', exact: true })).toBeVisible()
    await expect(identifierContract).toHaveCount(0)

    await page.getByRole('button', { name: 'Questionnaire', exact: true }).click()
    await expect(identifierContract.first()).toBeVisible()

    await page.getByRole('button', { name: 'Questionnaire', exact: true }).click()
    await expect(identifierContract).toHaveCount(0)
})

test('declares $translate on ConceptMap, the type whose URL answers it', async ({ page }) => {
    // The operation is conditional on the store: the fixture IG publishes the map the option-set
    // emitter writes, so the operation a client would use is answerable and is advertised. It rides
    // the ConceptMap entry because `/ConceptMap/$translate` is where it is served.
    await page.goto('/#/server')

    await expect(page.getByRole('heading', { name: 'Declared operations' })).toBeVisible()
    const row = page.getByRole('row').filter({ hasText: '$translate' })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('ConceptMap')
})

test('declares ConceptMap among the read types', async ({ page }) => {
    // The maps are published artifacts in the same store as the code systems, so they are read
    // and searched like every other type - which is what the Terminology browser reads them by.
    // Two rows name it now: the operations table above declares `$translate` on it.
    await page.goto('/#/server')

    const row = page
        .getByRole('row')
        .filter({ has: page.getByRole('cell', { name: 'ConceptMap', exact: true }) })
        .filter({ hasText: 'search-type' })

    await expect(row).toHaveCount(1)
    await expect(row).toContainText('read')
})

test('names the query it is a rendering of, and opens it in the format this server answers in', async ({
    page,
}) => {
    // THE CHIP IS THE PAGE'S OWN SOURCE, SAID OUT LOUD. Everything above it is this app's reading of
    // the CapabilityStatement; the link is the document. `_format=json` is what makes it openable at
    // all - a browser following a bare link sends an `Accept` naming markup, and the FHIR surface
    // refuses that with a 406 rather than sending JSON under a media type the client disclaimed.
    await page.goto('/#/server')

    await expect(page.getByTestId('api-link')).toHaveAttribute('href', '/metadata?_format=json')
    await expect(page.getByTestId('api-link')).toHaveAttribute('target', '_blank')
})

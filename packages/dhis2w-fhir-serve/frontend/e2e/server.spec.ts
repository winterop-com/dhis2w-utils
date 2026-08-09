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

test('does not declare $translate, because this project published no ConceptMaps', async ({ page }) => {
    // The honest half of the conditional: the fixture IG has terminology but no
    // maps, so the operation a client would use is genuinely not answerable here
    // and the page must not advertise it.
    await page.goto('/#/server')

    await expect(page.getByRole('heading', { name: 'Declared operations' })).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: '$translate' })).toHaveCount(0)
})

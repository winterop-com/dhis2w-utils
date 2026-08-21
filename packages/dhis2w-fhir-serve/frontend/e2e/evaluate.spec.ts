import { expect, test } from '@playwright/test'

/**
 * The Evaluate screen, driven end to end against the real `d2w fhir serve --ui`.
 *
 * ONE WALK, AND IT IS THE ONE THE SCREEN EXISTS FOR: pick a language, pick the example that comes
 * with it, press Evaluate, read the answer. Nothing here is fulfilled - `POST /evaluate` is answered
 * by the real server over the real fixture guide, because the whole claim of the generic examples is
 * that they run as they stand against any served guide, and a mocked response would prove that of a
 * fixture of itself rather than of the endpoint.
 *
 * THE PARSE FAILURE IS PART OF THE WALK. An expression that does not parse is the case a reader
 * meets within a minute of typing their own, and it is the case a 500 would have made useless. So
 * the spec breaks the loaded expression on purpose and asserts the position the server reported and
 * the line the screen showed it against.
 */

/** The three examples this file drives, by the label the picker shows them under. */
const FHIRPATH_EXAMPLE = 'The given names on a Patient'
const CQL_EXAMPLE = 'Everyone a Bundle holds'

test.describe('the evaluate screen', () => {
    test('opens with an example already loaded, and running it answers what the server said', async ({
        page,
    }) => {
        await page.goto('/#/evaluate')

        // No empty box: the first generic example is loaded before anything is clicked.
        await expect(page.getByLabel('Source', { exact: true })).toHaveValue('Patient.name.given')
        await expect(page.getByLabel('Context resource')).toContainText('Lovelace')
        await expect(page.getByRole('combobox', { name: 'Example' })).toContainText(FHIRPATH_EXAMPLE)

        await page.getByRole('button', { name: 'Evaluate' }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toBeVisible()
        // Two given names, said the way a person reads a count, with the values in the table.
        await expect(answer).toContainText('2 matches')
        await expect(answer.getByRole('cell', { name: 'Ada', exact: true })).toBeVisible()
        await expect(answer.getByRole('cell', { name: 'Byron', exact: true })).toBeVisible()
    })

    test('picks CQL, loads its own example, and answers one row per define', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByRole('combobox', { name: 'Language' }).click()
        await page.getByRole('option', { name: 'CQL' }).click()

        // The example goes with the language - a FHIRPath expression left behind would be a parse
        // error the reader did not ask for.
        await expect(page.getByRole('combobox', { name: 'Example' })).toContainText(CQL_EXAMPLE)
        await expect(page.getByLabel('Source', { exact: true })).toContainText('define People: [Patient]')

        await page.getByRole('button', { name: 'Evaluate' }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer.getByText('People', { exact: true })).toBeVisible()
        await expect(answer.getByText('HasCondition', { exact: true })).toBeVisible()
        // The retrieve read the Bundle the example carries: one Patient, and a Condition that exists.
        await expect(answer).toContainText('"resourceType": "Patient"')
        await expect(answer.getByRole('cell', { name: 'true', exact: true })).toBeVisible()
    })

    test('shows a parse error at the line and column the parser named', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByLabel('Source', { exact: true }).fill('Patient.name..given')
        await page.getByRole('button', { name: 'Evaluate' }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toContainText('Parse error at line 1, column 14')
        // Shown against the line it names, with the caret under the character it stopped on.
        await expect(answer.locator('pre').first()).toContainText('Patient.name..given')
        await expect(answer.locator('pre').first()).toContainText('^')
        // A parse failure is an answer, not a refusal - the server's own refusal card stays away.
        await expect(page.getByText('The server refused this evaluation')).toHaveCount(0)
    })

    test('offers a preset built from this guide’s own resources, and runs it', async ({ page }) => {
        await page.goto('/#/evaluate')

        const examples = page.getByRole('combobox', { name: 'Example' })
        await examples.click()
        await expect(page.getByRole('option', { name: 'Works on any served guide' })).toHaveCount(0)
        // The presets are found by what they ask rather than by which form the fixture happens to
        // publish first: which resource a guide holds is the guide's business, not this spec's.
        const preset = page.getByRole('option', { name: /^Every question asked by / })
        await expect(preset.first()).toBeVisible()
        await preset.first().click()

        await expect(page.getByLabel('Source', { exact: true })).toHaveValue('Questionnaire.item.linkId')
        await expect(page.getByLabel('Resource type')).toHaveValue('Questionnaire')

        await page.getByRole('button', { name: 'Evaluate' }).click()
        await expect(page.getByTestId('evaluate-answer')).toContainText('match')
    })

    test('is in the navigation on every run, because two of its contexts need no instance', async ({
        page,
    }) => {
        await page.goto('/')

        await expect(page.locator('a[href="#/evaluate"]').first()).toBeVisible()
        // The register context is the one that is not always there, and this run holds no instance.
        await page.goto('/#/evaluate')
        await page.getByRole('combobox', { name: 'Context' }).click()
        await expect(page.getByRole('option', { name: 'A resource pasted below' })).toBeVisible()
        await expect(page.getByRole('option', { name: 'A person this DHIS2 instance holds' })).toHaveCount(0)
    })
})

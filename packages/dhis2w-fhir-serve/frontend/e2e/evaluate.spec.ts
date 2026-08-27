import { expect, test, type Page } from '@playwright/test'

/**
 * The Evaluate screen, driven end to end against the real `d2w fhir serve --ui`.
 *
 * ONE WALK, AND IT IS THE ONE THE SCREEN EXISTS FOR: pick a language, pick the example that comes
 * with it, press Evaluate, read the answer. Nothing here is fulfilled - `POST /facade/evaluate` is answered
 * by the real server over the real fixture guide, because the whole claim of the generic examples is
 * that they run as they stand against any served guide, and a mocked response would prove that of a
 * fixture of itself rather than of the endpoint.
 *
 * THE PARSE FAILURE IS PART OF THE WALK. An expression that does not parse is the case a reader
 * meets within a minute of typing their own, and it is the case a 500 would have made useless. So
 * the spec breaks the loaded expression on purpose and asserts the position the server reported and
 * the line the screen showed it against.
 *
 * THE SOURCE BOX IS A CODEMIRROR DOCUMENT, NOT A TEXTAREA, which is why nothing here reads a value
 * off it. A CodeMirror document is a contenteditable named through `aria-labelledby`, so it is found
 * the same way and read as text; replacing what is in it is select-all and type, which is what a
 * person does. `typeSource` is that, once, so no spec re-invents it.
 */

/** The three examples this file drives, by the label the picker shows them under. */
const FHIRPATH_EXAMPLE = 'The given names on a Patient'
const CQL_EXAMPLE = 'Everyone a Bundle holds'

/** The editor holding the expression, found by the label above it. */
function sourceEditor(page: Page) {
    return page.getByTestId('evaluate-source')
}

/** Replace whatever the source editor holds with one expression, the way a person would. */
async function typeSource(page: Page, expression: string): Promise<void> {
    const editor = sourceEditor(page).locator('.cm-content')
    await editor.click()
    await page.keyboard.press('ControlOrMeta+a')
    await page.keyboard.type(expression)
}

test.describe('the evaluate screen', () => {
    test('opens empty, and a panel example loads and answers what the server said', async ({
        page,
    }) => {
        await page.goto('/#/evaluate')

        // The expression is the reader's: nothing is in that box on arrival, the button says
        // why it waits, and the examples panel is already open beside it. The context box is
        // not empty - the simple example Patient waits there for the first expression.
        await expect(sourceEditor(page)).not.toContainText('Patient')
        await expect(page.getByTestId('evaluate-context-resource')).toContainText('Lovelace')
        await expect(page.getByRole('button', { name: 'Evaluate', exact: true })).toBeDisabled()
        await expect(page.getByTestId('evaluate-examples')).toBeVisible()

        await page.getByTestId('evaluate-examples').getByRole('button', { name: FHIRPATH_EXAMPLE }).click()
        await expect(sourceEditor(page)).toContainText('Patient.name.given')
        await expect(page.getByTestId('evaluate-context-resource')).toContainText('Lovelace')

        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toBeVisible()
        // Two given names, said the way a person reads a count, with the values in the table.
        await expect(answer).toContainText('2 matches')
        await expect(answer.getByRole('cell', { name: 'Ada', exact: true })).toBeVisible()
        await expect(answer.getByRole('cell', { name: 'Byron', exact: true })).toBeVisible()
    })

    test('picks CQL, and a panel example answers one row per define', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByRole('combobox', { name: 'Language' }).click()
        await page.getByRole('option', { name: 'CQL' }).click()

        // Switching language empties the box - a FHIRPath expression left behind would be a
        // parse error, and an example put in would not be the reader's.
        await expect(page.getByRole('button', { name: 'Evaluate', exact: true })).toBeDisabled()

        await page.getByTestId('evaluate-examples').getByRole('button', { name: CQL_EXAMPLE }).click()
        await expect(sourceEditor(page)).toContainText('define People: [Patient]')

        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer.getByText('People', { exact: true })).toBeVisible()
        await expect(answer.getByText('HasCondition', { exact: true })).toBeVisible()
        // The retrieve read the Bundle the example carries: one Patient, and a Condition that exists.
        await expect(answer).toContainText('"resourceType": "Patient"')
        await expect(answer.getByRole('cell', { name: 'true', exact: true })).toBeVisible()
    })

    test('shows a parse error at the line and column the parser named', async ({ page }) => {
        await page.goto('/#/evaluate')

        await typeSource(page, 'Patient.name..given')
        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()

        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toContainText('Parse error at line 1, column 14')
        // Shown against the line it names, with the caret under the character it stopped on.
        await expect(answer.locator('pre').first()).toContainText('Patient.name..given')
        await expect(answer.locator('pre').first()).toContainText('^')
        // A parse failure is an answer, not a refusal - the server's own refusal card stays away.
        await expect(page.getByText('The server refused this evaluation')).toHaveCount(0)
    })

    test("offers a preset built from this guide's own resources, and runs it", async ({ page }) => {
        await page.goto('/#/evaluate')

        // The presets are found by what they ask rather than by which form the fixture happens to
        // publish first: which resource a guide holds is the guide's business, not this spec's.
        const preset = page
            .getByTestId('evaluate-examples')
            .getByRole('button', { name: /^Every question asked by / })
        await expect(preset.first()).toBeVisible()
        await preset.first().click()

        await expect(sourceEditor(page)).toContainText('Questionnaire.item.linkId')
        await expect(page.getByLabel('Resource type')).toHaveValue('Questionnaire')

        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()
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
        await expect(page.getByRole('option', { name: 'A tracked entity this DHIS2 instance holds' })).toHaveCount(0)
    })

    test('colours the source rather than showing it as one run of plain text', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByRole('combobox', { name: 'Language' }).click()
        await page.getByRole('option', { name: 'CQL' }).click()
        await page.getByTestId('evaluate-examples').getByRole('button', { name: CQL_EXAMPLE }).click()

        // The proof that a highlighter is running at all: the document is spans with token classes,
        // not one text node. Which colour each gets is the theme's business and is asserted in the
        // vitest cases over the tokeniser.
        const editor = sourceEditor(page)
        await expect(editor.locator('.cm-content')).toBeVisible()
        await expect(editor.locator('.tok-keyword').first()).toBeVisible()
    })

    test('holds a reference beside the editor, every language on its own tab', async ({ page }) => {
        await page.goto('/#/evaluate')

        // Open with the screen, because the second thing a reader wonders is what else they could
        // have written, and the answer to that is a list rather than a search engine.
        const examples = page.getByTestId('evaluate-examples')
        await expect(examples).toBeVisible()
        await expect(examples).toContainText('The email address, out of every way of reaching the person')

        // All three languages sit on the bar whatever the editor speaks - a reader writing
        // FHIRPath reads what CQL answers without touching the language picker.
        await expect(page.getByRole('tab', { name: 'CQL' })).toBeVisible()
        await expect(page.getByRole('tab', { name: 'ELM' })).toBeVisible()

        await page.getByRole('tab', { name: 'FHIRPath' }).click()
        const reference = page.getByTestId('evaluate-reference')
        await expect(reference).toBeVisible()
        await expect(reference.getByRole('heading', { name: 'Existence and counting' })).toBeVisible()
        await expect(reference).toContainText('exists([criteria])')
        // What it refuses is on the same shelf as what it answers, because half of learning a
        // language here is learning what it says no to.
        await expect(reference.getByRole('heading', { name: 'What it refuses' })).toBeVisible()
    })

    test('loads an example from the panel straight into the editor, and runs it', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page
            .getByTestId('evaluate-examples')
            .getByRole('button', { name: 'The email address, out of every way of reaching the person' })
            .click()

        await expect(sourceEditor(page)).toContainText("Patient.telecom.where(system = 'email').value")

        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()
        await expect(page.getByTestId('evaluate-answer')).toContainText('ada@example.org')
    })

    test('asks the household Bundle a question a single record could not answer', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page
            .getByTestId('evaluate-examples')
            .getByRole('button', { name: 'The weights above sixty kilograms' })
            .click()

        // The whole Bundle is pasted into the context box, not a reference to one held elsewhere.
        // Asserted on its opening lines: the box is a fixed-height viewport over a virtualising
        // editor, so text deep in the document is not in the DOM until scrolled to.
        await expect(page.getByTestId('evaluate-context-resource')).toContainText('"Bundle"')
        await expect(page.getByTestId('evaluate-context-resource')).toContainText('Selam')

        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()

        const answer = page.getByTestId('evaluate-answer')
        // Four weights are recorded and two of them clear the threshold, so the filter is doing work.
        await expect(answer).toContainText('2 matches')
        await expect(answer.getByRole('cell', { name: '63.4', exact: true })).toBeVisible()
    })

    test('states the CQL reference this engine answers, refusals included', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByRole('combobox', { name: 'Language' }).click()
        await page.getByRole('option', { name: 'CQL' }).click()

        await page.getByRole('tab', { name: 'CQL' }).click()
        const reference = page.getByTestId('evaluate-reference')
        await expect(reference.getByRole('heading', { name: 'Retrieves' })).toBeVisible()
        await expect(reference.getByRole('heading', { name: 'The header' })).toBeVisible()
        await expect(reference).toContainText('return [all | distinct] expression')
        await expect(reference).toContainText('value set')
    })

    test('starts open, and the corner control is the way out and back', async ({ page }) => {
        await page.goto('/#/evaluate')

        // The editor arrives empty, so the panel - the way in - is already open.
        await expect(page.getByTestId('evaluate-examples')).toBeVisible()
        await page.getByRole('button', { name: 'Collapse the examples' }).click()
        await expect(page.getByTestId('evaluate-examples')).toHaveCount(0)
        // The control belongs to the panel it acts on, not to the toolbar above the editor.
        await page.getByRole('button', { name: 'Expand the examples' }).click()
        await expect(page.getByTestId('evaluate-examples')).toBeVisible()
        await expect(page.getByRole('button', { name: 'Reference', exact: true })).toHaveCount(0)
    })

    test('runs a refusal example and shows the whole of what the engine said', async ({ page }) => {
        await page.goto('/#/evaluate')

        await page.getByRole('combobox', { name: 'Language' }).click()
        await page.getByRole('option', { name: 'CQL' }).click()

        await page
            .getByTestId('evaluate-examples')
            .getByRole('button', { name: 'A valueset the data holds no expansion for, refused' })
            .click()
        await page.getByRole('button', { name: 'Evaluate', exact: true }).click()

        // The refusal is the answer, and it arrives as a 200 with the engine's own sentence on it.
        const answer = page.getByTestId('evaluate-answer')
        await expect(answer).toContainText('holds no expansion for')
        await expect(page.getByText('The server refused this evaluation')).toHaveCount(0)
    })
})

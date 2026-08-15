import { expect, test, type Page } from '@playwright/test'

/**
 * What DHIS2 holds about a form beyond what R4 has elements for, rendered.
 *
 * WHAT IS UNDER TEST. A generated form carries more than its questions: the words the instance uses
 * for the dates it collects, whether a stage may be answered more than once, the description a form
 * designer wrote for a data element or a section, the categories a disaggregated cell is cut by, and
 * which attributes DHIS2 mints rather than takes. Every one of those rides as an extension or a
 * concept property, every one is optional, and every one of them is a thing a person filling the form
 * in would otherwise have to already know. This walks them on the real server: the fixture project
 * publishes each fact on the form that would really carry it, and the assertions are on what reaches
 * the screen.
 *
 * WHY IT IS ONE FILE. These are all one contract - the form is the authority on what it asks, and
 * this UI states what the form states - and they are read off three forms between them. Splitting
 * them per fact would boot the same server five times to read five labels.
 */

/** The forms of the fixture project each fact rides on. */
const STAGE_FORM = 'PsAncVisit1'
const AGGREGATE_FORM = 'BfMAe6Itzgt'
const REGISTRATION_FORM = 'PrAncCare01'

/** The words the fixture's instance uses for the dates its programme collects. */
const EVENT_DATE_LABEL = 'Date of visit'

/** The attribute DHIS2 mints, the shape it mints to, and the one a client really answers. */
const GENERATED_QUESTION = 'Programme identifier'
const GENERATED_PATTERN = 'ANC-#######'
const TYPED_QUESTION = 'National id'

/** Open one form and wait for the skeleton, which is what puts the drafted values in the controls. */
async function openForm(page: Page, questionnaireId: string): Promise<void> {
    const opened = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${questionnaireId}`)
    await opened
}

test('a stage form states its own word for the visit date, and that it repeats', async ({ page }) => {
    await openForm(page, STAGE_FORM)

    // The date control is headed by the programme's word rather than by this project's default. The
    // default is a fact-stating fallback and not a label to be decorated with, so it is gone.
    await expect(page.getByLabel(EVENT_DATE_LABEL)).toBeVisible()
    await expect(page.getByLabel('Visit date')).toHaveCount(0)

    // Whether one enrollment may answer this stage more than once changes what filling the form in
    // means, so it is said where the form describes itself.
    await expect(page.getByText('Repeats: each visit is its own record')).toBeVisible()
})

test('the forms listing says which stages repeat', async ({ page }) => {
    await page.goto('/#/forms')

    const stage = page.getByTestId('forms-tracker-program').getByRole('row').filter({ hasText: 'ANC visit' })
    await expect(stage).toContainText('stage - each visit is its own record')
})

test('a data element and a section carry the descriptions DHIS2 holds for them', async ({ page }) => {
    await openForm(page, AGGREGATE_FORM)

    // A section's description reads under its heading; a data element group's under its own. Both
    // are what a form designer wrote for whoever fills the form in, so both are on screen rather
    // than behind a hover.
    await expect(
        page.getByText('Doses given at this facility and on outreach, counted at the end of each month.'),
    ).toBeVisible()
    await expect(page.getByText('Count a dose once, on the day it was given.')).toBeVisible()
})

test('a group of disaggregated cells names the categories it is cut by', async ({ page }) => {
    await openForm(page, AGGREGATE_FORM)

    // "Fixed, <1y" names one corner of a grid and never says which grid. The axes come from the
    // served combo vocabulary's own property declarations, joined to the cells this form asks - and
    // they are stated once, above them, in the order DHIS2 declares the category combo.
    await expect(
        page.getByText('Disaggregated by Location Fixed/Outreach and EPI/nutrition age').first(),
    ).toBeVisible()

    // And the cells themselves are in the order the form asks them. Nothing in this UI sorts a
    // decomposition: DHIS2's order is the order a paper register is read in.
    const cells = page
        .getByRole('group')
        .filter({ hasText: 'BCG doses given' })
        .getByText(/^(Fixed|Outreach), [<>]1y$/)
    await expect(cells).toHaveText(['Fixed, <1y', 'Fixed, >1y', 'Outreach, <1y', 'Outreach, >1y'])
})

test('an attribute DHIS2 generates is asked of nobody and answered by nothing', async ({ page }) => {
    await openForm(page, REGISTRATION_FORM)

    // The form marks the item read-only, so the control takes no input; the dictionary states that
    // DHIS2 mints the value and the shape it mints to, which is what lets the screen say why.
    const generated = page.getByLabel(GENERATED_QUESTION)
    await expect(generated).toBeVisible()
    await expect(generated).toBeDisabled()
    await expect(
        page.getByText(`DHIS2 fills this in when the submission is imported, shaped ${GENERATED_PATTERN}`),
    ).toBeVisible()

    // It is required by the form, and it is not a question the form is waiting on: nothing anyone
    // types would reach the wire. The one question a person really answers is the one counted -
    // which is the same rule the capture grading holds on the server.
    await expect(page.getByText('1 required question is unanswered')).toBeVisible()

    // And `$generate` does not invent one either. A drawn value is a value DHIS2 discards, and one
    // drawn from the same shape as a real identifier would read as a claim about a person. The
    // question beside it is answered, so this is the draw declining rather than the draw failing.
    await page.getByRole('button', { name: 'Fill with test data' }).click()
    await expect(page.getByText('Filled with test data')).toBeVisible()
    await expect(generated).toHaveValue('')
    await expect(page.getByLabel(TYPED_QUESTION)).not.toHaveValue('')

    // Nothing is posted here. The suite drives one server with one spool, and that a submission
    // carrying no answer for a generated attribute is accepted - with no required warning about it -
    // is the Python suite's claim over the same fixture, where it costs no shared state.
    await expect(page.getByRole('button', { name: 'Submit' })).toBeEnabled()
})

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * What the keyboard does to a form being filled in, and what it must never do.
 *
 * ENTER IS THE ONE KEY THAT COULD FILE A SUBMISSION BY ACCIDENT. HTML's implicit submission posts a
 * form from any text box in it, so Enter after typing a period - or in the person-search box, where
 * pressing it is the obvious thing to do - filed a capture nobody had finished. A receipt is
 * permanent, so this is the behaviour worth pinning: the only thing that submits a capture is the
 * Submit button.
 *
 * AND WHAT A BOX HOLDS IS WHAT THE FORM GRADES. A numeric question is a text box precisely so the
 * literal survives the keystroke that a `type="number"` box would have dropped; the conversion runs
 * once, at submit, and a value it cannot carry is stated where the person who typed it can see it,
 * rather than vanishing out of a submission the server then accepts.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const TEMPORAL_FORM = 'PrTemporal1'

/** Open one form and wait for the skeleton, which is what puts the drafted values in the controls. */
async function openForm(page: Page, questionnaireId: string): Promise<void> {
    const opened = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${questionnaireId}`)
    await opened
}

/** How many receipts this project's spool holds right now. */
async function spoolTotal(request: APIRequestContext): Promise<number> {
    const listing = await request.get('/facade/spool', { headers: { Accept: 'application/json' } })
    expect(listing.status(), await listing.text()).toBe(200)
    const body = (await listing.json()) as { total: number }
    return body.total
}

test('Enter in a text box on a form does not post the capture', async ({ page, request }) => {
    const before = await spoolTotal(request)
    await openForm(page, AGGREGATE_FORM)

    // The identifier box, which is the text box the capture context has: the period is chosen from
    // a list of recent months, and Other period is what opens the box any period can be typed into.
    const period = page.getByLabel('Reporting period')
    await expect(period).toBeVisible()
    await period.click()
    await page.getByRole('option', { name: 'Other period' }).click()
    const identifier = page.getByLabel('Period identifier')
    await identifier.click()
    await identifier.press('Enter')

    // Nowhere else, nothing accepted, and nothing in the spool: the page a person was filling in is
    // the page they are still on.
    await expect(page).toHaveURL(new RegExp(`#/forms/${AGGREGATE_FORM}$`))
    await expect(page.getByText('The server accepted this submission')).toHaveCount(0)
    expect(await spoolTotal(request)).toBe(before)
})

test('Enter in a question box does not post the capture either', async ({ page, request }) => {
    const before = await spoolTotal(request)
    await openForm(page, TEMPORAL_FORM)

    const coverage = page.getByLabel('Coverage')
    await coverage.fill('58.3')
    await coverage.press('Enter')

    await expect(page).toHaveURL(new RegExp(`#/forms/${TEMPORAL_FORM}$`))
    await expect(page.getByText('The server accepted this submission')).toHaveCount(0)
    expect(await spoolTotal(request)).toBe(before)
    // The answer is still there to submit deliberately, which is the other half of swallowing the key.
    await expect(coverage).toHaveValue('58.3')
})

test('a box holding what its question cannot record refuses Submit, and says what it holds', async ({ page }) => {
    await openForm(page, TEMPORAL_FORM)

    // The keystroke a number box would have swallowed: it drops the character it cannot parse, so
    // `1.2.3` became `1.23` under the cursor with nothing said about it.
    await page.getByLabel('Coverage').fill('1.2.3')

    await expect(page.getByText('1.2.3 is not a number, which is what this question records')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Submit' })).toBeDisabled()
    await expect(page.getByText('1 answer is outside what this form accepts')).toBeVisible()
})

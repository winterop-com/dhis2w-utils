import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The receipt quick view, as the thing it is for: reading down a spool without losing your place.
 *
 * WHY THIS IS ITS OWN FILE. The capture spec proves the loop - a submission reaches the spool and
 * the listing shows it - and asserts the receipt's contents once. This is about the reading posture
 * instead: a filtered table, three receipts opened in turn, and the filter and the summary line
 * still saying what they said when the reading started. That is the whole argument for a sheet over
 * a navigation, and it is exactly what a spec of one page's contents cannot show.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

/** Ask the server to fill one form, then post the answer straight back at it. */
async function generateAndPost(request: APIRequestContext, seed: number): Promise<string> {
    const generated = await request.get(`/Questionnaire/${AGGREGATE_FORM}/$generate?seed=${String(seed)}`, {
        headers: { Accept: FHIR_JSON },
    })
    expect(generated.status(), await generated.text()).toBe(200)

    const posted = await request.post('/QuestionnaireResponse', {
        headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
        data: await generated.json(),
    })
    expect(posted.status(), await posted.text()).toBe(201)
    const location = posted.headers()['location']
    expect(location).toBeTruthy()
    return location.split('/').pop() ?? ''
}

test('reads three receipts in turn without losing the filter or the place in the table', async ({
    page,
    request,
}) => {
    const receipts = [
        await generateAndPost(request, 301),
        await generateAndPost(request, 302),
        await generateAndPost(request, 303),
    ]

    await page.goto('/#/responses')
    // A reader who has narrowed to one state, which is the ordinary way this table is read.
    await page.getByRole('button', { name: /^Received, / }).click()
    await expect(page).toHaveURL(/#\/responses\?lifecycle=received$/)
    const stated = await page.getByTestId('status-bar-summary').textContent()

    const sheet = page.getByTestId('receipt-sheet')
    for (const receiptId of receipts) {
        await page.getByRole('row').filter({ hasText: receiptId }).click()
        await expect(sheet.getByText(receiptId).first()).toBeVisible()
        await expect(sheet.getByRole('heading', { name: 'Answers' })).toBeVisible()
        await page.keyboard.press('Escape')
        await expect(sheet).toHaveCount(0)
    }

    // The narrowing, the address, and the line at the foot of the window are what they were before
    // any of it - three receipts read, and nothing about the table to redo.
    await expect(page).toHaveURL(/#\/responses\?lifecycle=received$/)
    await expect(page.getByTestId('status-bar-summary')).toHaveText(stated ?? '')
    await expect(page.getByTestId('status-bar-note')).toHaveText('Received')
})

test('the quick view and the page it links to are one reading of one receipt', async ({
    page,
    request,
}) => {
    const receiptId = await generateAndPost(request, 304)

    await page.goto('/#/responses')
    await page.getByRole('row').filter({ hasText: receiptId }).click()

    const sheet = page.getByTestId('receipt-sheet')
    // The form the receipt answers is what heads it, and the raw document waits behind a button at
    // the panel's foot - the escape hatch that makes the rest honest.
    await expect(sheet.getByRole('link', { name: 'Child Health' })).toBeVisible()
    await sheet.getByRole('button', { name: 'Raw QuestionnaireResponse' }).click()
    await expect(page.getByTestId('raw-questionnaire-response')).toContainText(
        '"resourceType": "QuestionnaireResponse"',
    )
    await page.keyboard.press('Escape')

    // The address carries the open quick view, so a reload - or the same address sent to somebody
    // else - lands with the panel already open on the same receipt.
    await expect(page).toHaveURL(new RegExp(`#/responses\\?open=${receiptId}$`))
    await page.reload()
    await expect(page.getByTestId('receipt-sheet').getByRole('link', { name: 'Child Health' })).toBeVisible()

    const fullPageOpened = page.context().waitForEvent('page')
    await page.getByRole('link', { name: 'Open the full page' }).click()
    const fullPage = await fullPageOpened
    await expect(fullPage).toHaveURL(new RegExp(`#/responses/${receiptId}$`))
    await expect(fullPage.getByRole('heading', { name: 'Child Health', level: 2 })).toBeVisible()
    await expect(fullPage.getByRole('heading', { name: 'Capture context' })).toBeVisible()
    await expect(fullPage.getByRole('heading', { name: 'Answers' })).toBeVisible()
})

test('Back shuts the receipt panel and leaves the filter that was on', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, 512)

    await page.goto('/#/responses')
    await page.getByRole('button', { name: /^Received/ }).click()
    await expect(page).toHaveURL(/#\/responses\?lifecycle=received$/)

    await page.getByRole('row').filter({ hasText: receiptId }).click()
    await expect(page).toHaveURL(new RegExp(`#/responses\\?lifecycle=received&open=${receiptId}$`))

    // Opening a receipt is a place a reader went, so Back is the way out of it - and because the
    // filter is in the address too, it is still on underneath.
    await page.goBack()
    await expect(page.getByTestId('receipt-sheet')).toHaveCount(0)
    await expect(page).toHaveURL(/#\/responses\?lifecycle=received$/)
    await expect(page.getByRole('button', { name: /^Received/ })).toHaveAttribute('aria-pressed', 'true')

    // And Back again walks off the filter, onto the listing it was applied to.
    await page.goBack()
    await expect(page).toHaveURL(/#\/responses$/)
})

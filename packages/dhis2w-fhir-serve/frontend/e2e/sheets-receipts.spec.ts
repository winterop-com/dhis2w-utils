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
    // The form the receipt answers is what heads it, and the raw document is under it here as it is
    // on the page - the escape hatch that makes the rest of either honest.
    await expect(sheet.getByRole('link', { name: 'Child Health' })).toBeVisible()
    await sheet.getByRole('button', { name: 'Raw QuestionnaireResponse' }).click()
    await expect(page.getByTestId('raw-questionnaire-response')).toContainText(
        '"resourceType": "QuestionnaireResponse"',
    )

    await page.getByRole('link', { name: 'Open the full page' }).click()
    await expect(page).toHaveURL(new RegExp(`#/responses/${receiptId}$`))
    await expect(page.getByRole('heading', { name: 'Child Health', level: 2 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Answers' })).toBeVisible()
})

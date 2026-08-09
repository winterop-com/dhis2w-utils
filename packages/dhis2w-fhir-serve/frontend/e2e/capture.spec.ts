import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The capture loop, end to end, against the real server.
 *
 * THE LOOP WITHOUT THE FORM UI. `$generate` fills one served form with synthetic
 * answers, and the operation's whole point is that its output posts back at the
 * same server for a 201 - so generate-then-post is the capture round trip with
 * the renderer taken out of it. That makes this spec provable today, and it
 * proves the half the renderer cannot: that a receipt reaches the spool, that
 * `/spool` reports it as `received`, and that the Responses page shows it.
 *
 * The last describe drives the same loop through the renderer instead, which is
 * how a person performs it.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

/** Ask the server to fill one form, then post the answer straight back at it. */
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

    // The receipt id is where the created resource is served from, which the
    // create interaction states in its Location header exactly as R4 says.
    const location = posted.headers()['location']
    expect(location).toBeTruthy()
    return location.split('/').pop() ?? ''
}

test('the Responses page starts empty and says where a response comes from', async ({ page }) => {
    // Runs before anything is posted in this file, which is why the fixture
    // builder empties the spool: a receipt left over from the last run would
    // make this pass for the wrong reason, then make it fail.
    await page.goto('/#/responses')

    await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
    await expect(page.getByText('Nothing has been captured into this project yet')).toBeVisible()
    await expect(page.getByText('$generate')).toBeVisible()
})

test('a generated response posts back and shows up as a received receipt', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 7)

    await page.goto('/#/responses')

    const row = page.getByRole('row').filter({ hasText: receiptId })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Received')
    await expect(row).toContainText('Child Health')
    await expect(row).toContainText('Aggregate data set')
})

test('the spool listing states the lifecycle and the counts', async ({ request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 11)

    const listing = await request.get('/spool', { headers: { Accept: 'application/json' } })
    expect(listing.status()).toBe(200)
    const body = (await listing.json()) as {
        total: number
        counts: { received: number; forwarded: number; rejected: number }
        responses: { response_id: string; lifecycle: string; period: string | null; answer_count: number }[]
    }

    const row = body.responses.find((candidate) => candidate.response_id === receiptId)
    expect(row).toBeDefined()
    expect(row?.lifecycle).toBe('received')
    expect(row?.answer_count).toBeGreaterThan(0)
    // An aggregate capture reports for a period; the listing derives it from the
    // D2Period extension on the stored resource.
    expect(row?.period).toBeTruthy()
    expect(body.counts.received).toBeGreaterThan(0)
})

test('the reload button re-reads the spool', async ({ page, request }) => {
    await page.goto('/#/responses')

    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 23)
    await page.getByRole('button', { name: 'Reload' }).click()

    // The point of the button: the server re-reads the spool directory to
    // answer, so a capture that happened after the page loaded appears without
    // anything being restarted. `d2w fhir forward` moves files the same way.
    await expect(page.getByRole('row').filter({ hasText: receiptId })).toHaveCount(1)
})

test('the detail dialog shows the receipt in full', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 42)

    await page.goto('/#/responses')
    await page.getByRole('row').filter({ hasText: receiptId }).getByRole('button', { name: 'Open' }).click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText(receiptId)
    await expect(dialog).toContainText('Period')
    await expect(dialog).toContainText('Organisation unit')
    await expect(dialog).toContainText('GET /QuestionnaireResponse/')
})

test('the lifecycle filter narrows the table', async ({ page, request }) => {
    await generateAndPost(request, AGGREGATE_FORM, 99)

    await page.goto('/#/responses')
    await page.getByRole('button', { name: /^Forwarded/ }).click()

    // Nothing has been forwarded in this project - the forwarder needs a DHIS2
    // instance - so the filter empties the table and says the total it is
    // filtering out of, rather than reading as "no receipts at all".
    await expect(page.getByText('No receipt matches this filter')).toBeVisible()
})

/**
 * The form-fill walkthrough: the half of the loop a person actually performs.
 *
 * The API round trip above proves the server side - generate, post, receipt. This
 * is the same loop driven the way it is used: open a form from the Forms table,
 * fill it with test data, submit, and land on the Responses page with the
 * receipt on it. It exercises the renderer, the answer state, the submit path,
 * and the listing in one pass, so it is the spec that fails when any of them
 * stops agreeing with the others.
 */
test.describe('filling a form in the browser', () => {
    test('opens a form, fills it with test data, submits, and finds the receipt', async ({
        page,
        request,
    }) => {
        const before = (await (await request.get('/spool')).json()) as { total: number }

        await page.goto('/')
        await page
            .getByRole('row')
            .filter({ hasText: 'Child Health' })
            .getByRole('link', { name: 'Open' })
            .click()
        await expect(page).toHaveURL(new RegExp(`#/forms/${AGGREGATE_FORM}$`))

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with generated answers')).toBeVisible()

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()

        // The form navigates to the listing on success, which is the point: the
        // receipt is the thing you want to see next.
        await expect(page).toHaveURL(/#\/responses$/)
        await expect(page.getByRole('row').filter({ hasText: 'Child Health' }).first()).toBeVisible()

        const after = (await (await request.get('/spool')).json()) as { total: number }
        expect(after.total).toBe(before.total + 1)
    })
})

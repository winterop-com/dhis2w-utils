import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * The Overview: the root route, and whether its numbers are the server's numbers.
 *
 * WHAT IS WORTH PROVING HERE is not that the cards render - it is that the count on a tile is
 * the count `GET /spool` reports, and that clicking one lands on the Responses table already
 * narrowed to that state. A dashboard whose headline number is computed from a different read
 * than the page it links to is the classic way this kind of screen goes quietly wrong.
 *
 * THE SPOOL IS SHARED WITH THE OTHER SPECS. The suite runs one server, one worker, in file order
 * (see playwright.config.ts), so `capture.spec.ts` has already posted receipts by the time this
 * file runs. This file posts one of its own anyway, so it holds when run alone - and asserts the
 * received count by sandwiching it between a read taken before the page loaded and one taken
 * after, which is the honest assertion over a spool that another process can add to.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

/** The lifecycle counts as the server reports them, right now. */
async function spoolCounts(
    request: APIRequestContext,
): Promise<{ received: number; forwarded: number; rejected: number }> {
    const listing = await request.get('/spool', { headers: { Accept: 'application/json' } })
    expect(listing.status()).toBe(200)
    const body = (await listing.json()) as {
        counts: { received: number; forwarded: number; rejected: number }
    }
    return body.counts
}

/** Put one receipt in the spool, so the pulse has something to be a pulse of. */
async function captureOne(request: APIRequestContext, seed: number): Promise<void> {
    const generated = await request.get(`/Questionnaire/${AGGREGATE_FORM}/$generate?seed=${String(seed)}`, {
        headers: { Accept: FHIR_JSON },
    })
    expect(generated.status(), await generated.text()).toBe(200)
    const posted = await request.post('/QuestionnaireResponse', {
        headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
        data: await generated.json(),
    })
    expect(posted.status(), await posted.text()).toBe(201)
}

/** The number printed on one lifecycle tile. */
async function tileCount(page: Page, lifecycle: string): Promise<number> {
    return Number(await page.getByTestId(`spool-${lifecycle}-count`).innerText())
}

test('the tiles carry the counts the spool reports', async ({ page, request }) => {
    await captureOne(request, 301)

    const before = await spoolCounts(request)
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
    await expect(page.getByTestId('spool-received-count')).toBeVisible()
    const after = await spoolCounts(request)

    // Sandwiched rather than equal to one read: the page took its own snapshot of a directory
    // any process can add to. What is being proved is that the tile is reporting that read
    // rather than a count of its own.
    const received = await tileCount(page, 'received')
    expect(received).toBeGreaterThanOrEqual(before.received)
    expect(received).toBeLessThanOrEqual(after.received)
    expect(received).toBeGreaterThan(0)

    // Nothing in this project can be forwarded, rejected, or withdrawn: reaching any of those
    // states needs a DHIS2 instance, and there is none behind the fixture server.
    expect(await tileCount(page, 'forwarded')).toBe(0)
    expect(await tileCount(page, 'rejected')).toBe(0)
    expect(await tileCount(page, 'withdrawn')).toBe(0)

    // The received tile is the one that is a task, and says so.
    await expect(page.getByRole('link', { name: /^Received/ })).toContainText('not yet sent to DHIS2')
})

test('a tile opens the responses already filtered to its state', async ({ page, request }) => {
    await captureOne(request, 302)

    await page.goto('/')
    await page.getByRole('link', { name: /^Received/ }).click()

    // The filter is in the URL, which is what makes it a link somebody can be sent - and what
    // lets the Responses page honour a selection made on another page.
    await expect(page).toHaveURL(/#\/responses\?lifecycle=received$/)
    await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Received/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /^All/ })).toHaveAttribute('aria-pressed', 'false')
})

test('a nonsense lifecycle in the URL shows everything rather than nothing', async ({ page, request }) => {
    await captureOne(request, 303)

    await page.goto('/#/responses?lifecycle=nowhere')

    await expect(page.getByRole('button', { name: /^All/ })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('row').filter({ hasText: 'Child Health' }).first()).toBeVisible()
})

test('a form card opens the form view', async ({ page }) => {
    await page.goto('/')

    // The card names the form the way the listing does - unescaped title, DHIS2 kind, question
    // count - because it is the same three facts that decide whether it is the one you want.
    const card = page.getByRole('link', { name: 'Open Child Health' })
    await expect(card).toContainText('Aggregate data set')
    await card.click()

    await expect(page).toHaveURL(new RegExp(`#/forms/${AGGREGATE_FORM}$`))
    await expect(page.getByRole('button', { name: 'Fill with test data' })).toBeVisible()
})

test('the server strip names the guide and links to what this server offers', async ({ page }) => {
    await page.goto('/')

    const strip = page.getByRole('link', { name: 'What this server offers' })
    await expect(page.getByText('DHIS2 FHIR Capture IG').first()).toBeVisible()
    // The operations are conditional on what the store holds, which is the point of showing them.
    await expect(page.getByText('$generate', { exact: true })).toBeVisible()
    await expect(page.getByText('$translate', { exact: true })).toBeVisible()

    await strip.click()
    await expect(page).toHaveURL(/#\/server$/)
})

test('the wordmark returns to the overview from anywhere', async ({ page }) => {
    await page.goto('/#/terminology')
    await expect(page.getByRole('heading', { name: 'Terminology', level: 2 })).toBeVisible()

    await page.getByRole('link', { name: 'Capture overview' }).click()

    await expect(page).toHaveURL(/#\/$/)
    await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
})

import { expect, test, type Page } from '@playwright/test'

/**
 * Two rules the browser is the only place to check: what a row does under a pointer, and what a
 * sentence looks like once it is on a screen.
 *
 * THE FIRST IS A PAINT. `.interactive` is a hover fill, a title that takes the accent with it, and
 * a chevron that leans - none of which exists until a browser has resolved a custom property against
 * a theme. A unit test can prove the class is on the row (`lib/theme.test.ts` does); only a browser
 * can prove the class does anything, and a token renamed out from under the rule is exactly the
 * failure that looks fine in the diff.
 *
 * THE SECOND IS A CHARACTER. A sentence written with backticks in it renders them - `d2w fhir
 * generate` arrives on screen wearing two marks and no change of face - and the empty states and
 * refusals are where the app talks about commands most. Those states need a server that answers
 * with nothing, or does not answer, so they are reached by intercepting the read rather than by
 * finding a project that happens to be broken.
 */

/** What the browser actually paints as an element's background, resting and under the pointer. */
async function fillUnderPointer(page: Page, selector: string): Promise<{ resting: string; hovered: string }> {
    const target = page.locator(selector).first()
    await expect(target).toBeVisible()
    const resting = await target.evaluate((element) => globalThis.getComputedStyle(element).backgroundColor)
    await target.hover()
    // The fill transitions over 150ms, so the value is read once it has settled rather than mid-way.
    await expect
        .poll(async () =>
            target.evaluate((element) => globalThis.getComputedStyle(element).backgroundColor),
        )
        .not.toBe(resting)
    const hovered = await target.evaluate((element) => globalThis.getComputedStyle(element).backgroundColor)
    return { resting, hovered }
}

test('a terminology row is painted under the pointer and ends in the mark that says it opens', async ({
    page,
}) => {
    await page.goto('/#/terminology')

    const row = page.getByRole('table').first().getByRole('row').nth(1)
    await expect(row).toBeVisible()
    // The mark is on the row before anything is hovered: on a list, it is what says these open.
    await expect(row.locator('.interactive-mark')).toHaveCount(1)
    await expect(row.locator('.interactive-title')).toHaveCount(1)

    const { resting, hovered } = await fillUnderPointer(page, 'table tbody tr')
    expect(hovered).not.toBe(resting)
})

test('a form card is painted the same way a row is, so one hover means one thing', async ({ page }) => {
    await page.goto('/#/forms')

    const { resting, hovered } = await fillUnderPointer(page, 'a.interactive')
    expect(hovered).not.toBe(resting)
})

test('a link inside prose is coloured before the pointer arrives, not after it', async ({ page }) => {
    // The category option combo, whose cells link down into the categories they are met from.
    await page.goto('/#/terminology/CodeSystem/d2-aoc-idcDPkDtepR-cs')

    const link = page.getByRole('link', { name: 'Improve access to clean water' }).first()
    await expect(link).toBeVisible()
    // The claim is that its colour is not the colour of the text around it, with nothing hovered:
    // a word coloured only under a pointer is a word nobody knows to point at, and on a touch
    // screen there is no pointer at all.
    const linkColour = await link.evaluate((element) => globalThis.getComputedStyle(element).color)
    const proseColour = await page
        .getByRole('heading', { level: 2 })
        .evaluate((element) => globalThis.getComputedStyle(element).color)
    expect(linkColour).not.toBe(proseColour)
})

/**
 * Every page whose own prose names a command, a path, or a setting somewhere on it.
 *
 * The Server page is not among them, and the omission is the point: almost everything on it is the
 * served CapabilityStatement's own text - the implementation description, the authentication
 * posture, what each operation documents itself as - written in `dhis2w_fhir_serve/capability.py`
 * rather than here. This spec is about what this app writes.
 */
const PAGES_THAT_TALK_ABOUT_COMMANDS = [
    { route: '', name: 'Overview' },
    { route: 'forms', name: 'Forms' },
    { route: 'responses', name: 'Responses' },
    { route: 'terminology', name: 'Terminology' },
    { route: 'organisation-units', name: 'Organisation units' },
]

for (const { route, name } of PAGES_THAT_TALK_ABOUT_COMMANDS) {
    test(`${name} spells a command as a face rather than as two characters`, async ({ page }) => {
        await page.goto(`/#/${route}`)
        await expect(page.getByRole('heading', { level: 2 })).toBeVisible()
        expect(await page.locator('body').innerText()).not.toContain('`')
    })
}

test('the reference beside the editor sets its function names in mono, marks and all gone', async ({
    page,
}) => {
    await page.goto('/#/evaluate')
    await page.getByRole('button', { name: 'Expand the examples panel' }).click()
    // The panel opens on the examples; the vocabulary is a tab away, one per language.
    await page.getByRole('tab', { name: 'FHIRPath' }).click()

    const reference = page.getByTestId('evaluate-reference')
    await expect(reference).toBeVisible()
    expect(await reference.innerText()).not.toContain('`')
    // The marks became elements rather than being deleted: the panel is full of them.
    expect(await reference.locator('code').count()).toBeGreaterThan(8)
})

test('a project publishing no Questionnaires is told which command writes them', async ({ page }) => {
    await page.route(
        (url) => url.pathname.endsWith('/Questionnaire'),
        (route) =>
            route.fulfill({
                contentType: 'application/fhir+json',
                body: JSON.stringify({ resourceType: 'Bundle', type: 'searchset', total: 0, entry: [] }),
            }),
    )
    await page.goto('/#/forms')

    const empty = page.getByText('This project publishes no Questionnaires')
    await expect(empty).toBeVisible()
    await expect(empty.locator('code', { hasText: 'd2w fhir generate' })).toHaveCount(1)
    expect(await empty.innerText()).not.toContain('`')
})

/**
 * The refusal names the process, and names it in the mono face.
 *
 * Read through the status menu rather than through the Server page's own refusal card, because a
 * `/metadata` that never answers leaves the shell with no posture and therefore no page at all -
 * the menu is what the shell says is left to say. The sentence is the same one the Server and
 * Overview cards state, so this is the one place it has to be right.
 */
test('a server that stops answering is named as the process a reader can go and restart', async ({
    page,
}) => {
    await page.route(
        (url) => url.pathname.endsWith('/metadata'),
        (route) => route.abort(),
    )
    await page.goto('/#/server')

    await page.getByRole('button', { name: 'Unreachable' }).click()
    const said = page.getByText('No answer from the server.')
    await expect(said).toBeVisible()
    await expect(said.locator('code', { hasText: 'd2w fhir serve --ui' })).toHaveCount(1)
    expect(await said.innerText()).not.toContain('`')
})

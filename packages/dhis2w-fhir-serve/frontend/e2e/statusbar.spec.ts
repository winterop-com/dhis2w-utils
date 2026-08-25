import { expect, test } from '@playwright/test'

/**
 * The summary bar at the foot of the content area, on the pages that count three different things.
 *
 * WHAT IS ACTUALLY UNDER TEST. Not the words - those are the pages' and they will be reworded -
 * but the three things that can break silently. The bar is on every page, whether or not the page
 * has anything to say. It is OUTSIDE the scroll, so it is still on screen at the bottom of a long
 * listing rather than having been scrolled past with the last row. And the line belongs to the
 * page on screen: navigating away must not leave the previous page's numbers under the next one.
 *
 * Three representative pages: a listing whose count comes from the spool, a listing whose counts
 * come from three FHIR searches at once, and a screen with no listing at all.
 */

const bar = (page: import('@playwright/test').Page) => page.getByTestId('status-bar')
const summary = (page: import('@playwright/test').Page) => page.getByTestId('status-bar-summary')

test('the terminology listing states its three counts', async ({ page }) => {
    await page.goto('/#/terminology')

    await expect(summary(page)).toContainText(/\d+ code systems? - \d+ value sets? - \d+ concept maps?/)
})

test('the filter states how much of the listing it admits', async ({ page }) => {
    await page.goto('/#/terminology')
    await expect(summary(page)).toContainText('code systems')

    await page.getByRole('textbox', { name: 'Filter terminology' }).fill('OsSymptom01')

    await expect(page.getByTestId('status-bar-note')).toContainText(/rows? match/)
})

test('the responses listing says how much of the spool is on screen', async ({ page }) => {
    await page.goto('/#/responses')

    await expect(summary(page)).toContainText(/Showing \d+ of \d+ receipts?/)
})

test('the server page counts what the conformance document declares', async ({ page }) => {
    await page.goto('/#/server')

    await expect(summary(page)).toContainText(/\d+ resource types? served - \d+ operations? declared/)
})

test('the bar stays on screen at the bottom of a long listing', async ({ page }) => {
    // The data-dictionary code system is the longest table the fixture publishes, and its own
    // paging line is the thing that used to run flush against the window's bottom edge.
    await page.goto('/#/terminology/CodeSystem/d2-de-cs')
    await expect(summary(page)).toContainText(/Showing \d+ of \d+ concepts/)

    await page.mouse.wheel(0, 4000)

    await expect(bar(page)).toBeInViewport()
    await expect(summary(page)).toContainText(/Showing \d+ of \d+ concepts/)
})

test('the line belongs to the page on screen and not to the one before it', async ({ page }) => {
    await page.goto('/#/terminology')
    await expect(summary(page)).toContainText('concept maps')

    await page.goto('/#/server')

    // Whatever the server page ends up saying, it is not the terminology page's sentence - and the
    // bar itself is still drawn, because it closes every page rather than the ones with numbers.
    await expect(bar(page)).toBeVisible()
    await expect(summary(page)).not.toContainText('concept maps')
})

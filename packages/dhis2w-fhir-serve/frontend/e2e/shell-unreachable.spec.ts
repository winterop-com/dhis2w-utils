import { expect, test } from '@playwright/test'

/**
 * What the shell does when the server behind it stops answering.
 *
 * THE POSTURE COMES OFF `/metadata`, which means an unanswered probe leaves the app not knowing
 * whether to ask for a credential - and a shell that draws no page while it waits draws no page at
 * all, for as long as the tab is open. The failure this file exists for is exactly that screen: a
 * blank column with one word in the corner, and a command palette that had gone silent with it.
 *
 * The server is not touched. `/metadata` is aborted in this page's own browser context, which is
 * what makes the case reproducible without disturbing anything else the run is doing.
 */

test('says the server is not answering, in the place the page would have been', async ({ page }) => {
    await page.route('**/metadata', (route) => route.abort())

    await page.goto('/')

    await expect(page.getByText('This server is not answering')).toBeVisible()
    await expect(page.getByRole('main')).toContainText('d2w fhir serve --ui')
})

test('keeps the palette open to the pages, which are reachable whatever the server says', async ({
    page,
}) => {
    await page.route('**/metadata', (route) => route.abort())

    await page.goto('/')
    await expect(page.getByText('This server is not answering')).toBeVisible()

    await page.getByRole('button', { name: 'Command palette' }).click()
    const palette = page.getByRole('dialog', { name: 'Command palette' })
    await expect(palette).toBeVisible()

    // The rows that read from the server come back empty and say nothing; the pages are still pages.
    await expect(palette.getByRole('option', { name: /^Evaluate/ })).toBeVisible()
})

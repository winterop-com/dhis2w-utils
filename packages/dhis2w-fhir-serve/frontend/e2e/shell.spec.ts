import { expect, test } from '@playwright/test'

/**
 * The shell: the bundle loads off the real server, and the rail reaches every page.
 *
 * This is the spec that would have caught the mount-ordering bug the `ui.py`
 * docstring is written around. A UI whose `/assets/index-<hash>.js` is claimed by
 * the FHIR read catch-all renders a white page with a 404 in the console, and
 * nothing about that failure says "router table". Here it is a failed
 * assertion on the first line.
 */

test('the bundle loads with no console errors and no failed requests', async ({ page }) => {
    const consoleErrors: string[] = []
    const failedRequests: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('response', (response) => {
        if (response.status() >= 400) failedRequests.push(`${String(response.status())} ${response.url()}`)
    })

    await page.goto('/')

    // The root route is the Overview, not a redirect to a listing.
    await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
    expect(failedRequests, failedRequests.join('\n')).toEqual([])
})

test('the rail navigates all six pages', async ({ page }) => {
    await page.goto('/')

    // The rail's links carry the page name as their aria-label - see NAV_ITEMS
    // in components/AppLayout.tsx, which is the one place a page is registered.
    const rail = page.getByRole('complementary')

    await rail.getByRole('link', { name: 'Forms' }).click()
    await expect(page).toHaveURL(/#\/forms$/)
    await expect(page.getByRole('heading', { name: 'Forms', level: 2 })).toBeVisible()

    await rail.getByRole('link', { name: 'Responses' }).click()
    await expect(page).toHaveURL(/#\/responses$/)
    await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()

    await rail.getByRole('link', { name: 'Org units' }).click()
    await expect(page).toHaveURL(/#\/org-units$/)
    await expect(page.getByRole('heading', { name: 'Org units', level: 2 })).toBeVisible()

    await rail.getByRole('link', { name: 'Terminology' }).click()
    await expect(page).toHaveURL(/#\/terminology$/)
    await expect(page.getByRole('heading', { name: 'Terminology', level: 2 })).toBeVisible()

    await rail.getByRole('link', { name: 'Server' }).click()
    await expect(page).toHaveURL(/#\/server$/)
    await expect(page.getByRole('heading', { name: 'Server', level: 2 })).toBeVisible()

    // Exact: the wordmark above the rail is a link home too, and its label
    // ("Capture overview") contains this one.
    await rail.getByRole('link', { name: 'Overview', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Overview', level: 2 })).toBeVisible()
})

test('a deep hash route survives a reload', async ({ page }) => {
    // Hash routing is what lets the SPA be a static mount with no server-side
    // rewrite: `#/server` never reaches the server as a path at all.
    await page.goto('/#/server')
    await expect(page.getByRole('heading', { name: 'Server', level: 2 })).toBeVisible()

    await page.reload()

    await expect(page.getByRole('heading', { name: 'Server', level: 2 })).toBeVisible()
})

test('the status header reports the served guide', async ({ page }) => {
    await page.goto('/')

    // The reachability light reads `/metadata`; the fixture project's title is
    // what the CapabilityStatement description leads with.
    await expect(page.getByRole('button', { name: /Server status/ })).toContainText('DHIS2 FHIR Capture IG')
})

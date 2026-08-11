import { expect, test, type Page } from '@playwright/test'

/**
 * The two things `/uiconfig` decides: which basemap layers the map offers, and which DHIS2 instance
 * the screens link identities into.
 *
 * WHY THIS ONE FILE FULFILS `/uiconfig` RATHER THAN READING IT. Every other spec in this suite runs
 * against the real `d2w fhir serve --ui`, and it stays that way here for everything except this one
 * endpoint. `/uiconfig` is the whole of what "how was this process started" means to the browser -
 * a project's configured layers, and whether the machine running the server resolved a profile at
 * all. The suite drives ONE server process, so a spec proving the layer switch and a spec proving
 * the no-instance case cannot both be true of the same started process; and whether a developer's
 * machine happens to have a `profiles.toml` is a property of the machine rather than of this code,
 * which is exactly the kind of thing a browser test must not depend on. Fulfilling this one route
 * is therefore not mocking the thing under test - it is starting the process differently, which is
 * all the endpoint ever reported. What the server really answers is held by the pytest suite over
 * the route and by the `basemaps = []` assertion in orgunits.spec.ts.
 *
 * THE TILES ARE FULFILLED IN THE BROWSER, so this file reaches no tile host either. The layers name
 * addresses nothing serves; every request to them is answered here with a one-pixel PNG, and a
 * request escaping that rule would fail the run rather than quietly leave the machine.
 */

/** A one-pixel transparent PNG, which is every tile any layer in this file ever gets. */
const PIXEL = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
    'base64',
)

/** The layers the fulfilled `/uiconfig` offers - two, so "the first one opens" is a real claim. */
const STREETS = { name: 'Streets', url: 'https://streets.test/{z}/{x}/{y}.png', attribution: null }
const AERIAL = { name: 'Aerial', url: 'https://aerial.test/{z}/{x}/{y}.png', attribution: null }

/** The DHIS2 instance the linking cases pretend this server resolved a profile for. */
const INSTANCE = 'https://dhis2.test/instance'

/** The map's own answer for which ground it is drawing, waited on rather than guessed at. */
const MAP_READY_TIMEOUT = 15_000

/** Serve one `/uiconfig` answer, and a pixel for any tile the layers in it ask for. */
async function serveSettings(
    page: Page,
    settings: { basemaps: typeof STREETS[]; dhis2_base_url: string | null },
): Promise<void> {
    await page.route('**/uiconfig', (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(settings) }),
    )
    await page.route('https://*.test/**', (route) =>
        route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL }),
    )
}

test('the layer control offers every configured layer and None, and opens on the first', async ({ page }) => {
    await serveSettings(page, { basemaps: [STREETS, AERIAL], dhis2_base_url: null })

    await page.goto('/#/organisation-units')
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: MAP_READY_TIMEOUT })

    // The first configured layer is the ground, because the order is the deployment's preference.
    await expect(map).toHaveAttribute('data-map-basemap', 'Streets')

    await page.getByRole('button', { name: 'Choose the basemap' }).click()
    const menu = page.getByRole('menu', { name: 'Choose the basemap' })
    await expect(menu.getByRole('menuitemradio')).toHaveText(['Streets', 'Aerial', 'None'])
    await expect(menu.getByRole('menuitemradio', { name: 'Streets' })).toHaveAttribute('aria-checked', 'true')
})

test('switching the layer swaps the raster source, and None draws no tiles at all', async ({ page }) => {
    await serveSettings(page, { basemaps: [STREETS, AERIAL], dhis2_base_url: null })

    const tileHosts: string[] = []
    page.on('request', (request) => {
        const host = new URL(request.url()).hostname
        if (host === 'streets.test' || host === 'aerial.test') {
            tileHosts.push(host)
        }
    })

    await page.goto('/#/organisation-units')
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: MAP_READY_TIMEOUT })
    await expect.poll(() => tileHosts.includes('streets.test'), { timeout: MAP_READY_TIMEOUT }).toBe(true)

    await page.getByRole('button', { name: 'Choose the basemap' }).click()
    await page.getByRole('menuitemradio', { name: 'Aerial' }).click()

    // The source really was swapped: the second host is asked for tiles, off the same camera.
    await expect(map).toHaveAttribute('data-map-basemap', 'Aerial')
    await expect.poll(() => tileHosts.includes('aerial.test'), { timeout: MAP_READY_TIMEOUT }).toBe(true)
    // And the map is still a map - the switch is a source swap, not a rebuild that loses the scene.
    await expect(map).toHaveAttribute('data-map-ready', 'true')

    const asked = tileHosts.length
    await page.getByRole('button', { name: 'Choose the basemap' }).click()
    await page.getByRole('menuitemradio', { name: 'None' }).click()

    await expect(map).toHaveAttribute('data-map-basemap', 'None')
    // Nothing further is fetched from either host: None is the boundary-only canvas, in full.
    await page.waitForTimeout(500)
    expect(tileHosts.length, tileHosts.join('\n')).toBe(asked)
})

test('an identity links into the instance the server resolved a profile for', async ({ page }) => {
    await serveSettings(page, { basemaps: [], dhis2_base_url: INSTANCE })

    await page.goto('/#/organisation-units?unit=DiszpKrYNg8')

    // The organisation unit itself, from the rail header that names it.
    const unit = page.getByRole('link', {
        name: "Open the organisation unit Ngelehun CHC in this DHIS2 instance's Maintenance app",
    })
    await expect(unit).toHaveAttribute(
        'href',
        `${INSTANCE}/dhis-web-maintenance/index.html#/edit/organisationUnitSection/organisationUnit/DiszpKrYNg8`,
    )
    // Opened elsewhere, and with no handle back to this page.
    await expect(unit).toHaveAttribute('target', '_blank')
    await expect(unit).toHaveAttribute('rel', 'noreferrer noopener')

    // And the forms shelved at that unit: a data set links to its data set, a stage to its stage.
    const shelf = page.getByTestId('org-unit-forms')
    await expect(shelf.getByRole('link', { name: /Open the data set .* Maintenance app/ }).first()).toHaveAttribute(
        'href',
        /#\/edit\/dataSetSection\/dataSet\/[A-Za-z0-9]+$/,
    )
    await expect(
        shelf.getByRole('link', { name: /Open the program stage .* Maintenance app/ }).first(),
    ).toHaveAttribute('href', /#\/edit\/programSection\/programStage\/[A-Za-z0-9]+$/)
})

test('a data element concept row opens the data element it is the uid of', async ({ page }) => {
    await serveSettings(page, { basemaps: [], dhis2_base_url: INSTANCE })

    await page.goto('/#/terminology/CodeSystem/d2-de-cs')

    const row = page.getByRole('row').filter({ hasText: 'DeAncDanger' })
    await expect(row.getByRole('link')).toHaveAttribute(
        'href',
        `${INSTANCE}/dhis-web-maintenance/index.html#/edit/dataElementSection/dataElement/DeAncDanger`,
    )
})

test('a server that resolved no profile shows no link out at all', async ({ page }) => {
    await serveSettings(page, { basemaps: [], dhis2_base_url: null })

    await page.goto('/#/organisation-units?unit=DiszpKrYNg8')
    await expect(page.getByRole('heading', { name: 'Ngelehun CHC' })).toBeVisible()

    // Not a disabled affordance, not a link to a search page - nothing, because there is nowhere
    // honest to point: this guide names no instance it was generated from.
    await expect(page.getByTestId('maintenance-link')).toHaveCount(0)

    await page.goto('/#/terminology/CodeSystem/d2-de-cs')
    await expect(page.getByRole('row').filter({ hasText: 'DeAncDanger' })).toBeVisible()
    await expect(page.getByTestId('maintenance-link')).toHaveCount(0)
})

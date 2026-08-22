import { expect, test, type Locator, type Page } from '@playwright/test'

/**
 * The map's own interactions, beyond mounting: the globe view, the two click gestures, the legend.
 *
 * Everything here drives the fixture registry orgunits.spec.ts documents - ten organisation units
 * over four levels, four boundaries and four points, `basemaps = []`. What this file adds is
 * the interaction model on top of those shapes: a left-click on any shape opens the info popup and
 * Open is the deliberate selection; a right-click drills straight down; the globe control eases
 * the camera out to where the curvature reads and flies back to exactly the framing it left.
 *
 * THE CAMERA IS ASSERTED THROUGH DATA ATTRIBUTES. `data-map-zoom` and `data-map-projection` are
 * the renderer's own answers, exposed on the container - a spec that read pixels to decide whether
 * a globe happened would be guessing at SwiftShader's rasteriser.
 */

/** How long the engine gets to fetch, paint, and settle - the same allowance orgunits.spec uses. */
const MAP_READY_TIMEOUT = 15_000

/** Open one page of the hierarchy and wait until the map has painted its layers. */
async function openMap(page: Page, path: string): Promise<Locator> {
    await page.goto(path)
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: MAP_READY_TIMEOUT })
    return map
}

/** The zoom the camera has settled at, as the container states it. */
async function settledZoom(map: Locator): Promise<number> {
    return Number((await map.getAttribute('data-map-zoom')) ?? '0')
}

test('the legend names the three tiers in full, and each row explains itself', async ({ page }) => {
    await openMap(page, '/#/organisation-units')

    await expect(page.getByText('Selected organisation unit')).toBeVisible()
    await expect(page.getByText('Below the selection')).toBeVisible()
    await expect(page.getByText('Other organisation units')).toBeVisible()
    // The tier names lean on the selection model; hovering a row states it in one plain sentence.
    await expect(page.getByText('Other organisation units')).toHaveAttribute(
        'title',
        'Organisation units this implementation guide publishes that are outside your selection.',
    )
})

test('the globe control switches projection in place, and the recenter fit works on the globe', async ({
    page,
}) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })

    const map = await openMap(page, '/#/organisation-units')
    await expect(map).toHaveAttribute('data-map-projection', 'mercator')

    // The fit settles well above the world zoom before the globe is entered.
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(3)
    const flatZoom = await settledZoom(map)

    const enter = page.getByRole('button', { name: 'View as a globe' })
    await expect(enter).toBeVisible()
    await enter.click()

    // A pure projection switch: the camera has not moved, only the geometry under it curves.
    await expect(map).toHaveAttribute('data-map-projection', 'globe')
    expect(await settledZoom(map)).toBeCloseTo(flatZoom, 1)

    // The recenter fit resolves on the globe without leaving it: wander out a step, come back.
    // The page opens on the root selected by default, so the button names the selection.
    await map.locator('canvas').evaluate((element) => {
        element.focus()
    })
    await page.keyboard.press('-')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeLessThan(flatZoom - 0.5)
    await page.getByRole('button', { name: 'Center on the selected organisation unit' }).click()
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeCloseTo(flatZoom, 1)
    await expect(map).toHaveAttribute('data-map-projection', 'globe')

    // The same button is the way back, and it moves nothing either.
    await page.getByRole('button', { name: 'View as a flat map' }).click()
    await expect(map).toHaveAttribute('data-map-projection', 'mercator')
    expect(await settledZoom(map)).toBeCloseTo(flatZoom, 1)

    // The shapes survived the projection round-trip: a right-click still drills into the unit
    // under the canvas centre, which is Sierra Leone's own boundary.
    await map.locator('canvas').click({ button: 'right' })
    await expect.poll(() => page.url()).toMatch(/#\/organisation-units\?unit=ImspTQPwCqd$/)

    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
})

test('the globe hangs in a starfield, and the flat map shows none of it', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })

    const map = await openMap(page, '/#/organisation-units')
    const starfield = page.getByTestId('org-unit-map-starfield')

    // The flat map wears no universe: the element is not merely hidden, it does not exist.
    await expect(starfield).toHaveCount(0)

    await page.getByRole('button', { name: 'View as a globe' }).click()
    await expect(map).toHaveAttribute('data-map-projection', 'globe')

    // Entering the globe puts deep space behind the transparent canvas: the element is there,
    // painted near-black with the stars as tiled data URIs - no network request for a sky.
    await expect(starfield).toBeVisible()
    await expect(starfield).toHaveCSS('background-color', 'rgb(5, 8, 15)')
    expect(await starfield.evaluate((element) => getComputedStyle(element).backgroundImage)).toContain(
        'data:image/svg+xml',
    )

    // Leaving the globe takes the universe down with it.
    await page.getByRole('button', { name: 'View as a flat map' }).click()
    await expect(map).toHaveAttribute('data-map-projection', 'mercator')
    await expect(starfield).toHaveCount(0)

    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
})

test('a left-click on a boundary opens the popup, and Open is what selects', async ({ page }) => {
    const map = await openMap(page, '/#/organisation-units')

    // The registry fit must sit above the boundary threshold for the click to ask rather than
    // drill - this guard fails loudly if the framing maths ever changes under the spec.
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(5.5)

    // The canvas centre is inside Sierra Leone's boundary, the outermost shape the fixture
    // publishes - the same geometry fact orgunits.spec leans on for its right-click.
    await map.locator('canvas').click()

    const popup = page.getByTestId('org-unit-map-popup')
    await expect(popup).toBeVisible()
    await expect(popup).toContainText('Sierra Leone')
    // The level is spelled the human way, never in the machine casing.
    await expect(popup).toContainText('Level 1')
    await expect(popup).not.toContainText('level-1')
    // Sierra Leone holds the whole served subtree bar the detached orphan.
    await expect(popup).toContainText('8 organisation units below')

    // The click asked a question; it did not write a selection into the address.
    expect(page.url()).not.toContain('unit=')

    await popup.getByTestId('org-unit-map-popup-open').click()

    await expect.poll(() => page.url()).toMatch(/#\/organisation-units\?unit=ImspTQPwCqd$/)
    await expect(page.getByRole('heading', { name: 'Sierra Leone', level: 3 })).toBeVisible()
    // Open answered the question, so the popup has nothing left to say.
    await expect(popup).toHaveCount(0)
})

test('the popup wears the app card tokens in both themes', async ({ page }) => {
    // MapLibre's own stylesheet ships inside the lazy map chunk, AFTER index.css - so the shell
    // being themed is no evidence the popup is: a same-specificity override loses to it silently
    // and leaves MapLibre's white card under dark ink. The computed styles are compared against
    // the card token as the browser resolves it, which is the only honest reading of a token.
    const map = await openMap(page, '/#/organisation-units')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(5.5)
    await map.locator('canvas').click()
    await expect(page.getByTestId('org-unit-map-popup')).toBeVisible()

    const resolvedCardColor = () =>
        page.evaluate(() => {
            const probe = document.createElement('div')
            probe.style.backgroundColor = 'var(--card)'
            document.body.append(probe)
            const resolved = getComputedStyle(probe).backgroundColor
            probe.remove()
            return resolved
        })
    const popupShellColors = () =>
        page.evaluate(() => {
            const content = document.querySelector('.maplibregl-popup-content')
            const tip = document.querySelector('.maplibregl-popup-tip')
            if (content === null || tip === null) return null
            const tipStyles = getComputedStyle(tip)
            return {
                background: getComputedStyle(content).backgroundColor,
                // The tip's one coloured border depends on the anchor, so all four are read and
                // the assertion is that the card colour is among them.
                tipBorders: [
                    tipStyles.borderTopColor,
                    tipStyles.borderBottomColor,
                    tipStyles.borderLeftColor,
                    tipStyles.borderRightColor,
                ],
            }
        })

    const lightCard = await resolvedCardColor()
    const lightShell = await popupShellColors()
    expect(lightShell?.background).toBe(lightCard)
    expect(lightShell?.tipBorders).toContain(lightCard)

    // The popup survives a theme flip - only its tokens change under it.
    await page.getByRole('button', { name: 'Switch to dark mode' }).click()
    await expect(map).toHaveAttribute('data-map-theme', 'dark')

    const darkCard = await resolvedCardColor()
    expect(darkCard).not.toBe(lightCard)
    expect(darkCard).not.toBe('rgb(255, 255, 255)')
    await expect.poll(async () => (await popupShellColors())?.background).toBe(darkCard)
    expect((await popupShellColors())?.tipBorders).toContain(darkCard)
})

test('typing in the filter with an unresolved ?unit= does not re-frame the map', async ({ page }) => {
    // A ?unit= naming a unit this registry does not hold selects nothing, so the framing target
    // is the whole registry - and it must be THE SAME framing on every render: a focus prop
    // minted fresh per render re-ran the fit and closed the popup on every keystroke in the
    // filter box. The camera is stepped off the fitted framing first, so a spurious re-fit would
    // be visible as the zoom snapping back.
    const map = await openMap(page, '/#/organisation-units?unit=NotPublished0')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(3)
    const framed = await settledZoom(map)

    await map.locator('canvas').evaluate((element) => {
        element.focus()
    })
    await page.keyboard.press('-')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeLessThan(framed - 0.5)
    const wandered = await settledZoom(map)

    await page.getByRole('textbox', { name: 'Filter organisation units' }).pressSequentially('bo')
    // A re-fit eases over 400ms; give it its full window to happen, then assert it did not.
    await page.waitForTimeout(900)
    expect(await settledZoom(map)).toBeCloseTo(wandered, 2)
})

test('a right-click on a shape drills straight down, with no popup in between', async ({ page }) => {
    const map = await openMap(page, '/#/organisation-units')

    await map.locator('canvas').click({ button: 'right' })

    await expect.poll(() => page.url()).toMatch(/#\/organisation-units\?unit=ImspTQPwCqd$/)
    await expect(page.getByTestId('org-unit-map-popup')).toHaveCount(0)
})

test('zoomed out, a left-click steps in toward the click instead of asking', async ({ page }) => {
    const map = await openMap(page, '/#/organisation-units')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(3)

    // Zoom out until the boundaries stop reading as shapes - below the drill threshold. Driven
    // through MapLibre's own keyboard handler: a wheel or a double-click would also run the click
    // gestures under test, and a spec must not trip over the thing it is measuring.
    const canvas = map.locator('canvas')
    await canvas.evaluate((element) => {
        element.focus()
    })
    // Sequential on purpose: each zoom step must settle before the next reads the camera.
    // oxlint-disable no-await-in-loop
    for (let step = 0; step < 12 && (await settledZoom(map)) >= 4; step += 1) {
        await page.keyboard.press('-')
        await page.waitForTimeout(400)
    }
    // oxlint-enable no-await-in-loop
    const farOut = await settledZoom(map)
    expect(farOut).toBeLessThan(4)

    await canvas.click()

    // No popup at speck scale - the click eases a two-level step in toward where it landed.
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeCloseTo(farOut + 2, 1)
    await expect(page.getByTestId('org-unit-map-popup')).toHaveCount(0)
})

test('the recenter control returns to the current framing, and says what it centres on', async ({
    page,
}) => {
    // A deep link to a unit this registry does not hold is the one state with no selection at
    // all - there the framing target is the whole registry, and the label says so.
    const map = await openMap(page, '/#/organisation-units?unit=NotPublished0')
    await expect(page.getByRole('button', { name: 'Center on the organisation units' })).toBeVisible()

    // With a selection the button recentres on it - wander off, then come back. Bo's fit sits
    // well above the registry framing the previous state left, so waiting for it to pass 7 is
    // what proves the new fit settled before its zoom is taken as the baseline.
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')
    const button = page.getByRole('button', { name: 'Center on the selected organisation unit' })
    await expect(button).toBeVisible()
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeGreaterThan(7)
    const framed = await settledZoom(map)

    await map.locator('canvas').evaluate((element) => {
        element.focus()
    })
    await page.keyboard.press('-')
    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeLessThan(framed - 0.5)

    await button.click()

    await expect
        .poll(() => settledZoom(map), { timeout: MAP_READY_TIMEOUT })
        .toBeCloseTo(framed, 1)
})

test('a point outranks the boundaries under it, and its popup says where it sits', async ({ page }) => {
    // Ngelehun CHC is a facility pin inside three nested boundaries. Selecting it centres the
    // camera on the pin at the single-point zoom, so the canvas centre is the pin itself.
    const map = await openMap(page, '/#/organisation-units?unit=DiszpKrYNg8')
    await expect
        .poll(async () => map.getAttribute('data-map-zoom'), { timeout: MAP_READY_TIMEOUT })
        .toBe('9.00')

    // Hovering the pin is an offer, and the cursor says so.
    const canvas = map.locator('canvas')
    await canvas.hover()
    await expect.poll(() => canvas.evaluate((element) => element.style.cursor)).toBe('pointer')

    await canvas.click()

    const popup = page.getByTestId('org-unit-map-popup')
    await expect(popup).toBeVisible()
    // The pin, not Badjia, Bo, or Sierra Leone stacked under it.
    await expect(popup).toContainText('Ngelehun CHC')
    await expect(popup).toContainText('Level 4')
    // The parent gives the pin its place.
    await expect(popup).toContainText('Badjia')
})

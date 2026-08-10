import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The organisation-unit browser, against the registry the fixture project really publishes.
 *
 * Ten organisation units over four levels published as eleven Locations - the eleventh being the
 * curated profile exemplar a generated IG ships beside its registry - with every geometry state on
 * them and two forms assigned to two of them. See `ORG_UNITS` in
 * packages/dhis2w-fhir-serve/tests/fixture_project.py. The reason that registry exists at all is
 * this page: the `partOf` fold, the identifier dedupe, the geometry decode, and the assignment join
 * are four rules whose failure modes are invisible against a registry of nothing.
 *
 * THE LAYOUT UNDER TEST IS THE THREE-PANE ONE. At the suite's default 1280px viewport the page
 * runs tree | map canvas | inspector rail, so the rail's sections are asserted directly, with no
 * tab clicks. The narrow fallback - the same sections behind tabs - has a spec of its own at a
 * sub-breakpoint viewport.
 *
 * THE PROJECT SETS `basemap = "none"`. A suite that fetched real tiles would be asserting on
 * somebody else's uptime and would make an offline test run reach the internet, so the browser here
 * draws the boundary-only map. The tiles-on style is covered by src/lib/basemap.test.ts.
 *
 * WHAT THE MAP IS ASSERTED ON. Headless chromium here renders WebGL through SwiftShader, so the
 * canvas really is acquired and the assertion is the positive one: the canvas mounts, and the page
 * logs no console error. The component degrades to a stated note rather than a crash when no
 * context can be had, and the note carries its own test id - so an environment without WebGL fails
 * this spec on a missing canvas rather than on a stack trace, which is the failure worth reading.
 */

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

    const location = posted.headers()['location']
    expect(location).toBeTruthy()
    return location.split('/').pop() ?? ''
}

test('the tree renders the roots and expands on demand', async ({ page }) => {
    await page.goto('/#/org-units')

    await expect(page.getByRole('heading', { name: 'Org units', level: 2 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sierra Leone', exact: true })).toBeVisible()

    // Adonkia CHP names a parent this project never published, so it is a root of its own.
    await expect(page.getByRole('button', { name: 'Adonkia CHP', exact: true })).toBeVisible()
    await expect(page.getByText('name a parent this project did not publish')).toBeVisible()

    // The registry also publishes the profile exemplar, which claims Sierra Leone's uid and hangs
    // off nothing. One unit, one row - not two roots with the same name.
    await expect(page.getByRole('button', { name: 'Sierra Leone', exact: true })).toHaveCount(1)
    await expect(page.getByText('10 units')).toBeVisible()

    // A closed node renders none of its children - that is the whole point of lazy expansion.
    await expect(page.getByRole('button', { name: 'Bo', exact: true })).toHaveCount(0)

    await page.getByRole('button', { name: 'Expand Sierra Leone' }).click()

    await expect(page.getByRole('button', { name: 'Bo', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toBeVisible()
})

test('the filter opens the ancestors of what it matches', async ({ page }) => {
    await page.goto('/#/org-units')

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('Ngelehun')

    // Ngelehun sits three levels down; the districts above it are shown so it is not detached.
    await expect(page.getByRole('button', { name: 'Ngelehun CHC', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Badjia', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toHaveCount(0)

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('OU_BOMBALI')
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toBeVisible()

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('nothing matches this')
    await expect(page.getByText('No unit matches that filter.')).toBeVisible()
})

test('selecting a unit fills the inspector, and puts the unit in the address', async ({ page }) => {
    await page.goto('/#/org-units')

    await page.getByRole('button', { name: 'Expand Sierra Leone' }).click()
    await page.getByRole('button', { name: 'Bo', exact: true }).click()

    await expect(page).toHaveURL(/#\/org-units\?unit=O6uvpzGd5pu$/)
    await expect(page.getByRole('heading', { name: 'Bo', level: 3 })).toBeVisible()
    await expect(page.getByTestId('org-unit-level')).toContainText('Level 2')
    // The DHIS2 uid and the org-unit code, each under the system that says which of the two it is.
    const uid = page.getByText('id/org-unitO6uvpzGd5pu')
    await expect(uid).toBeVisible()
    await expect(page.getByText('id/org-unit-codeOU_BO')).toBeVisible()

    // The counts and the child chips sit in the rail's Details section, no clicks between.
    await expect(page.getByText('3 direct children')).toBeVisible()
    // A child chip is a selection, same as a tree row.
    await page.getByRole('button', { name: 'Badjia', exact: true }).click()
    await expect(page).toHaveURL(/#\/org-units\?unit=YuQRtpLP10I$/)
})

test('a unit is a link that opens with its hierarchy already expanded', async ({ page }) => {
    await page.goto('/#/org-units?unit=DiszpKrYNg8')

    await expect(page.getByRole('heading', { name: 'Ngelehun CHC', level: 3 })).toBeVisible()
    await expect(page.getByTestId('org-unit-level')).toContainText('Level 4')

    // The parent chain is clickable, and clicking it moves the selection.
    const chain = page.getByRole('navigation', { name: 'Parent units' })
    await expect(chain).toContainText('Sierra Leone')
    await expect(chain).toContainText('Badjia')
    await chain.getByRole('button', { name: 'Badjia' }).click()
    await expect(page).toHaveURL(/#\/org-units\?unit=YuQRtpLP10I$/)
})

test('the rail shelves the forms by kind, beside a map that never leaves', async ({ page }) => {
    // Bo is one of the two units the fixture's assignment Lists admit.
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    // The whole point of the three-pane shape: the forms are readable while the map is on screen.
    await expect(page.getByTestId('org-unit-map')).toBeVisible()

    // Scoped to the shelves: a receipt in Captured here can carry the same form title, and this
    // spec is about the catalog, not the spool.
    const shelves = page.getByTestId('org-unit-forms')

    // Data sets and programs are different capture surfaces, so they are different shelves.
    await expect(shelves.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'Child Health' })).toBeVisible()
    await expect(shelves.getByRole('heading', { name: 'Programs' })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'Supervision visit' })).toBeVisible()

    // The two forms whose assignment Lists name Bo carry the badge; everything else is assigned
    // everywhere and appears plainly rather than behind a collapse.
    await expect(shelves.getByRole('link', { name: 'Outbreak response' })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'Antenatal care' })).toBeVisible()
    await expect(shelves.getByText('assigned to this unit')).toHaveCount(2)

    // A tracker program is one thing: its stage is grouped under its registration, with the role
    // note saying which row is which.
    await expect(shelves.getByText('registration', { exact: true })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'ANC follow-up - ANC visit' })).toBeVisible()
})

test('a unit outside the assignments is offered only the forms assigned everywhere', async ({ page }) => {
    await page.goto('/#/org-units?unit=ImspTQPwCqd')

    const shelves = page.getByTestId('org-unit-forms')
    await expect(shelves.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    // The two scoped forms are not reportable here, so they are not listed at all - and with no
    // named assignment reaching this unit, nothing carries the badge.
    await expect(shelves.getByRole('link', { name: 'Outbreak response' })).toHaveCount(0)
    await expect(shelves.getByRole('link', { name: 'Antenatal care' })).toHaveCount(0)
    await expect(shelves.getByText('assigned to this unit')).toHaveCount(0)
})

test('a form assigned to one unit opens from that unit', async ({ page }) => {
    await page.goto('/#/org-units?unit=DiszpKrYNg8')

    // Scoped to the shelves: earlier files in the run may have spooled Outbreak captures at
    // Ngelehun, and their receipt rows carry the same title.
    await page.getByTestId('org-unit-forms').getByRole('link', { name: 'Outbreak response' }).click()

    await expect(page).toHaveURL(/#\/forms\/PrScoped001$/)
})

test('the captured-here section joins the spool to the unit the capture named', async ({ page, request }) => {
    // Post a real capture and let the server say which unit the generated answer reports for -
    // the join under test is listing-field to selection, so the spec locates itself from the
    // receipt rather than assuming the draw.
    const receiptId = await generateAndPost(request, 'BfMAe6Itzgt', 77)
    const listing = await (await request.get('/spool')).json()
    const receipt = listing.responses.find(
        (candidate: { response_id: string }) => candidate.response_id === receiptId,
    )
    expect(receipt, 'the spool listing carries the receipt just posted').toBeTruthy()
    const unitId = receipt.organisation_unit
    expect(unitId, 'the listing states the organisation unit per receipt').toBeTruthy()

    await page.goto(`/#/org-units?unit=${unitId}`)

    const captured = page.getByTestId('org-unit-captured')
    await expect(captured.getByRole('heading', { name: 'Captured here' })).toBeVisible()
    // The lifecycle chips count what the spool holds at this unit - at least the one just posted.
    await expect(captured.getByText(/\d+ received/)).toBeVisible()
    // The recent list names the form and links to the receipt.
    await expect(captured.getByRole('link', { name: /Child Health/ }).first()).toBeVisible()
    await expect(captured.getByRole('link', { name: 'All responses' })).toBeVisible()
    // The honest scope: this is the server's spool, not DHIS2's answer.
    await expect(captured.getByText('Captures this server received')).toBeVisible()
})

test('a unit with no captures says so instead of showing a zero', async ({ page, request }) => {
    // Earlier files in the run spool captures at units of the generator's choosing, so the spec
    // asks the listing which published unit is still bare rather than assuming one. Workers run
    // one at a time, so nothing posts between the read and the assertion.
    const listing = await (await request.get('/spool')).json()
    const used = new Set(
        listing.responses.map((candidate: { organisation_unit?: string | null }) => candidate.organisation_unit),
    )
    const bare = ['Rp268JB6Ne4', 'EJoI3HuIUEV', 'MgFYJDBqSSs', 'vWbkYPRmKyS', 'lc3eMKXaEfw', 'YuQRtpLP10I'].find(
        (uid) => !used.has(uid),
    )
    expect(bare, 'every candidate unit already holds a capture - widen this list').toBeTruthy()

    await page.goto(`/#/org-units?unit=${bare ?? ''}`)

    const captured = page.getByTestId('org-unit-captured')
    await expect(captured.getByText('No capture this server received names this unit.')).toBeVisible()
    await expect(captured.getByText('Captures this server received')).toBeVisible()
})

test('the rail collapses to a strip, and a selection reopens it', async ({ page }) => {
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
    const withRail = (await map.boundingBox())?.width ?? 0

    await page.getByRole('button', { name: 'Collapse the unit inspector' }).click()

    // Collapsed, the rail's content is gone and the canvas takes the width it held.
    await expect(page.getByRole('heading', { name: 'This unit' })).toHaveCount(0)
    await expect.poll(async () => (await map.boundingBox())?.width ?? 0).toBeGreaterThan(withRail + 100)

    // Selecting a unit is a question about it, so the inspector opens to answer - the collapse is
    // a view choice, not a standing instruction. Bo's ancestors are already expanded by the URL
    // selection, so Bombali's row is on screen without another chevron.
    await page.getByRole('button', { name: 'Bombali', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'This unit' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Bombali', level: 3 })).toBeVisible()
})

test('the centre canvas owns the column height now the sections live in the rail', async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 })
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    // No tabs at this width - the map is never behind anything.
    await expect(page.getByRole('tab')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Data sets' })).toBeVisible()

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // Well past the 320px floor the stacked layout used to squeeze it to at this height.
    const height = (await map.boundingBox())?.height ?? 0
    expect(height).toBeGreaterThanOrEqual(500)
})

test('below the three-pane breakpoint the sections sit behind tabs, and Map is the default', async ({
    page,
}) => {
    // 1000px is under THREE_PANE_QUERY's 1100px: two columns, and the selection's sections
    // behind tabs so they do not stack the map off screen.
    await page.setViewportSize({ width: 1000, height: 900 })
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    await expect(page.getByRole('tab', { name: 'Map', selected: true })).toBeVisible()
    await expect(page.getByTestId('org-unit-map')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Data sets' })).toHaveCount(0)

    await page.getByRole('tab', { name: 'Forms' }).click()
    await expect(page.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Outbreak response' })).toBeVisible()

    await page.getByRole('tab', { name: 'Details' }).click()
    await expect(page.getByText('3 direct children')).toBeVisible()

    // A new selection opens on Map again - the tab is view state, not part of the link.
    await page.getByRole('button', { name: 'Badjia', exact: true }).click()
    await expect(page).toHaveURL(/#\/org-units\?unit=YuQRtpLP10I$/)
    await expect(page.getByRole('tab', { name: 'Map', selected: true })).toBeVisible()
})

test('the map offers a fullscreen control', async ({ page }) => {
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // Presence, and a click that does not throw, is the whole assertion: actually entering
    // fullscreen from a headless browser is flaky (the request needs a user-activation grant the
    // driver does not reliably confer), so `document.fullscreenElement` is deliberately not
    // asserted. The resize path the control exercises is the same ResizeObserver the viewport
    // specs already cover.
    const button = page.locator('.maplibregl-ctrl-fullscreen')
    await expect(button).toBeVisible()
    await button.click()
})

test('the map mounts a canvas, fetches everything it asks for, and logs nothing', async ({ page }) => {
    const consoleErrors: string[] = []
    const failedRequests: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })
    // The renderer parses GeoJSON off the main thread, and a worker script that 404s is a map that
    // paints its background and draws nothing - with a canvas present and no exception thrown. So
    // the request log is the assertion that the shapes had a chance to exist.
    page.on('response', (response) => {
        if (response.status() >= 400) failedRequests.push(`${String(response.status())} ${response.url()}`)
    })

    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toBeVisible()
    // The renderer is fetched only when this page opens, so the canvas arrives after the shell.
    await expect(map.locator('canvas')).toBeVisible({ timeout: 15_000 })
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
    await expect(page.getByTestId('org-unit-map-unavailable')).toHaveCount(0)

    // Four polygons; four pins, one of which comes from a Point attachment rather than a position.
    // Bo and Badjia state a centroid position beside their polygons and the boundary wins, so
    // neither adds a pin. Only Baoma's payload is genuinely unreadable, and that is the only
    // thing the caption counts.
    await expect(page.getByText('4 boundaries, 4 points')).toBeVisible()
    await expect(page.getByTestId('org-unit-map-unreadable')).toHaveText(
        '1 published geometry could not be read and is not drawn.',
    )

    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
    expect(failedRequests, failedRequests.join('\n')).toEqual([])
})

test('clicking a shape on the map selects the unit it belongs to', async ({ page }) => {
    // Nothing selected, so the map frames the whole registry - and the whole registry sits inside
    // Sierra Leone's own boundary, which means the centre of the canvas is over a shape.
    await page.goto('/#/org-units')

    const map = page.getByTestId('org-unit-map')
    // A click before the layers are on the map lands on an empty scene, so the component states
    // when it has painted them rather than leaving the spec to guess at a delay.
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // The shapes are hit-testable only once the renderer has turned them into geometry, so a click
    // that selects a unit is the proof that the whole path ran - the read, the decode, the worker,
    // and the layer. The point is inside Sierra Leone's own boundary, which is the outermost shape
    // the fixture publishes and therefore the one under an unselected map's centre.
    await map.locator('canvas').click({ position: { x: 200, y: 150 } })

    await expect(page.getByRole('heading', { name: 'Sierra Leone', level: 3 })).toBeVisible()
    // Asserted through a poll rather than `toHaveURL`: the selection is a `replaceState` made from
    // a canvas event handler, and the URL matcher does not always see one.
    await expect.poll(() => page.url()).toMatch(/#\/org-units\?unit=ImspTQPwCqd$/)
})

test('selecting the root frames its extent rather than the world', async ({ page }) => {
    await page.goto('/#/org-units?unit=ImspTQPwCqd')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // The fit is asserted on the camera the engine actually settled at, exposed as an attribute:
    // an unfitted world sits at zoom 1, and Sierra Leone's rectangle lands well above 3 at any
    // canvas size this suite runs. The descendants-union branch of the same priority - a bare
    // parent framed on its located children - is covered by unitExtent's vitest cases, because
    // every geometry-less unit this fixture publishes is a leaf.
    await expect
        .poll(async () => Number((await map.getAttribute('data-map-zoom')) ?? '0'), { timeout: 15_000 })
        .toBeGreaterThan(3)
})

test('a unit with no geometry keeps the map, framed on the nearest unit above it that has some', async ({
    page,
}) => {
    // Kagbere CHC publishes neither a point nor a boundary; Bombali above it publishes a polygon.
    await page.goto('/#/org-units?unit=EJoI3HuIUEV')

    await expect(page.getByTestId('org-unit-map')).toBeVisible()
    await expect(page.getByTestId('org-unit-map-note')).toContainText(
        'DHIS2 holds no geometry for Kagbere CHC, so the map is framed on Bombali',
    )
})

test('a unit with no geometry anywhere near it says so rather than framing on nothing', async ({ page }) => {
    // Adonkia CHP is the orphan: no geometry of its own, no descendants, and its parent is not
    // published at all.
    await page.goto('/#/org-units?unit=Rp268JB6Ne4')

    await expect(page.getByTestId('org-unit-map-note')).toContainText(
        'none for any unit above or below it, so the map shows the whole registry instead',
    )
})

test('the served settings turn the tiles off, and the map honours that', async ({ page }) => {
    const settings = await page.request.get('/uiconfig')

    expect(settings.status()).toBe(200)
    expect(await settings.json()).toEqual({ basemap: null })

    const tileRequests: string[] = []
    page.on('request', (request) => {
        if (/tile|\.png($|\?)/.test(request.url()) && !request.url().includes('/assets/')) {
            tileRequests.push(request.url())
        }
    })

    await page.goto('/#/org-units?unit=O6uvpzGd5pu')
    await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', {
        timeout: 15_000,
    })

    // No tiles asked for, and the caption says so rather than leaving a reader to wonder.
    expect(tileRequests, tileRequests.join('\n')).toEqual([])
    await expect(page.getByText('drawn from this server alone, with no basemap')).toBeVisible()
})

test('the theme reaches the renderer, not just the stylesheet', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await page.goto('/#/org-units?unit=O6uvpzGd5pu')
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
    await expect(map).toHaveAttribute('data-map-theme', 'light')

    await page.getByRole('button', { name: 'Switch to dark theme' }).click()

    // The canvas is painted from resolved token values rather than from CSS, so a theme change has
    // to be pushed into the renderer - and this is the assertion that it was.
    await expect(map).toHaveAttribute('data-map-theme', 'dark')
    await expect(map).toHaveAttribute('data-map-ready', 'true')
    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
})

test('the map takes the height the page has left, and floors rather than collapsing', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1400 })
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // On a tall screen the leftover under the caption is the map's, which is the whole point:
    // the old fixed box left dead space under itself here.
    const tall = (await map.boundingBox())?.height ?? 0
    expect(tall).toBeGreaterThan(500)

    // On a short one it stops at its floor instead of becoming a strip - and `main` scrolls, which
    // the container observer follows without a reload.
    await page.setViewportSize({ width: 1280, height: 900 })
    await expect.poll(async () => (await map.boundingBox())?.height ?? 0).toBeLessThan(tall)
    expect((await map.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(300)
})

test('there is one scroll container on the page, and it is never the document', async ({ page }) => {
    // Sequential on purpose: each iteration resizes the same page and reads what that did, so the
    // steps cannot be run in parallel however much the linter would like them to be.
    // oxlint-disable no-await-in-loop
    for (const height of [1400, 900, 700]) {
        await page.setViewportSize({ width: 1280, height })
        await page.goto('/#/org-units?unit=O6uvpzGd5pu')
        await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', {
            timeout: 15_000,
        })

        const documentScrolls = await page.evaluate(
            () => document.documentElement.scrollHeight > document.documentElement.clientHeight + 2,
        )
        expect(documentScrolls, `the document scrolls at ${String(height)}px tall`).toBe(false)
    }
    // oxlint-enable no-await-in-loop
})

test('the rail reaches the page and the page is not the entry bundle', async ({ page }) => {
    const chunks: string[] = []
    page.on('request', (request) => {
        if (request.url().includes('/assets/') && request.url().endsWith('.js')) chunks.push(request.url())
    })

    await page.goto('/')
    const beforeOpening = chunks.length

    await page.getByRole('complementary').getByRole('link', { name: 'Org units' }).click()

    await expect(page).toHaveURL(/#\/org-units$/)
    await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', {
        timeout: 15_000,
    })
    // The map engine is its own chunk, fetched on arrival here and not with the shell.
    expect(chunks.length).toBeGreaterThan(beforeOpening)
})

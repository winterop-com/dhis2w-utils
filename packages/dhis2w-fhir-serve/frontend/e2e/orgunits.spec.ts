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
 * runs tree | map canvas | inspector rail as three resizable panes, so the rail's sections are
 * asserted directly, with no tab clicks. The narrow fallback - the same sections behind tabs - has
 * a spec of its own at a sub-breakpoint viewport.
 *
 * THE PROJECT OFFERS NO BASEMAP (`basemaps = []`). A suite that fetched real tiles would be
 * asserting on somebody else's uptime and would make an offline test run reach the internet, so the
 * browser here draws the boundary-only map. The layer control over a real offer is covered by
 * uiconfig.spec.ts, which states its own layers over `/uiconfig` and fulfils their tiles in the
 * browser; the tiles-on style itself is covered by src/lib/basemap.test.ts.
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
    await page.goto('/#/organisation-units')

    await expect(page.getByRole('heading', { name: 'Organisation units', level: 2 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sierra Leone', exact: true })).toBeVisible()

    // Adonkia CHP names a parent this project never published, so it is a root of its own.
    await expect(page.getByRole('button', { name: 'Adonkia CHP', exact: true })).toBeVisible()
    await expect(page.getByText('name a parent this project did not publish')).toBeVisible()

    // The registry also publishes the profile exemplar, which claims Sierra Leone's uid and hangs
    // off nothing. One unit, one row - not two roots with the same name.
    await expect(page.getByRole('button', { name: 'Sierra Leone', exact: true })).toHaveCount(1)
    // Scoped to the page: the summary bar states the same count at the foot of the window.
    await expect(page.getByTestId('page-content').getByText('10 organisation units')).toBeVisible()

    // The page opens on the root selected and EXPANDED - the districts are on screen without a
    // click. Lazy expansion still holds below them: a district's own children stay unrendered.
    await expect(page.getByRole('button', { name: 'Bo', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Ngelehun CHC', exact: true })).toHaveCount(0)

    // Collapsing the root takes the districts off screen - expansion is still the reader's to undo.
    await page.getByRole('button', { name: 'Collapse Sierra Leone' }).click()
    await expect(page.getByRole('button', { name: 'Bo', exact: true })).toHaveCount(0)

    await page.getByRole('button', { name: 'Expand Sierra Leone' }).click()
    await expect(page.getByRole('button', { name: 'Bo', exact: true })).toBeVisible()
})

test('the filter opens the ancestors of what it matches', async ({ page }) => {
    await page.goto('/#/organisation-units')

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('Ngelehun')

    // Ngelehun sits three levels down; the districts above it are shown so it is not detached.
    await expect(page.getByRole('button', { name: 'Ngelehun CHC', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Badjia', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toHaveCount(0)

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('OU_BOMBALI')
    await expect(page.getByRole('button', { name: 'Bombali', exact: true })).toBeVisible()

    await page.getByRole('textbox', { name: 'Filter organisation units' }).fill('nothing matches this')
    await expect(page.getByText('No organisation unit matches that filter.')).toBeVisible()
})

test('the rail starts closed on a plain visit, and a selection opens it', async ({ page }) => {
    await page.goto('/#/organisation-units')

    // Nothing is selected, so there is nothing for the rail to answer - it starts as the strip.
    await expect(page.getByRole('button', { name: 'Expand the details panel' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Collapse the details panel' })).toHaveCount(0)

    // Picking in the tree is a question about that organisation unit; the rail opens to answer.
    await page.getByRole('button', { name: 'Adonkia CHP', exact: true }).click()

    await expect(page.getByRole('heading', { name: 'Adonkia CHP', level: 3 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Collapse the details panel' })).toBeVisible()
})

test('selecting a unit fills the inspector, and puts the unit in the address', async ({ page }) => {
    await page.goto('/#/organisation-units')

    // The root arrives expanded, so Bo is one click away.
    await page.getByRole('button', { name: 'Bo', exact: true }).click()

    await expect(page).toHaveURL(/#\/organisation-units\?unit=O6uvpzGd5pu$/)
    await expect(page.getByRole('heading', { name: 'Bo', level: 3 })).toBeVisible()
    // One spelling of the level, the human one - the machine casing stays in the tree's chips.
    await expect(page.getByTestId('org-unit-level')).toContainText('Level 2')
    await expect(page.getByTestId('org-unit-level')).not.toContainText('level-')
    // The DHIS2 uid and the org-unit code, each under the system that says which of the two it is.
    const uid = page.getByText('id/org-unitO6uvpzGd5pu')
    await expect(uid).toBeVisible()
    await expect(page.getByText('id/org-unit-codeOU_BO')).toBeVisible()

    // The subtree sits in the rail's Children section as a mini tree, no clicks between.
    const children = page.getByTestId('org-unit-children')
    await expect(children.getByRole('heading', { name: 'Children' })).toBeVisible()
    await expect(children).toContainText('3 direct')

    // Its rows expand lazily, exactly like the hierarchy pane's.
    await expect(children.getByRole('button', { name: 'Ngelehun CHC', exact: true })).toHaveCount(0)
    await children.getByRole('button', { name: 'Expand Badjia' }).click()
    await expect(children.getByRole('button', { name: 'Ngelehun CHC', exact: true })).toBeVisible()

    // A child row is a selection, same as a tree row - it re-roots the rail.
    await children.getByRole('button', { name: 'Badjia', exact: true }).click()
    await expect(page).toHaveURL(/#\/organisation-units\?unit=YuQRtpLP10I$/)
    await expect(page.getByRole('heading', { name: 'Badjia', level: 3 })).toBeVisible()

    // The rail never scrolls sideways: identifier chips wrap and their values break instead,
    // because one long attribute value must not put everything else behind a horizontal scroll.
    const rail = page.getByRole('complementary', { name: 'Organisation unit details' })
    const railOverflows = await rail.evaluate((element) => element.scrollWidth > element.clientWidth + 1)
    expect(railOverflows, 'the inspector rail scrolls horizontally').toBe(false)
})

test('a unit is a link that opens with its hierarchy already expanded', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=DiszpKrYNg8')

    await expect(page.getByRole('heading', { name: 'Ngelehun CHC', level: 3 })).toBeVisible()
    await expect(page.getByTestId('org-unit-level')).toContainText('Level 4')

    // A deep link arrives selected, so it deserves - and gets - the open rail.
    await expect(page.getByRole('button', { name: 'Collapse the details panel' })).toBeVisible()

    // The parent chain is clickable, and clicking it moves the selection.
    const chain = page.getByRole('navigation', { name: 'Parent organisation units' })
    await expect(chain).toContainText('Sierra Leone')
    await expect(chain).toContainText('Badjia')
    await chain.getByRole('button', { name: 'Badjia' }).click()
    await expect(page).toHaveURL(/#\/organisation-units\?unit=YuQRtpLP10I$/)
})

test('the rail shelves the forms by kind, beside a map that never leaves', async ({ page }) => {
    // Bo is one of the two units the fixture's assignment Lists admit.
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

    // The whole point of the three-pane shape: the forms are readable while the map is on screen.
    await expect(page.getByTestId('org-unit-map')).toBeVisible()

    // Scoped to the shelves: a receipt in Captured here can carry the same form title, and this
    // spec is about the catalog, not the spool.
    const shelves = page.getByTestId('org-unit-forms')

    // Data sets and programs are different capture surfaces, so they are different shelves.
    await expect(shelves.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    // `exact` throughout: beside each row's own link sits the link out to the same object in this
    // DHIS2 instance's Maintenance app, whose accessible name states the form's title too.
    await expect(shelves.getByRole('link', { name: 'Child Health', exact: true })).toBeVisible()
    await expect(shelves.getByRole('heading', { name: 'Programs' })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'Supervision visit', exact: true })).toBeVisible()

    // The two forms whose assignment Lists name Bo carry the badge; everything else is assigned
    // everywhere and appears plainly rather than behind a collapse.
    await expect(shelves.getByRole('link', { name: 'Outbreak response', exact: true })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'Antenatal care', exact: true })).toBeVisible()
    await expect(shelves.getByText('assigned to this organisation unit')).toHaveCount(2)

    // A tracker program is one thing: its stage is grouped under its registration, with the role
    // note saying which row is which.
    await expect(shelves.getByText('registration', { exact: true })).toBeVisible()
    await expect(shelves.getByRole('link', { name: 'ANC follow-up - ANC visit', exact: true })).toBeVisible()
})

test('a unit outside the assignments is offered only the forms assigned everywhere', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=ImspTQPwCqd')

    const shelves = page.getByTestId('org-unit-forms')
    await expect(shelves.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    // The two scoped forms are not reportable here, so they are not listed at all - and with no
    // named assignment reaching this unit, nothing carries the badge.
    await expect(shelves.getByRole('link', { name: 'Outbreak response', exact: true })).toHaveCount(0)
    await expect(shelves.getByRole('link', { name: 'Antenatal care', exact: true })).toHaveCount(0)
    await expect(shelves.getByText('assigned to this organisation unit')).toHaveCount(0)
})

test('a form assigned to one unit opens from that unit', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=DiszpKrYNg8')

    // Scoped to the shelves: earlier files in the run may have spooled Outbreak captures at
    // Ngelehun, and their receipt rows carry the same title.
    await page.getByTestId('org-unit-forms').getByRole('link', { name: 'Outbreak response', exact: true }).click()

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

    await page.goto(`/#/organisation-units?unit=${unitId}`)

    const captured = page.getByTestId('org-unit-captured')
    await expect(captured.getByRole('heading', { name: 'Captured here' })).toBeVisible()
    // The lifecycle chips count what the spool holds at this unit - at least the one just posted.
    await expect(captured.getByText(/\d+ received/)).toBeVisible()
    // The recent list names the form and links to the receipt.
    await expect(captured.getByRole('link', { name: /Child Health/ }).first()).toBeVisible()
    await expect(captured.getByRole('link', { name: 'All responses' })).toBeVisible()
    // The honest scope: this is the server's spool, not the DHIS2 instance's answer.
    await expect(captured.getByText('Captures this server received')).toBeVisible()
})

test('a long form label in the receipts is shown in full, not truncated', async ({ page, request }) => {
    // The longest title the fixture publishes - the one an ellipsis used to cut to the same
    // prefix as every other Child Programme form.
    const longTitle = 'Child Programme - Baby Postnatal'
    const receiptId = await generateAndPost(request, 'ZzYYXq4fJie', 41)
    const listing = await (await request.get('/spool')).json()
    const receipt = listing.responses.find(
        (candidate: { response_id: string }) => candidate.response_id === receiptId,
    )
    expect(receipt, 'the spool listing carries the receipt just posted').toBeTruthy()
    const unitId = receipt.organisation_unit
    expect(unitId, 'the listing states the organisation unit per receipt').toBeTruthy()

    await page.goto(`/#/organisation-units?unit=${unitId}`)

    const label = page.getByTestId('org-unit-captured').getByText(longTitle, { exact: true }).first()
    await expect(label).toBeVisible()
    // Wrapping, not clipping: the label's box holds every character it renders.
    const clipped = await label.evaluate((element) => element.scrollWidth > element.clientWidth + 1)
    expect(clipped, 'the receipt label overflows its box instead of wrapping').toBe(false)
})

test('a unit with no captures says so instead of showing a zero', async ({ page, request }) => {
    // Earlier files in the run spool captures at units of the generator's choosing, so the spec
    // asks the listing which published unit is still bare rather than assuming one. Workers run
    // one at a time, so nothing posts between the read and the assertion. The listing pages, and
    // bareness is a claim about the whole spool, so every page is read before a unit is called bare.
    const used = new Set<string | null | undefined>()
    let spoolUrl: string | null = '/spool?_count=500'
    while (spoolUrl) {
        const listing: {
            responses: { organisation_unit?: string | null }[]
            next_url?: string | null
        } = await (await request.get(spoolUrl)).json()
        for (const candidate of listing.responses) used.add(candidate.organisation_unit)
        spoolUrl = listing.next_url ?? null
    }
    // Every unit the registry publishes is a candidate - see ORG_UNITS in fixture_project.py.
    // The generator spreads its captures over the registry, so with enough earlier posts any
    // shorter list can be fully covered by chance within one run, and a retry re-reads the same
    // spool. When even the full registry is covered, bareness cannot be shown this run - skip
    // with the reason rather than fail on state no assertion here controls.
    const published = [
        'Rp268JB6Ne4',
        'EJoI3HuIUEV',
        'MgFYJDBqSSs',
        'vWbkYPRmKyS',
        'lc3eMKXaEfw',
        'YuQRtpLP10I',
        'DiszpKrYNg8',
        'fdc6uOvgoji',
        'O6uvpzGd5pu',
        'ImspTQPwCqd',
    ]
    const bare = published.find((uid) => !used.has(uid))
    test.skip(!bare, 'every published unit already holds a capture this run')

    await page.goto(`/#/organisation-units?unit=${bare ?? ''}`)

    const captured = page.getByTestId('org-unit-captured')
    await expect(captured.getByText('No received capture names this organisation unit.')).toBeVisible()
    await expect(captured.getByText('Captures this server received')).toBeVisible()
})

test('the rail collapses to a strip, and a selection reopens it', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
    const withRail = (await map.boundingBox())?.width ?? 0

    await page.getByRole('button', { name: 'Collapse the details panel' }).click()

    // Collapsed, the rail's content is gone and the canvas takes the width it held.
    await expect(page.getByRole('heading', { name: 'Bo', level: 3 })).toHaveCount(0)
    await expect.poll(async () => (await map.boundingBox())?.width ?? 0).toBeGreaterThan(withRail + 100)

    // Selecting a unit is a question about it, so the inspector opens to answer - the collapse is
    // a view choice, not a standing instruction. Bo's ancestors are already expanded by the URL
    // selection, so Bombali's row is on screen without another chevron.
    await page.getByRole('button', { name: 'Bombali', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Bombali', level: 3 })).toBeVisible()
})

test('the panes resize by dragging, and the map canvas follows live', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // Two handles: tree | map, and map | rail.
    const handles = page.locator('[data-separator]')
    await expect(handles).toHaveCount(2)

    const rail = page.getByRole('complementary', { name: 'Organisation unit details' })
    const railBefore = (await rail.boundingBox())?.width ?? 0
    const canvasBefore = (await map.locator('canvas').boundingBox())?.width ?? 0
    expect(railBefore).toBeGreaterThan(0)
    expect(canvasBefore).toBeGreaterThan(0)

    // Drag the rail handle 100px left: the rail widens, the canvas narrows.
    const handle = handles.nth(1)
    const box = await handle.boundingBox()
    expect(box).toBeTruthy()
    const grabX = (box?.x ?? 0) + (box?.width ?? 0) / 2
    const grabY = (box?.y ?? 0) + (box?.height ?? 0) / 2
    await page.mouse.move(grabX, grabY)
    await page.mouse.down()
    await page.mouse.move(grabX - 100, grabY, { steps: 8 })
    await page.mouse.up()

    await expect.poll(async () => (await rail.boundingBox())?.width ?? 0).toBeGreaterThan(railBefore + 60)
    // The canvas repainted at the new width - the ResizeObserver followed the drag, live.
    await expect
        .poll(async () => (await map.locator('canvas').boundingBox())?.width ?? 0)
        .toBeLessThan(canvasBefore - 60)
})

test('the centre canvas owns the column height now the sections live in the rail', async ({ page }) => {
    await page.setViewportSize({ width: 1400, height: 900 })
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

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
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

    await expect(page.getByRole('tab', { name: 'Map', selected: true })).toBeVisible()
    await expect(page.getByTestId('org-unit-map')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Data sets' })).toHaveCount(0)

    await page.getByRole('tab', { name: 'Forms' }).click()
    await expect(page.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Outbreak response', exact: true })).toBeVisible()

    await page.getByRole('tab', { name: 'Details' }).click()
    await expect(page.getByTestId('org-unit-children')).toContainText('3 direct')

    // A new selection opens on Map again - the tab is view state, not part of the link. Badjia
    // renders in both the hierarchy pane and the Details tab's children tree; the children tree
    // is the one on screen, so the click is scoped to it.
    await page.getByTestId('org-unit-children').getByRole('button', { name: 'Badjia', exact: true }).click()
    await expect(page).toHaveURL(/#\/organisation-units\?unit=YuQRtpLP10I$/)
    await expect(page.getByRole('tab', { name: 'Map', selected: true })).toBeVisible()
})

test('the map offers a fullscreen control', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

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

    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

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

test('right-clicking a shape on the map drills into the unit it belongs to', async ({ page }) => {
    // The page opens on the root by default, framing the registry - so the centre of the canvas
    // is over a shape, and the deepest boundary there is whichever unit covers that ground.
    await page.goto('/#/organisation-units')

    const map = page.getByTestId('org-unit-map')
    // A click before the layers are on the map lands on an empty scene, so the component states
    // when it has painted them rather than leaving the spec to guess at a delay.
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // Right-click is the drill: it selects whatever shape sits under the pointer - the proof the
    // whole path ran (the read, the decode, the worker, the layer, the hit test). Which unit that
    // is depends on the fit, so the spec asserts a selection happened and the inspector answered,
    // not a particular name.
    await map.locator('canvas').click({ button: 'right' })

    // Asserted through a poll rather than `toHaveURL`: the selection is a `replaceState` made from
    // a canvas event handler, and the URL matcher does not always see one.
    await expect.poll(() => page.url()).toMatch(/#\/organisation-units\?unit=[A-Za-z][A-Za-z0-9]{10}$/)
    await expect(page.getByRole('heading', { level: 3 }).first()).toBeVisible()
})

test('selecting the root frames its extent rather than the world', async ({ page }) => {
    await page.goto('/#/organisation-units?unit=ImspTQPwCqd')

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
    await page.goto('/#/organisation-units?unit=EJoI3HuIUEV')

    await expect(page.getByTestId('org-unit-map')).toBeVisible()
    await expect(page.getByTestId('org-unit-map-note')).toContainText(
        'This DHIS2 instance stores no boundary for Kagbere CHC, so the map frames Bombali',
    )
})

test('a unit with no geometry anywhere near it says so rather than framing on nothing', async ({ page }) => {
    // Adonkia CHP is the orphan: no geometry of its own, no descendants, and its parent is not
    // published at all.
    await page.goto('/#/organisation-units?unit=Rp268JB6Ne4')

    await expect(page.getByTestId('org-unit-map-note')).toContainText(
        'none for any organisation unit above or below it, so the map shows the whole registry instead',
    )
})

test('the served settings offer no tile layer, and the map honours that', async ({ page }) => {
    const settings = await page.request.get('/uiconfig')

    expect(settings.status()).toBe(200)
    // The instance address is deliberately not asserted: whether this machine resolves a profile
    // at all is a property of the machine, and uiconfig.spec.ts states both answers explicitly.
    expect((await settings.json()).basemaps).toEqual([])

    const tileRequests: string[] = []
    page.on('request', (request) => {
        if (/tile|\.png($|\?)/.test(request.url()) && !request.url().includes('/assets/')) {
            tileRequests.push(request.url())
        }
    })

    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')
    await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', {
        timeout: 15_000,
    })

    // No tiles asked for, and the caption says so rather than leaving a reader to wonder.
    expect(tileRequests, tileRequests.join('\n')).toEqual([])
    await expect(page.getByText('no basemap offered, so the map draws from this server alone')).toBeVisible()
    // The layer control is still there, holding the one thing this deployment offers.
    await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-basemap', 'None')
})

test('the theme reaches the renderer, not just the stylesheet', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })
    await expect(map).toHaveAttribute('data-map-theme', 'light')

    // The ground is switched at the gear in the lower left, which is where both appearance
    // controls live - the header carries neither.
    await page.getByRole('complementary').getByRole('button', { name: 'Settings' }).click()
    await page.getByRole('menuitem', { name: /^Switch to dark mode/ }).click()

    // The canvas is painted from resolved token values rather than from CSS, so a theme change has
    // to be pushed into the renderer - and this is the assertion that it was.
    await expect(map).toHaveAttribute('data-map-theme', 'dark')
    await expect(map).toHaveAttribute('data-map-ready', 'true')
    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
})

test('the map takes the height the page has left, and floors rather than collapsing', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1400 })
    await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')

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
        await page.goto('/#/organisation-units?unit=O6uvpzGd5pu')
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

    await page.getByRole('complementary').getByRole('link', { name: 'Organisation units' }).click()

    await expect(page).toHaveURL(/#\/organisation-units$/)
    await expect(page.getByTestId('org-unit-map')).toHaveAttribute('data-map-ready', 'true', {
        timeout: 15_000,
    })
    // The map engine is its own chunk, fetched on arrival here and not with the shell.
    expect(chunks.length).toBeGreaterThan(beforeOpening)
})

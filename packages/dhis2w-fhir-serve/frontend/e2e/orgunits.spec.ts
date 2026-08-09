import { expect, test } from '@playwright/test'

/**
 * The organisation-unit browser, against the registry the fixture project really publishes.
 *
 * Nine Locations over four levels, with every geometry state on them and one form restricted to
 * two of them - see `ORG_UNITS` in packages/dhis2w-fhir-serve/tests/fixture_project.py. The reason
 * that registry exists at all is this page: `partOf` folding, boundary decoding, and the assignment
 * join are three rules whose failure modes are invisible against a registry of nothing.
 *
 * WHAT THE MAP IS ASSERTED ON. Headless chromium here renders WebGL through SwiftShader, so the
 * canvas really is acquired and the assertion is the positive one: the canvas mounts, and the page
 * logs no console error. The component degrades to a stated note rather than a crash when no
 * context can be had, and the note carries its own test id - so an environment without WebGL fails
 * this spec on a missing canvas rather than on a stack trace, which is the failure worth reading.
 */

test('the tree renders the roots and expands on demand', async ({ page }) => {
    await page.goto('/#/org-units')

    await expect(page.getByRole('heading', { name: 'Org units', level: 2 })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sierra Leone', exact: true })).toBeVisible()

    // Adonkia CHP names a parent this project never published, so it is a root of its own.
    await expect(page.getByRole('button', { name: 'Adonkia CHP', exact: true })).toBeVisible()
    await expect(page.getByText('name a parent this project did not publish')).toBeVisible()

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

test('selecting a unit shows its level and identifiers, and puts it in the address', async ({ page }) => {
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
    await expect(page.getByText('3 direct children')).toBeVisible()
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

test('the forms reportable here name the ones assigned to the unit and collapse the rest', async ({
    page,
}) => {
    // Bo is one of the two units the fixture's assignment List admits.
    await page.goto('/#/org-units?unit=O6uvpzGd5pu')

    await expect(page.getByRole('heading', { name: 'Forms reportable here' })).toBeVisible()
    await expect(page.getByText('Assigned to this unit', { exact: false })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Outbreak response' })).toBeVisible()

    // The forms assigned everywhere are a count until asked for, because naming them at every unit
    // would bury the one that is assigned here specifically.
    const collapsed = page.getByRole('button', { name: /5 more assigned everywhere/ })
    await expect(collapsed).toBeVisible()
    await expect(page.getByRole('link', { name: 'Child Health' })).toHaveCount(0)
    await collapsed.click()
    await expect(page.getByRole('link', { name: 'Child Health' })).toBeVisible()
})

test('a unit outside the assignment is offered only the forms assigned everywhere', async ({ page }) => {
    await page.goto('/#/org-units?unit=ImspTQPwCqd')

    await expect(page.getByText('Assigned to this unit')).toHaveCount(0)
    await expect(
        page.getByRole('button', { name: 'All 5 published forms are assigned everywhere' }),
    ).toBeVisible()
})

test('a form assigned to one unit opens from that unit', async ({ page }) => {
    await page.goto('/#/org-units?unit=DiszpKrYNg8')

    await page.getByRole('link', { name: 'Outbreak response' }).click()

    await expect(page).toHaveURL(/#\/forms\/PrScoped001$/)
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

    // Four of the nine units publish a decodable boundary; Baoma's attachment is not GeoJSON and
    // is counted rather than drawn.
    await expect(page.getByText('4 boundaries, 5 points')).toBeVisible()
    await expect(page.getByText('1 published boundary could not be decoded')).toBeVisible()

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

test('a unit with no geometry anywhere above it says so rather than framing on nothing', async ({ page }) => {
    // Adonkia CHP is the orphan: no geometry of its own, and its parent is not published at all.
    await page.goto('/#/org-units?unit=Rp268JB6Ne4')

    await expect(page.getByTestId('org-unit-map-note')).toContainText(
        'none for any unit above it, so the map shows the whole registry instead',
    )
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

import { expect, test } from '@playwright/test'

/**
 * What the terminology pages answer, and what they decline to offer an answer for.
 *
 * The walkthrough beside this file reads the vocabularies; this one is about the question every
 * concept row carries. `$translate` reads the served maps and nothing else, so the button belongs
 * on the rows of a system some map translates from and nowhere else - the fixture publishes both
 * kinds, so both halves of that rule are checked against real generated terminology. The rest is
 * the reader's side of the same question: the answer arriving where the reader is, the same row
 * answering twice, and a filter that admits nothing saying which word emptied the table.
 */

/** The one system the fixture project publishes a ConceptMap for. */
const MAPPED_SYSTEM = '/#/terminology/CodeSystem/d2-os-OsSymptom01-cs'

/** The data dictionary: 70 concepts, and no map naming it as a source. */
const UNMAPPED_SYSTEM = '/#/terminology/CodeSystem/d2-de-cs'

test('a code system no served map translates from offers no lookup at all', async ({ page }) => {
    await page.goto(UNMAPPED_SYSTEM)

    // The concepts are all there - this is a vocabulary, and it reads like one.
    await expect(page.getByRole('row').filter({ hasText: 'DeAncDanger' })).toHaveCount(1)
    // What is not there is a button promising an answer no map can give: every press would come
    // back "no ConceptMap served here maps ...", which is a refusal dressed as an affordance.
    await expect(page.getByRole('button', { name: /^Details for/ })).toHaveCount(0)
    await expect(
        page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' }),
    ).toHaveCount(0)
})

test('a code system a map translates from offers it on every row', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    await expect(
        page.getByRole('button', { name: 'Details for OpFever0001', exact: true }),
    ).toBeVisible()
    // The panel names the instance the maps answer with, not the platform at large.
    await expect(
        page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' }),
    ).toBeVisible()
})

test('the answer arrives where the reader is, not eleven screens below', async ({ page }) => {
    // A window short enough that the panel starts below the fold, which is the ordinary state of
    // a vocabulary page: the concepts come first and there can be thousands of them.
    await page.setViewportSize({ width: 1280, height: 400 })
    await page.goto(MAPPED_SYSTEM)

    const panel = page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' })
    await page.getByRole('button', { name: 'Details for OpFever0001', exact: true }).click()

    await expect(panel).toBeInViewport()
    await expect(page.getByTestId('translate-result')).toContainText('2 mappings')
})

test('asking about the same row twice answers twice', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    const answer = page.getByTestId('translate-result')
    await page.getByRole('button', { name: 'Details for OpFever0001', exact: true }).click()
    await expect(answer).toContainText('2 mappings')

    // The box is typed over and asked about directly, which is what the panel is for.
    await page.getByRole('textbox', { name: 'Concept code' }).fill('NoSuchCode')
    await page.getByRole('button', { name: 'Look up', exact: true }).click()
    await expect(answer).toContainText('No mapping')

    // Pressing the same row again is a real question - the box no longer holds that code - and it
    // is answered, rather than settling on a value the page already held.
    await page.getByRole('button', { name: 'Details for OpFever0001', exact: true }).click()
    await expect(page.getByRole('textbox', { name: 'Concept code' })).toHaveValue('OpFever0001')
    await expect(answer).toContainText('2 mappings')
})

test('the refusal sets the identifiers it quotes in the mono face', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    await page.getByRole('textbox', { name: 'Concept code' }).fill('NoSuchCode')
    await page.getByRole('button', { name: 'Look up', exact: true }).click()

    const answer = page.getByTestId('translate-result')
    await expect(answer).toContainText('no ConceptMap served here maps')
    // The server marks its machine spellings - the code, and the system it was asked about - and a
    // mark is a change of typeface, never a backtick sitting in the middle of a sentence.
    await expect(answer.locator('code').first()).toHaveText('NoSuchCode')
    await expect(answer.locator('code')).toHaveCount(2)
    await expect(answer).not.toContainText('`')
})

test('a filter that admits nothing says which word emptied the table', async ({ page }) => {
    await page.goto('/#/terminology/CodeSystem/d2-de-cs?code=zzzz')
    await expect(page.getByText('Nothing here matches "zzzz".')).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Code', exact: true })).toHaveCount(0)

    await page.goto('/#/terminology/ValueSet/d2-os-OsSymptom01-vs?code=zzzz')
    await expect(page.getByText('Nothing here matches "zzzz".')).toBeVisible()

    await page.goto('/#/terminology/ConceptMap/d2-os-OsSymptom01-cm?code=zzzz')
    // One statement per group, over the two groups the map states.
    await expect(page.getByText('Nothing here matches "zzzz".')).toHaveCount(2)
    // And the group heading counts what it is showing, not what it would show unfiltered.
    await expect(page.getByText('0 mappings')).toHaveCount(2)
})

test('a filtered group counts its own rows, in the singular when there is one', async ({ page }) => {
    await page.goto('/#/terminology/ConceptMap/d2-os-OsSymptom01-cm?code=Fever')

    await expect(page.getByText('1 mapping', { exact: true })).toHaveCount(2)
    await expect(page.getByText('Showing 1 of 1 mapping')).toHaveCount(2)
})

test('a category vocabulary heads its DHIS2 code column by its subject', async ({ page }) => {
    // The system describes that property as "DHIS2 category option code." - a sentence shaped like
    // a category-axis declaration and naming nothing of the kind. The column is the concept's
    // DHIS2 code, and that is what it says.
    await page.goto('/#/terminology/CodeSystem/d2-cat-fMZEcRHuamy-cs')

    await expect(page.getByRole('columnheader', { name: 'DHIS2 code', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'option code', exact: true })).toHaveCount(0)
})

test('a code system states its content and case sensitivity as facts', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    // `complete` and `true` are R4 spellings; what a reader wants is whether the concepts are all
    // here and whether case counts.
    await expect(page.getByText('Every concept is here')).toBeVisible()
    await expect(page.getByText('Case sensitive Yes')).toBeVisible()
})

test('the listing hands its search to the page it opens, and Back gets the search back', async ({
    page,
}) => {
    await page.goto('/#/terminology')

    await page.getByRole('textbox', { name: 'Filter terminology' }).fill('DeAncDanger')
    await expect(page).toHaveURL(/#\/terminology\?q=DeAncDanger$/)

    await page.getByRole('row').filter({ hasText: 'd2-de-cs' }).click()

    // The row reported 1 matching code; the page it opens shows that code rather than making the
    // reader type the word a second time.
    await expect(page).toHaveURL(/#\/terminology\/CodeSystem\/d2-de-cs\?code=DeAncDanger$/)
    await expect(page.getByRole('textbox', { name: 'Filter concepts' })).toHaveValue('DeAncDanger')
    await expect(page.getByText(/Showing 1 of 1 concept$/)).toBeVisible()

    await page.goBack()

    await expect(page.getByRole('textbox', { name: 'Filter terminology' })).toHaveValue('DeAncDanger')
    await expect(page.getByRole('row').filter({ hasText: 'd2-de-cs' })).toHaveCount(1)
})

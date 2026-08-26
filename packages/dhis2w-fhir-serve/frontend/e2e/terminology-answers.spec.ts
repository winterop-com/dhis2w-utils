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
    await expect(page.getByRole('row', { name: /^What a code maps to in this DHIS2 instance:/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Look up a code' })).toHaveCount(0)
    await expect(
        page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' }),
    ).toHaveCount(0)
})

test('a code system a map translates from offers it on every row, and beside the filter', async ({
    page,
}) => {
    await page.goto(MAPPED_SYSTEM)

    await expect(
        page.getByRole('row', { name: 'What a code maps to in this DHIS2 instance: OpFever0001', exact: true }),
    ).toBeVisible()
    // The second way in, for a code somebody has in their head rather than on the screen.
    await expect(page.getByRole('button', { name: 'Look up a code' })).toBeVisible()

    // The question is not on the page until it is asked: the sheet holds it, and the vocabulary
    // under it is the page.
    await expect(
        page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' }),
    ).toHaveCount(0)

    await page.getByRole('button', { name: 'Look up a code' }).click()
    // The sheet names the instance the maps answer with, not the platform at large - and it opens
    // empty, because nothing was asked about.
    await expect(
        page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' }),
    ).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Concept code' })).toHaveValue('')
    await expect(page.getByTestId('translate-result')).toHaveCount(0)
})

test('the answer arrives where the reader is, not eleven screens below', async ({ page }) => {
    // A window short enough that a row well down the vocabulary is what the reader is looking at,
    // which is the ordinary state of a vocabulary page: the concepts come first and there can be
    // thousands of them. The height is the page's 400 plus the 46 the summary bar takes out of the
    // window, which is shell rather than page.
    await page.setViewportSize({ width: 1280, height: 446 })
    await page.goto(MAPPED_SYSTEM)

    const row = page.getByRole('row', { name: 'What a code maps to in this DHIS2 instance: OpFever0001', exact: true })
    await row.scrollIntoViewIfNeeded()
    await row.click()

    // The sheet arrives over the table, at the top of the window, wherever the reader had scrolled
    // to - which is the whole reason it is a sheet rather than a panel eleven screens down.
    const heading = page.getByRole('heading', { name: 'What a code maps to in this DHIS2 instance' })
    await expect(heading).toBeInViewport()
    await expect(page.getByTestId('translate-result')).toContainText('2 mappings')
})

test('asking about the same row twice answers twice', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    const answer = page.getByTestId('translate-result')
    await page.getByRole('row', { name: 'What a code maps to in this DHIS2 instance: OpFever0001', exact: true }).click()
    await expect(answer).toContainText('2 mappings')

    // The box is typed over and asked about directly, which is what the sheet is for.
    await page.getByRole('textbox', { name: 'Concept code' }).fill('NoSuchCode')
    await page.getByRole('button', { name: 'Look up', exact: true }).click()
    await expect(answer).toContainText('No mapping')

    await page.keyboard.press('Escape')
    await expect(page.getByTestId('code-lookup-sheet')).toHaveCount(0)

    // Pressing the same row again is a real question - the box no longer holds that code - and it
    // is answered, rather than settling on a value the page already held.
    await page.getByRole('row', { name: 'What a code maps to in this DHIS2 instance: OpFever0001', exact: true }).click()
    await expect(page.getByRole('textbox', { name: 'Concept code' })).toHaveValue('OpFever0001')
    await expect(answer).toContainText('2 mappings')
})

test('the refusal sets the identifiers it quotes in the mono face', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    await page.getByRole('button', { name: 'Look up a code' }).click()
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
    // And the group heading counts what it is showing, not what it would show unfiltered. Scoped
    // to the page: the summary bar counts the same mappings over the map as a whole.
    await expect(page.getByTestId('page-content').getByText('0 mappings')).toHaveCount(2)
})

test('a filtered group counts its own rows, in the singular when there is one', async ({ page }) => {
    await page.goto('/#/terminology/ConceptMap/d2-os-OsSymptom01-cm?code=Fever')

    // Each group heads itself with what the filter admitted; how much of the map that is over all
    // its groups is the summary bar's line, said once.
    await expect(page.getByText('1 mapping', { exact: true })).toHaveCount(2)
    await expect(page.getByTestId('status-bar-summary')).toContainText('2 mappings in 2 groups')
    await expect(page.getByTestId('page-content').getByText(/^Showing /)).toHaveCount(0)
})

test('a category vocabulary heads its DHIS2 code column by its subject', async ({ page }) => {
    // The system describes that property as "DHIS2 category option code." - a sentence shaped like
    // a category-axis declaration and naming nothing of the kind. The column is the concept's
    // DHIS2 code, and that is what it says.
    await page.goto('/#/terminology/CodeSystem/d2-cat-fMZEcRHuamy-cs')

    await expect(page.getByRole('columnheader', { name: 'DHIS2 code', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'option code', exact: true })).toHaveCount(0)
})

test('a code system states case sensitivity, and says nothing about holding its own concepts', async ({
    page,
}) => {
    await page.goto(MAPPED_SYSTEM)

    // `true` is an R4 spelling; what a reader wants is whether case counts.
    await expect(page.getByText('Case sensitive Yes')).toBeVisible()
    // Every vocabulary this project generates holds its concepts, and a fact printed on every page
    // to say the page holds what it obviously holds is a fact nobody reads. The count goes with it:
    // the summary bar states how many there are and how many are on screen, in one line.
    await expect(page.getByText('Every concept is here')).toHaveCount(0)
    await expect(page.getByTestId('page-content').getByText(/^Concepts \d+$/)).toHaveCount(0)
    await expect(page.getByTestId('status-bar-summary')).toContainText(/of \d+ concepts?$/)
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
    await expect(page.getByTestId('status-bar-summary')).toContainText(/Showing 1 of 1 concept$/)

    await page.goBack()

    await expect(page.getByRole('textbox', { name: 'Filter terminology' })).toHaveValue('DeAncDanger')
    await expect(page.getByRole('row').filter({ hasText: 'd2-de-cs' })).toHaveCount(1)
})

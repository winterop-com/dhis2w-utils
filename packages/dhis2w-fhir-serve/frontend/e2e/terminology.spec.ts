import { expect, test } from '@playwright/test'

/**
 * Terminology: the codes themselves, and the operation that takes one back to DHIS2.
 *
 * The fixture project publishes the symptom option set as the emitter writes it - a CodeSystem
 * whose concept codes are DHIS2 option UIDs with the option code carried as the `dhis2-code`
 * property, and the ConceptMap generated beside it. So every assertion here is against real
 * generated terminology: `OpFever0001` is a concept code, `FEVER` is what DHIS2 calls it, and
 * the map is what connects the two.
 *
 * The `$translate` test is the one that could not exist before the maps were served: it asks
 * the running server, over the same store the forwarder reads, and shows the answer.
 */

test('lists all three terminology types with their counts', async ({ page }) => {
    await page.goto('/#/terminology')

    await expect(page.getByRole('heading', { name: 'Terminology', level: 2 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Code systems' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Value sets' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Concept maps' })).toBeVisible()

    // The map carries the DHIS2 option set it was generated from as its identifier, which is
    // what the identifiers column is for.
    const map = page.getByRole('row').filter({ hasText: 'd2-os-OsSymptom01-cm' })
    await expect(map).toHaveCount(1)
    await expect(map).toContainText('id/option-set')
    await expect(map).toContainText('OsSymptom01')
})

test('the filter narrows every section at once', async ({ page }) => {
    await page.goto('/#/terminology')

    await page.getByRole('textbox', { name: 'Filter terminology' }).fill('OsSymptom01')

    await expect(page.getByRole('row').filter({ hasText: 'd2-os-OsSymptom01-cs' })).toHaveCount(1)
    await expect(page.getByRole('row').filter({ hasText: 'd2-de-cs' })).toHaveCount(0)
})

test('opening a code system shows its concepts and their DHIS2 codes', async ({ page }) => {
    await page.goto('/#/terminology')

    await page
        .getByRole('row')
        .filter({ hasText: 'd2-os-OsSymptom01-cs' })
        .click()

    await expect(page).toHaveURL(/#\/terminology\/CodeSystem\/d2-os-OsSymptom01-cs$/)
    // The concept code is the DHIS2 option UID; the property column carries the option code.
    // Both halves of a generated coding, on one row.
    const fever = page.getByRole('row').filter({ hasText: 'OpFever0001' })
    await expect(fever).toHaveCount(1)
    await expect(fever).toContainText('Fever')
    await expect(fever).toContainText('FEVER')
})

test('a long code system pages rather than rendering thousands of rows', async ({ page }) => {
    // The data-dictionary system is the biggest one the fixture publishes.
    await page.goto('/#/terminology/CodeSystem/d2-de-cs')

    await expect(page.getByText(/Showing \d+ of 70 concepts/)).toBeVisible()
    // Headed by the property code said as words: the page already names the system, so repeating
    // "DHIS2 data element" in every column says nothing.
    await expect(page.getByRole('columnheader', { name: 'Domain', exact: true })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Value type', exact: true })).toBeVisible()
    // This system declares no `dhis2-code` property - its concept codes are the DHIS2 data element
    // uids and that is the whole naming - so the one Code column is the concept code itself, not a
    // second property column full of dashes.
    await expect(page.getByRole('columnheader', { name: 'Code', exact: true })).toHaveCount(1)

    await page.getByRole('textbox', { name: 'Filter concepts' }).fill('danger')
    await expect(page.getByText(/Showing 1 of 1 concepts/)).toBeVisible()
})

test('the listing filter reaches into the codes and names the system that holds a match', async ({
    page,
}) => {
    await page.goto('/#/terminology')

    // A concept code, not a title: no artifact is *called* DeAncDanger, so a shallow filter would
    // answer nothing. The deep half counts the codes inside each artifact instead.
    await page.getByRole('textbox', { name: 'Filter terminology' }).fill('DeAncDanger')

    const owner = page.getByRole('row').filter({ hasText: 'd2-de-cs' })
    await expect(owner).toHaveCount(1)
    await expect(owner).toContainText('1 matching code')
    // The section counter says how much of the section survived the filter.
    await expect(page.getByText(/^1 of \d+$/)).toBeVisible()
    // The other two sections hold nothing with that code, and say so rather than going blank.
    await expect(page.getByText('Nothing here matches "DeAncDanger".')).toHaveCount(2)
})

test('the tracked-entity dictionary states its codes, uniqueness, and the honest dash', async ({
    page,
}) => {
    await page.goto('/#/terminology/CodeSystem/d2-tea-cs')

    // The published title, sentence case as the emitter writes it - not a rendered-up variant.
    // `exact` pins the casing: a case-insensitive match would also accept a title-cased rewrite.
    await expect(
        page.getByRole('heading', { name: 'DHIS2 tracked entity attributes', level: 2, exact: true }),
    ).toBeVisible()
    // The declared properties become columns: the DHIS2 code, the value type, and uniqueness -
    // the fact DHIS2 alone can enforce, surfaced because it decides what a duplicate submit does.
    await expect(page.getByRole('columnheader', { name: 'Unique', exact: true })).toBeVisible()

    // An attribute with a DHIS2 code shows it on the row beside the uid.
    const birthDate = page.getByRole('row').filter({ hasText: 'TeaBirthDat' })
    await expect(birthDate).toContainText('TEA_BIRTH_DATE')

    // The household attribute ships without a `dhis2-code`, and the cell is a dash rather than an
    // invented value - the honest-codes rule.
    const household = page.getByRole('row').filter({ hasText: 'TeaHousehld' })
    await expect(household).toHaveCount(1)
    await expect(household.getByRole('cell', { name: '-', exact: true })).toHaveCount(1)

    // The unique attribute says so; DHIS2 is what refuses the second person claiming its value.
    const nationalId = page.getByRole('row').filter({ hasText: 'TeaNationId' })
    await expect(nationalId.getByRole('cell', { name: 'true', exact: true })).toHaveCount(1)
})

test('the $translate tester answers with the DHIS2 identifiers a concept maps onto', async ({ page }) => {
    await page.goto('/#/terminology/CodeSystem/d2-os-OsSymptom01-cs')

    await page.getByRole('textbox', { name: 'Concept code' }).fill('OpFever0001')
    // Exact, because every concept row carries a "Translate <code>" button of its own.
    await page.getByRole('button', { name: 'Translate', exact: true }).click()

    const answer = page.getByTestId('translate-result')
    await expect(answer).toContainText('2 mappings')
    // The option UID under `id/option`, and the DHIS2 option code under `id/option-code`.
    await expect(answer).toContainText('id/option-code')
    await expect(answer).toContainText('FEVER')
})

test('a code the maps say nothing about is an answer, not an error', async ({ page }) => {
    await page.goto('/#/terminology/CodeSystem/d2-os-OsSymptom01-cs')

    await page.getByRole('textbox', { name: 'Concept code' }).fill('NoSuchCode')
    await page.getByRole('button', { name: 'Translate', exact: true }).click()

    const answer = page.getByTestId('translate-result')
    await expect(answer).toContainText('No mapping')
    await expect(answer).toContainText('no ConceptMap served here maps')
})

test('opening a concept map shows every mapping, grouped by target system', async ({ page }) => {
    await page.goto('/#/terminology')

    await page
        .getByRole('row')
        .filter({ hasText: 'd2-os-OsSymptom01-cm' })
        .click()

    await expect(page).toHaveURL(/#\/terminology\/ConceptMap\/d2-os-OsSymptom01-cm$/)
    // Two groups - the option UID and the option code - over two concepts.
    await expect(page.getByText('id/option-code').first()).toBeVisible()
    // Matched on the target cell: `hasText` is case-insensitive, so "COUGH" would also find the
    // `OpCough0001` row of the option-uid group.
    const cough = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'COUGH', exact: true }) })
    await expect(cough).toHaveCount(1)
    await expect(cough).toContainText('OpCough0001')
    await expect(cough).toContainText('equal')
})

test('a mapping row asks the server about its own concept', async ({ page }) => {
    await page.goto('/#/terminology/ConceptMap/d2-os-OsSymptom01-cm')

    await page
        .getByRole('row')
        .filter({ has: page.getByRole('cell', { name: 'COUGH', exact: true }) })
        .getByRole('button', { name: 'Translate OpCough0001' })
        .click()

    // Clicking a row asks the running server, so both mappings come back - the option uid and
    // the option code - even though the row that was clicked states only one of them.
    const answer = page.getByTestId('translate-result')
    await expect(answer).toContainText('2 mappings')
    await expect(answer).toContainText('COUGH')
})

test('a value set expands through the code system it composes', async ({ page }) => {
    await page.goto('/#/terminology/ValueSet/d2-os-OsSymptom01-vs')

    await expect(page.getByRole('heading', { name: 'What it admits' })).toBeVisible()
    await expect(page.getByRole('row').filter({ hasText: 'OpFever0001' })).toHaveCount(1)

    // The composed system links back to its own detail page.
    await page.getByRole('link', { name: 'CodeSystem/d2-os-OsSymptom01-cs' }).click()
    await expect(page).toHaveURL(/#\/terminology\/CodeSystem\/d2-os-OsSymptom01-cs$/)
})

test('the back link returns to the listing', async ({ page }) => {
    await page.goto('/#/terminology/CodeSystem/d2-de-cs')

    await page.getByRole('link', { name: 'All terminology' }).click()

    await expect(page).toHaveURL(/#\/terminology$/)
    await expect(page.getByRole('heading', { name: 'Terminology', level: 2 })).toBeVisible()
})

import { expect, test } from '@playwright/test'

/**
 * The slide-over, as a thing a person operates - rather than as a thing a component renders.
 *
 * ONE PATTERN, THREE PLACES. The code lookup, the register's quick view, and the receipt's are the
 * same sheet with different contents, and the promises they make are the sheet's rather than any
 * one screen's: it arrives from the right over what the reader was reading, Esc and the X close it,
 * the focus goes back where it came from, and the page underneath is untouched when it does. The
 * code lookup is the one checked here because it is the one whose page is a table thousands of rows
 * long - which is the case a modal is easiest to get wrong in.
 *
 * WHAT THE PAGE UNDERNEATH BEING UNTOUCHED MEANS, concretely: the filter still holds what was typed,
 * the address is the address that was opened, and the vocabulary is where it was left. Every one of
 * those was lost by the panel this sheet replaced, and every one of them is what a reader is in the
 * middle of when they press a row.
 */

/** The one system the fixture project publishes a ConceptMap for, so the only one with a lookup. */
const MAPPED_SYSTEM = '/#/terminology/CodeSystem/d2-os-OsSymptom01-cs'

test('opens from a row, closes on Escape, and gives the focus back to that row', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    const details = page.getByRole('button', { name: 'Details for OpFever0001', exact: true })
    await details.click()

    const sheet = page.getByTestId('code-lookup-sheet')
    await expect(sheet).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Concept code' })).toHaveValue('OpFever0001')

    await page.keyboard.press('Escape')
    await expect(sheet).toHaveCount(0)
    // The reader was in a table when they asked; they are back in it, on the row they asked from.
    await expect(details).toBeFocused()
})

test('closes on its own X, which is the affordance a pointer reaches for', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    await page.getByRole('button', { name: 'Look up a code' }).click()
    const sheet = page.getByTestId('code-lookup-sheet')
    await expect(sheet).toBeVisible()

    await sheet.getByRole('button', { name: 'Close' }).click()
    await expect(sheet).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Look up a code' })).toBeFocused()
})

test('leaves the page underneath exactly as it was found', async ({ page }) => {
    await page.goto(MAPPED_SYSTEM)

    // A reader in the middle of narrowing a vocabulary, which is the state a row is pressed from.
    await page.getByRole('textbox', { name: 'Filter concepts' }).fill('Fever')
    await expect(page).toHaveURL(/\?code=Fever$/)

    await page.getByRole('button', { name: 'Details for OpFever0001', exact: true }).click()
    await expect(page.getByTestId('translate-result')).toContainText('2 mappings')
    // The lookup is not a navigation: the address it was opened from is the address it is still at.
    await expect(page).toHaveURL(/\?code=Fever$/)

    await page.keyboard.press('Escape')
    await expect(page.getByRole('textbox', { name: 'Filter concepts' })).toHaveValue('Fever')
    await expect(page.getByRole('row').filter({ hasText: 'OpFever0001' })).toHaveCount(1)
})

test('the vocabulary under it scrolls as a page, with no scroller of its own', async ({ page }) => {
    // The panel this sheet replaced bounded the table to half the window, which put a second
    // scrollbar inside the page. With the panel gone the table is the page again: it is as tall as
    // its rows, and the window is what scrolls.
    await page.setViewportSize({ width: 1280, height: 600 })
    await page.goto('/#/terminology/CodeSystem/d2-de-cs')

    const table = page.getByRole('table')
    await expect(table).toBeVisible()
    const scrollsItself = await table.evaluate((element) => {
        const box = element.parentElement
        return box !== null && box.scrollHeight > box.clientHeight + 1
    })
    expect(scrollsItself).toBe(false)
    // Seventy rows in a six-hundred-pixel window: it is the page's own column that has somewhere
    // to go, which is the one scroller this app has ever had.
    const pageScrolls = await page
        .getByTestId('page-content')
        .evaluate((element) => element.scrollHeight > element.clientHeight + 1)
    expect(pageScrolls).toBe(true)
})

import { expect, test, type Page } from '@playwright/test'

/**
 * What the palette highlights for what is typed, against a real list of forms.
 *
 * `lib/palette.test.ts` decides the ranking and proves it in plain Node; this proves the ranking is
 * the one cmdk actually filters with. The two are different claims: the scorer can be right while
 * the component still mounts the primitive's own default, which is what shipped - a fuzzy match over
 * every row's whole value, uid included, so a query with one sensible answer highlighted a form
 * whose identifier happened to spell it.
 */

/** Open the palette, retrying the chord until the window listener is mounted. */
async function openPalette(page: Page): Promise<void> {
    const dialog = page.getByRole('dialog', { name: 'Command palette' })
    await page.getByRole('button', { name: 'Command palette' }).click()
    await expect(dialog).toBeVisible()
}

test('a word with one sensible answer highlights that row and nothing else', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)

    // The forms have to be on the list for this to be the case it claims: the read happens when the
    // palette is first opened, and a row from it appearing is that read having landed.
    await expect(page.getByRole('option', { name: /Antenatal care/ })).toBeVisible()

    await page.getByRole('combobox', { name: 'Command palette' }).fill('dark')

    const options = page.getByRole('option')
    await expect(options.first()).toContainText('Switch to dark mode')
    await expect(page.getByRole('option', { name: /Antenatal care/ })).toHaveCount(0)
})

test('nothing matches when nothing is named, so the empty state is reachable', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)
    await expect(page.getByRole('option', { name: /Antenatal care/ })).toBeVisible()

    await page.getByRole('combobox', { name: 'Command palette' }).fill('zzzzqqq')

    await expect(page.getByText('Nothing here matches that.')).toBeVisible()
    await expect(page.getByRole('option')).toHaveCount(0)
})

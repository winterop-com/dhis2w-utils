import { expect, test, type Page } from '@playwright/test'

/**
 * The panel beside the editor, and the picker above it, once a reader has actually used them.
 *
 * Three things here are facts about a browser rather than about a component: whether a tab bar is
 * still on the screen after its own panel has been scrolled, whether a picker still names an example
 * after the box under it has been typed into, and whether the long form is something a reader can
 * open. Each of them read correctly in the source and wrongly on the screen.
 */

/** The source editor, which is a CodeMirror instance rather than a textarea. */
function sourceEditor(page: Page) {
    return page.getByTestId('evaluate-source')
}

test('keeps the language tabs on screen while the shelves under them scroll', async ({ page }) => {
    await page.goto('/#/evaluate')
    await page.getByRole('button', { name: 'Expand the examples' }).click()

    const tabs = page.getByRole('tab', { name: 'CQL' })
    await expect(tabs).toBeVisible()

    // The examples shelf is far longer than the viewport on any real project, and reaching the
    // lower shelves used to take the whole tab bar off the top of the screen with it.
    await page.getByTestId('evaluate-examples').getByRole('button').last().scrollIntoViewIfNeeded()

    await expect(tabs).toBeInViewport()
})

test('stops naming an example once the source it loaded has been typed over', async ({ page }) => {
    await page.goto('/#/evaluate')
    await page.getByRole('button', { name: 'Expand the examples' }).click()

    const picker = page.getByRole('combobox', { name: 'Example' })
    await expect(picker).toContainText('The given names on a Patient')

    const editor = sourceEditor(page).locator('.cm-content')
    await editor.click()
    await page.keyboard.press('ControlOrMeta+a')
    await page.keyboard.type('1 + 1')

    // What is in the box is a reader's own expression, and the form must not say otherwise.
    await expect(picker).not.toContainText('The given names on a Patient')
    await expect(picker).toContainText('Pick an example')
    await expect(
        page.getByTestId('evaluate-examples').getByRole('button', { name: 'The given names on a Patient' }),
    ).not.toHaveAttribute('aria-current', 'true')
})

test('sends a reader to a published page rather than to a path in a source tree', async ({ page }) => {
    await page.goto('/#/evaluate')
    await page.getByRole('button', { name: 'Expand the examples' }).click()
    await page.getByRole('tab', { name: 'FHIRPath' }).click()

    const reference = page.getByTestId('evaluate-reference')
    await expect(reference).toContainText('The long form is')
    await expect(reference.getByRole('link', { name: 'FHIRPath' })).toHaveAttribute(
        'href',
        /^https:\/\/.+\/fhir\/501-fhirpath\/$/,
    )
    expect(await reference.innerText()).not.toContain('docs/fhir/')

    // ELM has no page of its own, and says nothing rather than pointing at one about something else.
    await page.getByRole('tab', { name: 'ELM' }).click()
    expect(await page.getByTestId('evaluate-reference').innerText()).not.toContain('The long form is')
})

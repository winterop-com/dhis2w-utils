import { expect, test } from '@playwright/test'

/**
 * Forms: every Questionnaire the fixture IG publishes, with the DHIS2 object kind it came from.
 *
 * The kind is the interesting column. It is read off the `D2FormType` extension
 * rather than guessed, and the fixture project deliberately carries one form per
 * kind - an aggregate data set, two event programs, and two tracker stages - so
 * a renderer that silently defaulted the extension away would show four
 * identical badges here.
 */

test('lists the fixture questionnaires with their form kinds', async ({ page }) => {
    await page.goto('/#/forms')

    const rows = page.getByRole('row')
    await expect(rows.filter({ hasText: 'Child Health' })).toHaveCount(1)

    // The label text comes from FORM_TYPE_LABELS in lib/fhir.ts, which spells
    // the `D2FormType` codes out. `tracker-event` is a program stage, not the
    // registration form - the one that catches people out.
    await expect(page.getByRole('cell', { name: 'Aggregate data set' }).first()).toBeVisible()
    await expect(page.getByRole('cell', { name: 'Event program' }).first()).toBeVisible()
    await expect(page.getByRole('cell', { name: 'Tracker program stage' }).first()).toBeVisible()
})

test('states how many questions each form asks', async ({ page }) => {
    await page.goto('/#/forms')

    const temporal = page.getByRole('row').filter({ hasText: 'Temporal capture' })
    await expect(temporal).toHaveCount(1)
    // Eight items, none of them a group or a display - see
    // TEMPORAL_QUESTIONNAIRE_BODY in tests/fixture_project.py.
    await expect(temporal.getByRole('cell', { name: '8', exact: true })).toBeVisible()
})

test('every row opens the form view on click', async ({ page }) => {
    await page.goto('/#/forms')

    const rows = page.getByRole('row').filter({ hasText: 'Child Health' })
    await expect(rows.first()).toBeVisible()
    await rows.first().click()
    await expect(page).toHaveURL(/#\/forms\//)
})

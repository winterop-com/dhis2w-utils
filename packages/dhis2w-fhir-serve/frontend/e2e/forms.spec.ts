import { expect, test } from '@playwright/test'

/**
 * Forms: the served Questionnaires grouped by the DHIS2 capture model each came from.
 *
 * The grouping is the interesting shape. The fixture project deliberately carries all three
 * models - two data sets, three event programs, and two tracker programs, one with a published
 * registration (`PrAncCare01`) and one whose stage is served alone (`IpHINAT79UW`) - so a page
 * that flattened them back into one table, or that guessed a registration where none is served,
 * fails here.
 */

test('the three capture models are sections, each saying what it is', async ({ page }) => {
    await page.goto('/#/forms')

    await expect(page.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Event programs' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Tracker programs' })).toBeVisible()

    // The explainers state the model's nature, which is what the kind badges used to gesture at.
    await expect(page.getByText('Periodic reports for an organisation unit. No person involved.')).toBeVisible()
    await expect(page.getByText('Single events, recorded without registering a person.')).toBeVisible()

    // Each form sits in its own model's section and nowhere else.
    const dataSets = page.getByTestId('forms-data-sets')
    await expect(dataSets.getByRole('row').filter({ hasText: 'Child Health' })).toHaveCount(1)
    await expect(dataSets.getByRole('row').filter({ hasText: 'EPI Stock' })).toHaveCount(1)

    const eventPrograms = page.getByTestId('forms-event-programs')
    await expect(eventPrograms.getByRole('row').filter({ hasText: 'Outbreak response' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('row').filter({ hasText: 'Supervision visit' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('row').filter({ hasText: 'Temporal capture' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('row').filter({ hasText: 'Child Health' })).toHaveCount(0)

    // The section states the kind once, so the old per-row badges are gone with the Kind column.
    await expect(page.getByText('Aggregate data set', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Event program', { exact: true })).toHaveCount(0)
})

test('a tracker program leads with its registration, stages beneath, dependency stated', async ({ page }) => {
    await page.goto('/#/forms')

    const ancCare = page.getByTestId('forms-tracker-program').filter({ hasText: 'Antenatal care' })
    await expect(ancCare.getByRole('heading', { name: 'Antenatal care' })).toBeVisible()

    // Row 0 is the table header; the registration row comes before the stage rows even though
    // its title sorts after the stage's - the order is the dependency, not the alphabet.
    const rows = ancCare.getByRole('row')
    await expect(rows.nth(1)).toContainText('Antenatal care')
    await expect(rows.nth(1)).toContainText('registration - enrols a person')
    await expect(rows.nth(2)).toContainText('ANC follow-up - ANC visit')
    await expect(rows.nth(2)).toContainText('stage - a visit for an enrolled person')

    await expect(ancCare.getByText('Stages record visits for a person the registration enrols.')).toBeVisible()
})

test('a program whose registration is not served says so instead of guessing one', async ({ page }) => {
    await page.goto('/#/forms')

    const childProgramme = page.getByTestId('forms-tracker-program').filter({ hasText: 'Baby Postnatal' })
    await expect(childProgramme.getByText('No registration form is published for this program.')).toBeVisible()
    await expect(childProgramme.getByText('registration - enrols a person')).toHaveCount(0)
    await expect(
        childProgramme.getByRole('row').filter({ hasText: 'Child Programme - Baby Postnatal' }),
    ).toContainText('stage - a visit for an enrolled person')
})

test('rows keep their question counts and ids', async ({ page }) => {
    await page.goto('/#/forms')

    const temporal = page.getByRole('row').filter({ hasText: 'Temporal capture' })
    await expect(temporal).toHaveCount(1)
    // Eight items, none of them a group or a display - see
    // TEMPORAL_QUESTIONNAIRE_BODY in tests/fixture_project.py.
    await expect(temporal.getByRole('cell', { name: '8', exact: true })).toBeVisible()
    await expect(temporal.getByRole('cell', { name: 'PrTemporal1' })).toBeVisible()
})

test('a row opens the form view on click, a stage row included', async ({ page }) => {
    await page.goto('/#/forms')

    await page.getByRole('row').filter({ hasText: 'Child Health' }).first().click()
    await expect(page).toHaveURL(/#\/forms\/BfMAe6Itzgt$/)

    await page.goto('/#/forms')
    await page.getByRole('row').filter({ hasText: 'ANC follow-up - ANC visit' }).first().click()
    await expect(page).toHaveURL(/#\/forms\/PsAncVisit1$/)
})

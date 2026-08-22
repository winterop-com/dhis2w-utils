import { expect, test } from '@playwright/test'

/**
 * Forms: the served Questionnaires grouped by the DHIS2 capture model each came from.
 *
 * The grouping is the interesting shape. The fixture project deliberately carries all four
 * models - two data sets, three event programs, two tracker programs (one with a published
 * registration, `PrAncCare01`, and one whose stage is served alone, `IpHINAT79UW`), and the
 * person-only form of the tracked entity type the first of those registers into - so a page that
 * flattened them back into one table, that guessed a registration where none is served, or that
 * filed a form enrolling nobody under a programme, fails here.
 *
 * EVERY FORM ON THIS PAGE IS A LINK, WHICH IS WHAT THE CASES SELECT ON. The listing is cards and
 * rows rather than tables now, and each of them navigates as a whole - so `getByRole('link')` is
 * both how a case finds a form and, incidentally, the assertion that the form can be opened at all.
 */

test('the four capture models are sections, each saying what it is', async ({ page }) => {
    await page.goto('/#/forms')

    await expect(page.getByRole('heading', { name: 'Data sets' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Event programs' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Tracker programs' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'People' })).toBeVisible()

    // The explainers state the model's nature, which the per-card badge cannot: what the badge
    // says is which of the five kinds this one form is.
    await expect(page.getByText('Periodic reports for an organisation unit. No person involved.')).toBeVisible()
    await expect(page.getByText('Single events, recorded without registering a person.')).toBeVisible()
    await expect(
        page.getByText('Registers a person in this DHIS2 instance without enrolling them in a program.'),
    ).toBeVisible()

    // Each form sits in its own model's section and nowhere else.
    const dataSets = page.getByTestId('forms-data-sets')
    await expect(dataSets.getByRole('link').filter({ hasText: 'Child Health' })).toHaveCount(1)
    await expect(dataSets.getByRole('link').filter({ hasText: 'EPI Stock' })).toHaveCount(1)

    const eventPrograms = page.getByTestId('forms-event-programs')
    await expect(eventPrograms.getByRole('link').filter({ hasText: 'Outbreak response' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('link').filter({ hasText: 'Supervision visit' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('link').filter({ hasText: 'Temporal capture' })).toHaveCount(1)
    await expect(eventPrograms.getByRole('link').filter({ hasText: 'Child Health' })).toHaveCount(0)

    // The person-only form is on its own shelf and in no programme's group: it names no
    // programme at all, so a fold that grouped it would have invented one out of its own id.
    // Matched on the uid rather than on the title, because "Person" is a substring of prose the
    // tracker section carries and the claim here is about where this one form sits.
    const people = page.getByTestId('forms-people')
    await expect(people.getByRole('link').filter({ hasText: 'TetPerson01' })).toHaveCount(1)
    await expect(
        page.getByTestId('forms-tracker-programs').getByRole('link').filter({ hasText: 'TetPerson01' }),
    ).toHaveCount(0)
})

test('each card wears the kind of the form it opens', async ({ page }) => {
    await page.goto('/#/forms')

    // The badge is the form's own fact rather than the shelf's, so it is on the card even where the
    // section heading has already said it - a card read anywhere else still says what it is.
    const childHealth = page.getByRole('link').filter({ hasText: 'Child Health' }).first()
    await expect(childHealth.getByText('Aggregate data set')).toBeVisible()

    const outbreak = page.getByRole('link').filter({ hasText: 'Outbreak response' }).first()
    await expect(outbreak.getByText('Event program')).toBeVisible()

    const person = page.getByTestId('forms-people').getByRole('link').first()
    await expect(person.getByText('Registration', { exact: true })).toBeVisible()
})

test('a tracker program leads with its registration, stages beneath, dependency stated', async ({ page }) => {
    await page.goto('/#/forms')

    const ancCare = page.getByTestId('forms-tracker-program').filter({ hasText: 'Antenatal care' })
    await expect(ancCare.getByRole('heading', { name: 'Antenatal care' })).toBeVisible()

    // The registration row comes before the stage rows even though its title sorts after the
    // stage's - the order is the dependency, not the alphabet.
    const rows = ancCare.getByRole('link')
    await expect(rows.nth(0)).toContainText('Antenatal care')
    await expect(rows.nth(0)).toContainText('Tracker registration')
    await expect(rows.nth(1)).toContainText('ANC follow-up - ANC visit')
    await expect(rows.nth(1)).toContainText('Tracker program stage')
    // The stage says how often it is answered, which is what the form declares on `d2-repeatable`
    // and the one fact its badge does not carry.
    await expect(rows.nth(1)).toContainText('each visit is its own record')

    // Said once, by the section, rather than once per program.
    await expect(
        page.getByText(
            "A person is enrolled once by the registration form, then each stage beneath it records one of that person's visits.",
        ),
    ).toBeVisible()
})

test('a program whose registration is not served says so instead of guessing one', async ({ page }) => {
    await page.goto('/#/forms')

    const childProgramme = page.getByTestId('forms-tracker-program').filter({ hasText: 'Baby Postnatal' })
    await expect(childProgramme.getByText('No registration form is published for this program.')).toBeVisible()
    await expect(childProgramme.getByText('Tracker registration')).toHaveCount(0)
    await expect(
        childProgramme.getByRole('link').filter({ hasText: 'Child Programme - Baby Postnatal' }),
    ).toContainText('one record per enrollment')
})

test('cards keep their question counts and ids', async ({ page }) => {
    await page.goto('/#/forms')

    const temporal = page.getByRole('link').filter({ hasText: 'Temporal capture' })
    await expect(temporal).toHaveCount(1)
    // Eight items, none of them a group or a display - see
    // TEMPORAL_QUESTIONNAIRE_BODY in tests/fixture_project.py.
    await expect(temporal).toContainText('8 questions')
    await expect(temporal).toContainText('PrTemporal1')
})

test('a card opens the form view on click, a stage row included', async ({ page }) => {
    await page.goto('/#/forms')

    await page.getByRole('link').filter({ hasText: 'Child Health' }).first().click()
    await expect(page).toHaveURL(/#\/forms\/BfMAe6Itzgt$/)

    await page.goto('/#/forms')
    await page.getByRole('link').filter({ hasText: 'ANC follow-up - ANC visit' }).first().click()
    await expect(page).toHaveURL(/#\/forms\/PsAncVisit1$/)
})

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

/**
 * The capture context a person states for themselves, driven the way they state it.
 *
 * WHAT IS UNDER TEST. `$generate` draws a whole postable context - when the event happened, when
 * the enrollment begins, which period the data set reports for, which organisation unit it is
 * reported from - and every one of those is a fact the person filling the form knows better than
 * the draw does. So each is a control, opening on the drafted value, and an edit has to ride the
 * envelope in the slot the draft put it in. The receipt is where that is provable: these specs edit
 * a control, submit, and read the stored QuestionnaireResponse back off the server.
 *
 * WHY THE STORED RESOURCE AND NOT THE PAGE. A receipt page renders what it reads, and what the
 * forwarder posts to DHIS2 is the document. `authored` is the only place an event's occurrence date
 * lives - `TrackerEvent.occurredAt` is derived from it - and the period's date range is a
 * sub-extension no screen shows. Both are only checkable against the bytes.
 */

const FHIR_JSON = 'application/fhir+json'

/** The event form of the goldens, whose skeleton dates itself and whose questions are all optional. */
const EVENT_FORM = 'EVTsupVis01'

/** The aggregate form of the goldens, whose data set reports monthly. */
const AGGREGATE_FORM = 'BfMAe6Itzgt'

/** The event form restricted to two organisation units, and the one restricted to none. */
const SCOPED_FORM = 'PrScoped001'
const UNSCOPED_FORM = 'PrTemporal1'

/** A unit the unrestricted form admits and the scoped form's assignment does not. */
const OUTSIDE_UNIT = 'Bombali'

/** A unit both of them admit, so a kept one can be adopted rather than only refused. */
const SHARED_UNIT = 'Bo'

/** The kind's code in the D2FormType terminology - `tracker` is the registration form. */
const REGISTRATION_FORM_TYPE = 'tracker'

/**
 * The id of the registration form this project publishes, or null when it publishes none.
 *
 * Discovered rather than named, exactly as the capture walkthrough discovers it: the spec is about
 * the kind rather than about one fixture's choice of uid.
 */
async function registrationFormId(request: APIRequestContext): Promise<string | null> {
    const bundle = await request.get('/Questionnaire', { headers: { Accept: FHIR_JSON } })
    expect(bundle.status(), await bundle.text()).toBe(200)
    const body = (await bundle.json()) as {
        entry?: { resource?: { id?: string; extension?: { url: string; valueCode?: string }[] } }[]
    }
    for (const entry of body.entry ?? []) {
        const resource = entry.resource
        if (resource?.id === undefined) continue
        const declared = resource.extension?.find((candidate) =>
            candidate.url.endsWith('/StructureDefinition/d2-form-type'),
        )
        if (declared?.valueCode !== REGISTRATION_FORM_TYPE) continue
        return resource.id
    }
    return null
}

/** Open one form and wait for the skeleton, which is what puts the drafted values in the controls. */
async function openForm(page: Page, questionnaireId: string): Promise<void> {
    const opened = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${questionnaireId}`)
    await opened
}

/** Submit the form on screen, answering with the receipt id the server minted for it. */
async function submitCapture(page: Page): Promise<string> {
    // The create interaction states where the receipt is served from in its Location header, which
    // is the id without a listing to read it off - and it is what proves the post was a 201.
    const posted = page.waitForResponse(
        (response) => response.request().method() === 'POST' && response.url().endsWith('/QuestionnaireResponse'),
    )
    await page.getByRole('button', { name: 'Submit' }).click()
    const response = await posted
    expect(response.status(), await response.text()).toBe(201)
    await expect(page.getByText('The server accepted this submission')).toBeVisible()
    return (response.headers()['location'] ?? '').split('/').pop() ?? ''
}

/** The parts of a stored receipt these specs read: the two places an edited date or period lands. */
interface StoredResponse {
    authored?: string
    extension?: {
        url: string
        valueDateTime?: string
        extension?: { url: string; valueString?: string; valueCode?: string }[]
    }[]
}

/** One stored receipt, as the document the forwarder will read. */
async function storedResponse(request: APIRequestContext, receiptId: string): Promise<StoredResponse> {
    const stored = await request.get(`/QuestionnaireResponse/${receiptId}`, { headers: { Accept: FHIR_JSON } })
    expect(stored.status(), await stored.text()).toBe(200)
    return (await stored.json()) as StoredResponse
}

test('an edited visit date is the date the stored event carries', async ({ page, request }) => {
    await openForm(page, EVENT_FORM)

    // The draft dates the submission, so the control arrives answered - editing it is a correction
    // rather than an entry, which is what makes a capture of last Tuesday's visit possible at all.
    const visitDate = page.getByLabel('Visit date')
    await expect(visitDate).toBeVisible()
    await expect(visitDate).not.toHaveValue('')

    await visitDate.fill('2026-07-02T09:15')
    const receiptId = await submitCapture(page)

    // The wall time as stated, stamped `Z` rather than shifted by the browser's zone: the same
    // keystrokes have to mean the same instant in every office.
    const stored = await storedResponse(request, receiptId)
    expect(stored.authored).toBe('2026-07-02T09:15:00Z')
})

test('an edited reporting period is captured as the identifier, with no range claimed for it', async ({
    page,
    request,
}) => {
    await openForm(page, AGGREGATE_FORM)

    const period = page.getByLabel('Reporting period')
    await expect(period).toBeVisible()
    // The type is the data set's own and is stated rather than asked, which is what makes the
    // identifier below editable without a calendar: what changes is which month, not which shape.
    await expect(page.getByText('Monthly period, as the data set reports.')).toBeVisible()

    const drafted = await period.inputValue()
    expect(drafted).toMatch(/^\d{6}$/)
    const edited = drafted.endsWith('01') ? `${drafted.slice(0, 4)}02` : `${drafted.slice(0, 4)}01`
    await period.fill(edited)

    const receiptId = await submitCapture(page)

    const stored = await storedResponse(request, receiptId)
    const captured = stored.extension?.find((extension) => extension.url.endsWith('/d2-period'))
    expect(captured?.extension?.find((sub) => sub.url === 'iso')?.valueString).toBe(edited)
    // The type rides unchanged, because the data set is what reports monthly.
    expect(captured?.extension?.find((sub) => sub.url === 'type')?.valueCode).toBe('Monthly')
    // And no date range at all: resolving one is DHIS2 period arithmetic this UI does not have, the
    // sub-extension is optional, and the ISO period is what is captured.
    expect(captured?.extension?.some((sub) => sub.url === 'period')).toBe(false)
})

test('an edited enrollment date is the date the stored enrollment begins', async ({ page, request }) => {
    const formId = await registrationFormId(request)
    test.skip(
        formId === null,
        'this project publishes no tracker registration form, so there is no enrollment to date',
    )
    // Narrowed for the compiler; `test.skip` above has already ended the run when it is null.
    if (formId === null) return

    await openForm(page, formId)

    const enrollmentDate = page.getByLabel('Enrollment date')
    await expect(enrollmentDate).toBeVisible()
    await expect(enrollmentDate).not.toHaveValue('')
    // The fixture's program collects no incident date and says so on `D2CollectsIncidentDate`, so
    // there is no second control - a date DHIS2 never asked for is not one this form offers.
    await expect(page.getByLabel('Incident date')).toHaveCount(0)

    await enrollmentDate.fill('2026-07-02T09:15')
    const receiptId = await submitCapture(page)

    const stored = await storedResponse(request, receiptId)
    const enrolledAt = stored.extension?.find((extension) => extension.url.endsWith('/d2-enrolled-at'))
    expect(enrolledAt?.valueDateTime).toBe('2026-07-02T09:15:00Z')
})

/**
 * The organisation unit a browser tab keeps, walked across three form loads.
 *
 * WHY IT IS KEPT AT ALL. A supervisor files six forms in a morning and reports every one of them
 * from the same facility. `$generate` draws a unit the form admits, which makes the draft postable
 * and says nothing about where the person is - so the choice is kept and the next form opens on it.
 *
 * WHY IT IS NOT ALWAYS ADOPTED. `PrScoped001` publishes an assignment naming two units, and the
 * facade refuses a capture outside it. A kept unit the assignment excludes is therefore not a unit
 * this form can be reported from, so the draft's own draw stands - and the picker says so, because
 * the difference between "the same unit as last time" and "some other unit" is exactly what a
 * person checking their submission needs to see.
 */
test.describe('the organisation unit a browser tab keeps', () => {
    test('carries a chosen unit into the next form, and states it when the next form excludes it', async ({
        page,
    }) => {
        // One tab throughout: this is session-scoped state, and a second tab would be a fresh start.
        await openForm(page, UNSCOPED_FORM)

        const unrestricted = page.getByLabel('Reporting from')
        await expect(page.getByText('The chosen organisation unit is kept for this browser tab')).toBeVisible()
        await unrestricted.click()
        await page.getByPlaceholder('Search by name, uid, or code').fill('bombali')
        await page.getByRole('option', { name: new RegExp(`^${OUTSIDE_UNIT}\\b`) }).click()
        await expect(unrestricted).toContainText(OUTSIDE_UNIT)

        // The scoped form is assigned to two units, and Bombali is neither.
        await openForm(page, SCOPED_FORM)
        const scoped = page.getByLabel('Reporting from')
        await expect(
            page.getByText('This form is not assigned to the organisation unit kept for this browser tab'),
        ).toBeVisible()
        await expect(scoped).not.toContainText(OUTSIDE_UNIT)
        await expect(scoped).toContainText(new RegExp(`${SHARED_UNIT}|Ngelehun CHC`))

        // Choosing answers the mismatch, and keeps a unit the next form can adopt.
        await scoped.click()
        await page.getByPlaceholder('Search by name, uid, or code').fill('OU_BO')
        await page.getByRole('option', { name: new RegExp(`^${SHARED_UNIT}\\b`) }).click()
        await expect(scoped).toContainText(SHARED_UNIT)
        await expect(
            page.getByText('This form is not assigned to the organisation unit kept for this browser tab'),
        ).toHaveCount(0)

        // The third load is the point of the whole feature: the form opens already reporting from
        // the unit the person chose, rather than from whichever unit the draw landed on.
        await openForm(page, UNSCOPED_FORM)
        await expect(page.getByLabel('Reporting from')).toContainText(SHARED_UNIT)
        await expect(
            page.getByText('This form is not assigned to the organisation unit kept for this browser tab'),
        ).toHaveCount(0)
    })
})

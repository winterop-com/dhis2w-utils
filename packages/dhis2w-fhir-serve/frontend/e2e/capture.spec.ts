import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The capture loop, end to end, against the real server.
 *
 * THE LOOP WITHOUT THE FORM UI. `$generate` fills one served form with synthetic
 * answers, and the operation's whole point is that its output posts back at the
 * same server for a 201 - so generate-then-post is the capture round trip with
 * the renderer taken out of it. That makes this spec provable today, and it
 * proves the half the renderer cannot: that a receipt reaches the spool, that
 * `/spool` reports it as `received`, and that the Responses page shows it.
 *
 * The last describe drives the same loop through the renderer instead, which is
 * how a person performs it.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

/** The aggregate form whose DHIS2 data set rides a non-default category combo. */
const ATTRIBUTE_COMBO_FORM = 'TuL8IOPzpHh'

/** One combo of the vocabulary that form declares, as the published CodeSystem displays it. */
const ATTRIBUTE_COMBO_CHOICE = 'Improve access to clean water'

/** The kind's code in the D2FormType terminology - `tracker-event` is the program stage. */
const REGISTRATION_FORM_TYPE = 'tracker'

/** What one served form states about itself, as far as finding the registration one needs. */
interface ServedForm {
    id: string
    title: string
}

/**
 * The registration form this project publishes, or null when it publishes none.
 *
 * Discovered rather than named, so the specs that need one are about the kind rather than about
 * one fixture's choice of uid - and start passing the moment the project publishes a
 * registration form, with nothing to unskip by hand.
 */
async function registrationForm(request: APIRequestContext): Promise<ServedForm | null> {
    const bundle = await request.get('/Questionnaire', { headers: { Accept: FHIR_JSON } })
    expect(bundle.status(), await bundle.text()).toBe(200)
    const body = (await bundle.json()) as {
        entry?: {
            resource?: {
                id?: string
                title?: string
                name?: string
                extension?: { url: string; valueCode?: string }[]
            }
        }[]
    }
    for (const entry of body.entry ?? []) {
        const resource = entry.resource
        if (resource?.id === undefined) continue
        const declared = resource.extension?.find((candidate) =>
            candidate.url.endsWith('/StructureDefinition/d2-form-type'),
        )
        if (declared?.valueCode !== REGISTRATION_FORM_TYPE) continue
        return { id: resource.id, title: resource.title ?? resource.name ?? resource.id }
    }
    return null
}

/** Ask the server to fill one form, then post the answer straight back at it. */
async function generateAndPost(request: APIRequestContext, questionnaireId: string, seed: number): Promise<string> {
    const generated = await request.get(`/Questionnaire/${questionnaireId}/$generate?seed=${String(seed)}`, {
        headers: { Accept: FHIR_JSON },
    })
    expect(generated.status(), await generated.text()).toBe(200)

    const posted = await request.post('/QuestionnaireResponse', {
        headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
        data: await generated.json(),
    })
    expect(posted.status(), await posted.text()).toBe(201)

    // The receipt id is where the created resource is served from, which the
    // create interaction states in its Location header exactly as R4 says.
    const location = posted.headers()['location']
    expect(location).toBeTruthy()
    return location.split('/').pop() ?? ''
}

test('the Responses page starts empty and says where a response comes from', async ({ page }) => {
    // Runs before anything is posted in this file, which is why the fixture
    // builder empties the spool: a receipt left over from the last run would
    // make this pass for the wrong reason, then make it fail.
    await page.goto('/#/responses')

    await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()
    await expect(page.getByText('Nothing has been captured into this project yet')).toBeVisible()
    await expect(page.getByText('$generate')).toBeVisible()
})

test('a generated response posts back and shows up as a received receipt', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 7)

    await page.goto('/#/responses')

    const row = page.getByRole('row').filter({ hasText: receiptId })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Received')
    await expect(row).toContainText('Child Health')
    await expect(row).toContainText('Aggregate data set')
})

test('the spool listing states the lifecycle and the counts', async ({ request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 11)

    const listing = await request.get('/spool', { headers: { Accept: 'application/json' } })
    expect(listing.status()).toBe(200)
    const body = (await listing.json()) as {
        total: number
        counts: { received: number; forwarded: number; rejected: number }
        responses: { response_id: string; lifecycle: string; period: string | null; answer_count: number }[]
    }

    const row = body.responses.find((candidate) => candidate.response_id === receiptId)
    expect(row).toBeDefined()
    expect(row?.lifecycle).toBe('received')
    expect(row?.answer_count).toBeGreaterThan(0)
    // An aggregate capture reports for a period; the listing derives it from the
    // D2Period extension on the stored resource.
    expect(row?.period).toBeTruthy()
    expect(body.counts.received).toBeGreaterThan(0)
})

test('the reload button re-reads the spool', async ({ page, request }) => {
    await page.goto('/#/responses')

    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 23)
    await page.getByRole('button', { name: 'Reload' }).click()

    // The point of the button: the server re-reads the spool directory to
    // answer, so a capture that happened after the page loaded appears without
    // anything being restarted. `d2w fhir forward` moves files the same way.
    await expect(page.getByRole('row').filter({ hasText: receiptId })).toHaveCount(1)
})

test('a row opens the receipt at its own route, with the answers on it', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 42)

    await page.goto('/#/responses')
    await page.getByRole('row').filter({ hasText: receiptId }).click()

    // The route is the receipt id, which is what makes one receipt a link somebody can be sent.
    await expect(page).toHaveURL(new RegExp(`#/responses/${receiptId}$`))
    await expect(page.getByText(receiptId).first()).toBeVisible()
    await expect(page.getByText('Received', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
    await expect(page.getByText('Period', { exact: true })).toBeVisible()
    await expect(page.getByText('Organisation unit', { exact: true })).toBeVisible()
    await expect(page.getByText('GET /QuestionnaireResponse/')).toBeVisible()

    // The headline: the answers joined to the questions the form asks. `Fixed, <1y` is the text
    // of a category option combo cell, and the group above it is what makes it mean something.
    const answers = page.getByRole('row').filter({ hasText: 's46m5MS0hxu.Prlt0C1RF0s' })
    await expect(answers).toHaveCount(1)
    await expect(answers).toContainText('BCG doses given')
    await expect(answers).toContainText('Fixed, <1y')

    await page.getByRole('link', { name: 'All responses' }).click()
    await expect(page).toHaveURL(/#\/responses$/)
})

test('the receipt route is deep-linkable and shows the raw resource on demand', async ({
    page,
    request,
}) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 43)

    // Straight to the URL, with no listing visited first - the whole point of the route.
    await page.goto(`/#/responses/${receiptId}`)

    await expect(page.getByRole('heading', { name: 'Answers' })).toBeVisible()
    await expect(page.getByText('generated from seed 43')).toBeVisible()

    await page.getByRole('button', { name: 'Raw QuestionnaireResponse' }).click()
    await expect(page.getByText('"resourceType": "QuestionnaireResponse"')).toBeVisible()
})

test('a keyboard user opens a receipt the same way', async ({ page, request }) => {
    const receiptId = await generateAndPost(request, AGGREGATE_FORM, 44)

    await page.goto('/#/responses')
    await page.getByRole('row').filter({ hasText: receiptId }).focus()
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(new RegExp(`#/responses/${receiptId}$`))
})

test('the lifecycle filter narrows the table', async ({ page, request }) => {
    await generateAndPost(request, AGGREGATE_FORM, 99)

    await page.goto('/#/responses')
    await page.getByRole('button', { name: /^Forwarded/ }).click()

    // Nothing has been forwarded in this project - the forwarder needs a DHIS2
    // instance - so the filter empties the table and says the total it is
    // filtering out of, rather than reading as "no receipts at all".
    await expect(page.getByText('No receipt matches this filter')).toBeVisible()
})

/**
 * The form-fill walkthrough: the half of the loop a person actually performs.
 *
 * The API round trip above proves the server side - generate, post, receipt. This
 * is the same loop driven the way it is used: open a form from the Forms table,
 * fill it with test data, submit, and land on the Responses page with the
 * receipt on it. It exercises the renderer, the answer state, the submit path,
 * and the listing in one pass, so it is the spec that fails when any of them
 * stops agreeing with the others.
 */
test.describe('filling a form in the browser', () => {
    test('opens a form, fills it with test data, submits, and finds the receipt', async ({
        page,
        request,
    }) => {
        const before = (await (await request.get('/spool')).json()) as { total: number }

        await page.goto('/#/forms')
        await page
            .getByRole('row')
            .filter({ hasText: 'Child Health' })
            .click()
        await expect(page).toHaveURL(new RegExp(`#/forms/${AGGREGATE_FORM}$`))

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()

        // The form navigates to the listing on success, which is the point: the
        // receipt is the thing you want to see next.
        await expect(page).toHaveURL(/#\/responses$/)
        await expect(page.getByRole('row').filter({ hasText: 'Child Health' }).first()).toBeVisible()

        const after = (await (await request.get('/spool')).json()) as { total: number }
        expect(after.total).toBe(before.total + 1)
    })
})

/**
 * The one piece of capture context a person supplies, on the one form that needs it.
 *
 * A DHIS2 data value is keyed by the organisation unit, the period, and the attribute option
 * combo. The first two come off `$generate`; the third cannot - which project a month of stock
 * figures is reported under is a fact the person filling the form brought with them - so the form
 * asks for it above the questions and Submit refuses until it has one. This walks that: the picker
 * renders the combos the served vocabulary publishes, the button is disabled with a reason, and
 * the chosen combo is on the receipt afterwards, named the same way it was picked.
 */
test.describe('a form whose data set reports per attribute option combo', () => {
    test('asks for the combo, refuses to submit without one, and puts it on the receipt', async ({
        page,
    }) => {
        // The skeleton read is awaited rather than raced: `$generate` draws a combo of its own and
        // it lands in the picker as the pre-selection, so "nothing is chosen" is a state this spec
        // has to arrive at deliberately - which is what Clear below is for.
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${ATTRIBUTE_COMBO_FORM}`)
        await opened

        // The label is the published vocabulary's own title - the DHIS2 category combo's name -
        // rather than the artifact's, which is what a data clerk is actually choosing between.
        const picker = page.getByLabel('Reporting for Project')
        await expect(picker).toBeVisible()
        // The draw is a proposal: whatever combo `$generate` filed its skeleton under is already
        // in the picker, so the common case is one click rather than a hunt through the list.
        await expect(picker).not.toHaveText('Not chosen')

        const submit = page.getByRole('button', { name: 'Submit' })
        await page.getByRole('button', { name: 'Clear' }).click()
        await expect(submit).toBeDisabled()
        await expect(page.getByText('Choose what this submission reports for before submitting')).toBeVisible()

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        // Chosen after the refill, because a refill is the server proposing a whole submission and
        // its combo lands in the picker too - so the last word here has to be the user's.
        await picker.click()
        await page.getByRole('option', { name: new RegExp(ATTRIBUTE_COMBO_CHOICE) }).click()
        await expect(submit).toBeEnabled()

        await submit.click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        await page.getByRole('row').filter({ hasText: 'EPI Stock' }).first().click()
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
        await expect(page.getByText('Reporting for Project', { exact: true })).toBeVisible()
        await expect(page.getByText(ATTRIBUTE_COMBO_CHOICE)).toBeVisible()
    })
})

/**
 * The other piece of capture context a person supplies, on the form whose assignment narrows it.
 *
 * `PrScoped001` publishes an organisation-unit assignment naming two of the ten units this project
 * publishes, and the facade grades a submission's unit against exactly that List - `E1029` is what
 * DHIS2 refuses a capture outside it with. So the picker offering two rows rather than ten is not a
 * convenience: it is the difference between a control that can produce a refused submission and one
 * that cannot. This walks it end to end - the offer, the search, the change, and the unit on the
 * receipt afterwards.
 */
test.describe('a form whose assignment narrows where it may be reported from', () => {
    /** The event form restricted to one district and one facility, on different branches. */
    const SCOPED_FORM = 'PrScoped001'

    /** The facility the specs below hold in the picker when they need a known selection. */
    const HELD_UNIT = 'Ngelehun CHC'

    /** The district, chosen here by its DHIS2 code to prove the search reads identifiers too. */
    const CHOSEN_UNIT = 'Bo'
    const CHOSEN_UNIT_CODE = 'OU_BO'
    const CHOSEN_UNIT_UID = 'O6uvpzGd5pu'

    test('offers only the assigned units, narrows on search, and puts the chosen one on the receipt', async ({
        page,
    }) => {
        // The skeleton is awaited rather than raced: the drawn unit lands in the picker as the
        // pre-selection, and "already answered" is the state this spec starts from. Which of the
        // two assigned units it is is the seed's business - the draw ranges over the whole
        // assignment - so the assertion is that the pre-selection is one the assignment admits.
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${SCOPED_FORM}`)
        await opened

        const picker = page.getByLabel('Reporting from')
        await expect(picker).toBeVisible()
        await expect(picker).toContainText(new RegExp(`${CHOSEN_UNIT}|${HELD_UNIT}`))
        await expect(page.getByText('2 organisation units are assigned to this form')).toBeVisible()
        // The consequence is stated as the fact, without the tracker importer's error code - the
        // refusal wording differs per kind, and E-codes belong to the import report that states them.
        await expect(
            page.getByText(
                "A capture outside the form's assigned organisation units is refused when it reaches DHIS2.",
            ),
        ).toBeVisible()

        // Two of ten. The registry the organisation-units page browses is the same one this reads.
        await picker.click()
        await expect(page.getByRole('option')).toHaveCount(2)

        const search = page.getByPlaceholder('Search by name, uid, or code')
        await search.fill('ngele')
        await expect(page.getByRole('option')).toHaveCount(1)

        await search.fill(CHOSEN_UNIT_CODE)
        await expect(page.getByRole('option')).toHaveCount(1)
        // The row is the unit's name, its level, and the parent it sits under - so it is matched on
        // the name it starts with rather than on the whole line.
        await page.getByRole('option', { name: new RegExp(`^${CHOSEN_UNIT}\\b`) }).click()
        await expect(picker).toContainText(CHOSEN_UNIT)

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        await page.getByRole('row').filter({ hasText: 'Outbreak response' }).first().click()
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
        // Named rather than left as a uid: the receipt page reads the registry, so the unit reads
        // as the place it is, with the uid DHIS2 stores beside it.
        await expect(page.getByText(`${CHOSEN_UNIT} (${CHOSEN_UNIT_UID})`)).toBeVisible()
    })

    /**
     * The same offer, walked as the hierarchy instead of typed at.
     *
     * The fixture's assignment is the shape this mode exists for: it names Bo and Ngelehun CHC, and
     * Ngelehun sits under Badjia, a district it does not name. So the tree has to keep two
     * unassigned units as unpickable context - they are the chain that says which Ngelehun CHC this
     * is - while dropping Bombali's whole branch, which admits nothing anywhere below it. What is
     * chosen at the end goes through the same submit path a searched choice does.
     */
    test('browses the hierarchy, disables what is not assigned, prunes what leads nowhere', async ({
        page,
    }) => {
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${SCOPED_FORM}`)
        await opened

        // Pinned before browsing: the draw ranges over the whole assignment, and this spec's tree
        // assertions are about the shape around one known selection - the facility, whose ancestor
        // chain is what the tree has to keep as unpickable context.
        const picker = page.getByLabel('Reporting from')
        await picker.click()
        await page.getByPlaceholder('Search by name, uid, or code').fill('ngele')
        await page.getByRole('option', { name: new RegExp(`^${HELD_UNIT}\\b`) }).click()
        await expect(picker).toContainText(HELD_UNIT)

        await picker.click()
        await page.getByRole('button', { name: 'Browse' }).click()

        // Opened on the selection's ancestors, so the unit the picker holds is on screen without a
        // chevron being clicked - which is the whole difference from a tree that opens collapsed.
        const tree = page.getByRole('tree', { name: 'Organisation unit hierarchy' })
        await expect(tree).toBeVisible()
        await expect(tree.getByRole('treeitem')).toHaveCount(4)
        await expect(tree.getByRole('treeitem', { name: 'Sierra Leone', exact: true })).toBeVisible()
        await expect(tree.getByRole('treeitem', { name: CHOSEN_UNIT, exact: true })).toBeVisible()
        await expect(tree.getByRole('treeitem', { name: 'Badjia', exact: true })).toBeVisible()
        await expect(tree.getByRole('treeitem', { name: HELD_UNIT, exact: true })).toBeVisible()

        // Pruned, not disabled: nothing under Bombali is assigned, so the branch is not drawn at
        // all. Bo's two other districts and Adonkia CHP, the detached root, go the same way.
        await expect(
            tree.getByRole('treeitem', { name: /Bombali|Kagbere|Yoni|Bargbe|Baoma|Adonkia/ }),
        ).toHaveCount(0)

        const unassigned = tree.getByRole('treeitem', { name: 'Badjia', exact: true })
        await expect(unassigned).toHaveAttribute('aria-disabled', 'true')
        await expect(tree.getByRole('treeitem', { name: 'Sierra Leone', exact: true })).toHaveAttribute(
            'aria-disabled',
            'true',
        )
        await expect(tree.getByRole('treeitem', { name: CHOSEN_UNIT, exact: true })).not.toHaveAttribute(
            'aria-disabled',
            'true',
        )

        // Clicking one changes nothing: the popover stays open and the picker keeps what it held.
        // Forced past the actionability wait, because the row states that it is disabled and the
        // point of the assertion is what the click does when it lands anyway.
        await unassigned.click({ force: true })
        await expect(tree).toBeVisible()
        await expect(picker).toContainText(HELD_UNIT)

        // The chevron is expansion and never selection, so folding a district up cannot answer the
        // control by accident - not even on a row that is itself a choice.
        await page.getByRole('button', { name: `Collapse ${CHOSEN_UNIT}` }).click()
        await expect(tree.getByRole('treeitem')).toHaveCount(2)
        await expect(picker).toContainText(HELD_UNIT)
        await page.getByRole('button', { name: `Expand ${CHOSEN_UNIT}` }).click()
        await expect(tree.getByRole('treeitem', { name: HELD_UNIT, exact: true })).toBeVisible()

        // Typing is searching in either mode: the query overrides Browse rather than landing in a
        // box that does nothing.
        await page.getByPlaceholder('Search by name, uid, or code').fill('bo')
        await expect(tree).toHaveCount(0)
        await expect(page.getByRole('option', { name: new RegExp(`^${CHOSEN_UNIT}\\b`) })).toBeVisible()

        // And the toggle takes it back, with the query cleared.
        await page.getByRole('button', { name: 'Browse' }).click()
        await expect(tree.getByRole('treeitem')).toHaveCount(4)

        await tree.getByRole('treeitem', { name: CHOSEN_UNIT, exact: true }).click()
        await expect(picker).toContainText(CHOSEN_UNIT)

        // The round trip is unchanged by which mode found the unit.
        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        await page.getByRole('row').filter({ hasText: 'Outbreak response' }).first().click()
        await expect(page.getByText(`${CHOSEN_UNIT} (${CHOSEN_UNIT_UID})`)).toBeVisible()
    })
})

/**
 * A DHIS2 `ORGANISATION_UNIT` data element, filled in.
 *
 * The emitter writes that value type as a `reference` question, and `PrTemporal1` asks one -
 * "Visited unit". It used to render as "not filled in this UI"; it is the same picker the reporting
 * unit uses, in the field grid. This form publishes no assignment, so the offer is the whole
 * registry - which is the other half of the intersection the spec above covers.
 */
test.describe('a form asking for an organisation unit as an answer', () => {
    const TEMPORAL_FORM = 'PrTemporal1'

    test('fills a reference question from the registry and shows the unit on the receipt', async ({
        page,
    }) => {
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${TEMPORAL_FORM}`)
        await opened

        const answer = page.getByLabel('Visited unit')
        await expect(answer).toBeVisible()
        await expect(page.getByText('is not filled in this UI')).toHaveCount(0)
        await expect(page.getByText('assigned everywhere')).toBeVisible()

        // The draw answers the question too, and a refill is what pours those answers into the
        // form - so this is the pre-selection landing, not the envelope's own unit. Which unit
        // the draw named is the seed's business; that the control stopped being unanswered is
        // the fact under test.
        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()
        await expect(answer).not.toContainText('Not chosen')

        await answer.click()
        await page.getByPlaceholder('Search by name, uid, or code').fill('bombali')
        await page.getByRole('option', { name: /Bombali/ }).click()
        await expect(answer).toContainText('Bombali')

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()

        await page.getByRole('row').filter({ hasText: 'Temporal capture' }).first().click()
        const row = page.getByRole('row').filter({ hasText: 'DeVisitUnit1' })
        await expect(row).toHaveCount(1)
        await expect(row).toContainText('Visited unit')
        // The name this UI wrote onto the reference's display, with the uid DHIS2 stores beside it.
        await expect(row).toContainText('Bombali')
        await expect(row).toContainText('fdc6uOvgoji')
    })

    /**
     * The tree by keyboard alone, on the form whose offer is the whole registry.
     *
     * Browse hands the keyboard to the tree the moment it opens, so a person who never touches the
     * mouse arrows down the hierarchy and presses Enter - the same two keys cmdk's list answers to
     * in search mode, which is the habit worth keeping across the toggle.
     */
    test('walks the hierarchy with the arrow keys and picks with Enter', async ({ page }) => {
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${TEMPORAL_FORM}`)
        await opened

        const answer = page.getByLabel('Visited unit')
        await answer.click()
        await page.getByRole('button', { name: 'Browse' }).click()

        // Nothing is held, so the tree opens one level down: the root and the detached unit, with
        // the keyboard already standing on the first row.
        const tree = page.getByRole('tree', { name: 'Organisation unit hierarchy' })
        await expect(tree.getByRole('treeitem', { name: 'Sierra Leone', exact: true })).toBeFocused()

        // One row down is the root's first district, and Enter answers with it - no assignment
        // narrows this form, so every row on the way is a choice.
        await page.keyboard.press('ArrowDown')
        await page.keyboard.press('Enter')
        await expect(answer).toContainText('Bo')
        await expect(tree).toHaveCount(0)
    })
})

/**
 * The tracker-event stage form, filled in the browser: the receipt that is about a person.
 *
 * A tracker event reports against an enrollment rather than a place, so its receipt carries the
 * tracked entity and enrollment uids on the envelope - the two handles the forwarder posts under
 * `/api/tracker`. This walks the one path no other fill spec reaches: a submission whose capture
 * context is entity-level, and whose coded answers come back with both halves of the coding.
 */
test.describe('filling a tracker-event form', () => {
    /** The program-stage form of the tracker goldens, with coded questions bound to published sets. */
    const TRACKER_EVENT_FORM = 'ZzYYXq4fJie'

    test('fills the stage form, submits, and the receipt names the entity and enrollment', async ({
        page,
    }) => {
        // The skeleton mints the tracker pair; awaiting it is what makes the fill submittable.
        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${TRACKER_EVENT_FORM}`)
        await opened

        // This stage's program has no registration form in the fixture, so the enrollment picker
        // has nothing to offer and says exactly what that means for the submission - the honest
        // framing of a synthetic pair, rather than a control that looks routinely answered.
        await expect(page.getByLabel('Answering for')).toBeVisible()
        await expect(page.getByText('No registration has been captured for this program yet')).toBeVisible()

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        const listed = page.getByRole('row').filter({ hasText: 'Baby Postnatal' }).first()
        await expect(listed).toContainText('Tracker program stage')
        await listed.click()

        // The entity-level context: the tracked entity and the enrollment, on the envelope rather
        // than in any answer, under the same labels the registration receipt uses.
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
        await expect(page.getByText('Tracked entity', { exact: true })).toBeVisible()
        await expect(page.getByText('Enrollment', { exact: true })).toBeVisible()

        // A coded answer keeps both halves: the display a person reads, and the DHIS2 option uid
        // the forwarder writes. The published option set holds one concept, so the draw is it.
        const coded = page.getByRole('row').filter({ hasText: 'X8zyunlgUfM' })
        await expect(coded).toHaveCount(1)
        await expect(coded).toContainText('Mixed')
        await expect(coded).toContainText('odMfnhhpjUj')
    })
})

/**
 * Registering a person: the form kind whose whole submission is context.
 *
 * A tracker registration answers the tracked entity attributes and files an enrollment, and every
 * fact about that enrollment - the tracked entity uid, the enrollment uid, the date it begins, the
 * date of the incident it follows - rides the envelope rather than any answer. So this walks the
 * one thing the other capture specs cannot: that a person can read those facts before submitting,
 * and find them again on the receipt afterwards.
 *
 * THE FORM IS DISCOVERED, NOT NAMED. Every other spec here hard-codes the uid of the form it
 * drives, because those forms have been in the fixture project since it was written. This one asks
 * the server which of its Questionnaires declares the `tracker` form type, so the spec is about
 * the kind rather than about one fixture's choice of uid - and so it starts passing the moment the
 * project publishes a registration form, with nothing to unskip by hand.
 */
test.describe('a tracker registration form', () => {
    test('opens as a registration, states the enrollment it files, and puts it on the receipt', async ({
        page,
        request,
    }) => {
        const form = await registrationForm(request)
        test.skip(
            form === null,
            'this project publishes no tracker registration form, so there is no kind to capture against',
        )
        // Narrowed for the compiler; `test.skip` above has already ended the run when it is null.
        if (form === null) return

        // `$generate` is what makes a registration postable - the minted uids and the enrollment
        // dates are all its work - so a server that does not answer for the kind is a dependency
        // this spec states rather than a failure it reports.
        const skeleton = await request.get(`/Questionnaire/${form.id}/$generate?seed=5`, {
            headers: { Accept: FHIR_JSON },
        })
        test.skip(
            skeleton.status() !== 200,
            'this server does not answer $generate for the tracker kind, so a registration cannot be filled here',
        )

        // The listing shelves the form inside its program's tracker group, with its role stated.
        await page.goto('/#/forms')
        const listed = page
            .getByTestId('forms-tracker-programs')
            .getByRole('row')
            .filter({ hasText: form.title })
            .first()
        await expect(listed).toContainText('registration - enrols a person')

        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await listed.click()
        await expect(page).toHaveURL(new RegExp(`#/forms/${form.id}$`))
        await opened

        // The facts the envelope carries and no question holds. The server draws them as part of
        // the skeleton that makes the submission postable, and the dates among them are the
        // reporter's to correct - a visit recorded on the day it is typed up is a visit misdated.
        const enrollment = page.getByRole('heading', { name: 'Enrollment', exact: true })
        await expect(enrollment).toBeVisible()
        await expect(page.getByLabel('Enrollment date')).toBeVisible()

        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        const receipt = page.getByRole('row').filter({ hasText: form.title }).first()
        await expect(receipt).toContainText('Tracker registration')
        await receipt.click()

        // The receipt states the same enrollment the form showed, under the same labels - the two
        // minted uids mono, because they are handles to type into DHIS2, and the date as prose.
        await expect(page.getByRole('heading', { name: 'Capture context' })).toBeVisible()
        await expect(page.getByText('Tracked entity', { exact: true })).toBeVisible()
        await expect(page.getByText('Enrollment', { exact: true })).toBeVisible()
        await expect(page.getByText('Enrolled at', { exact: true })).toBeVisible()
        await expect(page.getByText('Organisation unit', { exact: true })).toBeVisible()
    })
})

/**
 * A stage form answering for an enrollment this server really minted - the whole reason the
 * "Answering for" picker exists.
 *
 * The `$generate` skeleton adopts the newest spooled registration's pair and mints synthetic
 * identifiers only when no registration receipt exists - an unassisted submission is then
 * refused by DHIS2 at forward time (`E1079`/`E1313` - the enrollment does not exist). The real
 * pairs are in this server's own spool: `PsAncVisit1` names its program on the `{base}/id/program`
 * identifier, the fixture's registration form carries the same identifier as its identity, and
 * every receipt answering that form holds one minted pair. This walks the join end to end:
 * capture a registration, open the stage form, find its enrollment on offer, choose it, and read
 * the chosen pair off the stored stage receipt.
 *
 * The fixture suite runs no forwarder, so every offer here is in the `received` state - which is
 * precisely the state whose inline warning this spec pins, along with the refill rule that a
 * fresh draw's answers must not replace a chosen identity.
 */
test.describe('a stage form answering for a captured registration', () => {
    /** The stage form of the program whose registration form the fixture publishes. */
    const STAGE_FORM = 'PsAncVisit1'

    test('offers the captured enrollment, warns until it is forwarded, and submits with it', async ({
        page,
        request,
    }) => {
        const form = await registrationForm(request)
        test.skip(
            form === null,
            'this project publishes no tracker registration form, so there is no enrollment to offer',
        )
        if (form === null) return

        // Capture one registration - the same generate-then-post round trip the browser performs
        // - and keep the pair it minted, which is what the picker must offer back.
        const generated = await request.get(`/Questionnaire/${form.id}/$generate?seed=61`, {
            headers: { Accept: FHIR_JSON },
        })
        expect(generated.status(), await generated.text()).toBe(200)
        const registration = (await generated.json()) as {
            subject?: { identifier?: { value?: string } }
            extension?: { url: string; valueIdentifier?: { value?: string } }[]
        }
        const enrollment =
            registration.extension?.find((candidate) => candidate.url.endsWith('/d2-tracker-enrollment'))
                ?.valueIdentifier?.value ?? ''
        const trackedEntity = registration.subject?.identifier?.value ?? ''
        expect(enrollment).toBeTruthy()
        expect(trackedEntity).toBeTruthy()
        const posted = await request.post('/QuestionnaireResponse', {
            headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
            data: registration,
        })
        expect(posted.status(), await posted.text()).toBe(201)

        const opened = page.waitForResponse((response) => response.url().includes('$generate'))
        await page.goto(`/#/forms/${STAGE_FORM}`)
        await opened

        // Nothing has been forwarded, so nothing is defaulted - and the picker says what an
        // unchosen state means for the submission instead of letting it look routine.
        const picker = page.getByLabel('Answering for')
        await expect(picker).toBeVisible()
        await expect(
            page.getByText('Nothing is chosen, so this submission answers for the newest captured'),
        ).toBeVisible()

        // The offer is the registration just captured, labelled honestly: the minted uid and the
        // lifecycle its receipt is in.
        await picker.click()
        const offered = page.getByRole('option', { name: new RegExp(enrollment) })
        await expect(offered).toBeVisible()
        await expect(offered).toContainText('Received')
        await offered.click()
        await expect(picker).toContainText(enrollment)

        // Selectable but said out loud: DHIS2 must receive the registration first.
        await expect(page.getByText('DHIS2 has not received this registration yet')).toBeVisible()

        // The refill rule: the answers are the fresh draw's, the identity stands.
        await page.getByRole('button', { name: 'Fill with test data' }).click()
        await expect(page.getByText('Filled with test data')).toBeVisible()
        await expect(picker).toContainText(enrollment)

        await page.getByRole('button', { name: 'Submit' }).click()
        await expect(page.getByText('The server accepted this submission')).toBeVisible()
        await expect(page).toHaveURL(/#\/responses$/)

        // The stored stage receipt carries the chosen pair - the spool derives both off the
        // resource, so this is the submission as the forwarder will read it.
        const listing = await request.get('/spool', { headers: { Accept: 'application/json' } })
        expect(listing.status()).toBe(200)
        const spool = (await listing.json()) as {
            responses: {
                questionnaire_id?: string | null
                tracked_entity?: string | null
                tracker_enrollment?: string | null
            }[]
        }
        const stageReceipt = spool.responses.find((row) => row.questionnaire_id === STAGE_FORM)
        expect(stageReceipt).toBeDefined()
        expect(stageReceipt?.tracker_enrollment).toBe(enrollment)
        expect(stageReceipt?.tracked_entity).toBe(trackedEntity)
    })
})

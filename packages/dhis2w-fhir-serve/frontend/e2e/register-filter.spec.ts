import { expect, test, type Page } from '@playwright/test'

/**
 * Which of a register's tracked entities hold a given attribute value.
 *
 * THE SECOND QUESTION THIS REGISTER ANSWERS. The box at the top of the page asks who somebody is -
 * `identifier`, over the values DHIS2 declares unique - and this asks which of them hold one
 * attribute's value: `d2-attribute={uid}|{value}`, matched exactly. `/metadata` documents the
 * grammar and `/facade/uiconfig` states the attributes it answers over, so the control is drawn from the
 * server's own declaration rather than from a list this browser keeps.
 *
 * WHAT IS FULFILLED AND WHAT IS REAL, on the idiom register.spec.ts established. `/facade/uiconfig`,
 * `/metadata` and `/Patient` are answered here, because the fixture server serves a compiled guide
 * and holds no DHIS2 instance. The vocabulary behind the coded control is the real one: the fixture
 * project publishes `d2-os-OsSex000001`, whose concept codes are DHIS2 option UIDs and whose
 * `dhis2-code` property carries the value the instance actually holds. That difference is the whole
 * point of the coded case - a control sending the concept code would ask for `OpFemale001` and be
 * answered nobody, on every deployment, forever.
 */

const FHIR_JSON = 'application/fhir+json'
const CANONICAL = 'http://localhost:8080/fhir'
const IDENTIFIER_BASE = 'http://dhis2.org/fhir'

/** The published vocabulary the coded attribute draws its values from, and the two facts about one. */
const SEX_VALUE_SET = `${CANONICAL}/ValueSet/d2-os-OsSex000001-vs`
const FEMALE_LABEL = 'Female'
const FEMALE_VALUE = 'F'

/** The attributes this run declares `d2-attribute` answers over: one coded, one typed into. */
const FILTER_ATTRIBUTES = [
    { uid: 'TeaSex00001', name: 'Sex', value_type: 'TEXT', value_set: SEX_VALUE_SET },
    { uid: 'TeaHousehld', name: 'Household size', value_type: 'NUMBER', value_set: null },
]

/** The register the settings declare: people, filtered by those two attributes. */
const REGISTER = {
    resource: 'Patient',
    types: [{ uid: 'TetPerson01', name: 'Person' }],
    filter_attributes: FILTER_ATTRIBUTES,
}

/** The Patient entry a live process declares, `d2-attribute` and all. */
const PATIENT_CAPABILITY = {
    type: 'Patient',
    documentation: 'One DHIS2 tracked entity per Patient, read from the instance at request time.',
    interaction: [{ code: 'read' }, { code: 'search-type' }],
    searchParam: [
        { name: 'identifier', type: 'token' },
        { name: 'd2-attribute', type: 'token' },
    ],
}

/** One person per sex, so a filter that reached the instance is a page that changed. */
const FEMALE_UID = 'TeiPerson001'
const MALE_UID = 'TeiPerson002'
const FEMALE_ID = '19850312-4471'
const MALE_ID = '19910704-2210'

const PEOPLE = [
    person(FEMALE_UID, FEMALE_ID, FEMALE_VALUE, '4'),
    person(MALE_UID, MALE_ID, 'M', '6'),
]

/** One person as the projection publishes them: identity, and the attribute values they hold. */
function person(uid: string, nationalId: string, sex: string, household: string): Record<string, unknown> {
    return {
        resourceType: 'Patient',
        id: uid,
        meta: { tag: [{ system: `${IDENTIFIER_BASE}/id/tracked-entity-type`, code: 'TetPerson01' }] },
        identifier: [
            { system: `${IDENTIFIER_BASE}/id/tracked-entity`, value: uid },
            { system: `${IDENTIFIER_BASE}/tracked-entity-attribute/TeaNationId`, value: nationalId },
        ],
        extension: [
            {
                url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
                extension: [
                    { url: 'attributeId', valueString: 'TeaSex00001' },
                    { url: 'value', valueString: sex },
                ],
            },
            {
                url: `${CANONICAL}/StructureDefinition/d2-tracked-entity-attribute-value`,
                extension: [
                    { url: 'attributeId', valueString: 'TeaHousehld' },
                    { url: 'value', valueString: household },
                ],
            },
        ],
    }
}

/**
 * Answer as a live process filtering on `d2-attribute` does - exactly, and on the value alone.
 *
 * The narrowing is done here rather than asserted on the request alone because the page has to be
 * shown to change: a parameter that reached the server and narrowed nothing would pass a
 * request-only assertion while the reader looked at everybody.
 */
async function serveAFilteredRegister(page: Page): Promise<void> {
    await page.route('**/uiconfig', (route) =>
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                basemaps: [],
                dhis2_base_url: null,
                tracked_entities: { enabled: true, listing: true, registers: [REGISTER] },
            }),
        }),
    )
    await page.route('**/metadata', async (route) => {
        const response = await route.fetch()
        const document = (await response.json()) as { rest?: { resource?: unknown[] }[] }
        document.rest?.[0]?.resource?.push(PATIENT_CAPABILITY)
        await route.fulfill({ status: 200, contentType: FHIR_JSON, body: JSON.stringify(document) })
    })
    await page.route(
        (url) => url.pathname === '/Patient',
        (route) => {
            const parameters = new URL(route.request().url()).searchParams
            const filters = parameters.getAll('d2-attribute')
            const matching = PEOPLE.filter((candidate) =>
                filters.every((filter) => holdsValue(candidate, filter)),
            )
            return route.fulfill({
                status: 200,
                contentType: FHIR_JSON,
                body: JSON.stringify({
                    resourceType: 'Bundle',
                    type: 'searchset',
                    total: matching.length,
                    link: [{ relation: 'self', url: '/Patient?_count=25' }],
                    entry: matching.map((resource) => ({ resource, search: { mode: 'match' } })),
                }),
            })
        },
    )
}

/** Whether one served person holds the value one `{uid}|{value}` names, matched exactly. */
function holdsValue(candidate: Record<string, unknown>, filter: string): boolean {
    const marker = filter.indexOf('|')
    const attributeUid = filter.slice(0, marker)
    const value = filter.slice(marker + 1)
    const extensions = candidate.extension as { extension: { url: string; valueString: string }[] }[]
    return extensions.some((held) => {
        const sub = new Map(held.extension.map((part) => [part.url, part.valueString]))
        return sub.get('attributeId') === attributeUid && sub.get('value') === value
    })
}

test.describe('the register filtered by an attribute value', () => {
    test('sends the value DHIS2 holds for a coded attribute, not the concept code', async ({ page }) => {
        await serveAFilteredRegister(page)
        await page.goto('/#/tracked-entities')

        const listing = page.getByTestId('patient-listing')
        await expect(listing.getByRole('row').filter({ hasText: MALE_ID })).toBeVisible()

        await page.getByRole('combobox', { name: 'Tracked entity attribute' }).click()
        await page.getByRole('option', { name: 'Sex' }).click()

        const filtered = page.waitForRequest(
            (request) =>
                new URL(request.url()).searchParams.get('d2-attribute') === `TeaSex00001|${FEMALE_VALUE}`,
        )
        await page.getByRole('combobox', { name: 'Value', exact: true }).click()
        // The option reads as the vocabulary names it and writes the code DHIS2 stores - the
        // concept code beside it is an option UID, which no attribute value ever equals.
        await page.getByRole('option', { name: FEMALE_LABEL }).click()
        await filtered

        await expect(listing.getByRole('row').filter({ hasText: FEMALE_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: MALE_ID })).toHaveCount(0)
        // A filtered register is a link somebody can be sent, beside what is being searched for.
        await expect(page).toHaveURL(/attribute=TeaSex00001%7CF/)
    })

    test('takes a typed value on the control the value type shapes, and lets go of it again', async ({
        page,
    }) => {
        await serveAFilteredRegister(page)
        await page.goto('/#/tracked-entities')

        await page.getByRole('combobox', { name: 'Tracked entity attribute' }).click()
        await page.getByRole('option', { name: 'Household size' }).click()
        // A NUMBER attribute is typed into a number field: the two value types a browser can help
        // with are the two it is given.
        const value = page.getByLabel('Value', { exact: true })
        await expect(value).toHaveAttribute('type', 'number')

        const filtered = page.waitForRequest(
            (request) => new URL(request.url()).searchParams.get('d2-attribute') === 'TeaHousehld|6',
        )
        await value.fill('6')
        await page.getByRole('button', { name: 'Filter' }).click()
        await filtered

        const listing = page.getByTestId('patient-listing')
        await expect(listing.getByRole('row').filter({ hasText: MALE_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: FEMALE_ID })).toHaveCount(0)

        await page.getByRole('button', { name: 'Clear' }).click()
        await expect(listing.getByRole('row').filter({ hasText: FEMALE_ID })).toBeVisible()
        await expect(page).not.toHaveURL(/attribute=/)
    })

    test('opens on the filter the address named, and says the match is exact', async ({ page }) => {
        await serveAFilteredRegister(page)

        const filtered = page.waitForRequest(
            (request) => new URL(request.url()).searchParams.get('d2-attribute') === 'TeaHousehld|4',
        )
        await page.goto('/#/tracked-entities?attribute=TeaHousehld%7C4')
        await filtered

        const listing = page.getByTestId('patient-listing')
        await expect(listing.getByRole('row').filter({ hasText: FEMALE_ID })).toBeVisible()
        await expect(listing.getByRole('row').filter({ hasText: MALE_ID })).toHaveCount(0)
        // The one thing a person has to know before they type: this is equality and nothing else,
        // so half a value finds nobody rather than a shorter list.
        await expect(page.getByTestId('register-attribute-filter')).toContainText('matched exactly')
    })

    test('offers no such control on a register the server declares no filter attributes for', async ({
        page,
    }) => {
        await serveAFilteredRegister(page)
        // Registered after it, so it takes the settings route over: Playwright matches the most
        // recently added handler first. What changes is one field - the register declares no
        // attributes to filter by, and the control is gone rather than empty.
        await page.route('**/uiconfig', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    basemaps: [],
                    dhis2_base_url: null,
                    tracked_entities: {
                        enabled: true,
                        listing: true,
                        registers: [{ resource: 'Patient', types: REGISTER.types }],
                    },
                }),
            }),
        )
        await page.goto('/#/tracked-entities')

        await expect(page.getByTestId('patient-listing')).toBeVisible()
        await expect(page.getByTestId('register-attribute-filter')).toHaveCount(0)
    })
})

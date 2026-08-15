import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * The two DHIS2 value types R4 spells as one item type, and the No only one of them has.
 *
 * WHAT IS UNDER TEST. A `#boolean` question is a `BOOLEAN` data element or a `TRUE_ONLY` one, and
 * the compiled form says nothing about which: the fact is a `value-type` property on the concept the
 * item's `code` names, in the data dictionary the guide publishes beside the form. It matters
 * because DHIS2 stores no false value for a `TRUE_ONLY` data element - the forwarder drops one - so
 * a control offering No for one would offer an answer that is discarded on the way in.
 *
 * WHY THE TRUE_ONLY FORM IS DISCOVERED. This project's goldens declare no `TRUE_ONLY` data element,
 * and hard-coding one would be a spec about a fixture rather than about the value type. So the
 * dictionaries are read, a question of that type is looked for, and the spec states its dependency
 * by skipping when the project publishes none - and starts running the moment one is published.
 * The `BOOLEAN` half beside it always runs, and is what pins that the three-state control is
 * untouched.
 */

const FHIR_JSON = 'application/fhir+json'

/** The stage form of the goldens, which asks one plain BOOLEAN question. */
const BOOLEAN_FORM = 'PsAncVisit1'
const BOOLEAN_QUESTION = 'ANC danger signs present'

/** The DHIS2 value type that stores `true` or no value at all. */
const TRUE_ONLY = 'TRUE_ONLY'

/** One question of one served form, as far as opening it and reading its control needs. */
interface ServedQuestion {
    questionnaireId: string
    text: string
}

/** Every concept of every served dictionary that carries a value type, keyed by system and code. */
async function valueTypesByConcept(request: APIRequestContext): Promise<Map<string, string>> {
    const bundle = await request.get('/CodeSystem', { headers: { Accept: FHIR_JSON } })
    expect(bundle.status(), await bundle.text()).toBe(200)
    const body = (await bundle.json()) as {
        entry?: {
            resource?: {
                url?: string
                concept?: { code: string; property?: { code: string; valueCode?: string; valueString?: string }[] }[]
            }
        }[]
    }
    const valueTypes = new Map<string, string>()
    for (const entry of body.entry ?? []) {
        for (const concept of entry.resource?.concept ?? []) {
            const stated = concept.property?.find((property) => property.code === 'value-type')
            const valueType = stated?.valueCode ?? stated?.valueString
            if (valueType === undefined) continue
            valueTypes.set(`${entry.resource?.url ?? ''}|${concept.code}`, valueType)
        }
    }
    return valueTypes
}

/** The first boolean question this project publishes of one DHIS2 value type, or null for none. */
async function booleanQuestionOfType(
    request: APIRequestContext,
    valueType: string,
): Promise<ServedQuestion | null> {
    const valueTypes = await valueTypesByConcept(request)
    const bundle = await request.get('/Questionnaire', { headers: { Accept: FHIR_JSON } })
    expect(bundle.status(), await bundle.text()).toBe(200)
    const body = (await bundle.json()) as {
        entry?: { resource?: { id?: string; item?: ServedItem[] } }[]
    }
    for (const entry of body.entry ?? []) {
        const questionnaireId = entry.resource?.id
        if (questionnaireId === undefined) continue
        const found = firstBooleanOfType(entry.resource?.item ?? [], valueTypes, valueType)
        if (found !== null) return { questionnaireId, text: found }
    }
    return null
}

/** One item of a served form, read only for what a question of a value type needs. */
interface ServedItem {
    linkId: string
    text?: string
    type: string
    code?: { system?: string; code?: string }[]
    item?: ServedItem[]
}

/** The text of the first boolean question in one item tree whose concept carries the value type. */
function firstBooleanOfType(
    items: ServedItem[],
    valueTypes: Map<string, string>,
    valueType: string,
): string | null {
    for (const item of items) {
        const coding = item.code?.[0]
        const stated = valueTypes.get(`${coding?.system ?? ''}|${coding?.code ?? ''}`)
        if (item.type === 'boolean' && stated === valueType) return item.text ?? item.linkId
        const nested = firstBooleanOfType(item.item ?? [], valueTypes, valueType)
        if (nested !== null) return nested
    }
    return null
}

test('a BOOLEAN question offers Yes, No, and not answered', async ({ page }) => {
    const opened = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${BOOLEAN_FORM}`)
    await opened

    // Unanswered is a third state rather than a hidden false: nobody has said either thing yet.
    const question = page.getByLabel(BOOLEAN_QUESTION)
    await expect(question).toBeVisible()
    await expect(page.getByText('Not answered')).toBeVisible()

    await question.click()
    await expect(page.getByText('Yes', { exact: true })).toBeVisible()

    // The No a BOOLEAN data element really stores, and the way back out of both answers.
    await question.click()
    await expect(page.getByText('No', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Unanswer' })).toBeVisible()

    // And no note about a value type that stores one answer, because this one stores two.
    await expect(page.getByText('DHIS2 stores no No for this question')).toHaveCount(0)
})

test('a TRUE_ONLY question offers a tick and nothing else', async ({ page, request }) => {
    const question = await booleanQuestionOfType(request, TRUE_ONLY)
    test.skip(
        question === null,
        'this project publishes no TRUE_ONLY question, so there is no value type to capture against',
    )
    // Narrowed for the compiler; `test.skip` above has already ended the run when it is null.
    if (question === null) return

    const opened = page.waitForResponse((response) => response.url().includes('$generate'))
    await page.goto(`/#/forms/${question.questionnaireId}`)
    await opened

    // The control is found by its own accessible state rather than by the label beside it, because
    // a form asking several boolean questions says "Not answered" once per question.
    const control = page.getByLabel(question.text)
    await expect(control).toBeVisible()
    await expect(control).toHaveAttribute('aria-checked', 'false')
    await expect(
        page.getByText('yes or not answered - DHIS2 stores no No for this question').first(),
    ).toBeVisible()

    // Two states, and the second click is the way back to the first: there is no third to reach,
    // and no Unanswer button, because the tick going off is what unanswering one of these is.
    await control.click()
    await expect(control).toHaveAttribute('aria-checked', 'true')
    await control.click()
    await expect(control).toHaveAttribute('aria-checked', 'false')
    await expect(page.getByText('No', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Unanswer' })).toHaveCount(0)
})

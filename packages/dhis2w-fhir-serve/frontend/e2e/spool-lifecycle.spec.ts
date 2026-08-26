import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, request as playwrightRequest, test } from '@playwright/test'

import { E2E_BASE_URL } from '../playwright.config.ts'

/**
 * The three drained states of the lifecycle, driven the way the two commands that write them drive them.
 *
 * No DHIS2 stands behind the fixture server, so nothing in this suite can *earn* a forwarded,
 * rejected, or withdrawn receipt - and every other spec therefore only ever sees `received`. But the
 * spool is a directory those commands mutate from another process entirely: a forward is a rename
 * into `forwarded/`, a refusal is a rename into `rejected/` plus a `<id>.report.json` beside it, a
 * withdrawal is a rename into `withdrawn/` plus the record of the delete, and the server re-reads
 * the tree on every call. So this file does exactly what they do - posts three real receipts, then
 * renames their files - and asserts the UI over the states no other path reaches: the rejected
 * tile's cause line, the filtered landing, the import-report rollup, and what a withdrawn receipt
 * says about what the instance keeps.
 *
 * The seeded files are removed afterwards, so the specs after this one meet the same spool they
 * would have without it.
 */

const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

const here = path.dirname(fileURLToPath(import.meta.url))

/** The spool of the fixture project the suite's server runs over. */
const spoolDirectory = path.join(here, '.fixture-project', '.serve', 'responses')

/** The DHIS2 error code the seeded report states, with a message quoting instance uids. */
const SEEDED_CODE = 'E1029'
const SEEDED_UID = 'aWpTgkKeXz1'
const SEEDED_MESSAGE =
    `Event \`${SEEDED_UID}\` cannot be reported for organisation unit \`O6uvpzGd5pu\`, ` +
    'which is outside the program\'s assigned units.'

let forwardedId = ''
let rejectedId = ''
let withdrawnId = ''

/** The DHIS2 event the seeded withdrawal names, and the sentence the record states about it. */
const WITHDRAWN_EVENT_UID = 'EvTsupVis01'
const WITHDRAWAL_NOTE =
    'Withdrawn. This DHIS2 instance keeps a hidden copy of the event; it no longer appears in reports. ' +
    'The UID is burned, so this receipt can never be forwarded again.'

/** Post one generated response and answer with the receipt id the server minted for it. */
async function post(seed: number): Promise<string> {
    const api = await playwrightRequest.newContext({ baseURL: E2E_BASE_URL })
    try {
        const generated = await api.get(`/Questionnaire/${AGGREGATE_FORM}/$generate?seed=${String(seed)}`, {
            headers: { Accept: FHIR_JSON },
        })
        expect(generated.status(), await generated.text()).toBe(200)
        const posted = await api.post('/QuestionnaireResponse', {
            headers: { 'Content-Type': FHIR_JSON, Accept: FHIR_JSON },
            data: await generated.json(),
        })
        expect(posted.status(), await posted.text()).toBe(201)
        return (posted.headers()['location'] ?? '').split('/').pop() ?? ''
    } finally {
        await api.dispose()
    }
}

/** Rename one received receipt into another lifecycle directory, which is all a forward run does. */
function move(responseId: string, lifecycle: 'forwarded' | 'rejected' | 'withdrawn'): void {
    const destination = path.join(spoolDirectory, lifecycle)
    fs.mkdirSync(destination, { recursive: true })
    fs.renameSync(
        path.join(spoolDirectory, 'received', `${responseId}.json`),
        path.join(destination, `${responseId}.json`),
    )
}

test.beforeAll(async () => {
    forwardedId = await post(501)
    rejectedId = await post(502)
    withdrawnId = await post(503)
    move(forwardedId, 'forwarded')
    move(rejectedId, 'rejected')
    move(withdrawnId, 'withdrawn')
    // The import report the forwarder writes beside a refusal, in `ForwardImportOutcome`'s shape.
    fs.writeFileSync(
        path.join(spoolDirectory, 'rejected', `${rejectedId}.report.json`),
        JSON.stringify({
            status: 'ERROR',
            created: 0,
            updated: 0,
            ignored: 1,
            issues: [{ error_code: SEEDED_CODE, subject: SEEDED_UID, message: SEEDED_MESSAGE }],
        }),
    )
    // The record `d2w fhir withdraw` writes beside the receipt it files, in `WithdrawalRecord`'s
    // shape - the same file name as an import report, in the one directory whose sidecar is not one.
    fs.writeFileSync(
        path.join(spoolDirectory, 'withdrawn', `${withdrawnId}.report.json`),
        JSON.stringify({
            status: 'OK',
            created: 0,
            updated: 0,
            ignored: 0,
            deleted: 1,
            event_uid: WITHDRAWN_EVENT_UID,
            withdrawn_at: '2026-08-18T08:30:00Z',
            note: WITHDRAWAL_NOTE,
        }),
    )
})

test.afterAll(() => {
    // Leave the spool as the other specs expect it: nothing forwarded, nothing rejected.
    fs.rmSync(path.join(spoolDirectory, 'forwarded', `${forwardedId}.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'rejected', `${rejectedId}.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'rejected', `${rejectedId}.report.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'withdrawn', `${withdrawnId}.json`), { force: true })
    fs.rmSync(path.join(spoolDirectory, 'withdrawn', `${withdrawnId}.report.json`), { force: true })
})

test('the rejected tile names the top cause with its instances generalised away', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('spool-rejected-count')).toHaveText('1')
    await expect(page.getByTestId('spool-forwarded-count')).toHaveText('1')

    const rejectedTile = page.getByRole('link', { name: /^Rejected/ })
    // The cause line is the code plus the message - but the message DHIS2 wrote is about one
    // event, and a tile summarising a cause must not read as that single event's story. The
    // backtick-quoted uids become ellipses.
    await expect(rejectedTile).toContainText(SEEDED_CODE)
    await expect(rejectedTile).toContainText('Event ... cannot be reported')
    await expect(rejectedTile).not.toContainText(SEEDED_UID)

    await expect(page.getByRole('link', { name: /^Forwarded/ })).toContainText('accepted by DHIS2')
})

test('the rejected tile lands on the responses already filtered to rejections', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: /^Rejected/ }).click()

    await expect(page).toHaveURL(/#\/responses\?lifecycle=rejected$/)
    await expect(page.getByRole('button', { name: /^Rejected/ })).toHaveAttribute('aria-pressed', 'true')
    const row = page.getByRole('row').filter({ hasText: rejectedId })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Rejected')
    // The received receipts the earlier specs posted are filtered out, not merely outnumbered:
    // the one rejected receipt is the only body row the table holds.
    await expect(page.getByRole('row').filter({ hasText: 'Child Health' })).toHaveCount(1)
})

test('a rejected receipt shows its badge and the import report rollup', async ({ page }) => {
    await page.goto(`/#/responses/${rejectedId}`)

    await expect(page.getByText('Rejected', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'DHIS2 refused this import' })).toBeVisible()

    // The rollup matches the seeded report: the status, the counts, and the one issue row with
    // the rule, the object, and what DHIS2 said - verbatim here, because this is the detail.
    await expect(page.getByText('ERROR', { exact: true })).toBeVisible()
    const issue = page.getByRole('row').filter({ hasText: SEEDED_CODE })
    await expect(issue).toHaveCount(1)
    await expect(issue).toContainText(SEEDED_UID)
    await expect(issue).toContainText('outside the program')
})

test('a forwarded receipt still reads back, badged as accepted', async ({ page }) => {
    await page.goto(`/#/responses/${forwardedId}`)

    await expect(page.getByText('Forwarded', { exact: true }).first()).toBeVisible()
    // No refusal section: DHIS2 took this one, so there is nothing to explain.
    await expect(page.getByRole('heading', { name: 'DHIS2 refused this import' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Answers' })).toBeVisible()
})


test('the withdrawn tile says what happened rather than that something failed', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('spool-withdrawn-count')).toHaveText('1')
    const tile = page.getByRole('link', { name: /^Withdrawn/ })
    await expect(tile).toContainText('taken back out of this DHIS2 instance')
})

test('the withdrawn tile lands on the responses already filtered to withdrawals', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: /^Withdrawn/ }).click()

    await expect(page).toHaveURL(/#\/responses\?lifecycle=withdrawn$/)
    await expect(page.getByRole('button', { name: /^Withdrawn/ })).toHaveAttribute('aria-pressed', 'true')
    const row = page.getByRole('row').filter({ hasText: withdrawnId })
    await expect(row).toHaveCount(1)
    await expect(row).toContainText('Withdrawn')
})

test('a withdrawn receipt states what the instance keeps, and still shows its answers', async ({ page }) => {
    await page.goto(`/#/responses/${withdrawnId}`)

    await expect(page.getByText('Withdrawn', { exact: true }).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Withdrawn from DHIS2' })).toBeVisible()
    // The record's own sentence, not a paraphrase, and never the bare word "deleted".
    await expect(page.getByText('keeps a hidden copy of the event')).toBeVisible()
    await expect(page.getByText(WITHDRAWN_EVENT_UID, { exact: true })).toBeVisible()
    // The receipt is untouched: retracting the data from an instance does not unsay the submission.
    await expect(page.getByRole('heading', { name: 'Answers' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'DHIS2 refused this import' })).toHaveCount(0)
})

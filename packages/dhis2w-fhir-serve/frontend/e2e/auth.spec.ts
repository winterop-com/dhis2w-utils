import { expect, test, type Page } from '@playwright/test'

/**
 * The DHIS2 posture, end to end in a browser: refused before signing in, served after.
 *
 * WHAT IS REAL HERE AND WHAT IS FULFILLED. The bundle, the shell, the sign-in panel,
 * `sessionStorage`, and every header the browser sends are the real thing, against the real
 * `d2w fhir serve --ui` this suite drives. Three answers are fulfilled: `rest.security` on
 * `/metadata`, `GET /whoami`, and the 401 the create route gives an unsigned caller.
 *
 * WHY THOSE TWO. `uiconfig.spec.ts` argues this in full and this file inherits it: the suite drives
 * ONE server process, and `[serve] auth` is a property of how a process was STARTED - one process
 * cannot be both the `none` posture every other spec here needs and the `dhis2` posture this one is
 * about. The posture also needs a live DHIS2 instance to check credentials against, and whether a
 * machine running this suite has one is a property of the machine rather than of this code. So the
 * two answers a differently-started server would give are given here, and everything the browser
 * does with them is the code under test.
 *
 * WHAT THE SERVER SIDE IS PROVED BY INSTEAD. `packages/dhis2w-fhir-serve/tests/test_serve_auth.py`
 * drives all three postures over both scopes against a real application, checks the outgoing
 * `/api/me` request carries the CALLER's header rather than the runtime's, and holds the startup
 * refusals. Nothing in this file is the only proof of anything.
 *
 * THE JWT POSTURE IS HERE ON THE SAME TERMS, and needs no identity provider to be running. What the
 * browser does with that posture is draw a paste field headed with the issuer the conformance
 * document named, and put what was pasted on the wire as a bearer token - none of which depends on
 * the token being genuine. Whether a genuine token is accepted and a forged one refused is
 * `test_serve_auth_jwt.py`'s claim, made there against real keys and real signatures.
 *
 * THE CLAIM. A person opening this facade under the DHIS2 posture is asked who they are before any
 * page is drawn; what they type is checked against the server before this tab keeps it, so a wrong
 * password is refused at the prompt rather than at the first submission; what they type is sent as
 * HTTP Basic on every request after that; the app is the app again once the server accepts it; and
 * signing out forgets the lot. Under the JWT posture they are told whose token to bring, and what
 * they paste is what leaves the tab.
 */

/** The aggregate form the fixture project publishes, which is what the gated capture answers. */
const AGGREGATE_FORM = 'BfMAe6Itzgt'

/** The credentials the person at the keyboard types, and the header they have to become. */
const USERNAME = 'clerk'
const PASSWORD = 'district-secret'
const EXPECTED_AUTHORIZATION = `Basic ${Buffer.from(`${USERNAME}:${PASSWORD}`).toString('base64')}`

/** What a `dhis2`-posture server declares in `rest.security` - `Basic` by R4's own code. */
const DHIS2_SECURITY = {
    cors: false,
    service: [
        {
            coding: [
                {
                    system: 'http://terminology.hl7.org/CodeSystem/restful-security-service',
                    code: 'Basic',
                    display: 'Basic',
                },
            ],
            text: 'Basic',
        },
        { text: 'DHIS2 personal access token' },
    ],
    description:
        'Send the credentials you would sign in to the DHIS2 instance behind this server with. ' +
        'Credentials are required to create a QuestionnaireResponse.',
}

/** The identity provider a JWT-posture server federates with, and one token a person pastes. */
const ISSUER = 'https://idp.example.org/realms/health'
const PASTED_TOKEN = 'eyJhbGciOiJSUzI1NiIsImtpZCI6InJzYS0xIn0.e30.signature'
const EXPECTED_BEARER = `Bearer ${PASTED_TOKEN}`

/** Where a `jwt`-posture server states which issuer it takes tokens from - an extension on `security`. */
const JWT_ISSUER_EXTENSION_URL =
    'https://winterop-com.github.io/dhis2w-utils/fhir/StructureDefinition/serve-jwt-issuer'

/** What a `jwt`-posture server declares in `rest.security` - `OAuth` by R4's code, plus the issuer. */
const JWT_SECURITY = {
    cors: false,
    extension: [{ url: JWT_ISSUER_EXTENSION_URL, valueString: ISSUER }],
    service: [
        {
            coding: [
                {
                    system: 'http://terminology.hl7.org/CodeSystem/restful-security-service',
                    code: 'OAuth',
                    display: 'OAuth',
                },
            ],
            text: 'JWT bearer token',
        },
    ],
    description: `Send a token from ${ISSUER}, as \`Authorization: Bearer <token>\`.`,
}

/** What the server answers a caller it does not know, on the one address a `write` scope guards. */
const UNAUTHENTICATED_OUTCOME = {
    resourceType: 'OperationOutcome',
    issue: [
        {
            severity: 'error',
            code: 'login',
            diagnostics: 'this server takes no request without an `Authorization` header',
        },
    ],
}

/** Serve `/metadata` with the security element a DHIS2-posture server would carry. */
async function serveDhis2Posture(page: Page): Promise<void> {
    await servePosture(page, DHIS2_SECURITY)
}

/** Serve `/metadata` with the security element a JWT-posture server would carry, issuer and all. */
async function serveJwtPosture(page: Page): Promise<void> {
    await servePosture(page, JWT_SECURITY)
}

/** Answer `/metadata` from the real server, with one element rewritten to the posture under test. */
async function servePosture(page: Page, security: unknown): Promise<void> {
    await page.route('**/metadata', async (route) => {
        const answered = await route.fetch()
        const statement = (await answered.json()) as { rest?: { security?: unknown }[] }
        if (statement.rest?.[0]) statement.rest[0].security = security
        await route.fulfill({
            status: 200,
            contentType: 'application/fhir+json',
            body: JSON.stringify(statement),
        })
    })
}

/**
 * Answer `GET /whoami` the way a posture-configured server would: 401 unless the credential is the one.
 *
 * This is the address the sign-in panel asks before it keeps anything, so the credential the browser
 * puts on it is the credential a person typed - which makes the fulfilment a check of the very thing
 * under test rather than a stand-in for it. `username` is what the server says the caller is called,
 * and the panel is required to keep that rather than what was typed into the box.
 */
async function nameTheCaller(
    page: Page,
    accepted: string,
    named: { posture: string; username: string | null; name: string },
): Promise<void> {
    await page.route('**/whoami', async (route) => {
        const credential = await route.request().headerValue('authorization')
        const refused = credential !== accepted
        await route.fulfill({
            status: refused ? 401 : 200,
            contentType: refused ? 'application/fhir+json' : 'application/json',
            headers: refused ? { 'WWW-Authenticate': 'xBasic realm="d2w fhir serve"' } : {},
            body: JSON.stringify(refused ? UNAUTHENTICATED_OUTCOME : named),
        })
    })
}

/** What an accepted capture answers with, which is all the form screen reads off a 201. */
const ACCEPTED_OUTCOME = {
    resourceType: 'OperationOutcome',
    issue: [{ severity: 'information', code: 'informational', diagnostics: 'stored as `receipt-auth-spec`' }],
}

/**
 * Guard the create route the way a `write` scope does: 401 without the credential, 201 with it.
 *
 * The header the browser sends is recorded rather than assumed - that a signed-in tab actually puts
 * the typed credentials on the wire is the whole of what this file is here to prove.
 *
 * NEITHER OUTCOME REACHES THE SPOOL, and that is deliberate. The suite drives one server process
 * over one spool, and several specs assert on what is in it - `playwright.config.ts` says so and
 * runs the files in order because of it. This file's subject is what the browser does with a
 * credential, so it stops at the wire; the receipt reaching the spool is `capture.spec.ts`'s claim
 * and is made there against a server nothing has fulfilled.
 */
async function guardTheCapture(page: Page, sent: string[], accepted: string = EXPECTED_AUTHORIZATION): Promise<void> {
    await page.route('**/QuestionnaireResponse', async (route) => {
        if (route.request().method() !== 'POST') {
            await route.continue()
            return
        }
        const credential = await route.request().headerValue('authorization')
        sent.push(credential ?? '')
        const refused = credential !== accepted
        await route.fulfill({
            status: refused ? 401 : 201,
            contentType: 'application/fhir+json',
            headers: refused
                ? { 'WWW-Authenticate': 'Bearer realm="d2w fhir serve"' }
                : { Location: '/QuestionnaireResponse/receipt-auth-spec' },
            body: JSON.stringify(refused ? UNAUTHENTICATED_OUTCOME : ACCEPTED_OUTCOME),
        })
    })
}

test('a DHIS2-posture facade asks who this is, and is the app again once it knows', async ({ page }) => {
    const sent: string[] = []
    await serveDhis2Posture(page)
    await nameTheCaller(page, EXPECTED_AUTHORIZATION, { posture: 'dhis2', username: USERNAME, name: USERNAME })
    await guardTheCapture(page, sent)

    // Before signing in: the shell is there, and the panel is in place of the page.
    await page.goto('/#/forms')
    await expect(page.getByText('This server takes your DHIS2 credentials')).toBeVisible()
    // The shell's own header still names the section - it is the frame, not the page. What is not
    // there is the listing, because the read that would fill it was never made.
    await expect(page.getByRole('link').filter({ hasText: 'Child Health' })).toHaveCount(0)

    // What the panel keeps is a tab's credential, and it says so where a person can read it.
    await expect(page.getByText('this browser tab only')).toBeVisible()

    await page.getByLabel('DHIS2 username').fill(USERNAME)
    await page.getByLabel('DHIS2 password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()

    // After signing in: the page is drawn, and the header names who is signed in.
    await expect(page.getByText('This server takes your DHIS2 credentials')).toHaveCount(0)
    await expect(page.getByText(USERNAME)).toBeVisible()

    // And a capture goes through, carrying exactly what was typed.
    await page.goto(`/#/forms/${AGGREGATE_FORM}`)
    await page.getByRole('button', { name: 'Fill with test data' }).click()
    await expect(page.getByText('Filled with test data')).toBeVisible()
    await page.getByRole('button', { name: 'Submit' }).click()

    await expect(page.getByText('The server accepted this submission')).toBeVisible()
    expect(sent.at(-1)).toBe(EXPECTED_AUTHORIZATION)
})

test('a wrong password is refused at the prompt, before anything is filled in', async ({ page }) => {
    const sent: string[] = []
    await serveDhis2Posture(page)
    await nameTheCaller(page, EXPECTED_AUTHORIZATION, { posture: 'dhis2', username: USERNAME, name: USERNAME })
    await guardTheCapture(page, sent)

    await page.goto('/#/forms')
    await page.getByLabel('DHIS2 username').fill(USERNAME)
    await page.getByLabel('DHIS2 password').fill('not-the-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    // The refusal is on the panel, the fields are still there to try again with, and nothing was
    // kept - which is the whole point of asking before storing.
    await expect(page.getByText('This DHIS2 instance did not accept this username and password.')).toBeVisible()
    await expect(page.getByLabel('DHIS2 password')).toBeVisible()
    expect(await page.evaluate(() => sessionStorage.getItem('d2w-fhir-serve-authorization'))).toBeNull()

    // And the right password gets through, on the same panel, with nothing reloaded.
    await page.getByLabel('DHIS2 password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByText('This server takes your DHIS2 credentials')).toHaveCount(0)
    await expect(page.getByText(USERNAME)).toBeVisible()
})

test('a credential this server refuses brings the prompt back, wherever the refusal was met', async ({ page }) => {
    const sent: string[] = []
    await serveDhis2Posture(page)
    await nameTheCaller(page, EXPECTED_AUTHORIZATION, { posture: 'dhis2', username: USERNAME, name: USERNAME })
    await guardTheCapture(page, sent)

    // A tab holding a credential the server no longer accepts - a password changed, an account
    // disabled. The app opens as the app, because nothing has been refused yet: the check at the
    // prompt cannot cover a credential that went stale after somebody signed in.
    await page.addInitScript(() => {
        sessionStorage.setItem('d2w-fhir-serve-authorization', 'Basic d3JvbmM6d3Jvbmc=')
        sessionStorage.setItem('d2w-fhir-serve-identity', 'someone-else')
    })
    await page.goto(`/#/forms/${AGGREGATE_FORM}`)
    await expect(page.getByRole('button', { name: 'Fill with test data' })).toBeVisible()

    await page.getByRole('button', { name: 'Fill with test data' }).click()
    await expect(page.getByText('Filled with test data')).toBeVisible()
    await page.getByRole('button', { name: 'Submit' }).click()

    // The 401 the submission met is what asks again, and it says the credentials were not accepted.
    // The submission's own error path is what runs here - which it can only do because the server's
    // challenge names a scheme the browser hands back instead of intercepting.
    await expect(page.getByText('This DHIS2 instance did not accept this username and password.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    expect(sent.at(-1)).toBe('Basic d3JvbmM6d3Jvbmc=')
})

test('signing out forgets the credential and asks again', async ({ page }) => {
    const sent: string[] = []
    await serveDhis2Posture(page)
    await nameTheCaller(page, EXPECTED_AUTHORIZATION, { posture: 'dhis2', username: USERNAME, name: USERNAME })
    await guardTheCapture(page, sent)

    await page.goto('/#/forms')
    await page.getByLabel('DHIS2 username').fill(USERNAME)
    await page.getByLabel('DHIS2 password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByText(USERNAME)).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page.getByText('This server takes your DHIS2 credentials')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0)
    expect(await page.evaluate(() => sessionStorage.getItem('d2w-fhir-serve-authorization'))).toBeNull()
    expect(await page.evaluate(() => sessionStorage.getItem('d2w-fhir-serve-identity'))).toBeNull()
})


test('a JWT-posture facade names the issuer to get a token from, and sends what was pasted', async ({ page }) => {
    const sent: string[] = []
    await serveJwtPosture(page)
    await nameTheCaller(page, EXPECTED_BEARER, { posture: 'jwt', username: USERNAME, name: USERNAME })
    await guardTheCapture(page, sent, EXPECTED_BEARER)

    // Before signing in: one field, headed with the issuer, because a person told to bring a token
    // cannot bring one without being told whose.
    await page.goto('/#/forms')
    await expect(page.getByText(`This server takes a token from ${ISSUER}`)).toBeVisible()
    await expect(page.getByLabel('Token')).toBeVisible()
    await expect(page.getByLabel('DHIS2 username')).toHaveCount(0)

    // And the panel says whose business getting one is, and how long this tab keeps it.
    await expect(page.getByText('identity provider')).toBeVisible()
    await expect(page.getByText('this browser tab only')).toBeVisible()

    await page.getByLabel('Token').fill(PASTED_TOKEN)
    await page.getByRole('button', { name: 'Sign in' }).click()

    // After signing in: the page is drawn, and the person named is the one the SERVER read out of
    // the token at `/whoami` - never one this browser decided for itself by opening the token.
    await expect(page.getByText(`This server takes a token from ${ISSUER}`)).toHaveCount(0)
    await expect(page.getByText(USERNAME)).toBeVisible()

    // And a capture goes through, carrying exactly what was pasted, as a bearer token.
    await page.goto(`/#/forms/${AGGREGATE_FORM}`)
    await page.getByRole('button', { name: 'Fill with test data' }).click()
    await expect(page.getByText('Filled with test data')).toBeVisible()
    await page.getByRole('button', { name: 'Submit' }).click()

    await expect(page.getByText('The server accepted this submission')).toBeVisible()
    expect(sent.at(-1)).toBe(EXPECTED_BEARER)
})

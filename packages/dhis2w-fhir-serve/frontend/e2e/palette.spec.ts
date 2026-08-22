import { expect, request as playwrightRequest, test, type Page } from '@playwright/test'

import { E2E_BASE_URL } from '../playwright.config.ts'

/**
 * The command palette and the themes, against the real bundle the server ships.
 *
 * TWO THINGS HERE CANNOT BE TESTED ANYWHERE ELSE. The first is the shortcut: whether Ctrl+K reaches
 * a window listener and opens a dialog is a fact about a browser, not about a component. The second
 * is the palette of every theme, which only exists once a real stylesheet has been parsed and the
 * custom properties resolved - a unit test can prove that each theme block DECLARES every token
 * (lib/theme.test.ts does), and only a browser can say what those declarations come out as.
 *
 * THE CONTRAST CASE IS THE ONE THAT EARNS ITS RUNTIME. Five themes times two grounds is ten
 * palettes, each with about thirty colour pairs in it, and no reviewer opens twenty screenshots. So
 * the pairs are measured: each token is painted into a one-pixel canvas, which is what turns an
 * `oklch()` declaration into the sRGB bytes a screen actually shows, and the two are put through the
 * WCAG contrast formula. A theme whose muted text washes out on its own card fails here rather than
 * on somebody's laptop.
 */

/** Which themes exist, in the order the picker offers them. Mirrors `THEMES` in lib/theme.ts. */
const THEME_NAMES = ['clinical', 'indigo', 'paper', 'contrast', 'terminal'] as const

/**
 * The contrast one pair has to reach, by what the pair is for.
 *
 * NOT ONE NUMBER, BECAUSE THESE ARE NOT ONE KIND OF THING. Body text on its surface is held near the
 * top of the scale because it is what a form is read in; a status chip's tint is held at 3, which is
 * WCAG's own floor for a graphical element, because it is a coloured dot and a short word on a
 * ground already tinted with the same hue. Every number here sits below what the shipped themes
 * actually measure, so this fails on a theme that is worse than the ones in the repository rather
 * than on the ones in it.
 */
const FLOORS = {
    body: 12,
    muted: 5,
    identity: 4.5,
    accent: 9,
    status: 3,
    code: 4,
} as const

/** Every pair measured, as [ink, ground, floor]. */
const PAIRS: [string, string, number][] = [
    ['foreground', 'background', FLOORS.body],
    ['card-foreground', 'card', FLOORS.body],
    ['popover-foreground', 'popover', FLOORS.body],
    ['sidebar-foreground', 'sidebar', FLOORS.body],
    ['secondary-foreground', 'secondary', FLOORS.body],
    ['muted-foreground', 'background', FLOORS.muted],
    ['muted-foreground', 'card', FLOORS.muted],
    ['primary-foreground', 'primary', FLOORS.identity],
    ['primary', 'background', FLOORS.identity],
    ['accent-foreground', 'accent', FLOORS.accent],
    ['sidebar-accent-foreground', 'sidebar-accent', FLOORS.accent],
    ['status-received', 'card', FLOORS.status],
    ['status-forwarded', 'card', FLOORS.status],
    ['status-rejected', 'card', FLOORS.status],
    ['status-withdrawn', 'card', FLOORS.status],
    ['status-refused', 'card', FLOORS.status],
    ['destructive', 'card', FLOORS.status],
    ['code-keyword', 'card', FLOORS.code],
    ['code-operator', 'card', FLOORS.code],
    ['code-string', 'card', FLOORS.code],
    ['code-number', 'card', FLOORS.code],
    ['code-literal', 'card', FLOORS.code],
    ['code-comment', 'card', FLOORS.code],
    ['code-variable', 'card', FLOORS.code],
    ['code-type', 'card', FLOORS.code],
    ['code-property', 'card', FLOORS.code],
    ['code-punctuation', 'card', FLOORS.code],
]

/** A form the fixture project publishes, used to mint a receipt for the prefix case. */
const AGGREGATE_FORM = 'BfMAe6Itzgt'
const FHIR_JSON = 'application/fhir+json'

/** Post one generated response and answer with the receipt id the server minted for it. */
async function postReceipt(): Promise<string> {
    const api = await playwrightRequest.newContext({ baseURL: E2E_BASE_URL })
    try {
        const generated = await api.get(`/Questionnaire/${AGGREGATE_FORM}/$generate?seed=901`, {
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

/** Open the palette the way a person does, and wait until it is actually there. */
async function openPalette(page: Page): Promise<void> {
    await page.keyboard.press('Control+k')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()
}

test('Ctrl+K opens the palette, and typing a page name goes there', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)

    // The pages shelf is drawn from the same table the rail is, so what is on it is what this run
    // offers - not a second list that can drift from the first.
    await expect(page.getByRole('option', { name: /^Evaluate/ })).toBeVisible()

    await page.getByRole('combobox', { name: 'Command palette' }).fill('evalu')
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/#\/evaluate$/)
    await expect(page.getByRole('heading', { name: 'Evaluate', level: 2 })).toBeVisible()
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeHidden()
})

test('the same chord closes it again, and Escape does too', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)
    await page.keyboard.press('Control+k')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeHidden()

    await openPalette(page)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeHidden()
})

test('the header button opens the same palette, for anyone not told about the chord', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Command palette' }).click()
    await expect(page.getByRole('dialog', { name: 'Command palette' })).toBeVisible()
})

test('the forms shelf is the guide this server loaded, and a row opens the form', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)

    // The fixture project publishes this one. The palette reads `/Questionnaire` when it is first
    // opened, so the row appearing at all is the read having landed.
    const row = page.getByRole('option', { name: /Antenatal care/ })
    await expect(row).toBeVisible()
    await row.click()

    await expect(page).toHaveURL(/#\/forms\/PrAncCare01$/)
})

test('a typed receipt id prefix jumps to that receipt', async ({ page }) => {
    // Posted by this spec rather than read off whatever the spool happens to hold: a receipt id is
    // what the case is about, and a file run on its own would otherwise assert over an empty spool.
    const receiptId = await postReceipt()
    expect(receiptId).not.toBe('')

    await page.goto('/#/responses')
    await expect(page.getByRole('heading', { name: 'Responses', level: 2 })).toBeVisible()

    await openPalette(page)
    await page.getByRole('combobox', { name: 'Command palette' }).fill(receiptId.slice(0, 6))
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(new RegExp(`#/responses/${receiptId}$`))
})

test('a theme chosen in the palette is painted, and is still painted after a reload', async ({ page }) => {
    await page.goto('/')
    await openPalette(page)

    await page.getByRole('combobox', { name: 'Command palette' }).fill('Terminal theme')
    await page.keyboard.press('Enter')

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'terminal')

    // The attribute is written before the first paint by the inline script in index.html, off the
    // same storage key lib/theme.ts writes. If those two ever disagree, this reload shows Clinical.
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'terminal')

    // Put it back, so the specs after this one meet the theme every other spec assumes.
    await page.evaluate(() => {
        localStorage.removeItem('d2w-fhir.theme')
    })
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'clinical')
})

test('the header picker offers every theme and marks the one in force', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Theme' }).click()

    await Promise.all(
        ['Clinical', 'Indigo', 'Paper', 'Contrast', 'Terminal'].map((label) =>
            expect(page.getByRole('menuitemradio', { name: new RegExp(`^${label}`) })).toBeVisible(),
        ),
    )
    await expect(page.getByRole('menuitemradio', { name: /^Clinical/ })).toHaveAttribute(
        'aria-checked',
        'true',
    )
})

test('every theme stays legible on both grounds', async ({ page }) => {
    await page.goto('/')

    const measured = await page.evaluate(
        ({ themes, pairs }) => {
            const root = document.documentElement
            const wasTheme = root.getAttribute('data-theme')
            const wasDark = root.classList.contains('dark')

            // A one-pixel canvas is what turns an `oklch()` declaration into the sRGB bytes a screen
            // shows. Reading the computed property gives the declaration back verbatim, which no
            // contrast formula takes.
            const canvas = document.createElement('canvas')
            canvas.width = 1
            canvas.height = 1
            const context = canvas.getContext('2d', { willReadFrequently: true })
            if (context === null) throw new Error('this browser gave no 2d context')

            const channels = (colour: string): [number, number, number] => {
                context.clearRect(0, 0, 1, 1)
                context.fillStyle = '#000000'
                context.fillStyle = colour
                context.fillRect(0, 0, 1, 1)
                const pixel = context.getImageData(0, 0, 1, 1).data
                return [pixel[0], pixel[1], pixel[2]]
            }
            // sRGB relative luminance, WCAG 2's own formula, with the gamma step inlined per
            // channel rather than named: a helper here would be a function this file is told to
            // hoist out of the browser, which is the one place it cannot go.
            const luminance = (colour: string): number => {
                const weights = [0.2126, 0.7152, 0.0722]
                let total = 0
                let index = 0
                for (const raw of channels(colour)) {
                    const scaled = raw / 255
                    total +=
                        weights[index] *
                        (scaled <= 0.03928 ? scaled / 12.92 : Math.pow((scaled + 0.055) / 1.055, 2.4))
                    index += 1
                }
                return total
            }
            const contrast = (ink: string, ground: string): number => {
                const lit = Math.max(luminance(ink), luminance(ground))
                const dim = Math.min(luminance(ink), luminance(ground))
                return (lit + 0.05) / (dim + 0.05)
            }

            const failures: string[] = []
            for (const theme of themes) {
                for (const mode of ['light', 'dark']) {
                    root.setAttribute('data-theme', theme)
                    root.classList.toggle('dark', mode === 'dark')
                    const styles = getComputedStyle(root)
                    for (const [ink, ground, floor] of pairs) {
                        const ratio = contrast(
                            styles.getPropertyValue(`--${ink}`).trim(),
                            styles.getPropertyValue(`--${ground}`).trim(),
                        )
                        if (ratio < floor) {
                            failures.push(
                                `${theme}.${mode} ${ink} on ${ground}: ${ratio.toFixed(2)} < ${String(floor)}`,
                            )
                        }
                    }
                }
            }

            root.setAttribute('data-theme', wasTheme ?? 'clinical')
            root.classList.toggle('dark', wasDark)
            return failures
        },
        { themes: [...THEME_NAMES], pairs: PAIRS },
    )

    expect(measured, measured.join('\n')).toEqual([])
})

test('a theme change repaints the organisation-unit map with nothing reloaded', async ({ page }) => {
    await page.goto('/#/organisation-units')
    const map = page.getByTestId('org-unit-map')
    await expect(map).toHaveAttribute('data-map-ready', 'true', { timeout: 15_000 })

    // The map paints from the same tokens as the rest of the app, and it watches `<html>` for both
    // axes - the light/dark class and the theme attribute. Watching only the class would leave the
    // boundaries in the previous theme's colours until the ground happened to flip.
    const before = await map.getAttribute('data-map-theme')
    await page.getByRole('button', { name: 'Theme' }).click()
    await page.getByRole('menuitemradio', { name: /^Terminal/ }).click()

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'terminal')
    // The ground did not change, so the map's own light/dark marker must not have either - what has
    // to have happened is a repaint, which the marker cannot show. That it is still painted at all
    // is what this asserts: a rebuild that threw would leave the canvas without it.
    await expect(map).toHaveAttribute('data-map-theme', before ?? 'light')
    await expect(map).toHaveAttribute('data-map-ready', 'true')

    await page.evaluate(() => {
        localStorage.removeItem('d2w-fhir.theme')
    })
})

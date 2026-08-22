import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The two files that hold the other halves of the theme mechanism, read as text. `?raw` rather than
// `node:fs` because these tests belong to the browser tsconfig, which has no Node types and should
// not gain any: nothing in `src/` is allowed to reach the filesystem, and a test in `src/` that did
// would be the first thing to make that untrue.
import indexHtml from '../../index.html?raw'
import indexCss from '@/index.css?raw'

import { FORM_TYPES } from '@/lib/fhir'
import {
    chooseTheme,
    DEFAULT_THEME_NAME,
    isThemeName,
    initialiseTheme,
    storedThemeName,
    subscribeToTheme,
    THEME_ATTRIBUTE,
    THEME_NAMES,
    THEME_STORAGE_KEY,
    themeByName,
    themeLabel,
    themeSnapshot,
    THEMES,
} from '@/lib/theme'

/**
 * The theme store: what is written, what is read back, and what an unknown name does.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The theme is the one piece of state in this app that is
 * decided twice - once by a script in index.html before the first paint, and once by this module as
 * React mounts - and the two have to reach the same answer off the same storage key or every load
 * flashes one theme under another. So the storage key, the fallback, and the attribute written are
 * all asserted here, and the last case in this file reads index.html itself and checks the name list
 * in it against the one this module holds.
 *
 * The document is stubbed rather than emulated. What `applyTheme` does is set one attribute on one
 * element, and a recorder is a truer subject than a DOM implementation would be: it says exactly
 * which attribute got which value.
 */

/** What the stubbed document was told to write. */
let written: { attribute: string; value: string }[] = []

/**
 * A storage of the two methods this module uses, and nothing else.
 *
 * Node has no `localStorage` without being told where to keep one, and a file on disk is not what
 * these tests are about. What is under test is which key is written and what an unreadable one falls
 * back to, and a Map answers both.
 */
function inMemoryStorage(): Storage {
    const entries = new Map<string, string>()
    return {
        getItem: (key: string) => entries.get(key) ?? null,
        setItem: (key: string, value: string) => {
            entries.set(key, value)
        },
        removeItem: (key: string) => {
            entries.delete(key)
        },
        clear: () => {
            entries.clear()
        },
        key: (index: number) => [...entries.keys()][index] ?? null,
        get length() {
            return entries.size
        },
    }
}

beforeEach(() => {
    written = []
    vi.stubGlobal('localStorage', inMemoryStorage())
    vi.stubGlobal('document', {
        documentElement: {
            setAttribute: (attribute: string, value: string) => {
                written.push({ attribute, value })
            },
        },
    })
})

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('the themes this app has', () => {
    it('offers five, each with a name, a label, and a line about what it looks like', () => {
        expect(THEMES).toHaveLength(5)
        for (const theme of THEMES) {
            expect(theme.name).toMatch(/^[a-z]+$/)
            expect(theme.label.length).toBeGreaterThan(0)
            expect(theme.hint.length).toBeGreaterThan(0)
        }
    })

    it('starts in the one the base palette in index.css already is', () => {
        // Clinical is written as the bare `:root` and `.dark` blocks rather than as a `data-theme`
        // block of its own, so a document carrying no attribute at all is still a whole palette.
        expect(DEFAULT_THEME_NAME).toBe('clinical')
        expect(THEMES[0].name).toBe(DEFAULT_THEME_NAME)
    })

    it('names them all distinctly, because the name is both the stored value and the selector', () => {
        expect(new Set(THEME_NAMES).size).toBe(THEME_NAMES.length)
    })

    it('says nothing theatrical in a label: each is a plain noun, not a sentence', () => {
        for (const theme of THEMES) {
            expect(theme.label).not.toMatch(/^The /)
            expect(theme.label.split(' ')).toHaveLength(1)
        }
    })
})

describe('reading a name', () => {
    it('recognises every theme it has', () => {
        for (const name of THEME_NAMES) expect(isThemeName(name)).toBe(true)
    })

    it('refuses a name it does not have, and refuses nothing at all', () => {
        expect(isThemeName('solarized')).toBe(false)
        expect(isThemeName(null)).toBe(false)
    })

    it('reads an unknown name as the default rather than as an error', () => {
        // A value from a build that had a theme this one does not, or a hand-edited storage entry.
        // Neither is worth a screen; both are worth the theme everything starts in.
        expect(themeByName('solarized').name).toBe(DEFAULT_THEME_NAME)
        expect(themeByName(null).name).toBe(DEFAULT_THEME_NAME)
        expect(themeLabel('solarized')).toBe('Clinical')
    })

    it('reads a name it has as that theme', () => {
        expect(themeByName('terminal').label).toBe('Terminal')
    })
})

describe('what this browser last chose', () => {
    it('is the default when nothing has been stored', () => {
        expect(storedThemeName()).toBe(DEFAULT_THEME_NAME)
    })

    it('is what was stored, when what was stored is a theme this app has', () => {
        localStorage.setItem(THEME_STORAGE_KEY, 'paper')
        expect(storedThemeName()).toBe('paper')
    })

    it('is the default when what was stored is not a theme this app has', () => {
        localStorage.setItem(THEME_STORAGE_KEY, 'solarized')
        expect(storedThemeName()).toBe(DEFAULT_THEME_NAME)
    })
})

describe('choosing one', () => {
    it('persists it, paints it, and reports it', () => {
        chooseTheme('indigo')
        expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('indigo')
        expect(written).toEqual([{ attribute: THEME_ATTRIBUTE, value: 'indigo' }])
        expect(themeSnapshot()).toBe('indigo')
    })

    it('falls back to the default for a name this app does not have, and stores that', () => {
        // Nothing that calls this has to hold a valid name to call it safely - the same rule
        // `themeByName` follows, applied at the write end as well as the read end.
        expect(chooseTheme('solarized')).toBe(DEFAULT_THEME_NAME)
        expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe(DEFAULT_THEME_NAME)
        expect(written).toEqual([{ attribute: THEME_ATTRIBUTE, value: DEFAULT_THEME_NAME }])
    })

    it('tells every subscriber', () => {
        let told = 0
        const stop = subscribeToTheme(() => {
            told += 1
        })
        chooseTheme('terminal')
        chooseTheme('paper')
        stop()
        chooseTheme('contrast')
        expect(told).toBe(2)
    })

    it('brings the store into step with what was stored, on mount', () => {
        localStorage.setItem(THEME_STORAGE_KEY, 'contrast')
        expect(initialiseTheme()).toBe('contrast')
        expect(themeSnapshot()).toBe('contrast')
    })
})

describe('the pre-paint script in index.html', () => {
    it('knows exactly the themes this module knows', () => {
        // The script cannot import anything - it runs before the first module is fetched - so the
        // names are written out there a second time. This is what keeps the two copies honest: a
        // theme added here and not there would silently fall back to the default on every load, and
        // one added there and not here would be a name nothing can choose.
        const html = indexHtml
        const declared = /var known = \[([^\]]+)\]/.exec(html)
        expect(declared, 'index.html no longer declares a `known` theme list').not.toBeNull()
        const names = [...(declared?.[1] ?? '').matchAll(/'([a-z]+)'/g)].map((match) => match[1])
        expect(names).toEqual(THEME_NAMES)
    })

    it('reads the same storage key this module writes', () => {
        const html = indexHtml
        expect(html).toContain(`localStorage.getItem('${THEME_STORAGE_KEY}')`)
    })

    it('writes the same attribute this module writes, and defaults to the same theme', () => {
        const html = indexHtml
        expect(html).toContain(`setAttribute('${THEME_ATTRIBUTE}', chosen)`)
        expect(html).toContain(`var chosen = '${DEFAULT_THEME_NAME}'`)
    })
})

describe('every theme paints every token', () => {
    /**
     * The completeness rule, read straight off the stylesheet.
     *
     * A theme that repainted the surfaces and left `--code-string` behind would put Clinical's green
     * inside Terminal's editor, where the surface is already green. That failure is invisible in a
     * screenshot of the page a reviewer happens to open, and obvious here.
     *
     * THE RULE APPLIES TO THE LITERAL TOKENS, WHICH IS ALL THERE IS TO LEAVE BEHIND. `:root` also
     * declares a derived layer - tokens written in terms of other tokens - and those are stated once
     * for the whole app: `--status-rejected: var(--critical)` is Contrast's critical under Contrast
     * because a `var()` in a custom property resolves against the element it lands on, and every one
     * of these lands on the same `<html>` a theme block paints. A theme cannot forget one of those,
     * so requiring it to restate them would be requiring duplication rather than completeness.
     */
    const css = indexCss

    /** What one block declares, given the selector that opens it, as token to value. */
    const declarationsUnder = (selector: string): Map<string, string> => {
        const opened = css.indexOf(`${selector} {`)
        expect(opened, `index.css declares no block for ${selector}`).toBeGreaterThan(-1)
        const closed = css.indexOf('\n}', opened)
        const block = css.slice(opened, closed)
        return new Map(
            [...block.matchAll(/^\s+(--[a-z0-9-]+):\s*([^;]+);/gm)].map((match) => [
                match[1],
                match[2].trim(),
            ]),
        )
    }

    /** The tokens declared in one block, in a stable order. */
    const tokensUnder = (selector: string): string[] => [...declarationsUnder(selector).keys()].toSorted()

    const baseDeclarations = declarationsUnder(':root')
    /** A token written in terms of another token - the derived layer, stated once for every theme. */
    const derived = [...baseDeclarations]
        .filter(([, value]) => value.includes('var('))
        .map(([token]) => token)
    const base = [...baseDeclarations.keys()]
        .filter((token) => token !== '--radius' && !derived.includes(token))
        .toSorted()

    /** What one theme block declares, minus any derived token it has chosen to override. */
    const paletteUnder = (selector: string): string[] =>
        tokensUnder(selector).filter((token) => !derived.includes(token))

    for (const theme of THEMES) {
        if (theme.name === DEFAULT_THEME_NAME) continue

        it(`${theme.label} states the whole palette on the light ground`, () => {
            expect(paletteUnder(`html[data-theme='${theme.name}']`)).toEqual(base)
        })

        it(`${theme.label} states the whole palette on the dark ground`, () => {
            expect(paletteUnder(`html.dark[data-theme='${theme.name}']`)).toEqual(base)
        })
    }

    it('leaves the geometry alone: no theme redeclares the radius', () => {
        // One `--radius`, and every step derived from it, so the whole surface rescales from a
        // single number. A theme that changed it would be a second design rather than a palette.
        for (const theme of THEMES) {
            if (theme.name === DEFAULT_THEME_NAME) continue
            expect(tokensUnder(`html[data-theme='${theme.name}']`)).not.toContain('--radius')
        }
    })

    it('has a derived layer, and every token it is derived from is one every theme paints', () => {
        // The whole mechanism: a derivation is correct in five themes only if what it names is
        // repainted by five themes. A derived token that reached for something declared nowhere -
        // or for a literal - would be a colour one theme cannot move.
        expect(derived.length).toBeGreaterThan(0)
        const known = new Set([...base, ...derived])
        for (const token of derived) {
            const value = baseDeclarations.get(token) ?? ''
            for (const [, named] of value.matchAll(/var\((--[a-z0-9-]+)\)/g)) {
                expect(known, `${token} is derived from ${named}, which index.css declares nowhere`)
                    .toContain(named)
            }
        }
    })

    it('states the semantic set at the base, so a theme that said nothing would still have states', () => {
        // good / critical / warning / info are what a state MEANS. They are palette tokens - every
        // theme states its own four - and everything that carries a state is derived from them.
        for (const token of ['--good', '--critical', '--warning', '--info']) {
            expect(base).toContain(token)
        }
        for (const token of [
            '--status-received',
            '--status-forwarded',
            '--status-rejected',
            '--status-refused',
            '--status-in-progress',
            '--status-completed',
        ]) {
            expect(derived, `${token} should read the semantic set rather than a colour of its own`)
                .toContain(token)
        }
    })

    it('paints every form kind this app has, and no kind it does not', () => {
        // The badge's `data-form-kind` carries the `FormType` code verbatim, so a kind added to the
        // union without a tint here would render as an unstyled pill - which looks like a bug in the
        // form rather than a gap in the stylesheet. `none` is the sixth rule and not a sixth kind:
        // it is what a form declaring no D2FormType wears.
        const painted = [...css.matchAll(/\.kind-badge\[data-form-kind='([a-z-]+)'\]/g)].map(
            (match) => match[1],
        )
        expect(painted.toSorted()).toEqual([...FORM_TYPES, 'none'].toSorted())
        for (const kind of FORM_TYPES) {
            expect(derived).toContain(`--kind-${kind}`)
            expect(derived).toContain(`--kind-${kind}-surface`)
        }
    })

    it('ranks the dark block above its light sibling by specificity, not by source order', () => {
        // `html.dark[data-theme]` carries one class more than `html[data-theme]`, so the dark
        // palette wins wherever both match however the blocks are ordered in the file. Written as
        // `.dark[data-theme]` the two would tie and only document order would settle it.
        for (const theme of THEMES) {
            if (theme.name === DEFAULT_THEME_NAME) continue
            expect(css).toContain(`html.dark[data-theme='${theme.name}'] {`)
        }
    })
})

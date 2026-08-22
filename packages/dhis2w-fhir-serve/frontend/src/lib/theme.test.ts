import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The two files that hold the other halves of the theme mechanism, read as text. `?raw` rather than
// `node:fs` because these tests belong to the browser tsconfig, which has no Node types and should
// not gain any: nothing in `src/` is allowed to reach the filesystem, and a test in `src/` that did
// would be the first thing to make that untrue.
import indexHtml from '../../index.html?raw'
import indexCss from '@/index.css?raw'

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
     */
    const css = indexCss

    /** The tokens declared in one block, given the selector that opens it. */
    const tokensUnder = (selector: string): string[] => {
        const opened = css.indexOf(`${selector} {`)
        expect(opened, `index.css declares no block for ${selector}`).toBeGreaterThan(-1)
        const closed = css.indexOf('\n}', opened)
        const block = css.slice(opened, closed)
        return [...block.matchAll(/^\s+(--[a-z0-9-]+):/gm)].map((match) => match[1]).toSorted()
    }

    const base = tokensUnder(':root').filter((token) => token !== '--radius')

    for (const theme of THEMES) {
        if (theme.name === DEFAULT_THEME_NAME) continue

        it(`${theme.label} states the whole palette on the light ground`, () => {
            expect(tokensUnder(`html[data-theme='${theme.name}']`)).toEqual(base)
        })

        it(`${theme.label} states the whole palette on the dark ground`, () => {
            expect(tokensUnder(`html.dark[data-theme='${theme.name}']`)).toEqual(base)
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

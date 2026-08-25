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

/**
 * THE NEUTRAL LADDER, COMPUTED RATHER THAN LOOKED AT.
 *
 * The complaint this answers is that the surfaces were all one surface: a card barely off the page,
 * a border nobody could see, and three greys of text per row that nobody could tell apart. Every one
 * of those is a NUMBER, and every one of them drifts back toward flat the moment somebody nudges a
 * lightness to make one screen look nicer - which is exactly the change that looks fine in the
 * screenshot the author takes and is wrong in nine other palettes.
 *
 * So the floors are asserted here, in every theme and on both grounds, off the stylesheet itself.
 * The colours are oklch, which is not a space a ratio can be read out of, so this converts through
 * oklab to linear sRGB and takes the WCAG relative luminance from there - the same arithmetic a
 * browser does, written out once.
 *
 * WHAT EACH FLOOR IS FOR:
 *
 * - Ink on both surfaces at 12:1. Body text on the page and body text on a card. The rule the app
 *   is actually held to is far above AA, because a form somebody fills in for an hour is not a
 *   heading somebody glances at.
 * - The hint on the card at 4.5:1. Muted is dimmer than the ink by design; it is not decoration,
 *   and a reader has to be able to read it.
 * - The identifier on the card at 4.5:1 AND visibly cast. `--machine` separates from the hint by
 *   hue rather than by a third grey, so both halves of that are checked: it reads, and it is not
 *   simply another grey.
 * - Border and input against BOTH the card and the page at 1.3:1. A line has two sides and has to
 *   be seen from both; a border tuned against the card alone disappears wherever a card does not
 *   sit under it.
 * - The card off the page at 1.03:1, which is what "the card sits ON something" means numerically.
 */
/** A colour as oklab, which is the space these are mixed and converted through. */
interface Oklab {
    L: number
    a: number
    b: number
}

/** An `oklch(L C H)` literal as oklab, or nothing when the value is not one. */
function asOklab(value: string): Oklab | null {
    const stated = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)/.exec(value)
    if (stated === null) return null
    const chroma = Number(stated[2])
    const radians = (Number(stated[3]) * Math.PI) / 180
    return { L: Number(stated[1]), a: chroma * Math.cos(radians), b: chroma * Math.sin(radians) }
}

/** One channel of linear sRGB, held inside the gamut a screen can actually show. */
function clampChannel(channel: number): number {
    return Math.min(1, Math.max(0, channel))
}

/** WCAG relative luminance, via the oklab-to-linear-sRGB matrices. */
function luminance({ L, a, b }: Oklab): number {
    const long = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    const medium = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    const short = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    return (
        0.2126 * clampChannel(4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short) +
        0.7152 * clampChannel(-1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short) +
        0.0722 * clampChannel(-0.0041960863 * long - 0.7034186147 * medium + 1.707614701 * short)
    )
}

/** The contrast between two colours, lighter over darker, so the order they are named in is free. */
function contrast(one: Oklab, two: Oklab): number {
    const [lighter, darker] = [luminance(one), luminance(two)].toSorted((first, second) => second - first)
    return (lighter + 0.05) / (darker + 0.05)
}

/** How far off grey a colour is - the whole of what "casts" means. */
function chromaOf({ a, b }: Oklab): number {
    return Math.sqrt(a * a + b * b)
}

/**
 * One token's colour in one palette, following the two indirections index.css uses.
 *
 * The derived layer is written as `var(--other)` and as `color-mix(in oklab, var(--a) N%, var(--b))`,
 * and both have to be walked here or `--machine` and the table grounds could not be checked at all -
 * they have no literal to read anywhere in the file.
 */
function resolveToken(token: string, palette: Map<string, string>): Oklab {
    const value = palette.get(token)
    expect(value, `no theme declares ${token}`).toBeDefined()
    const literal = asOklab(value ?? '')
    if (literal !== null) return literal
    const alias = /^var\((--[a-z0-9-]+)\)$/.exec(value ?? '')
    if (alias !== null) return resolveToken(alias[1], palette)
    const mixed = /^color-mix\(in oklab,\s*var\((--[a-z0-9-]+)\)\s+([\d.]+)%,\s*var\((--[a-z0-9-]+)\)\)$/.exec(
        value ?? '',
    )
    expect(mixed, `${token} is written as something this test cannot read: ${value ?? ''}`).not.toBeNull()
    const weight = Number(mixed?.[2] ?? 0) / 100
    const one = resolveToken(mixed?.[1] ?? '', palette)
    const two = resolveToken(mixed?.[3] ?? '', palette)
    return {
        L: one.L * weight + two.L * (1 - weight),
        a: one.a * weight + two.a * (1 - weight),
        b: one.b * weight + two.b * (1 - weight),
    }
}

describe('the neutral ladder', () => {
    const css = indexCss

    /** What one block declares, given the selector that opens it, as token to value. */
    const declarationsUnder = (selector: string): Map<string, string> => {
        const opened = css.indexOf(`${selector} {`)
        expect(opened, `index.css declares no block for ${selector}`).toBeGreaterThan(-1)
        const closed = css.indexOf('\n}', opened)
        return new Map(
            [...css.slice(opened, closed).matchAll(/^\s+(--[a-z0-9-]+):\s*([^;]+);/gm)].map((match) => [
                match[1],
                match[2].trim(),
            ]),
        )
    }

    const base = declarationsUnder(':root')

    /** The two selectors a theme is painted under, as the light and dark palettes they resolve to. */
    const groundsOf = (name: string): { mode: string; palette: Map<string, string> }[] => {
        const light = name === DEFAULT_THEME_NAME ? ':root' : `html[data-theme='${name}']`
        const dark = name === DEFAULT_THEME_NAME ? '.dark' : `html.dark[data-theme='${name}']`
        return [
            { mode: 'light', palette: new Map([...base, ...declarationsUnder(light)]) },
            { mode: 'dark', palette: new Map([...base, ...declarationsUnder(dark)]) },
        ]
    }

    for (const theme of THEMES) {
        for (const { mode, palette } of groundsOf(theme.name)) {
            const at = (token: string): Oklab => resolveToken(token, palette)

            it(`${theme.label} sets its ink far enough off both surfaces on the ${mode} ground`, () => {
                expect(contrast(at('--foreground'), at('--background'))).toBeGreaterThanOrEqual(12)
                expect(contrast(at('--foreground'), at('--card'))).toBeGreaterThanOrEqual(12)
                // The table's header band is a surface text lands on too, and it is the one a theme
                // could flatten without noticing, because nothing else in the app is painted on it.
                expect(contrast(at('--foreground'), at('--table-head'))).toBeGreaterThanOrEqual(12)
            })

            it(`${theme.label} keeps its hint readable on the ${mode} ground`, () => {
                expect(contrast(at('--muted-foreground'), at('--card'))).toBeGreaterThanOrEqual(4.5)
                expect(contrast(at('--muted-foreground'), at('--table-head'))).toBeGreaterThanOrEqual(4.5)
            })

            it(`${theme.label} gives an identifier a cast of its own on the ${mode} ground`, () => {
                // Readable first - it is text, and the mono face does not excuse it from that.
                expect(contrast(at('--machine'), at('--card'))).toBeGreaterThanOrEqual(4.5)
                // Then actually cast. A `--machine` that resolved to a third grey would pass every
                // ratio above and fail the rule it exists for.
                expect(chromaOf(at('--machine'))).toBeGreaterThanOrEqual(0.03)
                expect(chromaOf(at('--machine'))).toBeGreaterThanOrEqual(1.8 * chromaOf(at('--muted-foreground')))
            })

            it(`${theme.label} draws a border that can be seen from either side on the ${mode} ground`, () => {
                for (const line of ['--border', '--input']) {
                    expect(contrast(at(line), at('--card'))).toBeGreaterThanOrEqual(1.3)
                    expect(contrast(at(line), at('--background'))).toBeGreaterThanOrEqual(1.3)
                }
            })

            it(`${theme.label} sits its card on a page rather than in one on the ${mode} ground`, () => {
                expect(contrast(at('--card'), at('--background'))).toBeGreaterThanOrEqual(1.03)
                // The two table grounds are fills, not surfaces: off the card, and the zebra quieter
                // than the header, or the stripe becomes a second header.
                const head = contrast(at('--table-head'), at('--card'))
                const zebra = contrast(at('--table-zebra'), at('--card'))
                expect(head).toBeGreaterThan(1.01)
                expect(zebra).toBeGreaterThan(1)
                expect(zebra).toBeLessThan(head)
            })
        }
    }

    it('states the ladder tokens once, so no theme can leave one of them behind', () => {
        // `--machine` and the two table grounds are derived from tokens every theme already paints,
        // which is what makes one line correct in ten palettes. A theme restating them as literals
        // would be ten chances to get one wrong.
        for (const token of ['--machine', '--table-head', '--table-zebra']) {
            expect(base.get(token), `:root no longer derives ${token}`).toContain('var(')
        }
    })

    it('spends the identifier ink where the rule for it is written', () => {
        // The token exists for `.machine-identifier` and is worth nothing until that class reads it.
        const rule = css.slice(css.indexOf('.machine-identifier {'))
        expect(rule.slice(0, rule.indexOf('}'))).toContain('color: var(--machine)')
    })
})

/**
 * The interactive rule, read off the stylesheet and then off everything that draws with it.
 *
 * WHY THIS IS ASSERTED AGAINST SOURCE TEXT. The rule is "a thing that navigates wears the accent,
 * and a thing that does not never does", and the way it is broken is not by editing index.css - it
 * is by writing a new row somewhere with the old hand-rolled hover on it, which looks right in the
 * one screenshot the author takes and is wrong on every other screen. Nothing at runtime can catch
 * that: a page that spells its own hover renders, it just renders a second vocabulary. So the
 * spellings the classes replaced are named here and refused wherever they reappear.
 *
 * The shadcn primitives under `components/ui` are excluded. They are vendored, they are regenerated
 * from upstream, and their `link` variants are the button and badge shapes rather than prose links.
 */
describe('the interactive rule', () => {
    /** Every source file this app is written in, as text, keyed by path. */
    const sources = import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true })

    /** The app's own files - the vendored primitives and the suites are neither written nor read here. */
    const ours = Object.entries(sources).filter(
        ([path]) => !path.includes('/components/ui/') && !path.includes('.test.'),
    )

    it('has files to read, so a glob that matched nothing cannot pass as a clean sweep', () => {
        expect(ours.length).toBeGreaterThan(40)
    })

    it('declares all four classes, because a page adopting three of them is a page half-painted', () => {
        for (const rule of ['.interactive {', '.interactive-title {', '.interactive-mark {', '.interactive-link {']) {
            expect(indexCss).toContain(rule)
        }
    })

    it('spends the accent on the hover fill and on a link at rest, and on nothing else', () => {
        expect(indexCss).toContain('.interactive:hover {')
        expect(indexCss).toContain('.interactive-link {')
        // A link is coloured before the pointer arrives - the half of the rule a hover cannot serve
        // on a touch screen, where there is no hover at all.
        const link = indexCss.slice(indexCss.indexOf('.interactive-link {'))
        expect(link.slice(0, link.indexOf('}'))).toContain('color: var(--accent-foreground)')
    })

    it('leaves no row wearing a hand-rolled hover in place of the class', () => {
        for (const [path, source] of ours) {
            expect(source, `${path} spells its own row hover`).not.toContain('hover:bg-accent cursor-pointer')
            expect(source, `${path} spells its own row hover`).not.toContain('cursor-pointer hover:bg-accent')
        }
    })

    it('leaves no link painting itself, now that a link at rest is a class', () => {
        for (const [path, source] of ours) {
            if (!source.includes('hover:underline')) continue
            expect(source, `${path} paints a link by hand`).not.toContain('text-primary')
        }
    })

    it('ends every list of rows that open with the mark that says they open', () => {
        // A chevron per listing page: on a list, the mark is what says these open before anything
        // is hovered, and a page that took the hover fill without it took half the affordance.
        for (const page of ['Forms', 'Responses', 'Terminology', 'TrackedEntities']) {
            const source = ours.find(([path]) => path.endsWith(`/pages/${page}.tsx`))?.[1]
            expect(source, `no source read for ${page}`).toBeDefined()
            expect(source, `${page} takes the fill without the mark`).toContain('interactive-mark')
            expect(source, `${page} names no row that opens`).toContain('interactive-title')
        }
    })
})

/** A line that is prose for a person rather than a note for a reader of the source. */
function isCode(line: string): boolean {
    const trimmed = line.trimStart()
    return !trimmed.startsWith('*') && !trimmed.startsWith('//') && !trimmed.startsWith('/*')
}

/**
 * The complete single- and double-quoted literals on one line.
 *
 * Scanned rather than matched with an expression, because a pattern reaching from a quote to the
 * next mark walks straight through a template literal: `item.path !== ''` followed later by a
 * `${...}` is two apostrophes with a mark between them, and no sentence at all.
 */
function quotedLiterals(line: string): string[] {
    const found: string[] = []
    let quote: string | null = null
    let opened = 0
    for (let index = 0; index < line.length; index += 1) {
        const character = line[index]
        if (character === '\\') {
            index += 1
            continue
        }
        if (quote === null) {
            if (character === "'" || character === '"') {
                quote = character
                opened = index + 1
            }
            continue
        }
        if (character === quote) {
            found.push(line.slice(opened, index))
            quote = null
        }
    }
    return found
}

/**
 * The one spelling a browser renders as a character rather than as a face.
 *
 * A backtick is how these sources mark machine spelling in a COMMENT, and how `lib/reference.ts`
 * marks it in prose that is data and gets a renderer for exactly that reason. Anywhere else - in a
 * sentence a component hands to the screen - it is a character a reader sees, and the fix is the
 * `<code className="font-mono">` element the rest of the app's prose already uses.
 */
describe('prose the screen is handed', () => {
    const sources = import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true })

    it('hands the screen no sentence with a mark left in it', () => {
        for (const [path, source] of Object.entries(sources)) {
            // `lib/reference.ts` is the one module whose marks are markup: they are data, they are
            // paired, and `proseRuns` turns every one of them into an element before it is drawn.
            // The suites hold fixtures - a server's own diagnostic is quoted as the server wrote it.
            if (path.includes('/components/ui/') || path.includes('.test.')) continue
            if (path.endsWith('/reference.ts')) continue
            for (const [index, line] of source.split('\n').entries()) {
                if (!isCode(line)) continue
                for (const literal of quotedLiterals(line)) {
                    // A mark with words around it is a sentence; a mark on its own is a character a
                    // parser is looking for, which `lib/codelang.ts` does when it colours a string.
                    if (!literal.includes('`') || !literal.includes(' ')) continue
                    expect.fail(`${path}:${String(index + 1)} renders a mark as a character: ${literal}`)
                }
            }
        }
    })
})

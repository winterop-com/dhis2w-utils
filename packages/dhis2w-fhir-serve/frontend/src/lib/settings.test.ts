import { afterEach, describe, expect, it, vi } from 'vitest'

import {
    APPEARANCE_LABEL,
    appearanceItems,
    MODE_SECTION,
    SETTINGS_LABEL,
    settingsSections,
    THEME_SECTION,
} from '@/lib/settings'
import { SWITCH_TO_DARK_LABEL, SWITCH_TO_LIGHT_LABEL } from '@/lib/palette'
import { chooseTheme, THEMES } from '@/lib/theme'

/**
 * What sits behind the gear in the lower left.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The menu is the only place the two appearance controls live
 * now that the header carries neither, so a control quietly missing from it is a control the app no
 * longer has. The rows are a pure function of what is painted precisely so that can be checked.
 *
 * THE LAST CASE IS THE ONE THAT JOINS THE TWO HALVES: a row's effect carries a theme name, and that
 * name put through `chooseTheme` is what paints the document. A menu that offered the right rows and
 * carried the wrong names would pass everything above it and change nothing on screen.
 */

const items = (dark = false, theme: 'clinical' | 'terminal' = 'clinical') => appearanceItems({ theme, dark })

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('the menu behind the gear', () => {
    it('offers both appearance controls, each under its own heading', () => {
        // Two axes, two questions: which of the five themes, and which ground it is painted on.
        const sections = settingsSections(items())
        expect(sections.map((section) => section.heading)).toEqual([THEME_SECTION, MODE_SECTION])
        expect(sections[0].items).toHaveLength(THEMES.length)
        expect(sections[1].items).toHaveLength(1)
    })

    it('offers every theme, the one in force included and marked', () => {
        // A list that dropped the current theme would re-order itself under the pointer the moment
        // anything was chosen, and the marked row is what says which theme is on.
        const offered = items(false, 'terminal')
        expect(offered.filter((item) => item.section === THEME_SECTION).map((item) => item.label)).toEqual(
            THEMES.map((theme) => theme.label),
        )
        expect(offered.filter((item) => item.checked).map((item) => item.id)).toEqual(['theme:terminal'])
    })

    it('offers the ground that is not the one in force, and never marks it', () => {
        const light = items(false).find((item) => item.id === 'mode:switch')
        const dark = items(true).find((item) => item.id === 'mode:switch')
        expect(light?.label).toBe(SWITCH_TO_DARK_LABEL)
        expect(dark?.label).toBe(SWITCH_TO_LIGHT_LABEL)
        expect(light?.effect).toEqual({ kind: 'mode', mode: 'dark' })
        expect(dark?.effect).toEqual({ kind: 'mode', mode: 'light' })
        expect(light?.checked).toBe(false)
    })

    it('names things plainly - the gear, the part, and the two headings', () => {
        // No theatrical headings, no shorthand nouns, and "mode" never dressed up as "theme".
        expect(SETTINGS_LABEL).toBe('Settings')
        expect(APPEARANCE_LABEL).toBe('Appearance')
        expect(THEME_SECTION).toBe('Theme')
        expect(MODE_SECTION).toBe('Mode')
        for (const item of items()) expect(item.label).not.toMatch(/^(The|On the) /)
    })

    it('gives every row an id of its own, so a row cannot stand in for another', () => {
        const offered = items()
        expect(new Set(offered.map((item) => item.id)).size).toBe(offered.length)
    })

    it('carries the theme it would apply, and applying it paints the document', () => {
        // The document is stubbed rather than emulated, as `lib/theme.test.ts` stubs it: what
        // applying a theme does is set one attribute on one element, and a recorder says exactly
        // which attribute got which value.
        const written: { attribute: string; value: string }[] = []
        vi.stubGlobal('localStorage', {
            getItem: () => null,
            setItem: () => undefined,
        })
        vi.stubGlobal('document', {
            documentElement: {
                setAttribute: (attribute: string, value: string) => {
                    written.push({ attribute, value })
                },
            },
        })

        const paper = items().find((item) => item.id === 'theme:paper')
        expect(paper?.effect).toEqual({ kind: 'theme', theme: 'paper' })
        if (paper?.effect.kind !== 'theme') throw new Error('the theme row carries no theme')
        expect(chooseTheme(paper.effect.theme)).toBe('paper')
        expect(written).toEqual([{ attribute: 'data-theme', value: 'paper' }])
    })
})

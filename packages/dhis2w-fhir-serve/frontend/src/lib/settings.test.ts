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

const items = (dark = false, theme: 'clinical' = 'clinical') => appearanceItems({ theme, dark })

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('the menu behind the gear', () => {
    it('offers the ground alone while there is one theme', () => {
        // One theme is no choice, so the theme section hides itself and the menu asks the one
        // question with two answers: which ground the palette is painted on.
        const sections = settingsSections(items())
        expect(sections.map((section) => section.heading)).toEqual([MODE_SECTION])
        expect(sections[0].items).toHaveLength(1)
    })

    it('offers no theme row while there is nothing to pick between', () => {
        // The rows return when a second theme lands in THEMES - offering every theme with the one
        // in force included and marked; those assertions come back with the gate.
        expect(items().filter((item) => item.section === THEME_SECTION)).toEqual([])
        expect(THEMES.length).toBe(1)
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

    it('applying a theme name paints the document', () => {
        // The document is stubbed rather than emulated, as `lib/theme.test.ts` stubs it: what
        // applying a theme does is set one attribute on one element, and a recorder says exactly
        // which attribute got which value. The row-to-effect half of this test returns with the
        // theme rows themselves, when a second theme lands in THEMES.
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

        expect(chooseTheme('clinical')).toBe('clinical')
        expect(written).toEqual([{ attribute: 'data-theme', value: 'clinical' }])
    })
})

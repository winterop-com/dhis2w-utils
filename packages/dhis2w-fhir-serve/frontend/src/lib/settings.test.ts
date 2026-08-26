import { afterEach, describe, expect, it, vi } from 'vitest'

import {
    APPEARANCE_LABEL,
    appearanceGroups,
    appearanceItems,
    matchesSettingsQuery,
    MODE_GROUP,
    SETTINGS_DESCRIPTION,
    SETTINGS_LABEL,
    SETTINGS_NO_MATCH,
    SETTINGS_SEARCH_LABEL,
    SETTINGS_SECTIONS,
    THEME_GROUP,
} from '@/lib/settings'
import { SWITCH_TO_DARK_LABEL, SWITCH_TO_LIGHT_LABEL } from '@/lib/palette'
import { SHORTCUTS_TITLE } from '@/lib/shortcuts'
import { chooseTheme, THEMES } from '@/lib/theme'

/**
 * What sits behind the gear in the lower left.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. The dialog is the only place the two appearance controls live
 * now that the header carries neither, so a control quietly missing from it is a control the app no
 * longer has. The rows are a pure function of what is painted precisely so that can be checked.
 *
 * THE LAST CASE IS THE ONE THAT JOINS THE TWO HALVES: a row's effect carries a theme name, and that
 * name put through `chooseTheme` is what paints the document. A dialog that offered the right rows
 * and carried the wrong names would pass everything above it and change nothing on screen.
 */

const items = (dark = false, theme: 'clinical' | 'terminal' = 'clinical') => appearanceItems({ theme, dark })

afterEach(() => {
    vi.unstubAllGlobals()
})

describe('the settings dialog', () => {
    it('holds more than the colours, each section named for what is in it', () => {
        // The gear said Settings and opened a theme list, which is the whole reason this is a dialog
        // with sections: appearance is one of the things a person sets here, not all of them.
        expect(SETTINGS_SECTIONS.map((section) => section.id)).toEqual(['appearance', 'shortcuts'])
        expect(SETTINGS_SECTIONS.map((section) => section.heading)).toEqual([APPEARANCE_LABEL, SHORTCUTS_TITLE])
    })

    it('offers both appearance controls, each under its own heading', () => {
        // Two axes, two questions: which of the themes, and which ground it is painted on.
        const groups = appearanceGroups(items())
        expect(groups.map((group) => group.heading)).toEqual([THEME_GROUP, MODE_GROUP])
        expect(groups[0].items).toHaveLength(THEMES.length)
        expect(groups[1].items).toHaveLength(1)
    })

    it('offers every theme, the one in force included and marked', () => {
        // A list that dropped the current theme would re-order itself under the pointer the moment
        // anything was chosen, and the marked row is what says which theme is on.
        const offered = items(false, 'terminal')
        expect(offered.filter((item) => item.group === THEME_GROUP).map((item) => item.label)).toEqual(
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

    it('names things plainly - the gear, the sections, and the two headings', () => {
        // No theatrical headings, no shorthand nouns, and "mode" never dressed up as "theme".
        expect(SETTINGS_LABEL).toBe('Settings')
        expect(APPEARANCE_LABEL).toBe('Appearance')
        expect(THEME_GROUP).toBe('Theme')
        expect(MODE_GROUP).toBe('Mode')
        expect(SETTINGS_DESCRIPTION).toBe('Appearance and keyboard shortcuts')
        for (const section of SETTINGS_SECTIONS) expect(section.heading).not.toMatch(/^(The|On the) /)
        for (const item of items()) expect(item.label).not.toMatch(/^(The|On the) /)
    })

    it('matches a row on any of its words, in whichever case they were typed', () => {
        // What somebody types into a box that small is the start of a word already on the screen -
        // the theme's name, a word out of its hint, or the key itself.
        expect(matchesSettingsQuery('term', ['Terminal', 'Phosphor green, and a ground to match.'])).toBe(true)
        expect(matchesSettingsQuery('PHOSPHOR', ['Terminal', 'Phosphor green, and a ground to match.'])).toBe(true)
        expect(matchesSettingsQuery('esc', ['Close a dialog, a menu, or the palette', 'Esc'])).toBe(true)
        expect(matchesSettingsQuery('indigo', ['Terminal', null])).toBe(false)
    })

    it('matches everything while the box is empty, so the box is what filters and not the caller', () => {
        expect(matchesSettingsQuery('', ['Clinical'])).toBe(true)
        expect(matchesSettingsQuery('   ', ['Clinical'])).toBe(true)
    })

    it('names the search box and says plainly when nothing answers to it', () => {
        expect(SETTINGS_SEARCH_LABEL).toBe('Search settings')
        expect(SETTINGS_NO_MATCH).toBe('No setting matches what you typed')
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

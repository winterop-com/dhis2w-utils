/**
 * What the settings dialog offers, as data.
 *
 * ONE GEAR IN THE LOWER LEFT, AND THE HEADER IS FOR THE PAGE. A header carrying a theme picker, a
 * mode toggle, a palette button, an identity, a sign-out and a server light is a header nobody reads
 * - the page's own name is what a header is for. So everything a person sets about this app sits
 * behind one gear at the foot of the sidebar, where they look for settings in every other app they
 * have used.
 *
 * A DIALOG WITH SECTIONS, NOT A MENU WITH ONE CHOOSER. Settings that were a theme list and nothing
 * else made the word Settings a promise the gear did not keep. `SETTINGS_SECTIONS` names what the
 * dialog holds - how the app looks, and every key it answers - and it is the list a section is added
 * to when this app accrues its next per-person preference.
 *
 * THE LIST IS A PURE FUNCTION, for the reason `lib/palette.ts` is one: the failures worth catching
 * are a control that quietly is not offered, a mark on the wrong row, and a label that breaks the
 * copy rules, and all three are visible in the returned array with no browser in scope.
 *
 * TWO AXES INSIDE APPEARANCE, TWO GROUPS. The **theme** is which of the seven sets of colours the
 * app spends; the **mode** is the light ground or the dark one. Every theme is designed for both, so
 * folding them into one list would make a reader pick a theme in order to change the ground. They
 * are two questions and they get two headings.
 */

import { THEMES, type ThemeName } from '@/lib/theme'
import { SWITCH_TO_DARK_LABEL, SWITCH_TO_LIGHT_LABEL } from '@/lib/palette'
import { SHORTCUTS_TITLE } from '@/lib/shortcuts'

/** What the gear is called, wherever it has to be named - its own label, its tooltip, the dialog. */
export const SETTINGS_LABEL = 'Settings'

/** One line under the dialog's title, saying what a reader will find in it. */
export const SETTINGS_DESCRIPTION = 'Appearance and keyboard shortcuts'

/** What the dialog calls the section that decides how the app looks. */
export const APPEARANCE_LABEL = 'Appearance'

/** The heading over the seven themes. */
export const THEME_GROUP = 'Theme'

/** The heading over the light ground and the dark one. */
export const MODE_GROUP = 'Mode'

/** Which section of the dialog is meant - by the gear, and by the ways in that name one. */
export type SettingsSectionId = 'appearance' | 'shortcuts'

/** One section of the dialog: what it is called, and the name the rest of the app refers to it by. */
export interface SettingsSection {
    id: SettingsSectionId
    /** The heading over the section, which names its content plainly. */
    heading: string
}

/**
 * Every section the dialog holds, in the order it stacks them.
 *
 * Appearance first because it is the one a person opens the gear to change; the keys after it,
 * because a reader who came for the list of keys got here by pressing one of them.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
    { id: 'appearance', heading: APPEARANCE_LABEL },
    { id: 'shortcuts', heading: SHORTCUTS_TITLE },
]

/** What the box at the top of the section rail is for, which is also its accessible name. */
export const SETTINGS_SEARCH_LABEL = 'Search settings'

/** What the pane says when the box has been typed into and nothing in the dialog answers to it. */
export const SETTINGS_NO_MATCH = 'No setting matches what you typed'

/**
 * Whether one row answers what has been typed into the search box.
 *
 * SUBSTRING, CASE-BLIND, AND NOTHING ELSE. The dialog holds a few dozen rows, and what a person
 * types into a box that small is the start of a word they can already see - "term" for Terminal,
 * "esc" for the key. A ranked or fuzzy match would put a row nobody asked for above the row they
 * meant, which on a list this short is worse than not matching at all.
 *
 * An empty box matches everything, so the caller filters unconditionally and the box decides.
 */
export function matchesSettingsQuery(query: string, terms: (string | null)[]): boolean {
    const needle = query.trim().toLowerCase()
    if (needle === '') return true
    return terms.some((term) => term !== null && term.toLowerCase().includes(needle))
}

/** What choosing one row does. Data rather than a callback, so the list can be asserted on. */
export type SettingsEffect = { kind: 'theme'; theme: ThemeName } | { kind: 'mode'; mode: 'light' | 'dark' }

/** One row of the appearance section: what it is called, what it says, and what it does. */
export interface SettingsItem {
    /** Stable across rebuilds of the list, so the renderer can key on it. */
    id: string
    /** The heading the row sits under. */
    group: string
    label: string
    /** The muted line beneath the label, or null when the label says the whole thing. */
    hint: string | null
    /** True on a row that states what is already in force rather than offering a change. */
    checked: boolean
    effect: SettingsEffect
}

/** One group inside the appearance section: the heading, and what sits under it. */
export interface SettingsGroup {
    heading: string
    items: SettingsItem[]
}

/** What the appearance rows are built from: which theme is painted, and which ground it is on. */
export interface SettingsInput {
    theme: ThemeName
    /** Whether the dark ground is the one in force, so the row offers the other one. */
    dark: boolean
}

/**
 * Every appearance row the dialog offers, the theme in force marked rather than dropped.
 *
 * A list that dropped the current theme would re-order itself under the pointer the moment anything
 * was chosen, and the marked row is what tells a reader which theme they are actually in.
 */
export function appearanceItems(input: SettingsInput): SettingsItem[] {
    const themes: SettingsItem[] = THEMES.map((theme) => ({
        id: `theme:${theme.name}`,
        group: THEME_GROUP,
        label: theme.label,
        hint: theme.hint,
        checked: theme.name === input.theme,
        effect: { kind: 'theme', theme: theme.name },
    }))
    return [
        ...themes,
        {
            id: 'mode:switch',
            group: MODE_GROUP,
            label: input.dark ? SWITCH_TO_LIGHT_LABEL : SWITCH_TO_DARK_LABEL,
            hint: 'Every theme is designed for both',
            // Never marked: it offers the ground that is NOT in force, so a mark on it would say the
            // opposite of what the label says.
            checked: false,
            effect: { kind: 'mode', mode: input.dark ? 'light' : 'dark' },
        },
    ]
}

/**
 * The rows grouped, keeping the order they were built in.
 *
 * A Map rather than a sort: the builder already decided the order of both the groups and the rows,
 * and re-deriving it here would be a second opinion about it.
 */
export function appearanceGroups(items: SettingsItem[]): SettingsGroup[] {
    const groups = new Map<string, SettingsItem[]>()
    for (const item of items) {
        const known = groups.get(item.group)
        if (known === undefined) groups.set(item.group, [item])
        else known.push(item)
    }
    return [...groups].map(([heading, grouped]) => ({ heading, items: grouped }))
}

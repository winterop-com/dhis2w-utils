/**
 * What the settings menu offers, as data.
 *
 * ONE MENU IN THE LOWER LEFT, AND THE HEADER IS FOR THE PAGE. A header carrying a theme picker, a
 * mode toggle, a palette button, an identity, a sign-out and a server light is a header nobody reads
 * - the page's own name is what a header is for. So the two appearance controls sit behind one gear
 * at the foot of the sidebar, where a person looks for settings in every other app they have used.
 *
 * THE LIST IS A PURE FUNCTION, for the reason `lib/palette.ts` is one: the failures worth catching
 * are a control that quietly is not offered, a tick on the wrong row, and a label that breaks the
 * copy rules, and all three are visible in the returned array with no browser in scope.
 *
 * TWO AXES, TWO SECTIONS. The **theme** is which of the five sets of colours the app spends;
 * the **mode** is the light ground or the dark one. Every theme is designed for both, so folding
 * them into one list would make a reader pick a theme in order to change the ground. They are two
 * questions and they get two headings.
 */

import { THEMES, type ThemeName } from '@/lib/theme'
import { SWITCH_TO_DARK_LABEL, SWITCH_TO_LIGHT_LABEL } from '@/lib/palette'

/** What the gear is called, wherever it has to be named - its own label, and its tooltip. */
export const SETTINGS_LABEL = 'Settings'

/** What the menu calls the part of itself that decides how the app looks. */
export const APPEARANCE_LABEL = 'Appearance'

/** The heading over the five themes. */
export const THEME_SECTION = 'Theme'

/** The heading over the light ground and the dark one. */
export const MODE_SECTION = 'Mode'

/** What choosing one row does. Data rather than a callback, so the list can be asserted on. */
export type SettingsEffect = { kind: 'theme'; theme: ThemeName } | { kind: 'mode'; mode: 'light' | 'dark' }

/** One row of the menu: what it is called, what it says, and what it does. */
export interface SettingsItem {
    /** Stable across rebuilds of the list, so the renderer can key on it. */
    id: string
    /** The heading the row sits under. */
    section: string
    label: string
    /** The muted line beneath the label, or null when the label says the whole thing. */
    hint: string | null
    /** True on a row that states what is already in force rather than offering a change. */
    checked: boolean
    effect: SettingsEffect
}

/** One section of the menu: the heading, and what sits under it. */
export interface SettingsSection {
    heading: string
    items: SettingsItem[]
}

/** What the menu is built from: which theme is painted, and which ground it is painted on. */
export interface SettingsInput {
    theme: ThemeName
    /** Whether the dark ground is the one in force, so the row offers the other one. */
    dark: boolean
}

/**
 * Every appearance row the menu offers, the theme in force marked rather than dropped.
 *
 * A list that dropped the current theme would re-order itself under the pointer the moment anything
 * was chosen, and the marked row is what tells a reader which theme they are actually in.
 */
export function appearanceItems(input: SettingsInput): SettingsItem[] {
    // One theme is no choice: the section hides itself until a second theme lands in THEMES.
    const themes: SettingsItem[] = THEMES.length < 2 ? [] : THEMES.map((theme) => ({
        id: `theme:${theme.name}`,
        section: THEME_SECTION,
        label: theme.label,
        hint: theme.hint,
        checked: theme.name === input.theme,
        effect: { kind: 'theme', theme: theme.name },
    }))
    return [
        ...themes,
        {
            id: 'mode:switch',
            section: MODE_SECTION,
            label: input.dark ? SWITCH_TO_LIGHT_LABEL : SWITCH_TO_DARK_LABEL,
            hint: null,
            // Never marked: it offers the ground that is NOT in force, so a tick on it would say the
            // opposite of what the label says.
            checked: false,
            effect: { kind: 'mode', mode: input.dark ? 'light' : 'dark' },
        },
    ]
}

/**
 * The rows sectioned, keeping the order they were built in.
 *
 * A Map rather than a sort: the builder already decided the order of both the sections and the rows,
 * and re-deriving it here would be a second opinion about it.
 */
export function settingsSections(items: SettingsItem[]): SettingsSection[] {
    const sections = new Map<string, SettingsItem[]>()
    for (const item of items) {
        const known = sections.get(item.section)
        if (known === undefined) sections.set(item.section, [item])
        else known.push(item)
    }
    return [...sections].map(([heading, grouped]) => ({ heading, items: grouped }))
}

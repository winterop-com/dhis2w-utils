/**
 * The themes this app can be painted in, and the one this browser is painted in now.
 *
 * TWO INDEPENDENT AXES, AND KEEPING THEM APART IS THE WHOLE DESIGN. The **mode** is light or dark -
 * next-themes owns it, writes it as a `dark` class on `<html>`, and follows the operating system
 * until somebody says otherwise. The **theme** is which set of colours the app spends inside that
 * mode - this module owns it, writes it as `data-theme` on the same element, and every theme is
 * designed for both modes. Neither axis knows about the other: picking Paper does not decide light
 * or dark, and switching to dark does not decide Paper.
 *
 * WHERE THE COLOURS ARE. Nowhere near here. Each theme is a block of custom-property overrides in
 * index.css, hung off `html[data-theme='<name>']` for the light ground and
 * `html.dark[data-theme='<name>']` for the dark one, beside the base palette that Clinical is. This
 * module carries the names, and names are all it carries - so adding a theme is a block of CSS plus
 * one row in `THEMES`, and no component learns that a theme exists.
 *
 * EVERY THEME OVERRIDES EVERY TOKEN THE BASE DECLARES, the source colours the editors are painted
 * from included. A theme that overrode the surfaces and left `--code-string` behind would put the
 * base palette's green inside Terminal's editor, where the surface is already green - which is the
 * failure the completeness rule exists to prevent.
 *
 * APPLIED BEFORE FIRST PAINT, in index.html rather than here. A theme read in a React effect is a
 * theme that arrives one frame after the app does, and the reader sees Clinical flash under Terminal
 * on every load. The inline script in index.html sets the attribute off the same storage key and the
 * same name list this module holds, and `themeNamesInIndexHtml` in the test beside this file is what
 * keeps the two copies honest.
 *
 * A MODULE-LEVEL STORE, read through `useSyncExternalStore`, for the reason `lib/auth` is one:
 * several components look at the same fact - the header's picker marks the current theme, the
 * command palette marks it too - and it is read once for all of them.
 */

/** The name one theme is stored and written under: its `data-theme` value and its localStorage value. */
export type ThemeName = 'clinical' | 'indigo' | 'paper' | 'contrast' | 'terminal'

/** One theme: what it is called on screen, and what it looks like. */
export interface Theme {
    name: ThemeName
    /** What the picker and the command palette call it. */
    label: string
    /** One line saying what it looks like - true of the theme in both modes, because it has both. */
    hint: string
}

/**
 * Every theme, in the order a picker offers them.
 *
 * Clinical first because it is what an app that has never been told anything is painted in. The
 * three after it are quiet - they change the ground and the identity hue and nothing about how much
 * colour the surface spends - and the two at the end are the ones with an argument: Contrast pushes
 * text and surface as far apart as the tokens go, and Terminal is a deliberate piece of character.
 *
 * THE ORDER IS NOT A RANKING. It is quiet-to-loud, so somebody scanning the list meets the ones that
 * look like the app they already have before the ones that do not.
 */
export const THEMES: Theme[] = [
    {
        name: 'clinical',
        label: 'Clinical',
        hint: 'Near-achromatic surfaces and one clinical blue. The default.',
    },
    {
        name: 'indigo',
        label: 'Indigo',
        hint: 'Deep blue surfaces under a violet identity.',
    },
    {
        name: 'paper',
        label: 'Paper',
        hint: 'Warm surfaces and an ink blue, the way a printed form reads.',
    },
    {
        name: 'contrast',
        label: 'Contrast',
        hint: 'The widest separation this app has between text and the surface under it.',
    },
    {
        name: 'terminal',
        label: 'Terminal',
        hint: 'Phosphor green, and a ground to match.',
    },
]

/** What the app is painted in when nothing has been chosen, and what an unknown name falls back to. */
export const DEFAULT_THEME_NAME: ThemeName = 'clinical'

/** Where the chosen theme is kept. `localStorage`, so it survives the tab that chose it. */
export const THEME_STORAGE_KEY = 'd2w-fhir.theme'

/** The attribute on `<html>` the CSS blocks hang off. */
export const THEME_ATTRIBUTE = 'data-theme'

/** Every theme name, which is what a stored value is checked against. */
export const THEME_NAMES: ThemeName[] = THEMES.map((theme) => theme.name)

/** Whether a string is a theme this app has - the one gate a stored or written value passes. */
export function isThemeName(candidate: string | null): candidate is ThemeName {
    return candidate !== null && THEME_NAMES.includes(candidate as ThemeName)
}

/**
 * The theme one name means, with anything this app does not have read as the default.
 *
 * An unknown name is not an error state worth a screen: it is a value from a build that had a theme
 * this one does not, or a hand-edited storage entry. Either way the honest answer is the theme
 * everything starts in, rather than an app painted in no theme at all.
 */
export function themeByName(name: string | null): Theme {
    const known = THEMES.find((theme) => theme.name === name)
    return known ?? THEMES[0]
}

/** What one theme is called, for a label that has only the name to hand. */
export function themeLabel(name: string | null): string {
    return themeByName(name).label
}

/**
 * The theme this browser last chose, or the default.
 *
 * Storage that refuses to be read - a browser with it denied, a private window under some settings -
 * is the same answer as storage that holds nothing: the app is painted in the default and the choice
 * simply does not survive the reload.
 */
export function storedThemeName(): ThemeName {
    try {
        const stored = localStorage.getItem(THEME_STORAGE_KEY)
        return isThemeName(stored) ? stored : DEFAULT_THEME_NAME
    } catch {
        return DEFAULT_THEME_NAME
    }
}

/** Write one theme onto the document, which is what makes the CSS blocks apply. */
export function applyTheme(name: ThemeName): void {
    document.documentElement.setAttribute(THEME_ATTRIBUTE, name)
}

let current: ThemeName = DEFAULT_THEME_NAME
const listeners = new Set<() => void>()

/** The theme in force as of this instant. */
export function themeSnapshot(): ThemeName {
    return current
}

/** Subscribe a component to the chosen theme. */
export function subscribeToTheme(listener: () => void): () => void {
    listeners.add(listener)
    return () => {
        listeners.delete(listener)
    }
}

/**
 * Read what is stored, paint the document with it, and let every reader know.
 *
 * Called once as the app mounts. The document already carries the attribute by then - index.html put
 * it there before the first paint - so this is what brings the module store into step with the page
 * rather than what decides how the page looks.
 */
export function initialiseTheme(): ThemeName {
    return chooseTheme(storedThemeName())
}

/**
 * Choose one theme: persist it, paint it, publish it.
 *
 * A name this app does not have is read as the default rather than refused, by the same rule
 * `themeByName` follows - so nothing that calls this has to hold a valid name to call it safely.
 */
export function chooseTheme(name: string): ThemeName {
    const chosen = isThemeName(name) ? name : DEFAULT_THEME_NAME
    try {
        localStorage.setItem(THEME_STORAGE_KEY, chosen)
    } catch {
        // A browser with storage denied still gets the theme it asked for, for as long as this
        // document is open. Only surviving the reload is lost.
    }
    applyTheme(chosen)
    current = chosen
    for (const listener of listeners) listener()
    return chosen
}

import { useCallback, useEffect, useSyncExternalStore } from 'react'

import {
    chooseTheme,
    initialiseTheme,
    subscribeToTheme,
    themeSnapshot,
    type ThemeName,
} from '@/lib/theme'

/** The theme in force, and the way to change it. */
export interface ThemeChoice {
    theme: ThemeName
    choose: (name: ThemeName) => void
}

/**
 * Which theme this app is painted in.
 *
 * NAMED `useThemeChoice` AND NOT `useTheme` because next-themes already owns that name for the other
 * axis - light or dark. The two are independent and both are real, so the names have to say which
 * one is meant wherever they sit side by side.
 *
 * `initialiseTheme` runs once on mount, and what it does is bring the module store into step with a
 * document that is already painted: the attribute was written before the first paint by the inline
 * script in index.html, and this reads the same storage key to the same answer. It is deliberately
 * not the thing that decides how the page looks - by the time React runs, that is settled.
 */
export function useThemeChoice(): ThemeChoice {
    const theme = useSyncExternalStore(subscribeToTheme, themeSnapshot, themeSnapshot)

    useEffect(() => {
        initialiseTheme()
    }, [])

    const choose = useCallback((name: ThemeName) => {
        chooseTheme(name)
    }, [])

    return { theme, choose }
}

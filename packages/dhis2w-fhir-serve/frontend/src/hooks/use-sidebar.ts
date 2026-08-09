import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'd2w-fhir.sidebarCollapsed'

/**
 * Sidebar collapsed state, persisted across reloads.
 *
 * Read synchronously in the initial state rather than in an effect, so the
 * sidebar renders at its correct width on the first paint instead of expanding
 * and then snapping shut.
 */
export function useSidebar() {
    const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(STORAGE_KEY) === 'true')

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, String(collapsed))
    }, [collapsed])

    const toggle = useCallback(() => setCollapsed((value) => !value), [])

    return { collapsed, toggle }
}

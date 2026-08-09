import { useEffect, useState } from 'react'

import { readUiConfig } from '@/lib/api'
import { DEFAULT_UI_CONFIG, type UiConfig } from '@/lib/uiconfig'

/** The settings read, and whether the read has finished - which is what gates building the map. */
export interface UiConfigState {
    config: UiConfig
    loading: boolean
}

/**
 * Read the run-time settings this UI acts on.
 *
 * NO ERROR STATE, ON PURPOSE. Every other read in this app keeps its refusal, because a page that
 * cannot load its data has nothing honest to render. This one has: a server that does not answer
 * `/uiconfig` is an older facade or a proxy that swallowed the path, and the right response to both
 * is the boundary-only map - the same thing the setting's own "none" produces. So a failure falls
 * back to `DEFAULT_UI_CONFIG` and the page carries on drawing shapes rather than reporting that it
 * could not find out which tiles to draw under them.
 *
 * `loading` still matters: the map is built once against these settings, so it waits for the read
 * to land rather than constructing a tile-less map and rebuilding it a moment later.
 */
export function useUiConfig(): UiConfigState {
    const [config, setConfig] = useState<UiConfig>(DEFAULT_UI_CONFIG)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false
        readUiConfig()
            .then((read) => {
                if (cancelled) return
                setConfig(read)
                setLoading(false)
            })
            .catch(() => {
                if (cancelled) return
                setConfig(DEFAULT_UI_CONFIG)
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [])

    return { config, loading }
}

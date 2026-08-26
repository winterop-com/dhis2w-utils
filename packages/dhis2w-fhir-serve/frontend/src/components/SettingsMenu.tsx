import { useState } from 'react'
import { Settings } from 'lucide-react'

import { SettingsDialog } from '@/components/SettingsDialog'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { SETTINGS_LABEL } from '@/lib/settings'
import { cn } from '@/lib/utils'

/**
 * The gear at the foot of the sidebar, and the dialog behind it.
 *
 * LOWER LEFT, WHERE SETTINGS LIVE. The header names the page and says who is signed in and whether
 * the server is answering; how the app looks is not that, and two icon buttons for it were two
 * things competing with the page's own name. One gear, at the bottom of the rail, holding all of it.
 *
 * IT OPENS A DIALOG, NOT A DROPDOWN. What sits behind Settings is a small page - the seven themes
 * with a line each, the ground, and every key this app answers - and a small page in a menu is a
 * menu that has to be scrolled with the pointer held down. `SettingsDialog` holds the sections; this
 * holds only the way in, which is why the gear owns whether it is open rather than the shell.
 *
 * COLLAPSED, IT IS AN ICON WITH A TOOLTIP, which is the idiom every other entry on the rail already
 * follows. A gear that vanished when the rail was collapsed would make the collapse a decision about
 * more than the width.
 */
export function SettingsMenu({
    collapsed,
}: {
    /** Whether the rail is collapsed to icons, which decides whether the gear carries its name. */
    collapsed: boolean
    /** Taken and not used: the keys are a section of the dialog this gear opens on its own. */
    onShowShortcuts?: () => void
}) {
    const [open, setOpen] = useState(false)

    const gear = (
        <Button
            variant="ghost"
            size={collapsed ? 'icon' : 'sm'}
            aria-label={SETTINGS_LABEL}
            aria-haspopup="dialog"
            onClick={() => {
                setOpen(true)
            }}
            className={cn(
                'text-muted-foreground hover:bg-sidebar-wash hover:text-foreground',
                collapsed ? 'mx-auto flex size-10' : 'w-full justify-start gap-3 px-3',
            )}
        >
            <Settings className="size-4 shrink-0" aria-hidden />
            {!collapsed && <span>{SETTINGS_LABEL}</span>}
        </Button>
    )

    return (
        <>
            {collapsed ? (
                <Tooltip>
                    <TooltipTrigger asChild>{gear}</TooltipTrigger>
                    <TooltipContent side="right">{SETTINGS_LABEL}</TooltipContent>
                </Tooltip>
            ) : (
                gear
            )}
            <SettingsDialog open={open} onOpenChange={setOpen} section="appearance" />
        </>
    )
}

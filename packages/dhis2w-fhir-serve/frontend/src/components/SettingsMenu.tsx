import { useMemo } from 'react'
import { Check, Keyboard, Settings } from 'lucide-react'
import { useTheme } from 'next-themes'

import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useThemeChoice } from '@/hooks/use-theme-choice'
import {
    APPEARANCE_LABEL,
    appearanceItems,
    SETTINGS_LABEL,
    settingsSections,
    THEME_SECTION,
    type SettingsEffect,
} from '@/lib/settings'
import { SHORTCUTS_KEY, SHORTCUTS_TITLE } from '@/lib/shortcuts'
import { cn } from '@/lib/utils'

/**
 * The gear at the foot of the sidebar, and everything behind it.
 *
 * LOWER LEFT, WHERE SETTINGS LIVE. The header names the page and says who is signed in and whether
 * the server is answering; how the app looks is not that, and two icon buttons for it were two
 * things competing with the page's own name. One gear, at the bottom of the rail, holding both.
 *
 * IT HOLDS THE TWO APPEARANCE AXES, EACH UNDER ITS OWN HEADING. **Theme** is which of the five sets
 * of colours the app spends; **Mode** is the light ground or the dark one. Every theme is designed
 * for both, so they are two questions and they get two headings - see `lib/settings`, which decides
 * the rows, and `lib/theme`, which explains why the axes are separate at all.
 *
 * COLLAPSED, IT IS AN ICON WITH A TOOLTIP, which is the idiom every other entry on the rail already
 * follows. A settings menu that vanished when the rail was collapsed would make the collapse a
 * decision about more than the width.
 */
export function SettingsMenu({
    collapsed,
    onShowShortcuts,
}: {
    /** Whether the rail is collapsed to icons, which decides the trigger and where the menu opens. */
    collapsed: boolean
    /** Opens the list of every key this app answers - the dialog `?` opens. */
    onShowShortcuts: () => void
}) {
    const { theme, choose } = useThemeChoice()
    const { resolvedTheme, setTheme: setMode } = useTheme()
    const sections = useMemo(
        () => settingsSections(appearanceItems({ theme, dark: resolvedTheme === 'dark' })),
        [theme, resolvedTheme],
    )
    const run = (effect: SettingsEffect) => {
        if (effect.kind === 'theme') choose(effect.theme)
        else setMode(effect.mode)
    }

    const trigger = (
        <DropdownMenuTrigger asChild>
            <Button
                variant="ghost"
                size={collapsed ? 'icon' : 'sm'}
                aria-label={SETTINGS_LABEL}
                className={cn(
                    'text-muted-foreground hover:bg-sidebar-accent/40 hover:text-foreground',
                    collapsed ? 'mx-auto flex size-10' : 'w-full justify-start gap-3 px-3',
                )}
            >
                <Settings className="size-4 shrink-0" aria-hidden />
                {!collapsed && <span>{SETTINGS_LABEL}</span>}
            </Button>
        </DropdownMenuTrigger>
    )

    return (
        <DropdownMenu>
            {collapsed ? (
                <Tooltip>
                    <TooltipTrigger asChild>{trigger}</TooltipTrigger>
                    <TooltipContent side="right">{SETTINGS_LABEL}</TooltipContent>
                </Tooltip>
            ) : (
                trigger
            )}

            <DropdownMenuContent
                side={collapsed ? 'right' : 'top'}
                align="start"
                sideOffset={8}
                className="w-[min(20rem,calc(100vw-1.5rem))]"
            >
                <DropdownMenuLabel>{APPEARANCE_LABEL}</DropdownMenuLabel>
                {sections.map((section) => (
                    <DropdownMenuGroup key={section.heading}>
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
                            {section.heading}
                        </DropdownMenuLabel>
                        {section.items.map((item) => (
                            <DropdownMenuItem
                                key={item.id}
                                // A theme row is one of five and says which one is on, so it is a
                                // radio. The mode row is an act - it offers the ground that is not
                                // in force - so it is an item, and a tick on it would say the
                                // opposite of what it says.
                                {...(section.heading === THEME_SECTION
                                    ? { role: 'menuitemradio' as const, 'aria-checked': item.checked }
                                    : {})}
                                className="items-start gap-2"
                                onSelect={() => {
                                    run(item.effect)
                                }}
                            >
                                <Check
                                    className={cn('mt-0.5 size-4 shrink-0', !item.checked && 'opacity-0')}
                                    aria-hidden
                                />
                                <span className="grid gap-0.5">
                                    <span className={cn(item.checked && 'font-medium')}>{item.label}</span>
                                    {item.hint !== null && (
                                        <span className="text-muted-foreground text-xs">{item.hint}</span>
                                    )}
                                </span>
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuGroup>
                ))}

                <DropdownMenuSeparator />
                <DropdownMenuItem
                    onSelect={() => {
                        onShowShortcuts()
                    }}
                >
                    <Keyboard className="size-4 shrink-0" aria-hidden />
                    <span>{SHORTCUTS_TITLE}</span>
                    <KbdGroup className="ml-auto">
                        <Kbd>{SHORTCUTS_KEY}</Kbd>
                    </KbdGroup>
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

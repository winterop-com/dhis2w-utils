import { Check, Palette } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useThemeChoice } from '@/hooks/use-theme-choice'
import { THEMES } from '@/lib/theme'
import { cn } from '@/lib/utils'

/** What the picker is called, wherever it has to be named - its own label, and its tooltip. */
export const THEME_PICKER_LABEL = 'Theme'

/**
 * Which of the five themes the app is painted in.
 *
 * BESIDE THE LIGHT/DARK TOGGLE AND NOT INSTEAD OF IT. The two are separate questions - every theme
 * has a light ground and a dark one - so folding them into one menu would make a reader pick a
 * theme in order to change the ground, or the other way round. Two controls, side by side, one
 * question each.
 *
 * A MENU RATHER THAN A CYCLE BUTTON. Five is too many to step through, and a theme is chosen by what
 * it looks like rather than by its position in a list - so each row states what it is, and the row
 * in force carries a tick.
 */
export function ThemePicker() {
    const { theme, choose } = useThemeChoice()

    return (
        <DropdownMenu>
            <Tooltip>
                <TooltipTrigger asChild>
                    <DropdownMenuTrigger asChild>
                        <Button
                            variant="ghost"
                            size="icon"
                            aria-label={THEME_PICKER_LABEL}
                            className="text-muted-foreground hover:text-foreground"
                        >
                            <Palette className="size-4" />
                        </Button>
                    </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent>{THEME_PICKER_LABEL}</TooltipContent>
            </Tooltip>

            <DropdownMenuContent align="end" sideOffset={8} className="w-[min(20rem,calc(100vw-1.5rem))]">
                <DropdownMenuLabel>{THEME_PICKER_LABEL}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {THEMES.map((offered) => {
                    const chosen = offered.name === theme
                    return (
                        <DropdownMenuItem
                            key={offered.name}
                            aria-checked={chosen}
                            role="menuitemradio"
                            className="items-start gap-2"
                            onSelect={() => {
                                choose(offered.name)
                            }}
                        >
                            <Check
                                className={cn('mt-0.5 size-4 shrink-0', !chosen && 'opacity-0')}
                                aria-hidden
                            />
                            <span className="grid gap-0.5">
                                <span className={cn(chosen && 'font-medium')}>{offered.label}</span>
                                <span className="text-muted-foreground text-xs">{offered.hint}</span>
                            </span>
                        </DropdownMenuItem>
                    )
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

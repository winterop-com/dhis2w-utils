import { Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'

import { Button } from '@/components/ui/button'
import { SWITCH_TO_DARK_LABEL, SWITCH_TO_LIGHT_LABEL } from '@/lib/palette'

/**
 * The switch between the light ground and the dark one.
 *
 * A two-way switch rather than a three-way menu: the initial value already
 * follows the system preference, so an explicit "system" option would add a
 * click for something that is the default anyway.
 *
 * IT SWITCHES THE MODE, NOT THE THEME. Which of the five themes the app is
 * painted in is the picker beside this button (`ThemePicker`), and every one of
 * them is designed for both grounds - so this control says "mode" and leaves
 * "theme" to the control that means it. The two words are not interchangeable
 * here and a label that mixed them would send somebody to the wrong control.
 */
export function ThemeToggle() {
    const { resolvedTheme, setTheme } = useTheme()
    const dark = resolvedTheme === 'dark'

    return (
        <Button
            variant="ghost"
            size="sm"
            aria-label={dark ? SWITCH_TO_LIGHT_LABEL : SWITCH_TO_DARK_LABEL}
            onClick={() => setTheme(dark ? 'light' : 'dark')}
        >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
    )
}

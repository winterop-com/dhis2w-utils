import { Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'

import { Button } from '@/components/ui/button'

/**
 * Light/dark toggle.
 *
 * A two-way switch rather than a three-way menu: the initial value already
 * follows the system preference, so an explicit "system" option would add a
 * click for something that is the default anyway.
 */
export function ThemeToggle() {
    const { resolvedTheme, setTheme } = useTheme()
    const dark = resolvedTheme === 'dark'

    return (
        <Button
            variant="ghost"
            size="sm"
            aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
            onClick={() => setTheme(dark ? 'light' : 'dark')}
        >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
    )
}

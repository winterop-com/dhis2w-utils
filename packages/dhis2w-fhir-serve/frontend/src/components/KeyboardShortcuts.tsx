import { useMemo } from 'react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { applePlatform, shortcuts, SHORTCUTS_DESCRIPTION, SHORTCUTS_TITLE } from '@/lib/shortcuts'

/**
 * Every key this app answers, on screen.
 *
 * THE LIST EXISTS BECAUSE THE CHORDS DID NOT ANNOUNCE THEMSELVES. Cmd+K has opened the palette for
 * as long as there has been one, and the only thing that ever said so was a hint on one button -
 * which is to say most people never found it. `?` puts the whole list up, and the settings menu
 * carries a row into the same dialog for anybody who would never press a bare key to find out.
 *
 * WHAT IT IS AND IS NOT. Each row is what the press does in plain language, and the keys beside it
 * drawn as keys. No command names, no key names inside the sentence: a reader is being told what
 * happens, and the chord is the thing to the right of that.
 *
 * The keys are spelled for the keyboard in front of the reader - the command glyph on an Apple one,
 * the word Ctrl everywhere else - which is the same rule the palette button's own hint follows.
 */
export function KeyboardShortcuts({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
    // The user agent does not change under a running tab, so this is read once rather than per row.
    const rows = useMemo(() => shortcuts(applePlatform(navigator.userAgent)), [])

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogTitle>{SHORTCUTS_TITLE}</DialogTitle>
                <DialogDescription>{SHORTCUTS_DESCRIPTION}</DialogDescription>
                <dl className="grid gap-1">
                    {rows.map((shortcut) => (
                        <div
                            key={shortcut.id}
                            className="flex items-center justify-between gap-6 rounded-md px-2 py-1.5 odd:bg-muted/40"
                        >
                            <dt>{shortcut.action}</dt>
                            <dd>
                                <KbdGroup>
                                    {shortcut.keys.map((key) => (
                                        <Kbd key={key}>{key}</Kbd>
                                    ))}
                                </KbdGroup>
                            </dd>
                        </div>
                    ))}
                </dl>
            </DialogContent>
        </Dialog>
    )
}

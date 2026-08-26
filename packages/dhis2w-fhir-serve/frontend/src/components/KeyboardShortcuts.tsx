import { SettingsDialog } from '@/components/SettingsDialog'

/**
 * The way into the keys: the settings dialog, opened at the section that lists them.
 *
 * THE LIST EXISTS BECAUSE THE CHORDS DID NOT ANNOUNCE THEMSELVES. Cmd+K has opened the palette for
 * as long as there has been one, and the only thing that ever said so was a hint on one button -
 * which is to say most people never found it. `?` puts the list up, and the command palette carries
 * a row to the same place for anybody who would never press a bare key to find out.
 *
 * ONE DIALOG, NOT TWO. The keys are a section of Settings rather than a dialog of their own: a
 * person who opens the gear should meet everything this app lets them set, and a second overlay
 * holding one list would be a second place to look. So this is the same `SettingsDialog` the gear
 * opens, told which section the reader asked for - it scrolls there and hands its heading focus.
 */
export function KeyboardShortcuts({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
    return <SettingsDialog open={open} onOpenChange={onOpenChange} section="shortcuts" />
}

import * as React from 'react'

import { cn } from '@/lib/utils'

/** One key, drawn as a key: the shortcuts list and the palette footer both spell chords with it. */
function Kbd({ className, ...props }: React.ComponentProps<'kbd'>) {
    return (
        <kbd
            data-slot="kbd"
            className={cn(
                'bg-muted text-muted-foreground ring-border inline-flex h-5 min-w-5 items-center justify-center rounded px-1.5 font-mono text-[0.7rem] leading-none ring-1',
                className,
            )}
            {...props}
        />
    )
}

/** A chord, as the keys pressed together to make it. */
function KbdGroup({ className, ...props }: React.ComponentProps<'span'>) {
    return <span data-slot="kbd-group" className={cn('inline-flex items-center gap-1', className)} {...props} />
}

export { Kbd, KbdGroup }

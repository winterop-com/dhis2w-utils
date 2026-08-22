import { useEffect, useState } from 'react'
import { ChevronDown, PlugZap, RefreshCw, ServerCrash, ServerCog } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { refreshServerStatus, serverStatusSnapshot, useServerStatus } from '@/hooks/use-server-status'
import { servedIgLabel } from '@/lib/fhir'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

/**
 * Reachability light, plus what the server on the other end of it is serving.
 *
 * The dot answers "is anything there" at a glance. The panel answers the
 * question that actually matters when a capture goes wrong - which guide, at
 * which version, from which store mode - because a UI pointed at a stale
 * `--live` process and a UI pointed at a freshly compiled IG look identical
 * until you read the conformance document.
 */
export function StatusMenu() {
    const { reachability, capability, checking } = useServerStatus()
    const [open, setOpen] = useState(false)

    useEffect(() => {
        void refreshServerStatus()
    }, [])

    const label = checking ? 'Checking' : reachability === 'ok' ? 'Connected' : 'Unreachable'
    const StatusIcon = checking ? RefreshCw : reachability === 'ok' ? PlugZap : ServerCrash
    const dotClass =
        reachability === 'ok'
            ? 'bg-status-forwarded'
            : reachability === 'unreachable'
              ? 'bg-status-rejected'
              : 'bg-muted-foreground'

    const software = capability?.software
    const igLabel = servedIgLabel(capability)
    const storeMode = capability?.implementation?.description ?? null

    return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="ghost"
                    size="sm"
                    className="gap-2"
                    aria-label={`Server status: ${label}. Open details.`}
                >
                    <span className="relative flex size-2.5">
                        {/* Halo only while a probe is in flight, so motion means something. */}
                        {checking && (
                            <span
                                className={cn(
                                    'absolute inline-flex size-full animate-ping rounded-full opacity-70',
                                    dotClass,
                                )}
                            />
                        )}
                        <span className={cn('relative inline-flex size-2.5 rounded-full', dotClass)} />
                    </span>
                    <span className="hidden sm:inline">{igLabel ?? label}</span>
                    {software?.version && (
                        <Badge variant="secondary" className="ml-0.5 font-mono text-[0.7rem]">
                            {software.version}
                        </Badge>
                    )}
                    <ChevronDown className="size-3.5 opacity-60" aria-hidden />
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent
                align="end"
                sideOffset={8}
                className="w-[min(22rem,calc(100vw-1.5rem))]"
                onCloseAutoFocus={(event) => {
                    // Radix re-focuses the trigger on close, which paints the focus ring after a
                    // plain mouse dismiss; keyboard users re-enter via Tab as with any button.
                    event.preventDefault()
                }}
            >
                <DropdownMenuLabel className="flex items-center gap-2">
                    <StatusIcon className={cn('size-4', checking && 'animate-spin')} aria-hidden />
                    {label}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                <div className="space-y-2 px-2 py-1.5 text-sm">
                    {igLabel ? (
                        <p className="font-medium">{igLabel}</p>
                    ) : (
                        <p className="text-muted-foreground">
                            {reachability === 'ok'
                                ? 'Answering, but not as a FHIR endpoint.'
                                : 'No answer from the server. Is `d2w fhir serve --ui` still running?'}
                        </p>
                    )}
                    {software && (
                        <p className="text-muted-foreground font-mono text-xs">
                            {software.name} {software.version ?? ''}
                        </p>
                    )}
                    {capability?.fhirVersion && (
                        <p className="text-muted-foreground text-xs">FHIR {capability.fhirVersion}</p>
                    )}
                    {storeMode && <p className="text-muted-foreground text-xs">{storeMode}</p>}
                </div>

                <DropdownMenuSeparator />
                <DropdownMenuItem
                    disabled={checking}
                    onSelect={(event) => {
                        event.preventDefault()
                        void refreshServerStatus().then(() => {
                            const after = serverStatusSnapshot()
                            if (after.reachability !== 'ok') {
                                toast.error('Server unreachable', {
                                    description: 'This server did not answer.',
                                })
                            } else if (after.capability === null) {
                                // The same wording as the panel above states for the same
                                // condition, so one fact is not read twice in two spellings.
                                toast.warning('Answering, but not as a FHIR endpoint', {
                                    description:
                                        'The server answered, but not with the document that says what it offers.',
                                })
                            } else {
                                toast.success('Server checked', {
                                    description:
                                        servedIgLabel(after.capability) ??
                                        'What this server offers was read again.',
                                })
                            }
                        })
                    }}
                >
                    {checking ? (
                        <RefreshCw className="size-4 animate-spin" aria-hidden />
                    ) : (
                        <ServerCog className="size-4" aria-hidden />
                    )}
                    {checking ? 'Checking' : 'Check this server again'}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

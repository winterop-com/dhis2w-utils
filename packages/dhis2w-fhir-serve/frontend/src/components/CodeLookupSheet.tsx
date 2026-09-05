import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Loader2 } from 'lucide-react'

import { ProseText } from '@/components/ProseText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Sheet,
    SheetBody,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from '@/components/ui/sheet'
import { translateCode } from '@/lib/api'
import { countedNoun } from '@/lib/utils'
import {
    TRANSLATE_QUESTION,
    systemLabel,
    translationResult,
    type AskedConcept,
    type TranslationResult,
} from '@/lib/terminology'

/** The select value standing for "every group of every map", since Radix has no empty-string item. */
const ANY_TARGET = 'any'

/**
 * `$translate`, as a thing to click - in a sheet over the vocabulary it answers about.
 *
 * WHY THIS EXISTS AT ALL. The whole point of the ConceptMaps is that a generated concept code
 * resolves back to the DHIS2 option uid and option code the forwarder writes - and until you have
 * asked the server, "the map says so" is a claim about a document rather than about the running
 * process. One button turns the claim into an answer from the same store the forwarder reads.
 *
 * A code the maps say nothing about comes back as `result: false` with a message, HTTP 200. That
 * is not a failure of the call and is not rendered as one; only a refused request (a missing
 * parameter, an unreachable server) lands in the error line.
 *
 * WHY A SHEET RATHER THAN A PANEL BESIDE THE TABLE. A vocabulary is thousands of rows long and the
 * table is the page; a panel pinned beside it bounded the table to half the window, put a second
 * scrollbar inside the page, and still answered below the fold on a short window. The sheet arrives
 * over the table, at the top of the screen wherever the reader has scrolled to, and leaves on Esc
 * with the focus back on the row that opened it - so the vocabulary reads as one page again.
 *
 * THE ASK IS A PROP rather than local state, so a concept row can open this with the code it names
 * and the call is made straight away - a two-step "fill, then press" would make the row button do
 * half a thing. The nonce is what makes the same row asked twice a second question rather than a
 * value the component already held.
 */
export function CodeLookupSheet({
    open,
    onOpenChange,
    system,
    asked,
    targetSystems,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    /** The code system a concept is translated *from*, which is fixed by the page showing this. */
    system: string
    /** What was asked about, or a nonce-bumped empty code when the reader opened it to type one. */
    asked: AskedConcept
    /** The target systems the maps land on, offered as a filter. Empty means offer no choice. */
    targetSystems: string[]
}) {
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            {/* SIZED TO THE FORM IT HOLDS, and not to the width a reader last dragged a panel to.
                Every other side panel in this app carries a record whose width is a reading choice,
                so they share one dragged width; this one holds a box, a select, and a handful of
                answer rows, and inheriting a width dragged on a tracked entity's record covered the
                vocabulary it was opened from. `resizable={false}` is what keeps it its own size. */}
            <SheetContent data-testid="code-lookup-sheet" className="max-w-xl" resizable={false}>
                <SheetHeader>
                    <SheetTitle>{TRANSLATE_QUESTION}</SheetTitle>
                    <SheetDescription>
                        Type a concept code - or open a row in the table behind this panel - and the
                        published maps answer with the DHIS2 option UID and code it stands for. On
                        the wire this is the <code className="font-mono">$translate</code> operation
                        - the same one <code className="font-mono">d2w fhir forward</code> resolves a
                        coded answer with.
                    </SheetDescription>
                </SheetHeader>
                <SheetBody>
                    {/* Mounted with the sheet, so an ask made while it was shut is run when it
                        opens, and closing it leaves nothing half-answered behind. */}
                    <CodeLookup system={system} asked={asked} targetSystems={targetSystems} />
                </SheetBody>
            </SheetContent>
        </Sheet>
    )
}

/** One question on the wire: the code, the direction, and which press of Look up asked it. */
interface Lookup {
    code: string
    targetSystem: string
    /** Which ask this is, so looking the same code up twice is two questions rather than one. */
    nonce: number
}

/** What one question answered, stamped with the question it answered. */
interface AnsweredLookup {
    lookup: Lookup
    result: TranslationResult | null
    error: string | null
}

/** The question an ask carries, or none when it names no code. */
function lookupFor(asked: AskedConcept, nonce: number): Lookup | null {
    if (asked.code === '') return null
    return { code: asked.code.trim(), targetSystem: asked.targetSystem ?? ANY_TARGET, nonce }
}

/** The question and its answer: the box, the direction, the wire line, and what came back. */
function CodeLookup({
    system,
    asked,
    targetSystems,
}: {
    system: string
    asked: AskedConcept
    targetSystems: string[]
}) {
    const [entered, setEntered] = useState(asked.code)
    const [target, setTarget] = useState(asked.targetSystem ?? ANY_TARGET)
    const [lookup, setLookup] = useState<Lookup | null>(lookupFor(asked, 0))
    const [answered, setAnswered] = useState<AnsweredLookup | null>(null)

    const run = useCallback((code: string, targetSystem: string) => {
        if (code.trim() === '') return
        setLookup((previous) => ({ code: code.trim(), targetSystem, nonce: (previous?.nonce ?? 0) + 1 }))
    }, [])

    // THE ASK CARRIES ITS OWN DIRECTION. A row of a map's group is a question about that group -
    // "what does this concept become over here" - and the ask names the group's target system, so
    // the answer is the one the row is part of. A concept row of a code system names no target and
    // asks every map: a row click that answered nothing because a leftover target system was still
    // selected would look like a code with no mapping. The box is filled and the question sent as
    // the ask arrives rather than after the paint that carried it, so no frame shows the previous
    // code under a new answer.
    const [askedShown, setAskedShown] = useState(asked)
    if (askedShown !== asked) {
        setAskedShown(asked)
        if (asked.code !== '') {
            setEntered(asked.code)
            setTarget(asked.targetSystem ?? ANY_TARGET)
            setLookup((previous) => lookupFor(asked, (previous?.nonce ?? 0) + 1))
        }
    }

    useEffect(() => {
        if (lookup === null) return
        let cancelled = false
        translateCode(system, lookup.code, lookup.targetSystem === ANY_TARGET ? undefined : lookup.targetSystem)
            .then((parameters) => {
                if (cancelled) return
                setAnswered({ lookup, result: translationResult(parameters), error: null })
            })
            .catch((failure: unknown) => {
                if (cancelled) return
                setAnswered({
                    lookup,
                    result: null,
                    error: failure instanceof Error ? failure.message : String(failure),
                })
            })
        return () => {
            cancelled = true
        }
    }, [system, lookup])

    const running = lookup !== null && answered?.lookup !== lookup
    const result = answered?.result ?? null
    const error = running ? null : (answered?.error ?? null)

    return (
        <div className="space-y-4">
            <form
                className="flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                    event.preventDefault()
                    run(entered, target)
                }}
            >
                <div className="grid gap-1.5">
                    <Label htmlFor="translate-code">Concept code</Label>
                    <Input
                        id="translate-code"
                        className="w-56 font-mono"
                        placeholder="A code of this system"
                        value={entered}
                        onChange={(event) => setEntered(event.target.value)}
                    />
                </div>
                {targetSystems.length > 0 && (
                    <div className="grid gap-1.5">
                        <Label htmlFor="translate-target">Target system</Label>
                        <Select value={target} onValueChange={setTarget}>
                            <SelectTrigger id="translate-target" className="w-56">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={ANY_TARGET}>Any target system</SelectItem>
                                {targetSystems.map((candidate) => (
                                    <SelectItem key={candidate} value={candidate}>
                                        {systemLabel(candidate)}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                )}
                <Button type="submit" disabled={running || entered.trim() === ''}>
                    {running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                    Look up
                </Button>
            </form>

            <p className="machine-identifier text-xs break-all">
                GET /ConceptMap/$translate?system={system}&amp;code={entered || '...'}
                {target === ANY_TARGET ? '' : `&targetsystem=${target}`}
            </p>

            {error !== null && (
                <p className="text-destructive text-sm" role="alert">
                    {error}
                </p>
            )}

            {result !== null && error === null && <TranslationAnswer result={result} />}
        </div>
    )
}

/** What the operation answered: one row per mapping, or the message it stated instead. */
function TranslationAnswer({ result }: { result: TranslationResult }) {
    if (!result.matched || result.matches.length === 0) {
        return (
            <div className="space-y-1" data-testid="translate-result">
                <p className="text-sm font-medium">No mapping</p>
                <p className="text-muted-foreground text-sm">
                    {result.message === null ? (
                        'The maps served here state nothing for that code.'
                    ) : (
                        // The server marks the identifiers it quotes; a mark is a change of
                        // typeface, never a backtick sitting in the middle of a sentence.
                        <ProseText text={result.message} />
                    )}
                </p>
            </div>
        )
    }
    return (
        <div className="space-y-2" data-testid="translate-result">
            <p className="text-sm font-medium">
                {countedNoun(result.matches.length, 'mapping')}
            </p>
            <div className="grid gap-2">
                {result.matches.map((match) => (
                    <div
                        key={`${match.system ?? ''}-${match.code}`}
                        className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                    >
                        <span className="machine-identifier text-xs">
                            {systemLabel(match.system ?? undefined)}
                        </span>
                        <ArrowRight className="text-muted-foreground size-3.5" aria-hidden />
                        <span className="font-mono font-medium">{match.code}</span>
                        {match.display !== null && (
                            <span className="text-muted-foreground">{match.display}</span>
                        )}
                        {match.equivalence !== null && (
                            <Badge variant="secondary" className="text-[10px]">
                                {match.equivalence}
                            </Badge>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

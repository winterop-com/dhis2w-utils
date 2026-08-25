import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, Loader2 } from 'lucide-react'

import { ProseText } from '@/components/ProseText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { translateCode } from '@/lib/api'
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
 * `$translate`, as a thing to click.
 *
 * WHY THIS IS ON THE PAGE AT ALL. The whole point of the ConceptMaps is that a generated concept
 * code resolves back to the DHIS2 option uid and option code the forwarder writes - and until you
 * have asked the server, "the map says so" is a claim about a document rather than about the
 * running process. One button turns the claim into an answer from the same store the forwarder
 * reads.
 *
 * A code the maps say nothing about comes back as `result: false` with a message, HTTP 200. That
 * is not a failure of the call and is not rendered as one; only a refused request (a missing
 * parameter, an unreachable server) lands in the error line.
 *
 * THE ASK IS A PROP rather than local state, so a concept row can load the tester with the code it
 * names, and the call is made straight away when it does - a two-step "fill, then press" would
 * make the row button do half a thing. The panel sits beside the table it answers, always in
 * view, so an ask fills it in place and nothing on the page moves.
 */
export function TranslateTester({
    system,
    asked,
    targetSystems,
}: {
    /** The code system a concept is translated *from*, which is fixed by the page showing this. */
    system: string
    /** What a concept row asked about, or `NOTHING_ASKED` while the reader has pressed nothing. */
    asked: AskedConcept
    /** The target systems the maps land on, offered as a filter. Empty means offer no choice. */
    targetSystems: string[]
}) {
    const [entered, setEntered] = useState(asked.code)
    const [target, setTarget] = useState(ANY_TARGET)
    const [result, setResult] = useState<TranslationResult | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [running, setRunning] = useState(false)

    const run = useCallback(
        (code: string, targetSystem: string) => {
            if (code.trim() === '') return
            setRunning(true)
            setError(null)
            translateCode(system, code.trim(), targetSystem === ANY_TARGET ? undefined : targetSystem)
                .then((parameters) => setResult(translationResult(parameters)))
                .catch((failure: unknown) => {
                    setResult(null)
                    setError(failure instanceof Error ? failure.message : String(failure))
                })
                .finally(() => setRunning(false))
        },
        [system],
    )

    useEffect(() => {
        // THE ASK CARRIES ITS OWN DIRECTION. A row of a map's group is a question about that
        // group - "what does this concept become over here" - and the ask names the group's
        // target system, so the answer is the one the row is part of. A concept row of a code
        // system names no target and asks every map: a row click that answered nothing because a
        // leftover target system was still selected would look like a code with no mapping.
        if (asked.code === '') return
        const wanted = asked.targetSystem ?? ANY_TARGET
        setEntered(asked.code)
        setTarget(wanted)
        run(asked.code, wanted)
    }, [asked, run])

    return (
        <Card>
            <CardContent className="space-y-4 py-6">
                <div className="space-y-1">
                    <h3 className="text-base font-semibold">{TRANSLATE_QUESTION}</h3>
                    <p className="text-muted-foreground text-sm">
                        Type a concept code - or press Details on any row above - and the
                        published maps answer with the DHIS2 option UID and code it stands for.
                        On the wire this is the{' '}
                        <code className="font-mono">$translate</code> operation - the same one{' '}
                        <code className="font-mono">d2w fhir forward</code> resolves a coded answer
                        with.
                    </p>
                </div>

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

                <p className="text-muted-foreground font-mono text-xs break-all">
                    GET /ConceptMap/$translate?system={system}&amp;code={entered || '...'}
                    {target === ANY_TARGET ? '' : `&targetsystem=${target}`}
                </p>

                {error !== null && (
                    <p className="text-destructive text-sm" role="alert">
                        {error}
                    </p>
                )}

                {result !== null && error === null && <TranslationAnswer result={result} />}
            </CardContent>
        </Card>
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
                {result.matches.length} {result.matches.length === 1 ? 'mapping' : 'mappings'}
            </p>
            <div className="grid gap-2">
                {result.matches.map((match) => (
                    <div
                        key={`${match.system ?? ''}-${match.code}`}
                        className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm"
                    >
                        <span className="text-muted-foreground font-mono text-xs">
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

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { ExternalLink, Loader2, Plus, Send, Terminal, X } from 'lucide-react'
import { toast } from 'sonner'

import { CodeBlock, CodeEditor } from '@/components/CodeEditor'
import { PageHeader } from '@/components/PageState'
import { RAIL_TOGGLE_GUTTER, RailToggle } from '@/components/RailToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuth } from '@/hooks/use-auth'
import { usePlaygroundSamples } from '@/hooks/use-playground-samples'
import { useServerStatus } from '@/hooks/use-server-status'
import { useStatusLine } from '@/hooks/use-status-bar'
import { apiFetch, FHIR_JSON_MEDIA_TYPE } from '@/lib/api'
import {
    authorizationScheme,
    curlCommand,
    emptyParameter,
    formatHref,
    OPENING_REQUEST,
    playgroundPresets,
    prettyBody,
    presetShelves,
    readHistory,
    rememberSent,
    requestTarget,
    PLAYGROUND_METHODS,
    type PlaygroundMethod,
    type PlaygroundPreset,
    type PlaygroundRequest,
    type SentRequest,
    declaredParameters,
    type DeclaredParameter,
} from '@/lib/playground'
import { cn, RESIZE_HANDLE_TINT } from '@/lib/utils'

// How narrow and how wide the presets rail drags, and where the chosen width is remembered.
const PRESETS_RAIL_DEFAULT_WIDTH = 352
const PRESETS_RAIL_MINIMUM_WIDTH = 280
const PRESETS_RAIL_MAXIMUM_WIDTH = 640
const PRESETS_RAIL_WIDTH_STORAGE_KEY = 'playground-rail-width'

/** The width the reader last dragged the presets rail to, else its default (or storage is blocked). */
function storedPresetsRailWidth(): number {
    try {
        const kept = Number(window.localStorage.getItem(PRESETS_RAIL_WIDTH_STORAGE_KEY))
        return Number.isFinite(kept) && kept >= PRESETS_RAIL_MINIMUM_WIDTH && kept <= PRESETS_RAIL_MAXIMUM_WIDTH
            ? kept
            : PRESETS_RAIL_DEFAULT_WIDTH
    } catch {
        return PRESETS_RAIL_DEFAULT_WIDTH
    }
}

/** Remember a dragged rail width, silently letting go when storage is blocked. */
function keepPresetsRailWidth(width: number): void {
    try {
        window.localStorage.setItem(PRESETS_RAIL_WIDTH_STORAGE_KEY, String(Math.round(width)))
    } catch {
        // A private window forgets; the rail still resizes for this tab.
    }
}

/** What one send came back as: the status, how long it took, and the bytes. */
interface Answer {
    /** The status the server answered with, or null when nothing answered at all. */
    status: number | null
    /** What the status line of the response said, as the browser reports it. */
    statusText: string
    /** How long the round trip took, in whole milliseconds. */
    elapsed: number
    /** The body as it arrived, pretty-printed when it is JSON. */
    body: string
    /** What went wrong before there was a response at all, or null when something answered. */
    failure: string | null
}

/**
 * A place to send one request to this server and read exactly what it answers.
 *
 * WHY THE SCREEN EXISTS. Every other page here is a reading of this API: the Forms page is a
 * `GET /Questionnaire` with the answer laid out as cards, the Server page is `GET /metadata` laid out
 * as tables. Somebody writing an integration against this facade needs the other thing - the bytes,
 * under the status code, at an address they can copy - and until this page they had to leave the app
 * and reach for curl to get it. So this is the API itself, with the reading taken off.
 *
 * THE PRESETS ARE THIS SERVER'S OWN DECLARATION, not a written-down list of what a DHIS2 capture
 * server generally answers. Every row on the panel is derived from the CapabilityStatement this
 * process published plus one resource of each kind it was found to hold, so a guide publishing no
 * ConceptMaps offers no `$translate` row and a guide publishing forms offers a `$generate` that
 * answers on the first press. `lib/playground` builds the list and `use-playground-samples` reads
 * the two resources it is filled from.
 *
 * A PRESET NEVER SENDS ITSELF. Choosing one fills the builder and stops there. Half of what this
 * page teaches is what an address is made of, and a row that fired on click would answer the
 * question before a reader had read it - and would make a POST something that happens by pointing.
 *
 * AN OPERATIONOUTCOME IS THE ANSWER, NOT AN ERROR STATE. A refused read comes back as a document in
 * the same box a searchset does, under the status the server gave it. That is the whole posture of
 * this facade - a refusal is a FHIR resource saying why - and a page that hid it behind a red card
 * would be teaching the opposite of what the server does. The one thing that is not an answer is a
 * request nothing responded to, which says so in its own words.
 */
export function Playground() {
    const { capability } = useServerStatus()
    const samples = usePlaygroundSamples()
    const auth = useAuth()

    const [request, setRequest] = useState<PlaygroundRequest>(OPENING_REQUEST)
    const [answer, setAnswer] = useState<Answer | null>(null)
    const [sending, setSending] = useState(false)
    const [history, setHistory] = useState<SentRequest[]>([])
    // The panel choice lives for this mount of the page, exactly as the Evaluate screen's does. It
    // opens open: the builder holds one read and the panel is where every other address comes from.
    const [presetsShown, setPresetsShown] = useState(true)
    const [presetsWidth, setPresetsWidth] = useState<number>(() => storedPresetsRailWidth())

    // Read once, on the client, because storage is not there during a server-side render and a
    // useState initialiser reading it would run before the guard has anything to guard.
    useEffect(() => {
        setHistory(readHistory())
    }, [])

    const presets = useMemo(() => playgroundPresets(capability, samples), [capability, samples])
    const target = requestTarget(request)
    const scheme = authorizationScheme(auth.authorization)

    const load = useCallback((preset: PlaygroundPreset) => {
        setRequest(preset.request)
        setAnswer(null)
    }, [])

    const send = useCallback(() => {
        setSending(true)
        const sent = requestTarget(request)
        const started = performance.now()
        const carriesBody = request.method === 'POST' && request.body.trim() !== ''
        apiFetch(sent, {
            method: request.method,
            headers: carriesBody ? { 'Content-Type': FHIR_JSON_MEDIA_TYPE } : undefined,
            body: carriesBody ? request.body : undefined,
            cache: 'no-store',
        })
            .then(async (response) => {
                const body = await response.text()
                setAnswer({
                    status: response.status,
                    statusText: response.statusText,
                    elapsed: Math.round(performance.now() - started),
                    body: prettyBody(body),
                    failure: null,
                })
                setHistory((kept) => rememberSent(kept, { request, status: response.status }))
            })
            .catch((failure: unknown) => {
                setAnswer({
                    status: null,
                    statusText: '',
                    elapsed: Math.round(performance.now() - started),
                    body: '',
                    failure: failure instanceof Error ? failure.message : String(failure),
                })
                setHistory((kept) => rememberSent(kept, { request, status: null }))
            })
            .finally(() => setSending(false))
    }, [request])

    const copyCurl = useCallback(() => {
        const command = curlCommand(window.location.origin, request, scheme)
        void navigator.clipboard
            .writeText(command)
            .then(() => {
                toast.success('The curl command is on the clipboard')
            })
            .catch(() => {
                toast.error('This browser did not let the page write to the clipboard')
            })
    }, [request, scheme])

    // What is in the builder, and what the last send answered. Before anything has been sent there is
    // only the address, which is the fact the whole screen is arranged around.
    useStatusLine(
        answer === null
            ? `${request.method} ${target}`
            : answer.failure !== null
              ? `${request.method} ${target} - no answer`
              : `${request.method} ${target} - ${String(answer.status)} in ${String(answer.elapsed)} ms`,
    )

    return (
        <>
            <PageHeader
                title="Playground"
                description="Send one request to this server and read exactly what it answers. The presets beside the builder are this server's own declaration - one address per resource type it serves and per operation it declares."
            />

            <div
                className={cn(
                    'grid gap-6',
                    presetsShown
                        ? 'lg:grid-cols-[minmax(0,1fr)_var(--presets-rail-width)]'
                        : 'lg:grid-cols-[minmax(0,1fr)_auto]',
                )}
                style={{ '--presets-rail-width': `${String(presetsWidth)}px` } as CSSProperties}
            >
                <div className="flex min-w-0 flex-col gap-6">
                    <Card>
                        <CardContent className="flex flex-col gap-4 py-6">
                            <div className="flex flex-wrap items-end gap-3">
                                <div className="grid gap-1.5">
                                    <Label htmlFor="playground-method">Method</Label>
                                    <Select
                                        value={request.method}
                                        onValueChange={(value) =>
                                            setRequest({ ...request, method: value as PlaygroundMethod })
                                        }
                                    >
                                        <SelectTrigger
                                            id="playground-method"
                                            data-testid="playground-method"
                                            className="w-28 font-mono"
                                        >
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {PLAYGROUND_METHODS.map((method) => (
                                                <SelectItem key={method} value={method} className="font-mono">
                                                    {method}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="grid min-w-0 flex-1 gap-1.5">
                                    <Label htmlFor="playground-path">Path</Label>
                                    <Input
                                        id="playground-path"
                                        data-testid="playground-path"
                                        className="min-w-64 font-mono"
                                        value={request.path}
                                        onChange={(event) => setRequest({ ...request, path: event.target.value })}
                                    />
                                </div>

                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button
                                            type="button"
                                            onClick={send}
                                            disabled={sending || request.path.trim() === ''}
                                            data-testid="playground-send"
                                        >
                                            {sending ? (
                                                <Loader2 className="size-4 animate-spin" aria-hidden />
                                            ) : (
                                                <Send className="size-4" aria-hidden />
                                            )}
                                            Send
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>Send this request and show what the server answers</TooltipContent>
                                </Tooltip>
                            </div>

                            <p className="text-muted-foreground text-xs">
                                The path is relative to the service base, which is the address this page is
                                served from. Every request carries{' '}
                                <code className="font-mono">Accept: {FHIR_JSON_MEDIA_TYPE}</code>
                                {scheme === null
                                    ? ', and this browser is signing nothing.'
                                    : `, and the ${scheme} credential this browser holds.`}
                            </p>

                            <QueryParameters request={request} onChange={setRequest} declared={declaredParameters(capability, request.path)} />

                            {request.method === 'POST' && (
                                <div className="flex flex-col gap-1.5">
                                    <Label id="playground-body-label">Request body</Label>
                                    <CodeEditor
                                        value={request.body}
                                        onChange={(body) => setRequest({ ...request, body })}
                                        language="json"
                                        labelId="playground-body-label"
                                        testId="playground-body"
                                        className="shrink-0"
                                        minHeight="14rem"
                                        maxHeight="14rem"
                                    />
                                </div>
                            )}

                            <div className="flex flex-wrap items-center gap-2">
                                <Button type="button" variant="outline" size="sm" onClick={copyCurl}>
                                    <Terminal className="size-4" aria-hidden />
                                    Copy as curl
                                </Button>
                                {request.method === 'GET' && (
                                    <Button asChild variant="outline" size="sm">
                                        <a
                                            href={formatHref(window.location.origin, request)}
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            <ExternalLink className="size-4" aria-hidden />
                                            Open in a new tab
                                        </a>
                                    </Button>
                                )}
                                <span className="text-muted-foreground machine-identifier text-xs break-all">
                                    {target}
                                </span>
                            </div>
                        </CardContent>
                    </Card>

                    {answer !== null && <AnswerCard answer={answer} />}

                    {history.length > 0 && <History history={history} onLoad={setRequest} />}
                </div>

                <PresetsPanel
                    open={presetsShown}
                    onToggle={() => setPresetsShown(!presetsShown)}
                    onResize={setPresetsWidth}
                >
                    <Presets presets={presets} onLoad={load} />
                </PresetsPanel>
            </div>
        </>
    )
}

/**
 * The query string as rows, because a query string typed into a path is one long line to proofread.
 *
 * The rows and the path both feed the address, and neither owns it: a path pasted with its query
 * already on it keeps it, and a row is appended. `requestTarget` is where the two meet, and the
 * address they add up to is printed under the builder so there is never a question about what would
 * be sent.
 */
function QueryParameters({
    request,
    onChange,
    declared,
}: {
    request: PlaygroundRequest
    onChange: (next: PlaygroundRequest) => void
    /** What the current path is declared to answer, for the suggestions and the datalist. */
    declared: DeclaredParameter[]
}) {
    /** Fill the first nameless row with a suggested name, or append a row carrying it. */
    const suggest = (name: string) => {
        const empty = request.parameters.findIndex((parameter) => parameter.name.trim() === '')
        if (empty === -1) {
            onChange({ ...request, parameters: [...request.parameters, { name, value: '' }] })
            return
        }
        const parameters = request.parameters.map((parameter, position) =>
            position === empty ? { ...parameter, name } : parameter,
        )
        onChange({ ...request, parameters })
    }
    const setParameter = (index: number, next: Partial<{ name: string; value: string }>) => {
        const parameters = request.parameters.map((parameter, position) =>
            position === index ? { ...parameter, ...next } : parameter,
        )
        onChange({ ...request, parameters })
    }
    return (
        <div className="flex flex-col gap-2" data-testid="playground-parameters">
            <Label>Query parameters</Label>
            {declared.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-muted-foreground text-xs">This path answers</span>
                    {declared.map((parameter) => (
                        <button
                            key={parameter.name}
                            type="button"
                            onClick={() => suggest(parameter.name)}
                            title={parameter.documentation ?? undefined}
                            className="machine-identifier hover:bg-accent hover:text-accent-foreground rounded-full border px-2 py-0.5 text-[11px]"
                        >
                            {parameter.name}
                        </button>
                    ))}
                </div>
            )}
            <datalist id="playground-parameter-names">
                {declared.map((parameter) => (
                    <option key={parameter.name} value={parameter.name} />
                ))}
            </datalist>
            {request.parameters.map((parameter, index) => (
                // The index is the identity here on purpose: a row IS its position in the query
                // string, the rows carry no id of their own, and two rows may legitimately share a
                // name (`_tag` twice is a real search). Keying on the name would collapse those two
                // into one and lose whichever was typed second.
                // oxlint-disable-next-line react/no-array-index-key
                <div key={index} className="flex flex-wrap items-center gap-2">
                    <Input
                        aria-label={`Parameter ${String(index + 1)} name`}
                        className="w-48 font-mono"
                        list="playground-parameter-names"
                        value={parameter.name}
                        onChange={(event) => setParameter(index, { name: event.target.value })}
                    />
                    <Input
                        aria-label={`Parameter ${String(index + 1)} value`}
                        className="w-72 min-w-0 flex-1 font-mono"
                        value={parameter.value}
                        onChange={(event) => setParameter(index, { value: event.target.value })}
                    />
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove parameter ${String(index + 1)}`}
                        onClick={() =>
                            onChange({
                                ...request,
                                parameters: request.parameters.filter((_, position) => position !== index),
                            })
                        }
                    >
                        <X className="size-4" aria-hidden />
                    </Button>
                </div>
            ))}
            <div>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onChange({ ...request, parameters: [...request.parameters, emptyParameter()] })}
                >
                    <Plus className="size-4" aria-hidden />
                    Add a parameter
                </Button>
            </div>
        </div>
    )
}

/** What came back: the status and the round trip, over the bytes themselves. */
function AnswerCard({ answer }: { answer: Answer }) {
    return (
        <Card data-testid="playground-response">
            <CardContent className="space-y-3 py-6">
                <div className="flex flex-wrap items-baseline gap-3">
                    {answer.failure === null ? (
                        <>
                            <Badge variant={answer.status !== null && answer.status < 400 ? 'secondary' : 'outline'}>
                                <span className="font-mono">{answer.status}</span>
                                {answer.statusText !== '' && <span className="opacity-70"> {answer.statusText}</span>}
                            </Badge>
                            <span className="text-muted-foreground text-sm">{answer.elapsed} ms</span>
                        </>
                    ) : (
                        <span className="text-sm font-medium">Nothing answered this request</span>
                    )}
                </div>
                {answer.failure === null ? (
                    <CodeBlock
                        value={answer.body === '' ? '(the server answered with no body)' : answer.body}
                        language="json"
                        testId="playground-response-body"
                        maxHeight="32rem"
                    />
                ) : (
                    <p className="machine-identifier text-xs break-words">{answer.failure}</p>
                )}
            </CardContent>
        </Card>
    )
}

/** The last requests this browser sent, newest first, each one a click away from the builder again. */
function History({
    history,
    onLoad,
}: {
    history: SentRequest[]
    onLoad: (request: PlaygroundRequest) => void
}) {
    return (
        <Card data-testid="playground-history">
            <CardContent className="space-y-3 py-6">
                <div className="space-y-0.5">
                    <h3 className="text-base font-semibold">Sent requests</h3>
                    <p className="text-muted-foreground text-sm">
                        The last twenty requests sent from this browser, newest first. Choosing one puts it
                        back in the builder.
                    </p>
                </div>
                <div className="flex flex-col gap-1">
                    {history.map((sent, index) => (
                        // Two identical requests sent twice are two rows, and neither carries an id -
                        // the position in the list is what tells them apart.
                        // oxlint-disable-next-line react/no-array-index-key
                        <button key={index}
                            type="button"
                            onClick={() => onLoad(sent.request)}
                            className="hover:bg-muted focus-visible:ring-ring/50 flex items-baseline gap-2 rounded-md px-2 py-1.5 text-left focus-visible:ring-[3px] focus-visible:outline-none"
                        >
                            <span className="text-muted-foreground w-12 shrink-0 font-mono text-xs">
                                {sent.request.method}
                            </span>
                            <span className="min-w-0 flex-1 font-mono text-xs break-all">
                                {requestTarget(sent.request)}
                            </span>
                            <span className="text-muted-foreground shrink-0 font-mono text-xs">
                                {sent.status ?? 'no answer'}
                            </span>
                        </button>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}

/** Every address this server earns, shelved, each one a click away from being in the builder. */
function Presets({
    presets,
    onLoad,
}: {
    presets: PlaygroundPreset[]
    onLoad: (preset: PlaygroundPreset) => void
}) {
    return (
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pt-10" data-testid="playground-presets">
            {presetShelves(presets).map((shelf) => (
                <div key={shelf.group} className="space-y-1">
                    <h3 className="text-sm font-semibold">{shelf.group}</h3>
                    {shelf.presets.map((preset) => (
                        <button
                            key={preset.id}
                            type="button"
                            // The row's own id, so a browser test names the address it is clicking
                            // rather than matching prose that is free to be reworded.
                            data-preset={preset.id}
                            onClick={() => onLoad(preset)}
                            className="hover:bg-muted focus-visible:ring-ring/50 grid w-full gap-0.5 rounded-md px-2 py-1.5 text-left focus-visible:ring-[3px] focus-visible:outline-none"
                        >
                            <span className="font-mono text-xs break-all">{preset.label}</span>
                            <span className="text-muted-foreground text-xs">{preset.hint}</span>
                            {/* The label already shows the placeholder, so this says that one has to
                                be replaced and never repeats which one. */}
                            {!preset.runnable && (
                                <span className="text-muted-foreground text-xs italic">
                                    Replace the placeholder before sending.
                                </span>
                            )}
                        </button>
                    ))}
                </div>
            ))}
        </div>
    )
}

/**
 * The presets, beside the builder - and the way to fold them out of it.
 *
 * The Evaluate screen's examples rail, in the same corner and under the same control, because two
 * panels on two screens that fold the same way are one thing a reader learns once. `RailToggle`
 * states the geometry both of them stand on.
 */
function PresetsPanel({
    open,
    onToggle,
    onResize,
    children,
}: {
    open: boolean
    onToggle: () => void
    /** Take a dragged width, in CSS px - the page owns the column the width belongs to. */
    onResize: (width: number) => void
    children: ReactNode
}) {
    const beginResize = (event: ReactPointerEvent<HTMLDivElement>) => {
        event.preventDefault()
        const rail = event.currentTarget.parentElement
        if (rail === null) return
        const startX = event.clientX
        const startWidth = rail.getBoundingClientRect().width
        let latest = startWidth
        const follow = (move: PointerEvent) => {
            latest = Math.min(
                Math.max(startWidth + (startX - move.clientX), PRESETS_RAIL_MINIMUM_WIDTH),
                PRESETS_RAIL_MAXIMUM_WIDTH,
            )
            onResize(latest)
        }
        const release = () => {
            document.removeEventListener('pointermove', follow)
            document.removeEventListener('pointerup', release)
            keepPresetsRailWidth(latest)
        }
        document.addEventListener('pointermove', follow)
        document.addEventListener('pointerup', release)
    }
    return (
        <aside aria-label="Presets" className="relative min-w-0 self-start lg:sticky lg:top-6">
            <RailToggle open={open} railName="the presets" onToggle={onToggle} />
            {open && (
                <div
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize the presets"
                    onPointerDown={beginResize}
                    className={cn(
                        'absolute inset-y-0 -left-3 z-10 hidden w-1.5 cursor-col-resize touch-none rounded-full lg:block',
                        RESIZE_HANDLE_TINT,
                    )}
                />
            )}
            {open ? (
                <Card className="flex max-h-[calc(100vh-8rem)] flex-col">
                    <CardContent className="flex min-h-0 flex-1 flex-col gap-1 py-6">{children}</CardContent>
                </Card>
            ) : (
                <div aria-hidden className={RAIL_TOGGLE_GUTTER} />
            )}
        </aside>
    )
}

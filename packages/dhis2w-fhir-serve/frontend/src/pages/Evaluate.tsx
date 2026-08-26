import {
    useCallback,
    useEffect,
    useMemo,
    useState,
    type CSSProperties,
    type PointerEvent as ReactPointerEvent,
    type ReactNode,
} from 'react'
import { Loader2, Play } from 'lucide-react'

import { CodeBlock, CodeEditor, type EditorLanguage } from '@/components/CodeEditor'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EvaluateReference } from '@/components/EvaluateReference'
import { PageHeader } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { RAIL_TOGGLE_GUTTER, RailToggle } from '@/components/RailToggle'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useStatusLine } from '@/hooks/use-status-bar'
import { useUiConfig } from '@/hooks/use-ui-config'
import { evaluateExpression, searchResources } from '@/lib/api'
import {
    caretUnder,
    cellText,
    diagnosticHeadline,
    evaluationRequest,
    genericExamples,
    guidePresets,
    matchSummary,
    resultShape,
    sourceLine,
    whyNotReady,
    type EvaluationContextKind,
    type EvaluationDiagnostic,
    type EvaluationExample,
    type EvaluationForm,
    type EvaluationLanguage,
    type EvaluationOutcome,
    type EvaluationResultRow,
    type ServedResource,
} from '@/lib/evaluate'
import { trackedEntitySettings } from '@/lib/uiconfig'
import { cn, countedNoun, RESIZE_HANDLE_TINT } from '@/lib/utils'

/** The three languages, in the order the picker offers them, each under the name its own community uses. */
const LANGUAGES: { value: EvaluationLanguage; label: string }[] = [
    { value: 'fhirpath', label: 'FHIRPath' },
    { value: 'cql', label: 'CQL' },
    { value: 'elm', label: 'ELM' },
]

/**
 * The resource types a guide preset is built from, in the order they are looked for.
 *
 * Not every guide publishes all of them, and a guide that publishes none of them offers no presets
 * at all - which is a state rather than a gap, because the generic examples still run.
 */
const PRESET_RESOURCE_TYPES = ['Questionnaire', 'CodeSystem', 'ValueSet', 'ConceptMap'] as const

/** How many of this server's own resources the presets are built from - one per type, at most. */
const PRESET_LIMIT = 1

// How narrow and how wide the examples rail drags, and where the chosen width is remembered.
const EXAMPLES_RAIL_DEFAULT_WIDTH = 352
const EXAMPLES_RAIL_MINIMUM_WIDTH = 280
const EXAMPLES_RAIL_MAXIMUM_WIDTH = 640
const EXAMPLES_RAIL_WIDTH_STORAGE_KEY = 'evaluate-rail-width'

/** The width the reader last dragged the examples rail to, else its default (or storage is blocked). */
function storedExamplesRailWidth(): number {
    try {
        const kept = Number(window.localStorage.getItem(EXAMPLES_RAIL_WIDTH_STORAGE_KEY))
        return Number.isFinite(kept) &&
            kept >= EXAMPLES_RAIL_MINIMUM_WIDTH &&
            kept <= EXAMPLES_RAIL_MAXIMUM_WIDTH
            ? kept
            : EXAMPLES_RAIL_DEFAULT_WIDTH
    } catch {
        return EXAMPLES_RAIL_DEFAULT_WIDTH
    }
}

/** Remember a dragged rail width, silently letting go when storage is blocked. */
function keepExamplesRailWidth(width: number): void {
    try {
        window.localStorage.setItem(EXAMPLES_RAIL_WIDTH_STORAGE_KEY, String(Math.round(width)))
    } catch {
        // A private window forgets; the rail still resizes for this tab.
    }
}

/**
 * How each source language is coloured.
 *
 * ELM is JSON and is read by the JSON grammar, brace matching and all; the other two are read by the
 * stream tokenisers in `lib/codelang.ts`. One mapping, so the editor and any read-only rendering of
 * the same source cannot disagree about which language it is.
 */
export function editorLanguage(language: EvaluationLanguage): EditorLanguage {
    if (language === 'elm') return 'json'
    return language === 'cql' ? 'cql' : 'fhirpath'
}

/**
 * What the box is called, which is not the same thing in all three languages.
 *
 * A FHIRPath run is one expression; a CQL or ELM run is a library whose statements the server picks
 * from. "Source" covers both by naming neither, and a reader who has just chosen FHIRPath is owed
 * the word for what they are about to type.
 */
export function sourceLabel(language: EvaluationLanguage): string {
    return language === 'fhirpath' ? 'Expression' : 'Library source'
}

/**
 * A place to run an expression and see what this server answers.
 *
 * WHY THE SCREEN OPENS FULL. An expression box that opens empty teaches nothing: FHIRPath and CQL
 * are both languages a reader is meeting for the first time here, and an empty box plus an empty
 * context is two blanks to fill before anything happens at all. So the first generic example is
 * already loaded when the page arrives, and pressing Evaluate is the first thing a reader can do.
 *
 * THE EXAMPLES PANEL WAITS IN THE CORNER. The second thing a reader does is wonder what else they
 * could have written, and the answer is a list of what this engine implements rather than a search
 * engine: the rail expands from its corner control holding the runnable examples on one tab and
 * each language's own vocabulary on the tab named for it - the same affordance the organisation
 * units page's inspector rail carries, in the same words. It starts folded because the editor
 * already holds a runnable example, so the panel is the second question's answer, not the first
 * screen's furniture. `lib/reference.ts` states why the subset is ours rather than the
 * specification's.
 *
 * TWO KINDS OF EXAMPLE IN ONE MENU. The generic ones carry their own data and run identically
 * against any served guide, including one that publishes nothing. The presets underneath are built
 * from resources this particular server was found to hold, so they show the same language pointed at
 * the reader's own project. `lib/evaluate` states which is which and why.
 *
 * A BAD EXPRESSION IS NOT AN ERROR HERE. The server answers 200 with the line and column its parser
 * stopped on, so a parse failure is rendered where a reader can act on it - the offending line, with
 * a caret under the character - rather than in the red box that means the server refused the
 * request. That box is kept for what it is: a refusal, which is what a resource this guide does not
 * hold, or a register this run does not publish, answers with.
 */
export function Evaluate() {
    const { config } = useUiConfig()
    const registerOffered = trackedEntitySettings(config).enabled
    const registerResource = trackedEntitySettings(config).registers[0]?.resource ?? 'Patient'

    const [served, setServed] = useState<ServedResource[]>([])
    // THE EXPRESSION STARTS EMPTY; THE CONTEXT DOES NOT. The question is the reader's - an
    // expression already in the box on arrival is somebody else's, and running it teaches only
    // that the button works. The simple example Patient stays in the context box, so the first
    // expression written has something to answer over, and the examples wait one glance to the
    // right, each runnable as it stands.
    const [form, setForm] = useState<EvaluationForm>(() => ({
        ...genericExamples('fhirpath')[0].form,
        source: '',
    }))
    // Which example is in the editor, read off the editor rather than remembered from the last
    // click: an example is what is in the box, not what was once put there, so the highlight
    // holds exactly as long as the source does and typing over it answers for itself.
    const [loaded, setLoaded] = useState({ id: '', source: '' })
    const chosenExample = loaded.id !== '' && form.source === loaded.source ? loaded.id : ''
    const [outcome, setOutcome] = useState<EvaluationOutcome | null>(null)
    const [refusal, setRefusal] = useState<string | null>(null)
    const [running, setRunning] = useState(false)
    // The panel choice lives for this mount of the page and nowhere else - deliberately plain
    // state, not storage, on the same argument the organisation units page makes about its
    // inspector rail. It opens open: the editor arrives empty, so the screen's first job is
    // picking an example or writing an expression, and the list is where that starts.
    const [examplesShown, setExamplesShown] = useState(true)
    // The rail's dragged width - a standing preference, unlike the open/shut choice above.
    const [examplesWidth, setExamplesWidth] = useState<number>(() => storedExamplesRailWidth())

    // What this guide holds, read once: one resource per type the presets know how to ask about.
    // A type this server does not serve answers a refusal, which is not an error here - it is the
    // reason that type contributes no preset.
    useEffect(() => {
        let cancelled = false
        const found: ServedResource[] = []
        const reads = PRESET_RESOURCE_TYPES.map((resourceType) =>
            searchResources<{ id?: string; title?: string; name?: string }>(resourceType, {
                _count: String(PRESET_LIMIT),
            })
                .then((bundle) => {
                    const resource = bundle.entry?.[0]?.resource
                    if (resource?.id === undefined) return
                    found.push({
                        resourceType,
                        resourceId: resource.id,
                        title: resource.title ?? resource.name ?? null,
                    })
                })
                .catch(() => undefined),
        )
        void Promise.all(reads).then(() => {
            if (!cancelled) setServed(found)
        })
        return () => {
            cancelled = true
        }
    }, [])


    // The panel browses all three languages whatever the editor speaks; the current one leads.
    const examplesByLanguage = useMemo(
        () =>
            Object.fromEntries(
                (['fhirpath', 'cql', 'elm'] as const).map((candidate) => [
                    candidate,
                    [...genericExamples(candidate), ...guidePresets(candidate, served)],
                ]),
            ) as Record<EvaluationLanguage, EvaluationExample[]>,
        [served],
    )

    const load = useCallback((example: EvaluationExample) => {
        setLoaded({ id: example.id, source: example.form.source })
        setForm(example.form)
        setOutcome(null)
        setRefusal(null)
    }, [])

    const pickLanguage = useCallback(
        (language: EvaluationLanguage) => {
            // The example goes with the language: a CQL library left in the box under FHIRPath would
            // be a parse error the reader did not ask for.
            load(genericExamples(language)[0])
        },
        [load],
    )

    const notReady = whyNotReady(form)

    const run = useCallback(() => {
        if (whyNotReady(form) !== null) return
        setRunning(true)
        setRefusal(null)
        evaluateExpression(evaluationRequest(form))
            .then((answered) => {
                setOutcome(answered)
                setRefusal(null)
            })
            .catch((failure: unknown) => {
                setOutcome(null)
                setRefusal(failure instanceof Error ? failure.message : String(failure))
            })
            .finally(() => setRunning(false))
    }, [form])

    // What language is loaded, and what the last run answered. Before anything has been run there
    // is only the language, which is the fact the whole screen is arranged around; a refusal says
    // so rather than reading as an answer of no values, because those are different outcomes.
    const languageLabel =
        LANGUAGES.find((candidate) => candidate.value === form.language)?.label ?? form.language
    const values = outcome === null ? null : outcome.results.reduce((total, result) => total + result.values.length, 0)
    useStatusLine(
        refusal !== null
            ? `${languageLabel} - the server refused this evaluation`
            : values === null
              ? languageLabel
              : `${languageLabel} - ${countedNoun(values, 'value')}`,
    )

    return (
        <>
            <PageHeader
                title="Evaluate"
                description="Run a FHIRPath expression, a CQL library, or a compiled ELM library against what this server serves. Write your own, or pick one of the examples beside the editor - every one of them runs as it stands."
            />

            {/* THE EDITORS HOLD THEIR SIZE. Loading an example, and an answer arriving
                underneath, must move nothing: a screen that reflows between the click and the
                result reads as jumping around, and the reader loses the line they were on. So
                both boxes own a fixed height and scroll inside it - a long library or a pasted
                Bundle scrolls in place, and the page below only ever grows downward. */}
            <div
                className={cn(
                    'grid gap-6',
                    examplesShown
                        ? 'lg:grid-cols-[minmax(0,1fr)_var(--examples-rail-width)]'
                        : 'lg:grid-cols-[minmax(0,1fr)_auto]',
                )}
                style={{ '--examples-rail-width': `${String(examplesWidth)}px` } as CSSProperties}
            >
                <div className="flex min-w-0 flex-col gap-6">
                    <Card className="flex flex-col">
                        <CardContent className="flex flex-col gap-4 py-6">
                            <div className="flex flex-wrap items-end gap-3">
                                <div className="grid gap-1.5">
                                    <Label htmlFor="evaluate-language">Language</Label>
                                    <Select
                                        value={form.language}
                                        onValueChange={(value) => pickLanguage(value as EvaluationLanguage)}
                                    >
                                        <SelectTrigger id="evaluate-language" className="w-40">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {LANGUAGES.map((language) => (
                                                <SelectItem key={language.value} value={language.value}>
                                                    {language.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {form.language !== 'fhirpath' && (
                                    <div className="grid gap-1.5">
                                        <Label htmlFor="evaluate-define">Define to answer</Label>
                                        <Input
                                            id="evaluate-define"
                                            className="w-56 font-mono"
                                            placeholder="every define"
                                            value={form.expressionName}
                                            onChange={(event) =>
                                                setForm({ ...form, expressionName: event.target.value })
                                            }
                                        />
                                    </div>
                                )}

                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <Button type="button" onClick={run} disabled={running || notReady !== null}>
                                            {running ? (
                                                <Loader2 className="size-4 animate-spin" aria-hidden />
                                            ) : (
                                                <Play className="size-4" aria-hidden />
                                            )}
                                            Evaluate
                                        </Button>
                                    </TooltipTrigger>
                                    <TooltipContent>Run this and show what the server answers</TooltipContent>
                                </Tooltip>

                            </div>

                            <div className="flex flex-col gap-1.5">
                                <Label id="evaluate-source-label" className="shrink-0">
                                    {sourceLabel(form.language)}
                                </Label>
                                <CodeEditor
                                    value={form.source}
                                    onChange={(source) => setForm({ ...form, source })}
                                    language={editorLanguage(form.language)}
                                    labelId="evaluate-source-label"
                                    testId="evaluate-source"
                                    lineNumbersShown={form.language !== 'fhirpath'}
                                    className="shrink-0"
                                    minHeight="16rem"
                                    maxHeight="16rem"
                                />
                            </div>

                            <ContextPicker
                                form={form}
                                onChange={setForm}
                                registerOffered={registerOffered}
                                registerResource={registerResource}
                            />

                            {notReady !== null && <p className="text-muted-foreground text-sm">{notReady}</p>}
                        </CardContent>
                    </Card>

                    {refusal !== null && (
                        <Card>
                            <CardContent className="space-y-1 py-6">
                                <p className="text-sm font-medium">The server refused this evaluation</p>
                                <p className="machine-identifier text-xs break-words">{refusal}</p>
                            </CardContent>
                        </Card>
                    )}

                    {outcome !== null && refusal === null && (
                        <Answer outcome={outcome} source={form.source} />
                    )}
                </div>

                <ExamplesPanel
                    open={examplesShown}
                    onToggle={() => setExamplesShown(!examplesShown)}
                    onResize={setExamplesWidth}
                >
                    <EvaluateReference
                        language={form.language}
                        examplesByLanguage={examplesByLanguage}
                        chosen={chosenExample}
                        onLoad={load}
                    />
                </ExamplesPanel>
            </div>
        </>
    )
}

/**
 * The examples, beside the box - and the way to fold them out of it.
 *
 * THE PANEL CARRIES ITS OWN CONTROL, rather than a toolbar button above the editor saying whether
 * something on the other side of the screen is there. A control belongs to the thing it acts on, and
 * a reader who wants the width back reaches for the edge of the panel taking it. Collapsed, it is a
 * strip holding the way back, so the panel never disappears without leaving a door.
 *
 * The affordance is the organisation units page's inspector rail, deliberately: two panels on two
 * screens that fold the same way are one thing a reader learns once.
 */
function ExamplesPanel({
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
                Math.max(startWidth + (startX - move.clientX), EXAMPLES_RAIL_MINIMUM_WIDTH),
                EXAMPLES_RAIL_MAXIMUM_WIDTH,
            )
            onResize(latest)
        }
        const release = () => {
            document.removeEventListener('pointermove', follow)
            document.removeEventListener('pointerup', release)
            keepExamplesRailWidth(latest)
        }
        document.addEventListener('pointermove', follow)
        document.addEventListener('pointerup', release)
    }
    // The shared RailToggle holds the corner; the sized placeholder is what keeps the collapsed
    // column as wide as the button, and the card's top stays level with the editor card's.
    return (
        // `self-start` keeps the rail its own height inside a row that now stretches, which is what
        // leaves `sticky` something to do once an answer has made the page longer than the window.
        <aside aria-label="Examples" className="relative min-w-0 self-start lg:sticky lg:top-6">
            <RailToggle open={open} railName="the examples" onToggle={onToggle} />
            {open && (
                <div
                    role="separator"
                    aria-orientation="vertical"
                    aria-label="Resize the examples"
                    onPointerDown={beginResize}
                    className={cn(
                        'absolute inset-y-0 -left-3 z-10 hidden w-1.5 cursor-col-resize touch-none rounded-full lg:block',
                        RESIZE_HANDLE_TINT,
                    )}
                />
            )}
            {open ? (
                /* The card is what the viewport bounds, and the panel inside it decides which of
                   its parts scrolls - which is what keeps the language tabs on screen while the
                   shelves under them move. */
                <Card className="flex max-h-[calc(100vh-8rem)] flex-col">
                    <CardContent className="flex min-h-0 flex-1 flex-col gap-1 py-6">{children}</CardContent>
                </Card>
            ) : (
                /* Exactly as wide as the control standing in it, so the collapsed rail is the
                   button and not a gutter with a button loose in it. */
                <div aria-hidden className={RAIL_TOGGLE_GUTTER} />
            )}
        </aside>
    )
}

/** Which resource the expression runs over, offering exactly what the server offers and nothing more. */
function ContextPicker({
    form,
    onChange,
    registerOffered,
    registerResource,
}: {
    form: EvaluationForm
    onChange: (form: EvaluationForm) => void
    /** Whether this run reaches a DHIS2 instance, which is what makes the register a real option. */
    registerOffered: boolean
    /** The FHIR resource this run serves its tracked entities as, which the request has to name. */
    registerResource: string
}) {
    const context = form.context
    const setKind = (kind: EvaluationContextKind) =>
        onChange({ ...form, context: { ...context, kind, registerResource } })

    return (
        // The column grows only when it holds an editor: a resource id and a UID are one row each,
        // and a picker stretched over the leftover height would be dead air with a select in it.
        <div className={cn('flex flex-col gap-3', context.kind === 'inline' && 'min-h-0 flex-1')}>
            <div className="grid gap-1.5">
                <Label htmlFor="evaluate-context">Context</Label>
                <Select value={context.kind} onValueChange={(value) => setKind(value as EvaluationContextKind)}>
                    <SelectTrigger id="evaluate-context" className="w-80">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="inline">A resource pasted below</SelectItem>
                        <SelectItem value="stored">A resource from this guide</SelectItem>
                        {registerOffered && (
                            <SelectItem value="registered">
                                A tracked entity this DHIS2 instance holds
                            </SelectItem>
                        )}
                        <SelectItem value="none">No resource at all</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {context.kind === 'inline' && (
                <div className="flex flex-col gap-1.5">
                    <Label id="evaluate-resource-label">Context resource</Label>
                    <CodeEditor
                        value={context.resource}
                        onChange={(resource) => onChange({ ...form, context: { ...context, resource } })}
                        language="json"
                        labelId="evaluate-resource-label"
                        testId="evaluate-context-resource"
                        className="shrink-0"
                        minHeight="14rem"
                        maxHeight="14rem"
                    />
                </div>
            )}

            {context.kind === 'stored' && (
                <div className="flex flex-wrap items-end gap-3">
                    <div className="grid gap-1.5">
                        <Label htmlFor="evaluate-resource-type">Resource type</Label>
                        <Input
                            id="evaluate-resource-type"
                            className="w-56 font-mono"
                            value={context.resourceType}
                            onChange={(event) =>
                                onChange({
                                    ...form,
                                    context: { ...context, resourceType: event.target.value },
                                })
                            }
                        />
                    </div>
                    <div className="grid gap-1.5">
                        <Label htmlFor="evaluate-resource-id">Resource id</Label>
                        <Input
                            id="evaluate-resource-id"
                            className="w-56 font-mono"
                            value={context.resourceId}
                            onChange={(event) =>
                                onChange({ ...form, context: { ...context, resourceId: event.target.value } })
                            }
                        />
                    </div>
                </div>
            )}

            {context.kind === 'registered' && (
                <div className="grid gap-1.5">
                    <Label htmlFor="evaluate-tracked-entity">Tracked entity UID</Label>
                    <Input
                        id="evaluate-tracked-entity"
                        className="w-56 font-mono"
                        value={context.trackedEntityUid}
                        onChange={(event) =>
                            onChange({
                                ...form,
                                context: { ...context, trackedEntityUid: event.target.value },
                            })
                        }
                    />
                    <p className="text-muted-foreground text-xs">
                        Read from this DHIS2 instance and served as {registerResource}, exactly as the
                        register serves it.
                    </p>
                </div>
            )}
        </div>
    )
}

/** What the server answered: the diagnostics first, because they are why anything is missing. */
function Answer({ outcome, source }: { outcome: EvaluationOutcome; source: string }) {
    return (
        <div className="space-y-4" data-testid="evaluate-answer">
            {outcome.diagnostics.map((diagnostic, index) => (
                <Diagnostic
                    key={`${diagnostic.kind}-${String(index)}`}
                    diagnostic={diagnostic}
                    source={source}
                />
            ))}
            {outcome.results.map((result) => (
                <ResultCard key={result.name} result={result} />
            ))}
            {outcome.results.length === 0 && outcome.diagnostics.length === 0 && (
                <Card>
                    <CardContent className="text-muted-foreground py-6 text-sm">
                        This library declares no defines, so there was nothing to answer.
                    </CardContent>
                </Card>
            )}
        </div>
    )
}

/**
 * One diagnostic, shown at the line it names - with the line itself and a caret under the column.
 *
 * The one place on this screen that stays a plain `<pre>` rather than becoming a highlighted block:
 * what makes it readable is that the caret sits under the character the parser stopped on, and that
 * only holds while the two lines share one metric and neither of them wraps. Colour would buy nothing
 * here and a wrapped line would cost the whole point.
 */
function Diagnostic({ diagnostic, source }: { diagnostic: EvaluationDiagnostic; source: string }) {
    const line = sourceLine(source, diagnostic.line)
    return (
        <Card>
            <CardContent className="space-y-2 py-6">
                <p className="text-sm font-medium">{diagnosticHeadline(diagnostic)}</p>
                {line !== null && (
                    <pre className="show-scrollbars bg-muted overflow-x-auto rounded-md p-3 font-mono text-xs">
                        {line}
                        {'\n'}
                        {caretUnder(line, diagnostic.column)}
                    </pre>
                )}
                <p className="machine-identifier text-xs break-words whitespace-pre-wrap">
                    {diagnostic.message}
                </p>
                {diagnostic.expression_name !== null && (
                    <Badge variant="secondary">{diagnostic.expression_name}</Badge>
                )}
            </CardContent>
        </Card>
    )
}

/** One define's answer on two tabs: the table reading, and the raw JSON the server sent. */
function ResultCard({ result }: { result: EvaluationResultRow }) {
    const shape = resultShape(result.values)
    return (
        <Card>
            <CardContent className="space-y-3 py-6">
                <div className="flex flex-wrap items-baseline gap-3">
                    <h3 className="font-mono text-sm font-semibold">{result.name}</h3>
                    {result.refusal === null && (
                        <span className="text-muted-foreground text-sm">
                            {matchSummary(result.values.length)}
                        </span>
                    )}
                </div>

                {result.refusal !== null && (
                    <p className="machine-identifier text-xs break-words whitespace-pre-wrap">
                        {result.refusal}
                    </p>
                )}

                {result.refusal === null && (
                    <Tabs defaultValue={shape === 'table' ? 'table' : 'raw'} className="gap-3">
                        <TabsList>
                            <TabsTrigger value="table">Table</TabsTrigger>
                            <TabsTrigger value="raw">Raw</TabsTrigger>
                        </TabsList>
                        <TabsContent value="table">
                            <div className="show-scrollbars overflow-x-auto rounded-lg border">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead className="w-16">#</TableHead>
                                            <TableHead>Value</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {result.values.map((value, index) => (
                                            <TableRow key={`${result.name}-${String(index)}`}>
                                                <TableCell className="machine-identifier text-xs">
                                                    {index + 1}
                                                </TableCell>
                                                <TableCell className="font-mono text-xs">
                                                    {cellText(value)}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </TabsContent>
                        <TabsContent value="raw">
                            <CodeBlock
                                value={JSON.stringify(result.values, null, 2)}
                                testId="evaluate-result-json"
                            />
                        </TabsContent>
                    </Tabs>
                )}
            </CardContent>
        </Card>
    )
}

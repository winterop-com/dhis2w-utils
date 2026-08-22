import { useCallback, useEffect, useMemo, useState } from 'react'
import { BookOpen, Loader2, Play } from 'lucide-react'

import { CodeBlock, CodeEditor, type EditorLanguage } from '@/components/CodeEditor'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EvaluateReference } from '@/components/EvaluateReference'
import { PageHeader } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectGroup,
    SelectItem,
    SelectLabel,
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
import { useUiConfig } from '@/hooks/use-ui-config'
import { evaluateExpression, searchResources } from '@/lib/api'
import {
    caretUnder,
    cellText,
    diagnosticHeadline,
    evaluationRequest,
    exampleGroups,
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
import { cn } from '@/lib/utils'

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
 * A place to run an expression and see what this server answers.
 *
 * WHY THE SCREEN OPENS FULL. An expression box that opens empty teaches nothing: FHIRPath and CQL
 * are both languages a reader is meeting for the first time here, and an empty box plus an empty
 * context is two blanks to fill before anything happens at all. So the first generic example is
 * already loaded when the page arrives, and pressing Evaluate is the first thing a reader can do.
 *
 * WHY THE REFERENCE IS OPEN BESIDE IT. The second thing a reader does is wonder what else they could
 * have written, and the answer to that is a list of what this engine implements rather than a search
 * engine. So the panel opens with the screen, holding the examples on one tab and the language's own
 * vocabulary on the other, and the button in the toolbar folds it away for somebody who already knows.
 * `lib/reference.ts` states why the subset is ours rather than the specification's.
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
    const [form, setForm] = useState<EvaluationForm>(() => genericExamples('fhirpath')[0].form)
    const [chosenExample, setChosenExample] = useState('fhirpath-given-names')
    const [outcome, setOutcome] = useState<EvaluationOutcome | null>(null)
    const [refusal, setRefusal] = useState<string | null>(null)
    const [running, setRunning] = useState(false)
    const [referenceShown, setReferenceShown] = useState(true)

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

    const generic = useMemo(() => genericExamples(form.language), [form.language])
    const presets = useMemo(() => guidePresets(form.language, served), [form.language, served])
    const offered = useMemo(() => [...generic, ...presets], [generic, presets])

    const load = useCallback((example: EvaluationExample) => {
        setChosenExample(example.id)
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

    return (
        <>
            <PageHeader
                title="Evaluate"
                description="Run a FHIRPath expression, a CQL library, or a compiled ELM library against what this server serves. Pick an example to start with; every one of them runs as it stands."
            />

            <div
                className={cn(
                    'grid items-start gap-6',
                    referenceShown && 'lg:grid-cols-[minmax(0,1fr)_22rem]',
                )}
            >
                <div className="min-w-0 space-y-6">
                    <Card>
                        <CardContent className="space-y-4 py-6">
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

                                <div className="grid gap-1.5">
                                    <Label htmlFor="evaluate-example">Example</Label>
                                    <Select
                                        value={chosenExample}
                                        onValueChange={(value) => {
                                            const picked = offered.find((example) => example.id === value)
                                            if (picked !== undefined) load(picked)
                                        }}
                                    >
                                        <SelectTrigger id="evaluate-example" className="w-80">
                                            <SelectValue placeholder="Pick an example" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {exampleGroups(offered).map((shelf) => (
                                                <SelectGroup key={shelf.group}>
                                                    <SelectLabel>{shelf.group}</SelectLabel>
                                                    {shelf.examples.map((example) => (
                                                        <SelectItem key={example.id} value={example.id}>
                                                            {example.label}
                                                        </SelectItem>
                                                    ))}
                                                </SelectGroup>
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

                                <Button type="button" onClick={run} disabled={running || notReady !== null}>
                                    {running ? (
                                        <Loader2 className="size-4 animate-spin" aria-hidden />
                                    ) : (
                                        <Play className="size-4" aria-hidden />
                                    )}
                                    Evaluate
                                </Button>

                                <Button
                                    type="button"
                                    variant="outline"
                                    aria-expanded={referenceShown}
                                    onClick={() => setReferenceShown(!referenceShown)}
                                >
                                    <BookOpen className="size-4" aria-hidden />
                                    Reference
                                </Button>
                            </div>

                            <div className="grid gap-1.5">
                                <Label id="evaluate-source-label">Source</Label>
                                <CodeEditor
                                    value={form.source}
                                    onChange={(source) => setForm({ ...form, source })}
                                    language={editorLanguage(form.language)}
                                    labelId="evaluate-source-label"
                                    testId="evaluate-source"
                                    lineNumbersShown={form.language !== 'fhirpath'}
                                    minHeight="9rem"
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
                                <p className="text-muted-foreground font-mono text-xs break-words">{refusal}</p>
                            </CardContent>
                        </Card>
                    )}

                    {outcome !== null && refusal === null && (
                        <Answer outcome={outcome} source={form.source} />
                    )}
                </div>

                {referenceShown && (
                    <aside className="min-w-0 lg:sticky lg:top-6">
                        <Card>
                            <CardContent className="show-scrollbars max-h-[calc(100vh-8rem)] overflow-y-auto py-6">
                                <EvaluateReference
                                    language={form.language}
                                    examples={offered}
                                    chosen={chosenExample}
                                    onLoad={load}
                                />
                            </CardContent>
                        </Card>
                    </aside>
                )}
            </div>
        </>
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
        <div className="space-y-3">
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
                                A person this DHIS2 instance holds
                            </SelectItem>
                        )}
                        <SelectItem value="none">No resource at all</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {context.kind === 'inline' && (
                <div className="grid gap-1.5">
                    <Label id="evaluate-resource-label">Context resource</Label>
                    <CodeEditor
                        value={context.resource}
                        onChange={(resource) => onChange({ ...form, context: { ...context, resource } })}
                        language="json"
                        labelId="evaluate-resource-label"
                        testId="evaluate-context-resource"
                        minHeight="9rem"
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
                    <Label htmlFor="evaluate-tracked-entity">Tracked entity uid</Label>
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
                <p className="text-muted-foreground font-mono text-xs break-words whitespace-pre-wrap">
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
                    <p className="text-muted-foreground font-mono text-xs break-words whitespace-pre-wrap">
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
                                                <TableCell className="text-muted-foreground font-mono text-xs">
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

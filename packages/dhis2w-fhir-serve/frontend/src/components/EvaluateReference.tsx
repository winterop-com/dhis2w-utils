import { useEffect, useState } from 'react'

import { ProseText } from '@/components/ProseText'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { exampleGroups, type EvaluationExample, type EvaluationLanguage } from '@/lib/evaluate'
import { languageReference, type LanguageReference } from '@/lib/reference'
import { cn } from '@/lib/utils'

/**
 * What this server answers, beside the box somebody is writing in.
 *
 * WHY A PANEL AND NOT A LINK TO THE DOCUMENTATION. A reader meeting FHIRPath for the first time does
 * not know what to search for: the question is "what can I even write here", and the answer is a list
 * of the things this engine implements. A link sends them to another tab to read prose; a panel puts
 * the vocabulary a metre from the cursor, so a half-remembered function name is a glance rather than
 * a context switch. The prose is still where the argument lives - each language's reference names its
 * own published page - and this is the part of it that belongs beside the keyboard.
 *
 * WHY THE EXAMPLES ARE IN THE SAME PANEL. A vocabulary list teaches names and nothing else. What
 * turns a name into something a person can use is one worked expression they can run without typing
 * it, so the examples share the panel and load into the editor on a click. Every one of them runs as
 * it stands - `lib/evaluate.ts` states why that is a rule rather than an aspiration.
 *
 * WHY THE REFUSALS ARE LISTED WITH THE REST. Half of learning a language here is learning what it
 * says no to, and this engine says no loudly on purpose. A shelf named for the refusals, with each
 * one stated beside the thing it refuses, is the difference between a reader recognising a message
 * and a reader filing a bug.
 */
export function EvaluateReference({
    language,
    examplesByLanguage,
    chosen,
    onLoad,
}: {
    language: EvaluationLanguage
    /** Every example on offer, per language, generic and guide-built alike - the browser shows all three. */
    examplesByLanguage: Record<EvaluationLanguage, EvaluationExample[]>
    /** Which one is loaded, so the list can mark it rather than leaving the reader to remember. */
    chosen: string
    onLoad: (example: EvaluationExample) => void
}) {
    // All three references stay on the bar whatever the editor speaks: a reader writing FHIRPath
    // still gets to read what CQL answers without touching the language picker. Changing the
    // language moves an open reference tab to the new language's own, and leaves Examples alone.
    const [tab, setTab] = useState('examples')
    useEffect(() => {
        setTab((current) => (current === 'examples' ? current : language))
    }, [language])
    return (
        // THE TAB BAR IS OUTSIDE THE SCROLLER, and the shelves under it are what scrolls. The panel
        // is eighty rows tall on a real project, so a bar that scrolled with its content was off
        // screen for the whole of the reading a reader does - nine hundred pixels back up to reach
        // the language whose vocabulary they wanted. The column claims the height the page gives it
        // and hands the leftover to the one element that has more than fits.
        <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col gap-3">
            <TabsList className="shrink-0">
                <TabsTrigger value="examples">Examples</TabsTrigger>
                {REFERENCE_LANGUAGES.map((candidate) => (
                    <TabsTrigger key={candidate} value={candidate}>
                        {languageReference(candidate).title}
                    </TabsTrigger>
                ))}
            </TabsList>
            <div className="show-scrollbars min-h-0 flex-1 overflow-y-auto">
                <TabsContent value="examples">
                    <ExampleBrowser
                        language={language}
                        examplesByLanguage={examplesByLanguage}
                        chosen={chosen}
                        onLoad={onLoad}
                    />
                </TabsContent>
                {REFERENCE_LANGUAGES.map((candidate) => (
                    <TabsContent key={candidate} value={candidate}>
                        <ReferenceBody reference={languageReference(candidate)} />
                    </TabsContent>
                ))}
            </div>
        </Tabs>
    )
}

/** The three languages the panel documents, in the order the picker offers them. */
const REFERENCE_LANGUAGES: EvaluationLanguage[] = ['fhirpath', 'cql', 'elm']

/**
 * Every example, on its shelf, each one a button that loads it.
 *
 * The label is what the example answers rather than what it demonstrates, so the list reads as a set
 * of questions somebody might have. The one that is loaded is marked, because a reader who clicked
 * three in a row otherwise has no way to tell which of them is in the box.
 */
function ExampleBrowser({
    language,
    examplesByLanguage,
    chosen,
    onLoad,
}: {
    language: EvaluationLanguage
    examplesByLanguage: Record<EvaluationLanguage, EvaluationExample[]>
    chosen: string
    onLoad: (example: EvaluationExample) => void
}) {
    // The editor's own language leads; the other two follow under their names, because an example
    // is a door into its language - loading one switches the editor over, context and all.
    const ordered = [language, ...REFERENCE_LANGUAGES.filter((candidate) => candidate !== language)]
    const total = ordered.reduce((count, candidate) => count + examplesByLanguage[candidate].length, 0)
    return (
        <div className="space-y-5" data-testid="evaluate-examples">
            <p className="text-muted-foreground text-xs">
                {total} examples across the three languages, each one runnable as it stands. Choosing one
                replaces what is in the editor, and one from another language brings its language along.
            </p>
            {ordered.map((candidate) => (
                <section key={candidate} className="space-y-4">
                    <h2 className="border-b pb-1 text-xs font-semibold">
                        {languageReference(candidate).title}
                    </h2>
                    <LanguageShelves
                        examples={examplesByLanguage[candidate]}
                        chosen={chosen}
                        onLoad={onLoad}
                    />
                </section>
            ))}
        </div>
    )
}

/** One language's examples, shelf by shelf. */
function LanguageShelves({
    examples,
    chosen,
    onLoad,
}: {
    examples: EvaluationExample[]
    chosen: string
    onLoad: (example: EvaluationExample) => void
}) {
    const shelves = exampleGroups(examples)
    return (
        <div className="space-y-4">
            {shelves.map((shelf) => (
                <section key={shelf.group} className="space-y-1">
                    <h3 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                        {shelf.group}
                    </h3>
                    <ul className="grid gap-0.5">
                        {shelf.examples.map((example) => (
                            <li key={example.id}>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    aria-current={example.id === chosen ? 'true' : undefined}
                                    className={cn(
                                        'h-auto w-full justify-start px-2 py-1.5 text-left text-xs whitespace-normal',
                                        example.id === chosen && 'bg-accent text-accent-foreground',
                                    )}
                                    onClick={() => onLoad(example)}
                                >
                                    {example.label}
                                </Button>
                            </li>
                        ))}
                    </ul>
                </section>
            ))}
        </div>
    )
}

/** What one language is, and then everything it answers, shelf by shelf. */
function ReferenceBody({ reference }: { reference: LanguageReference }) {
    return (
        <div className="space-y-5" data-testid="evaluate-reference">
            <div className="space-y-2">
                {reference.summary.map((paragraph) => (
                    <p key={paragraph} className="text-muted-foreground text-xs leading-relaxed">
                        <ProseText text={paragraph} />
                    </p>
                ))}
                {reference.reading !== null && (
                    <p className="text-muted-foreground text-xs">
                        The long form is{' '}
                        <a
                            href={reference.reading.url}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:text-foreground underline underline-offset-2"
                        >
                            {reference.reading.title}
                        </a>{' '}
                        in the published documentation.
                    </p>
                )}
            </div>

            {reference.sections.map((section) => (
                <section key={section.title} className="space-y-1.5">
                    <div className="flex flex-wrap items-baseline gap-2">
                        <h3 className="text-sm font-semibold">{section.title}</h3>
                        <Badge variant="secondary" className="text-[10px]">
                            {section.entries.length}
                        </Badge>
                    </div>
                    {section.note !== undefined && (
                        <p className="text-muted-foreground text-xs leading-relaxed">
                            <ProseText text={section.note} />
                        </p>
                    )}
                    <dl className="grid gap-1.5">
                        {section.entries.map((entry) => (
                            <div key={entry.name} className="grid gap-0.5">
                                <dt className="font-mono text-xs break-words">{entry.name}</dt>
                                <dd className="text-muted-foreground text-xs leading-relaxed">
                                    <ProseText text={entry.meaning} />
                                </dd>
                            </div>
                        ))}
                    </dl>
                </section>
            ))}
        </div>
    )
}

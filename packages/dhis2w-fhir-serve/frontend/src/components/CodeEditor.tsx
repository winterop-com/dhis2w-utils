import { Suspense, lazy, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * The source editors this app writes and reads code in, deferred to their own chunk.
 *
 * WHY THERE IS A LAZY BOUNDARY HERE AT ALL. CodeMirror is the second heaviest thing this bundle can
 * reach, after the map renderer, and it is reached by three screens out of eleven: the Evaluate page,
 * the receipt's raw document, and the conformance document on the Server page. A data clerk who only
 * fills forms in must not download a code editor to do it, so `components/CodeMirrorEditor.tsx` is
 * imported through `React.lazy` and lands in a chunk of its own - the same argument, and the same
 * shape, as the deferred MapLibre import in pages/OrgUnits.tsx.
 *
 * WHAT CROSSES THE BOUNDARY. This module owns the props and the language type, because a type is
 * erased at build time and can therefore be imported by anything without pulling the editor in with
 * it. Everything that actually touches `@codemirror/*` lives on the other side.
 *
 * THE FALLBACK IS A BOX OF THE RIGHT SIZE, not a spinner. What loads here is an editor that is about
 * to occupy a fixed rectangle in a form, and a fallback that took no space would make the whole page
 * jump the moment the chunk landed.
 */

/** Which of the languages this app edits a box holds. */
export type EditorLanguage = 'json' | 'cql' | 'fhirpath'

/** What a writable source box takes. */
export interface CodeEditorProps {
    value: string
    onChange: (next: string) => void
    language: EditorLanguage
    /** The id of the `<Label>` above this box - a CodeMirror document is not a labelable control. */
    labelId: string
    /** What a browser test finds the box by, when one does. */
    testId?: string
    minHeight?: string
    maxHeight?: string
    /** Line numbers, for a source long enough that a diagnostic's line number is worth locating. */
    lineNumbersShown?: boolean
    className?: string
}

/** What a read-only source block takes. */
export interface CodeBlockProps {
    value: string
    language?: EditorLanguage
    testId?: string
    maxHeight?: string
    className?: string
}

const LoadedEditor = lazy(async () => {
    const module = await import('@/components/CodeMirrorEditor')
    return { default: module.CodeMirrorEditor }
})

const LoadedBlock = lazy(async () => {
    const module = await import('@/components/CodeMirrorEditor')
    return { default: module.CodeMirrorBlock }
})

/** A box somebody writes source in, with the editor fetched the first time one is opened. */
export function CodeEditor(props: CodeEditorProps) {
    return (
        <Placeholder minHeight={props.minHeight ?? '8rem'} className={props.className}>
            <LoadedEditor {...props} />
        </Placeholder>
    )
}

/**
 * Source nobody is editing, painted the way the editors paint it.
 *
 * Results, diagnostics, a stored QuestionnaireResponse, the conformance document - every JSON this
 * app shows a reader goes through here, so there is one set of colours and one font metric whether a
 * document is being written or read back.
 */
export function CodeBlock(props: CodeBlockProps) {
    return (
        <Placeholder minHeight="6rem" className={props.className}>
            <LoadedBlock {...props} />
        </Placeholder>
    )
}

/** The rectangle the editor will occupy, held open while its chunk is in flight. */
function Placeholder({
    minHeight,
    className,
    children,
}: {
    minHeight: string
    className?: string
    children: ReactNode
}) {
    return (
        <Suspense
            fallback={
                <div
                    className={cn('bg-muted/40 rounded-md border', className)}
                    style={{ minHeight }}
                    aria-hidden
                />
            }
        >
            {children}
        </Suspense>
    )
}

import { useEffect, useId, useRef } from 'react'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { json } from '@codemirror/lang-json'
import {
    bracketMatching,
    HighlightStyle,
    indentOnInput,
    syntaxHighlighting,
    type LanguageSupport,
    type StreamLanguage,
} from '@codemirror/language'
import { EditorState, type Extension } from '@codemirror/state'
import {
    drawSelection,
    EditorView,
    highlightActiveLine,
    highlightSpecialChars,
    keymap,
    lineNumbers,
    rectangularSelection,
} from '@codemirror/view'
import { tags } from '@lezer/highlight'

import type { CodeBlockProps, CodeEditorProps, EditorLanguage } from '@/components/CodeEditor'
import { cqlLanguage, fhirpathLanguage } from '@/lib/codelang'
import { cn } from '@/lib/utils'

/**
 * The CodeMirror editors themselves - the only module in this app that imports CodeMirror.
 *
 * WHY IT IS ALONE IN HERE. Everything below is reached through `components/CodeEditor.tsx`, which
 * defers this module behind `React.lazy` so the editor lands in its own chunk rather than in the
 * entry bundle. A capture client that only fills forms in must not download a code editor, and the
 * way to guarantee that is to keep every `@codemirror/*` import on one side of one lazy boundary.
 *
 * WHY CODEMIRROR AND NOT A TEXTAREA. Everything a person types on the Evaluate screen is code, and
 * the three shapes it comes in fail in ways a plain box cannot show: an ELM library is a JSON
 * document deep enough that a missing brace is invisible without matching, a CQL library is a
 * sequence of declarations whose keywords are what tell one define from the next, and a pasted
 * context resource is JSON somebody is editing by hand. Colour and brace matching are not decoration
 * here - they are the difference between reading a refusal and seeing the character that caused it.
 *
 * WHY NOT MONACO. Monaco is a code editor with a language server protocol in it, and this screen has
 * three small languages and no language server. CodeMirror 6 is modular enough that the whole cost is
 * the state, the view, the JSON grammar, and the pieces named in the import list above - the rest of
 * the library is never referenced and never bundled. `lib/codelang.ts` supplies FHIRPath and CQL as
 * stream tokenisers, which is the other half of keeping this small.
 *
 * WHY THE THEME IS CSS VARIABLES AND NOT TWO THEMES. next-themes puts a class on `<html>` and the
 * whole palette hangs off it, so an editor painted in `var(--code-keyword)` follows the toggle with
 * nothing re-created and no theme prop threaded through. The alternative - a light extension and a
 * dark one, swapped on a `useTheme` read - would rebuild the editor state every time somebody flips
 * the toggle, which throws away the cursor and the undo history to change a colour.
 *
 * THE VALUE IS CONTROLLED, and the reconciliation is deliberate rather than incidental: a prop that
 * differs from what the document holds is dispatched as a replacement, and a change the user made is
 * reported up. The guard against the loop those two would otherwise form is the comparison itself -
 * an incoming value equal to the current document dispatches nothing.
 */


/**
 * How each token is named, so the stylesheet can paint it.
 *
 * CLASSES RATHER THAN COLOURS, and the reason is where the palette belongs. CodeMirror will happily
 * take a colour per tag and mint an opaque class name for each - but then this app's design tokens
 * would live in two places, and the one place the light and dark palettes are declared together is
 * index.css. So every tag is given a stable name here and `.tok-*` is painted there, beside the
 * tokens it spends. A theme toggle then repaints the editor with nothing re-created, and a browser
 * test has something to assert a highlighter ran at all.
 *
 * The tags are the ones `lib/codelang.ts` emits plus the ones the JSON grammar emits.
 */
const CODE_HIGHLIGHT = HighlightStyle.define([
    { tag: tags.keyword, class: 'tok-keyword' },
    { tag: tags.operator, class: 'tok-operator' },
    { tag: tags.string, class: 'tok-string' },
    { tag: tags.number, class: 'tok-number' },
    { tag: tags.bool, class: 'tok-literal' },
    { tag: tags.null, class: 'tok-literal' },
    { tag: tags.literal, class: 'tok-literal' },
    { tag: tags.comment, class: 'tok-comment' },
    { tag: tags.variableName, class: 'tok-variable' },
    { tag: tags.typeName, class: 'tok-type' },
    { tag: tags.propertyName, class: 'tok-property' },
    { tag: tags.punctuation, class: 'tok-punctuation' },
    { tag: tags.invalid, class: 'tok-invalid' },
])

/**
 * The chrome: surfaces, the caret, the selection, and the matching-bracket mark, all in app tokens.
 *
 * NOTHING IS MARKED UNTIL SOMEBODY IS IN THE BOX. CodeMirror keeps a caret position and a matching
 * brace whether or not the editor has focus, so an untouched editor arrived with a band across its
 * first line and a box round its first brace - two marks answering a caret nobody had placed, which
 * on a page holding two editors read as one of them being active. Every mark that answers the caret
 * is therefore drawn under `&.cm-focused`, and an unfocused editor is the source and nothing else.
 *
 * The three washes are `--editor-*` tokens rather than colours: see index.css, where they are
 * derived - and where Paper overrides the one of them its cream card could not take.
 */
const EDITOR_THEME = EditorView.theme({
    '&': {
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        fontSize: '0.75rem',
    },
    '.cm-content': {
        fontFamily: 'var(--font-mono)',
        padding: '0.625rem 0',
        caretColor: 'var(--foreground)',
    },
    '.cm-line': { padding: '0 0.75rem' },
    '&.cm-focused': { outline: 'none' },
    '.cm-gutters': {
        backgroundColor: 'transparent',
        color: 'var(--muted-foreground)',
        border: 'none',
        fontFamily: 'var(--font-mono)',
    },
    '.cm-activeLine': { backgroundColor: 'transparent' },
    '&.cm-focused .cm-activeLine': { backgroundColor: 'var(--editor-active-line)' },
    '.cm-activeLineGutter': { backgroundColor: 'transparent' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
        backgroundColor: 'var(--editor-selection)',
    },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--foreground)' },
    '.cm-matchingBracket, .cm-nonmatchingBracket': { backgroundColor: 'transparent', outline: 'none' },
    '&.cm-focused .cm-matchingBracket': {
        backgroundColor: 'var(--editor-bracket)',
        outline: 'none',
    },
    '&.cm-focused .cm-nonmatchingBracket': {
        backgroundColor: 'color-mix(in oklab, var(--destructive) 22%, transparent)',
    },
    '.cm-scroller': { overflow: 'auto', lineHeight: '1.6' },
})

/** The grammar or tokeniser one language is read with. */
function languageExtension(language: EditorLanguage): LanguageSupport | StreamLanguage<null> {
    if (language === 'json') return json()
    return language === 'cql' ? cqlLanguage : fhirpathLanguage
}

/** Everything both the writable and the read-only editor share. */
function commonExtensions(language: EditorLanguage): Extension[] {
    return [
        languageExtension(language),
        syntaxHighlighting(CODE_HIGHLIGHT),
        EDITOR_THEME,
        EditorView.lineWrapping,
        highlightSpecialChars(),
        drawSelection(),
        bracketMatching(),
    ]
}

/**
 * A box somebody writes source in.
 *
 * `language` decides how it is read, `labelId` is what a screen reader and a test find it by - a
 * CodeMirror document is a contenteditable rather than a form control, so the visible `<Label>` is
 * bound through `aria-labelledby` rather than through `for`.
 */
export function CodeMirrorEditor({
    value,
    onChange,
    language,
    labelId,
    testId,
    minHeight = '8rem',
    maxHeight = '24rem',
    lineNumbersShown = false,
    className,
}: CodeEditorProps) {
    const host = useRef<HTMLDivElement | null>(null)
    const view = useRef<EditorView | null>(null)
    // The callback is held in a ref rather than in the effect's dependencies: rebuilding the editor
    // because a parent re-rendered would drop the cursor mid-word.
    const report = useRef(onChange)
    report.current = onChange

    useEffect(() => {
        const parent = host.current
        if (parent === null) return
        const editor = new EditorView({
            parent,
            state: EditorState.create({
                doc: value,
                extensions: [
                    ...commonExtensions(language),
                    lineNumbersShown ? lineNumbers() : [],
                    history(),
                    indentOnInput(),
                    highlightActiveLine(),
                    rectangularSelection(),
                    keymap.of([...defaultKeymap, ...historyKeymap]),
                    EditorView.contentAttributes.of({ 'aria-labelledby': labelId }),
                    EditorView.updateListener.of((update) => {
                        if (update.docChanged) report.current(update.state.doc.toString())
                    }),
                ],
            }),
        })
        view.current = editor
        return () => {
            editor.destroy()
            view.current = null
        }
        // The document is seeded once and reconciled by the effect below; re-creating the editor
        // whenever the value changes would be re-creating it on every keystroke.
        // oxlint-disable-next-line react/exhaustive-deps
    }, [language, labelId, lineNumbersShown])

    useEffect(() => {
        const editor = view.current
        if (editor === null) return
        const current = editor.state.doc.toString()
        if (current === value) return
        editor.dispatch({ changes: { from: 0, to: current.length, insert: value } })
    }, [value])

    return (
        <div
            ref={host}
            data-testid={testId}
            className={cn(
                'border-input bg-card focus-within:ring-ring/50 show-scrollbars overflow-auto rounded-md border focus-within:ring-[3px]',
                className,
            )}
            style={{ minHeight, maxHeight }}
        />
    )
}

/**
 * Source nobody is editing, painted the same way the editors paint it.
 *
 * The read-only half, and it is the same editor rather than a `<pre>` with a tokeniser bolted on:
 * one set of colours, one font metric, one scroll behaviour, whether a document is being written or
 * read back.
 */
export function CodeMirrorBlock({
    value,
    language = 'json',
    testId,
    maxHeight = '24rem',
    className,
}: CodeBlockProps) {
    const host = useRef<HTMLDivElement | null>(null)
    const view = useRef<EditorView | null>(null)
    const label = useId()

    useEffect(() => {
        const parent = host.current
        if (parent === null) return
        const editor = new EditorView({
            parent,
            state: EditorState.create({
                doc: value,
                extensions: [
                    ...commonExtensions(language),
                    EditorState.readOnly.of(true),
                    EditorView.editable.of(false),
                    // No accessible name: this is a rendering of a document the page has already
                    // headed, not a control. Naming it would put a second "Source" on a screen that
                    // has one, which is exactly the collision the editors' own labels must not meet.
                    EditorView.contentAttributes.of({ id: label, 'aria-readonly': 'true' }),
                ],
            }),
        })
        view.current = editor
        return () => {
            editor.destroy()
            view.current = null
        }
        // oxlint-disable-next-line react/exhaustive-deps
    }, [language, label])

    useEffect(() => {
        const editor = view.current
        if (editor === null) return
        const current = editor.state.doc.toString()
        if (current === value) return
        editor.dispatch({ changes: { from: 0, to: current.length, insert: value } })
    }, [value])

    return (
        <div
            ref={host}
            data-testid={testId}
            className={cn('bg-muted/40 show-scrollbars overflow-auto rounded-md border', className)}
            style={{ maxHeight }}
        />
    )
}

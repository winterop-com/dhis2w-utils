import { useState } from 'react'

import { CodeBlock } from '@/components/CodeEditor'
import { Button } from '@/components/ui/button'
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * The served document behind a panel, at the panel's own foot.
 *
 * WHY IT IS A SHEET OVER A SHEET rather than a section inside one. Every panel here is a reading of
 * a document - a receipt joined to the questions it answers, a tracked entity joined to the names
 * its attributes were published under - and the document itself is the thing to check when the
 * reading looks wrong. A JSON block folded into the panel would push that reading down the page for
 * every reader who did not want it; behind a button it costs nothing until it is asked for.
 *
 * ONE COMPONENT FOR EVERY RESOURCE TYPE, because "show me what the server actually sent" is one
 * question with one answer, and two copies of it would drift into two shapes of the same panel.
 * The type names itself in the button, the title and the test id, so a screen carrying two of these
 * still says which document each one opens.
 *
 * THE DOCUMENT TAKES THE PANEL'S HEIGHT. A JSON rendering capped at its own height inside a
 * full-height panel leaves most of the panel empty with the document scrolling in a letterbox - so
 * the panel is a column, the block is the one thing in it that grows, and the scroll is the block's
 * own. `min-h-0` at both levels is what lets a flex child be shorter than its content.
 */
export function RawResourceSheet({
    resource,
    resourceType,
    description,
}: {
    /** The served document, rendered exactly as it arrived. */
    resource: object
    /** The FHIR resource type this opens - what the button, the title and the test id are named for. */
    resourceType: string
    /** The one line under the title: what this document is, in the words of the panel it opens from. */
    description: string
}) {
    const [shown, setShown] = useState(false)
    const label = `Raw ${resourceType}`
    return (
        <>
            {/* The label names the document, because that is what opens; the tooltip says what the
                document is, for a reader who has never met the word. */}
            <Tooltip>
                <TooltipTrigger asChild>
                    <Button variant="outline" size="sm" onClick={() => setShown(true)}>
                        {label}
                    </Button>
                </TooltipTrigger>
                <TooltipContent>{description}</TooltipContent>
            </Tooltip>
            <Sheet open={shown} onOpenChange={setShown}>
                <SheetContent className="flex w-full flex-col overflow-hidden sm:max-w-2xl">
                    <SheetHeader>
                        <SheetTitle>{label}</SheetTitle>
                        <SheetDescription>{description}</SheetDescription>
                    </SheetHeader>
                    <div className="flex min-h-0 flex-1 flex-col px-4 pb-6">
                        <CodeBlock
                            value={JSON.stringify(resource, null, 2)}
                            testId={rawResourceTestId(resourceType)}
                            maxHeight="none"
                            className="min-h-0 flex-1"
                        />
                    </div>
                </SheetContent>
            </Sheet>
        </>
    )
}

/** What one raw rendering is found by: the resource type, hyphenated the way every test id here is. */
export function rawResourceTestId(resourceType: string): string {
    const hyphenated = resourceType
        .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
    return `raw-${hyphenated}`
}

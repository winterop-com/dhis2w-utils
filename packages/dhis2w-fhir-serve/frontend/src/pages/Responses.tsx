import { PageHeader } from '@/components/PageState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * What came back: the receipts the server holds in its spool.
 *
 * PLACEHOLDER. The renderer worker owns this page, because it is the far end of
 * the same loop that starts at the Questionnaire renderer, and the two share the
 * item-tree walk: rendering a QuestionnaireResponse against its Questionnaire is
 * the same traversal as rendering the form, with answers instead of inputs.
 *
 * The data it needs is already reachable through the seams that exist:
 * `useFhirSearch<QuestionnaireResponse>('QuestionnaireResponse')` lists the
 * spool, `?questionnaire=<canonical>` narrows it to one form, and
 * `readResource('QuestionnaireResponse', id)` reads one receipt back verbatim.
 * The lifecycle colours a listing wants - received, forwarded, rejected, refused -
 * are theme tokens already: `bg-status-received` and friends.
 */
export function Responses() {
    return (
        <>
            <PageHeader
                title="Responses"
                description="Every capture this server stored, as the receipt it was stored as."
            />
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Not built yet</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground space-y-3 text-sm">
                    <p>
                        The response list and the response detail view land with the Questionnaire renderer:
                        showing a stored answer is the same item-tree walk as showing the form that asked for
                        it.
                    </p>
                    <p>
                        Until then, the receipts are readable over the API this page will use:{' '}
                        <code className="font-mono text-xs">GET /QuestionnaireResponse</code> lists them and{' '}
                        <code className="font-mono text-xs">GET /QuestionnaireResponse/{'{id}'}</code> reads
                        one back exactly as it was submitted.
                    </p>
                </CardContent>
            </Card>
        </>
    )
}

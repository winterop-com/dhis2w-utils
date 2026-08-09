import { Link } from 'react-router-dom'

import { PageHeader, PageState } from '@/components/PageState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { useFhirSearch } from '@/hooks/use-fhir-search'
import {
    FORM_TYPE_LABELS,
    canonicalId,
    formTypeOf,
    questionCount,
    type FormType,
    type Questionnaire,
} from '@/lib/fhir'

/**
 * Every form this server publishes, as one table.
 *
 * This is the entry point of the capture loop: a Questionnaire here is something
 * a client can fill in and POST back as a QuestionnaireResponse. The row states
 * the three facts that decide whether it can be: its title, the DHIS2 object
 * kind it came from (the `D2FormType` extension - a form without one is one the
 * server will refuse to capture against), and how many questions it asks.
 *
 * The renderer sibling owns `/forms/:id`. This page only routes there.
 */
export function Forms() {
    const { resources, loading, error } = useFhirSearch<Questionnaire>('Questionnaire')
    const questionnaires = resources.toSorted((left, right) =>
        (left.title ?? left.id ?? '').localeCompare(right.title ?? right.id ?? ''),
    )

    return (
        <>
            <PageHeader
                title="Forms"
                description="Questionnaires this server publishes. Each one is a DHIS2 data set, event program, or tracker stage as a capture form."
            />
            <PageState
                loading={loading}
                error={error}
                empty={questionnaires.length === 0}
                emptyMessage="This project publishes no Questionnaires. Run `make generate` then `make sushi` to compile the IG, or serve it with --live."
            >
                <div className="show-scrollbars overflow-x-auto rounded-lg border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Title</TableHead>
                                <TableHead>Kind</TableHead>
                                <TableHead className="text-right">Questions</TableHead>
                                <TableHead>Id</TableHead>
                                <TableHead className="w-0" />
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {questionnaires.map((questionnaire) => {
                                const identifier = questionnaire.id ?? canonicalId(questionnaire.url) ?? ''
                                return (
                                    <TableRow key={questionnaire.url ?? identifier}>
                                        <TableCell className="font-medium">
                                            {questionnaire.title ?? questionnaire.name ?? identifier}
                                        </TableCell>
                                        <TableCell>
                                            <FormTypeBadge kind={formTypeOf(questionnaire)} />
                                        </TableCell>
                                        <TableCell className="text-right font-mono text-xs">
                                            {questionCount(questionnaire.item)}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground font-mono text-xs">
                                            {identifier}
                                        </TableCell>
                                        <TableCell>
                                            <Button asChild variant="outline" size="sm">
                                                <Link to={`/forms/${identifier}`}>Open</Link>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>
                </div>
            </PageState>
        </>
    )
}

/** The DHIS2 object kind a form came from, or a stated absence. */
function FormTypeBadge({ kind }: { kind: FormType | null }) {
    if (kind === null) {
        return (
            <Badge variant="outline" className="text-muted-foreground">
                no form type
            </Badge>
        )
    }
    return <Badge variant="secondary">{FORM_TYPE_LABELS[kind]}</Badge>
}

import { Link, Route, Routes } from 'react-router-dom'

import { AppLayout } from '@/components/AppLayout'
import { PageHeader } from '@/components/PageState'
import { Card, CardContent } from '@/components/ui/card'
import { Evaluate } from '@/pages/Evaluate'
import { FormFill } from '@/pages/FormFill'
import { Forms } from '@/pages/Forms'
import { MetadataHealth } from '@/pages/MetadataHealth'
import { OrgUnits } from '@/pages/OrgUnits'
import { Overview } from '@/pages/Overview'
import { Playground } from '@/pages/Playground'
import { ResponseDetail } from '@/pages/ResponseDetail'
import { Responses } from '@/pages/Responses'
import { Server } from '@/pages/Server'
import { Terminology } from '@/pages/Terminology'
import { TerminologyDetail } from '@/pages/TerminologyDetail'
import { TrackedEntities } from '@/pages/TrackedEntities'
import { TrackedEntityDetail } from '@/pages/TrackedEntityDetail'

/**
 * The route table.
 *
 * Flat and hash-routed. Flat because the top-level pages are peers and the
 * four detail routes below are one segment deeper rather than a nested layout;
 * hash-routed because `d2w fhir serve --ui` mounts
 * the bundle as plain static files behind every FHIR route, and a static mount
 * has no SPA fallback to give a deep path - `#/terminology` never reaches the
 * server as a path at all, so a reload on any page works with no server-side
 * rewrite rule.
 *
 * ADDING A PAGE: add a `<Route>` here and an entry in `NAV_ITEMS`
 * (components/AppLayout.tsx). The shell reads the nav array; nothing else needs
 * to know.
 *
 * `/forms/:questionnaireId`, `/responses/:responseId`,
 * `/terminology/:resourceType/:resourceId`, and
 * `/tracked-entities/:resourceType/:trackedEntityUid` are the four routes that
 * are not listings: the first renders one Questionnaire as a fillable form and
 * posts the answers back, the second opens one stored receipt with its answers
 * joined to the questions that were asked, the third opens one terminology
 * resource and shows the codes inside it, and the fourth opens one tracked
 * entity the DHIS2 instance holds.
 *
 * The tracked entity route carries a resource type because the register serves
 * as many FHIR resources as the published map names - `Patient` for the people,
 * whatever a project states for the rest - and a tracked entity uid alone does
 * not say which of them reads it back.
 *
 * `/tracked-entities` and its detail route are the two that can be offered or
 * not: the register is mounted only by a run that reaches a DHIS2 instance, so
 * both pages read `/facade/uiconfig` and send a reader to the overview when this run
 * offers no register. The route table stays whole either way, because whether a
 * page exists is a fact about the running server rather than about the bundle.
 *
 * `/evaluate` is a listing of nothing: it is a place to run an expression and
 * read what this server answers, so it holds its whole state in the form on it
 * and links to nothing deeper. It is offered by every run, because the two
 * contexts that need no DHIS2 instance - a pasted resource, a resource this
 * guide publishes - are the two it opens with.
 *
 * `/metadata-health` is the second page that can be offered or not, and for the
 * same reason the register is: grading DHIS2 metadata needs a DHIS2 instance, so
 * a run reading a compiled guide off disk offers no entry to it. Unlike the
 * register it is still answered at the address - the server states in words that
 * there is no instance behind it - so a bookmark kept from a live run lands on an
 * explanation rather than being sent elsewhere.
 *
 * `/organisation-units` is the one page that keeps its selection in the query
 * string (`#/organisation-units?unit=<uid>`) rather than in the path: the tree,
 * the detail panel, and the map are one screen over one read, and an
 * organisation unit is a state of that screen rather than a document of its
 * own. It is also the only route that lazy-loads anything - the map renderer is
 * fetched when the page mounts, not with the bundle.
 *
 * The index route is the Overview - the state of capture in one screen - and
 * every listing keeps a path of its own, so `/forms` is a link that can be sent
 * rather than "whatever the root happens to show".
 *
 * An address none of them matches is answered by `NotFound`, at the address it
 * was opened at.
 */
export default function App() {
    return (
        <AppLayout>
            <Routes>
                <Route index element={<Overview />} />
                <Route path="forms" element={<Forms />} />
                <Route path="forms/:questionnaireId" element={<FormFill />} />
                <Route path="responses" element={<Responses />} />
                <Route path="responses/:responseId" element={<ResponseDetail />} />
                <Route path="tracked-entities" element={<TrackedEntities />} />
                <Route
                    path="tracked-entities/:resourceType/:trackedEntityUid"
                    element={<TrackedEntityDetail />}
                />
                <Route path="organisation-units" element={<OrgUnits />} />
                <Route path="evaluate" element={<Evaluate />} />
                <Route path="playground" element={<Playground />} />
                <Route path="metadata-health" element={<MetadataHealth />} />
                <Route path="terminology" element={<Terminology />} />
                <Route path="terminology/:resourceType/:resourceId" element={<TerminologyDetail />} />
                <Route path="server" element={<Server />} />
                <Route path="*" element={<NotFound />} />
            </Routes>
        </AppLayout>
    )
}

/**
 * An address this app does not answer, said plainly.
 *
 * NOT A REDIRECT. Exchanging an unknown hash for the overview leaves a reader looking at a page
 * they did not ask for, with the address bar quietly rewritten and nothing anywhere saying that a
 * link was wrong - which is indistinguishable from the app having lost their place. So the address
 * is answered where it was opened, the same way the register answers a link to a page this run does
 * not serve, and the way back to the overview is a link rather than something that already happened.
 */
function NotFound() {
    return (
        <>
            <PageHeader
                title="Nothing at this address"
                description="This app does not answer for the address in the browser bar."
            />
            <Card>
                <CardContent className="text-muted-foreground py-8 text-sm">
                    <p data-testid="route-not-found">
                        The link may be from a run of this app that served a page this one does not,
                        or the address may have been mistyped.{' '}
                        <Link to="/" className="interactive-link">
                            Open the overview
                        </Link>
                        .
                    </p>
                </CardContent>
            </Card>
        </>
    )
}

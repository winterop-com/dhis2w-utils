import { Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from '@/components/AppLayout'
import { FormFill } from '@/pages/FormFill'
import { Forms } from '@/pages/Forms'
import { OrgUnits } from '@/pages/OrgUnits'
import { Overview } from '@/pages/Overview'
import { PatientDetail } from '@/pages/PatientDetail'
import { Patients } from '@/pages/Patients'
import { ResponseDetail } from '@/pages/ResponseDetail'
import { Responses } from '@/pages/Responses'
import { Server } from '@/pages/Server'
import { Terminology } from '@/pages/Terminology'
import { TerminologyDetail } from '@/pages/TerminologyDetail'

/**
 * The route table.
 *
 * Flat and hash-routed. Flat because the six top-level pages are peers and the
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
 * `/terminology/:resourceType/:resourceId`, and `/patients/:trackedEntityUid`
 * are the four routes that are not listings: the first renders one Questionnaire
 * as a fillable form and posts the answers back, the second opens one stored
 * receipt with its answers joined to the questions that were asked, the third
 * opens one terminology resource and shows the codes inside it, and the fourth
 * opens one person the DHIS2 instance holds.
 *
 * `/patients` and `/patients/:trackedEntityUid` are the two routes that can be
 * offered or not: the person routes are mounted only by a run that reaches a
 * DHIS2 instance, so both pages read `/uiconfig` and send a reader to the
 * overview when this run offers no people. The route table stays whole either
 * way, because whether a page exists is a fact about the running server rather
 * than about the bundle.
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
                <Route path="patients" element={<Patients />} />
                <Route path="patients/:trackedEntityUid" element={<PatientDetail />} />
                <Route path="organisation-units" element={<OrgUnits />} />
                <Route path="terminology" element={<Terminology />} />
                <Route path="terminology/:resourceType/:resourceId" element={<TerminologyDetail />} />
                <Route path="server" element={<Server />} />
                {/* An unknown hash route returns to the overview rather than a blank page. */}
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </AppLayout>
    )
}

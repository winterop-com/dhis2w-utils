import { useEffect, useState } from 'react'

import { readCapabilityStatement } from '@/lib/api'
import { declaresPatientSearch } from '@/lib/fhir'

/**
 * Whether this server publishes patient search, in the three states a control has to tell apart.
 *
 * `absent` and `unknown` are deliberately not the same answer. A compiled process really does
 * declare no `Patient`, and saying so - "this server answers from a compiled guide" - is a fact
 * worth putting on screen. A `/metadata` read that failed says nothing about what the server can
 * do, so a control that printed the compiled explanation for it would be inventing a reason. Both
 * hide the find-a-person option; only one of them explains why.
 */
export type PatientSearchSupport = 'unknown' | 'supported' | 'absent'

/**
 * The conformance document, read once for the whole tab.
 *
 * WHY IT IS MEMOISED AT MODULE LEVEL. `/metadata` is rendered once at startup and served verbatim,
 * so its answer cannot change under a running process - a server that changed its mind about
 * serving Patient would have restarted, and a restart reloads this page. Every registration and
 * stage form in a session would otherwise re-ask the same question, and the answer would be the
 * same every time. A failed read is not cached: the next form asks again, which is what makes a
 * server that came up slowly recoverable without a reload.
 */
let pending: Promise<PatientSearchSupport> | null = null

/** Read the conformance document once and reduce it to whether patient search is published. */
async function readSupport(): Promise<PatientSearchSupport> {
    pending ??= readCapabilityStatement()
        .then((capability) => (declaresPatientSearch(capability) ? 'supported' : 'absent'))
        .catch((): PatientSearchSupport => {
            pending = null
            return 'unknown'
        })
    return pending
}

/**
 * Ask whether a person can be found in the DHIS2 instance behind this server.
 *
 * The one gate on every control in this app that reaches the instance rather than the store. It is
 * asked ahead of the request rather than discovered from a refusal, because a search box that
 * appears and then always answers "not supported" is worse than no search box.
 */
export function usePatientSearchSupport(): PatientSearchSupport {
    const [support, setSupport] = useState<PatientSearchSupport>('unknown')

    useEffect(() => {
        let cancelled = false
        void readSupport().then((read) => {
            if (!cancelled) setSupport(read)
        })
        return () => {
            cancelled = true
        }
    }, [])

    return support
}

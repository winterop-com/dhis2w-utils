import { useEffect, useState } from 'react'

import { readCapabilityStatement } from '@/lib/api'
import { type CapabilityStatement, declaresRegisterSearch } from '@/lib/fhir'

/**
 * Whether this server publishes a search over one register, in the three states a control tells apart.
 *
 * `absent` and `unknown` are deliberately not the same answer. A server whose conformance statement
 * really declares no search over the asked-for register - a compiled process declares none at all -
 * is a fact worth putting on screen. A `/metadata` read that failed says nothing about what the
 * server can do, so a control that printed the absent explanation for it would be inventing a
 * reason. Both hide the find-a-record option; only one of them explains why.
 */
export type RegisterSearchSupport = 'unknown' | 'supported' | 'absent'

/**
 * The conformance document, read once for the whole tab.
 *
 * WHY IT IS MEMOISED AT MODULE LEVEL. `/metadata` is rendered once at startup and served verbatim,
 * so its answer cannot change under a running process - a server that changed its mind about its
 * registers would have restarted, and a restart reloads this page. Every registration and stage
 * form in a session would otherwise re-ask the same question, and the answer would be the same
 * every time. The document is what is cached rather than a verdict, because two forms can ask
 * about two different registers of one statement. A failed read is not cached: the next form asks
 * again, which is what makes a server that came up slowly recoverable without a reload.
 */
let pending: Promise<CapabilityStatement | null> | null = null

/** Read the conformance document once, answering null for a read that failed. */
async function readCapability(): Promise<CapabilityStatement | null> {
    pending ??= readCapabilityStatement().catch((): null => {
        pending = null
        return null
    })
    return pending
}

/**
 * Ask whether a record of one register can be found in the DHIS2 instance behind this server.
 *
 * The one gate on every control in this app that reaches the instance rather than the store. It is
 * asked ahead of the request rather than discovered from a refusal, because a search box that
 * appears and then always answers "not supported" is worse than no search box. The register is the
 * caller's to name - a form's `subjectType` says which one its registrations land in, and `Patient`
 * is only the default a guide maps an unnamed tracked entity type onto.
 */
export function useRegisterSearchSupport(resource: string): RegisterSearchSupport {
    const [support, setSupport] = useState<RegisterSearchSupport>('unknown')

    useEffect(() => {
        let cancelled = false
        void readCapability().then((capability) => {
            if (cancelled) return
            if (capability === null) setSupport('unknown')
            else setSupport(declaresRegisterSearch(capability, resource) ? 'supported' : 'absent')
        })
        return () => {
            cancelled = true
        }
    }, [resource])

    return support
}

import { useEffect, useState } from 'react'

import { apiFetch, outcomeMessage } from '@/lib/api'
import type { OperationOutcome } from '@/lib/fhir'

/**
 * Why this process does not answer for a register, in the words it refuses requests with.
 *
 * THE SERVER ALREADY SAYS THIS WELL. A run that reaches no DHIS2 instance answers `GET /{resource}`
 * with a `not-supported` OperationOutcome naming the reason - that it serves a compiled
 * implementation guide, and that `--live` is what searches the register - and a run whose project
 * turns the register off names the setting that turned it off. Two different states, two different
 * things for an operator to do, and both already written down by the process itself. So a screen
 * that cannot show the register asks for it and shows the refusal, rather than inventing a sentence
 * of its own or, worse, sending a reader somewhere else without a word.
 *
 * A REFUSAL IS THE EXPECTED ANSWER HERE, which is why nothing about this read is an error. The read
 * is only ever made on a run whose `/facade/uiconfig` already said the register is not served; what is
 * being asked for is the reason, and a run that answers something other than a refusal simply has
 * none to state.
 */

/** What asking a register-less server about its register answered: its own sentence, or nothing. */
export interface RegisterRefusalState {
    loading: boolean
    /** The server's own refusal, or null while it is in flight and when it stated none. */
    stated: string | null
}

/**
 * Ask this server why it does not answer for one register.
 *
 * `_count=0` because none of the answer is wanted: the request exists to be refused, and a run that
 * does answer for the resource is asked for a count rather than for a page of somebody's database.
 */
export function useRegisterRefusal(resource: string | null): RegisterRefusalState {
    const asked = resource === null || resource === '' ? null : resource
    const [answered, setAnswered] = useState<AnsweredRefusal>({ resource: null, stated: null })

    useEffect(() => {
        if (asked === null) return
        let cancelled = false
        apiFetch(`/${asked}?_count=0`, { cache: 'no-store' })
            .then(async (response) => {
                const body: unknown = response.ok ? null : await response.json().catch(() => null)
                if (cancelled) return
                setAnswered({
                    resource: asked,
                    stated: response.ok ? null : outcomeMessage(body as OperationOutcome | null),
                })
            })
            .catch(() => {
                if (cancelled) return
                setAnswered({ resource: asked, stated: null })
            })
        return () => {
            cancelled = true
        }
    }, [asked])

    if (asked === null) return { loading: false, stated: null }
    if (answered.resource !== asked) return { loading: true, stated: null }
    return { loading: false, stated: answered.stated }
}

/** What one ask answered, stamped with the register it was asked about. */
interface AnsweredRefusal {
    resource: string | null
    stated: string | null
}

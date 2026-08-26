import { describe, expect, it } from 'vitest'

import { apiHref } from '@/components/ApiLink'

/**
 * The href behind every API chip: the screen's own query, asked for in the format the server has.
 *
 * The FHIR surface refuses a request whose `Accept` rules JSON out, and a browser following a link
 * sends exactly such a header - so a link without `_format=json` on it is a link that answers 406.
 * The separator is the other half: a register query already carries a question mark, and a second
 * one would make the parameter part of the last filter's value rather than a parameter of its own.
 */
describe('the query an API chip opens', () => {
    it('asks for JSON on a path that carries no query yet', () => {
        expect(apiHref('/metadata')).toBe('/metadata?_format=json')
        expect(apiHref('/Questionnaire/d2-pr-anc-visit-q')).toBe('/Questionnaire/d2-pr-anc-visit-q?_format=json')
    })

    it('joins onto a path that already carries one', () => {
        expect(apiHref('/Patient?identifier=SCEN-A-0001')).toBe('/Patient?identifier=SCEN-A-0001&_format=json')
    })

    it('keeps every filter the screen is showing the answer to', () => {
        const live = '/Patient?_content=Smith&_tag=TeiPerson01&d2-attribute=AttrNatId01%7CX-1'

        expect(apiHref(live)).toBe(`${live}&_format=json`)
    })
})

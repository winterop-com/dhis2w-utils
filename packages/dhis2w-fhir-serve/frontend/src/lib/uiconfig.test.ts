import { describe, expect, it } from 'vitest'

import { DEFAULT_UI_CONFIG, patientSettings, type UiConfig } from '@/lib/uiconfig'

/**
 * Which pages this run offers, decided in one place.
 *
 * WHY THIS IS WORTH A TEST OF ITS OWN. Every other setting `/uiconfig` carries changes how a page
 * renders; this one decides whether a page is reachable at all, and the failure it guards against
 * is a navigation entry that leads somewhere answering a refusal. A live server always states the
 * object - a compiled run says `{enabled: false, listing: false}` rather than leaving it out - so
 * every absent form here is a server nothing is known about, and the answer for all of them is the
 * same as for a server that stated it offers nothing.
 */

const settings = (patients: UiConfig['patients']): UiConfig => ({
    basemaps: [],
    dhis2_base_url: null,
    patients,
})

describe('what a run offers about people', () => {
    it('offers the pages when the server says the routes are there', () => {
        expect(patientSettings(settings({ enabled: true, listing: true }))).toEqual({
            enabled: true,
            listing: true,
        })
    })

    it('keeps the search and the listing as two separate offers', () => {
        // A deployment can answer a lookup by identifier value and decline to page through an
        // instance's whole set of tracked entities, which is a heavier thing to publish.
        expect(patientSettings(settings({ enabled: true, listing: false })).listing).toBe(false)
    })

    it('offers nothing on a compiled run, which states the effective state rather than nothing', () => {
        expect(patientSettings(settings({ enabled: false, listing: false })).enabled).toBe(false)
    })

    it('offers nothing when the server stated nothing, however that came about', () => {
        // An older facade, a proxy that swallowed the path, or a read that failed and left the
        // defaults in place: three routes to the same state, and none of them is an offer.
        expect(patientSettings(settings(undefined)).enabled).toBe(false)
        expect(patientSettings(settings(null)).enabled).toBe(false)
        expect(patientSettings(DEFAULT_UI_CONFIG).enabled).toBe(false)
    })

    it('offers no listing wherever it offers no routes, because the listing is one of them', () => {
        expect(patientSettings(settings(null)).listing).toBe(false)
        expect(patientSettings(DEFAULT_UI_CONFIG).listing).toBe(false)
    })
})

import { describe, expect, it } from 'vitest'

import listBundleFixture from '@/lib/__fixtures__/list-bundle.json'
import locationBundleFixture from '@/lib/__fixtures__/location-bundle.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import scopedQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrScoped001.json'
import {
    ancestorsOf,
    assignedUnitIds,
    assignmentListIdOf,
    boundaryOf,
    boundsOf,
    buildFormAssignments,
    buildOrgUnitTree,
    descendantIdsOf,
    hasGeometry,
    levelOf,
    matchingUnitIds,
    pointOf,
    readGeometry,
    reportableFormsAt,
} from '@/lib/orgunits'
import { bundleResources, type Bundle, type Location, type Questionnaire, type ResourceList } from '@/lib/fhir'

/**
 * The registry reader, against the registry the fixture project really publishes.
 *
 * Every document here was harvested from a running `d2w fhir serve` over
 * `packages/dhis2w-fhir-serve/tests/fixture_project.py` - the same tree the browser suite boots -
 * so the base64, the extension urls, and the `partOf` spellings are the server's rather than a
 * hand-written guess at them. That matters most for the boundary: an attachment written by hand
 * would be exactly as valid as the reader assumed it was.
 *
 * The nine units are four levels of the DHIS2 demo hierarchy with every geometry state on them:
 * Sierra Leone carries a MultiPolygon, Bo a Polygon and a point, Bombali a Polygon and no point,
 * Bargbe and Ngelehun a point and no polygon, Baoma an attachment that is not GeoJSON at all,
 * Kagbere CHC nothing at all under a parent that has a boundary, and Adonkia CHP names a parent the
 * project never published.
 */

const locations = bundleResources(locationBundleFixture as unknown as Bundle<Location>)
const lists = bundleResources(listBundleFixture as unknown as Bundle<ResourceList>)
const questionnaires = bundleResources(questionnaireBundleFixture as unknown as Bundle<Questionnaire>)
const scopedQuestionnaire = scopedQuestionnaireFixture as unknown as Questionnaire

/** A Location publishing one arbitrary boundary payload, for the cases the fixture cannot carry. */
function withBoundaryData(data: string): Location {
    return {
        resourceType: 'Location',
        id: 'X',
        extension: [
            {
                url: 'http://hl7.org/fhir/StructureDefinition/location-boundary-geojson',
                valueAttachment: { data },
            },
        ],
    }
}

/** One Location of the fixture registry, by the DHIS2 uid it is served under. */
function unit(id: string): Location {
    const found = locations.find((location) => location.id === id)
    if (found === undefined) throw new Error(`the fixture registry publishes no Location/${id}`)
    return found
}

describe('folding the registry into a tree', () => {
    it('roots the units that name no parent', () => {
        const tree = buildOrgUnitTree(locations)

        expect(tree.total).toBe(9)
        expect(tree.roots.map((node) => node.id)).toContain('ImspTQPwCqd')
        expect(tree.byId.get('ImspTQPwCqd')?.parentId).toBeNull()
    })

    it('hangs each unit off the parent its partOf names', () => {
        const tree = buildOrgUnitTree(locations)

        const bo = tree.byId.get('O6uvpzGd5pu')
        expect(bo?.parentId).toBe('ImspTQPwCqd')
        expect(tree.byId.get('ImspTQPwCqd')?.children.map((child) => child.name)).toEqual(['Bo', 'Bombali'])
    })

    it('sorts children by the name that is rendered', () => {
        const tree = buildOrgUnitTree(locations)

        // Baoma, Badjia, Bargbe are all under Bo, and the fixture writes them in another order.
        expect(tree.byId.get('O6uvpzGd5pu')?.children.map((child) => child.name)).toEqual([
            'Badjia',
            'Baoma',
            'Bargbe',
        ])
    })

    it('makes a unit whose parent was never published a flagged root rather than dropping it', () => {
        const tree = buildOrgUnitTree(locations)

        const adonkia = tree.byId.get('Rp268JB6Ne4')
        expect(adonkia?.orphaned).toBe(true)
        expect(adonkia?.unresolvedParentId).toBe('Unpublished01')
        expect(adonkia?.parentId).toBeNull()
        expect(tree.roots.map((node) => node.id)).toContain('Rp268JB6Ne4')
        expect(tree.orphanCount).toBe(1)
    })

    it('puts the orphans after the real roots', () => {
        const tree = buildOrgUnitTree(locations)

        expect(tree.roots.map((node) => node.id)).toEqual(['ImspTQPwCqd', 'Rp268JB6Ne4'])
    })

    it('counts the whole subtree under each unit', () => {
        const tree = buildOrgUnitTree(locations)

        // Every unit but Adonkia, which is orphaned, and Sierra Leone itself.
        expect(tree.byId.get('ImspTQPwCqd')?.descendantCount).toBe(7)
        expect(tree.byId.get('O6uvpzGd5pu')?.descendantCount).toBe(4)
        expect(tree.byId.get('DiszpKrYNg8')?.descendantCount).toBe(0)
    })

    it('drops a Location carrying no id, which no route could open', () => {
        const tree = buildOrgUnitTree([...locations, { resourceType: 'Location', name: 'Nameless' }])

        expect(tree.total).toBe(9)
    })

    it('re-roots a partOf cycle instead of walking it forever', () => {
        const left: Location = { resourceType: 'Location', id: 'A', name: 'A', partOf: { reference: 'Location/B' } }
        const right: Location = { resourceType: 'Location', id: 'B', name: 'B', partOf: { reference: 'Location/A' } }

        const tree = buildOrgUnitTree([left, right])

        expect(tree.roots).toHaveLength(1)
        expect(tree.total).toBe(2)
        expect(tree.roots[0].descendantCount).toBe(1)
    })

    it('walks the chain above a unit root-first', () => {
        const tree = buildOrgUnitTree(locations)

        expect(ancestorsOf(tree, 'DiszpKrYNg8').map((node) => node.name)).toEqual([
            'Sierra Leone',
            'Bo',
            'Badjia',
        ])
        expect(ancestorsOf(tree, 'ImspTQPwCqd')).toEqual([])
    })

    it('lists every unit below one, at any depth', () => {
        const tree = buildOrgUnitTree(locations)
        const bo = tree.byId.get('O6uvpzGd5pu')

        expect(bo === undefined ? [] : descendantIdsOf(bo)).toEqual([
            'YuQRtpLP10I',
            'DiszpKrYNg8',
            'vWbkYPRmKyS',
            'lc3eMKXaEfw',
        ])
    })
})

describe('the filter over the tree', () => {
    it('keeps every ancestor of a match, so the hierarchy above it can expand', () => {
        const tree = buildOrgUnitTree(locations)

        const visible = matchingUnitIds(tree, 'ngelehun')

        expect([...visible].toSorted()).toEqual(['DiszpKrYNg8', 'ImspTQPwCqd', 'O6uvpzGd5pu', 'YuQRtpLP10I'])
    })

    it('matches on the DHIS2 uid and on the org-unit code as well as the name', () => {
        const tree = buildOrgUnitTree(locations)

        expect(matchingUnitIds(tree, 'O6uvpzGd5pu').has('O6uvpzGd5pu')).toBe(true)
        expect(matchingUnitIds(tree, 'OU_BOMBALI').has('fdc6uOvgoji')).toBe(true)
    })

    it('answers with nothing for an empty filter, which is how a page knows not to narrow', () => {
        const tree = buildOrgUnitTree(locations)

        expect(matchingUnitIds(tree, '   ').size).toBe(0)
    })
})

describe('reading the level off the published coding', () => {
    it('reads the code, the display, the system, and the depth', () => {
        const level = levelOf(unit('DiszpKrYNg8'))

        expect(level?.code).toBe('level-4')
        expect(level?.display).toBe('Level 4')
        expect(level?.system).toBe('http://localhost:8080/fhir/CodeSystem/d2-ou-level-cs')
        expect(level?.depth).toBe(4)
    })

    it('answers null for a Location carrying no level extension', () => {
        expect(levelOf({ resourceType: 'Location', id: 'X' })).toBeNull()
    })

    it('keeps a code that is not shaped level-<n>, with no depth', () => {
        const level = levelOf({
            resourceType: 'Location',
            id: 'X',
            extension: [
                {
                    url: 'http://example.org/fhir/StructureDefinition/d2-organisation-unit-level',
                    valueCoding: { code: 'district' },
                },
            ],
        })

        expect(level?.code).toBe('district')
        expect(level?.depth).toBeNull()
        expect(level?.display).toBeNull()
    })
})

describe('decoding the boundary attachment', () => {
    it('reads a Polygon out of the base64 GeoJSON Feature', () => {
        const boundary = boundaryOf(unit('O6uvpzGd5pu'))

        expect(boundary?.unitId).toBe('O6uvpzGd5pu')
        expect(boundary?.geometry.type).toBe('Polygon')
        expect(boundary?.geometry.coordinates[0]).toHaveLength(5)
    })

    it('reads a MultiPolygon, which is the other shape DHIS2 stores', () => {
        const boundary = boundaryOf(unit('ImspTQPwCqd'))

        expect(boundary?.geometry.type).toBe('MultiPolygon')
    })

    it('answers null for an attachment that is not GeoJSON, rather than throwing', () => {
        expect(boundaryOf(unit('vWbkYPRmKyS'))).toBeNull()
    })

    it('answers null for a unit publishing no boundary at all', () => {
        expect(boundaryOf(unit('lc3eMKXaEfw'))).toBeNull()
    })

    it('refuses base64 that is not JSON and JSON that is not a polygon', () => {
        expect(boundaryOf(withBoundaryData('not-base64-at-all!!'))).toBeNull()
        expect(boundaryOf(withBoundaryData(btoa('{"type":"Feature"}')))).toBeNull()
        expect(boundaryOf(withBoundaryData(btoa('{"type":"Point","coordinates":[1,2]}')))).toBeNull()
    })

    it('accepts a bare geometry as well as a Feature, since a hand-written registry may write one', () => {
        const bare = btoa('{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}')

        expect(boundaryOf(withBoundaryData(bare))?.geometry.type).toBe('Polygon')
    })
})

describe('reading the whole registry geometry', () => {
    it('collects every polygon and every point, and counts what it could not read', () => {
        const geometry = readGeometry(locations)

        expect(geometry.boundaries.map((boundary) => boundary.unitId)).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
            'fdc6uOvgoji',
        ])
        // Kagbere CHC publishes neither, which is what the map's ancestor fallback exists for.
        expect(geometry.boundaries.some((boundary) => boundary.unitId === 'EJoI3HuIUEV')).toBe(false)
        expect(geometry.points.some((point) => point.unitId === 'EJoI3HuIUEV')).toBe(false)
        expect(geometry.points.map((point) => point.unitId)).toEqual([
            'DiszpKrYNg8',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
            'lc3eMKXaEfw',
            'vWbkYPRmKyS',
        ])
        // Baoma publishes an attachment that does not decode - one skip, and four shapes kept.
        expect(geometry.skippedBoundaries).toBe(1)
        expect(hasGeometry(geometry)).toBe(true)
    })

    it('reads a point in longitude-then-latitude order, the order GeoJSON itself uses', () => {
        expect(pointOf(unit('O6uvpzGd5pu'))).toEqual({
            unitId: 'O6uvpzGd5pu',
            longitude: -11.74,
            latitude: 7.96,
        })
    })

    it('reports no geometry for a registry that publishes none', () => {
        const geometry = readGeometry([{ resourceType: 'Location', id: 'X', name: 'X' }])

        expect(hasGeometry(geometry)).toBe(false)
        expect(geometry.skippedBoundaries).toBe(0)
    })

    it('bounds a set of shapes over both the polygons and the points', () => {
        const geometry = readGeometry(locations)

        expect(boundsOf(geometry.boundaries, geometry.points)).toEqual([-13.3, 6.9, -10.3, 10])
    })

    it('answers no bounds for nothing to bound', () => {
        expect(boundsOf([], [])).toBeNull()
    })
})

describe('joining the forms to their organisation-unit assignments', () => {
    const served = [...questionnaires, scopedQuestionnaire]

    it('reads the List a form names on its assignment extension', () => {
        expect(assignmentListIdOf(scopedQuestionnaire)).toBe('d2-pr-PrScoped001-org-units')
        expect(assignmentListIdOf(questionnaires[0])).toBeNull()
    })

    it('reads the units a published List admits', () => {
        expect(assignedUnitIds(lists[0])).toEqual(['O6uvpzGd5pu', 'DiszpKrYNg8'])
    })

    it('treats a form with no assignment artifact as assigned everywhere', () => {
        const index = buildFormAssignments(served, lists)

        expect(index.universalFormIds).toEqual(questionnaires.map((form) => form.id))
        expect(index.restrictedFormIds).toEqual(['PrScoped001'])
    })

    it('adds a restricted form only at the units its List names', () => {
        const index = buildFormAssignments(served, lists)

        expect(reportableFormsAt(index, 'O6uvpzGd5pu').restrictedFormIds).toEqual(['PrScoped001'])
        expect(reportableFormsAt(index, 'DiszpKrYNg8').restrictedFormIds).toEqual(['PrScoped001'])
        expect(reportableFormsAt(index, 'ImspTQPwCqd').restrictedFormIds).toEqual([])
    })

    it('says nothing per unit about the forms assigned everywhere, however many units there are', () => {
        const index = buildFormAssignments(served, lists)

        // The join is what keeps a 1300-unit registry from building a pair per form per unit: only
        // the two units the one specifically assigned form names have an entry at all.
        expect([...index.formIdsByUnitId.keys()].toSorted()).toEqual(['DiszpKrYNg8', 'O6uvpzGd5pu'])
        expect(reportableFormsAt(index, 'ImspTQPwCqd').universalFormIds).toEqual(index.universalFormIds)
    })

    it('widens a form naming a List this server does not publish, and names it', () => {
        const index = buildFormAssignments(served, [])

        expect(index.unresolvedAssignmentFormIds).toEqual(['PrScoped001'])
        expect(index.universalFormIds).toContain('PrScoped001')
        expect(index.restrictedFormIds).toEqual([])
    })

    it('ignores a List entry naming something other than a Location', () => {
        const mixed: ResourceList = {
            resourceType: 'List',
            id: 'mixed',
            entry: [
                { item: { reference: 'Organization/O6uvpzGd5pu' } },
                { item: { reference: 'Location/DiszpKrYNg8' } },
                { item: { display: 'no reference at all' } },
            ],
        }

        expect(assignedUnitIds(mixed)).toEqual(['DiszpKrYNg8'])
    })
})

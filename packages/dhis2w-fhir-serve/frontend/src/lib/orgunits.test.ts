import { describe, expect, it } from 'vitest'

import listBundleFixture from '@/lib/__fixtures__/list-bundle.json'
import locationBundleFixture from '@/lib/__fixtures__/location-bundle.json'
import questionnaireBundleFixture from '@/lib/__fixtures__/questionnaire-bundle.json'
import scopedQuestionnaireFixture from '@/lib/__fixtures__/questionnaire-PrScoped001.json'
import {
    admittedUnitIds,
    ancestorsOf,
    assignedUnitIds,
    attachmentGeometryOf,
    dedupeByOrgUnitIdentifier,
    orgUnitIdentifierValue,
    assignmentListIdOf,
    boundaryOf,
    boundsOf,
    browseAncestorIds,
    buildFormAssignments,
    buildOrgUnitTree,
    carriesUnitOnExtension,
    descendantIdsOf,
    expandedForSelection,
    hasGeometry,
    levelLabel,
    levelOf,
    matchesUnit,
    matchingUnitIds,
    orgUnitBrowseTree,
    orgUnitChoices,
    orgUnitReference,
    organisationUnitExtensionUrl,
    pointOf,
    readGeometry,
    referencedUnitId,
    reportableFormsAt,
    unitExtent,
    visibleBrowseRows,
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
 * The bundle holds eleven Locations for ten organisation units: the eleventh is the curated
 * profile exemplar a generated IG publishes beside the registry, which claims the root unit's uid
 * on the same identifier system and hangs off nothing.
 *
 * The ten units are four levels of the DHIS2 demo hierarchy with every geometry state on them:
 * Sierra Leone carries a MultiPolygon, Bo a Polygon and a position, Bombali a Polygon and no
 * position, Ngelehun a position only, Bargbe a position AND a Point attachment that disagrees with
 * it, Yoni CHP a Point attachment and no position - which is what DHIS2 stores for a facility -
 * Baoma an attachment that is not GeoJSON at all, Kagbere CHC nothing at all under a parent that
 * has a boundary, and Adonkia CHP names a parent the project never published.
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

/** A Location claiming one organisation-unit uid and nothing else, for the tiebreak cases. */
function claim(id: string): Location {
    return {
        resourceType: 'Location',
        id,
        name: 'Lone unit',
        identifier: [{ system: 'http://dhis2.org/fhir/id/org-unit', value: 'OnlyOne0001' }],
    }
}

/** A Location carrying an org-unit CODE identifier, which is a different system entirely. */
function byCode(id: string): Location {
    return {
        resourceType: 'Location',
        id,
        name: id,
        identifier: [{ system: 'http://dhis2.org/fhir/id/org-unit-code', value: 'OU_SHARED' }],
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

        expect(tree.total).toBe(10)
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
        expect(tree.byId.get('ImspTQPwCqd')?.descendantCount).toBe(8)
        expect(tree.byId.get('O6uvpzGd5pu')?.descendantCount).toBe(4)
        expect(tree.byId.get('DiszpKrYNg8')?.descendantCount).toBe(0)
    })

    it('drops a Location carrying no id, which no route could open', () => {
        const tree = buildOrgUnitTree([...locations, { resourceType: 'Location', name: 'Nameless' }])

        expect(tree.total).toBe(10)
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

describe('one organisation unit published as two Locations', () => {
    it('folds the registry instance and drops the profile exemplar', () => {
        const tree = buildOrgUnitTree(locations)

        // Both documents claim `ImspTQPwCqd` on `{base}/id/org-unit`. The registry instance is what
        // every other unit's partOf points at, so it is the one the hierarchy needs.
        expect(tree.byId.has('ImspTQPwCqd')).toBe(true)
        expect(tree.byId.has('d2-location-example')).toBe(false)
        expect(tree.duplicateCount).toBe(1)
    })

    it('shows the root once rather than twice, which is the bug this exists for', () => {
        const tree = buildOrgUnitTree(locations)

        expect(tree.roots.filter((node) => node.name === 'Sierra Leone')).toHaveLength(1)
        // And not as a flagged root either: the exemplar is not a detached unit, it is not a unit.
        expect(tree.roots.map((node) => node.id)).toEqual(['ImspTQPwCqd', 'Rp268JB6Ne4'])
    })

    it('does not count the dropped copy among the units', () => {
        const tree = buildOrgUnitTree(locations)

        expect(locations).toHaveLength(11)
        expect(tree.total).toBe(10)
    })

    it('keeps the instance the hierarchy hangs off even when it is listed second', () => {
        const exemplar = locations.find((location) => location.id === 'd2-location-example')
        const real = locations.find((location) => location.id === 'ImspTQPwCqd')
        const others = locations.filter(
            (location) => location.id !== 'd2-location-example' && location.id !== 'ImspTQPwCqd',
        )

        const reordered = buildOrgUnitTree([exemplar!, ...others, real!])

        expect(reordered.byId.has('ImspTQPwCqd')).toBe(true)
        expect(reordered.byId.has('d2-location-example')).toBe(false)
    })

    it('prefers the copy that names a parent when neither is pointed at', () => {
        const orphanExemplar: Location = {
            resourceType: 'Location',
            id: 'd2-location-example',
            name: 'Lone unit',
            identifier: [{ system: 'http://dhis2.org/fhir/id/org-unit', value: 'OnlyOne0001' }],
        }
        const inTree: Location = {
            resourceType: 'Location',
            id: 'OnlyOne0001',
            name: 'Lone unit',
            identifier: [{ system: 'http://dhis2.org/fhir/id/org-unit', value: 'OnlyOne0001' }],
            partOf: { reference: 'Location/Unpublished01' },
        }

        const tree = buildOrgUnitTree([orphanExemplar, inTree])

        expect(tree.byId.has('OnlyOne0001')).toBe(true)
        expect(tree.total).toBe(1)
    })

    it('falls back to the lowest resource id, and does so whatever order they arrive in', () => {
        // Neither participates in any hierarchy, so the tiebreak is arbitrary - and the point of
        // the rule is that it is the SAME arbitrary answer however the Bundle was ordered.
        expect([...buildOrgUnitTree([claim('bbb'), claim('aaa')]).byId.keys()]).toEqual(['aaa'])
        expect([...buildOrgUnitTree([claim('aaa'), claim('bbb')]).byId.keys()]).toEqual(['aaa'])
    })

    it('never drops a Location that claims no organisation unit', () => {
        const nameless: Location = { resourceType: 'Location', id: 'no-identifier', name: 'Somewhere' }
        const second: Location = { resourceType: 'Location', id: 'also-none', name: 'Elsewhere' }

        const { kept, dropped } = dedupeByOrgUnitIdentifier([nameless, second])

        expect(kept).toHaveLength(2)
        expect(dropped).toEqual([])
    })

    it('does not confuse the org-unit-code system for the org-unit one', () => {
        // Two units can share nothing on the uid system while carrying the same code, and a
        // suffix match that was not exact at the end would silently merge them.
        expect(dedupeByOrgUnitIdentifier([byCode('one'), byCode('two')]).dropped).toEqual([])
        expect(orgUnitIdentifierValue(byCode('one'))).toBeNull()
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

describe('how a level is spelled on screen', () => {
    it('says what the level CodeSystem published', () => {
        expect(levelLabel({ code: 'level-4', display: 'Facility', system: null, depth: 4 })).toBe('Facility')
    })

    it('numbers the level itself when the CodeSystem published no display', () => {
        // Never the `level-2` casing: a tree row and the panel beside it would then state one fact
        // in two spellings.
        expect(levelLabel({ code: 'level-2', display: null, system: null, depth: 2 })).toBe('Level 2')
    })

    it('shows a level that is not numbered as the code it was published under', () => {
        expect(levelLabel({ code: 'district', display: null, system: null, depth: null })).toBe('district')
    })
})

describe('decoding the geometry attachment', () => {
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

    it('answers null for a unit publishing no attachment at all', () => {
        expect(boundaryOf(unit('DiszpKrYNg8'))).toBeNull()
        expect(attachmentGeometryOf(unit('DiszpKrYNg8'))).toBeNull()
    })

    it('reads a Point attachment as a point, which is what DHIS2 stores for a facility', () => {
        const read = attachmentGeometryOf(unit('MgFYJDBqSSs'))

        expect(read?.boundary).toBeNull()
        expect(read?.unreadable).toBe(false)
        expect(read?.points).toEqual([{ unitId: 'MgFYJDBqSSs', longitude: -12.1, latitude: 9.2 }])
    })

    it('reads a MultiPoint attachment as every point it holds', () => {
        const many = btoa('{"type":"MultiPoint","coordinates":[[1,2],[3,4]]}')

        const read = attachmentGeometryOf(withBoundaryData(many))

        expect(read?.unreadable).toBe(false)
        expect(read?.points).toEqual([
            { unitId: 'X', longitude: 1, latitude: 2 },
            { unitId: 'X', longitude: 3, latitude: 4 },
        ])
    })

    it('calls an attachment unreadable only when it holds nothing this map can draw', () => {
        const unreadable = (payload: string) => attachmentGeometryOf(withBoundaryData(payload))?.unreadable

        expect(unreadable('not-base64-at-all!!')).toBe(true)
        expect(unreadable(btoa('{"type":"Feature"}'))).toBe(true)
        // A shape with no mark on this map. Counting it is the honest answer; drawing nothing and
        // saying nothing would not be.
        expect(unreadable(btoa('{"type":"LineString","coordinates":[[0,0],[1,1]]}'))).toBe(true)
        expect(unreadable(btoa('{"type":"Point","coordinates":["west","north"]}'))).toBe(true)
        expect(unreadable(btoa('{"type":"Point","coordinates":[1,2]}'))).toBe(false)
    })

    it('answers no boundary for a Point attachment, because a point is not a polygon', () => {
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
        // Bo and Badjia publish a position beside their polygons - the exporter's centroid - and
        // the boundary wins, so neither is in the point set at all.
        expect(geometry.points.map((point) => point.unitId)).toEqual([
            'DiszpKrYNg8',
            'MgFYJDBqSSs',
            'lc3eMKXaEfw',
            'vWbkYPRmKyS',
        ])
        // Baoma alone: its attachment is not GeoJSON. Yoni's Point attachment is a point, not a
        // failure, which is the whole difference between this count and the one it replaced.
        expect(geometry.unreadableGeometries).toBe(1)
        expect(hasGeometry(geometry)).toBe(true)
    })

    it('keeps the position when a unit states one twice, and never draws the same unit twice', () => {
        const geometry = readGeometry(locations)

        // Bargbe publishes a position AND a Point attachment at other coordinates. The R4 element
        // is what every other FHIR client reads, so it is what the map draws - once.
        const bargbe = geometry.points.filter((point) => point.unitId === 'lc3eMKXaEfw')
        expect(bargbe).toEqual([{ unitId: 'lc3eMKXaEfw', longitude: -11.62, latitude: 7.72 }])
    })

    it('takes the attachment point for a unit that states no position, which is the facility case', () => {
        const geometry = readGeometry(locations)

        expect(geometry.points.filter((point) => point.unitId === 'MgFYJDBqSSs')).toEqual([
            { unitId: 'MgFYJDBqSSs', longitude: -12.1, latitude: 9.2 },
        ])
    })

    it('keeps the position of a unit whose attachment is unreadable', () => {
        const geometry = readGeometry(locations)

        expect(geometry.points.some((point) => point.unitId === 'vWbkYPRmKyS')).toBe(true)
    })

    it('draws a unit with a boundary as the boundary alone, dropping its centroid position', () => {
        const geometry = readGeometry(locations)

        // Bo states both: a Polygon attachment and a position inside it. One unit, one mark.
        expect(geometry.boundaries.some((boundary) => boundary.unitId === 'O6uvpzGd5pu')).toBe(true)
        expect(geometry.points.some((point) => point.unitId === 'O6uvpzGd5pu')).toBe(false)
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
        expect(geometry.unreadableGeometries).toBe(0)
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

/**
 * What a picker may offer, and what a chosen unit is written as.
 *
 * THE OFFER IS THE INTERSECTION THE SERVER GRADES. `PrScoped001` publishes an assignment naming two
 * of the ten units, and `dhis2w_fhir_serve.capture.validate._assignment_issues` refuses a capture
 * outside it - so the set below is not a UI convenience, it is the set the facade accepts. The
 * absence of an artifact is the whole registry, and so is an artifact this server does not publish,
 * because that is how `capture.index._assignment` reads it.
 */
describe('offering the units a form may be captured against', () => {
    const tree = buildOrgUnitTree(locations)
    const scopedList = lists.find((list) => list.id === 'd2-pr-PrScoped001-org-units') ?? null

    it('offers the whole registry to a form that declares no assignment', () => {
        expect(admittedUnitIds(null)).toBeNull()
        expect(orgUnitChoices(tree, null)).toHaveLength(tree.total)
    })

    it('offers exactly the units a published assignment names', () => {
        const admitted = admittedUnitIds(scopedList)

        expect([...(admitted ?? [])].toSorted()).toEqual(['DiszpKrYNg8', 'O6uvpzGd5pu'])
        expect(orgUnitChoices(tree, admitted).map((choice) => choice.id)).toEqual([
            'O6uvpzGd5pu',
            'DiszpKrYNg8',
        ])
    })

    it('offers nothing at all for an assignment naming no published unit', () => {
        const empty: ResourceList = { resourceType: 'List', id: 'empty', entry: [] }

        // Not the same as no assignment: an empty List is a form assigned nowhere, and offering the
        // registry there would offer exactly what the server refuses with E1029.
        expect(orgUnitChoices(tree, admittedUnitIds(empty))).toEqual([])
    })

    it('walks the tree rather than the alphabet, and names each row`s parent', () => {
        const choices = orgUnitChoices(tree, null)

        expect(choices.map((choice) => choice.id)).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
            'DiszpKrYNg8',
            'vWbkYPRmKyS',
            'lc3eMKXaEfw',
            'fdc6uOvgoji',
            'EJoI3HuIUEV',
            'MgFYJDBqSSs',
            // The detached unit sorts last for the same reason it does in the tree: its parent was
            // left out of the selection, so it is a root by accident rather than by design.
            'Rp268JB6Ne4',
        ])
        expect(choices[0].parentName).toBeNull()
        expect(choices[1].parentName).toBe('Sierra Leone')
        expect(choices[3].name).toBe('Ngelehun CHC')
        expect(choices[3].level?.code).toBe('level-4')
    })

    it('keeps the hierarchy`s parent on a row whose parent is not itself offered', () => {
        const choices = orgUnitChoices(tree, admittedUnitIds(scopedList))

        // Badjia sits between Bo and Ngelehun CHC and is not assigned. The row still says where the
        // facility is, because that is a fact about the registry rather than about the offer.
        expect(choices[1].parentName).toBe('Badjia')
    })

    it('finds a unit by name, uid, or DHIS2 code, through the rule the tree filter uses', () => {
        const choices = orgUnitChoices(tree, null)
        const matching = (query: string) =>
            choices.filter((choice) => matchesUnit(choice, query)).map((choice) => choice.id)

        expect(matching('ngelehun')).toEqual(['DiszpKrYNg8'])
        expect(matching('diszpkryng8')).toEqual(['DiszpKrYNg8'])
        expect(matching('ou_ngelehun')).toEqual(['DiszpKrYNg8'])
    })
})

/**
 * The same offer as a hierarchy: what is pruned, what is disabled, and what it opens on.
 *
 * The fixture registry is the exact shape this mode exists for. `PrScoped001` admits Bo and
 * Ngelehun CHC, and Ngelehun sits under Badjia - a district the assignment does not name - so the
 * tree has to keep an unadmitted unit as context while dropping Bombali's whole branch, which
 * admits nothing anywhere below it. A picker that hid every unadmitted unit would hang the facility
 * off nothing; one that kept them all would render eight rows to offer two.
 */
describe('browsing the units a form may be captured against', () => {
    const tree = buildOrgUnitTree(locations)
    const scopedList = lists.find((list) => list.id === 'd2-pr-PrScoped001-org-units') ?? null
    const admitted = admittedUnitIds(scopedList)

    /** Every id the browse tree keeps, in the order the rows would render fully expanded. */
    const kept = (roots: ReturnType<typeof orgUnitBrowseTree>) =>
        visibleBrowseRows(roots, new Set(tree.byId.keys())).map((row) => row.node.id)

    it('keeps the whole registry for a form that declares no assignment, admitting everything', () => {
        const roots = orgUnitBrowseTree(tree, null)

        expect(kept(roots)).toHaveLength(tree.total)
        expect(kept(roots).slice(0, 4)).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
            'DiszpKrYNg8',
        ])
        expect(visibleBrowseRows(roots, new Set(tree.byId.keys())).every((row) => row.node.admitted)).toBe(
            true,
        )
    })

    it('prunes a branch admitting nothing and keeps an unadmitted unit that leads to one', () => {
        const roots = orgUnitBrowseTree(tree, admitted)

        // Sierra Leone and Badjia are not assigned and are kept: they are the chain that says which
        // Ngelehun CHC this is. Bombali, its two facilities, Bargbe, Baoma and the detached Adonkia
        // CHP admit nothing below them and are gone entirely.
        expect(kept(roots)).toEqual(['ImspTQPwCqd', 'O6uvpzGd5pu', 'YuQRtpLP10I', 'DiszpKrYNg8'])
    })

    it('marks exactly the assigned units as pickable', () => {
        const roots = orgUnitBrowseTree(tree, admitted)
        const rows = visibleBrowseRows(roots, new Set(tree.byId.keys()))
        const admittedIds = rows.filter((row) => row.node.admitted).map((row) => row.node.id)

        expect(admittedIds).toEqual(['O6uvpzGd5pu', 'DiszpKrYNg8'])
        expect(rows.map((row) => row.depth)).toEqual([0, 1, 2, 3])
    })

    it('prunes everything for an assignment naming no published unit', () => {
        const empty: ResourceList = { resourceType: 'List', id: 'empty', entry: [] }

        expect(orgUnitBrowseTree(tree, admittedUnitIds(empty))).toEqual([])
    })

    it('finds the chain above a unit, and answers null for one the tree pruned away', () => {
        const roots = orgUnitBrowseTree(tree, admitted)

        expect(browseAncestorIds(roots, 'DiszpKrYNg8')).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
        ])
        expect(browseAncestorIds(roots, 'ImspTQPwCqd')).toEqual([])
        expect(browseAncestorIds(roots, 'fdc6uOvgoji')).toBeNull()
    })

    it('opens on the selection`s ancestors, and on the roots when nothing is held', () => {
        const roots = orgUnitBrowseTree(tree, admitted)

        expect([...expandedForSelection(roots, 'DiszpKrYNg8')]).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'YuQRtpLP10I',
        ])
        // A root has no ancestors, and a collapsed tree is not an opening state - so it falls back
        // to the same one level down that an empty picker opens on.
        expect([...expandedForSelection(roots, 'ImspTQPwCqd')]).toEqual(['ImspTQPwCqd'])
        expect([...expandedForSelection(roots, null)]).toEqual(['ImspTQPwCqd'])
        expect([...expandedForSelection(roots, 'fdc6uOvgoji')]).toEqual(['ImspTQPwCqd'])
    })

    it('draws a closed branch as one row, and states the nesting on every row it draws', () => {
        const roots = orgUnitBrowseTree(tree, null)
        const rows = visibleBrowseRows(roots, expandedForSelection(roots, null))

        // Sierra Leone open, its two districts closed - so Ngelehun CHC is four levels down and not
        // mounted at all. The detached root is the second row of the top level.
        expect(rows.map((row) => row.node.id)).toEqual([
            'ImspTQPwCqd',
            'O6uvpzGd5pu',
            'fdc6uOvgoji',
            'Rp268JB6Ne4',
        ])
        expect(rows[1]).toMatchObject({ depth: 1, parentId: 'ImspTQPwCqd', positionInParent: 1, siblingCount: 2 })
        expect(rows[3]).toMatchObject({ depth: 0, parentId: null, positionInParent: 2, siblingCount: 2 })
    })
})

/** How a chosen unit is written back, and read back off a submission. */
describe('an organisation unit as a reference', () => {
    const tree = buildOrgUnitTree(locations)
    const choices = orgUnitChoices(tree, null)
    const named = choices.find((choice) => choice.id === 'DiszpKrYNg8')

    it('writes `Location/<stem>` with the registry`s name as the display', () => {
        expect(orgUnitReference(named!)).toEqual({
            reference: 'Location/DiszpKrYNg8',
            display: 'Ngelehun CHC',
        })
    })

    it('carries no display for a unit the registry does not name', () => {
        const anonymous = { id: 'X', name: 'X', location: { resourceType: 'Location' as const, id: 'X' }, level: null, parentName: null }

        // `orgUnitName` falls back to the id, and a display that repeats the reference says
        // nothing - so it is left off rather than written as a name.
        expect(orgUnitReference(anonymous)).toEqual({ reference: 'Location/X' })
    })

    it('reads the unit id back off a reference, and refuses one naming something else', () => {
        expect(referencedUnitId({ reference: 'Location/DiszpKrYNg8' })).toBe('DiszpKrYNg8')
        expect(referencedUnitId({ reference: 'Organization/DiszpKrYNg8' })).toBeNull()
        expect(referencedUnitId({ reference: 'Location/' })).toBeNull()
        expect(referencedUnitId(null)).toBeNull()
    })

    it('derives the response-side extension url from the form`s own canonical', () => {
        expect(organisationUnitExtensionUrl(scopedQuestionnaire)).toBe(
            'http://localhost:8080/fhir/StructureDefinition/d2-organisation-unit',
        )
        expect(organisationUnitExtensionUrl({ resourceType: 'Questionnaire', status: 'draft' })).toBeNull()
    })

    it('knows which form kinds carry their unit on the extension rather than on subject', () => {
        expect(carriesUnitOnExtension('aggregate')).toBe(false)
        expect(carriesUnitOnExtension('event')).toBe(false)
        expect(carriesUnitOnExtension('tracker')).toBe(true)
        expect(carriesUnitOnExtension('tracker-event')).toBe(true)
        expect(carriesUnitOnExtension(null)).toBe(false)
    })
})

describe('the extent one unit is framed on', () => {
    const tree = buildOrgUnitTree(locations)
    const geometry = readGeometry(locations)

    it('frames a unit with geometry of its own on that geometry alone', () => {
        // Bo publishes a Polygon; the fit is that polygon's rectangle, not its subtree's union.
        const extent = unitExtent(tree, 'O6uvpzGd5pu', geometry)

        expect(extent.coverage).toBe('own')
        expect(extent.unitIds).toEqual(['O6uvpzGd5pu'])
        expect(extent.framedOnUnitId).toBeNull()
        expect(extent.bounds).toEqual([-12.2, 7.5, -11.2, 8.4])
    })

    it('frames a geometry-less parent on the union of its located descendants', () => {
        // The real Sierra Leone shape of the problem: a level-1 unit with no polygon of its own
        // over districts that have them. The fixture root carries geometry, so the case is built
        // by hand - a bare parent over one bounded child and one pinned grandchild.
        const bare: Location[] = [
            { resourceType: 'Location', id: 'P0000000001', name: 'Parent' },
            {
                resourceType: 'Location',
                id: 'C0000000001',
                name: 'Bounded child',
                partOf: { reference: 'Location/P0000000001' },
                extension: [
                    {
                        url: 'http://hl7.org/fhir/StructureDefinition/location-boundary-geojson',
                        valueAttachment: {
                            data: btoa(
                                JSON.stringify({
                                    type: 'Feature',
                                    geometry: {
                                        type: 'Polygon',
                                        coordinates: [
                                            [
                                                [10, 10],
                                                [12, 10],
                                                [12, 12],
                                                [10, 12],
                                                [10, 10],
                                            ],
                                        ],
                                    },
                                }),
                            ),
                        },
                    },
                ],
            },
            {
                resourceType: 'Location',
                id: 'G0000000001',
                name: 'Pinned grandchild',
                partOf: { reference: 'Location/C0000000001' },
                position: { longitude: 20, latitude: 5 },
            },
        ]
        const bareTree = buildOrgUnitTree(bare)
        const bareGeometry = readGeometry(bare)

        const extent = unitExtent(bareTree, 'P0000000001', bareGeometry)

        expect(extent.coverage).toBe('descendants')
        expect(new Set(extent.unitIds)).toEqual(new Set(['C0000000001', 'G0000000001']))
        // The union rectangle covers the child's polygon and the grandchild's pin together.
        expect(extent.bounds).toEqual([10, 5, 20, 12])
    })

    it('frames a bare leaf on the nearest located ancestor', () => {
        // Kagbere CHC publishes nothing; Bombali above it publishes a Polygon.
        const extent = unitExtent(tree, 'EJoI3HuIUEV', geometry)

        expect(extent.coverage).toBe('ancestor')
        expect(extent.framedOnUnitId).toBe('fdc6uOvgoji')
        expect(extent.unitIds).toEqual(['fdc6uOvgoji'])
        expect(extent.bounds).toEqual([-12.6, 8.8, -11.7, 9.6])
    })

    it('falls back to the whole registry for a fully bare branch, and to nothing for a bare registry', () => {
        // Adonkia CHP: no geometry, no located descendant, and its parent is not published at all.
        const orphaned = unitExtent(tree, 'Rp268JB6Ne4', geometry)
        expect(orphaned.coverage).toBe('registry')
        expect(orphaned.unitIds).toEqual([])
        expect(orphaned.bounds).toEqual(boundsOf(geometry.boundaries, geometry.points))

        const bare: Location[] = [{ resourceType: 'Location', id: 'P0000000001', name: 'Alone' }]
        const none = unitExtent(buildOrgUnitTree(bare), 'P0000000001', readGeometry(bare))
        expect(none.coverage).toBe('none')
        expect(none.bounds).toBeNull()
    })
})

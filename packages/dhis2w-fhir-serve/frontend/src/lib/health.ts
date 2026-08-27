/**
 * What `GET /facade/metadata-health` answers: what the DHIS2 instance behind this run holds that the guide
 * cannot carry cleanly, and how far the selection is translated.
 *
 * Not FHIR. There is no FHIR shape for "this DHIS2 name has a `<` in it" and none at all for a
 * translation that stops halfway, so the server answers plain JSON and these interfaces are its
 * models, field for field, in the wire's own spelling. The Python side is
 * `dhis2w_fhir_serve.health`.
 *
 * THE WORDING IS THE SERVER'S. Every finding carries the sentence `d2w fhir validate` wrote for it,
 * and nothing here rephrases one: the same defect read in a terminal and read in a browser has to be
 * the same sentence, or two people looking at one instance are looking at two reports. What this
 * module adds is arrangement - which severity a row sits under, which object kind it is shelved
 * beside, and the arithmetic under the coverage strip.
 */

/** How bad one finding is, in the terms `d2w fhir validate` grades by. */
export type FindingSeverity = 'error' | 'warning' | 'info'

/** Whether a finding sits on an object this project publishes, or on one it never reads. */
export type FindingScope = 'selection' | 'instance'

/** The three severities in the order a page reads them: what stops a build first. */
export const FINDING_SEVERITIES: readonly FindingSeverity[] = ['error', 'warning', 'info'] as const

/** What each severity is called on screen - the word a reader scans for, capitalised as a label. */
export const SEVERITY_LABELS: Record<FindingSeverity, string> = {
    error: 'Errors',
    warning: 'Warnings',
    info: 'Notes',
}

/** What one of each is called in a sentence about a single row. */
export const SEVERITY_SINGULAR: Record<FindingSeverity, string> = {
    error: 'Error',
    warning: 'Warning',
    info: 'Note',
}

/**
 * The hue each severity wears, off the state tokens the receipts already use.
 *
 * A KIND GETS A HUE, AND THESE ARE THE SAME THREE KINDS THE REST OF THE APP PAINTS. A defect that
 * stops a build is the red a DHIS2 rejection wears, one that degrades a page is the amber a refused
 * submission wears, and a note about an object no build reads is not a state at all - so it gets the
 * muted pair rather than a third alarm colour. Words take the measured ink variant where a fill is
 * tuned for dots; see the note beside the tokens in index.css.
 */
export const SEVERITY_TINTS: Record<FindingSeverity, { dot: string; badge: string }> = {
    error: {
        dot: 'bg-status-rejected',
        badge: 'border-status-rejected/40 text-status-rejected bg-status-rejected/10',
    },
    warning: {
        dot: 'bg-status-refused',
        badge: 'border-status-refused/40 text-status-refused-ink bg-status-refused/10',
    },
    info: {
        dot: 'bg-muted-foreground',
        badge: 'border-border text-muted-foreground bg-muted/40',
    },
}

/** One thing the validator found about one DHIS2 object. */
export interface MetadataFinding {
    severity: FindingSeverity
    scope: FindingScope
    /** The validator's own name for the kind of defect - `invalid-code`, `template-hostile-name`. */
    category: string
    /** The DHIS2 metadata collection the object belongs to, in DHIS2's own spelling. */
    resource_type: string
    uid: string
    name: string
    code: string | null
    /** The DHIS2 field at fault, or null where the category is about none of the object's own fields. */
    field: string | null
    /** The exact problem, in the validator's own words. */
    message: string
    /** What this grade costs the project, in a sentence rather than in a severity word. */
    cost: string
}

/** How many findings there are of each severity. */
export interface FindingCounts {
    errors: number
    warnings: number
    infos: number
}

/** Whether a locale covers less than half the selection's translatable strings, or half or more. */
export type LocaleStanding = 'sparse' | 'majority'

/** One selected object that carries a translation in a locale little of the selection carries. */
export interface LocaleCarrier {
    resource_type: string
    uid: string
    name: string
    /** Whether this object carries a name translation in this locale. */
    carries_name: boolean
    /** Whether this object has a DHIS2 form name and carries a form-name translation in this locale. */
    carries_form_name: boolean
}

/** One selected object holding no translation in a locale most of the selection is translated into. */
export interface LocaleUntranslated {
    resource_type: string
    uid: string
    name: string
    name_untranslated: boolean
    form_name_untranslated: boolean
}

/**
 * How much of the selection one locale covers, and which side of it the server listed.
 *
 * `standing` says which of the two lists carries anything: a sparse locale is told through the
 * objects that carry it, a majority locale through the objects that do not. Neither list means
 * something different depending on the other, which is why there are two of them.
 */
export interface LocaleCoverage {
    /** The BCP-47 tag, normalised from the Java locale DHIS2 stores - `pt_BR` arrives as `pt-BR`. */
    locale: string
    /** Selected objects carrying a name translation in this locale. */
    name_count: number
    /** Selected objects that have a DHIS2 form name and carry a form-name translation in this locale. */
    form_name_count: number
    standing: LocaleStanding
    carriers: LocaleCarrier[]
    missing: LocaleUntranslated[]
}

/**
 * How far the selection is translated.
 *
 * `locales` is the union of the tags the selection's own translations carry, which is what "in use
 * on this instance" means: an instance is being maintained in the languages somebody wrote into it.
 * Empty is an instance nobody has translated, which is one language and a whole state.
 */
export interface TranslationCoverage {
    locales: string[]
    object_count: number
    /** Of those objects, how many DHIS2 gives a form name - the denominator the form-name counts read against. */
    form_named_count: number
    per_locale: LocaleCoverage[]
}

/**
 * The whole answer.
 *
 * `available` false is a compiled run and nothing else, and it arrives as a body rather than as a
 * refusal: there is nothing wrong with serving a compiled guide, and `reason` is the sentence the
 * page renders in place of the report.
 */
export interface MetadataHealth {
    available: boolean
    reason: string | null
    /** The `[generate] hostile_names` posture the severities were graded under, in the server's own line. */
    graded_under: string | null
    /** Metadata objects the validator swept, across every collection the instance holds. */
    object_count: number
    counts: FindingCounts
    findings: MetadataFinding[]
    translations: TranslationCoverage
}

/** What this page assumes before the read lands: an answer with nothing in it and no reason stated. */
export const EMPTY_METADATA_HEALTH: MetadataHealth = {
    available: true,
    reason: null,
    graded_under: null,
    object_count: 0,
    counts: { errors: 0, warnings: 0, infos: 0 },
    findings: [],
    translations: { locales: [], object_count: 0, form_named_count: 0, per_locale: [] },
}

/** How many findings one severity holds, off the counts the server stated. */
export function countOf(counts: FindingCounts, severity: FindingSeverity): number {
    if (severity === 'error') return counts.errors
    if (severity === 'warning') return counts.warnings
    return counts.infos
}

/**
 * Whether there is nothing on this run to put on a page.
 *
 * A finding of any severity is something to show. So is a locale in use, which is a fact about the
 * instance rather than a defect in it - the coverage a reader came to see is worth a page even on an
 * instance the validator had nothing to say about. Neither is an instance nobody has translated
 * whose names and codes all pass, and that is the one state this answers true for.
 */
export function isClean(health: MetadataHealth): boolean {
    return health.findings.length === 0 && health.translations.locales.length === 0
}

/** The one word the validator's `<field> <name> ...` shape continues with, which is what makes the cut safe. */
const NAMED_SUBJECT_VERB = 'contains '

/**
 * One finding's message as a row reads it, with the head the row's own columns already carry cut.
 *
 * THE VALIDATOR WRITES FOR A TERMINAL, where a finding is one line and has to name its subject:
 * `name CMC Post abortion related services - E&C/D&C contains '&' which the IG publisher ...`. A row
 * has an Object column and a Field column, so that head is the row's first two cells said a third
 * time, and it pushes the sentence a reader came for off the side of the table.
 *
 * THE CUT IS THE WHOLE SHAPE OR IT DOES NOT HAPPEN. It fires on the field label, the object's name,
 * and the verb that shape always continues with - all three, exactly - and the verb is what keeps it
 * honest: a data element named `Weight` whose form name is `Weight in kg` opens its finding with
 * `form name Weight in kg contains ...`, and matching on the name alone would cut it to `in kg
 * contains ...`. Anything the shape does not fit is rendered exactly as the validator wrote it, so a
 * change of wording upstream costs a head on a row rather than a mangled sentence.
 *
 * The wire payload is untouched either way: this is what the cell shows, not what the run found.
 */
export function findingMessage(finding: MetadataFinding): string {
    if (finding.field === null) return finding.message
    const head = `${finding.field} ${finding.name} ${NAMED_SUBJECT_VERB}`
    if (!finding.message.startsWith(head)) return finding.message
    return `Contains ${finding.message.slice(head.length)}`
}

/**
 * The findings one filter leaves, matched against what a reader would type.
 *
 * The object's name and its uid, because those are the two strings a person has in front of them -
 * a name they read in DHIS2, or a uid they copied out of a build log. Case-insensitive and a
 * substring rather than a prefix: half a name is what somebody types when they are not sure how the
 * instance spelled the rest of it.
 */
export function matchingFindings(findings: MetadataFinding[], query: string): MetadataFinding[] {
    return matchingObjects(findings, query)
}

/** One object kind's findings, under the kind DHIS2 calls it. */
export interface FindingGroup {
    /** The DHIS2 metadata collection, in DHIS2's own spelling - `dataElements`, `organisationUnits`. */
    resourceType: string
    findings: MetadataFinding[]
}

/** One severity's findings, shelved by the object kind each is about. */
export interface SeverityShelf {
    severity: FindingSeverity
    /** How many findings the shelf holds, over every group on it. */
    total: number
    groups: FindingGroup[]
}

/**
 * The findings arranged as the page reads them: severity first, then object kind.
 *
 * SEVERITY LEADS BECAUSE IT IS WHAT A READER CAME FOR. An error stops the build and a note does not,
 * so the errors are the first thing on the page whichever kind of object they are about; the kind is
 * the second cut, because a person fixing names fixes a run of data elements at once.
 *
 * A severity holding nothing is dropped rather than rendered empty, and so is a kind: a heading over
 * no rows is a heading that makes a reader look for rows. Groups are ordered by the DHIS2 collection
 * name, and the findings inside one keep the order the server sent - which is the validator's own
 * order, by severity then type then name.
 */
export function shelveFindings(findings: MetadataFinding[]): SeverityShelf[] {
    return FINDING_SEVERITIES.map((severity) => {
        const held = findings.filter((finding) => finding.severity === severity)
        return { severity, total: held.length, groups: groupByResourceType(held) }
    }).filter((shelf) => shelf.total > 0)
}

/** One severity's findings bucketed by object kind, kinds in DHIS2's own alphabetical order. */
export function groupByResourceType(findings: MetadataFinding[]): FindingGroup[] {
    const buckets = new Map<string, MetadataFinding[]>()
    for (const finding of findings) {
        const held = buckets.get(finding.resource_type)
        if (held === undefined) buckets.set(finding.resource_type, [finding])
        else held.push(finding)
    }
    return [...buckets.entries()]
        .toSorted((left, right) => left[0].localeCompare(right[0]))
        .map(([resourceType, held]) => ({ resourceType, findings: held }))
}

/**
 * One locale's coverage as the strip states it: how many of the selection's translatable strings it has.
 *
 * THE DENOMINATOR IS EVERY STRING, NOT EVERY OBJECT. A data element carries two strings DHIS2 puts on
 * a page - the name every vocabulary displays and the form name a question is asked under - and a
 * locale that translated the first and not the second has done half the work on that object. So the
 * total is the objects plus the form-named ones among them, and the covered count is the two counts
 * the server stated added together.
 *
 * A selection with nothing in it is 0 of 0, which reads as complete and is: there is nothing to
 * translate. Callers render the ratio rather than dividing by it.
 */
export interface CoverageRatio {
    locale: string
    covered: number
    total: number
    /** The share covered, 0 to 1, and 1 for a selection with nothing to translate. */
    share: number
    standing: LocaleStanding
    /** The objects that carry this locale, filled where it is sparse and empty where it is not. */
    carriers: LocaleCarrier[]
    /** The objects that do not, filled where it is a majority locale and empty where it is sparse. */
    missing: LocaleUntranslated[]
}

/** One locale's covered-over-total, over every translatable string in the selection. */
export function coverageRatio(coverage: TranslationCoverage, locale: LocaleCoverage): CoverageRatio {
    const total = coverage.object_count + coverage.form_named_count
    const covered = locale.name_count + locale.form_name_count
    return {
        locale: locale.locale,
        covered,
        total,
        share: total === 0 ? 1 : covered / total,
        standing: locale.standing,
        carriers: locale.carriers,
        missing: locale.missing,
    }
}

/** How many objects one locale's row lists - its carriers where it is sparse, the rest where it is not. */
export function listedCount(ratio: CoverageRatio): number {
    return ratio.standing === 'sparse' ? ratio.carriers.length : ratio.missing.length
}

/** Every locale's ratio, weakest first - the language somebody stopped translating leads the strip. */
export function coverageRatios(coverage: TranslationCoverage): CoverageRatio[] {
    return coverage.per_locale
        .map((locale) => coverageRatio(coverage, locale))
        .toSorted((left, right) => left.share - right.share || left.locale.localeCompare(right.locale))
}

/** One share as a whole percent, which is the only precision a strip of this size can carry. */
export function coveragePercent(ratio: CoverageRatio): number {
    return Math.round(ratio.share * 100)
}

/** What either translation list is a list of: an object a reader can find by name or by uid. */
export interface NamedObject {
    uid: string
    name: string
}

/**
 * The objects one filter leaves, matched the way the findings are - by object name and by uid.
 *
 * One filter box over the page rather than one per section: a reader looking for an object is
 * looking for it wherever it is, and a name that matched the findings and not the translation lists
 * would hide half of what is known about it.
 */
export function matchingObjects<T extends NamedObject>(objects: T[], query: string): T[] {
    const wanted = query.trim().toLowerCase()
    if (wanted === '') return objects
    return objects.filter(
        (object) => object.name.toLowerCase().includes(wanted) || object.uid.toLowerCase().includes(wanted),
    )
}

/**
 * Every locale's ratio with the objects it lists narrowed to the filter, the counts left as they are.
 *
 * The counts are what the instance holds and a filter does not change them - a meter that moved when
 * somebody typed would be answering a different question from the one it is labelled with.
 */
export function matchingRatios(coverage: TranslationCoverage, query: string): CoverageRatio[] {
    return coverageRatios(coverage).map((ratio) => ({
        ...ratio,
        carriers: matchingObjects(ratio.carriers, query),
        missing: matchingObjects(ratio.missing, query),
    }))
}

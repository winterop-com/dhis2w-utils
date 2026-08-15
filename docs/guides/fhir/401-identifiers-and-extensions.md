# Identifiers and the D2 extensions

**Who this is for:** integration developers consuming a generated guide or a
served facade, who need to know exactly where the DHIS2 identity of every
artifact lives and what the `D2*` extensions carry.

**Before you start:** read [FHIR for DHIS2 people](101-fhir-concepts.md) for
what an extension and an identifier slice are; have a generated project nearby
([quickstart](101-quickstart.md)) if you want to read real output alongside.

**You will be able to:**

- resolve any generated artifact or concept back to its DHIS2 UID and code
- read `D2Period` and `D2AttributeValue` extensions off a resource
- rely on the fall-back rules instead of special-casing missing codes

## The D2Period extension

DHIS2 reporting periods have no FHIR equivalent: a FHIR `Period` is a pair of
instants, while a DHIS2 period is a *typed* interval - `202401` is not merely
1-31 January, it is the January instance of the `Monthly` period type, and the
type is what makes it comparable, aggregatable, and round-trippable.

`D2Period` carries all three facts:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `iso` | `string` | 1..1 | The DHIS2 ISO period identifier, e.g. `202401` |
| `type` | `code` | 1..1 | The period type, bound (required) to `D2PeriodType_VS` |
| `period` | `Period` | 0..1 | The date range the identifier resolves to |

Its context names exactly the two resources that carry it: `QuestionnaireResponse`
(every example response against a data set form) and `MeasureReport` (the later
summary projection). A context of bare `Element` would attach it anywhere, which
the IG publisher's QA calls out as an unbounded extension.

The `D2PeriodType_CS` CodeSystem publishes every period type DHIS2 registers,
each displayed with its ISO format: `Daily (yyyyMMdd)`, `Monthly (yyyyMM)`,
`FinancialApril (yyyyApril)`, and so on through the weekly variants, the
bi-weekly and bi-monthly types, the November-anchored financial types, and the
rest of the twenty-three.

The matching parser lives in `dhis2w_fhir.period`:

```python
from dhis2w_fhir.period import parse_period

parse_period("2024BiW2")
# PeriodValue(iso='2024BiW2', period_type='BiWeekly',
#             start_date=date(2024, 1, 15), end_date=date(2024, 1, 28))
```

`recent_periods` is its inverse, and the example target's way of finding a period
worth looking for data in: the most recent periods of a type whose end date is
already past, newest first.

```python
import datetime
from dhis2w_fhir.period import recent_periods

recent_periods("Monthly", 3, datetime.date(2026, 8, 2))
# ['202607', '202606', '202605']
```

It is written as an inverse rather than as a second transcription of the upstream
month offsets: each type declares only how its ISO strings are spelled for a given
year, and `parse_period` decides which of those exist and what dates they cover -
so the two can never disagree.

## The D2AttributeValue extension

A DHIS2 `Attribute` is the metadata extensibility point: any object can carry
typed key-value pairs under `attributeValues`, and instances use them for the
codes that tie DHIS2 to everything around it - a national registry id on a
facility, an external warehouse key, an ICD-10 code on a data element. Those
pairs are instance-specific by definition, so no FHIR element holds them and they
travel as a complex extension instead.

`D2AttributeValue` carries one such pair:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `attributeId` | `string` | 1..1 | The UID of the DHIS2 attribute the value belongs to |
| `attributeCode` | `string` | 0..1 | The attribute's DHIS2 code, absent when the instance left it unset |
| `value` | `string` | 1..1 | The value the object holds, as DHIS2 sends it |

Its `^context` names the five resource types that carry it: `Organization`,
`Location`, `CodeSystem`, `ValueSet`, and `Questionnaire`.

**`attributeCode` is optional because DHIS2 leaves most attributes uncoded.**
On the Lao instance eleven of twelve attributes have no `code` at all. An
uncoded attribute gets no `attributeCode` sub-extension rather than an empty
one - an empty code would claim the instance coded that attribute.

**`value` is a string whatever the attribute declares.** DHIS2 sends every
attribute value as a string regardless of the attribute's `valueType`, and one
real attribute on that instance carries a whole GeoJSON document that way. The
extension takes the wire value as it stands rather than re-typing it.

**The code is a join, resolved once per generate run.** The wire shape of an
attribute value is `{"attribute": {"id": "..."}, "value": "..."}` - an id and
nothing else, with no code, no name, and no value type. So each generate target
calls `resolve_attribute_code_index`, which reads `id,code` for every attribute
off `/api/attributes` **unpaged**: DHIS2 answers 50 attributes to a page by
default, and an instance defining more than one page of them would otherwise
lose the tail of the join silently. Attributes DHIS2 left without a code are
absent from the index rather than present with an empty entry, which is what the
optional `attributeCode` reads from.

**Where the values land today.** Organisation units carry them on both halves of
the registry pair, option sets on both the CodeSystem and the ValueSet, and data
sets, event programs, and tracker program stages on their Questionnaire.
Concept-level attribute values -
those on individual data elements and options - are not emitted: a
`CodeSystem.concept` has no carrier chosen for them yet, and that choice is its
own decision, sized in
[fhir roadmap section 9.2](../../project/fhir-roadmap.md#92-mid-term). Nor is a
value promoted to `identifier` when DHIS2 marks its attribute `unique`; every
value rides the extension, and the identifier shape is the other half of that
same roadmap entry.

## Program rules

DHIS2 enforces program rules on import, not only in the Capture app: a tracker
payload whose values a `SHOWERROR` rule refuses comes back `E1300` and nothing
lands. A form that stated none of that would ask for answers the server rejects,
so every rule a published program holds reaches its forms - in one of three
tiers, and each rule is in exactly one.

**Tier 1 - a numeric refusal becomes a bound.** A rule whose single action is
`SHOWERROR` and whose condition compares one question against one number becomes
the core `minValue` / `maxValue` extensions on that question, on the `value[x]`
its item type takes. The bound is the complement of what the rule refuses:
`#{hemoglobin} > 99` with `SHOWERROR` admits up to and including 99, so the
question carries `maxValue` 99. A refusal that is strict at the boundary
(`>= 99`) has no inclusive complement in a decimal, so it bounds a whole-number
question one step in (98) and goes to tier 3 on a decimal one. Where the question
already carries a bound from its DHIS2 value type - a percentage admits 0..100 -
the tighter of the two is published, once.

`SHOWWARNING` never becomes a bound. DHIS2 lets a warned value through, and a
`maxValue` a server accepts answers past is a constraint nobody enforces.

**Tier 2 - a single-question hide becomes `enableWhen`.** A rule whose actions
are all `HIDEFIELD` and whose condition compares one *other* question against one
literal becomes core `item.enableWhen` entries on each question it hides. DHIS2
hides when its condition holds and R4 shows when its own does, so the operator is
negated: a hide when the apgar score is over 7 shows when the score is 7 or less.

Two things keep that inversion faithful. A comparison against the empty string is
DHIS2's spelling of "no answer", so it becomes the `exists` operator rather than
an empty `answerString` - which R4 has no valid form for. And DHIS2 evaluates a
rule over a blank question by substituting the value type's empty value, where R4
leaves a question whose `enableWhen` no answer can satisfy hidden. Where the DHIS2
condition is false of a blank answer - so the question starts out shown - the
translation adds the arm that says so, joined by `enableBehavior = #any`:

```
* item[=].enableWhen[+].question = "a3kGcGDCuk6"
* item[=].enableWhen[=].operator = #"<="
* item[=].enableWhen[=].answerDecimal = 7
* item[=].enableWhen[+].question = "a3kGcGDCuk6"
* item[=].enableWhen[=].operator = #exists
* item[=].enableWhen[=].answerBoolean = false
* item[=].enableBehavior = #any
```

**Tier 3 - everything else is published, non-normatively.** Every other rule
becomes a repeating `D2ProgramRule` extension on the Questionnaire:

| Sub-extension | Type | Cardinality | Meaning |
| --- | --- | --- | --- |
| `rule` | `id` | 1..1 | The UID of the DHIS2 program rule |
| `name` | `string` | 1..1 | The name the instance holds it under, with its translations |
| `description` | `string` | 0..1 | The rule's free text, absent when the instance states none |
| `condition` | `string` | 1..1 | The DHIS2 expression the server evaluates, character for character |
| `action` | `code` | 1..1 | What the rule does, from `D2ProgramRuleAction_VS` |

Nothing about tier 3 is normative. It states that the server holds a rule this
form cannot express, so a consumer knows an answer the form admits may still be
refused - and can show the rule to a person even where it cannot evaluate it. A
rule tiers 1 or 2 expressed is never repeated here.

The `condition` is verbatim, spacing included, because it is the string an
administrator searches the instance for. Nothing is prettified.

**The grammar is conservative by construction.** The parser reads one shape and
no other: a single comparison between one `#{variable}` and one literal, in
either order, optionally joined by `&&` to a `d2:hasValue` guard naming that same
variable, with the variable resolved through `programRuleVariables` to a question
the same form asks. Anything else - two variables, an `||` chain, a `d2:` function
beyond `hasValue`, a negation, an `A{...}` attribute reference, a variable reading
another program stage - goes to tier 3 whole. So does a rule whose actions this
form cannot all state: a hide targeting a question on another stage's form is
published rather than half-translated, because a rule half-read publishes a
constraint that is neither what DHIS2 enforces nor nothing.

**Every form of a program carries its program's rules.** A rule belongs to the
program rather than to one stage, so a stage form, its siblings, and the
registration form beside them all state the same list - a consumer holding one
form learns from that form alone which rules the server may refuse its answers
under. An aggregate form carries none: DHIS2 states program rules over programs.

**`d2w fhir forward` reads them back.** DHIS2 names the rule that refused an
import by UID alone, and the guide published that UID beside the rule's name, so
the run's rejection roll-up reads `Generated by ProgramRule (\`Show error for
high hemoglobin value\`)` rather than twelve characters. The UID itself stays
untouched on the response's own `.report.json`, which is where a reader goes for
the machine record.

Only the published rules are nameable that way, which is the set that matters: a
client answering a form cannot trip a rule the form already states, so the
refusals that reach a reader are the ones tier 3 published. A UID the guide holds
no rule for still generalises to `` `...` ``, so one cause stays one row.

## Identifiers

Every FHIR artifact representing a DHIS2 object exposes **both** DHIS2
identifiers - the UID and the code - wherever FHIR gives it a slot. This is the
standing rule for every generator, present and future (Questionnaire, Patient,
EpisodeOfCare, MeasureReport identifiers will follow it).

- **Instances** carry identifier slices discriminated on `system`:
  `{base}/id/<kind>` holds the UID and `{base}/id/<kind>-code` holds the code.
  Both slices are always emitted, on the Organization and on the Location alike.
- **Option-set concepts** carry the complementary identifier as a concept
  property: in id mode every concept gets `dhis2-code`, in code mode every
  concept gets `dhis2-id`. No option goes without the pair - a DHIS2 option must
  have a code, so there is always one to carry.
- **Data-dictionary and registry concepts** carry `dhis2-code` only where DHIS2
  states a code. A data element, a tracked entity attribute, a category option
  combo, or an organisation unit may have none, and the concept code is the UID
  already - repeating it under a `dhis2-code` label would publish a code the
  instance does not hold.
- **Option-set CodeSystems and ValueSets** carry the source set's own pair as
  `identifier` business identifiers, under `{base}/id/option-set` and
  `{base}/id/option-set-code` - the same two URLs the `$DHIS2-OS` /
  `$DHIS2-OS-CODE` aliases name, written out in full because these resources
  ship as JSON rather than FSH.

- **Questionnaires** carry the source object's pair: a data set through `$DHIS2-DS` /
  `$DHIS2-DS-CODE`, an event program through `$DHIS2-PROGRAM` /
  `$DHIS2-PROGRAM-CODE`, a tracker program stage through `$DHIS2-PS` / `$DHIS2-PS-CODE`,
  and a tracker program's registration form through `$DHIS2-PROGRAM` /
  `$DHIS2-PROGRAM-CODE`, because that form *is* the program.
- **Tracker stage Questionnaires carry a third slice**, `$DHIS2-PROGRAM` holding the
  UID of the program the stage belongs to. That slice is the grouping handle: a
  program's whole capture surface - its registration form, whose own identity is that
  same pair, and every one of its stages - is one search on any FHIR server, in the
  order the server returns them.

    ```
    GET Questionnaire?identifier=http://dhis2.org/fhir/id/program|IpHINAT79UW
    ```

- **A registration Questionnaire carries a third slice too**, `$DHIS2-TET` holding the
  UID of the tracked entity type it enrols a person as - what a client needs to know
  before it can name the person its response creates.

**A unique attribute's values are identifiers.** A DHIS2 attribute value is an
arbitrary key-value pair, so it normally rides the
[`D2AttributeValue` extension](#the-d2attributevalue-extension). An attribute DHIS2
declares **unique** is a different thing: its value names the object rather than
annotating it, which is what a FHIR `Identifier` is for. Those values leave the
extension and join the resource's identifier list - after the UID and code slices, so
the order stays stable across runs - under a namespace of their own:

```
{base}/attribute/{attributeUid}
```

The namespace keys on the attribute **UID**, not its code: a DHIS2 attribute code may
hold spaces, and a system URI may not. Every emitting surface follows the same rule -
Organization and Location, an option set's and a category's CodeSystem/ValueSet pair,
and a Questionnaire.

**A unique tracked entity attribute's values are identifiers too**, under a family of
their own:

```
{base}/tracked-entity-attribute/{attributeUid}
```

A tracked entity attribute is a different DHIS2 object from a metadata attribute - it
is a question asked about a person, not an annotation on a metadata object - so it gets
its own namespace rather than sharing the one above, and its own extension
(`D2TrackedEntityAttributeValue`) for the values that are not identifiers. The rule for
which is which is the same: DHIS2 enforces uniqueness on the attribute, so its value
names the person. `D2TEA_CS` publishes that flag as a `unique` concept property, which
is what a server reads to decide. This is the family
[`GET /Patient?identifier=...`](401-consume-the-fhir-api.md#patient-who-a-person-is-in-the-instance)
searches on.

These per-attribute namespaces are declared **by convention rather than as
NamingSystems**, and deliberately so: the foundation layer is built from `fhir.toml`
alone and never reads an instance, so it cannot know which attributes exist, let alone
which are unique. A NamingSystem naming an attribute the instance does not have would
be worse than none. What `d2-naming-systems.fsh` declares is the fixed family below.

**Every system is declared as a NamingSystem.** `foundation/d2-naming-systems.fsh`
emits one `NamingSystem` per identifier system - a UID system and a code system for
each of the organisation unit, option set, category, data set, program, data element,
category option combo, program stage, and tracked entity type, plus a UID system alone
for the tracked entity and the tracker enrollment. Those last two are data objects rather
than metadata: DHIS2 gives them no `code` attribute, so there is no code system to declare.
Each declaration is `kind = #identifier` with a single
preferred `uri` uniqueId and a description of the convention, the code slot's UID
fall-back included. Without them, a validator meeting `{base}/id/org-unit` has no
definition to resolve and warns on every artifact carrying one. Because R4 makes
`NamingSystem.date` mandatory, the declarations carry a pinned date rather than
the time of the run - a generated timestamp would rewrite the file every time.

**The code slot falls back to the UID.** DHIS2 codes are optional, and plenty of
instances have units without one. Rather than emit a half-populated identifier,
the code slot repeats the UID whenever the DHIS2 code is missing or is not a
valid FHIR code. That keeps the profiles conformant (`dhis2code` is `1..1`) and
keeps consumers from special-casing absence. It is a "for now" state, owned by
the instance team: `d2w fhir validate` warns on every organisation unit without a
code precisely so those fall-backs get replaced with real codes over time.

## See also

- [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md) - how a
  consumer holding a generated concept code gets its DHIS2 identifiers back.
- [Generate the IG source](201-generate.md#know-the-eight-targets) - the `foundation` target that
  writes the extensions and NamingSystems described here.
- [How things are generated](301-generation.md#naming) - which DHIS2 identifier
  becomes an artifact's id, name, and file name.

Next: [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md)

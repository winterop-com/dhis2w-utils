---
title: Harmonization across country guides
---

# Harmonization across country guides

One DHIS2 instance, one project, one guide. That is
[decision 3.10](fhir-roadmap.md#310-a-project-is-one-dhis2-instances-fhir-home) and it
is settled. This page is about what happens when there are ten of them.

The fleet the toolkit is being pointed at is roughly ten country instances - one real
national HMIS, several play and demo servers, more arriving. Each gets its own project,
its own canonical, its own registry, its own terminology, and its own published guide.
Nothing about that changes. The harmonization question is the one that sits on top:
**how do N country guides relate to each other, without pretending the instances agree
when they do not?**

That question has three different answers, because it is three different products
wearing one word. This page separates them, states what each needs, says honestly which
of those things exist in this repository today, and proposes one concrete first slice.

**This is a design document, not a build.** Nothing here is scheduled. Section 7 is the
list of calls the owner has to make before any of it is, and section 8 is the list of
things that stay out regardless of the answers.

## 1. Three tiers, stated as three products

Harmonization is usually asked for as one thing and delivered as one of these three. They
share a vocabulary and almost nothing else: different artifacts, different consumers,
different prerequisites, different failure modes. Conflating them is how a terminology
report gets sold as comparable indicators.

| Tier | The product | Who consumes it | FHIR carrier | Gated on |
| --- | --- | --- | --- | --- |
| 1. Terminology alignment | A statement of which country codes mean the same thing | Anyone integrating across two instances; the tier-2 and tier-3 layers | `ConceptMap`, `$translate` | A matching key that is not a name, and a decision about a reference vocabulary |
| 2. Structural alignment | A master guide the country guides derive from | Implementers building one bridge that works against several countries | A published IG package, `dependsOn`, shared profiles and logical models | Two real country guides existing first |
| 3. Indicator comparability | The same indicator, computed comparably, across instances | Analysts, funders, regional programmes | `Measure`, `MeasureReport` | Tiers 1 and 2, the data-serving leg, and an actual agreement between countries |

They are ordered because each one's honesty depends on the one before it. A master
guide that shares a profile but not a vocabulary shares a shape and no meaning. An
indicator computed over two instances whose option sets disagree produces a number that
looks comparable and is not - which is worse than producing nothing.

The order is a dependency, not a schedule. Tier 1 is the only one this repository could
start on with what it has.

## 2. Tier 1 - terminology alignment

**What it is.** For each country instance, a statement of which of its option sets,
categories, and data elements correspond to a shared reference vocabulary, or to the
corresponding object in another country's instance. The product is not a merged
vocabulary; it is a set of mappings between vocabularies that stay separate. Each
country keeps its own codes, its own option sets, and its own guide. What is added is
the translation between them, published as a resource rather than kept in a
spreadsheet.

**Why FHIR makes this the cheapest tier.** The mechanism is already built. Every
generated guide ships one `ConceptMap` per option set and per category, into
`ig/input/resources/concept-maps/`, and `d2w fhir serve` answers R4's type-level
`ConceptMap/$translate` over them in both compiled and `--live` mode. Those maps are
**self-referential today** - they take a generated concept code back to the DHIS2 option
UID and the DHIS2 option code, two identifier conventions for one object, every row
`equivalence = #equal`. The shape and the plumbing of a cross-vocabulary map are the
same; what changes is that `group.target` names something outside the instance and the
equivalence stops being `#equal` on every row. See
[Terminology and ConceptMaps](../guides/fhir/401-terminology-and-conceptmaps.md#conceptmaps-the-route-back-to-dhis2)
for the shape that already ships.

**The seeded-attribute pattern is the data source.** The cheapest way to get an
option-to-external-code mapping out of a DHIS2 instance is to have the instance carry it:
a DHIS2 `Attribute` - the play stacks already seed a `SNOMED_CODE` one - valued on each
option. The toolkit already speaks that pattern from both ends. `d2w metadata
option-sets attributes set` writes a value; `d2w metadata option-sets attributes find`
is the reverse lookup an integrator wants, taking an external SNOMED / ICD / LOINC code
and returning the DHIS2 option it maps to. On the FHIR side, DHIS2 attribute values reach
CodeSystems and ValueSets as `D2AttributeValue` extensions, and typed facts about a
concept reach it as `CodeSystem.property` under a `<identifier_system_base>/property/<code>`
URI - the mechanism the category axes on a category-option-combo concept already use.

**The gap in that path is specific and already recorded.** Attribute values on
*individual options* are not emitted, because `CodeSystem.concept` has no carrier chosen
for them - property or extension - and the choice has a volume cost worth measuring
before it is made: the Lao data-element CodeSystem carries 45,880 concepts. That is
roadmap entry
[9.2 "Attribute values on CodeSystem concepts"](fhir-roadmap.md#92-mid-term), and it is
the one repository-side prerequisite that tier 1's seeded route genuinely blocks on. A
seeded `SNOMED_CODE` on a DHIS2 option is invisible to the generated guide until that
carrier exists.

**Two topologies, and they are not equivalent.**

- **Star** - every country maps to one reference vocabulary. N maps, each independently
  reviewable, each meaningful on its own. Adding the eleventh country costs one map. The
  cost is that a reference vocabulary has to exist and be chosen, with whatever
  licensing that implies per country.
- **Mesh** - country maps to country. No reference vocabulary needed, so it can start
  immediately with two instances, and the first map is genuinely useful to the pair that
  owns it. The cost is N(N-1)/2 maps and no transitivity anyone should trust: a map from
  A to B composed with a map from B to C is a guess, not a mapping.

Mesh is defensible for exactly two instances that need to talk to each other. It is not
a fleet strategy. This is [decision H2](#7-decisions-reserved-for-the-owner).

**Prerequisites, honestly.**

| Prerequisite | State |
| --- | --- |
| A matching key across instances that is not a display name | Partly there - see section 6 |
| Option-level attribute values reaching the emitted CodeSystem | Missing - roadmap 9.2, carrier undecided |
| A reference vocabulary chosen | Not chosen - decision H1 |
| Code coverage good enough that codes can be the key | Unknown per instance until `d2w fhir validate` runs across the fleet |
| Any command that reads more than one instance in one run | Missing for FHIR - section 5 |

## 3. Tier 2 - structural alignment, or the master guide

**What it is.** An implementation guide the country guides derive from rather than
duplicate: the shared profiles, extensions, logical models, NamingSystems, and
CapabilityStatement, published on its own canonical as a real IG package, with each
country guide declaring a `dependsOn` on it and adding only what is genuinely its own -
its registry, its terminology, its forms.

This is the layer WHO SMART Guidelines calls L2-shaped: a Digital Adaptation Kit states
the data dictionary, the decision logic, and the indicator definitions in a
system-neutral form, and the L3 implementation guide is the machine-readable expression
of it for one context. The analogy is worth naming and worth not overclaiming - a master
guide assembled out of DHIS2 metadata conventions is not a DAK, has no clinical content
governance behind it, and would be dishonest to publish as one. What it borrows is the
layering: one thing that states the shared shape, several things that implement it.

**More of this already exists than it looks like.** The `foundation` target emits ten
artifacts and opens no client at all - the identifier NamingSystems, the period grammar,
the form-type vocabulary, the `D2AttributeValue` / `D2OrganisationUnit` /
`D2TrackerEnrollment` extensions, the response profiles, the `$generate`
OperationDefinition, the capture-server CapabilityStatement. Their *content* is
instance-independent by construction. Only their *addresses* are project-scoped, because
each project bakes its own canonical and its own naming tokens into them. Add the
canonical naming-token registry documented in the
[naming configuration](../guides/fhir/301-generation.md#naming) and the four DHIS2
identifier namespaces under `identifier_system_base`, and the shared layer is not a
design exercise - it is a promotion.

**The hard part is not the promotion. It is the namespace.** `identifier_system_base`
defaults to `http://dhis2.org/fhir`, and every guide generated with that default labels
its identifiers `http://dhis2.org/fhir/id/option` plus a DHIS2 UID. Inside one instance
that pair is unique. Across a fleet it is unique only to the degree that DHIS2 UIDs are
globally unique in practice - which is a property of the generator, not a guarantee of
the identifier system, and it is not a claim the toolkit currently states anywhere. Two
country instances that both derive from a common DHIS2 metadata package will share UIDs
by design, which is the case where the shared namespace is exactly right, and the case
where a naive cross-instance join is exactly wrong. `identifier_system_base` is already
the dial that answers this; what is missing is the decision about which way to turn it.
This is [decision H4](#7-decisions-reserved-for-the-owner).

**Prerequisites, honestly.**

| Prerequisite | State |
| --- | --- |
| Two real country guides, published, that a shared layer can be extracted *from* | One real national instance in play; zero published country guides |
| The identifier-namespace question answered | Open - decision H4 |
| A place for a master package to be published and versioned | Does not exist |
| Country projects able to declare a dependency | Not expressed - the scaffolded `sushi-config.yaml` writes no `dependencies:` block |

The first row is the one that matters. A shared layer extracted from one guide is that
guide with a second name on it, and every place it guessed wrong about the second
country is a guess that gets baked in before anyone can check it. Two first.

## 4. Tier 3 - indicator comparability

**What it is.** The analytics-facing end: an indicator - ANC first visit coverage, BCG
doses administered - defined once and computed from N country instances such that the
resulting numbers can be placed beside each other. This is what people usually mean when
they say harmonization out loud, and it is deliberately the farthest out.

**Why it is farthest out, in three parts.**

*It is a DHIS2 metadata problem before it is a FHIR problem.* Two instances computing
"ANC first visit coverage" differ in the numerator's data elements, the denominator's
population source, the disaggregation, the period type, and the completeness rule.
Publishing both as FHIR `Measure` resources makes the disagreement machine-readable; it
does not make it smaller. The FHIR layer's honest contribution here is to state the
definitions precisely enough that the disagreement is visible - which is valuable, and
is not the same as comparability.

*The FHIR carrier is already parked, deliberately.*
[Decision 3.3](fhir-roadmap.md#33-measurereport-is-not-a-capture-shape) places
`MeasureReport` in the conversion layer as a lossy analytics projection over the same
data, deferred until a consumer needs it, with a stated technical reason - R4's `mrp-1`
invariant forbids a data-collection MeasureReport from carrying groups, which is exactly
what a disaggregated DHIS2 data set needs. Nothing about a multi-country ask changes
that reading. `Measure` on the definition side is unblocked by it, but a `Measure` with
no `MeasureReport` under it is a published definition and no numbers.

*It needs the data leg the roadmap has as long-term.* Serving DHIS2 *data* through the
facade - not just its metadata - is the open half of "full circle" in
[roadmap 9.3](fhir-roadmap.md#93-long-term). Until a FHIR client can read one country's
values through the guide, there is nothing to compute a cross-country measure over
except the DHIS2 analytics API, which is a straight DHIS2 problem with no FHIR layer in
it at all.

**And it is a governance act.** Whether two ministries agree that their ANC indicator is
the same indicator is not a decision this toolkit gets to make, encode, or infer. The
most a tool can honestly do is state both definitions, state where they differ, and stop
there. Anything past that is a tool inventing agreement.

**Prerequisites, honestly:** tier 1 for the terms, tier 2 for the shared definition
layer, the data-serving leg for the numbers, and a real agreement between real countries
for the claim. Three of those four are missing and the fourth is not ours.

## 5. What exists, and what does not

The building blocks, graded. Ticked rows are shipped and usable today; the rest is what
a harmonization tier would have to build or decide.

| Capability | State | What harmonization needs of it |
| --- | --- | --- |
| Identity stem: `source = "id"` / `"code-or-id"` / `"code"` | [x] Shipped | Codes are the endgame. A cross-instance match on UIDs only works within a shared metadata lineage; a match on codes works wherever codes are maintained. This is the dial that decides which. |
| `d2w fhir validate` with its code-coverage line and `--code-source code` | [x] Shipped, per instance | Says exactly what one instance would pay to move to code-based identity. Nothing aggregates it across instances. |
| ConceptMaps per terminology family, plus `$translate` at serve | [x] Shipped, self-referential | The carrier for tier 1. Needs a second kind of map whose target is not the same DHIS2 object. |
| `CodeSystem.property` under `<identifier_system_base>/property/<code>` | [x] Shipped | The declaration mechanism a seeded external code would ride, once concept-level values have a carrier. |
| `d2w metadata option-sets attributes get / set / find` | [x] Shipped | Seeds and reverse-looks-up an external code on a DHIS2 option, instance by instance. |
| `d2w metadata diff-profiles` | [x] Shipped | The only cross-instance command in the toolkit: a structural diff of a narrow resource slice between exactly two profiles, ignoring per-instance noise. Not terminology-aware - it answers "did these two objects drift", not "do these two vocabularies mean the same thing". |
| `d2w fhir doctor`, with `--json` and its typed report | [x] Shipped, one instance per run | The per-instance verdict a fleet report would be built out of. There is deliberately no local `--profile`: one instance per run, named through the root flag. |
| Attribute values on individual options and data elements | [ ] Missing | Roadmap 9.2. Carrier undecided between `CodeSystem.property` and a concept extension; the choice has a measurable volume cost. |
| Fleet operations - any run that spans N profiles | [ ] Missing | Nothing in `d2w fhir` takes more than one profile. `diff-profiles` and `merge` take exactly two, and are metadata commands rather than FHIR ones. |
| Code coverage across the fleet | [ ] Unknown | Not a missing feature so much as a missing measurement: nobody has run `validate` against ten country instances and read the ten coverage lines together. |
| A reference vocabulary | [ ] Not chosen | Decision H1. |
| A master guide package | [ ] Does not exist | Tier 2, and gated on two published country guides. |
| Published country guides | [ ] Zero | One real national instance is in play. |

Two of those rows deserve to be read together. **Fleet operations do not exist**, and
**code coverage across the fleet is unknown**. The second is a consequence of the first,
and it is why the first slice proposed below is a report rather than a mapping: the
toolkit does not yet know whether the instances agree, and every tier-1 design choice
past this point depends on the answer.

## 6. Slice one: a cross-instance terminology report

The smallest thing that is genuinely useful, genuinely buildable on what exists, and
that produces the measurement every later stage needs.

**What it is.** One command, N profiles, one report. For every option set the fleet
holds, it states which instances carry it, how it was matched, and whether the instances
agree about its contents. It writes nothing to any instance, emits no ConceptMap, and
picks no winner. It is a fact sheet.

```
d2w fhir compare terminology -p lao -p tanzania -p play-2-42
```

The verb is provisional; the noun is [decision H8](#7-decisions-reserved-for-the-owner).

**The matching key is the whole design.** Three candidates, and the report uses all
three with different standing:

- **Code, as the primary key.** The only honest cross-instance key. It exists exactly
  where someone maintained it, which is why code coverage is the measurement this report
  also delivers, and why
  [decision 3.8](fhir-roadmap.md#38-namingsource-and-concept_code_source-default-to-id)'s
  id-first-then-code workflow is the same workflow at fleet scale.
- **UID, as a lineage key, reported separately.** Two instances sharing a UID for an
  option set share a metadata package lineage. That is strong evidence and a
  fundamentally different claim from a code match, so it is a separate column rather
  than a fallback that silently blends into the first.
- **Name, as advisory only, never as identity.** DHIS2 names have no rules, are
  unstable, and are localized - which is precisely why `naming.source` offers no name
  mode at all. A name match is surfaced as "possible, unconfirmed" for a human to accept
  or reject, and never counted as a match.

**What it states per matched set.** One row per vocabulary, one verdict:

| Verdict | Meaning |
| --- | --- |
| `identical` | Same code set, same displays, in every instance holding it |
| `superset` / `subset` | One instance's option list contains another's exactly |
| `divergent` | Codes overlap, membership does not |
| `conflicting` | The same code carries a different meaning in two instances - the finding that matters most, and the one a name-keyed comparison would hide |
| `single` | Present in one instance only |

Plus the per-instance code-coverage figure, so the report doubles as the fleet-wide
readiness measurement that section 5 says nobody has taken.

**Why terminology, and why option sets first.** An option set is the smallest closed
vocabulary DHIS2 has; the ConceptMap machinery is already built around it; its
disagreements are the cheapest kind to state precisely. Organisation units are a
hierarchy, not a vocabulary, and two countries' hierarchies are *supposed* to differ.
Forms are the largest surface and the least likely to agree. Indicators are tier 3.

**What it costs.** One `/api/optionSets` read per profile, with the same field selector
`generate option-sets` already uses, over the same client. No writes, no compile, no
publisher. The report is a typed model rendered as markdown and CSV with a `--json`
dump, the shape `d2w fhir validate` already established.

**What it deliberately defers.** No ConceptMap is emitted. No instance is written to.
Categories, data elements, organisation units, forms, and indicators are all out. No
reference vocabulary is assumed, which is what lets this run before decision H1 is made -
and its output is a substantial part of what that decision should be made on.

**What comes after it, sketched only.** Slice two emits a cross-instance ConceptMap for
the sets a human confirmed, in whichever topology H2 picks. Slice three promotes the
`foundation` layer into a published master package, and only once two country guides
exist to extract it from. Neither is designed here, because slice one's output is what
should design them.

## 7. Decisions reserved for the owner

Same shape as [roadmap section 5](fhir-roadmap.md#5-open-decisions): the question, the
options, what depends on it. None of these are a reviewer's to settle.

**H1. Is there a reference vocabulary, and which one?** SNOMED CT, LOINC, ICD-11, the
WHO SMART Guidelines terminology, or a project-defined reference set assembled from the
fleet's own vocabularies. Licensing is part of the call and is not uniform - SNOMED
affiliate licensing is per country, which makes "map everything to SNOMED" a legal
question in every country before it is a technical one. *Depends on it:* whether tier 1
is a star or has no centre at all.

**H2. Star or mesh.** Every country to a reference vocabulary, or country to country.
*Depends on it:* the number of maps, whether the eleventh country is cheap or expensive,
and whether transitivity is ever claimed. Recommendation recorded, not decided: mesh for
a specific pair with a specific reason, star for anything called a fleet.

**H3. Where a cross-instance map lives.** Inside each country project, in a separate
harmonization project of its own, or in the master guide package. *Depends on it:*
who regenerates it, whose canonical it carries, and whether a country guide's build
breaks when a mapping changes.

**H4. The identifier-namespace question.** Does `http://dhis2.org/fhir/id/option` stay a
single shared namespace across countries - which asserts that DHIS2 UIDs are globally
unique, an assertion the toolkit does not currently make in writing - or does each
country set its own `identifier_system_base` so its identifiers are unambiguous by
construction? The dial exists; the default is shared. *Depends on it:* whether any
cross-instance join on identifiers is sound, and whether two instances sharing a
metadata lineage are read as agreeing or as colliding.

**H5. Is the master guide a published package or a documented convention?** A real IG
package with a canonical, a version, and a `dependsOn` from each country guide; or a
written convention that country guides follow without a machine-checkable link.
*Depends on it:* whether "derives from the master guide" is a claim a validator can
check, and whether the scaffolded `sushi-config.yaml` grows a `dependencies:` block.

**H6. What a fleet is, concretely.** Repeated `-p` flags, a `fleet.toml` listing
profiles, or a group defined inside `profiles.toml` itself. And where that file lives -
beside the profiles, or beside a harmonization project. *Depends on it:* every
fleet-shaped command's argument surface, starting with slice one.

**H7. May harmonization write to DHIS2 instances?** Seeding a `SNOMED_CODE` attribute
value onto options is the cheapest route to tier 1 data and it is a write to a
production national instance. Options: read-only forever, with seeding done by the
country team through the existing `d2w metadata option-sets attributes set`; or a
harmonization write path with its own dry-run discipline. *Depends on it:* the risk
profile of the entire tier-1 line. Note the standing precedent - `d2w fhir doctor` never
writes, and `d2w fhir forward` makes a dry run the default.

**H8. The vocabulary.** `harmonize`, `fleet`, `compare`, or something else, as the noun
this whole line of work is spelled with in the CLI and the docs. Per the working
convention that vocabulary decisions are the owner's - the same convention behind
[decision 5.8](fhir-roadmap.md#58-fhir-build-versus-the-scaffolded-projects-make-build).

## 8. Non-goals

Stated hard, because each one is something that gets proposed the moment the word
"harmonization" is used in a room.

- **No mCSD, and no OpenHIE-derived facade.**
  [Decision 3.4](fhir-roadmap.md#34-ihe-mcsd-is-rejected-outright) rejects mCSD outright
  and a multi-country registry is precisely the setting where it gets proposed again.
  The answer does not change with the number of countries. The registry stays plain R4
  `Organization` + `Location`.
- **No master guide before two real country guides exist.** A shared layer extracted
  from a single instance is that instance's guide with a grander name, and every wrong
  guess in it is load-bearing before anyone can catch it.
- **No merged instance, ever.** Harmonization never proposes writing one country's
  metadata into another's instance. `d2w metadata merge` exists, does exactly that on
  purpose for staging-to-production promotion within one organisation, and is
  deliberately not part of this line of work.
- **No inferred agreement.** A report states a conflict and stops. No tool in this line
  resolves a disagreement between two instances, picks a winner, or promotes a name
  match to a real match without a human accepting it.
- **No global canonical DHIS2 instance.** Nothing here builds, implies, or requires a
  central instance the countries are projections of.
- **No analytics harmonizer before tier 1.** Cross-country indicator numbers computed
  over unaligned vocabularies are more dangerous than no numbers, because they are
  usable.
- **No new mapping language.** Whatever the cross-instance mapping turns out to be, it
  is `ConceptMap` plus whatever
  [the conversion layer](fhir-conversion.md) settles on for the structural half. This
  page adds no third carrier.
- **No IHE profile adoption of any kind**, on the same reasoning as the first item.

## 9. The staged plan in one table

| Stage | What ships | Gate that opens it | What it unlocks |
| --- | --- | --- | --- |
| 0 | Nothing. This document. | - | A shared vocabulary for the question |
| 1 | The cross-instance terminology report | H6 and H8 answered; two or more country profiles resolvable | The fleet-wide code-coverage measurement, and the evidence H1 and H2 should be decided on |
| 2 | Concept-level attribute values reaching the emitted CodeSystem | Roadmap 9.2 carrier chosen and measured | A seeded external code becomes visible in the published guide |
| 3 | Cross-instance ConceptMaps for confirmed matches | H1, H2, H3 answered; slice one's report says the matches exist | Tier 1 delivered |
| 4 | The master guide package | Two published country guides; H4 and H5 answered | Tier 2 delivered |
| 5 | Comparable indicators | Tier 1, tier 2, the data-serving leg, and a real inter-country agreement | Tier 3 delivered |

Stages 1 and 2 are independent of each other and of every decision except the ones named
in their own row. Everything from stage 3 on is gated on owner calls that have not been
made.

## See also

- [FHIR roadmap and review guide](fhir-roadmap.md) - what exists, the settled
  decisions, and the open ones this page adds to rather than reopens.
- [The FHIR conversion layer](fhir-conversion.md) - the structural half of the
  contract question, and where the ConceptMap mechanism this page builds on is
  specified.
- [Terminology and ConceptMaps](../guides/fhir/401-terminology-and-conceptmaps.md) -
  the maps and concept properties as they ship today.
- [How things are generated](../guides/fhir/301-generation.md#naming) - the identity
  stem, the naming tokens, and `identifier_system_base`.
- [Check an instance with doctor](../guides/fhir/201-doctor.md) - the per-instance
  verdict a fleet report would be assembled from.

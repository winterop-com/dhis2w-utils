# What goes in: the selection tables

**Who this is for:** the person editing `fhir.toml`.

**Before you start:** read [The settings file](301-fhir-toml.md) - what
`fhir.toml` is, where it lives, and how to edit it without breaking it. Have
the UIDs of the objects you want to add or remove at hand (the Maintenance
app shows them).

**You will be able to:**

- add or remove a data set, event program, tracker program, or person-only
  registration form from the guide
- narrow which option sets and categories become code lists
- say what each tracked entity type is published as, scope the
  organisation-unit registry, and choose how example responses are made
- tell a misspelled UID from a missing object after a run

This page covers the options that decide which of your DHIS2 metadata the
guide covers: the six selection tables (option sets, categories, data sets,
event programs, tracker programs, tracked entity forms), the organisation unit
scope, what tracked entity types are, and the example responses. These are the
options an M&E officer changes most often - adding a data set to the guide is
one line here.

Three rules apply to every selection table:

1. **Selections are by UID, never by name** - names are not unique in DHIS2.
   A UID is the eleven-character id like `BfMAe6Itzgt`; the quickest way to
   find one is the Maintenance app, where it is shown on the object's details
   pane (it is also the last part of the address bar when the object is open).
2. **An absent table, or an empty list, means "all of them".** You write a
   list to narrow the guide, not to switch it on.
3. **A UID that matches nothing does not stop the run - it is written down.**
   The guide is generated without that object, and the run records a note
   naming the UID and the table it was written in. So a misspelled UID and an
   object somebody deleted from DHIS2 look identical in the guide, and are told
   apart by reading the note and checking the id against the Maintenance app.

### Where the run tells you what it left out { #reading-the-notes }

The notes are the whole feedback channel for the options on this page: nothing
here can be checked against your instance while you edit the file, so
everything is reported after the run instead.

`d2w fhir generate` ends with a line saying how many notes it raised and where
they are:

```text
note: 3 note(s) across 2 target(s); full list in /home/you/hmis-ig/reports/fhir-generate-notes.md (--details to print)
```

`reports/fhir-generate-notes.md` is an ordinary text file grouped by what was
being generated, one line per note. An unmatched selection reads:

```text
- 1 [generate.data_sets] include_ids entries matched no data set: BfMAe6Itzgu
```

`d2w fhir generate --details` prints every note in the terminal instead of
writing the file, which is easier when you are fixing one line at a time. The
`reports/` folder is regenerated on every run and is not part of the published
guide.

### `[generate.data_sets]` include_ids { #data-sets }

**In plain words.** Which aggregate data sets become forms in the guide. Each
selected data set is published as one fill-in form with the same sections,
data elements, and disaggregations as its DHIS2 entry screen. A data set may
restate the disaggregation of an element it carries, and that restatement is
what the form asks: the cells come from the data set's own category combo for
that element when it states one, and from the data element's own when it does
not - the same rule the DHIS2 entry screen follows.

**When you would change it.** The most common edit in the file: the guide
should cover the HIV monthly summary, so you add its UID. Or a national
instance has 40 data sets and the guide is about 3 - list the 3.

**Example.**

```toml
[generate.data_sets]
include_ids = ["BfMAe6Itzgt", "Nyh6laLdBEJ"]
```

The guide publishes exactly two data-set forms.

**Default:** absent - **If you leave it out:** every data set on the instance
becomes a form.

**If you get it wrong:** a UID matching nothing selects nothing and is named in
the run's notes ([reading the notes](#reading-the-notes)). Writing a single UID
without list brackets stops the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.data_sets.include_ids
  Input should be a valid list [type=list_type, input_value='BfMAe6Itzgt', input_type=str]
```

### `[generate.event_programs]` include_ids { #event-programs }

**In plain words.** Which event programs - programs *without* registration,
where each record stands alone - become forms. One program, one form.

**When you would change it.** Same reasons as data sets: naming the event
programs this guide is actually about.

**Example.**

```toml
[generate.event_programs]
include_ids = ["VBqh0ynB2wv"]
```

That program's stage becomes one form in the guide.

**Default:** absent - **If you leave it out:** every event program on the
instance becomes a form.

**If you get it wrong:** a non-list value refuses the run exactly as under
[data sets](#data-sets). A *tracker* program's UID listed here is refused by
name - the run stops with an error shaped like:

```text
error: program 'Child Programme' (IpHINAT79UW) has programType WITH_REGISTRATION; a tracker program is selected under [generate.tracker_programs], which emits one Questionnaire per stage
```

### `[generate.tracker_programs]` include_ids { #tracker-programs }

**In plain words.** Which tracker programs - programs *with* registration,
following a person (or other tracked entity) over time - the guide covers.
Each selected program contributes its registration form plus one form per
program stage.

**When you would change it.** When the guide should cover a tracker program -
an immunisation registry, a TB treatment programme - you add its UID here,
not under event programs. DHIS2's program type decides which table a program
belongs in.

**Example.**

```toml
[generate.tracker_programs]
include_ids = ["IpHINAT79UW"]
```

The guide gets that program's registration form and one form for each of its
stages.

**Default:** absent - **If you leave it out:** every tracker program on the
instance is covered.

**If you get it wrong:** a non-list value refuses the run as under
[data sets](#data-sets); an event program's UID listed here is refused by
name, mirroring the refusal shown under
[event programs](#event-programs).

### `[generate.tracked_entity_forms]` include_ids { #tracked-entity-forms }

**In plain words.** Which tracked entity types publish a **person-only
registration form** - a form that creates a person and enrols them in nothing.
DHIS2 accepts that on its own, and the person it creates can be enrolled in a
programme later, so a project that registers people before deciding what to
enrol them in has a form for exactly that.

The form asks the attributes the *type itself* collects, which is the set DHIS2
imports onto the tracked entity rather than onto an enrollment.

**When you would change it.** When the guide should publish a person-only form
for a type no selected tracker programme registers, or should publish it for
only some of the types they do.

**Example.**

```toml
[generate.tracked_entity_forms]
include_ids = ["nEenWmSyUEp"]
```

**Default:** absent - **If you leave it out:** one form per tracked entity type
that a selected tracker programme registers. This is the one selection table
whose empty default is not the whole instance: a project that selects no tracker
programme and names no type here publishes no person-only form at all, and costs
no request for one.

**If you get it wrong:** a UID that matches no tracked entity type is reported
by name in [the run's notes](#reading-the-notes) and skipped, the way an
unmatched data set UID is.

### `[generate.option_sets]` include_ids { #option-sets }

**In plain words.** Which option sets are published as code lists. You rarely
need to touch this: every option set that any selected form uses is pulled in
automatically, so this table is for publishing code lists *beyond* what the
forms require.

**When you would change it.** You want the guide to double as a code-list
reference for sets no selected form happens to use - list them here. Or you
are building a terminology-only guide with no forms at all.

**Example.**

```toml
[generate.option_sets]
include_ids = ["Qdm5fPK5Ra9"]
```

That option set's code list is published even if no selected form uses it.

**Default:** absent - **If you leave it out:** every option set on the
instance is published (and with forms selected, everything they use is always
included regardless).

**If you get it wrong:** same behaviour as every selection table: an unknown
UID selects nothing and is named in the run's notes as
`include_ids entry '...' matched no option set`; a non-list value refuses the
run as under [data sets](#data-sets).

### `[generate.categories]` include_ids { #categories }

**In plain words.** Which DHIS2 categories (the axes your data is
disaggregated by - Sex, Age group) are published as code lists of their
category options.

**When you would change it.** When the guide should publish a specific few of
the instance's categories as reference code lists rather than all of them.

**Example.**

```toml
[generate.categories]
include_ids = ["O5P6e8yu1T6"]
```

Only that category's code list is published.

**Default:** absent - **If you leave it out:** every category on the instance
is published - except DHIS2's built-in `default` category, which the next
option controls.

**If you get it wrong:** same behaviour as every selection table: an unknown
UID selects nothing and is named in the run's notes as
`include_ids entry '...' matched no category`.

### `[generate.categories]` include_default { #include_default }

**In plain words.** Every DHIS2 instance has a built-in category literally
named `default` - the placeholder meaning "no disaggregation". It says nothing
a reader can use, so the guide skips it even when "all categories" are
selected. This switch opts it back in.

**When you would change it.** Only when a system consuming your guide insists
on seeing the placeholder spelled out. If you do not know whether you need it,
you do not need it.

**Example.**

```toml
[generate.categories]
include_default = true
```

The `default` category's code list is published alongside the real ones.
(Listing its UID in `include_ids` has the same effect - an explicit ask wins.)

**Default:** `false` - **If you leave it out:** the `default` placeholder is
skipped, and every real category is unaffected.

**If you get it wrong:** TOML wants bare `true` or `false` (no quotes);
anything unrecognisable stops the run with a printout naming
`generate.categories.include_default`.

### `[generate.tracked_entity_types]` { #tracked_entity_types }

**In plain words.** A DHIS2 tracker program follows a tracked entity type -
usually a person, but projects track households, buildings, herds, equipment.
This table says what each type *is*, so the generated forms describe their
subject correctly. Any type you do not mention is treated as a person.

**When you would change it.** Only when a tracker program in your guide tracks
something other than people: a livestock vaccination programme, a water-point
maintenance programme. Then you map that tracked entity type's UID to the word
for what it is. There are nine to choose from, and the choice is a
plain-language one:

| Write this | When the type is | Example on a DHIS2 instance |
| --- | --- | --- |
| `Patient` | a person receiving care - the default | Person, Malaria case |
| `Person` | a person the guide holds no care record for | Contact, Household head |
| `Practitioner` | a person doing the work rather than receiving it | Community health worker |
| `RelatedPerson` | a person tracked because of their relation to another | Guardian, Treatment supporter |
| `Group` | several individuals tracked as one record | Household, Herd, Class |
| `Device` | a piece of equipment | Cold-chain fridge, Bed net batch |
| `Location` | a place | Water point, Latrine, Well |
| `Organization` | an organisation | Clinic under inspection, School |
| `Specimen` | a sample taken from somebody or something | Blood sample, Sputum sample |

If two look plausible, pick the one a reader of the published guide would
recognise; nothing else in the guide changes with the choice.

**Example.**

```toml
[generate.tracked_entity_types]
"Kd6Nk9wnAJa" = "Group"      # a livestock herd
"Bx8L1nQ4EiP" = "Location"   # a water point
```

Every form of every program tracking those types now says its subject is a
group or a place, not a person.

**Only the exceptions go here, and only UIDs.** What a type is *called* is the
instance's to say, so no name is ever written into this table - the generated
guide reads the names off DHIS2 and publishes them as the `D2TET_CS` vocabulary,
with a `D2TET_CM` row per type naming the resource its registrations are published
as. A consumer of the guide therefore resolves a type without holding this file
(see [Terminology and ConceptMaps](401-terminology-and-conceptmaps.md#the-resource-each-type-is-published-as)),
and renaming a type in DHIS2 changes the guide on the next run with nothing to edit
here.

**Default:** absent - **If you leave it out:** every tracked entity type is
treated as a person, which is right for the typical health project - a
person-tracking project leaves this table out entirely. A run whose forms register
two or more types that this table never names says so as a generate note, naming
each one - two kinds of thing published as one resource is usually a table someone
meant to fill in.

**If you get it wrong:** a kind outside the list refuses the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.tracked_entity_types
  Value error, tracked entity type Kd6Nk9wnAJa is mapped to 'Car', which is not a FHIR resource type a tracked entity is published as: name one of Patient, Person, Practitioner, RelatedPerson, Group, Device, Location, Organization, Specimen [type=value_error, ...]
```

## The `[generate.organisation_units]` table { #organisation-units }

The guide publishes a facility registry: every organisation unit in scope
becomes two entries (the organisation, and the place with its map shape).
These three options set the scope - and because organisation units are usually
the biggest thing in a national instance, they are also the guide's size dial.

### `root`

**In plain words.** The organisation unit to start from. The guide covers this
unit and everything below it, instead of the whole tree.

**When you would change it.** A district-level project on a national instance:
set `root` to the district and the guide covers only that branch.

**Example.**

```toml
[generate.organisation_units]
root = "ImspTQPwCqd"
```

Only that unit and its descendants are published.

**Default:** unset - **If you leave it out:** the entire organisation unit tree
is in scope. Note the quiet twin: `root = ""` also means the entire tree - it
is treated as unset, with no message (see
[the settings file](301-fhir-toml.md#two-values-that-quietly-mean-not-set)).

**If you get it wrong:** a UID matching no organisation unit selects nothing,
and unlike the selection tables above it raises no note: the run succeeds and
the registry comes out empty. The registry run prints how many organisation
units it wrote - check that number after setting this.

### `max_level`

!!! warning "Read before you decide - this is the cost lever"
    Organisation unit hierarchies fan out at the bottom: the deepest level (the
    facilities) is usually *most* of the tree, and every unit in scope becomes
    two published entries plus its map shape. On a national instance,
    `max_level` is the difference between a guide that generates and builds in
    minutes and one that takes the better part of an hour or fails the build's
    time limits. Start capped (the project may already have been created with
    `--max-level` for exactly this reason), confirm the build is comfortable,
    then deepen deliberately.

**In plain words.** The deepest hierarchy level to include: `max_level = 3` on
a country / province / district / facility tree publishes down to districts
and leaves the thousands of facilities out.

**When you would change it.** In both directions: raise it (or remove it) when
the guide is genuinely about facilities; lower it when builds are slow and the
guide's consumers only need administrative areas.

**Example.**

```toml
[generate.organisation_units]
max_level = 3
```

Levels 1-3 are published; everything deeper stays out.

**Default:** unset - **If you leave it out:** every level down to the deepest
facility is published. Note the quiet twin: `max_level = 0` also means "no
limit" - it is treated as unset, with no message.

**If you get it wrong:** nothing refuses a wrong number. Too small (or
negative) and the registry comes out nearly or completely empty; too large
simply means "everything". You find out from the run's counts and the build
time.

### `terminology`

**In plain words.** Besides the registry entries, also publish the organisation
units as a code list - one entry per unit, with its level, parent, and DHIS2
code - so systems that work with code lists can validate "is this a real
facility code?" against it.

**When you would change it.** When a consuming system asks for the facility
list *as a code list* rather than as registry entries. Otherwise leave it off;
it roughly repeats the registry in a second form.

**Example.**

```toml
[generate.organisation_units]
terminology = true
```

The guide additionally publishes the organisation unit code list (`D2OU_CS` and
its companion).

**Default:** `false` - **If you leave it out:** no organisation unit code list;
the registry entries are unaffected.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming
`generate.organisation_units.terminology`.

## The `[generate.examples]` table { #examples }

Every form in the guide can ship with example filled-in responses, so a reader
sees real-shaped data, not just an empty form.

### `per_target`

**In plain words.** How many example responses each form gets: `0` switches
examples off, `10` is the ceiling - past a handful they stop illustrating.

**When you would change it.** `0` when examples add noise to a terminology-
focused guide; `2`-`3` when one example does not show a form's variety (say,
different disaggregations).

**Example.**

```toml
[generate.examples]
per_target = 3
```

Every form ships with three example responses.

**Default:** `1` - **If you leave it out:** one example per form.

**If you get it wrong:** outside 0-10 refuses the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.examples.per_target
  Input should be less than or equal to 10 [type=less_than_equal, input_value=11, input_type=int]
```

### `source` { #examples-source }

**In plain words.** Where example values come from. `"synthetic"` invents
plausible values locally - nothing is read from your server's data, so
nothing real can leak into a published guide. `"instance"` copies real
recorded values from the server into the examples.

**When you would change it.** `"instance"` only against a demo or training
server, where realistic-looking examples help and the data is not real. The
guide is a *published document*: with `"instance"` against a production
server, real reported values travel into it - review every example before
publishing if you ever do this.

**Example.**

```toml
[generate.examples]
source = "instance"
```

Example responses carry values actually recorded on the connected server.

**Default:** `"synthetic"` - **If you leave it out:** examples are invented
and safe everywhere.

**If you get it wrong:** any other word refuses the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.examples.source
  Input should be 'synthetic' or 'instance' [type=literal_error, input_value='real', input_type=str]
```

Next: [How things are generated](301-generation.md) - identifiers, codes,
time zone, languages, and naming.

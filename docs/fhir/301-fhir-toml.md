# The settings file: fhir.toml

**Who this is for:** the person who looks after what the FHIR guide contains -
an M&E officer, a data manager - and edits it through one text file. You do not
need to program. You need a text editor, the project folder someone set up for
you, and the command written down for you (`d2w fhir generate`).

**Before you start:** know your DHIS2 - data sets, programs, organisation
units, option sets. FHIR terms are explained where they appear, or glossed in
[FHIR for DHIS2 people](101-fhir-concepts.md).

**You will be able to:**

- say what `fhir.toml` is, where it lives, and how commands find it
- edit it without breaking it, and read the error when you do
- find the right page for any option you want to change

## What the file is

`fhir.toml` is the one settings file of a FHIR guide project. Everything the
project publishes - which data sets become forms, which option sets become code
lists, how far down the organisation unit tree it reaches, what everything is
named, how the local server runs - is decided by this file. It is plain text:
you edit it with any text editor (Notepad, TextEdit, VS Code), save it, and run
the generate command again. There is no database, no hidden state, and no app
to click through - the file is the whole configuration.

It sits at the top of the project folder, next to the `Makefile`. Commands find
it on their own: run `d2w fhir generate` anywhere inside
the project folder and it walks up until it finds `fhir.toml`. Run it somewhere
with no project above it and it stops with:

```text
no fhir.toml found in this directory or any parent. Run `d2w fhir init [DIRECTORY]` to scaffold a FHIR IG project first.
```

That error means "you are in the wrong folder", not "something is broken".

## fhir.toml and fhir.toml.example

The project folder holds two files with nearly the same name, and the split is
deliberate:

- **`fhir.toml`** is yours. It holds only what your project actually decides -
  the guide's identity, and whatever options you have set. Short is good: an
  option that is not in the file keeps its default.
- **`fhir.toml.example`** is the catalog. It lists every option the commands
  understand, each with its default value and a one-line comment pointing at
  the section of these pages that explains it. It is never read by any command -
  it exists so you can find an option, copy its line into `fhir.toml`, and
  change the value there.

Copying from the example is the recommended way to edit: it gives you correct
spelling and correct punctuation for free, which matters more than it sounds
(see the next section). The example file is refreshed when the project's
tooling is updated, so it always matches what your installed version actually
understands.

## Editing safely

The file format is called TOML. You need four rules:

1. **Text values wear double quotes**: `status = "draft"`. Numbers and the
   words `true` / `false` do not: `max_level = 4`, `ui = false`.
2. **Lines in `[square brackets]` are section headers**: `[generate.naming]`
   starts the naming section, and every `key = value` line below it belongs to
   that section until the next header. Do not delete a header whose lines you
   are keeping.
3. **Lists sit in square brackets with commas**:
   `include_ids = ["BfMAe6Itzgt", "Nyh6laLdBEJ"]`.
4. **A line starting with `#` is a comment** - it is ignored. Putting `#` in
   front of a line is how the example file shows an option without setting it,
   and removing the `#` is how you switch it on.

Four things to know about getting it wrong:

**A misspelled option name is refused, and the right name is suggested.** Write
`max_lvl = 4` and the next command stops with:

```text
error: fhir.toml: unknown key 'max_lvl' in [generate.organisation_units]
  did you mean 'max_level'?
```

The refusal names three things: the key you wrote, the section it sits in, and -
when one of that section's real options is close enough to be worth naming - the
spelling you probably meant. A name that resembles nothing in its section is
reported without a suggestion, because a wrong guess is worse than none:

```text
error: fhir.toml: unknown key 'listen_on_every_interface' in [serve]
```

Every misspelling in the file is reported in one run, so you fix them in one
edit rather than one command per typo. There is no such thing as an option that
quietly does nothing: if `fhir.toml` loads, every line in it is a setting the
commands understand. Copying option lines from `fhir.toml.example` is still the
easiest way to get the spelling right first time.

**A wrong value is refused before anything is written.** Misspell a *value* -
`status = "published"`, a time zone with a typo, a name piece starting with a
digit - and the very next `d2w fhir generate` or `d2w fhir validate` stops
before touching a single file. Nothing is half-generated: fix the line and run
again.

**Errors come in two shapes.** Some are friendly lines starting with `error:` -
one per thing that is wrong, sometimes with an indented suggestion or a hint
under them, as the misspelled name above. Others are a long technical printout
(a "traceback") - scroll to its last lines, which always name the setting and
say what was expected:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
ig.status
  Input should be 'draft' or 'active' [type=literal_error, input_value='published', input_type=str]
```

Read that as: the `status` option in the `[ig]` section holds `"published"`,
and the only accepted values are `"draft"` and `"active"`. Every option page in
this series shows the exact text its mistakes produce, so you can match what
you see to what to fix.

**A broken file stops everything.** Delete a closing quote and every command
refuses with a printout ending in a line like
`tomllib.TOMLDecodeError: Illegal character '\n' (at line 10, column 19)` -
line 10 is where to look. Because `fhir.toml` is a committed file in the
project's version control, someone can always restore the last working copy.

## Two values that quietly mean "not set"

Two organisation unit options treat a particular value as "unset" rather than
as a value:

- `root = ""` (empty text) means the same as leaving `root` out entirely: the
  whole organisation unit tree.
- `max_level = 0` means the same as leaving `max_level` out entirely: no depth
  limit.

Neither produces an error or a message. If you meant to limit the guide and it
came out covering everything, check whether one of these two slipped in.
Details on both: [what goes in](301-what-goes-in.md#organisation-units).

## Read these three before you decide

Most options are safe to try, look at, and change back. Three are not like the
others - each has a warning box on its own page, and each is worth reading
*before* the first real publish, not after:

1. **[`naming.source`](301-generation.md#source)** - whether generated names
   build on DHIS2 ids or DHIS2 codes. Changing it later renames every page and
   every web address the guide has ever published, and there is no way to
   change it without that happening.
2. **[`organisation_units.max_level`](301-what-goes-in.md#max_level)** - the
   single biggest lever over how large the guide is and how long it takes to
   build. A national facility list at full depth is most of the build time.
3. **[`serve.host`](301-serving.md#host)** and
   **[`serve.auth`](301-serving.md#auth)** - who can reach the capture server,
   and who it answers. The first is the switch between "visible only on this
   computer" and "everyone on the network can reach it"; the second is whether
   any of them is asked who they are, and under its default nobody is - which is
   why binding anything but loopback with `auth` unwritten is refused at startup.
   On a server started in live mode, what sits behind it includes the people the
   DHIS2 instance holds - how much of that it offers is
   [`[serve.tracked_entities]`](301-serving.md#tracked_entities).

## Where the run tells you what it did

Most of what you write in this file is a UID or a name that only your DHIS2
server can confirm, and nothing in the file can be checked against the server
while you edit it. So the checking happens after a run instead:
`d2w fhir generate` ends with a line saying how many notes it raised and where
they are, and writes them to `reports/fhir-generate-notes.md` in the project
folder. That file is where a selection that matched nothing, a code the run had
to fall back from, or a tracked entity type nobody said anything about is named.
Read it after any edit to this file:
[reading the notes](301-what-goes-in.md#reading-the-notes).

## Where every option is explained

Each option gets the same treatment on its page: what it controls in plain
words, a concrete situation where you would change it, an example, what
happens when you leave it out, and the exact error you see when you get it
wrong.

Four pages cover the file between them:

| Page | Sections covered |
| --- | --- |
| [Who the guide is](301-identity.md) | `profile`, `[ig]` - which DHIS2 server it reads, and the guide's own identity |
| [What goes in](301-what-goes-in.md) | the six selection tables, `[generate.tracked_entity_types]`, `[generate.organisation_units]`, `[generate.examples]`, `[ips.identity]` - which of your DHIS2 metadata the guide covers, and which attribute carries which fact about a person |
| [How things are generated](301-generation.md) | `[generate]`, `[generate.naming]` - identifier addresses, code choices, time zone, languages, and everything about naming |
| [Serving it](301-serving.md) | `[serve]`, `[serve.tracked_entities]`, `[serve.search]`, `[serve.projection]`, `[[serve.basemaps]]`, `[forward]` - how the local capture server runs, what it answers about people, what answers a search for one, where the synced copy of the register lives, and how forwarding behaves |

### Every option, alphabetically within its section

Every line `fhir.toml` accepts is here. Anything not in this table is a name
the file refuses.

| Section | Option | Default | What it decides |
| --- | --- | --- | --- |
| (top level) | [`profile`](301-identity.md#profile) | unset | which saved DHIS2 connection the guide is read from |
| `[ig]` | [`canonical`](301-identity.md#canonical) | required | the guide's permanent web address |
| `[ig]` | [`id`](301-identity.md#id) | required | the guide's package identifier |
| `[ig]` | [`name`](301-identity.md#name) | required | the guide's computer-facing name |
| `[ig]` | [`publisher`](301-identity.md#publisher) | required | the organisation standing behind the guide |
| `[ig]` | [`status`](301-identity.md#status) | `"draft"` | draft-and-experimental, or official |
| `[ig]` | [`title`](301-identity.md#title) | required | the title readers see on every page |
| `[generate]` | [`concept_code_source`](301-generation.md#concept_code_source) | `"id"` | whether published codes are DHIS2 ids or DHIS2 codes |
| `[generate]` | [`hostile_names`](301-generation.md#hostile_names) | unset (the run asks) | whether a DHIS2 name carrying `<` refuses the run or is published in rewritten wording |
| `[generate]` | [`identifier_system_base`](301-generation.md#identifier_system_base) | `"http://dhis2.org/fhir"` | the web-address stem the DHIS2 identifier labels are built from |
| `[generate]` | [`locales`](301-generation.md#locales) | every language found | which languages the guide publishes translations in |
| `[generate]` | [`timezone`](301-generation.md#timezone) | unset (read as UTC) | the zone DHIS2's clock times are wall-clock readings in |
| `[generate.naming]` | [`attribute_option_combo`](301-generation.md#attribute_option_combo) | `"AOC"` | name piece for a data set's extra reporting dimension |
| `[generate.naming]` | [`category`](301-generation.md#category) | `"CAT"` | name piece for categories |
| `[generate.naming]` | [`data_set`](301-generation.md#data_set) | `"DS"` | name piece for data set forms |
| `[generate.naming]` | [`option_set`](301-generation.md#option_set) | `"OS"` | name piece for option sets |
| `[generate.naming]` | [`organisation_unit`](301-generation.md#organisation_unit) | `"OU"` | name piece for organisation units (never empty) |
| `[generate.naming]` | [`prefix`](301-generation.md#prefix) | `"D2"` | the piece in front of every generated name |
| `[generate.naming]` | [`program`](301-generation.md#program) | `"PR"` | name piece for program forms |
| `[generate.naming]` | [`program_stage`](301-generation.md#program_stage) | `"PS"` | name piece for tracker stage forms |
| `[generate.naming]` | [`source`](301-generation.md#source) | `"id"` | whether names are built on DHIS2 ids or DHIS2 codes |
| `[generate.naming]` | [`tracked_entity_type`](301-generation.md#tracked_entity_type) | `"TET"` | name piece for person-only registration forms |
| `[generate.data_sets]` | [`include_ids`](301-what-goes-in.md#data-sets) | all data sets | which data sets become forms |
| `[generate.event_programs]` | [`include_ids`](301-what-goes-in.md#event-programs) | all event programs | which event programs become forms |
| `[generate.tracker_programs]` | [`include_ids`](301-what-goes-in.md#tracker-programs) | all tracker programs | which tracker programs the guide covers |
| `[generate.tracked_entity_forms]` | [`include_ids`](301-what-goes-in.md#tracked-entity-forms) | the types the selected tracker programs register | which types publish a person-only registration form |
| `[generate.option_sets]` | [`include_ids`](301-what-goes-in.md#option-sets) | all option sets | which option sets become code lists |
| `[generate.categories]` | [`include_default`](301-what-goes-in.md#include_default) | `false` | whether DHIS2's built-in `default` category is published |
| `[generate.categories]` | [`include_ids`](301-what-goes-in.md#categories) | all categories | which categories become code lists |
| `[generate.tracked_entity_types]` | [UID = kind](301-what-goes-in.md#tracked_entity_types) | every type is a person | what each tracked entity type actually is |
| `[generate.organisation_units]` | [`max_level`](301-what-goes-in.md#max_level) | every level | the deepest hierarchy level published - the size lever |
| `[generate.organisation_units]` | [`root`](301-what-goes-in.md#root) | the whole tree | which branch of the hierarchy is published |
| `[generate.organisation_units]` | [`terminology`](301-what-goes-in.md#terminology) | `false` | whether the organisation units are also published as a code list |
| `[generate.examples]` | [`per_target`](301-what-goes-in.md#per_target) | `1` | how many example responses each form ships with |
| `[generate.examples]` | [`source`](301-what-goes-in.md#examples-source) | `"synthetic"` | whether example values are invented or copied off the server |
| `[serve]` | [`capture`](301-serving.md#capture) | `true` | whether the server accepts filled-in forms at all |
| `[serve]` | [`host`](301-serving.md#host) | `"127.0.0.1"` | who can reach the capture server - the exposure switch |
| `[serve]` | [`port`](301-serving.md#port) | `8080` | which port it listens on |
| `[serve]` | [`spool_dir`](301-serving.md#spool_dir) | `".serve/responses"` | which folder the received forms are kept in |
| `[serve]` | [`strict_codes`](301-serving.md#strict_codes) | `false` | whether an out-of-list code is refused or stored with a warning |
| `[serve]` | [`ui`](301-serving.md#ui) | `false` | whether the data-entry screens are served too |
| `[[serve.basemaps]]` | [`name`, `url`](301-serving.md#basemaps) | one OpenStreetMap layer | the map backgrounds the screens offer - the one outbound call |
| `[serve.tracked_entities]` | [`enabled`](301-serving.md#tracked_entities-enabled) | `true` | whether a live run answers questions about people at all |
| `[serve.tracked_entities]` | [`listing`](301-serving.md#tracked_entities-listing) | `true` | whether people can be paged through, not only searched for |
| `[serve.tracked_entities]` | [`page_size`](301-serving.md#tracked_entities-page_size) | `20` | how many people one page holds by default |
| `[serve.tracked_entities]` | [`page_size_limit`](301-serving.md#tracked_entities-page_size_limit) | `100` | the largest page anybody may ask for |
| `[serve.tracked_entities]` | [`search_attributes`](301-serving.md#tracked_entities-search_attributes) | the unique and searchable ones | which attributes a search keys on |
| `[serve.tracked_entities]` | [`tracked_entity_types`](301-serving.md#tracked_entities-tracked_entity_types) | the types the published forms register | which types the register covers |
| `[serve.search]` | [`backend`](301-serving.md#search-backend) | `"dhis2"` | what answers a search for a person - the instance, or the synced copy |
| `[serve.projection]` | [`store`](301-serving.md#projection-store) | `"none"` | whether this project holds a synced copy of the register at all |
| `[serve.projection]` | [`path`](301-serving.md#projection-path) | `".serve/projection.sqlite"` | which file that copy lives in |
| `[serve.projection]` | [`overlap_seconds`](301-serving.md#projection-overlap) | `300` | how far back an incremental sync re-reads, so no row falls off the edge |
| `[forward]` | [`import`](301-serving.md#import) | `false` | whether a plain forward writes to DHIS2 or only checks |
| `[forward]` | [`live`](301-serving.md#live) | `true` | what a drain reads when the project holds no compiled guide |
| `[forward]` | [`register_completeness`](301-serving.md#register_completeness) | `true` | whether a finished aggregate form also marks its data set complete |
| `[forward]` | [`overwrites`](301-serving.md#overwrites) | `"allow"` | whether a figure a previous submission already sent is sent again and named, or the form left in the queue |
| `[forward]` | [`corrections`](201-forward.md#where-a-runs-posture-comes-from) | `"off"` | whether this deployment accepts a submission that names the receipt it amends |
| `[forward]` | [`withdrawals`](201-forward.md#withdraw-what-you-forwarded) | `"off"` | whether `d2w fhir withdraw` may take back from DHIS2 what a forwarded receipt landed |
| `[ips.identity]` | [`name`](301-what-goes-in.md#ips-name) | unset | which tracked entity attribute holds a person's name |
| `[ips.identity]` | [`birth_date`](301-what-goes-in.md#ips-birth_date) | unset | which tracked entity attribute holds a person's birth date |
| `[ips.identity]` | [`sex`](301-what-goes-in.md#ips-sex) | unset | which tracked entity attribute holds a person's sex |
| `[ips.identity.administrative_gender]` | [value = gender](301-what-goes-in.md#ips-administrative_gender) | unset | what each value of that attribute means, in FHIR's four words |

What the generated output itself looks like from the inside - the identifier
families, the code-list structures - is the integrate-tier's territory:
[Identifiers and the D2 extensions](401-identifiers-and-extensions.md) and
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md).

Next: [Who the guide is: `profile` and `[ig]`](301-identity.md)

# The settings file: fhir.toml

**Who this is for:** the person who looks after what the FHIR guide contains -
an M&E officer, a data manager - and edits it through one text file. You do not
need to program. You need a text editor, the project folder someone set up for
you, and the command written down for you (usually `make generate`).

**Before you start:** know your DHIS2 - data sets, programs, org units, option
sets. FHIR terms are explained where they appear, or glossed in
[FHIR for DHIS2 people](101-fhir-concepts.md).

**You will be able to:**

- say what `fhir.toml` is, where it lives, and how commands find it
- edit it without breaking it, and read the error when you do
- find the right page for any option you want to change

## What the file is

`fhir.toml` is the one settings file of a FHIR guide project. Everything the
project publishes - which data sets become forms, which option sets become code
lists, how far down the org unit tree it reaches, what everything is named, how
the local server runs - is decided by this file. It is plain text: you edit it
with any text editor (Notepad, TextEdit, VS Code), save it, and run the
generate command again. There is no database, no hidden state, and no app to
click through - the file is the whole configuration.

It sits at the top of the project folder, next to the `Makefile`. Commands find
it on their own: run `d2w fhir generate` (or `make generate`) anywhere inside
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

Three things to know about getting it wrong:

**A misspelled option name is silently ignored.** If you write `max_lvl = 4`,
nothing complains - the line simply does nothing, and the option keeps its
default. This is the most treacherous mistake the file allows, because
everything appears to work. It is the reason to copy option lines from
`fhir.toml.example` rather than typing them from memory. If a setting seems to
have no effect, check its spelling against the example file first.

**A wrong value is refused before anything is written.** Misspell a *value* -
`status = "published"`, a time zone with a typo, a name piece starting with a
digit - and the very next `d2w fhir generate` or `d2w fhir validate` stops
before touching a single file. Nothing is half-generated: fix the line and run
again.

**Errors come in two shapes.** Some are a single friendly line starting with
`error:` and a hint. Others are a long technical printout (a "traceback") -
scroll to its last lines, which always name the setting and say what was
expected:

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

Two org-unit options treat a particular value as "unset" rather than as a
value:

- `root = ""` (empty text) means the same as leaving `root` out entirely: the
  whole org unit tree.
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
3. **[`serve.host`](301-serving.md#host)** - the switch between "the capture
   server is visible only on this computer" and "everyone on the network can
   reach it". The server has no login, so this line is its whole access
   control.

## Where every option is explained

Each option gets the same treatment on its page: what it controls in plain
words, a concrete situation where you would change it, an example, what
happens when you leave it out, and the exact error you see when you get it
wrong.

| Page | Sections covered | Options |
| --- | --- | --- |
| [Who the guide is](301-identity.md) | `profile`, `[ig]` | which DHIS2 server it reads, the guide's name, address, publisher, and life-cycle status |
| [How things are generated](301-generation.md) | `[generate]`, `[generate.naming]` | identifier addresses, code choices, time zone, languages, and everything about naming |
| [What goes in](301-what-goes-in.md) | the selection tables, `[generate.tracked_entity_types]`, `[generate.examples]`, `[generate.organisation_units]` | which data sets, programs, option sets, categories, and org units the guide covers, and the example responses |
| [Serving it](301-serving.md) | `[serve]` | how the local capture server runs: address, port, strictness, data-entry screens, map background |

What the generated output itself looks like from the inside - the identifier
families, the code-list structures - is the integrate-tier's territory:
[Identifiers and the D2 extensions](401-identifiers-and-extensions.md) and
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md).

Next: [Who the guide is: `profile` and `[ig]`](301-identity.md)

# How things are generated: `[generate]` and `[generate.naming]`

**Who this is for:** the person editing `fhir.toml`.

**Before you start:** read [The settings file](301-fhir-toml.md) - what
`fhir.toml` is, where it lives, and how to edit it without breaking it.
Naming choices are best made before the first real publish, so read this page
early.

**You will be able to:**

- put the guide's identifier labels under your own domain
- choose whether concepts are coded by DHIS2 id or DHIS2 code
- set the reporting time zone and the translation languages
- rename what every generated thing is called, and read the refusal when a
  name piece breaks the shared rule

This page covers the `[generate]` section - four options that shape what the
generated content says - and the `[generate.naming]` section, which decides
what every generated thing is called. Which DHIS2 objects get generated at all
is the next page, [what goes in](301-what-goes-in.md).

## The `[generate]` section

### `identifier_system_base`

**In plain words.** Everything the guide publishes carries its DHIS2 id (and
DHIS2 code, where one exists) as a labelled identifier, so a reader can always
trace an entry back to your DHIS2. The label on such an identifier is a web
address, and this option is the stem those addresses are built from - for
example `http://dhis2.org/fhir/id/organisation-unit` labels "this is a DHIS2
organisation unit id".

**When you would change it.** When the ministry wants those labels under its
own domain - `https://moh.gov.sl/dhis2` instead of the generic
`http://dhis2.org/fhir` - so that identifiers from *this* DHIS2 are labelled
distinctly from any other country's. Decide before the first real publish:
anyone matching records on the old labels stops matching when the labels
change.

**Example.**

```toml
[generate]
identifier_system_base = "https://moh.gov.sl/dhis2"
```

An org unit's DHIS2 id is now labelled
`https://moh.gov.sl/dhis2/id/organisation-unit`.

**Default:** `"http://dhis2.org/fhir"` - **If you leave it out:** every
identifier label starts with `http://dhis2.org/fhir`, which works fine and
simply is not yours.

**If you get it wrong:** a trailing slash is quietly removed. Beyond that
nothing refuses this - you find out when the published identifier labels look
wrong to the people consuming them.

What these labelled identifiers look like in the output is covered in
[Identifiers and the D2 extensions](401-identifiers-and-extensions.md).

### `concept_code_source`

**In plain words.** Every DHIS2 option and category option has two possible
identities: its DHIS2 id (`Qdm5fPK5Ra9` - stable, unique, meaningless to
people) and its DHIS2 code (`FEMALE` - readable, but only as good as your
instance's code hygiene). This option picks which of the two becomes the
*code* in the code lists the guide publishes; the other one always rides along
as a property, so no information is lost either way.

**When you would change it.** The people receiving your data already know your
DHIS2 codes - their systems are configured against `FEMALE` / `MALE`, not
against ids - so you set `"code"` to publish the familiar values. Stay on
`"id"` when codes on your instance are missing or inconsistent; run
`d2w fhir validate` first to see whether your codes are good enough.

**Example.**

```toml
[generate]
concept_code_source = "code"
```

An option coded `FEMALE` in DHIS2 is published with `FEMALE` as its code and
its DHIS2 id as a property. An option whose code is missing or not usable
falls back to its id, with a note in the run's report.

**Default:** `"id"` - **If you leave it out:** published codes are DHIS2 ids,
which always works on any instance. How the published code lists are put
together is covered in
[Terminology and ConceptMaps](401-terminology-and-conceptmaps.md).

**If you get it wrong:** any value except the two stops the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.concept_code_source
  Input should be 'id' or 'code' [type=literal_error, input_value='uid', input_type=str]
```

### `timezone`

**In plain words.** DHIS2 stores clock times without saying which time zone
they were recorded in. Naming your zone here tells the generator "these are
local wall-clock times in this zone", so a visit recorded at 09:00 is
published as 09:00 in your country's time - daylight saving handled - instead
of being read as 09:00 UTC.

**When you would change it.** Set it once for any project whose published
example responses or captured data carry times, using your country's zone from
the standard IANA list: `"Africa/Freetown"`, `"Asia/Vientiane"`,
`"Europe/Oslo"`.

**Example.**

```toml
[generate]
timezone = "Asia/Vientiane"
```

A DHIS2 timestamp of `2026-03-01 09:00` is published as
`2026-03-01T09:00+07:00`.

**Default:** unset - **If you leave it out:** times are published exactly as
DHIS2 stored them, read as UTC. For a country not on UTC that shifts every
published time by the zone difference.

**If you get it wrong:** a zone name the standard list does not hold stops the
run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.timezone
  Value error, unknown IANA time zone 'Asia/Vientane': name a zone from the tz database (e.g. 'Asia/Vientiane', 'Europe/Oslo', 'UTC') [type=value_error, ...]
```

### `locales`

**In plain words.** Which languages the guide publishes translations in. Your
DHIS2 metadata may carry names in several languages; this list picks which of
them travel into the guide.

**When you would change it.** Your instance holds translations in five
languages but the guide is for a two-language audience: list those two and the
rest stay home. Language tags are the short standard ones - `"lo"`, `"en"`,
`"pt-BR"` - and DHIS2-style tags like `"pt_BR"` are understood too.

**Example.**

```toml
[generate]
locales = ["lo", "en"]
```

Only the Lao and English translations of names are published.

**Default:** unset - **If you leave it out:** every translation found on the
instance is published.

**If you get it wrong:** nothing refuses an unknown tag - a language your
metadata does not carry simply contributes nothing, and you find out when the
expected translations are missing from the guide.

## The `[generate.naming]` section { #naming }

Everything the guide generates needs a name and a web address:
`D2OS_Qdm5fPK5Ra9_CS` is the code list of one option set,
`d2-os-Qdm5fPK5Ra9-cs` its address segment. These names are assembled from
three kinds of pieces, and this section configures two of them:

- a **prefix** on everything the generator makes (`D2` by default),
- a **kind piece** saying what sort of DHIS2 thing it came from (`OS` for
  option set, `OU` for organisation unit, `DS` for data set...),
- an **identity stem** naming the individual object - and whether that stem is
  the object's DHIS2 id or its DHIS2 code is the `source` option, the one
  decision on this page that deserves real caution.

### `source`

!!! warning "Read before you decide - changing this later re-identifies everything"
    `source` decides the identity stem inside every generated name, address,
    and file name. Change it after the guide has been shared and *every one of
    those changes at once*: every page gets a new web address, every link
    anyone saved breaks, and every system matching on the old identities stops
    matching. There is no partial version of this - it is a different guide
    with the same content. Decide before the first publish, and treat a later
    change as republishing from scratch.

**In plain words.** Whether generated names are built on DHIS2 ids
(`D2OS_Qdm5fPK5Ra9_CS`) or DHIS2 codes (`D2OS_BirthType_CS`). Ids always work
- every object has one, they never collide. Codes read beautifully but only
exist where someone maintained them.

**When you would change it.** Set `"code"` when your instance's codes are
complete and well kept and you want a guide people can read addresses off -
and you are willing to have the run refuse until every selected object's code
is up to standard. Set `"code-or-id"` to get code-based names where a good
code exists and id-based names elsewhere - the pragmatic middle while codes
are being cleaned up. Stay on `"id"` when in doubt.

**Example.**

```toml
[generate.naming]
source = "code-or-id"
```

An option set coded `BIRTH_TYPE` is published as `D2OS_BirthType_CS`; an
uncoded one keeps its id-based name, with a note listing every fall-back.

**Default:** `"id"` - **If you leave it out:** every name is built on DHIS2
ids. Safe on any instance.

**If you get it wrong:** a value outside the three stops the run:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
generate.naming.source
  Input should be 'id', 'code-or-id' or 'code' [type=literal_error, input_value='name', input_type=str]
```

Under `source = "code"`, a selected object whose code is missing, unusable, or
shared with another object refuses the run with a message shaped like:

```text
error: [generate.naming] source = "code" needs a usable, unique code on every selected option set; 3 cannot serve as identity stems: Birth type (Qdm5fPK5Ra9) has no code; ... Fix the codes in DHIS2, or use source = "code-or-id" while migrating; `d2w fhir validate` names every offender.
```

### The name pieces and their shared rule { #the-token-rule }

The remaining eight options are the name pieces themselves. One rule covers
all of them:

- a piece is **letters and digits only, starting with a letter** - `D2`,
  `Dhis2`, `MOH`, `OrgUnit`;
- a piece set to `""` (empty) is **dropped from names entirely** - except
  `organisation_unit`, which must stay non-empty;
- pieces are joined with underscores in display names (`D2` + `OS` +
  `_BirthType` + `_CS`) and with hyphens, lowercased, in web addresses
  (`d2-os-birth-type-cs`).

A piece that breaks the rule stops the run with one of:

```text
generate.naming.prefix
  Value error, token must be letter-leading alphanumeric (e.g. 'D2', 'Dhis2', 'OU') [type=value_error, input_value='2D', input_type=str]
```

```text
generate.naming.organisation_unit
  Value error, token must not be empty [type=value_error, input_value='', input_type=str]
```

Like `source`, these pieces are baked into every name and address: renaming a
piece after publishing renames everything it appears in. Decide early, then
leave them alone.

### `prefix`

**In plain words.** The piece in front of every generated name, marking
"generated from DHIS2 by this project". `D2` by default.

**When you would change it.** A ministry that wants its own stamp on the
guide's names - `prefix = "SL"` gives `SLOS_..._CS`, `sl-os-...`. Or `""` to
drop the stamp entirely for shorter names.

**Example.**

```toml
[generate.naming]
prefix = "SL"
```

Every generated name starts `SL...` instead of `D2...`.

**Default:** `"D2"` - **If you leave it out:** names carry the `D2` stamp.

**If you get it wrong:** the shared rule above refuses it before anything is
written.

### `option_set`

**In plain words.** The kind piece on names generated from option sets:
`D2OS_..._CS` is "the code list of an option set".

**When you would change it.** Preference for longer words
(`option_set = "OptionSet"`) or shorter names (`""` drops the piece). Almost
never worth changing.

**Example.**

```toml
[generate.naming]
option_set = "OptionSet"
```

Produces `D2OptionSet_..._CS` instead of `D2OS_..._CS`.

**Default:** `"OS"` - **If you leave it out:** option-set names carry `OS`.

**If you get it wrong:** the shared rule above refuses it.

### `category`

**In plain words.** The kind piece on names generated from DHIS2 categories -
the code lists a category's options are published as: `D2CAT_Sex_CS`.

**When you would change it.** Almost never; same preferences as `option_set`.

**Example.**

```toml
[generate.naming]
category = "Cat"
```

Produces `D2Cat_..._CS` instead of `D2CAT_..._CS`.

**Default:** `"CAT"` - **If you leave it out:** category names carry `CAT`.

**If you get it wrong:** the shared rule above refuses it.

### `attribute_option_combo`

**In plain words.** Some data sets report every value under an extra
dimension - by funding partner, by project. When a data set does, the guide
publishes the vocabulary of that extra dimension, and this is the kind piece
on its name: `D2AOC_..._VS`.

**When you would change it.** Almost never. If none of your data sets use such
a dimension, the piece never even appears in your guide.

**Example.**

```toml
[generate.naming]
attribute_option_combo = "Reporting"
```

Produces `D2Reporting_..._VS` instead of `D2AOC_..._VS`.

**Default:** `"AOC"` - **If you leave it out:** these names carry `AOC`.

**If you get it wrong:** the shared rule above refuses it.

### `organisation_unit`

**In plain words.** The kind piece on everything generated from organisation
units - the facility registry entries and, if switched on, the org-unit code
list: `D2OU_..._CS`.

**When you would change it.** Preference (`"OrgUnit"` reads better to some).
This is the one piece that cannot be `""`: org-unit names would collapse into
nothing distinguishable.

**Example.**

```toml
[generate.naming]
organisation_unit = "OrgUnit"
```

Produces `D2OrgUnit_..._CS`, and `d2-org-unit-...` in addresses.

**Default:** `"OU"` - **If you leave it out:** org-unit names carry `OU`.

**If you get it wrong:** emptying it stops the run with
`token must not be empty` (shown under the shared rule above).

### `data_set`

**In plain words.** The kind piece on forms generated from data sets:
`D2DS_<data set>` is the form of one data set.

**When you would change it.** Almost never; preference only.

**Example.**

```toml
[generate.naming]
data_set = "Form"
```

Produces `D2Form_...` instead of `D2DS_...`.

**Default:** `"DS"` - **If you leave it out:** data-set form names carry `DS`.

**If you get it wrong:** the shared rule above refuses it.

### `program`

**In plain words.** The kind piece on forms generated from programs: an event
program's form, and a tracker program's registration form, are both
`D2PR_<program>`.

**When you would change it.** Almost never; preference only.

**Example.**

```toml
[generate.naming]
program = "Prog"
```

Produces `D2Prog_...` instead of `D2PR_...`.

**Default:** `"PR"` - **If you leave it out:** program form names carry `PR`.

**If you get it wrong:** the shared rule above refuses it.

### `program_stage`

**In plain words.** The kind piece on forms generated from tracker program
stages - each stage of a tracker program becomes its own form,
`D2PS_<stage>`.

**When you would change it.** Almost never; preference only.

**Example.**

```toml
[generate.naming]
program_stage = "Stage"
```

Produces `D2Stage_...` instead of `D2PS_...`.

**Default:** `"PS"` - **If you leave it out:** stage form names carry `PS`.

**If you get it wrong:** the shared rule above refuses it.

Next: [Serving it: the `[serve]` section](301-serving.md) - how the local
capture server runs.

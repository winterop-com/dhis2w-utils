# Who the guide is: `profile` and `[ig]`

**Who this is for:** the person editing `fhir.toml`.

**Before you start:** read [The settings file](301-fhir-toml.md) - what
`fhir.toml` is, where it lives, and how to edit it without breaking it. Have
your project's file open.

**You will be able to:**

- point the project at a different saved DHIS2 connection with `profile`
- change the guide's id, address, name, title, and publisher in `[ig]`
- move the guide from `draft` to `active`, and read the refusal when a value
  is not one the file accepts

This page covers the seven options that say where the guide's content comes
from and who the guide itself is: the top-level `profile` line, and the six
lines of the `[ig]` section. All six `[ig]` lines are filled in when the
project is first created (`d2w fhir init` asks for them), so day to day you
read this page when one of them needs to change - a new title, a real web
address before the first publish, the switch from draft to active.

"IG" is short for implementation guide - the website of forms, code lists, and
facility pages this project generates. This series just calls it "the guide".

### `profile`

**In plain words.** Which saved DHIS2 server connection the generate command
reads your metadata from. Connections are saved once with `d2w profile add`
(name, server address, login) and referred to by name after that - this line
holds that name, so the file never contains a password.

**When you would change it.** Your project moves from reading the test server
to reading the real one: someone saves a connection named `production` for
you, and you change this line to point at it. Or you are handed a project with
no profile line at all and the generate command tells you to set one.

**Example.**

```toml
profile = "hmis"
```

Every `d2w fhir generate` in this project now reads from the DHIS2 server the
`hmis` connection points at.

**Default:** unset - **If you leave it out:** the command falls back to
whatever default connection is configured on your computer, and refuses with a
"no profile" message when there is none. A project should name its profile
here so every person who runs it reads the same server.

**What wins over this line.** Three things can name the connection, and the
first one present is the one used:

1. `-p othername` on the command (`d2w -p othername fhir generate`) - one run,
   nothing on disk changes;
2. the `DHIS2_PROFILE` setting in the environment the command runs in - how a
   scheduled job or a build server points the same project at its own server;
3. this line.

With none of the three, the connection marked default on the computer is used.

**If you get it wrong:** a name that matches no saved connection stops
immediately with a one-liner listing what does exist:

```text
error: no profile named 'nosuchprofile' (available: local, play42, ...). Run `d2w profile list` to see all profiles.

hint:
  run `d2w profile list` to see available profiles
  or `d2w profile add <name> ...` to create one
```

## The `[ig]` section

### `id`

**In plain words.** The guide's technical identifier - a short, dotted,
lowercase name like `dhis2.fhir.sl` that names the built guide as a package.
Computers read it; people read `title`.

**When you would change it.** Almost never after the project is created. It is
chosen at `d2w fhir init` time, and everything the build produces is filed
under it - treat it like a filename you committed to.

**Example.**

```toml
[ig]
id = "dhis2.fhir.sl"
```

The built guide identifies itself as the package `dhis2.fhir.sl`.

**Default:** none, required - **If you leave it out:** the run refuses with
`ig.id  Field required` in the printout (same shape as the `canonical` error
below).

**If you get it wrong:** nothing in `d2w fhir generate` checks the id's shape -
you find out when the compile step (SUSHI) refuses the package name.
Stick to lowercase words separated by dots.

The next `d2w fhir init --refresh` (`make update` in a scaffolded project)
writes this id into every scaffold-managed file that carries it -
`ig/sushi-config.yaml`, `fhir.toml.example`, `ig/ig.ini`, and the project's
`pyproject.toml` name - which is what puts it on the built package.

### `canonical`

**In plain words.** The guide's permanent web address - the stem every page
and every published artifact hangs its own address off. It does not have to be
live while you are building; it has to be the address the guide will really be
published at.

**When you would change it.** Once, before the first real publish: the project
was scaffolded with a placeholder like `http://example.org/fhir` and the
ministry decides the real home, say `https://moh.gov.sl/fhir`. Changing it
after people have the published guide breaks every address they saved, so
decide it early.

**Example.**

```toml
[ig]
canonical = "https://moh.gov.sl/fhir"
```

Every code list and form in the guide now identifies itself under
`https://moh.gov.sl/fhir/...`.

**Default:** none, required - **If you leave it out:** the run refuses before
writing anything:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
ig.canonical
  Field required [type=missing, input_value={'id': 'dhis2.fhir.errlab...}, input_type=dict]
```

**If you get it wrong:** a trailing slash is quietly removed for you
(`.../fhir/` becomes `.../fhir`). Beyond that nothing refuses a wrong address -
you find out when the published guide's internal links point somewhere the
guide does not actually live.

The next `d2w fhir init --refresh` (`make update` in a scaffolded project)
writes this address into every scaffold-managed file that carries it -
`ig/sushi-config.yaml` and `fhir.toml.example` - which is what points the built
guide at it.

### `name`

**In plain words.** The guide's computer-facing name: one word, letters and
digits, capitalized like `Dhis2FhirSl`. It appears where a machine needs a
name without spaces.

**When you would change it.** Almost never - it is set at project creation and
nothing user-facing shows it. Change `title` when you want to change what
people see.

**Example.**

```toml
[ig]
name = "Dhis2FhirSl"
```

**Default:** none, required - **If you leave it out:** the run refuses with
`ig.name  Field required` (same shape as the `canonical` error above).

**If you get it wrong:** nothing refuses a strange name here - you find out
when the compile step (SUSHI) complains about it. One word, starting
with a capital letter, is always safe.

The next `d2w fhir init --refresh` (`make update` in a scaffolded project)
writes this name into every scaffold-managed file that carries it -
`ig/sushi-config.yaml` and `fhir.toml.example` - which is what carries it into
the compile.

### `title`

**In plain words.** The human title shown at the top of every page of the
published guide - "Sierra Leone HMIS FHIR Guide", not `Dhis2FhirSl`.

**When you would change it.** Whenever the people naming the publication want
different words on the cover. It is display text: no generated artifact
depends on the wording.

**Example.**

```toml
[ig]
title = "Sierra Leone HMIS FHIR Guide"
```

That exact text becomes the guide's page heading, and the guide's one-line
description under it. The next `d2w fhir init --refresh` (`make update` in a
scaffolded project) writes it into every scaffold-managed file that carries it -
`ig/sushi-config.yaml`, `fhir.toml.example`, and the guide's front page at
`ig/input/pagecontent/index.md` - which is what puts the new words on the
published guide.

**Default:** none, required - **If you leave it out:** the run refuses with
`ig.title  Field required`.

**If you get it wrong:** nothing refuses this - it is free text, and whatever
you type is what readers see.

### `publisher`

**In plain words.** The organisation standing behind the guide, shown in the
published guide's footer - typically the ministry or programme name.

**When you would change it.** When the owning organisation's name changes or
was entered wrong. Display text: no generated artifact depends on the wording.
The next `d2w fhir init --refresh` (`make update` in a scaffolded project)
writes it into every scaffold-managed file that carries it -
`ig/sushi-config.yaml` and `fhir.toml.example` - which is what puts the new name
in the published guide's footer.

**Example.**

```toml
[ig]
publisher = "Ministry of Health and Sanitation, Sierra Leone"
```

**Default:** none, required - **If you leave it out:** the run refuses with
`ig.publisher  Field required`.

**If you get it wrong:** nothing refuses this - it is free text.

### `status`

**In plain words.** Where the guide is in its life: `"draft"` while you are
still building and reviewing it, `"active"` when it is the published, official
version. Every generated form and code list carries this status, and while it
is `"draft"` they are all additionally marked experimental - a reader's tools
can tell "still cooking" from "rely on this".

**When you would change it.** Exactly once in the normal life of a project: the
day the ministry signs off and the guide becomes official, change `"draft"` to
`"active"` and regenerate. If a published guide is later reworked, back to
`"draft"` on the working copy.

**Example.**

```toml
[ig]
status = "active"
```

The next generate marks every artifact in the guide as active and no longer
experimental, and the next `d2w fhir init --refresh` (`make update` in a
scaffolded project) writes the same status into every scaffold-managed file that
carries it - `ig/sushi-config.yaml` and `fhir.toml.example` - which is what the
published guide states about itself.

**Default:** `"draft"` - **If you leave it out:** the guide and everything in
it is generated as draft and experimental, which is right while you are
building.

**If you get it wrong:** any other word refuses the run before anything is
written:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
ig.status
  Input should be 'draft' or 'active' [type=literal_error, input_value='published', input_type=str]
```

Next: [What goes in: the selection tables](301-what-goes-in.md) - selecting
data sets, programs, option sets, categories, and organisation units.

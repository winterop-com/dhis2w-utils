# Serving it: the `[serve]` and `[forward]` sections

**Who this is for:** the person editing `fhir.toml`.

**Before you start:** read [The settings file](301-fhir-toml.md) - what
`fhir.toml` is, where it lives, and how to edit it without breaking it - and
[Serve the guide](201-serve.md) for what the capture server is.

**You will be able to:**

- decide who can reach the capture server, and who it asks to identify
  themselves - the two settings to read twice
- change the port it listens on and read the refusal when the port is taken
- turn strict code checking on, serve the data-entry screens, and choose the
  map backgrounds the screens offer (or offer none, for an air-gapped
  deployment)
- decide whether the server accepts filled-in forms at all, and where the ones
  it accepts are kept
- decide whether the server answers questions about people at all, who can be
  found, and how many of them one page holds
- decide what answers a search for one of them
- state the posture every `d2w fhir forward` in the project runs in

`d2w fhir serve` starts a small
web server on your computer that serves the guide's content and accepts
filled-in forms - the capture server. The `[serve]` section is how *this
project* wants that server run, stated once in the file instead of retyped on
every start. For most of these options a command-line flag wins over the file
for a single run. Three have no flag behind them, and each for the same reason -
what they decide is what the server *is* rather than how one run of it went:
[`capture`](#capture), [`spool_dir`](#spool_dir), and the whole
[`[serve.tracked_entities]`](#tracked_entities) table - which
[`[serve.search]`](#search) joins for the same reason.

Two things to know before the options:

- The server serves what was last generated and compiled. Starting it in a
  project that has never been built stops with the line below, which names the
  two commands that produce one. (`d2w fhir serve --live` skips the compile by
  reading straight from the DHIS2 server instead.)

    ```text
    error: no compiled IG at ig/fsh-generated/resources - run `d2w fhir generate`, then `make sushi` in the project, and serve again.
    ```

- The server asks nobody who they are until you tell it to. `auth = "none"` -
  the default - serves every caller who can reach it, so `host` and
  [`auth`](#auth) are two halves of one decision: who can reach it, and who it
  will answer. Binding anything but loopback while `auth` is unwritten is
  refused at startup for exactly that reason. A `--live` run widens what a
  caller can see: that mode answers questions about people - it searches the
  DHIS2 instance for a person by identifier, returns the attribute values DHIS2
  holds about them, and, until you say otherwise, lists the people the instance
  holds a page at a time. A default run serves only what the guide published and
  can answer no such question, so an exposed live server is a materially
  different decision from an exposed compiled one. How much of that a live run
  offers is [`[serve.tracked_entities]`](#tracked_entities) below.

- **Who an answer is read as depends on `auth`.** Under
  [`auth = "dhis2"`](#auth) a register read is answered under the *caller's* own
  DHIS2 authorization - this server forwards their credentials to the instance,
  and DHIS2 decides per caller. Under `none` and `token` there is no caller to
  read as, so every answer is read under the facade's own DHIS2 profile,
  whoever asked.

- **Give the facade profile the rights the guide needs and no more**, in every
  posture. The startup store build, the instance address `/uiconfig` hands the
  capture screens, and `d2w fhir forward`'s drain all run as that profile in
  every posture, because none of them acts on behalf of a caller. And DHIS2
  skips its tracker ownership and access-level model outright for a superuser,
  writing no break-the-glass audit entry when it does - so a facade running as
  an administrator reads past sharing, ownership, and access levels with
  nothing in the audit trail to say so. Under `none` and `token` that profile
  is what answers every caller.

### `host`

!!! warning "Read before you decide - this is the exposure switch"
    `host = "127.0.0.1"` means the server is reachable from this computer
    only. Anything else - your machine's network address, or the
    every-network address `"0.0.0.0"` - opens it to other computers. Under the
    default `auth = "none"` this one line is the server's entire access
    control, which is why writing it without also writing [`auth`](#auth) is
    refused. Serving a district office is a deliberate deployment - someone
    accountable decides the posture and puts the server behind proper
    protection first. Changing this line to make an error go away is never the
    fix.

**In plain words.** Which network face the server listens on: your own
computer only (the default), or an address other machines can reach.

**When you would change it.** For an afternoon of showing a colleague on the
same office network, `host = "0.0.0.0"` makes your machine's address reachable
from their browser - and you change it back after. Anything longer-lived than
that is a deployment, not a config edit.

**Example.**

```toml
[serve]
host = "0.0.0.0"
```

The server answers on every network interface of the machine.

**Default:** `"127.0.0.1"` - **If you leave it out:** the server is reachable
only from the computer it runs on. This is the posture to keep.

**If you get it wrong:** an address the machine does not have makes the server
fail at startup with a system error naming the address; nothing checks the
value before that. Opening it wide without stating a posture is refused before
the socket opens, and the refusal names the line to write - see
[`auth`](#auth).

### `port`

**In plain words.** The number after the colon in the server's address
(`http://127.0.0.1:8080`). Two programs cannot share one port on one machine.

**When you would change it.** You run a local DHIS2 on the same machine - it
usually owns 8080, so the project states `port = 8090` once and every
`d2w fhir serve` in it uses that.

**Example.**

```toml
[serve]
port = 8090
```

The server starts at `http://127.0.0.1:8090`.

**Default:** `8080` - **If you leave it out:** the server tries 8080, the very
port a local dev DHIS2 commonly owns.

**If you get it wrong:** a taken port is refused as one line before anything
starts:

```text
error: port 8080 on 127.0.0.1 is already in use (usually the local DHIS2 instance; set [serve] port in fhir.toml or pass --port)
```

The check tries to take the port on every address whose holder would contend
for it: the one `host` names, the other IP stack's loopback, and the
all-interfaces address of both stacks. A program published to all interfaces
- Docker publishing `*:8080` is the common case - is caught by that last
pair, which is the one that matters: a server can otherwise bind `127.0.0.1`
underneath such a listener, leaving two programs on one port number answering
different callers.

A non-number stops the run earlier:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
serve.port
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='eighty', input_type=str]
```

### `auth`

**In plain words.** Who this server answers: everybody, anybody holding a token
you issued, or anybody who can sign in to the DHIS2 instance behind it.

**When you would change it.** The moment the server is reachable from another
computer. `token` is the posture for a machine client - one shared secret, handed
to whoever integrates. `dhis2` is the posture for people: the clerks filling in
forms already have DHIS2 accounts, and this is how those accounts become their
credentials for the facade. It needs `--live`, because checking a credential
means asking the instance.

**Example.**

```toml
[serve]
host = "0.0.0.0"
auth = "dhis2"
```

Every caller presents the DHIS2 username and password they would sign in to the
instance with (or a DHIS2 personal access token as
`Authorization: ApiToken <token>`), and this server checks it by reading
`/api/me` on that instance as them. The username it gets back is recorded on
every receipt that caller captures - and every register read that caller makes
is sent to the instance under the same credentials, so each of them sees exactly
the people DHIS2 lets them see.

The `token` posture takes its tokens from the environment, never from this file:

```toml
[serve]
host = "0.0.0.0"
auth = "token"
```

```bash
export D2W_FHIR_SERVE_TOKENS='a-long-random-value,another-for-the-second-client'
```

Comma-separated. Rotating them is replacing the variable and restarting the
server. They are secrets, and `fhir.toml` is a file projects commit - so a
`token` posture with the variable unset is refused at startup rather than
started as a server that accepts nobody.

**Default:** the key is absent, which is not the same as `auth = "none"` -
**If you leave it out:** the server serves every caller and binds loopback
only. Binding any other interface with the key absent is refused:

```text
error: `0.0.0.0` is not a loopback interface, and this project's fhir.toml states no [serve] auth. Write the posture down before serving the facade where other hosts can reach it - add one line under [serve] in fhir.toml: auth = "none" to serve every caller, auth = "token" to take a static bearer token out of D2W_FHIR_SERVE_TOKENS, or auth = "dhis2" to have every caller present the DHIS2 credentials this facade checks against the instance. --auth states the same thing for one run.
```

`auth = "none"` written out passes that check. The difference is deliberate: an
absent key is nobody's decision, a written one is somebody's.

**If you get it wrong:** a value that is not one of the three stops the run
before anything starts.

```text
serve.auth
  Input should be 'none', 'token' or 'dhis2'
```

`"oauth2"` is among the values it will tell you it does not accept, and that is
current rather than an oversight: DHIS2 2.43.1's own authorization server
returns a 500 for any client its API creates (BUGS.md 96), so a project could
state it and nothing would answer. The name is reserved for when that is fixed.

**What each posture decides about the answer.** `none` and `token` decide who
may ask and nothing more: a live run reads DHIS2 as the profile the server was
started with, so what any caller sees is that profile's rights rather than their
own. `dhis2` decides both. Every register read it answers - the tracked entity
read, identifier search, the listing and its counts, the enrollment listing, and
`/evaluate`'s registered context - is sent to DHIS2 carrying the caller's own
`Authorization` header, so DHIS2's sharing, organisation unit scopes, ownership,
and access levels answer per caller, and this server applies no rule of its own.
What DHIS2 hides it hides: a tracked entity a caller may not see is a 404 here
because it is a 404 there. Each forwarded read also carries one header of this
server's own, `X-DHIS2W-Facade`, naming the software and version the read
arrived through - provenance for the DHIS2 access log, and never the username,
which the caller's own header already carries.

A register read that presents no credential is refused with a 401 rather than
answered as the facade, even under `auth_scope = "write"`, which leaves reads
unguarded otherwise: there is nobody to answer as. A read that presents one is
answered, whichever scope is in force - the credential is checked on the spot,
through the same brief cache the guarded addresses use.

The startup store build, the instance address `/uiconfig` hands the screens, and
`d2w fhir forward`'s drain stay on the facade's own profile in every posture,
because none of them acts on behalf of a caller - so give that profile the
rights the guide needs and no more. See the notes above the options.

### `auth_scope`

**In plain words.** How much of the server the posture covers: submissions only,
or everything.

**When you would change it.** `all` is for a server whose published guide is
itself not public - a project whose Questionnaires name programs and data
elements you would rather not hand out. `write` is right whenever the guide is
publishable and only the captures need a name against them.

**Example.**

```toml
[serve]
auth = "token"
auth_scope = "all"
```

Every address needs a token except `GET /metadata`, which stays open in every
posture: a client has to be able to read how to authenticate to a server before
it can. The capture UI's own files stay open too - a sign-in page nobody can
load is a sign-in page nobody can use.

**Default:** `"write"` - **If you leave it out:** credentials are asked for on
`POST /QuestionnaireResponse` and nowhere else. That is the one address this
facade changes anything at; every other POST it serves writes nothing -
`$generate` drafts a response from a published form, `/evaluate` runs an
expression over what is served, and a CDS Hooks call answers cards.

Under [`auth = "dhis2"`](#auth) the register is the exception to that, and not
by this key's doing: a read of it is answered under the caller's own DHIS2
authorization, so it asks for credentials in either scope. `write` still leaves
every read of the *published guide* open - the Questionnaires, the code lists,
`/metadata` - because those are the same documents for everybody.

**If you get it wrong:** a value that is neither stops the run before anything
starts.

```text
serve.auth_scope
  Input should be 'write' or 'all'
```

### `strict_codes`

**In plain words.** What the server does when a submitted form answer carries
a code that is not in the guide's published code lists. Off (the default), the
submission is stored and the mismatch is flagged as a warning. On, the
submission is refused outright.

**When you would change it.** Turn it on when the point of the exercise is
catching bad codes at the door - a data-quality drill, or a feed from a system
you do not trust yet. Leave it off when you would rather collect everything
and review the warnings than have submissions bounce.

**Example.**

```toml
[serve]
strict_codes = true
```

A submission whose coded answer is outside the served code lists is refused
instead of stored-with-warning.

**Default:** `false` - **If you leave it out:** out-of-list codes are stored
and flagged, never refused.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `serve.strict_codes`.

### `capture`

**In plain words.** Whether the server accepts filled-in forms at all. On -
the default - it receives submissions, stores each as a receipt, and says so
in the machine-readable description of itself it serves at `/metadata`. Off,
it publishes the guide and receives nothing: a submission is refused, and the
description no longer offers to take one.

**What stays on when it is off.** Everything that reads. The forms, the code
lists, the organisation unit registry, and the draft-a-response operation the
screens fill a form from all answer exactly as before - and so do **the
receipts this project already holds**. A form sent last month is still read
back at the address the sender was given, still searchable, and still counted
in the queue, because "this server stopped accepting new forms" is not a
reason to stop answering for the ones it took. Only the sending is gone, and
a receipt still in the queue is still forwarded by
[`d2w fhir forward`](201-forward.md).

**When you would change it.** Two situations. A project published for reading -
a guide someone browses, a reference server a colleague points their software
at to see what the forms look like - has no reason to accept data, and
accepting it would mean somebody has to look after what arrives. And a second
copy of a deployment, run so people can read the guide while one capturing
server does the collecting, must not quietly become a second place data lands.

**Example.**

```toml
[serve]
capture = false
```

The guide is served and read; a submitted form is refused.

**What a person using the screens sees.** The form opens, fills in, and reads
exactly as it does anywhere else - a form is worth reading on a server that
takes nothing - and where **Submit** would be there is the sentence *This
server does not accept submissions*. Nothing is offered that would fail.

**What a program sees.** The submission is refused with the FHIR error
document every refusal here uses, saying `[serve] capture` is false in this
project, and `/metadata` no longer lists `create` among the interactions it
answers on QuestionnaireResponse - so a client that reads the description
before sending never sends at all.

**Default:** `true` - **If you leave it out:** the server receives
submissions, which is what a capture server is.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `serve.capture`. There is
no command-line flag for this one: it changes what the server tells every
client it is, which is a decision the project makes rather than one
invocation.

### `ui`

**In plain words.** Whether the server also offers data-entry screens in the
browser - open the server's address and you get clickable forms and an
organisation unit map, not just machine-facing routes.

**When you would change it.** Set it `true` in a project whose whole workflow
is people filling in forms, so every `d2w fhir serve` brings the screens up. For
one demo run without editing the file, `d2w fhir serve --ui` turns it on for that
run only.

**Example.**

```toml
[serve]
ui = true
```

Opening `http://127.0.0.1:8080/` in a browser shows the data-entry screens.

**Default:** `false` - **If you leave it out:** the server runs
machine-facing only, and `d2w fhir serve --ui` remains the one-off way to get the
screens.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `serve.ui`.

### `spool_dir`

**In plain words.** Which folder the received forms are kept in. Every
submission the server accepts is written there as a file, and that folder is
also the queue [`d2w fhir forward`](201-forward.md) drains into DHIS2.

**One setting, both halves.** It sits in `[serve]` because the server is what
writes the files, and the forwarder reads this very key rather than having one
of its own - so moving the folder moves it for the whole loop at once. There is
no way to point the two at different places, which is deliberate: a receipt
written where nothing drains it is a form that was accepted and never arrived.

**When you would change it.** When the receipts should not live inside the
project folder. A deployment keeping data on a volume that is backed up says
so with an absolute path; a project whose folder is copied around a lot keeps
the data out of the copy the same way.

**Example.**

```toml
[serve]
spool_dir = "/srv/dhis2w/receipts"
```

The forms land in `/srv/dhis2w/receipts/received/`, and `d2w fhir forward`
drains that folder.

**Relative or absolute.** A path that does not start with `/` is read from the
project folder, so `spool_dir = "receipts"` is the project's own `receipts/`.
A path that does is used exactly as written.

**Version control and backups are yours once it leaves the project.** The
default folder is one the scaffold already tells git to ignore. A folder you
name somewhere else is outside all of that: nothing here excludes it from a
repository it happens to sit in, and nothing here backs it up. Received forms
that have not been forwarded yet are the only copy of what someone typed, so a
folder holding them is a folder worth backing up.

**Default:** `".serve/responses"` - **If you leave it out:** the receipts live
in `.serve/responses/` inside the project folder, which the scaffold's
`.gitignore` already covers.

**If you get it wrong:** an empty value (`spool_dir = ""`) is refused before
the run starts, because it names no folder:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
serve.spool_dir
  Value error, spool_dir is empty: name a directory the receipts live in, relative to the project root or absolute, or leave the key out for '.serve/responses'
```

A folder this machine will not let the server write to fails when a form
arrives rather than at startup, with the system's own error in the log. A
folder that simply does not exist yet is not a mistake: it is created.

### `basemaps`

!!! note "The one outbound call"
    Everything else the capture server does stays on your machine. The map
    background is the single exception: the browser fetches map tiles from
    whatever address a layer names. `basemaps = []` is the fully offline
    posture - boundaries on a plain canvas, no outside request ever.

**In plain words.** The background maps (streets, coastlines, imagery) the
data-entry screens can draw under the organisation-unit boundaries. Each entry
gives a layer a name and a web address template pointing at a tile service.

**How the screens use it.** The map's layer control lists these layers in the
order you write them, opens on the first, and always carries a **None** entry
beside them. So switching the background off is a click for whoever is reading
the map, and offering no layer at all - `basemaps = []` - is how a deployment
says the browser must never fetch a tile.

**When you would change it.** Three situations. Air-gapped or no-outside-
traffic environment: write `basemaps = []`. A deployment serving other people:
name your own tile service - the default is OpenStreetMap's volunteer-funded
servers, fine for one laptop for an afternoon, not for a district office's
daily traffic. Somebody needs to see roofs and fields rather than street lines:
add a satellite layer beside the street one, so both are a click apart.

**Example.**

```toml
[[serve.basemaps]]
name = "OpenStreetMap"
url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

[[serve.basemaps]]
name = "Satellite"
url = "https://tiles.example.org/satellite/{z}/{x}/{y}.jpg?api_key=YOUR_KEY"
```

The map opens on OpenStreetMap, and its layer control offers Satellite and
None beside it.

**Attribution is worked out here, not configured.** The capture server states
OpenStreetMap's required credit line for OpenStreetMap's tiles, because it is
the source this project ships. It states none for anybody else's, because it
does not know their terms - crediting a tile service you point it at is your
obligation, and a satellite provider will tell you the exact line they want.

**Default:** one layer, `OpenStreetMap` at
`https://tile.openstreetmap.org/{z}/{x}/{y}.png` - **If you leave it out:** the
map offers OpenStreetMap's tiles, which need no account or key, and each
viewer's browser fetches them from openstreetmap.org.

**If you get it wrong:** nothing refuses this - a wrong address just means that
layer's background comes up blank or broken in the browser while the boundaries
still draw, and None is one click away. A layer with an empty `url` is dropped
rather than offered.

**From the command line.** `--basemap` overrides the whole table for one run
and repeats: `--basemap "Streets=https://.../{z}/{x}/{y}.png" --basemap
"https://aerial.example/{z}/{x}/{y}.jpg"`. A value with no `Name=` in front is
named after its host. `--basemap none` offers no layer at all, which is what
`basemaps = []` says in the file; naming it beside a real layer is refused
rather than guessed at.

### The register: the `[serve.tracked_entities]` table { #tracked_entities }

!!! note "The one surface whose cost grows with use"
    Everything else this server answers, it answers out of files it read once
    when it started: a hundred readers cost it no more than one. The register is
    the exception. Every search, and every page of the listing, is a question put
    to the DHIS2 instance while somebody waits - so the more this surface is
    used, the more work the instance does. The six settings below are how a
    project decides how much of that it wants.

A live run - `d2w fhir serve --live` - answers three
questions about the instance's tracked entities that no other run can answer:

- *"Who holds this identifier?"* - the search, from a card number, a register
  number, a barcode, or whatever value the subject is known by.
- *"Who is in here?"* - the listing: records a page at a time, for somebody who
  has no identifier to type.
- *"Which programmes is this record in?"* - the enrollment list the capture
  screens' pickers choose from, at
  `/tracked-entities/{uid}/enrollments`.

A server reading a compiled guide answers none of the three and says so. It
holds no connection to a DHIS2 instance, so there is nothing to answer about -
that is a property of the mode, not something this table turns on.

#### What the register calls the things it holds { #tracked_entities-resources }

Not this table's business, and deliberately so. DHIS2 tracks whatever a project
tracks - people, households, herds, water points, specimen batches - and the
word the guide publishes each of those under is decided once, on the generation
side, in
[`[generate.tracked_entity_types]`](301-what-goes-in.md#tracked_entity_types).
Generating the guide turns that decision into part of the published guide: a
small lookup table with one row per tracked entity type, saying which word its
records are served under.

**The published guide decides, not this file.** When the server starts it reads
that lookup table and offers one search address per word it finds: a project
tracking people alone offers the address for people and nothing else, and a
project that also registers specimen batches offers a second address for
specimens beside it. So the way to change which kinds of record the register
answers about is to change `[generate.tracked_entity_types]` and generate again -
not to edit the file the server was started with. That is also what keeps the
register and the published forms from ever describing the same type differently.

Each address answers the same way, and answers narrowly: it gives back the DHIS2
id of the record, the values of the attributes DHIS2 declares unique, and the
remaining attribute values as labelled extras - **and nothing else**. There is no
name, sex, or date of birth on a person served here unless a tracked entity
attribute of your instance holds it, because DHIS2 is the only thing this server
reads and it never invents a value it was not given.

`[serve.tracked_entities]` is how a project offers *less* than all of that, and
it says the same thing about every kind of record: whether this server answers
about the instance's records at all is one decision, not one per kind. Every
setting has a default that makes the register work without your writing the
table at all; you write it when a deployment wants the register narrowed, or a
page size the default does not fit. Unlike the rest of `[serve]`, there is no
command-line flag for any of these six - a run that should answer less is a
project that says so in the file.

```toml
[serve.tracked_entities]
enabled = true
listing = true
page_size = 20
page_size_limit = 100
```

#### `enabled` { #tracked_entities-enabled }

**In plain words.** Whether this server answers questions about people at all.
On - the default - a live run searches by identifier, lists people, and lists
one person's enrollments. Off, none of the three exists: the run is live in
every other way, and the people surface is simply not there.

**When you would change it.** Two situations, and neither is a fault being
worked around. A live run whose whole job is to serve the guide's forms
straight off the instance without a compile step has no reason to also let
anyone who can reach the port ask about the people in that instance. And a
demonstration on an instance that holds real records is exactly the room in
which the safest posture is that no person can be looked up at all.

**Example.**

```toml
[serve.tracked_entities]
enabled = false
```

A live server that serves forms, code lists, and the organisation-unit
registry, and answers nothing about people.

**What a person using the screens sees.** No register in the navigation,
and a registration form's **Person** control offers **New person** alone -
exactly what a compiled guide offers. Nothing is greyed out or half-offered:
the screens are told what this server answers and draw only that.

**Default:** `true` - **If you leave it out:** a live run answers all three
questions and a compiled run answers none of them. That difference is the mode
doing the work, not this setting.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `serve.tracked_entities.enabled`.

#### `listing` { #tracked_entities-listing }

**In plain words.** Whether "show me the people" is a question this server
answers. On - the default - asking for people without naming an identifier
returns them a page at a time. Off, the identifier search still works, so
somebody you can name can be found; nobody can page through the register.

**When you would change it.** When looking a known person up is legitimate and
browsing everybody is not. That line is a common one to draw: a clerk capturing
a visit has a card in their hand and needs the one person on it, while paging
through everyone an instance holds is a different capability that happens to
share an address. This setting draws the line in one word.

**Example.**

```toml
[serve.tracked_entities]
listing = false
```

An identifier search answers as it always did; a request that names no
identifier is refused with a message saying the listing is off in this project.

**What a person using the screens sees.** The register keeps its search
box and offers no browsing: it opens on an invitation to search rather than on
the first page of people, and there are no paging controls rather than empty
ones.

**Default:** `true` - **If you leave it out:** a live run's register opens
on the first page of the people the instance holds.

**If you get it wrong:** TOML wants bare `true` or `false`; a printout naming
`serve.tracked_entities.listing` is what a different value gets you. Setting
`listing = true` beside `enabled = false` changes nothing - `enabled` removes
the surface the listing is part of.

#### `page_size` { #tracked_entities-page_size }

**In plain words.** How many people come back in one page when whoever asked
did not say. The register shows a page of this size, and a program reading
the server directly gets this many per page unless it asks for a different
number.

**When you would change it.** To fit what the page is read on: twenty is a
comfortable browser page, and a deployment whose clerks work on large monitors
may prefer fifty. Lower it - ten, five - when the instance is slow and what
matters is that the first page arrives quickly.

**Example.**

```toml
[serve.tracked_entities]
page_size = 50
```

Fifty people per page, for anyone who does not ask for a different number.

**Default:** `20` - **If you leave it out:** twenty people per page. Keep the
value at or below `page_size_limit`: the limit is the ceiling on any page, and
a default page larger than the ceiling is a contradiction the file should not
state.

**If you get it wrong:** a value that is not a whole number stops the run
before it starts, with a printout naming `serve.tracked_entities.page_size` and saying
an integer was expected.

#### `page_size_limit` { #tracked_entities-page_size_limit }

**In plain words.** The largest page anybody is allowed to ask for. A request
that asks for more is not refused - it is answered with this many, and a link
to the next page. Ask for five thousand people at once and you get a hundred,
plus the link that gets you the next hundred.

**Why there is a ceiling at all.** One page is one read from the DHIS2
instance, and the size of the page is the size of that read. With no ceiling, a
single request could ask the instance to assemble every person it holds - a
heavy question for the instance, and a slow answer for everyone queued behind
it. The ceiling turns that one enormous question into a sequence of ordinary
ones, without anybody being told no.

**When you would change it.** Raise it when a known program is pulling people
out in bulk and the instance is comfortable with larger reads. Lower it -
twenty-five, ten - on a modest instance, or one shared with people doing real
work, where the point is that no single request can cost much.

**Example.**

```toml
[serve.tracked_entities]
page_size_limit = 25
```

Nobody obtains more than twenty-five people in one page, however large a page
they ask for.

**Default:** `100` - **If you leave it out:** the largest page anyone can
obtain holds a hundred people, and a larger ask is quietly given a hundred
rather than refused. A refusal would leave a client that asked for too much
holding nothing, when a smaller page is precisely what it should have had.

**If you get it wrong:** a value that is not a whole number stops the run with
a printout naming `serve.tracked_entities.page_size_limit`.

#### `tracked_entity_types` { #tracked_entities-tracked_entity_types }

**What a tracked entity type is.** DHIS2 does not only track people. Every
record it tracks is of exactly one **tracked entity type**, and an instance
decides what its types are: Person, certainly, but a laboratory instance also
tracks Specimen, a livestock programme tracks a herd, a water programme tracks
a water point. The type is what kind of thing the record is about.

**In plain words.** Which of those types this server treats as people. Left
empty - the default - it is the types this project's own registration forms
register, read off the guide the project published. Naming ids here narrows it
to exactly those, for the search and the listing alike.

**When you would change it.** The laboratory instance is the clearest case. It
registers people *and* specimens, both as tracked entity types, and if this
project publishes a registration form for each, then "the types the forms
register" includes both: the listing pages through specimens beside patients,
and an identifier search can find a specimen whose barcode happens to match
what somebody typed. Naming the person type here makes people the only thing
this surface is about. The other case is plain narrowing - an instance with
several person-like registers, where this deployment works with one of them.

**Example.**

```toml
[serve.tracked_entities]
tracked_entity_types = ["nEenWmSyUEp"]
```

The search and the listing consider records of that one type, whatever else
the project's forms register.

**Where the ids come from.** The eleven-character id DHIS2 shows for the type
under Tracked entity types in its Maintenance app - the same id the guide
publishes that type's registration form under.

**Not the same table as `[generate.tracked_entity_types]`.** That one, on the
generation side, says *what a type is* - the word a herd or a water point is
published under ([what goes in](301-what-goes-in.md#tracked_entity_types)) - and
what it produces is the lookup table this server reads at startup. This one says
which types the register answers about at all. The same words doing two
different jobs, in two different sections - and naming a type here does not
change what it is served as, only whether it is served.

**Default:** `[]` (empty) - **If you leave it out:** the types this project's
registration forms register, which for an ordinary person-tracking project is
one type and needs no configuration at all. A project that publishes no
registration form names no type at all, and the people surface answers empty -
the honest reading of a guide with no people in it.

**If you get it wrong:** nothing in `fhir.toml` can check an id against an
instance it has not connected to, so a mistyped one is not refused. It shows up
as a surface that finds nobody: an empty listing, and searches that match
no one, on an instance you know holds thousands of people. Check the id against
the type in DHIS2 before concluding the search is broken.

#### `search_attributes` { #tracked_entities-search_attributes }

**The two flags DHIS2 publishes.** An instance can mark a tracked entity
attribute **unique**, which means it refuses to store the same value on two
records - that flag is what turns a value into a name for a subject rather than
a fact about one, since two people can share a village and a year of birth but
only one person holds card number 10023. It can also mark an attribute
**searchable**, which is DHIS2's own statement that this is a value people are
looked up by. The guide publishes both flags on every attribute it carries, and
this server reads them back off the guide.

**Both are keys by default.** A search that names no key looks under every
attribute the instance declares unique **or** searchable. Uniqueness alone would
be too narrow to be useful: a clinic finds a woman by typing her first name,
which DHIS2 marks searchable and nothing enforces uniqueness on, and a facade
that keyed on uniqueness alone would refuse the one lookup the instance itself
permits. Several matches is a normal answer, not a failure - the register's
listing is already the shape that renders them.

**In plain words.** Which attributes count as search keys: what somebody can
search by. Empty - the default - means the unique and the searchable ones.
Naming attribute ids here means those, whether DHIS2 marks them anything at all.

**When you would change it.** Two situations.

An instance declares five unique attributes and marks a dozen searchable, and
the field only ever quotes one of them. A search that names no key tries every
key at once, so seventeen keys mean seventeen questions to the instance for one
typed value. Naming the key people actually carry makes it one question, and the
results come back only under that key.

Or the number a clerk actually types - a national identity number, a facility
register number - is one the instance marked neither unique nor searchable,
which happens whenever somebody decided the flags would be more trouble than
they are worth. Naming it here makes it a search key regardless.

!!! warning "A key that is not unique can name more than one record"
    Uniqueness is the thing that makes one value mean one subject. A searchable
    attribute - the default set includes them - can honestly come back with
    several people who share the value: a first name, a phone number shared by a
    household, a register number reused after a book was filled. The answer is
    not wrong; it is what the instance holds. It does mean whoever reads it has
    to choose between records, which is what the listing on screen is for.

**Example.**

```toml
[serve.tracked_entities]
search_attributes = ["lZGmxYbs97q"]
```

One key. A value typed with no key named is looked for under that attribute and
no other.

**Where the ids come from.** The eleven-character id DHIS2 shows for the
attribute under Tracked entity attributes in its Maintenance app. The guide
also publishes them, with their names and their uniqueness flag, in the tracked
entity attribute dictionary the capture screens' Terminology page browses.

**Default:** `[]` (empty) - **If you leave it out:** every attribute the
instance declares unique or searchable is a search key, which is the set DHIS2
itself already treats as worth looking somebody up by.

**If you get it wrong:** as with the types above, no check is possible before
the server connects, so a mistyped id is a key nothing is ever found under. The
symptom is a value you know a person holds finding nobody.

### What answers a search: the `[serve.search]` table { #search }

`[serve.tracked_entities]` says what may be looked up. This table says what
answers the lookup. It has one key today, and a live run that writes no table at
all behaves exactly as it always has.

#### `backend` { #search-backend }

**In plain words.** What a register search runs through. `"dhis2"` is the DHIS2
instance itself: one `filter=<attribute>:eq:<value>` query per search key per
tracked entity type, put to the instance while somebody waits, which is the
search this server has always run.

**Why the key exists while it has one value.** Because of the shape it fixes,
which is worth more than the choice it offers. A search answers with tracked
entity identifiers - who matched, and nothing about them. The record behind a
match is then read back from the instance under the credentials the request runs
as, so DHIS2 applies its sharing, its organisation-unit scopes, and its
ownership rules to every record this server hands out, whatever found it. That
is what lets something other than the instance answer the *finding* half later
without this server ever deciding on DHIS2's behalf who may see whom. The design
is [the materialized projection](design/projection.md), sections 7 and 9.

**What that costs, stated.** A search that finds nobody costs what it always
did. A search that finds somebody spends one more read on the instance - the
read of the person it is about to hand over, which is the read DHIS2 authorizes.

**When you would change it.** Not yet. The second value, `"index"`, arrives with
the OpenSearch backend, and with it the things an exact match cannot do: finding
`ສົມສັກ` from `Somsack`, surviving a typed one-character slip, ranking near
matches. Until that ships, this key has one word and the file refuses every
other.

**Example.**

```toml
[serve.search]
backend = "dhis2"
```

**Default:** `"dhis2"` - **If you leave it out:** the instance answers every
search, which is what a live run has always done.

**If you get it wrong:** the file refuses the value and names the key, before
the server starts:

```
error: 1 validation error for FhirProjectConfig
serve.search.backend
  Input should be 'dhis2' [type=enum, input_value='index', input_type=str]
```

## Forwarding it: the `[forward]` section { #forward }

`d2w fhir forward` is the other half of the loop the capture server opens - see
[Forward captures into DHIS2](201-forward.md). Four options in `fhir.toml`
belong to it, and each but `live` has a command-line flag that outranks it for one run:
**flag beats table beats default**, the same order the rest of `[serve]`
follows. Which folder a drain reads is not here - it is
[`[serve] spool_dir`](#spool_dir), because the server is what writes it.

### `live`

**In plain words.** What a drain does when the project holds no compiled guide.
On (the default), it builds the guide it needs off the DHIS2 instance, using
the same builders a `--live` run reads through. Off, it refuses and names the
two commands that produce a compiled guide.

**When you would change it.** Turn it off when forwards must read a reviewed,
published guide and nothing else - a production drain where "whatever the
instance says today" is not an acceptable answer to "which form was this
answered against". Leave it on for the live workflow, where nothing was ever
built: a `--live` run captures receipts a compiled guide would refuse to
explain, and this is what lets those receipts reach DHIS2.

**Example.**

```toml
[forward]
live = false
```

**Default:** `true` - **If you leave it out:** a project with a compiled guide
reads it off disk exactly as before, and a project without one builds a guide
off the instance instead, paying one full metadata read per drain. The progress
step says which happened.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `forward.live`.

### `import`

**In plain words.** Whether a plain `d2w fhir forward` in this project writes
to DHIS2. Off - the default - a bare run is a **dry run**: every form is still
sent to the real DHIS2 server, under the mode that server offers for checking
without saving, so DHIS2's own rules decide whether it would be accepted while
nothing is stored and no receipt moves. On, the bare run commits.

**Why a project would say it.** Because typing `--import` on every run is how
a team ends up with one person who forgot. A project whose drains are routine -
a nightly job, a clerk running `d2w fhir forward` at the end of the day - states
`import = true` once, and a run that is meant to check rather than to write
says `--dry-run` on the command line for that one run.

**Example.**

```toml
[forward]
import = true
```

`d2w fhir forward` writes to DHIS2; `d2w fhir forward --dry-run` still checks
without writing.

**Both flags still work, in both directions.** `--import` commits whatever the
file says, and `--dry-run` checks whatever the file says. The flag is a
statement rather than an absence, so it wins even when it agrees with the
default and the file does not.

**Default:** `false` - **If you leave it out:** a bare run is a dry run, and
`--import` is what commits it. That is the safe way round, and it is the one to
keep until the runs are boring.

**If you get it wrong:** the key is spelled `import` - the word the command
uses. `import_responses` is refused as a name the file does not declare, as is
anything else close to it. TOML wants bare `true` or `false`; another kind of
value stops the run with a printout naming `forward.import`.

### `register_completeness`

**In plain words.** Whether a forwarded aggregate form that says it is
finished also marks its data set complete for the period, organisation unit,
and reporting dimension its figures landed under. On by default, because the
form said it was finished.

**When you would change it.** When marking a data set complete is somebody
else's decision - a supervisor signing off in DHIS2 after checking the figures,
or a workflow where completeness means "approved" rather than "typed in".
Turning it off leaves the figures imported exactly as before and marks nothing.

**Example.**

```toml
[forward]
register_completeness = false
```

The figures are imported; no data set is marked complete by the drain.

**Default:** `true` - **If you leave it out:** a `completed` aggregate form
marks its data set complete once DHIS2 has taken its figures - never before, so
the mark is never a claim about data the server refused. A form that says it is
still in progress imports its figures and marks nothing, whatever this key says.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming
`forward.register_completeness`. `--register-completeness` and
`--no-register-completeness` override it either way for one run.

### `overwrites`

**In plain words.** What a drain does when a figure it is about to send is one
a form this project already forwarded sent - the same data element, category
option combo, period, organisation unit, and reporting dimension. `"allow"` -
the default - sends it, and the run names every figure it replaced along with
the form that sent it before. `"refuse"` sends nothing at all: any form
carrying such a figure stays in the queue with the covered figures written down
beside it.

**When you would change it.** Turn it to `"refuse"` in a deployment where
forwarded figures must only change through a declared correction that somebody
reviews - or while two capture clients are running against one instance and
nobody has decided yet which of them is authoritative. Leave it at `"allow"`
where a clerk re-entering a month they got wrong is the ordinary case, which is
what DHIS2 itself expects: the server keeps the newest figure for a cell
whatever a client does, and this is the toolkit agreeing with the platform it
writes into rather than inventing a stricter rule on top.

**Example.**

```toml
[forward]
overwrites = "refuse"
```

A form carrying a figure an earlier submission already sent is refused whole -
never in part, because a form posted half-way would land a report nobody filled
in. It stays in `.serve/responses/received/` with `<id>.refusal.json` beside it
naming each covered figure, and `d2w fhir spool` lists it as refused and still
queued. Running `d2w fhir forward --import --overwrites allow` sends it.

**Default:** `"allow"` - **If you leave it out:** every figure an earlier
submission already sent is sent again and named in the run report, and nothing
is refused over it. That is what a drain has always done; the key is what lets
a deployment say otherwise.

**If you get it wrong:** the two values are `"allow"` and `"refuse"`, quoted.
Anything else - `"reject"`, `"off"`, a bare `false` - stops the run with a
printout naming `forward.overwrites`. `--overwrites allow` and
`--overwrites refuse` override it either way for one run. The key reaches
aggregate figures only: tracker records carry their own DHIS2 identity, so they
collide rather than overwrite, and no setting here changes that.

Next: [The capture contract](401-capture-contract.md) - the integrate tier
starts with what a valid submission carries. Or back to
[The settings file](301-fhir-toml.md), the index of this section.

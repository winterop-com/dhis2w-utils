# Serving it: the `[serve]` section

**Who this is for:** the person editing `fhir.toml`.

**Before you start:** read [The settings file](301-fhir-toml.md) - what
`fhir.toml` is, where it lives, and how to edit it without breaking it - and
[Serve the guide](201-serve.md) for what the capture server is.

**You will be able to:**

- decide who can reach the capture server, and understand why that is the
  one setting to read twice
- change the port it listens on and read the refusal when the port is taken
- turn strict code checking on, serve the data-entry screens, and set the
  map background (or turn it off for an air-gapped deployment)

`d2w fhir serve` (the `make serve` target runs exactly that) starts a small
web server on your computer that serves the guide's content and accepts
filled-in forms - the capture server. The `[serve]` section is how *this
project* wants that server run, stated once in the file instead of retyped on
every start. A command-line flag still wins over the file for a single run.

Two things to know before the options:

- The server serves what was last generated and compiled. Starting it in a
  project that has never been built stops with
  `error: no compiled IG at ig/fsh-generated/resources - run 'd2w fhir generate', then 'make sushi' in the project, and serve again.`
  (`make serve-live` skips the compile by reading straight from the DHIS2
  server instead.)
- The server has **no login**. Anyone who can reach it can read everything it
  serves and submit forms to it. That is why `host` below is the option to
  read most carefully.

### `host`

!!! warning "Read before you decide - this is the exposure switch"
    `host = "127.0.0.1"` means the server is reachable from this computer
    only. Anything else - your machine's network address, or the
    every-network address `"0.0.0.0"` - opens it to other computers, and the
    server has no login: this one line is its entire access control. Serving
    a district office is a deliberate deployment - someone accountable puts
    the server behind proper protection first. Changing this line to make an
    error go away is never the fix.

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
value before that. The riskier mistake - opening it wide - produces no error
at all, which is what the warning above is for.

### `port`

**In plain words.** The number after the colon in the server's address
(`http://127.0.0.1:8080`). Two programs cannot share one port on one machine.

**When you would change it.** You run a local DHIS2 on the same machine - it
usually owns 8080, so the project states `port = 8090` once and every
`make serve` in it uses that.

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

The check binds an IPv4 socket, so a listener holding the port only on IPv6
(Docker on macOS publishing `*:8080` is the common case) is not caught, and
the server starts beside it.

A non-number stops the run earlier:

```text
pydantic_core._pydantic_core.ValidationError: 1 validation error for FhirProjectConfig
serve.port
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='eighty', input_type=str]
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

### `ui`

**In plain words.** Whether the server also offers data-entry screens in the
browser - open the server's address and you get clickable forms and an
org-unit map, not just machine-facing routes.

**When you would change it.** Set it `true` in a project whose whole workflow
is people filling in forms, so every `make serve` brings the screens up. For
one demo run without editing the file, `make serve-ui` turns it on for that
run only.

**Example.**

```toml
[serve]
ui = true
```

Opening `http://127.0.0.1:8080/` in a browser shows the data-entry screens.

**Default:** `false` - **If you leave it out:** the server runs
machine-facing only, and `make serve-ui` remains the one-off way to get the
screens.

**If you get it wrong:** TOML wants bare `true` or `false`; anything
unrecognisable stops the run with a printout naming `serve.ui`.

### `basemap`

!!! note "The one outbound call"
    Everything else the capture server does stays on your machine. The map
    background is the single exception: the browser fetches map tiles from
    whatever address this option names. `basemap = "none"` is the fully
    offline posture - boundaries on a plain canvas, no outside request ever.

**In plain words.** The background map (streets, coastlines) drawn under the
org-unit boundaries in the data-entry screens' map. It is a web address
template pointing at a tile service.

**When you would change it.** Three situations. Air-gapped or no-outside-
traffic environment: set `"none"`. A deployment serving other people: point it
at your own tile service - the default is OpenStreetMap's volunteer-funded
servers, fine for one laptop for an afternoon, not for a district office's
daily traffic. Otherwise: leave it alone.

**Example.**

```toml
[serve]
basemap = "none"
```

The map shows org-unit boundaries on a plain background and makes no outside
request.

**Default:** `"https://tile.openstreetmap.org/{z}/{x}/{y}.png"` - **If you
leave it out:** the map draws OpenStreetMap tiles, which need no account or
key - and each viewer's browser fetches them from openstreetmap.org.

**If you get it wrong:** nothing refuses this - a wrong address just means the
map's background comes up blank or broken in the browser while the boundaries
still draw. (`"none"` in any capitalisation is understood as "off".)

Next: [The capture contract](401-capture-contract.md) - the integrate tier
starts with what a valid submission carries. Or back to
[The settings file](301-fhir-toml.md), the index of this section.

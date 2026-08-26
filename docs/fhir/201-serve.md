# Serve the guide

So far the project is files on disk. This step puts a small HTTP server in
front of them, so another system can ask for a form the way it would ask any
web API - *give me the Child Health data set*, *give me the option list for
this data element*, *here is a filled-in form* - without a DHIS2 login and
without knowing anything about DHIS2's own API. It is not a second copy of
DHIS2 and it never writes to your instance: a submission it takes is held as
a receipt, and putting that receipt into DHIS2 is a separate command on a
later page.

**Who this is for:** the operator turning a generated project into that
running endpoint - something a capture client can read forms from and post
captures back to.

**Before you start:** a generated and compiled project - `d2w fhir generate`,
then a SUSHI run (see [Build and publish the guide](201-build-and-publish.md))
- or, for `--live`, a reachable DHIS2 instance and a resolvable profile.

**You will be able to:**

- start `d2w fhir serve` in both of its modes and know which one you want
- set the port, host, coded-answer strictness, and who is served once, in `[serve]`
- read a stored capture back and say precisely what it is - a receipt
- find the spool on disk and read the queue depth off it

The pages in this walkthrough run against a real project whose `fhir.toml`
states `[serve] port = 8390` - a local DHIS2 stack usually owns 8080, and
moving out of its way in config is exactly what `[serve]` is for. Every
output shown is what that server actually answered.

## Install the server

The server ships as its own package, `dhis2w-fhir-serve`, because it needs
FastAPI and uvicorn while generation needs neither. A scaffolded project
already declares it, so `uv sync` in the project is enough; anywhere else:

```bash
pip install 'dhis2w-cli[serve]'      # or: uv add dhis2w-fhir-serve
```

Without it, `d2w fhir serve` says so and names both install routes rather
than failing on an import.

## Quickstart

```bash
cd demo-ig

# 1. Generate the IG source and compile it. The facade serves what SUSHI
#    wrote, so a project that has never been compiled has nothing to serve.
d2w fhir generate
docker run --rm -v $(pwd)/ig:/home/publisher/ig -v fhir-ig-cache:/home/publisher/.fhir \
    fhir-ig sushi .

# 2. Serve it. Loopback and port 8080 by default; ctrl-c stops it.
d2w fhir serve
```

(In a scaffolded project the Makefile wraps both: `make sushi` is the docker
run above, `make serve` is `uv run d2w fhir serve --ui` - the same endpoint
plus the capture UI at `/`.)

Then, from another shell, ask the server what it is:

```console
$ curl -s localhost:8390/metadata | jq '.software, .implementation.description'
{
  "name": "d2w fhir serve",
  "version": "1.7.0.dev0"
}
"DHIS2 FHIR capture facade (compiled store); stored QuestionnaireResponses are submissions as received - receipts, not a live view of DHIS2 data"
```

Read one form back, byte-faithful to what the project published:

```console
$ curl -s localhost:8390/Questionnaire/BfMAe6Itzgt | jq .title
"Child Health"
```

The read set is what a capture client resolves a form from: `Questionnaire`,
`CodeSystem`, `ValueSet`, `Location`, `Organization`, and `List`, plus
`ConceptMap` and its `$translate` operation, plus `QuestionnaireResponse` -
the one type the facade also receives. The full API surface, with search
semantics and both operations, is
[Consume the FHIR API](401-consume-the-fhir-api.md).

## The two modes

| Mode | What the store holds | What it also answers | What it needs |
| --- | --- | --- | --- |
| default | `ig/fsh-generated/resources` (what SUSHI compiled) merged with `ig/input/resources/` (the registry, terminology, concept-map, and category JSON the generate targets wrote, which SUSHI never re-emits) | nothing beyond the store | a compiled IG on disk; no DHIS2 connection at all |
| `--live` | the same read set, built straight off a DHIS2 instance at startup | the register - one tracked entity by identifier, the listing of them, one entity's enrollments, and one person's patient summary - read from the instance per request, and gated by `[serve.tracked_entities]` and `[ips]` | a reachable instance and a resolvable profile; no compile step |

A live run has one more posture available to it, and it is opt-in: a **synced
copy** of the register, filled by `d2w fhir sync` and searched instead of the
instance. It changes what a search can find and how much it costs, and it changes
nothing about who may see whom - [Serve from a synced
copy](#serve-from-a-synced-copy) is the whole of it.

The default mode is fully offline. If the project has never been compiled,
the server refuses to start and says what to run:

```
error: no compiled IG at ig/fsh-generated/resources - run `d2w fhir generate`,
then `make sushi` in the project, and serve again.
```

`--live` skips the compiled-IG check and builds the store through one DHIS2
client, opened during startup and held open for the life of the process. No
read of the store ever talks to DHIS2 again; the connection stays because the
register routes answer from the instance rather than from the store, and they
are the only ones that do. `GET /Patient?identifier=` finds one tracked
entity, `GET /Patient` with no parameters pages through the ones the instance
holds, `GET /tracked-entities/{uid}/enrollments` lists the programs one of
them is enrolled in, and `GET /tracked-entities/{uid}/events` answers what has
happened to one of them - every event of their enrollments, each served as the
response its program stage's own published form describes. All four are
documented in
[Consume the FHIR API](401-consume-the-fhir-api.md#the-register-search-identifier),
and all four shaped by
[`[serve.tracked_entities]`](301-serving.md#tracked_entities), which is how a project offers
less than all of them.

A fifth read sits on top of those two: `GET /Patient/{uid}/$summary` assembles
one person's [International Patient Summary](https://hl7.org/fhir/uv/ips/STU2/)
out of the register's own answer about them and the events it already serves.
It has a dial of its own, [`[ips] enabled`](301-what-goes-in.md#ips-enabled),
and it is off until a project turns it on -
[the patient summary](301-serving.md#ips-summary) is what it answers and what
it says about itself.

`Patient` is the resource a tracked entity type is published as by default,
not a fixed fact: the served register answers under whichever resource this
project's published map states each type is, so an instance whose types are
herds or specimen batches is read at that type's own resource rather than at
`Patient` ([what goes in](301-what-goes-in.md#tracked_entity_types)).

A compiled run holds no client, so all five answer a `not-supported`
OperationOutcome and `/metadata` declares no register resource at all. What `--live` serves is
byte-identical to what the compiled store would have served for the same
metadata, because both come out of the same JSON builders - the CodeSystem and
ValueSet pairs the foundation FSH declares included, so a client resolving the
form-type, period-type, or organisation-unit terminology gets the same
documents either way. What live mode leaves out is the definitional layer:
StructureDefinitions and the profiles only exist as JSON once SUSHI has
compiled them, and no FSH compiler runs in the server.

Either way, the store is a snapshot: read once at startup and never re-read.
Regenerate, recompile, or re-fetch, then restart the server to serve the new
state.

## `[serve]` in practice

Where a project is served from is a property of the project, not of the
invocation, so it is stated once:

```toml
[serve]
host = "127.0.0.1"          # loopback: only this machine reaches the facade
port = 8080                 # a local dev DHIS2 commonly owns 8080; 8090 is the usual way out
auth = "none"               # none | token | dhis2 - who this facade serves
auth_scope = "write"        # write gates submissions; all gates everything but /metadata
strict_codes = false        # true refuses an answer whose code is outside the served terminology
capture = true              # false serves the guide and receives nothing - the viewer posture
ui = false                  # true also serves the capture UI at /
spool_dir = ".serve/responses"   # where the receipts live, and what d2w fhir forward drains
```

`--live` and `--ui` runs read the table too, as do the Makefile targets that
wrap them - which is the point: a developer whose DHIS2 stack already holds 8080 states
`port = 8390` here and every invocation in that project honours it.
Precedence is **flag beats table beats default** - and `--strict-codes` has
an explicit `--no-strict-codes` twin so all three levels are reachable from
the command line.

A port something else already holds is refused before any output that looks
like a start:

```
error: port 8391 on 127.0.0.1 is already in use (usually the local DHIS2 instance;
set [serve] port in fhir.toml or pass --port)
```

The probe claims the port on every address whose holder would contend for it:
the host's own, the other IP stack's loopback, and both wildcards. That last
pair is what catches the common case. A published Docker container listens on
all interfaces, and the socket option a server sets to restart cleanly also
lets a second server bind `127.0.0.1` *underneath* such a listener - so a
loopback-only probe would call 8080 free, serve would start beside a local
DHIS2 container, and the two would split the `localhost:8080` requests
between them. Probing the wildcard collides with the wildcard listener, and
the run is refused instead.

Two of those keys have no flag beside them, because what they decide is what
the server *is* rather than how one run of it went. `capture = false` is the
**viewer posture**: the guide is served, read, searched, and drafted against,
and a submitted form is refused - which is the shape of a reference server, or
of a second copy run for reading while one capturing server does the
collecting. Nothing about the receipts already on disk changes: they are still
read back at the addresses their senders were given, still searched, still
counted by `GET /spool`, and still drained by
[`d2w fhir forward`](201-forward.md). `spool_dir` says which folder those
receipts live in, and the forwarder reads the same key - so moving the folder
moves it for both halves of the loop at once.

A live run has one more table to state: `[serve.tracked_entities]`, which decides
whether this server answers about people at all, whether the listing is offered
beside the identifier search, how large a page is, and which tracked entity
types and which attributes the two surfaces work over. Every default there is
"offer it", so a project writes the table when it wants less - and a live server
on an instance holding real records is exactly the case for wanting less.

A second live-only table says how a lookup is answered rather than what may be
looked up: `[serve.search]`. Its one key, `backend`, names what a register
search runs through, and `"dhis2"` - the default, and what a project that writes
no table gets - is the DHIS2 instance itself, asked one exact-match query per
search key while somebody waits. The reason the key exists before there is a
second value for it is the shape it forces: a search answers with tracked entity
identifiers, and the record behind a match is then read back live, under the
credentials the request runs as, so DHIS2 authorizes every record this server
hands out whatever found it. A search index can therefore sit behind that key
without this server deciding on the instance's behalf who may see whom. `"index"`
arrives with the OpenSearch backend and is refused until then, naming the key it
was refused at.

The table has one more setting, `basemaps` - the raster tile layers the
capture UI's organisation-unit map offers under the boundaries. The screens'
layer control lists them, opens on the first, and always carries a **None**
entry beside them; `basemaps = []` offers None alone, which is the posture of
a deployment that must reach no origin but this server. Every `[serve]` key,
the basemap policy included, is covered in
[Configure serving](301-serving.md).

## Who the facade serves

`[serve] auth` is the posture, and there are four:

| Posture | What a caller presents | Where the answer comes from |
| --- | --- | --- |
| `none` | Nothing | Every caller is served. The default. |
| `token` | `Authorization: Bearer <token>` | The values of `D2W_FHIR_SERVE_TOKENS`, compared in constant time. |
| `dhis2` | The DHIS2 credentials they would sign in to the instance with | One `GET /api/me` against that instance, as them - and every register read goes to it as them too. Needs `--live`. |
| `jwt` | `Authorization: Bearer <token>`, from an OpenID Connect issuer | The signing keys that issuer publishes, read once at startup and checked in memory on every request. |

They are a ladder rather than a menu, and each rung is the one below it with one
more thing known about the caller. `none` knows nothing. `token` knows the caller
holds a secret this deployment handed out. `dhis2` knows the caller is a
particular DHIS2 user, because DHIS2 said so. `jwt` knows the caller is a
particular person at an identity provider, because that provider signed for it.
Climbing a rung is editing `fhir.toml` and restarting - never porting anything.

`[serve] auth_scope` says how much of the surface the posture covers. `write` -
the default - asks for credentials on `POST /QuestionnaireResponse`, which is
the one address this facade changes anything at, and leaves every read, both
operations, `/metadata`, and the capture UI open. `all` asks for them
everywhere except `/metadata`, which stays open in every posture because a
client has to be able to read how to authenticate to a server before it can.

Every posture declares itself. `GET /metadata` carries `rest.security` whether
this server authenticates everybody, somebody, or nobody - so a client reads
what it must present rather than discovering it from a refusal, and the `none`
posture says in words that it serves every caller.

### Checking a credential without spending one

Wherever a posture is configured, `GET /whoami` names whoever is calling:

```console
$ curl -su clerk:the-right-password http://127.0.0.1:8080/whoami
{"posture":"dhis2","username":"clerk","name":"clerk"}
```

It carries the authentication check under **both** scopes, so it gives a verdict
on a credential without doing anything with it - which under `write`, where every
read is open, is otherwise only discoverable by making a submission. Wrong
credentials answer 401 with the same OperationOutcome every other refusal on this
facade carries. `username` is the DHIS2 username under `dhis2`, the claim
`[serve.jwt] username_claim` names under `jwt` - the same value a receipt is
stamped with - and null under `token`, which names a deployment rather than a
person. Under `auth = "none"` the address answers 404 saying this server
authenticates nobody, so it names nobody, and that `/whoami` answers a caller only
where `[serve] auth` states a posture. It is what the capture UI's sign-in panel
asks before it holds on to anything.

### The DHIS2 posture's 401 names `xBasic`

The refusal a `dhis2`-posture facade gives carries
`WWW-Authenticate: xBasic realm="d2w fhir serve", charset="UTF-8"`, not `Basic`.
A browser that meets `Basic` on a request a page made opens its own credential
dialog and never hands the response back, so a capture screen's Submit sits
pending forever instead of rendering the refusal the server sent it. The scheme
callers **send** is untouched - HTTP Basic, or `Authorization: ApiToken <token>`
- and a command-line client reads the status and the OperationOutcome exactly as
it always did. The header says the same thing to every caller rather than
changing shape depending on which ones look like browsers.

### An absent key binds loopback and nothing else

A project that has never written `auth` is served on loopback and refused
anywhere else:

```
error: `0.0.0.0` is not a loopback interface, and this project's fhir.toml states no
[serve] auth. Write the posture down before serving the facade where other hosts can
reach it - add one line under [serve] in fhir.toml: auth = "none" to serve every caller,
auth = "token" to take a static bearer token out of D2W_FHIR_SERVE_TOKENS, or
auth = "dhis2" to have every caller present the DHIS2 credentials this facade checks
against the instance. --auth states the same thing for one run.
```

`auth = "none"` written out passes that check, and the difference between the
two is the whole point: an absent key is nobody's decision, and a written one
is somebody's. The refusal comes before the socket opens, so it is a line in a
terminal rather than an endpoint the world reached.

### `token`: one shared secret, out of the environment

```bash
export D2W_FHIR_SERVE_TOKENS='a-long-random-value,another-for-the-second-client'
d2w fhir serve --auth token
```

Comma-separated, and never in `fhir.toml` - that file is committed. Rotating
is replacing the variable and restarting the process; the tokens are read once
and a running server holds what it started with. The posture names no person,
so a receipt captured under it records no submitter. A server started with the
variable unset is refused rather than left promising to accept tokens it does
not hold.

### `dhis2`: the caller's own DHIS2 credentials

```bash
d2w fhir serve --live --auth dhis2
```

A caller sends what they would send DHIS2 - a username and password as HTTP
Basic, or a DHIS2 personal access token as `Authorization: ApiToken <token>` -
and this facade checks it with one `GET /api/me` against the same instance the
live run reads, in a request carrying **their** header and never the server's
own. The username DHIS2 answers with becomes the request identity, and the
capture route records it on the receipt. An answer is reused for about a
minute, keyed by a hash of the header, so a page of requests costs one round
trip rather than one each.

The posture needs an instance, so it is refused on a compiled run, which has
none. What that credential then buys is the next section: the register is read
as you, not as the server.

```bash
curl -u clerk:secret -X POST http://127.0.0.1:8390/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @response.json
```

### Attribution is facade-side provenance

Under `dhis2`, the receipt carries `submitted_by` - the DHIS2 username this
facade validated the submission under. `d2w fhir spool --details` shows it as
a **Captured by** column when any receipt has one, and the forward report
carries it through.

**That is who handed the submission over, and not who wrote the data.**
`d2w fhir forward` posts as the forwarding profile, and `storedBy` on the
instance is DHIS2's own stamp of that profile. The receipt is where "who
captured this" is answered; the instance is where "who wrote this" is.

### Under `dhis2`, the register is read as you

Authenticating a caller says who is asking. It says nothing, on its own, about
what they may see - and a facade that checked every caller and then read the
instance as its own profile would hand each of them that profile's rights.

So under `dhis2`, every register read carries **your** `Authorization` header to
the instance, exactly as it arrived:

| Read | Answered as |
| --- | --- |
| `GET /Patient/{uid}` and every other registered type | The caller |
| `GET /Patient?identifier=...` | The caller |
| `GET /Patient` (the register listing, and its `_count=0` total) | The caller |
| `GET /tracked-entities/{uid}/enrollments` | The caller |
| `GET /tracked-entities/{uid}/events` (the record, and one event of it) | The caller |
| `GET /Patient/{uid}/$summary` and `GET /Patient/$summary?identifier=` | The caller |
| `POST /evaluate` and `POST /$evaluate` with a `registered` context | The caller |
| The store built at startup | The facade's profile |
| The instance address `/uiconfig` hands the screens | The facade's profile |
| `d2w fhir forward`'s drain | The forwarding profile |

DHIS2 then applies its own five gates - authority, sharing, the data element
bits, the organisation unit scopes, and ownership with access levels - to the
person who actually asked, and this facade applies no rule of its own. **What
DHIS2 hides stays hidden as DHIS2 hides it**: a tracked entity you may not see
answers 404 here because it answers 404 there, and no verdict is invented that
the instance never gave.

The credential is never parsed, never logged, and never held past the request.
Nothing on this path is cached - one caller's page is never another caller's
page - and the only thing the facade does remember for about a minute is the
username `/api/me` gave, keyed by a hash of the header. Each forwarded read
carries one header of the facade's own, `X-DHIS2W-Facade`, naming the software
and version it arrived through; that is provenance for whoever reads the DHIS2
access log, and it is deliberately not your username, which your own header
already carries.

Two consequences worth stating plainly:

- A register read with no credential is a 401, even under
  `auth_scope = "write"`, which leaves reads unguarded otherwise. There is
  nobody to answer as, and answering as the facade is the read this posture
  exists to prevent. A read that *does* carry credentials is answered in either
  scope.
- **The facade's own DHIS2 profile still wants least privilege.** The three
  bottom rows of that table run as it in every posture, and under `none` and
  `token` it answers every caller besides. DHIS2 skips its tracker ownership and
  access-level model outright for a superuser and writes no break-the-glass
  audit entry when it does, so a facade running as an administrator reads past
  sharing, ownership, and access levels with nothing in the audit trail to say
  so. Give it a least-privilege user, never an administrator.

`GET /metadata` says all of this to a client: `rest.security.description` under
`dhis2` states that reads of the register are answered under the caller's own
DHIS2 authorization.

### `jwt`: a token from the identity provider you already run

This is the posture for a ministry that already has an identity provider. The
clerks, the analysts, and the partner systems already sign in to it for
everything else; `auth = "jwt"` is this facade taking that answer instead of
asking the same question a second time. **It needs no new infrastructure at all** -
no authorization server here, no client secret here, no token minted here.

```toml
[serve]
host = "0.0.0.0"
auth = "jwt"

[serve.jwt]
issuer = "https://idp.example.org/realms/health"
audience = "d2w-fhir-serve"
username_claim = "preferred_username"
```

```bash
d2w fhir serve
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/Questionnaire
```

While the server starts it reads
`https://idp.example.org/realms/health/.well-known/openid-configuration`, takes
the `jwks_uri` from it, and reads the keys published there. **An issuer this
machine cannot reach refuses the run**, in one line, before the socket opens: a
posture that could not be honoured is not one to discover on a caller's behalf.

Every request after that is checked in memory, against those keys, with no round
trip to anybody:

| Checked | What holds |
| --- | --- |
| Signature | One of the keys the issuer publishes, selected by the token's `kid`. RSA and ECDSA only - never a shared-secret algorithm, which on a public key is the algorithm-confusion attack. |
| `iss` | Exactly the issuer `[serve.jwt] issuer` names. |
| `exp` | In the future, with a minute of clock leeway. A token with no `exp` is refused. |
| `nbf` | In the past, where the token states one. |
| `aud` | Contains `[serve.jwt] audience`, when the table states one. Stating none accepts whatever this issuer signed. |
| `[serve.jwt] username_claim` | Present and non-empty. Its value becomes the request identity, and the receipt records it. |

The keys are held for as long as the JWKS response's own `Cache-Control` asks,
never for less than five minutes - an issuer sending `max-age=0` on a document of
public keys would otherwise put itself in the path of every request. **A key
rotation is not an outage**: a token signed under a `kid` this process does not
hold sends it back to the issuer once, and the new keys answer. A `kid` that
never existed costs that issuer one read a minute, however many such tokens
arrive.

The trade this posture makes, stated plainly: **a token revoked before it expires
stays valid here until it expires.** That is what local verification buys, and it
is what every JWKS validator trades. The answer is short token lifetimes at the
issuer.

### Under `jwt`, the register is not read at all unless you say so

A token this facade accepts is not automatically a token *DHIS2* accepts. DHIS2
resolves a foreign issuer's JWT to a DHIS2 user only when the instance was
configured to trust that same issuer -
[`oidc.jwt.token.authentication.enabled`](https://docs.dhis2.org/en/manage/performing-system-administration/dhis-core-version-master/installation.html)
in `dhis.conf` - and whether it was is a fact about the instance that this facade
cannot read and will not guess.

So `[serve.jwt] forward_bearer` states it, and it is **false by default**:

```toml
[serve.jwt]
issuer = "https://idp.example.org/realms/health"
forward_bearer = true       # only when DHIS2 trusts the same issuer
```

- **False.** The register answers 501, with an OperationOutcome naming both
  halves that would make it answerable. The published guide, the received
  responses, `$generate`, `/evaluate`, `$evaluate`, and the terminology reads are
  served exactly as they always were.
- **True.** A register read carries the caller's own `Bearer` header to the
  instance, verbatim, over the same credential-free pool and by the same opaque
  forward the `dhis2` posture uses. DHIS2 resolves the token to one of its users
  and applies its five gates to that person.

**What it never does is fall back to the facade's own profile.** That would
answer every caller with that profile's rights - and DHIS2 skips its ownership
and access-level model outright for a superuser without writing a
break-the-glass audit entry, so an administrator profile would read past
sharing, ownership, and access levels with nothing in the trail to say so. A
loud 501 is the only honest answer to "this caller cannot be authorized here".

`GET /metadata` says which of the two is in force, so a client learns it from the
conformance document rather than from a refusal. The issuer is named there too,
in an extension on `rest.security` - never a key, never the audience, never the
claim name. The issuer is printed inside every token it signs, so stating it
discloses nothing.

`oauth2` is the name reserved for an authorization server this facade would run
itself. It is deliberately not a value `[serve] auth` accepts: DHIS2 2.43.1's
authorization server returns a 500 for any client its API creates (BUGS.md 96),
so a project could state it and nothing would answer. **A deployment that wants
bearer tokens today states `jwt` and names the issuer it already has** - which is
the case that reservation was ever really about.

## Serving with a profile also links the screens back to the instance

`d2w fhir serve` resolves a DHIS2 profile the same way `d2w fhir generate`
does - `d2w -p <name>`, `DHIS2_PROFILE`, then `profile` in `fhir.toml`, then
the default - and it does so whether or not `--live` needs to connect with it.
Reads still come from the compiled guide; what the profile adds to a compiled
run is the instance's **address**, which the capture UI uses to link an
organisation unit, a form, or a data element back to the DHIS2 object it was
generated from ([The capture UI](201-capture-ui.md)).

A machine that names no profile at all is a supported posture, not a broken
one: the run starts, the guide is served, and the screens simply carry no links
out - there is nowhere honest to point a compiled guide that names no instance.
A profile that **is** named and does not exist is a different thing, and it
refuses the run. Which of the two happened is stated at startup when the
screens are being served:

```
starting /home/you/demo-ig on http://127.0.0.1:8390 as a FHIR endpoint + capture UI (ctrl-c to stop)
links: the screens link identities into http://localhost:8080 (local_basic, from fhir.toml)
2026-08-15 20:06:23,044 INFO dhis2w_fhir_serve loaded the compiled IG at /home/you/demo-ig:
2830 resources across 14 types, 0 stored responses
```

Only the address crosses to the browser. The profile's name, its credentials,
and any userinfo written into its base url stay in the process.

A `--live` run says so in the same place, and names what it read:

```
2026-08-15 20:12:26,781 INFO dhis2w_fhir_serve live store: reading http://localhost:8080 as
profile local_basic (from fhir.toml)
2026-08-15 20:12:28,693 INFO dhis2w_fhir_serve loaded live DHIS2 at /home/you/demo-ig:
2757 resources across 7 types, 30 stored responses
```

Seven types against a compiled run's fourteen is the definitional layer
missing: no StructureDefinitions, no profiles, no ImplementationGuide - the
documents only a FSH compile produces. The stored-response count is the spool
on disk, which both modes read the same way.

## Serve from a synced copy { #serve-from-a-synced-copy }

A live run asks the instance every time somebody searches. That is right, it is
current, and it has one shape it cannot get out of: `filter=<attribute>:eq:<value>`
is an exact match, so a clerk gets exactly one chance to spell a value the way it
was stored, and one query goes out per search key per tracked entity type while
they wait.

A **projection** is a durable copy of the mapped scope of the instance, held as
the FHIR resources this project's map publishes. `d2w fhir sync` fills it, and
`[serve.search] backend = "projection"` searches it. Two lines of `fhir.toml` and
one command:

```toml
[serve.projection]
store = "sqlite"

[serve.search]
backend = "projection"
```

```console
$ d2w fhir sync
[1/3] register: 1 tracked entity type(s), 1 program(s), mode initial
[2/3] tracked entities: 502 created, 0 updated, 0 removed over 5 page(s)
[3/3] enrollments: 0 entity(s) re-read from an enrollment that moved
ok: created 502, updated 0, removed 0 over 10 page(s)
ok: answers served from this projection are as of 2026-08-21T16:46:57.099000
```

The first run reads the whole mapped scope. Every run after it reads what moved,
which on an unchanged instance is one request:

```console
$ d2w fhir sync
[2/3] tracked entities: 0 created, 1 updated, 0 removed over 2 page(s)
ok: created 0, updated 1, removed 0 over 4 page(s)
```

`--rebuild` drops the copy and fills it from zero. That is a routine operation
rather than a recovery step: it is how a change to `[serve.tracked_entities]` or
to the published map reaches what is already stored. `--dry-run` reads the
instance exactly as a committing run does, counts what would change, and writes
nothing.

### What the synced copy changes

**A search can find somebody by a value rather than by the whole of one.**
`_content` is R4's own parameter for a text search over a resource's whole
content, and this server answers it only from the projection:

```console
$ curl -sG http://127.0.0.1:8080/Patient --data-urlencode '_content=minata-Ren'
```

It is spelled `_content` and not `name` or `family` on purpose. This server does
not know which of somebody's DHIS2 attribute values is their name, and will not
guess - DHIS2 states no such mapping, and a wrong `family` on a person is a worse
answer than none. So it offers a search across every value they hold, and says
that is what it is doing.

**A search costs one query instead of many.** One read of one local file, however
many search keys and tracked entity types are in scope.

**Every answer says when it was true.** A searchset served from the projection
carries an `outcome` entry stating the instant, and an
`X-DHIS2W-Projection-As-Of` header beside it:

```
x-dhis2w-projection-as-of: 2026-08-21T16:46:57.099000
```

That is the one way a client can tell the two backends apart, and it is
deliberate: an answer out of a copy is *as of* an instant, never *now*, and a
client that cannot tolerate that reads the instance instead.

### What it does not change

**Who may see whom.** The projection says who is on the page; the record behind
each one is read from the instance under the credentials of whoever asked. So
DHIS2 applies its sharing, its organisation-unit scopes, and its ownership rules
to every record this server hands out, per person, per request, exactly as it does
without a projection. A person the copy holds and the instance will not disclose
to this caller is on nobody's page. `GET /Patient/{id}` is a person-level read and
is answered from the instance whatever the search backend says.

That is why a projection-served searchset states **no `total`**. The copy knows
how many rows it holds; that number was counted under the identity `d2w fhir sync`
ran as, and how many of them *you* may see is the instance's to say one read at a
time. A count taken for somebody else is not offered.

**Where the data comes from.** DHIS2 stays the record for everything DHIS2 can
hold. The projection is a copy, `d2w fhir sync` is the only thing that writes it,
and a row that disagrees with the instance is a defect of the sync whose fix is
`--rebuild` rather than an edit. Deleting `.serve/projection.sqlite` is a
supported operation.

**When a capture appears.** A submission still travels spool, then
[`d2w fhir forward`](201-forward.md), then DHIS2, then the next sync - so a
captured value appears in a synced server one sync interval after DHIS2 accepted
it. The receipt is readable from the spool immediately, which is what the spool is
for. There is no write-through, and there will not be one: it would make this copy
a second system of record.

### What it still cannot do

Find `ສົມສັກ` from `Somsack`. Matching across scripts needs transliteration
applied when the index is built, which arrives with a search-engine backend rather
than with this one. A one-character typo finds nothing here too. The full
measurement, and what closes each gap, is in
[the materialized projection](design/projection.md) section 3.3.

Every key is documented in
[Configure serving](301-serving.md#projection).

## Stored responses are receipts

This is the one thing to be clear about before pointing a client at it.

A response the facade accepted is stored as a **receipt**: the submission
exactly as it arrived, stamped with the id it is now served under. Reading
it back through `GET /QuestionnaireResponse/{id}` tells you *what was
submitted*, never what DHIS2 now holds. DHIS2 remains the system of record;
a receipt is evidence of a submission, not a view of data.

That matters because two obvious questions are answered at two addresses:

- *"What did this client send me?"* - the spool, read at
  `GET /QuestionnaireResponse/{id}` and `GET /spool`.
- *"What does DHIS2 hold about this person now?"* - the record, read at
  `GET /tracked-entities/{uid}/events` on a `--live` run: every event of that
  entity's enrollments, in the same shape and under the same profiles, read from
  the instance while you wait. It is scoped to one tracked entity, so it answers
  "this person" and never "this form, this period, this organisation unit" - the
  aggregate half of the read leg is not built.

The two are never mixed. A receipt keeps the id the submission was accepted
under whatever DHIS2 later made of it; a record carries the DHIS2 event UID and
whatever the instance holds under it this second.

Writing a receipt into DHIS2 is a separate, explicit act:
[`d2w fhir forward`](201-forward.md). Until you run it, accepting a capture
means the submission was understood and kept, and nothing has been written
to an instance. The server says so itself, in the OperationOutcome of every
accepted capture and in `/metadata`'s `implementation.description` above.

## Posting a capture

`POST /QuestionnaireResponse` is the only write, and a project can decline to
offer it: `capture = false` refuses every submission and drops `create` from
`/metadata`, leaving every read exactly where it was
([`capture`](301-serving.md#capture)). What follows is a server that receives.

One response per request - a Bundle is refused with a message saying so. The
easiest first capture is
the server's own `$generate` operation posted straight back: ask the server
to fill in one of its own forms, then hand the answer back to it.

```console
$ curl -s 'localhost:8390/Questionnaire/BfMAe6Itzgt/$generate?seed=4242' -o response.json
$ curl -s -X POST localhost:8390/QuestionnaireResponse \
    -H 'Content-Type: application/fhir+json' --data-binary @response.json -D -
HTTP/1.1 201 Created
date: Sat, 15 Aug 2026 18:07:03 GMT
server: uvicorn
location: http://localhost:8390/QuestionnaireResponse/9c0d30598b194aef9e1e1e8f4bab70ec
content-length: 252
content-type: application/fhir+json

{"resourceType":"OperationOutcome","issue":[{"severity":"information","code":"informational","diagnostics":"stored response 9c0d30598b194aef9e1e1e8f4bab70ec; a stored response is the submission as received - a receipt, not a live view of DHIS2 data"}]}
```

`?seed=` is optional and reproducible: the same seed against the same form
draws the same answers, so a submission that misbehaved can be asked for
again.

A refused capture answers with the same resource type, a different severity,
and a FHIRPath `expression` naming where each problem is. Validation runs in
phases so a rejection is readable rather than a wall of consequences - the
phase table and worked refusals are in
[Consume the FHIR API](401-consume-the-fhir-api.md). Warnings never reject:
they record what the server had to interpret or could not check, and they
ride back on the accepted capture's OperationOutcome *and* into the stored
receipt, so the interpretation is discoverable later.

## Coded answers: lenient by default

The generated CodeSystem carries every DHIS2 option twice - the concept code
the contract asks for, plus the other spelling as a `dhis2-id` or
`dhis2-code` property. So a client that sends the DHIS2 UID where the
contract wanted the option code has still named exactly one option,
unambiguously. By default the server resolves it, stores the submission, and
warns:

```
linkId eY5ehpbEsB7: code 'Op1aaaaaaaa' matched option Op1aaaaaaaa by option-uid;
the contract expects concept code 'MALE'
```

`--strict-codes` flips the leniencies into refusals. One dial grades four
things the same way:

| What the dial grades | Lenient (default) | Strict |
| --- | --- | --- |
| a coded answer outside the concept-code spelling | resolved via the DHIS2 UID or code, with a warning | 422 |
| the `D2AttributeOptionCombo` a form declares | missing or drifted is a warning | 422 (DHIS2 would refuse the write with `E8023`) |
| the organisation unit, against the form's published assignment | outside the assignment is a warning | 422 (DHIS2 would refuse with `E1029`) |
| the subject type, against the form's `subjectType` | mismatch is a warning | 422 |

Two things are refused whatever the dial, because they are malformed rather
than drifted: a coding from a different system than the one the form
declares, and a coding with no code at all. The published contract stays
strict either way - leniency is a property of this server's runtime, not of
what the IG asks for.

## The spool on disk

A receipt is a file, and the directory it is in is its state:

```
demo-ig/.serve/responses/received/<id>.json
```

`.serve/responses` is where receipts live unless the project says otherwise;
[`spool_dir`](301-serving.md#spool_dir) moves the whole tree, and the
forwarder follows it there.

Each file holds the response as received plus the receipt metadata around it
- when it was accepted, which form kind it declared, which questionnaire it
answered, and every warning recorded against it. The server holds no index of
any of that: every read re-scans the directory, because
[`d2w fhir forward`](201-forward.md) is a separate process renaming these
files while the server runs, and anything remembered would be stale the
moment the first drain finished.

A write is atomic *and* durable - a temporary file, `fsync`, a rename, then
an `fsync` of the directory - so a reader never sees a half-written receipt
and the `201` a client is answered with is a promise that survives the
machine losing power.

`ls .serve/responses/received | wc -l` is therefore the pending count, with
no extra bookkeeping: the directory *is* the queue
[`d2w fhir forward`](201-forward.md) drains, which is why it is named
`received/` rather than `responses/` - `forwarded/`, `rejected/`, and
`withdrawn/` are its siblings.

`malformed/` is not a state a receipt is in. A file that
no longer reads as a receipt - truncated, hand-edited, half-copied - is moved
there with a `<file>.reason.json` beside it naming what stopped it, and the
read that found it carries on with everything else. One unreadable byte costs
one row rather than the whole listing, and the file is named rather than
skipped: a submission that disappears quietly looks to its sender exactly like
one that never arrived.

`.serve/` is gitignored by the scaffold. A project scaffolded before the
entry existed gains it from `d2w fhir init . --refresh`.

To read receipts back, and to read the queue depth without touching the disk:

```console
$ curl -s localhost:8390/QuestionnaireResponse | jq .total
30
$ curl -s localhost:8390/spool | jq .counts
{
  "received": 0,
  "forwarded": 28,
  "rejected": 1,
  "withdrawn": 0,
  "malformed": 0
}
```

`GET /QuestionnaireResponse` counts every receipt whatever state it is in;
`GET /spool` splits them by directory, which is the envelope the capture UI's
own pages read. The spool search takes `_id` and `questionnaire`; the
definitional types take `_id`, `url`, and `identifier`.

Both reads are paged, with the same two parameters the register listing uses:
`_count` for how many rows a page carries (50 by default, 500 at most) and
`page` for a cursor a client only ever gets from a `next` or `previous` link.
`total` is the whole listing on every page of a walk, and `/spool`'s counts are
the whole spool rather than the page. `_count=0` is the one value the two read
differently: on `GET /QuestionnaireResponse` it is R4's request for the total
alone, answered with a searchset stating how many receipts matched and carrying
none of them, while `/spool` is this server's own envelope listing and refuses
it as a page of no rows.

```console
$ curl -s 'localhost:8390/spool?_count=2' | jq '{total, rows: (.responses | length), next: .next_url}'
{
  "total": 29,
  "rows": 2,
  "next": "http://localhost:8390/spool?_count=2&page=bzJuMjk"
}
```

`d2w fhir spool` answers the same question from the other side, off the
directory alone and with no DHIS2 connection - see
[Forward captures into DHIS2](201-forward.md#reading-the-queue).

## Generating a load set

`d2w fhir generate load-set` writes a synthetic corpus to POST at a running
facade:

```console
$ d2w fhir generate load-set --per-target 2 --salt docs201
running 2 step(s)
[1/2] instance metadata: 14 questionnaire target(s)
[2/2] load set: 28 written, 0 unchanged
$ for response in load/*.json; do
    curl -s -o /dev/null -w '%{http_code}\n' \
      -X POST localhost:8390/QuestionnaireResponse \
      -H 'Content-Type: application/fhir+json' \
      --data-binary "@${response}"
  done | sort | uniq -c
  28 201
```

The corpus is drawn to be instance-valid - every response is captured at a
unit its form's DHIS2 assignment admits, a data set on a non-default
category combo carries its attribute option combo, and a tracker program's
registrations and stage events agree on the identities they mint - so
forwarding it measures what DHIS2 accepts, not refusals already known
about. A corpus imports once, because it mints the DHIS2 identities it
names; `--salt second-run` draws a fresh corpus, and the same salt
reproduces the same corpus. `load/` is not IG source: it sits beside `ig/`,
the scaffold gitignores it, and the IG publisher never renders it.

## What this server is not

- **Not an authorisation server.** `[serve] auth` establishes who is calling;
  it grants nobody more or less of what this facade serves, and on a live run
  the answers are read under the facade's own DHIS2 profile rather than the
  caller's. See [Who the facade serves](#who-the-facade-serves).
- **One process, one project.** No clustering, no shared state. The spool
  assumes a single writing process, which is what `d2w fhir serve` is.
- **No batch and no transaction.** `POST /` is where FHIR posts a Bundle of
  interactions; this facade takes one QuestionnaireResponse per request and
  answers a 405 there saying so.
- **One format.** Every FHIR route answers `application/fhir+json`. A request
  whose `Accept` rules JSON out is answered 406 rather than sent a body it said
  it could not read. R4's `_format=json` overrides the header, so any query is
  a link a browser can open.
- **The store is a snapshot.** Restart to serve regenerated state.
- **The server never writes to DHIS2.** A capture is a receipt and nothing
  more. Writing to the instance is [`d2w fhir forward`](201-forward.md).

Next: [Capture in the browser](201-capture-ui.md) - the same facade with a
UI on it - then [Forward captures into DHIS2](201-forward.md).

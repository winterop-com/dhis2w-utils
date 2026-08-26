# Secure the facade

Every posture this server takes towards a caller is opt-in, and the one it
takes when a project has stated nothing is the narrow one: a facade whose
`fhir.toml` names no `auth` binds loopback, serves this machine, and refuses to
start anywhere else. Opening it up is a decision somebody writes down - one
line of `fhir.toml` and one of four postures answers for every caller after
that, whether that is a shared bearer token, the caller's own DHIS2
credentials, or a token from the identity provider a ministry already runs.

**Who this is for:** the operator putting a served project somewhere other than
their own machine - and anybody who has to state, in writing, who may call it
and what the register answers them.

**Before you start:** a project you can already serve
([Serve the guide](201-serve.md)). The `dhis2` posture also needs `--live` and a
resolvable profile; the `jwt` posture needs an OpenID Connect issuer this
machine can reach while the server starts.

**You will be able to:**

- read the refusal an unwritten `auth` earns, and say why loopback is the floor
- pick one of the four postures and state it once, in `fhir.toml`
- decide how much of the surface the posture covers - `write` or `all`
- check a credential without spending one, at `GET /whoami`
- say precisely who the register is read as under `dhis2` and under `jwt`

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

### Attribution is facade-side provenance

Under `dhis2`, the receipt carries `submitted_by` - the DHIS2 username this
facade validated the submission under. `d2w fhir spool --details` shows it as
a **Captured by** column when any receipt has one, and the forward report
carries it through.

**That is who handed the submission over, and not who wrote the data.**
`d2w fhir forward` posts as the forwarding profile, and `storedBy` on the
instance is DHIS2's own stamp of that profile. The receipt is where "who
captured this" is answered; the instance is where "who wrote this" is.

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

## Checking a credential without spending one

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

## What a posture does not decide

`[serve] auth` establishes who is calling. It is not a permission model of this
facade's own: it grants nobody more or less of the published guide than anybody
else, and what a caller may see of the register is DHIS2's answer about that
person rather than a rule invented here. That, with the other five things this
server deliberately is not, is
[What this server is not](201-serve.md#what-this-server-is-not).

The search backend decides none of it either. `[serve.search] backend =
"projection"` changes how a lookup is answered and what it costs, never who may
see whom - the record behind every match is still read from the instance under
the credentials of whoever asked ([Serve from a synced
copy](201-serve.md#serve-from-a-synced-copy)).

Every `[serve]` key here, `auth` and `auth_scope` and the whole `[serve.jwt]`
table, is documented in full at [Configure serving](301-serving.md). The four
postures run end to end in
[`examples/fhir/cli/serve_auth_postures.sh`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/cli/serve_auth_postures.sh),
and the register read as the caller in
[`examples/fhir/client/read_register_as_yourself.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/fhir/client/read_register_as_yourself.py).

Next: [Forward captures into DHIS2](201-forward.md) - what the facade does
with what it accepted. [Run a secured facade](201-run-a-secured-facade.md) is
where this step sits in the whole path.

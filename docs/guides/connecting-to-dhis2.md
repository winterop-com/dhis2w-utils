# Connecting to DHIS2 — end-to-end

Everything you need to point `dhis2w-utils` at a real DHIS2 instance. Pick an authentication method, follow its section, and you'll have a verified profile you can reuse from the CLI and MCP tools.

## Which auth should I use?

| Method | Best for | Interactivity | Lifecycle | Trust model |
| --- | --- | --- | --- | --- |
| **PAT** | Automation, CI, day-to-day dev | None after first mint | Long-lived, user-revocable | Static token — anyone with it is that user |
| **Basic** | Scripts against dev/play instances | None | Forever until password change | Password hits the wire on every request |
| **OAuth2 / OIDC** | Interactive use, humans-in-the-loop, short-lived access tokens | Browser popup on first login | Access token ~5 min, refresh token auto-rotates | Per-device, per-user, revocable server-side |
| **Session cookie** | Riding an existing browser login when PATs are unavailable | None (cookie captured from the browser) | Dies with the server-side session; re-add on expiry | Anyone with the cookie is that browser session |

**Short version:** start with PAT. Switch to OAuth2/OIDC only when you need interactive login flows or you explicitly need short-lived access tokens with refresh. Use Basic only when you can't avoid it. Session cookies are the fallback when the instance can't mint PATs (pre-2.38, disabled, or 403 for the user).

The code paths are orthogonal — every `AuthProvider` in `dhis2w-client/auth/` implements the same `headers()` / `refresh_if_needed()` Protocol, so the rest of the client is identical regardless of what you pick. See [Pluggable auth](../architecture/auth.md) for the internals.

---

## Option 1 — Personal Access Token (PAT)

### How DHIS2 issues PATs

Every DHIS2 user can mint long-lived PATs on their own profile page (`/dhis-web-user-profile`). Each token is scoped to that user's permissions. You can optionally restrict a token to specific HTTP methods, IP ranges, or referrer URLs. They're revocable one-by-one without affecting the user's password. Under the hood they carry the prefix `d2pat_`.

PATs travel as `Authorization: ApiToken <token>` — not `Bearer`, not `Basic`.

### Minting a PAT

Three paths:

1. **DHIS2 UI.** Log into your instance → profile menu → Personal Access Tokens → Add new. Copy the token immediately (DHIS2 never shows it again).

2. **The seed script (local stack).** `make dhis2-seed` creates six variations bound to `admin` and writes them to `infra/home/credentials/.env.auth`:

    ```bash
    make dhis2-seed
    cat infra/home/credentials/.env.auth | grep DHIS2_PAT
    ```

    See [Local DHIS2 setup § Seeded auth](../local-setup.md#seeded-auth) for what each variation does.

3. **Playwright helper.** `make -C infra pat` drives the DHIS2 UI via Playwright to mint one token against any instance you can log into with username + password. Useful when you want a PAT for a remote server without clicking through the UI manually. See [Playwright PAT helper](../pat-helper.md).

### Adding the PAT as a profile

```bash
# `d2w profile add` has no `--token` flag — secrets must never end up in
# shell history. When DHIS2_PAT is unset, the command prompts silently:
d2w profile add local \
  --url http://localhost:8080 \
  --auth pat \
  --default --verify
# Personal Access Token: ******** (typed silently, doesn't echo)
```

For non-interactive use (a Makefile, CI step, or a bash function), source the secret from an env file that you keep out of git:

```bash
set -a; source ./.env.auth; set +a
d2w profile add local --url http://localhost:8080 --auth pat --default --verify
```

The `--verify` flag probes `/api/system/info` and `/api/me` immediately so you know the token works before saving. `--default` makes this the profile used when no `--profile` is specified. Omit either if you want separate steps.

Or edit `~/.config/dhis2/profiles.toml` directly:

```toml
default = "local"

[profiles.local]
base_url = "http://localhost:8080"
auth = "pat"
token = "d2pat_XXXXX..."
```

### Verifying

```bash
d2w profile verify local
# OK local  http://localhost:8080  auth=pat  version=2.42.4  user=admin  273 ms
```

Re-run any time. `verify` with no argument probes every profile you have.

---

## Option 2 — Basic auth

Only for dev / play instances. DHIS2 accepts HTTP Basic on `/api/*`, so `dhis2w-client` just base64-encodes `user:pass` and attaches it as `Authorization: Basic ...` on every request.

### Adding a basic profile

```bash
# `d2w profile add` only takes `--username` on the command line; the
# password is prompted silently (or read from DHIS2_PASSWORD if set).
d2w profile add play \
  --url https://play.im.dhis2.org/dev \
  --auth basic \
  --username system \
  --verify
# Password: ********
```

Profile shape in `profiles.toml`:

```toml
[profiles.play]
base_url = "https://play.im.dhis2.org/dev"
auth = "basic"
username = "system"
password = "System123"
```

`profiles.toml` is chmod 0600, but the password still sits on disk in plaintext. Treat Basic profiles as disposable.

---

## Option 3 — OAuth2 / OIDC

Interactive browser-based flow with PKCE. DHIS2 mints short-lived JWT access tokens (default TTL 5 min) plus a refresh token (TTL 1 hour). On subsequent API calls `dhis2w-client` reuses the cached access token until it's about to expire, then auto-refreshes without bothering you. If the refresh token itself expires or is revoked, the next call triggers a fresh browser login.

This is the richest option and the one with the most moving parts. It requires **both** server-side configuration (dhis.conf + an OAuth2 client registration + a user column) and client-side configuration (a profile).

### Step 0 — The big picture

DHIS2 v2.42 ships three cooperating pieces that must all be turned on:

1. **Spring Authorization Server** — mounts `/oauth2/authorize`, `/oauth2/token`, `/oauth2/jwks`, `/.well-known/openid-configuration`. This is what mints JWTs.
2. **OIDC-login filter chain** — bridges DHIS2's own login form into Spring AS so `/oauth2/authorize` knows who you are.
3. **JWT Bearer authentication** on `/api/*` — validates incoming `Authorization: Bearer <jwt>` headers, looks the issuer up in a registry, maps the JWT subject to a DHIS2 user, and attaches the right permissions.

Each piece has its own dhis.conf keys, and getting any of them wrong produces a distinct failure mode. The [Troubleshooting](#troubleshooting) table below shows exactly which error points to which missing key.

### Step 1 — Turn on Spring Authorization Server (`dhis.conf`)

Add these to `infra/home/dhis.conf` (or your production dhis.conf) and restart DHIS2:

```properties
# 1. Mount Spring AS endpoints. Without this: GET /oauth2/authorize returns 404.
oauth2.server.enabled = on

# 2. Issuer URL embedded in minted JWTs (the `iss` claim). Must be the URL
# clients actually reach DHIS2 at. Without this: tokens have an empty/wrong
# issuer and the API-side validator rejects them.
server.base.url = http://localhost:8080

# 3. Accept JWT Bearer tokens on /api/*. Without this: API calls with a minted
# access token return 401 even though the token is cryptographically valid.
oidc.jwt.token.authentication.enabled = on

# 4. Wire DHIS2's own login form as the user-authentication front-end of the AS.
# Without this: /oauth2/authorize returns 500 with
#   "No AuthenticationProvider found for OAuth2AuthorizationCodeRequestAuthenticationToken"
oidc.oauth2.login.enabled = on

# 5. Register DHIS2's own AS as a "generic" OIDC provider so the API-side JWT
# validator can find it by issuer. Without this: API calls return
#   401 "Invalid issuer"
# even when the token is fine. All URIs must be spelled out — DHIS2's
# GenericOidcProviderConfigParser does NOT auto-discover them from the issuer.
oidc.provider.dhis2.client_id         = dhis2w-utils-local
oidc.provider.dhis2.client_secret     = dhis2w-utils-local-secret-do-not-use-in-prod
oidc.provider.dhis2.issuer_uri        = http://localhost:8080
oidc.provider.dhis2.authorization_uri = http://localhost:8080/oauth2/authorize
oidc.provider.dhis2.token_uri         = http://localhost:8080/oauth2/token
oidc.provider.dhis2.jwk_uri           = http://localhost:8080/oauth2/jwks
oidc.provider.dhis2.user_info_uri     = http://localhost:8080/userinfo
oidc.provider.dhis2.redirect_url      = http://localhost:8765
oidc.provider.dhis2.scopes            = ALL
oidc.provider.dhis2.mapping_claim     = sub
```

No keystore config is needed — DHIS2 auto-generates one on first start because `oauth2.server.jwt.keystore.generate-if-missing` defaults to `true`.

After saving, restart:

```bash
make dhis2-down
make dhis2-run   # foreground — wait for the DHIS2 log to stabilise, or watch http://localhost:8080/dhis-web-login
```

### Step 2 — Smoke-check that the server is wired up

```bash
# should return 200 with JSON listing issuer + endpoints
curl -s http://localhost:8080/.well-known/openid-configuration | python3 -m json.tool | head

# should 302 -> /dhis-web-login/ (anonymous user redirected to sign in)
curl -sL -o /dev/null -w '%{http_code} -> %{url_effective}\n' \
  -G 'http://localhost:8080/oauth2/authorize' \
  --data-urlencode 'response_type=code' \
  --data-urlencode 'client_id=dhis2w-utils-local' \
  --data-urlencode 'redirect_uri=http://localhost:8765' \
  --data-urlencode 'scope=ALL' \
  --data-urlencode 'state=probe' \
  --data-urlencode 'code_challenge=abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqr' \
  --data-urlencode 'code_challenge_method=S256'
```

If the discovery endpoint 404s or the authorize endpoint 500s, stop and fix dhis.conf before going further — no profile will work until these probes pass.

### Step 3 — Register an OAuth2 client in DHIS2

DHIS2 stores OAuth2 clients under `/api/oAuth2Clients`. Three non-obvious requirements — each was a real 500/401 during bring-up:

- **`clientSecret` must be BCrypt-hashed.** DHIS2 wires a `BCryptPasswordEncoder` into Spring AS's client-authentication filter, so plaintext secrets in the `oauth2_client.client_secret` column always fail `/oauth2/token` with `401 invalid_client`.
- **`clientSettings` and `tokenSettings` must be non-empty Jackson-serialized Spring AS JSON.** Leaving them blank triggers `IllegalArgumentException: settings cannot be empty` inside `Dhis2OAuth2ClientServiceImpl.toObject` when the authorization endpoint tries to rebuild a `RegisteredClient`. The values below match exactly what DHIS2's built-in settings app (`/apps/settings#/oauth2`) writes when you create a client via its UI.
- **Only `ALL` works as a `scopes` value.** DHIS2 has no fine-grained OAuth scopes; Spring AS's `validateScopes` rejects anything that contains whitespace (so `"openid email ALL"` fails), and the server only recognises the single pseudo-scope `ALL`.

The DHIS2 settings app at `/apps/settings#/oauth2` will create a client with working `clientSettings`/`tokenSettings` defaults but **does not expose `scopes` or `clientAuthenticationMethods`**, so a UI-created client cannot complete the end-to-end flow without post-editing. Use the API.

Two paths:

=== "Option A — seed (fastest, local stack only)"

    ```bash
    make dhis2-seed
    cat infra/home/credentials/.env.auth
    ```

    Creates a client named `dhis2w-utils-local` with a deterministic secret, registers it against the running DHIS2, and writes the credentials to `infra/home/credentials/.env.auth`. Internals live in `infra/scripts/_seed_auth_oauth2.py` — inspect that file if you want to see the exact payload before POSTing.

=== "Option B — manual (any DHIS2 instance)"

    Works against any DHIS2 v2.42+ you can log into as a user with "Manage oAuth2 clients" authority (admin has this). No `make` required. The recipe below produces a client equivalent to the seeded one.

    **1. BCrypt-hash the client secret.** One-liner using `uv run` so the `bcrypt` dep is resolved on demand without a permanent install:

    ```bash
    HASHED_SECRET=$(uv run --with bcrypt python -c '
    import bcrypt
    plain = b"CHANGE_ME_TO_A_REAL_SECRET"
    print(bcrypt.hashpw(plain, bcrypt.gensalt(rounds=10)).decode())')
    echo "$HASHED_SECRET"
    # $2b$10$... (60 chars starting with $2b$ or $2a$)
    ```

    Keep the plaintext separately — that's what ends up in your profile's `client_secret` field. DHIS2 only ever sees the hash.

    **2. POST the client to DHIS2.** Paste this into a terminal, replacing `DHIS2_URL`, `ADMIN_USER`, `ADMIN_PASS`, the plaintext inside the `python3 -c`, and `$CLIENT_ID` / redirect URI if you want something other than the defaults:

    ```bash
    DHIS2_URL=http://localhost:8080
    ADMIN_USER=admin
    ADMIN_PASS=district
    CLIENT_ID=my-oauth2-client
    REDIRECT_URI=http://localhost:8765

    curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
      -H 'Content-Type: application/json' \
      -X POST "$DHIS2_URL/api/oAuth2Clients" \
      -d @- <<EOF
    {
      "name": "$CLIENT_ID",
      "clientId": "$CLIENT_ID",
      "clientSecret": "$HASHED_SECRET",
      "clientAuthenticationMethods": "client_secret_basic,client_secret_post",
      "authorizationGrantTypes": "authorization_code,refresh_token",
      "redirectUris": "$REDIRECT_URI",
      "scopes": "ALL",
      "clientSettings": "{\"@class\":\"java.util.Collections\$UnmodifiableMap\",\"settings.client.require-proof-key\":false,\"settings.client.require-authorization-consent\":true}",
      "tokenSettings": "{\"@class\":\"java.util.Collections\$UnmodifiableMap\",\"settings.token.reuse-refresh-tokens\":true,\"settings.token.x509-certificate-bound-access-tokens\":false,\"settings.token.id-token-signature-algorithm\":[\"org.springframework.security.oauth2.jose.jws.SignatureAlgorithm\",\"RS256\"],\"settings.token.access-token-time-to-live\":[\"java.time.Duration\",300.000000000],\"settings.token.access-token-format\":{\"@class\":\"org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat\",\"value\":\"self-contained\"},\"settings.token.refresh-token-time-to-live\":[\"java.time.Duration\",3600.000000000],\"settings.token.authorization-code-time-to-live\":[\"java.time.Duration\",300.000000000],\"settings.token.device-code-time-to-live\":[\"java.time.Duration\",300.000000000]}"
    }
    EOF
    ```

    Expect a JSON response with `"httpStatus":"Created"` and a newly-minted `uid`. Check with:

    ```bash
    curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
      "$DHIS2_URL/api/oAuth2Clients?filter=clientId:eq:$CLIENT_ID&fields=clientId,scopes,authorizationGrantTypes"
    ```

    **3. Update an existing client (PUT).** The same payload works with `PUT /api/oAuth2Clients/<uid>`:

    ```bash
    UID=$(curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
      "$DHIS2_URL/api/oAuth2Clients?filter=clientId:eq:$CLIENT_ID&fields=id" \
      | jq -r '.oAuth2Clients[0].id')

    curl -s -u "$ADMIN_USER:$ADMIN_PASS" \
      -H 'Content-Type: application/json' \
      -X PUT "$DHIS2_URL/api/oAuth2Clients/$UID" \
      -d @- <<EOF
    { ...same payload... }
    EOF
    ```

    The `clientId` field is the unique key — running POST with the same `clientId` twice fails with a uniqueness error, so use PUT once the client exists.

    **4. Also register the same client in `dhis.conf`.** The `oidc.provider.dhis2.*` block from Step 1 references this `clientId` / `clientSecret`. The plaintext goes in `dhis.conf` (DHIS2 uses the plaintext secret at *startup* to build the internal OIDC client registration), while the BCrypt hash lives in the database (DHIS2 uses the hash at *request time* to verify Basic auth on `/oauth2/token`). If you changed `CLIENT_ID` or the plaintext above, update `dhis.conf` to match and restart.

### Step 4 — Wire the admin user's `openId`

DHIS2's JWT validator (`Dhis2JwtAuthenticationManagerResolver$DhisJwtAuthenticationProvider`) takes the value of whichever claim you named in `oidc.provider.dhis2.mapping_claim` (we use `sub`), and looks it up in the `userinfo.openid` column via `UserService.getUserByOpenId`. If the column is empty, the token is rejected with:

```
401 "Found no matching DHIS2 user for the mapping claim: 'sub' with the value: 'admin'"
```

even though the token itself is valid. The fix is to set the `openId` attribute on the DHIS2 user so it matches the JWT subject:

```bash
ADMIN_ID=$(curl -s -u admin:district 'http://localhost:8080/api/me?fields=id' | jq -r '.id')

curl -s -u admin:district -X PATCH "http://localhost:8080/api/users/$ADMIN_ID" \
  -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"add","path":"/openId","value":"admin"}]'
```

`make dhis2-seed` does this automatically for the admin user after upserting the OAuth2 client, so on the local stack you don't need to touch it yourself. See [Appendix: The `openId` user field](#appendix-the-openid-user-field) for why this field exists.

### Step 5 — Add an OAuth2 profile

After the seed has populated `.env.auth`, `--from-env` pulls the client credentials straight in:

```bash
set -a; source infra/home/credentials/.env.auth; set +a
d2w profile add local_oidc --auth oauth2 --from-env --default
```

The expanded form (for non-seeded instances). `d2w profile add` accepts `--client-id`, `--scope`, and `--redirect-uri` on the command line; the client secret is prompted silently (or read from `DHIS2_OAUTH_CLIENT_SECRET` env when set). Same rationale as PAT / Basic: secrets must never end up in shell history.

```bash
d2w profile add local_oidc \
  --url http://localhost:8080 \
  --auth oauth2 \
  --client-id dhis2w-utils-local \
  --scope ALL \
  --redirect-uri http://localhost:8765 \
  --default
# OAuth2 client secret: ********
```

To persist the OAuth2 client config separately (so you can pair it with `--auth oauth2 --from-env`), see `d2w profile oidc-config` — that command has the `--client-secret` flag because its job is exactly to write the client credentials block.

Note: `add` does **not** open a browser. It just writes the profile. Unlike PAT/Basic, where the profile itself is usable as soon as it's saved, OAuth2 needs a separate interactive step to actually obtain an access token.

The profile ends up in `profiles.toml` as:

```toml
default = "local_oidc"

[profiles.local_oidc]
base_url = "http://localhost:8080"
auth = "oauth2"
client_id = "dhis2w-utils-local"
client_secret = "dhis2w-utils-local-secret-do-not-use-in-prod"
scope = "ALL"
redirect_uri = "http://localhost:8765"
```

### Step 6 — Run the interactive login

```bash
d2w profile login local_oidc
```

What happens in order:

1. The CLI runs a preflight `GET /.well-known/openid-configuration` against the profile's `base_url`. If DHIS2 isn't running the AS, you get a clean error pointing at the missing `oauth2.server.enabled` config — no browser opens.
2. It generates a PKCE `code_verifier` / `code_challenge` pair and a CSRF `state` nonce.
3. It starts a FastAPI + uvicorn receiver bound to the `redirect_uri` host:port (default `127.0.0.1:8765`). The receiver is plain HTTP, no WebSockets, and handles exactly one `GET /` request.
4. It opens your default browser to `http://localhost:8080/oauth2/authorize?...` with the PKCE challenge.
5. DHIS2 detects you're anonymous and redirects to its login page (`/dhis-web-login/`). You log in with your DHIS2 credentials — whatever the admin or a real user account is. **This is DHIS2's own form, not anything `dhis2w-utils` ships.**
6. After login DHIS2 returns you to `/oauth2/authorize` with a session cookie, Spring AS mints an authorization code, and redirects your browser back to `http://localhost:8765/?code=...&state=...`.
7. The FastAPI receiver captures the code, validates `state`, and renders a styled "Authentication successful, you can close this tab" page.
8. `dhis2w-client` POSTs the code to `/oauth2/token` with the PKCE verifier to exchange for access + refresh tokens.
9. Tokens are persisted to `~/.config/dhis2/tokens.sqlite` (global scope) or `.dhis2/tokens.sqlite` (project scope) under the key `profile:<name>`.
10. A final verification against `/api/system/info` + `/api/me` prints the authenticated username, version, and latency.

Expected output:

```
opening browser for 'local_oidc' -> http://localhost:8080 ...
  verified: version=2.42.4 user=admin (273 ms)
```

### Step 7 — Verify

```bash
d2w profile verify local_oidc
# OK local_oidc  http://localhost:8080  auth=oauth2  version=2.42.4  user=admin  273 ms
```

`verify` never opens a browser. If the cached access token is still valid it just uses it; if it's near expiry, it silently refreshes. If there are no cached tokens yet (you haven't run `login`), you get a clean error telling you to run `login` first — no surprise browser popup.

---

## Option 4 — Session cookie

The fallback for instances where PAT creation is unavailable: the DHIS2 is older than 2.38, PATs are disabled server-side, or the user's role gets a 403 on `/api/apiToken`. Instead of minting a credential, the profile stores the session cookie of an existing browser login and sends it verbatim as a raw `Cookie` header on every request. The stored value is the full header value, cookie name included (e.g. `JSESSIONID=abc123`), so any cookie name DHIS2 uses works unchanged.

The primary consumer is browser-extension "use my login" flows that bind CLI/MCP tooling to the user's live DHIS2 session, but capturing a cookie by hand from DevTools (Application > Cookies) works the same way.

### Adding a session profile

```bash
# Like every other secret, the cookie never goes on argv. It's read from
# DHIS2_SESSION_COOKIE, or prompted silently when unset:
DHIS2_SESSION_COOKIE="JSESSIONID=abc123" \
  d2w profile add browser --url https://dhis2.example.org --auth session --local
```

Profile shape in `profiles.toml`:

```toml
[profiles.browser]
base_url = "https://dhis2.example.org"
auth = "session"
cookie = "JSESSIONID=abc123"
```

### Lifecycle

The session lives (and dies) server-side; there is nothing to refresh client-side. When the browser session expires or the user logs out, requests start failing — `d2w profile verify browser` is the cheap detector. Re-binding is just re-running the same `profile add` upsert with a fresh cookie.

Note that `profile env` exports `DHIS2_SESSION_COOKIE`, but the raw-env fallback (`DHIS2_URL` + secret, no TOML) handles PAT and Basic only — a session binding always needs the saved profile.

See `examples/v{41,42,43}/cli/profile_session.sh` for the end-to-end flow.

---

## Troubleshooting

Every DHIS2-side failure we hit during OAuth2 bring-up, the error message you'll see, and the knob that fixes it:

| Symptom | Layer | Fix |
| --- | --- | --- |
| `GET /oauth2/authorize` returns **404** | Spring AS not mounted | Add `oauth2.server.enabled = on`, restart |
| `GET /.well-known/openid-configuration` returns **404** | Same as above | Same as above |
| `GET /oauth2/authorize` returns **500** with `scope "..." contains invalid characters` | Client has whitespace in `scopes` | `scopes = "ALL"` in the seed / client, not `"openid email ALL"` |
| `GET /oauth2/authorize` returns **500** with `settings cannot be empty` | Client's `clientSettings` / `tokenSettings` are blank | Populate both with valid Jackson-serialized Spring AS JSON (see seed) |
| `GET /oauth2/authorize` returns **500** with `No AuthenticationProvider found for OAuth2AuthorizationCodeRequestAuthenticationToken` | OIDC login chain not wired to AS | Add `oidc.oauth2.login.enabled = on`, restart |
| `POST /oauth2/token` returns **401** `invalid_client` | Client secret in DB is not BCrypt-hashed | Re-seed with a BCrypt-hashed secret |
| `POST /oauth2/token` returns **400** `invalid_grant` | Authorization code expired (5 min TTL) or already used | Run `d2w profile login <name>` again — it's a one-shot code |
| `GET /api/system/info` returns **401** `Invalid issuer` | No OIDC provider registered for the token's `iss` claim | Add the full `oidc.provider.dhis2.*` block (all URIs required), restart |
| DHIS2 startup log: `OIDC configuration for provider: 'dhis2' contains an invalid property: 'scope', did you mean 'scopes'?` | Typo in dhis.conf | Rename `oidc.provider.dhis2.scope` → `oidc.provider.dhis2.scopes` |
| DHIS2 startup log: `missing a required property: 'user_info_uri'` (or `authorization_uri`, `token_uri`, `jwk_uri`) | Incomplete generic OIDC provider config | Add all seven `oidc.provider.dhis2.*_uri` entries, not just `issuer_uri` |
| `GET /api/system/info` returns **401** `Found no matching DHIS2 user for the mapping claim: 'sub'` | User's `openId` column is empty | PATCH `/api/users/<uid>` to set `openId = <username>`; `make dhis2-seed` does this automatically |
| `d2w profile verify` hangs or browser pops up unexpectedly | Cached tokens are missing | `verify` should never browse — check you're on a current `dhis2w-utils`; otherwise run `login` first |

---

## Appendix: the `openId` user field

DHIS2 has, confusingly, both an **openid** database column on `userinfo` and an OpenID Connect feature. They pre-date each other — the column was there long before OIDC was wired up — but today they meet in the OIDC JWT validator.

When `oidc.jwt.token.authentication.enabled = on`, DHIS2 intercepts every request to `/api/*` that carries an `Authorization: Bearer <jwt>` header and runs it through `Dhis2JwtAuthenticationManagerResolver`:

1. Extract the JWT's `iss` claim.
2. Find the `DhisOidcClientRegistration` whose `issuer_uri` matches — this is what the `oidc.provider.<id>.*` block creates. If none match, reject with `"Invalid issuer"`.
3. Verify the JWT's signature using the registration's JWK set.
4. Pull the claim named by the registration's `mapping_claim` (for us: `sub`). This yields a string — typically the DHIS2 username for self-issued tokens, or an email address for Google/Azure/WSO2 tokens.
5. Call `UserService.getUserByOpenId(<that-string>)` and look up a `userinfo` row whose `openid` column equals it. If none match, reject with `"Found no matching DHIS2 user for the mapping claim"`.
6. Attach that user's permissions to the request and continue.

The `openid` column is essentially a *pointer* from an external identity (whatever your IdP calls a user) to a DHIS2 user. Multiple `userinfo` rows can't share the same `openid` value — there's a btree index on it, and the constraint is enforced at insert time.

For our self-issued-JWT case (`oidc.provider.dhis2`, minting tokens for DHIS2 users against DHIS2 itself), we set `openId = <username>` so the JWT's `sub=admin` maps cleanly to the `admin` user row. For a federated setup (Google as IdP, DHIS2 as OIDC client), you'd set `openId = <user's Google account id>` or `<user's email>` depending on what you put in `mapping_claim`.

### Setting it programmatically

```bash
ADMIN_ID=$(curl -s -u admin:district 'http://localhost:8080/api/me?fields=id' | jq -r '.id')

curl -s -u admin:district -X PATCH "http://localhost:8080/api/users/$ADMIN_ID" \
  -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"add","path":"/openId","value":"admin"}]'
```

Note: the REST API field is named `openId` (camelCase); the database column is `openid` (lowercase). Use the API name in PATCH bodies.

### Setting it via the UI

User profile → Edit details → **OpenID** field. Save. Works for any user.

### Setting it via the seed

`make dhis2-seed` runs `ensure_user_openid_mapping(admin, "admin")` after upserting the OAuth2 client. See `infra/scripts/seed_auth.py`. For other users you need to set `openId` yourself; the seed only handles the admin used to run it.

---

## Related docs

- [Pluggable auth](../architecture/auth.md) — the `AuthProvider` Protocol, `OAuth2Auth` internals, `TokenStore` design.
- [Profiles](../architecture/profiles.md) — how `profiles.toml` is discovered and resolved across scopes.
- [Local DHIS2 setup](../local-setup.md) — running the Docker stack + what `make dhis2-seed` writes.
- [Playwright PAT helper](../pat-helper.md) — minting PATs against any DHIS2 by driving the UI.

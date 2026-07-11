# Pluggable auth

**Looking for a step-by-step setup?** See [Connecting to DHIS2](../guides/connecting-to-dhis2.md) — the end-to-end guide with working commands for Basic, PAT, OAuth2/OIDC, and session cookies. This page covers the *internals*.

`dhis2w-client` has no hardcoded auth. It takes an `AuthProvider` Protocol at construction time and asks it for request headers.

## The Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class AuthProvider(Protocol):
    """Injects authentication headers into outgoing DHIS2 requests."""

    async def headers(self) -> dict[str, str]:
        """Return headers to apply to the next request."""
        ...

    async def refresh_if_needed(self) -> None:
        """Refresh credentials when close to expiry; no-op for static auth."""
        ...
```

That's it. Any class with these two async methods works.

## Shipped providers

### BasicAuth

HTTP Basic: `Authorization: Basic <base64(user:pass)>`. `refresh_if_needed` is a no-op. Good for local dev; **not recommended** for production — use PAT or OAuth2 instead.

```python
from dhis2w_client import BasicAuth
auth = BasicAuth(username="admin", password="district")
```

### PatAuth

DHIS2 Personal Access Token: `Authorization: ApiToken <pat>`. Long-lived and revocable. **Best for automation and CI** — no interactive flow, no token expiry to manage, no client secrets. Tokens are issued by each DHIS2 user on their profile page.

```python
from dhis2w_client import PatAuth
auth = PatAuth(token="d2pat_...")
```

For the profile-based convenience path, `dhis2w_client.build_auth_for_basic(profile)` returns `PatAuth` for `profile.auth == "pat"`, `BasicAuth` for `profile.auth == "basic"`, and `SessionCookieAuth` for `profile.auth == "session"`. It raises `NotImplementedError` on OAuth2 (which needs the token store in `dhis2w-core`). The full `dhis2w_core.client_context.build_auth(profile)` is a strict superset that adds the OAuth2 path.

### SessionCookieAuth

An existing browser session, sent verbatim as a raw `Cookie` header. The `cookie` value holds the full header value, name included (e.g. `"JSESSIONID=abc123"`), so the provider stays cookie-name-agnostic. `refresh_if_needed` is a no-op — the session lives (and dies) server-side; when it expires, store a fresh cookie. **The fallback when PAT creation is unavailable** (pre-2.38 instances, PATs disabled, or 403 for the user) — the primary consumer is browser-extension flows that bind tooling to the user's live DHIS2 login.

```python
from dhis2w_client import SessionCookieAuth
auth = SessionCookieAuth(cookie="JSESSIONID=abc123")
```

### OAuth2Auth

OAuth 2.1 authorization-code flow with PKCE against DHIS2's `/oauth2/authorize` and `/oauth2/token` endpoints. Matches DHIS2 core's `AuthorizationServerConfig.java`. **Preferred for interactive use.**

The flow:

1. The provider generates a PKCE `code_verifier` / `code_challenge` pair and a `state` nonce.
2. It starts an asyncio loopback server on `redirect_uri`'s host:port.
3. It opens the browser at `/oauth2/authorize?...`.
4. The user authenticates in DHIS2 and gets redirected back.
5. The loopback server captures `code` + `state`, validates state (CSRF).
6. The provider exchanges `code` for access + refresh tokens via POST `/oauth2/token`.
7. Tokens are persisted via an injected `TokenStore`.

On subsequent calls:

- If the access token is valid, just use it.
- If it's within 60s of expiry, refresh via `refresh_token` grant.
- If no refresh token exists or refresh fails, re-run the authorization flow.

```python
from dhis2w_client import OAuth2Auth
auth = OAuth2Auth(
    base_url="https://dhis2.example.org",
    client_id="dhis2-utils-local",
    client_secret="...",
    scope="ALL",  # DHIS2 only recognises the single `ALL` scope
    redirect_uri="http://localhost:8765",
    token_store=my_token_store,
    store_key="profile:prod",  # distinguishes tokens across profiles
)
```

### TokenStore

`OAuth2Auth` never touches the filesystem or keyring directly. Instead, it takes a `TokenStore` Protocol:

```python
class TokenStore(Protocol):
    async def get(self, key: str) -> OAuth2Token | None: ...
    async def set(self, key: str, token: OAuth2Token) -> None: ...
```

`dhis2w-core` provides a SQLAlchemy+SQLite implementation backed by `.dhis2/tokens.sqlite`. A future keyring-backed implementation can be swapped in without touching `OAuth2Auth`.

## DHIS2 server prerequisites (v2.42)

DHIS2 ships its own Spring Authorization Server, but none of it is turned on by default. Without the right `dhis.conf` keys, `d2w profile login` will fail in one of three distinct ways depending on which layer is missing. Getting OAuth2 working against a local DHIS2 means adding **all** of these to `dhis.conf` and restarting the instance:

```properties
# 1. Mount Spring AS endpoints (/oauth2/authorize, /oauth2/token, /oauth2/jwks,
# /.well-known/openid-configuration). Without this: 404 on /oauth2/authorize.
oauth2.server.enabled = on

# 2. Issuer URL baked into minted JWTs (`iss` claim). Must be the URL clients
# reach DHIS2 at. Without this: tokens are minted with an empty/wrong issuer
# and the API rejects them.
server.base.url = http://localhost:8080

# 3. Accept JWT Bearer tokens at /api/*. Without this: every /api call with a
# minted access-token returns 401 even when the token is valid.
oidc.jwt.token.authentication.enabled = on

# 4. Wire DHIS2's login form as the user-authenticating front-end of the AS.
# Without this: /oauth2/authorize returns 500 "No AuthenticationProvider found"
# because Spring AS has no provider that knows how to prompt for a user session.
oidc.oauth2.login.enabled = on

# 5. Register DHIS2's own AS as a "generic" OIDC provider so the API-side JWT
# validator can find it by issuer. Without this: authorized API calls fail with
# 401 "Invalid issuer" even though the token is cryptographically valid.
# All URIs must be spelled out — DHIS2's GenericOidcProviderConfigParser rejects
# registrations missing any of authorization_uri / token_uri / jwk_uri, it does
# not auto-discover them from the issuer.
oidc.provider.dhis2.client_id         = dhis2-utils-local
oidc.provider.dhis2.client_secret     = dhis2-utils-local-secret-do-not-use-in-prod
oidc.provider.dhis2.issuer_uri        = http://localhost:8080
oidc.provider.dhis2.authorization_uri = http://localhost:8080/oauth2/authorize
oidc.provider.dhis2.token_uri         = http://localhost:8080/oauth2/token
oidc.provider.dhis2.jwk_uri           = http://localhost:8080/oauth2/jwks
oidc.provider.dhis2.user_info_uri     = http://localhost:8080/userinfo
oidc.provider.dhis2.redirect_url      = http://localhost:8765
oidc.provider.dhis2.scopes            = ALL
oidc.provider.dhis2.mapping_claim     = sub
```

The `dhis.conf` keys are additive — you can leave them on even when not using OAuth2. PAT and Basic auth continue to work unchanged.

Two subtleties in the registered OAuth2 client itself (seeded by `make dhis2-seed`):

- **`clientSecret` must be BCrypt-hashed.** DHIS2 wires a `BCryptPasswordEncoder` into Spring AS's client auth filter, so plaintext secrets in the DB always fail `/oauth2/token` with 401 `invalid_client`. The seed script hashes the plaintext before POSTing to `/api/oAuth2Clients`.
- **`clientSettings` and `tokenSettings` must be non-empty Jackson-serialized Spring AS JSON.** Leaving them blank triggers `IllegalArgumentException: settings cannot be empty` inside `Dhis2OAuth2ClientServiceImpl.toObject` on `/oauth2/authorize`. The seed script sends the same defaults DHIS2's built-in settings app writes when a client is created via `/apps/settings#/oauth2`.
- **Only `ALL` works as a scope.** DHIS2 has no fine-grained OAuth scopes; the seed uses `scopes = "ALL"` and the client's default `--scope` flag is `ALL`.

The `d2w profile login` CLI preflights the server with a `GET /.well-known/openid-configuration` before opening a browser, so a misconfigured instance produces the message *"DHIS2 at ... does not expose OAuth2/OIDC endpoints — set `oauth2.server.enabled = on` in dhis.conf and restart"* rather than a cryptic mid-flow failure.

### `--no-browser` / `DHIS2_OAUTH_NO_BROWSER`

Pass `--no-browser` (or set `DHIS2_OAUTH_NO_BROWSER=1`) to skip `webbrowser.open()` and print the authorization URL to stderr for copy-paste:

```
$ d2w profile login local_oidc --no-browser
starting OAuth2 login for 'local_oidc' -> http://localhost:8080 (no-browser mode) ...

Open this URL in a browser to authenticate:

  http://localhost:8080/oauth2/authorize?client_id=...&response_type=code&...

Waiting for redirect to http://localhost:8765 ...
```

Useful when:

- You're on SSH / WSL / Remote Desktop and the default browser is either unset or points at the wrong machine.
- You want to log in with a specific browser (or profile) other than the system default.
- A Playwright harness drives the IdP login — read the URL from stderr, navigate its own Chromium there, and the local loopback receiver on `redirect_uri` closes the loop normally.

The flag plumbs through `build_auth(..., open_browser=False)` in `dhis2w_core.client_context`; library callers bypassing the profile plugin can set `OAuth2Auth(open_browser=False)` or pass the equivalent through their own `redirect_capturer` to `dhis2w_core.oauth2_redirect.capture_code(..., open_browser=False)`.

### Playwright-driven login

`dhis2w_browser` ships two helpers for automating the full flow:

- `drive_oauth2_login(profile_name, *, username, password)` — subprocess-driven. Spawns `d2w profile login <name> --no-browser`, reads the auth URL from its stderr, and drives Chromium through (1) the DHIS2 React login form, (2) the Spring AS "Consent required" screen, (3) the loopback redirect. Used by `examples/v42/client/oidc_playwright_login.py` + the `DHIS2_USERNAME`/`DHIS2_PASSWORD`-auto-dispatched `examples/v42/cli/profile_oidc_login.sh`.
- `drive_login_form(auth_url, *, username, password)` — lower-level. Takes an authorize URL that an in-process flow already built and drives the same two screens. Used by `examples/v42/client/oidc_login.py`'s library-level `OAuth2Auth` path when `DHIS2_USERNAME`/`DHIS2_PASSWORD` are set.

Both accept `headless=None` which honours the `DHIS2_HEADFUL=1` env fallback (matching every other `dhis2w-browser` helper). Both require the `[browser]` extra (`uv add 'dhis2w-cli[browser]' && playwright install chromium`).

### "Local OIDC" button on the login page is CLI-only

DHIS2's login page renders a button for every configured OIDC provider. With the committed fixture, that's the `d2w` provider above, labelled `Local OIDC` via `oidc.provider.dhis2.display_alias`. The button **fails when clicked from a browser** because its `redirect_url` is `http://localhost:8765` — our CLI's ephemeral callback listener, not a long-running HTTP server. Browser users should log in with username + password directly; the OIDC button exists purely so the CLI OAuth2 flow (`d2w profile login local_oidc`) has a live provider to round-trip against.

Removing the button is not possible without removing the provider entirely (DHIS2 v42 has no per-provider "hide from login UI" flag), and removing the provider would break the CLI OAuth2 integration path.

## Design choices

- **No sync mirror.** Every provider is async-only. Callers running in notebooks can do `asyncio.run(auth.headers())` if needed; matching our async-first client.
- **TokenStore is injected, not discovered.** Keeps `dhis2w-client` free of filesystem/OS concerns. All "where do tokens live" decisions live in `dhis2w-core`.
- **OAuth2 loopback server is `asyncio.start_server`, not `http.server` on a thread.** Native async, no thread pool, cleaner teardown, no concurrent-request surprise. One HTTP request, server closes.
- **PKCE is mandatory.** Even with a confidential client. OAuth 2.1 recommends it, DHIS2 accepts it, and we have no reason to support the pre-PKCE flow.
- **`store_key` defaults to `f"{base_url}:{client_id}"`** but can be overridden. Profiles override it to `f"profile:{name}"` so tokens don't collide across instances.

## Future providers

All future providers land in `dhis2w-client/auth/`. No changes to `client.py` needed.

- `ServiceAccountJwtAuth` — signed-JWT client-credentials grant, for unattended backends.
- `StaticBearerAuth` — pre-minted access token, dev/testing.
- `HeaderInjectorAuth` — sitting behind an auth proxy that already sets `Authorization`.
- `KeyringOAuth2Auth` — swap the `TokenStore` for an OS keyring-backed one.

The PyPI-track for `dhis2w-client` means downstream users can also ship their own `AuthProvider` without forking us.

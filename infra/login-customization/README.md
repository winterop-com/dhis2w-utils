# Login customization — committed preset

Branding applied to every freshly-built DHIS2 fixture so `make dhis2-run`
on a clean clone shows a dhis2w-utils-flavoured login page + authenticated
top menu. The seed calls `Dhis2Client.customize.apply_preset(...)` during
the build, so the committed fixture dump already carries these settings
— no post-start step needed.

| File | What it does |
| --- | --- |
| `logo_front.png` | 64×64 peach "d2" monogram uploaded via `POST /api/staticContent/logo_front`. DHIS2's login app renders it both in the upper-right slot (at native 64×64) and as the OIDC button icon (scaled to 24×24). The square shape stays legible at both sizes. |
| `logo_banner.png` | 300×60 peach "dhis2w-utils" wordmark uploaded via `POST /api/staticContent/logo_banner`. Shown in the top-menu slot on every authenticated page. |
| `preset.json` | System-setting overrides (`applicationTitle`, `keyApplicationIntro`, `keyApplicationNotification`, `keyApplicationFooter`, plus the `keyUseCustomLogo*` flags DHIS2 requires to actually serve the uploaded bytes). |

## "Local OIDC" button — CLI-only, don't click it from a browser

The `Local OIDC` button on the login page exists so the CLI OAuth2 flow
(`dhis2 profile login local_oidc`) has a live end-to-end provider to
authenticate against. Its `redirect_url` in `infra/home/dhis.conf` is
`http://localhost:8765` — the ephemeral localhost listener our CLI spins
up for the `/oauth2/authorize` callback.

Clicking the button in a browser will **fail** — DHIS2 will complete the
auth handshake and redirect to `http://localhost:8765/?code=...`, but
nothing is listening there unless the CLI is actively running the flow.

DHIS2 v42's login app renders a button for every configured OIDC
provider with no per-provider "hide from login UI" flag. Removing the
provider config would silence the button but break the CLI's OAuth2
integration tests. Log in with username + password for a regular
interactive session.

## Known upstream layout quirk (not caused by this preset)

DHIS2's login-app bundled CSS leaves `html` transparent and sets
`.app { height: 100vh }`. At any browser zoom >100% or on tall windows,
the browser's native background shows through below the footer. This is
upstream — `POST /api/files/style` only affects post-auth pages; we
can't fix it without a full `loginPageTemplate` takeover. See BUGS.md
entry 12.

## Regenerating the logos

```bash
uv run python infra/scripts/generate_login_logo.py
```

PIL-based generator. Edit the script to tweak palette / font / size.

## Customizing a DHIS2 instance yourself

The `dhis2 dev customize` plugin exposes the same surface from the CLI:

```bash
# Apply everything in a preset directory:
dhis2 dev customize apply infra/login-customization/

# Or one piece at a time:
dhis2 dev customize logo-front  path/to/logo.png
dhis2 dev customize logo-banner path/to/banner.png
dhis2 dev customize style       path/to/theme.css
dhis2 dev customize set         applicationTitle "My DHIS2"
dhis2 dev customize show
```

See `docs/architecture/customize-plugin.md` for the full surface.

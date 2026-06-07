# Customize plugin — DHIS2 branding + theming

The `customize` plugin is a thin, typed surface over DHIS2's three branding
endpoint families. One `dhis2 customize apply DIR` re-brands an instance;
the same library call (`Dhis2Client.customize`) lets Python code do it
programmatically; the same MCP tool set lets an agent do it.

## Surfaces

| Layer | Entry point | Where |
| --- | --- | --- |
| Library | `Dhis2Client.customize` | `packages/dhis2w-client/src/dhis2w_client/customize.py` |
| CLI | `dhis2 customize …` | `packages/dhis2w-core/src/dhis2w_core/v42/plugins/customize/cli.py` |
| MCP | `customize_*` tools | `packages/dhis2w-core/src/dhis2w_core/v42/plugins/customize/mcp.py` |
| Committed preset | `infra/login-customization/` | Applied by the seed in `infra/scripts/build_e2e_dump.py` |

## DHIS2 endpoint mapping

| What you call | What DHIS2 receives | What it affects |
| --- | --- | --- |
| `upload_logo_front(bytes)` | `POST /api/staticContent/logo_front` + `POST /api/systemSettings/keyUseCustomLogoFront=true` | Login-page upper-right slot + OIDC button icon (scaled to 24×24). |
| `upload_logo_banner(bytes)` | `POST /api/staticContent/logo_banner` + `POST /api/systemSettings/keyUseCustomLogoBanner=true` | Top-menu banner on every authenticated page. |
| `upload_style(css)` | `POST /api/files/style` + `POST /api/systemSettings/keyStyle=style` | CSS served on authenticated pages only — the login app (`/dhis-web-login/`) ignores it. |
| `set_system_setting(key, value)` | `POST /api/systemSettings/<key>` | Any single setting. |
| `apply_preset(LoginCustomization)` | All of the above, in order | One declarative call. |
| `get_login_config()` | `GET /api/loginConfig` | Read-only snapshot of what the login app renders. |

## Why DHIS2 needs the `keyUseCustomLogo*` flag

A plain `POST /api/staticContent/logo_front` writes bytes to disk but leaves
`keyUseCustomLogoFront=false`. GETs then redirect to DHIS2's built-in default,
so the upload appears to have had no effect. The accessor auto-flips the flag
so the uploaded bytes actually render (tracked as BUGS.md entry 11).

## Why `applicationTitle` isn't prefixed but the others are

DHIS2's system-setting keys are inconsistent — `applicationTitle` is
unprefixed, while the four closely related login-page strings are
`keyApplication{Intro,Notification,Footer,RightFooter}`. `/api/loginConfig`
advertises them under yet a third naming scheme (`applicationDescription`,
`applicationLeftSideFooter`, …). Tracked as BUGS.md entry 10. The preset
ships the correct wire-key names so callers never have to discover the map.

## Applying the committed preset

The directory at `infra/login-customization/` is the source of truth:

```
infra/login-customization/
├── README.md      — documents what gets applied (and what we deliberately skip)
└── preset.json    — {applicationTitle, keyApplicationIntro,
                      keyApplicationNotification, keyApplicationFooter}
```

The seed ships text-only branding — no committed logos, no CSS — because
the DHIS2 login app has enough layout quirks around logos (one asset
renders in two incompatible slots, no `html { background }` under zoom,
...) that a half-applied restyle looks worse than the default. The plugin
still supports logos + CSS; any user can drop them in their own preset
directory and `dhis2 customize apply DIR` will upload them.

The seed calls `Dhis2Client.customize.apply_preset(...)` at the end of the
build so the committed fixture dump (`infra/v42/dump.sql.gz`) already carries
the branding. On `make dhis2-run` the DB restore includes it; the login page
shows it immediately.

From the CLI, one call re-applies the preset against a live instance:

```bash
dhis2 customize apply infra/login-customization/
dhis2 customize show   # read back /api/loginConfig to verify
```

## Known visual quirk — black band below the footer at non-100% zoom

The login-app's inline CSS sets `body { background: #2a5298 }` and
`.app { height: 100vh }` but leaves `html` transparent. When the browser's
rendered viewport is taller than CSS `100vh` — which happens at any zoom
level >100%, or on some HiDPI tall windows — the blue `.app` only fills
`100vh` and the html transparent backdrop shows the browser's default
color below the footer (dark grey / black in dark-themed Chrome, white
elsewhere).

This is a DHIS2 upstream bug (BUGS.md entry 12). We can't fix it from the
customize surface: `POST /api/files/style` doesn't affect the login app,
and a full `loginPageTemplate` takeover is out of scope here. DHIS2 needs
one line in the login-app's bundled CSS: `html { background: #2a5298; }`.

## Why the committed preset is text-only

DHIS2's login page has two layout constraints that make custom logos +
CSS a bad default:

1. **`logo_front` is reused in two slots** — the 200×80+ upper-right slot
   and the 24×24 OIDC button icon. Wordmarks clip in the corner; square
   monograms stay legible at both sizes but make the upper-right slot
   look randomly placed. No single asset design satisfies both.
2. **The login app's bundled CSS leaves `html` transparent** — see BUGS.md
   entry 12. At any zoom >100% or on a tall window, the browser's native
   background shows below the footer.

Neither is fixable from the `/api/staticContent` / `/api/files/style` /
`/api/systemSettings` surface. So the default preset ships only the
safe-to-override text strings; anyone who wants branded logos drops them
in their own preset directory.

## Why no `style.css` in the preset

The login app at `/dhis-web-login/` is a standalone React bundle with its
own CSS imports. It doesn't include `/api/files/style`, so any CSS we'd
upload only restyles the post-auth UI. Keeping the login page stock
(DHIS2's blue/white look) is cleaner than half-applied theming. If you do
want to restyle authenticated pages, drop a `style.css` in the preset
directory and `dhis2 customize apply` will pick it up; to fully restyle
the login page itself, use DHIS2's `loginPageTemplate` system setting
(full HTML takeover, out of scope here).

## Roadmap — larger file-upload surfaces

DHIS2 has two other file-upload surfaces that this plugin deliberately
does not cover:

- `/api/documents` — user-uploaded attachments (content management, not branding).
- `/api/fileResources` — typed files attached to metadata / data capture (data-element images, event photos).

Both are different problem domains — this plugin is purely about visual
identity at brand-touchpoints. When + if the workspace grows a
document-management or data-capture-media story, a separate plugin fits
better than overloading this one.

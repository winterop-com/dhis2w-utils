# Customize — branding + theming accessor

Thin wrapper over DHIS2's three branding endpoint families — `/api/staticContent/*`,
`/api/files/style`, `/api/systemSettings/*` — plus a declarative
`LoginCustomization` preset for bulk apply. Accessed via
`Dhis2Client.customize`.

See also:
- Architecture walkthrough: [Customize plugin](../architecture/customize-plugin.md)
- Committed preset: `infra/login-customization/`
- CLI surface: `d2w customize` (under [Plugins](../architecture/plugins.md))

::: dhis2w_client.v42.customize

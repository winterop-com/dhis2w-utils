"""Root pytest configuration: the environment every package's tests run under.

The colour-forcing variables are cleared at import rather than from a fixture. `cli_output`
builds its `Console` at module scope, so the setting is captured the moment a test module
imports the CLI - earlier than any fixture runs. pytest imports this file before it imports
test modules, which is the only point early enough to matter.

The profile-resolution variables are cleared from a fixture rather than at import, because
they are set *after* this file is imported: pytest imports the root conftest first and the
per-package ones second, and a developer's own shell can export them too. Only a per-test
reset catches both.
"""

from __future__ import annotations

import os

import pytest

#: Variables that force Rich to emit ANSI colour even when stdout is not a terminal. A developer
#: whose shell sets one of these would otherwise see CLI tests fail on assertions like
#: `assert "applied 1 retag" in result.output`, because the rendered text carries escape codes
#: between the words. Tests assert on what the CLI says, not on how a terminal paints it.
_COLOUR_FORCING_VARIABLES = ("FORCE_COLOR", "CLICOLOR_FORCE")

for _variable in _COLOUR_FORCING_VARIABLES:
    os.environ.pop(_variable, None)


#: Variables `dhis2w_core.profile.resolve()` consults before it ever reads a `profiles.toml`:
#: `DHIS2_PROFILE` names a profile outright, and `DHIS2_URL` plus one credential pair
#: (`DHIS2_PAT`, or `DHIS2_USERNAME` + `DHIS2_PASSWORD`, with `DHIS2_VERSION` pinning the major)
#: synthesises the `env-raw` profile. Both layers outrank the project and global TOML files.
#:
#: That precedence makes them process-wide state a test cannot isolate by pointing `HOME` and
#: `XDG_CONFIG_HOME` at a `tmp_path`: a fixture can own every TOML file the resolver will read
#: and still lose to an ambient `DHIS2_URL`. A developer who has run `make -C infra up-seeded`
#: has exactly that - the local stack's URL and credentials, exported by their shell or read out
#: of `infra/home/credentials/.env.auth` - so a profile-resolving test would silently resolve
#: against localhost instead of the profile the fixture wrote.
#:
#: Tests that want the seeded stack ask for it explicitly (`local_url` / `local_pat` fixtures,
#: then `monkeypatch.setenv` inside the test), which lands after this fixture and therefore wins.
_PROFILE_RESOLUTION_VARIABLES = (
    "DHIS2_PROFILE",
    "DHIS2_URL",
    "DHIS2_PAT",
    "DHIS2_USERNAME",
    "DHIS2_PASSWORD",
    "DHIS2_VERSION",
)


@pytest.fixture(autouse=True)
def _neutral_profile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the env layers of profile resolution so no test inherits an ambient DHIS2 instance."""
    for variable in _PROFILE_RESOLUTION_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

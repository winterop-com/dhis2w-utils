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
import webbrowser

import pytest

#: Variables that make Rich render as if stdout were a terminal - ANSI colour, 80-column
#: panels, wrapped lines - even under a captured stream. `FORCE_COLOR` / `CLICOLOR_FORCE` are
#: developer-shell settings; `GITHUB_ACTIONS` and `TF_BUILD` are set by the CI runners
#: themselves, and Rich treats either as a colour terminal so its output looks good in CI
#: logs. Under `CliRunner` that means assertions like `assert "--code-source" in result.output`
#: fail on escape codes and panel wrapping. Tests assert on what the CLI says, not on how a
#: terminal paints it.
_COLOUR_FORCING_VARIABLES = ("FORCE_COLOR", "CLICOLOR_FORCE", "GITHUB_ACTIONS", "TF_BUILD")

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


#: Every entry point `webbrowser` offers for handing a URL to the desktop. `capture_code`
#: calls `webbrowser.open`, and the module's other two names reach the same browsers, so all
#: three are stubbed together: leaving one live would let a future call site slip through.
_BROWSER_LAUNCHERS = ("open", "open_new", "open_new_tab")


@pytest.fixture(autouse=True)
def _no_browser_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that reaches the interactive OAuth2 login instead of opening a browser.

    The OAuth2 authorization-code flow runs when no usable cached token is found, and its
    first act is to open the developer's own browser at the instance's `/oauth2/authorize`
    and then wait five minutes for a redirect that will never arrive. A test that means to
    exercise a cached token but stores one the provider rejects hits exactly that path, so
    the failure surfaces as the developer's browser opening on a fabricated URL and the
    suite hanging - neither of which names the test that caused it.

    Raising here turns that into an immediate failure naming the URL and, through the
    traceback, the test. A test that legitimately drives a browser launch overrides the stub
    with its own `monkeypatch.setattr(webbrowser, "open", ...)`, which lands after this
    fixture and therefore wins.
    """

    def _refuse(url: str, *args: object, **kwargs: object) -> bool:
        raise AssertionError(
            f"a test reached the interactive OAuth2 login and tried to open a browser at {url!r}. "
            "Pass `open_browser=False`, inject a `redirect_capturer`, or store a token carrying "
            "this provider's `base_url` and `client_id` so the cached-token path is taken."
        )

    for launcher in _BROWSER_LAUNCHERS:
        monkeypatch.setattr(webbrowser, launcher, _refuse)

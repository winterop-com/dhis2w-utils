"""Root pytest configuration: the environment every package's tests run under.

The colour-forcing variables are cleared at import rather than from a fixture. `cli_output`
builds its `Console` at module scope, so the setting is captured the moment a test module
imports the CLI - earlier than any fixture runs. pytest imports this file before it imports
test modules, which is the only point early enough to matter.
"""

from __future__ import annotations

import os

#: Variables that force Rich to emit ANSI colour even when stdout is not a terminal. A developer
#: whose shell sets one of these would otherwise see CLI tests fail on assertions like
#: `assert "applied 1 retag" in result.output`, because the rendered text carries escape codes
#: between the words. Tests assert on what the CLI says, not on how a terminal paints it.
_COLOUR_FORCING_VARIABLES = ("FORCE_COLOR", "CLICOLOR_FORCE")

for _variable in _COLOUR_FORCING_VARIABLES:
    os.environ.pop(_variable, None)

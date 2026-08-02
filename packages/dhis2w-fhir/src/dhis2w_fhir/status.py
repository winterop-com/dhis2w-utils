"""The IG life-cycle status and the publication flags every generated artifact derives from it.

`[ig] status` is the single dial: it is the `status` of `sushi-config.yaml`, the
publication `status` of every generated definitional artifact, and - through
`experimental_for_status` - their `experimental` flag. This module is a leaf so
every emitter can import it without reaching for `dhis2w_fhir.config`.
"""

from __future__ import annotations

from typing import Literal

#: Where the IG is in its life cycle: `draft` while it is being built, `active` in production.
IgStatus = Literal["draft", "active"]


def experimental_for_status(status: IgStatus) -> bool:
    """Whether artifacts generated under `status` are experimental - a draft IG's are, an active IG's are not."""
    return status == "draft"

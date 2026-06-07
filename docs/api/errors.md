# Errors

Every non-success response from DHIS2 raises a typed exception. The hierarchy is rooted at `Dhis2ClientError` and branches into four leaves: `Dhis2ApiError` (any HTTP non-success), `AuthenticationError` (401 / 403 specifically, on top of `Dhis2ApiError`), `OAuth2FlowError` (raised by the OAuth2 PKCE flow when token exchange fails), `UnsupportedVersionError` (raised on `connect()` when the live DHIS2 has no generated module).

## Worked example — branch on `Dhis2ApiError`

```python
from dhis2w_client import Dhis2ApiError
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    try:
        # `delete_bulk` takes (resource_type, uids).
        await client.metadata.delete_bulk("dataElements", ["doesNotExist"])
    except Dhis2ApiError as exc:
        print(f"HTTP {exc.status_code}: {exc.message}")
        # `web_message()` materialises the typed envelope when DHIS2 returned one;
        # returns None on errors whose body isn't a WebMessage (network 500s, etc.).
        wm = exc.web_message()
        if wm is not None and wm.response is not None:
            for c in wm.response.conflicts or []:
                print(f"  conflict: {c.object} -> {c.value}")
```

## Worked example — narrow `except` for auth failures

```python
from dhis2w_client import AuthenticationError, Dhis2ApiError

try:
    await client.system.me()
except AuthenticationError as exc:
    # Bad PAT / expired / wrong username/password. Distinct from
    # other 4xx failures so callers can prompt for re-auth specifically.
    print(f"re-auth needed: {exc.message}")
except Dhis2ApiError as exc:
    # Any other DHIS2-side error (404, 409, 500, ...).
    print(f"unexpected: {exc.status_code} {exc.message}")
```

## Worked example — `UnsupportedVersionError`

```python
from dhis2w_client import Dhis2Client, BasicAuth
from dhis2w_client.errors import UnsupportedVersionError

# `allow_version_fallback=False` (the default) fails fast when the live
# DHIS2 is on a version without a committed `generated/v{NN}` tree.
try:
    async with Dhis2Client("https://newer-dhis2.example", auth=BasicAuth(...)) as client:
        ...
except UnsupportedVersionError as exc:
    # `exc.version` is the unsupported version key (e.g. 'v44');
    # `exc.available` is the list of trees the client does have.
    print(f"no generated module for {exc.version}; available: {exc.available}")
    print("run `dhis2 codegen generate --url ...` to add one")
```

Pass `allow_version_fallback=True` on the client constructor (or via `open_client(..., allow_version_fallback=True)`) to use the nearest-lower populated version instead of raising.

Worked example: [`examples/v42/client/error_handling.py`](https://github.com/winterop-com/dhis2w-utils/blob/main/examples/v42/client/error_handling.py).

::: dhis2w_client.errors

# User plugin

`d2w user` wraps DHIS2's user-administration surface — reads via the generated `/api/users` CRUD accessor, writes via the dedicated `/api/users/invite`, `/api/users/{uid}/invite`, and `/api/users/{uid}/reset` endpoints the generated CRUD doesn't cover.

- CLI: `d2w user {list,get,me,invite,reinvite,reset-password}`
- MCP: `user_{list,get,me,invite,reinvite,reset_password}`
- Service: `packages/dhis2w-core/src/dhis2w_core/v42/plugins/user/service.py`

## Reads

### `d2w user list`

Forwards the full metadata query surface: `--fields`, repeatable `--filter`, `--order`, `--root-junction`, `--page`, `--page-size`. Default table shows `id,username,displayName,email,disabled,lastLogin` — swap via `--fields`.

```bash
# Recently active accounts.
d2w user list --filter "disabled:eq:false" --order "lastLogin:desc" --page-size 10

# Name match (note: `username` is flat in v42+ — there is no `userCredentials.username` path).
d2w user list --filter "username:like:admin" --fields ":identifiable"
```

### `d2w user get <uid-or-username>`

Fetch one user. DHIS2's `/api/users/{id}` only accepts a UID (passing a username returns 405), so the service resolves non-UID input through `GET /api/users?filter=username:eq:<input>` first, then refetches by UID. Raises `UserNotFoundError` → clean CLI error when the username doesn't exist.

### `d2w system whoami`

Prints `/api/me` — the authenticated user's richer profile (authorities, settings, programs, allowed OUs). Distinct from `get <username>` because `/api/me` returns fields that don't appear on the `/api/users/{uid}` view.

## Writes

### `d2w user invite <email> --first-name ... --surname ... [--user-role UID ...] [--org-unit UID ...]`

Creates a user and dispatches the invitation email via DHIS2's configured mailer. DHIS2 derives the username from the email prefix when `--username` is omitted.

Under the hood: `POST /api/users/invite` with a `UserInvite` body — `{username, email, firstName, surname, userRoles: [{id}...], organisationUnits: [{id}...]}`. DHIS2 returns a `WebMessage` envelope; `created_uid` carries the new user's UID.

### `d2w user reinvite <uid>`

`POST /api/users/{uid}/invite` — re-sends the invite for a user who hasn't completed registration. DHIS2 rejects with 400 if the user has already accepted.

### `d2w user reset-password <uid>`

`POST /api/users/{uid}/reset` — DHIS2 mints a reset token and mails a link to the user's verified email. No password ever flows through the client.

## Typed models

- Return type of `list` / `get`: `dhis2w_client.generated.v42.oas.User` (the OpenAPI-derived class — 46 fields including `disabled`, `lastLogin`, `authorities`, `userRoles`, `organisationUnits`, `settings`).
- `UserInvite` lives in `dhis2w_core.v42.plugins.user.service` — it's a write-side payload builder, not a read return type.
- `WebMessageResponse` is returned from every write helper so callers can project `created_uid` / `task_ref` / `conflicts` without re-parsing.

## MCP parity

Every CLI verb has an MCP tool with matching arg names. Read tools (`user_list`, `user_get`, `whoami`) are safe for agent callers; write tools (`user_invite`, `user_reinvite`, `user_reset_password`) hit real DHIS2 state and dispatch real email — scope profiles with read-only PATs when you don't want an agent triggering them.

## Service layer

```python
from dhis2w_core.v42.plugins.user import service
from dhis2w_core.v42.plugins.user.service import UserInvite, UserNotFoundError

users = await service.list_users(profile, filters=["disabled:eq:false"], page_size=10)
user = await service.get_user(profile, "alice")  # username or UID
envelope = await service.invite_user(profile, UserInvite(email="alice@example.com", firstName="Alice", surname="Example"))
```

Both the CLI and the MCP tool call into these functions unchanged — exception handling + I/O formatting stays at the edges.

## What's not included

The near-term plan flagged `grant-authority` as a fifth verb. Authority management lives on `UserRole` (authorities are granted by adding a user to a role, not by editing the user directly), so it belongs in a future `d2w user-role` sub-tree alongside `user-group`. Keep this plugin scoped to the user entity itself until there's a concrete need.

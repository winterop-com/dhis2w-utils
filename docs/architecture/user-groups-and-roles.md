# User-group + user-role plugins

`d2w user-group` and `d2w user-role` round out the user-administration surface that `d2w user` started. Groups own *sharing* (who can read/write what metadata, data-wise). Roles own *authorities* (what verbs a user can do — `F_METADATA_EXPORT`, `F_USER_VIEW`, `ALL`, …). Authorities are granted by adding a user to a role, not by editing the user directly — hence the verbs live here, not on `d2w user`.

Both plugins share the same shape: reads via the generated `/api/userGroups` / `/api/userRoles` CRUD accessors (full metadata query surface), membership edits via the dedicated single-entry endpoints that avoid the fetch-and-rewrite race.

## User groups

- CLI: `d2w user group {list,get,add-member,remove-member,sharing-get,sharing-grant-user}`
- MCP: `user_group_{list,get,add_member,remove_member,sharing_get}`
- Service: `packages/dhis2w-core/src/dhis2w_core/v42/plugins/user_group/service.py`

### Membership

```bash
# list + inspect
d2w user group list
d2w user group get <group-uid>

# single-member edits — POST/DELETE /api/userGroups/<gid>/users/<uid>
# (DHIS2 v42 calls the collection `users` on UserGroup, not `members`.)
d2w user group add-member <group-uid> <user-uid>
d2w user group remove-member <group-uid> <user-uid>
```

The single-member endpoints beat PATCHing the full group because they're atomic and don't race with other edits. No need to re-fetch + re-POST the entire `users[]` array.

### Sharing

Every persistable DHIS2 object has a sharing block: who can read it, who can write it, who owns it. Groups are themselves shareable — you grant access to the group metadata, which is distinct from the access the group's members collectively have on other objects.

```bash
# inspect
d2w user group sharing-get <group-uid>

# grant — preserves existing grants, appends (or overwrites) the target user.
d2w user group sharing-grant-user <group-uid> <user-uid> --metadata-write
d2w user group sharing-grant-user <group-uid> <user-uid> --metadata-read
```

`sharing-grant-user` fetches the current sharing block first, replays every existing user and group grant, then appends the new target grant. The result is POSTed to `/api/sharing` (typed via `dhis2w_client.apply_sharing`) so no JSON-Patch juggling is needed — see `docs/api/sharing.md`.

## User roles

- CLI: `d2w user role {list,get,authorities,add-user,remove-user}`
- MCP: `user_role_{list,get,authorities,add_user,remove_user}`
- Service: `packages/dhis2w-core/src/dhis2w_core/v42/plugins/user_role/service.py`

### Authority listing

```bash
d2w user role list                                # table: id, name, #auths, #users
d2w user role authority-list <role-uid>           # one authority per line, sorted
```

`authority-list` is the fast way to answer "what can this role do?" without dumping the full `UserRole` model.

### Role membership

```bash
# Grant / revoke a role on a user — POST/DELETE /api/userRoles/<rid>/users/<uid>.
d2w user role add-user <role-uid> <user-uid>
d2w user role remove-user <role-uid> <user-uid>
```

Same atomic-single-entry rationale as user-group members.

## MCP parity

Every CLI verb has an MCP tool with matching arg names. Read tools (`*_list`, `*_get`, `user_role_authority_list`, `user_group_sharing_get`) are safe for agent callers. Write tools (`add_member`, `remove_member`, `add_user`, `remove_user`) mutate real DHIS2 state — scope agent profiles with read-only PATs if you don't want them triggered.

## Typed models

- `dhis2w_client.generated.v42.oas.UserGroup` and `UserRole` — the OpenAPI-derived classes. Both carry the full sharing block, full member list, and (for roles) `authorities: list[str]`.
- `dhis2w_client.SharingBuilder` / `apply_sharing` / `get_sharing` — the typed helpers used by `sharing-grant-user`. See [Sharing](../api/sharing.md) for the access-string grammar and the builder API.

## What's not in scope

- Role *creation* via CLI. `/api/userRoles` accepts a full `UserRole` POST; the generated `client.resources.user_roles.create(role)` already covers it. A CLI wrapper would be thin; add when a concrete workflow needs it.
- `d2w authority list` — DHIS2's global authority inventory at `/api/authorities`. Useful for discovering authority strings when you build your own roles; out of scope here, belongs in a future `d2w system authorities` sub-command.

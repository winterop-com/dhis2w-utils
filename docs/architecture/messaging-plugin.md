# Messaging plugin

`d2w messaging` covers DHIS2's internal messaging surface
(`/api/messageConversations`). Pairs with the files plugin — a
`MESSAGE_ATTACHMENT`-domain fileResource uploaded via `d2w files
resources upload --domain MESSAGE_ATTACHMENT ...` can be referenced
from a message by UID.

```
d2w messaging {list,get,send,reply,mark-read,mark-unread,delete}
```

MCP mirrors the full surface: `messaging_list`, `messaging_get`,
`messaging_send`, `messaging_reply`, `messaging_mark_read`,
`messaging_mark_unread`, `messaging_delete`.

## Scope

- **Private / direct conversations** (user ↔ user, user ↔ group, user ↔
  orgUnit). The common case.
- **Tickets** (feedback, priority, status, assignee) exist as an extra
  endpoint family on the OpenAPI spec (`/assign`, `/priority`,
  `/status`). Not wired into this plugin — they're workflow-plugin
  material. Use `post_raw` directly if you need them.

## Send + reply

```bash
# Send a direct message:
d2w messaging send "Pilot rollout" "Please review the attached plan." \
  --user YzqyZKXzcxI --user aB3dEf5gH7i

# Attach a previously-uploaded fileResource (send-time only):
d2w files resources upload report.pdf --domain MESSAGE_ATTACHMENT  # prints the FR uid
d2w messaging send "Report" "latest numbers" \
  --user YzqyZKXzcxI \
  --attachment <fr-uid>

# Reply to the thread:
d2w messaging reply <conversation-uid> "thanks — reviewed"
```

**Reply attachment caveat:** DHIS2's reply endpoint
(`POST /api/messageConversations/{uid}`) takes a `text/plain` body on
v42 — it stores whatever bytes arrive as the message text. Attachments
+ the internal-note flag only work on the initial `send` call. To
attach a second file after a thread exists, start a new conversation
referencing the earlier one in the subject.

## List + inbox filtering

```bash
# Full inbox (rich table):
d2w messaging list

# Unread only (DHIS2 filter syntax):
d2w messaging list --filter "read:eq:false"

# Machine-readable:
d2w --json messaging list
```

The CLI table colors the `read` column (`unread` bold-yellow) and the
`type` column (TICKET / SYSTEM / VALIDATION_RESULT in magenta, PRIVATE /
DIRECT in blue).

## Read-state + cleanup

```bash
d2w messaging mark-read <uid> [<uid> ...]
d2w messaging mark-unread <uid> [<uid> ...]
d2w messaging delete <uid>           # soft-delete for the calling user only
```

`delete` is always soft from the caller's perspective: other participants
of the conversation keep their view. DHIS2 purges fully once every
participant has deleted.

## Library API

```python
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env

async with open_client(profile_from_env()) as client:
    me = await client.system.me()
    assert me.id is not None

    # Upload an attachment first.
    fr = await client.files.upload_file_resource(
        b"...",
        filename="report.pdf",
        domain="MESSAGE_ATTACHMENT",
    )

    # Send — returns a typed MessageConversation (BUGS.md #17 workaround).
    conversation = await client.messaging.send(
        subject="Report",
        text="Latest numbers attached.",
        users=[me.id],
        attachments=[fr.id],
    )

    # Read / reply / mark / delete.
    await client.messaging.reply(conversation.id, text="thanks")
    await client.messaging.mark_read(conversation.id)
    await client.messaging.delete_conversation(conversation.id)
```

## BUGS.md #17 — the Location-header UID dance

`POST /api/messageConversations` returns `201 Created` with the new UID
on the `Location` header, NOT in the JSON envelope. Every other DHIS2
create endpoint carries `response.uid` inside the body. The accessor
papers over this: `send()` extracts the UID from `Location` and GETs the
conversation back, so callers receive a typed `MessageConversation`
object the way they do from `client.files.upload_document`. See
`BUGS.md #17` for the full repro + upstream-fix preference.

Related wire quirks the accessor handles so callers don't have to:

- Attachments must be `{id}` reference objects on `send` — bare UID
  strings produce a 500. Callers pass `list[str]`; the accessor wraps.
- The reply endpoint (`POST /api/messageConversations/{uid}`) takes
  `text/plain` body on v42, not JSON — a JSON payload gets stored
  verbatim as the message text. `reply()` encodes its `text` argument
  as plain UTF-8 bytes.

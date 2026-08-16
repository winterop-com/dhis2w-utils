"""Send a message with a fileResource attachment — messaging + files together.

Exercises the typical workflow that combines the two plugins:

1. Upload a file as a `MESSAGE_ATTACHMENT` fileResource via `client.files`.
2. Create a new conversation via `client.messaging.send(...)`, referencing
   the fileResource UID in the `attachments` list.
3. List, reply, mark-read, delete.

`send()` returns a typed `MessageConversation` — DHIS2 puts the new UID
on the `Location` header rather than in the JSON envelope (see BUGS.md
#17), but the accessor papers over that.

Usage:
    uv run python examples/client/messaging_with_attachment.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from _runner import run_example
from dhis2w_core.client_context import open_client
from dhis2w_core.profile import profile_from_env


async def main() -> None:
    """Upload an attachment, send a self-addressed message referencing it, tear down."""
    async with open_client(profile_from_env()) as client:
        me = await client.system.me()
        assert me.id is not None, "connected profile must have a known user id"

        with tempfile.TemporaryDirectory() as tmp:
            attachment = Path(tmp) / "notes.txt"
            attachment.write_text("project kickoff notes — handoff to ops team")

            print("--- upload attachment ---")
            fr = await client.files.upload_file_resource(
                attachment.read_bytes(),
                filename=attachment.name,
                domain="MESSAGE_ATTACHMENT",
            )
            print(f"  fileResource uid: {fr.id}  domain={fr.domain}  storage={fr.storageStatus}")

            print("\n--- send self-addressed message with attachment ---")
            assert fr.id is not None
            conversation = await client.messaging.send(
                subject="Project kickoff notes",
                text="Attaching the handoff document for review.",
                users=[me.id],
                attachments=[fr.id],
            )
            print(f"  conversation uid: {conversation.id}  subject={conversation.subject!r}")
            assert conversation.id is not None

            print("\n--- list + reply (plain text only on DHIS2 v42) ---")
            rows = await client.messaging.list_conversations(filter="read:eq:false")
            print(f"  unread inbox: {len(rows)} conversations")
            # Replies take a text/plain body on v42 — attachments are only
            # wired on the initial send(). To attach a second file after
            # the thread exists, start a new conversation.
            await client.messaging.reply(conversation.id, text="thanks, will circulate")

            print("\n--- refetch + inspect thread ---")
            fetched = await client.messaging.get_conversation(conversation.id)
            print(f"  thread has {fetched.messageCount} messages")

            print("\n--- clean up ---")
            await client.messaging.mark_read(conversation.id)
            await client.messaging.delete_conversation(conversation.id)
            print("  marked read, deleted")


if __name__ == "__main__":
    run_example(main)

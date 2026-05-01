# `arena` recipes

Concrete workflows the skill is designed to support. Each recipe is a sequence of `arena` commands a Hermes Agent (or a human) can run. Replace bracketed values with real ones.

---

## 1. Verify everything before writing anything

Run this once at session start. Stop if any step fails.

```bash
arena doctor                              # token works?
arena doctor --channel <your-slug>        # write access on the target channel?
```

Expected: `{"ok": true, ...}`. If `ok: false`, do not proceed — surface the error.

---

## 2. Push a curated batch of artwork

The Clio Press flow.

```bash
# 1. Build a manifest at /tmp/push.json (see manifest.example.json)
# 2. Push:
arena block batch --manifest /tmp/push.json --pretty
# 3. Verify:
arena channel info <your-slug> --pretty   # check counts.blocks went up
```

The batch summary tells you which blocks succeeded and which failed (with reasons). Free tier rate limit is 120/min; default 700 ms throttle keeps you under it.

---

## 3. Mirror a public channel's contents into a new channel

When you want to fork or re-curate someone else's channel.

```bash
# 1. Read the source channel's contents:
arena channel list-contents <source-slug> --per 100 > /tmp/src.json

# 2. Create the destination:
arena channel create --title "Re-curated: <topic>" --visibility closed > /tmp/dst.json
# (note the id from /tmp/dst.json)

# 3. For each block in /tmp/src.json that you want to re-curate, connect it
#    to the new channel (does not duplicate — same block, additional connection):
arena block connect <block-id> --channel-id <new-channel-id>
```

Connecting (rather than re-creating) keeps the original attribution and source intact.

---

## 4. Remove a stale block from a channel

```bash
# 1. Find the connection id for the block-in-channel:
arena channel list-contents <channel-slug> --per 100 | jq '.contents[] | select(.id == <block-id>) | .connection_id'

# 2. Disconnect:
arena block disconnect <connection-id>
```

The block itself persists in any other channels it's connected to. To delete the block entirely, the user must do it in the Are.na web UI (the API does not support block deletion).

---

## 5. Rename or describe a channel after creation

```bash
arena channel update <slug-or-id> \
  --title "New Title" \
  --description "A short description, markdown supported."
```

---

## 6. Inspect what's in a channel

```bash
arena channel info <slug-or-id> --pretty   # metadata + counts + permissions
arena channel list-contents <slug-or-id> --per 50 --pretty   # actual blocks
```

`counts.blocks` is the authoritative count. `can.add_to` tells you whether the current token can write.

---

## 7. Look up a user's full body of work on Are.na

```bash
arena user info <slug>                     # bio + counts
arena user contents <slug> --per 50        # paginated blocks/channels
arena user contents <slug> --type Channel  # channels only
arena user contents <slug> --type Block    # blocks only
```

Useful for surfacing the corpus of a practitioner whose work you want to cite or curate from.

---

## 8. Update a block's metadata (e.g. add a description after the fact)

```bash
arena block update <block-id> --description "Added context: from the Drifella series, 2024."
```

For Text blocks, also pass `--content "<new markdown body>"`.

---

## 9. Cross-list a canonical block to multiple curated views

```bash
arena block connect <block-id> --channel-id <view-1>
arena block connect <block-id> --channel-id <view-2>
```

Same block, multiple appearances. Use this for press workflows where one canonical work appears in several thematic channels.

---
name: arena
description: "Are.na v3 API: read and write channels, blocks, connections, users."
version: 0.1.0
author: Cache Atelier
license: MIT
prerequisites:
  commands: [python3]
metadata:
  hermes:
    tags: [arena, are.na, social-media, curation, archive, channels, blocks]
    category: social-media
    homepage: https://github.com/cacheatelier/hermes-arena
---

# arena — Are.na via v3 API

`arena` is the official Are.na CLI for Hermes Agent. It wraps the v3 REST API and exposes a single `arena` command with subcommands for channel and block operations, plus the connection model that Are.na actually uses for "removing a block from a channel."

Use this skill for:

- Reading any public Are.na channel and its contents
- Creating, updating, and managing channels you own
- Pushing image, text, and link blocks to a channel (single or batch from a manifest)
- Connecting an existing block to additional channels (Are.na's "Connect" operation)
- Removing a block from a specific channel without deleting the block itself
- Looking up users (the authenticated user, public profiles, their contents)
- Verifying credentials and channel write-access at session start

The skill encapsulates several non-obvious Are.na API behaviors so neither the agent nor the user has to rediscover them. See **Pitfalls** below.

---

## Secret Safety (MANDATORY)

Critical rules when operating inside an agent or LLM session:

- **Never** read, print, parse, summarize, upload, or send the contents of `~/.hermes/.env` to the LLM context.
- **Never** pass the Are.na PAT inline as an argument to any command (no `--api-key` flag exists on this CLI for that exact reason).
- **Never** ask the user to paste their PAT into a chat prompt. PAT generation happens outside the agent session, on the Are.na website.
- The token must be set in the environment as `ARENA_API_KEY` before any `arena` command is run. The CLI reads it from env and uses it only for the `Authorization: Bearer …` header. The token is never logged, printed, or echoed.
- `arena doctor` is the safe verification path — it confirms the token works without ever revealing the token.

---

## Installation

```
hermes skills install cacheatelier/hermes-arena/arena --category social-media
```

Python 3 is the only host requirement. The skill installs `requests` automatically when invoked.

## One-Time User Setup

The user does this **outside the agent session**:

1. Sign in to [are.na](https://www.are.na) using the account that owns (or has write permission on) the channels they want to manage.
2. Visit [are.na/developers/personal-access-tokens](https://www.are.na/developers/personal-access-tokens).
3. Generate a new Personal Access Token. **Grant `write` scope.** Read-only tokens fail silently on POST with 401 — this is the most common gotcha.
4. The token is shown once. Copy it.
5. Set it in the Hermes environment:
   ```
   hermes config set ARENA_API_KEY <token>
   ```
   (or add `ARENA_API_KEY=<token>` to `~/.hermes/.env` directly).
6. Verify in a fresh shell:
   ```
   arena doctor
   ```
   Expected: `{"ok": true, "checks": {"auth": {"ok": true, "user_slug": "...", ...}}}`

The PAT must be issued by the **same Are.na account that owns the target channel**. Generating a PAT under a personal account and then trying to write to a press/team account's channel returns 401. Confirm with `arena doctor --channel <slug>` to verify write access on a specific channel before any batch operation.

---

## Quick Reference

| Command | Purpose |
|---|---|
| `arena doctor [--channel <slug>]` | Verify token + reachability; optionally confirm write access on a channel |
| `arena channel info <slug-or-id>` | Get channel object including `can.add_to`, owner, counts, links |
| `arena channel create --title <t>` | Create a new channel (`--visibility public/closed/private`, `--description`) |
| `arena channel update <id>` | Update channel metadata |
| `arena channel list-contents <id> [--page N --per N]` | Paginated blocks/channels in a channel |
| `arena channel list-connections <id>` | Paginated connections |
| `arena block info <id>` | Get block object |
| `arena block create --value <url-or-text> --channel-id <id>` | Single block; type inferred from `value` |
| `arena block update <id>` | Update block metadata or text content |
| `arena block batch --manifest <path>` | Batch-create from JSON; throttled per-block |
| `arena block connect <id> --channel-id <id>` | Add existing block to additional channel |
| `arena block disconnect <connection-id>` | Remove block from a channel (block persists) |
| `arena user me` | Get the authenticated user |
| `arena user info <slug-or-id>` | Public user profile |
| `arena user contents <slug-or-id> [--type Block/Channel]` | Paginated user contents |

All commands return JSON to stdout. Use `--pretty` for indented output.

---

## Command Details

### `arena doctor`

Verifies the env token works and (optionally) that it has write access on a specific channel. Always run this once at session start before any other `arena` operation.

```
arena doctor                              # validates token, returns user info
arena doctor --channel schizocollage      # also verifies can.add_to on that channel
```

Returns a structured `checks` object. Top-level `ok: true` means safe to proceed; `ok: false` means do not proceed — surface the error to the user.

### `arena channel info <slug-or-id>`

Returns the full channel object: `id`, `slug`, `title`, `description`, `visibility`, `state`, `owner`, `counts` (blocks, channels, contents, collaborators), `can` (add_to, update, destroy, manage_collaborators), and `_links` (self, owner, contents, connections, followers).

The `can.add_to` boolean is the authoritative signal that the current token can push blocks to this channel. Always check before batch operations.

### `arena channel create --title <t> [--visibility ...] [--description ...]`

Creates a new channel under the authenticated user. Default visibility is `closed` (visible at the URL but not on profiles). `public` is fully indexed; `private` is invite-only.

### `arena channel update <slug-or-id> [...]`

Updates `title`, `description`, and/or `visibility`. At least one field is required.

### `arena channel list-contents <slug-or-id> [--page N --per N --sort S]`

Paginated. `--per` defaults to 24, max 100. Response includes a `meta` object with `total_count`, `total_pages`, `has_more_pages`, `next_page`, `prev_page`. Use these to paginate fully.

### `arena channel list-connections <slug-or-id> [--page N --per N]`

Connections are the join records between blocks/channels and the channels they appear in. Use this when you need to know the *connection id* for a `block disconnect` operation (the connection id is required by the API to remove a block from a channel).

### `arena block info <id>`

Returns the full block object with `id`, `type` (Image/Text/Link/Embed/Attachment), `title`, `description`, `content` (for Text), `source`, `image` (for Image), `_links`, and `connections`.

### `arena block create --value <url-or-text> --channel-id <id> [...]`

Creates a single block in the specified channel. The `value` field is type-inferred:

- A URL pointing to an image (JPG, PNG, GIF, WebP, etc.) → **Image** block. Are.na fetches the URL and resolves it.
- A URL pointing to a non-image webpage → **Link** block. Are.na fetches title and excerpt.
- Plain text → **Text** block. Markdown supported.

Optional metadata: `--title`, `--description` (markdown), `--alt-text` (for images), `--original-source-url` (attribution URL when the image is mirrored from somewhere).

### `arena block update <id>`

Update block metadata: `--title`, `--description`, `--alt-text`. For **Text** blocks specifically, also `--content` to update the body. At least one field required.

### `arena block batch --manifest <path>`

Pushes multiple blocks from a JSON manifest. The manifest format:

```json
{
  "channel": "schizocollage",
  "throttle_ms": 700,
  "blocks": [
    {
      "value": "https://example.com/work.jpg",
      "title": "Drifella III #1075",
      "description": "From the *Drifella III* collection by Evil Biscuit. Source: tensor.trade",
      "original_source_url": "https://www.tensor.trade/item/..."
    }
  ]
}
```

`channel` accepts slug or integer id. `throttle_ms` defaults to 700 (≥ 600 ms is recommended; well under the 120/min free-tier rate limit).

The output is a summary object with per-block result entries (success: `block_id`, `type`; failure: `error.status`, `error.message`). Exit code 0 if all succeeded, 1 if any failed.

### `arena block connect <id> --channel-id <id>`

Adds an existing block to an additional channel. The block now appears in both its original channel(s) and the target. Use this for cross-channel curation.

### `arena block disconnect <connection-id>`

Removes a block from a channel. The block itself **persists** — only the connection is deleted. To find the connection id for a given block-in-channel, use `arena channel list-contents <channel-id>` (each item carries its own `id` and a `connection_id`) or `arena channel list-connections <channel-id>`.

This is the only way to "remove a block from a channel" — `DELETE /v3/blocks/{id}` does not exist in the Are.na API.

### `arena user me` / `arena user info <slug>` / `arena user contents <slug>`

Standard user lookups. `me` requires auth and returns the token-owning user. `info` is public. `contents` paginates a user's blocks and channels with optional `--type Block` or `--type Channel` filter.

---

## Common Workflows

### Push a curated batch of artwork to an Are.na channel

The batch flow Clio Press uses:

1. `arena doctor --channel <slug>` — verify auth + write access. Stop if `can.add_to: false`.
2. Build a manifest JSON locally (see `examples/manifest.example.json`). One entry per block.
3. `arena block batch --manifest path/to/manifest.json --pretty` — pushes throttled, prints per-block results.
4. Verify the channel now has the new blocks: `arena channel info <slug>` (check `counts.blocks`).

### Verify a token has the right scope before any agent task

```
arena doctor
```

If `ok: false` and the error is `401`, the token is missing, expired, or read-only-scoped. Surface to the user; do not retry blindly.

### Remove a block from a channel without destroying the block

```
arena channel list-contents <channel-id> --per 100
# Find the entry whose `id` matches the block you want to remove.
# Note its `connection_id`.
arena block disconnect <connection-id>
```

The block persists in any other channels it's connected to. To delete the block entirely, contact the user (Are.na does not expose block deletion via API; it must be done in the web UI).

### Cross-list a block to additional channels

```
arena block connect <block-id> --channel-id <other-channel-id>
```

Useful for press workflows where one canonical work appears in multiple curated views.

---

## Error Handling

| HTTP / signal | Likely cause | Fix |
|---|---|---|
| `401 Invalid credentials` on POST | Token is read-only scope, or expired, or for the wrong account | Regenerate PAT with `write` scope at [are.na/developers/personal-access-tokens](https://www.are.na/developers/personal-access-tokens) while logged in as the channel-owning account |
| `401` on GET of public channel | Token is malformed or not present | Confirm `ARENA_API_KEY` is set in env (no leading/trailing whitespace) |
| `403` with body `error code: 1010` | Cloudflare bot-block — **the client always sets a real UA, so you should never see this** | If seen, something downstream is stripping the User-Agent header. Confirm `arena_client.py` is unmodified |
| `404` on `arena channel info <slug>` | Slug typo, or channel is private and your token doesn't have access | Verify the slug at [are.na](https://www.are.na); for private channels, ensure the token belongs to a member |
| `422 Unprocessable Entity` on `block create` | `channel_ids` was a slug instead of an int, or `value` is missing | Resolve slug to id first via `arena channel info`, pass int id |
| `429 Too Many Requests` | Rate limit hit (free tier: 120/min) | Client retries automatically using `X-RateLimit-Reset`. If repeated, lower batch throttle |

---

## Pitfalls

These are the gotchas this skill exists to encapsulate. The agent should not have to rediscover them.

- **`DELETE /v3/blocks/{id}` does not exist.** The Are.na v3 API does not allow block deletion via API. To remove a block from a channel, use `arena block disconnect <connection-id>`. The block itself persists; only its appearance in the channel goes away. To delete the block entirely, the user must do it in the Are.na web UI.
- **`channel_ids` requires integer ids, not slugs.** Posting a block with `channel_ids: ["schizocollage"]` returns 422. Always resolve slug → id first via `arena channel info <slug>`. The CLI's `--channel-id` flag enforces int.
- **Cloudflare User-Agent gating.** Are.na's API sits behind Cloudflare, which blocks default Python `urllib`/`requests` User-Agents as bot traffic (HTTP 403, body `error code: 1010`). The client always sets a real browser-shape UA; do not modify `arena_client.py` to remove or shorten it.
- **PAT scope is non-obvious.** A token with default `read` scope returns 401 on any POST/PUT/DELETE — same response as an invalid token, so the failure mode looks like an auth bug. Always verify with `arena doctor` after generating a new PAT.
- **PAT account ownership.** The PAT authenticates as the user who issued it. If a press uses a separate Are.na account (e.g. `clio-press`), generate the PAT while logged in as that account — not the operator's personal account — or write attempts to the press's channels return 401.
- **IPFS gateway URL fragility.** When pushing image blocks whose `value` is a free IPFS gateway URL (e.g. `*.mypinata.cloud`, `nftstorage.link`), the gateway can rate-limit or expire. Are.na fetches the URL once at create time but the block keeps pointing at the original URL. For long-term archival, use the upload flow (planned for v0.2) instead.
- **Throttle defensively.** Free-tier rate limit is 120/min. The default 700 ms throttle in `block batch` keeps you well under it. If you raise the rate, watch `X-RateLimit-Remaining` headers.

---

## Agent Workflow

When Hermes detects an Are.na-shaped task, it should:

1. **Always run `arena doctor` first** to confirm the token works. Cache the result for the session.
2. If the task targets a specific channel, run `arena doctor --channel <slug>` to confirm `can.add_to: true` before any write operation.
3. For single-block operations, use `arena block create` directly.
4. For multi-block operations (more than ~3 blocks), build a manifest JSON and use `arena block batch` rather than looping single creates — the manifest path throttles correctly and produces a structured summary.
5. When asked to "remove a block from a channel," use `arena channel list-contents` to find the connection id, then `arena block disconnect <connection-id>`. Do not attempt `arena block delete` (it does not exist).
6. Never paste the PAT into chat. Never echo it. The CLI does not accept inline PATs precisely to enforce this.

---

## Notes

- **Rate limits** (per minute, by Are.na account tier): Guest 30, Free 120, Premium 300, Supporter/Lifetime 600. Watch the `X-RateLimit-*` response headers.
- **Search** (`GET /v3/search`) and **async batch** (`POST /v3/blocks/batch`) are Are.na **Premium-only** endpoints. Not exposed in v0.1; planned for v0.2 with graceful degradation.
- **File upload** via presigned S3 (`POST /v3/uploads/presign`) is planned for v0.2 — useful for local files and durable rehosting of fragile IPFS sources.
- **Comments** (`/v3/blocks/{id}/comments`) are not in v0.1; planned for v0.2.

The full v3 endpoint catalog is available at [`references/api-reference.md`](references/api-reference.md). The official OpenAPI spec snapshot is pinned at [`references/openapi-snapshot.json`](references/openapi-snapshot.json).

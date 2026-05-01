# hermes-arena

A [Hermes Agent](https://hermes-agent.nousresearch.com/) skill that gives the agent first-class access to the [Are.na](https://www.are.na) v3 API: channels, blocks, connections, users.

Built by [Cache Atelier](https://cacheatelier.work) for [Clio Press](https://www.are.na/clio-press), the press uses Are.na as the *evidence* layer of its three-artifact output (wiki = argument, Are.na channel = evidence, zine = capsule). The skill is open source so any Hermes user can teach their agent the same capability.

## Install

```
hermes skills install cacheatelier/hermes-arena/arena --category social-media
```

The skill needs Python 3 and `requests` (one dependency). Hermes' install flow handles them.

## One-time setup

1. Create or sign in to your Are.na account at [are.na](https://www.are.na).
2. Generate a Personal Access Token at [are.na/developers/personal-access-tokens](https://www.are.na/developers/personal-access-tokens) — **make sure to grant `write` scope, not just `read`**. (Read-only tokens fail silently on POST with 401.)
3. The token must be issued by the account that owns or has write permission on the channels you want to publish to. If you want to publish to `are.na/your-account/your-channel`, generate the PAT while logged in as `your-account`.
4. Add the token to Hermes' env:
   ```
   hermes config set ARENA_API_KEY <your-pat>
   ```
   (Or add `ARENA_API_KEY=<pat>` to `~/.hermes/.env` directly.)
5. Verify everything is wired:
   ```
   arena doctor
   ```

## What the skill does

Ask Hermes to do anything Are.na-shaped — it'll reach for `arena` automatically. Examples:

- *"Push these 30 image URLs to my schizocollage Are.na channel as image blocks with proper attribution."*
- *"Pull the contents of `clio-press/cyanotypes` and tell me how many image blocks are in there."*
- *"Create a new closed Are.na channel called 'New Surrealism research' under my account."*
- *"Connect block 45747337 to my reference channel as well."*
- *"Verify my Are.na token has write access to the `schizocollage` channel."*

Direct CLI use also supported — every Hermes-facing operation is also a clean shell command, so the skill is useful outside agent contexts too.

## Quick reference

```
arena doctor                          # verify auth + reachability
arena channel info <slug-or-id>       # channel object + permissions (can.add_to)
arena channel create --title "..."    # new channel
arena channel update <id> [...]       # edit metadata
arena channel list-contents <id>      # paginated blocks
arena channel list-connections <id>   # paginated connections
arena block info <id>                 # block object
arena block create --value <url-or-text> --channel-id <id>  [--title --description --alt-text --original-source-url]
arena block update <id> [...]         # edit metadata
arena block batch --manifest <path>   # batch from JSON, throttled
arena block connect <id> --channel-id <id>     # add to additional channel
arena block disconnect <connection-id>          # remove from a channel
arena user me                         # current authenticated user
arena user info <slug-or-id>          # public user info
arena user contents <slug-or-id>      # user's blocks/channels
```

All commands return JSON to stdout. Use `--pretty` for indented output.

## Manifest format (for `arena block batch`)

```json
{
  "channel": "schizocollage",
  "throttle_ms": 700,
  "blocks": [
    {
      "value": "https://example.com/work.jpg",
      "title": "Drifella III #1075",
      "description": "From the Drifella III collection by Evil Biscuit. Source: tensor.trade",
      "original_source_url": "https://www.tensor.trade/item/..."
    },
    {
      "value": "Direct quotation as text becomes a Text block automatically.",
      "description": "— Practitioner Name, Source, 2025"
    }
  ]
}
```

`channel` accepts slug or integer id. `throttle_ms` defaults to 700 ms (well under the 120/min free-tier rate limit).

## Recipes

See [`skills/arena/examples/recipes.md`](skills/arena/examples/recipes.md) for common workflows: pushing a curated artwork batch, mirroring a public channel, doing the editor-checkpoint pattern Clio Press uses.

## Why this skill exists (lessons it encapsulates)

Are.na's v3 API has a few quiet sharp edges that aren't obvious from the docs. The skill encapsulates each one so agents and humans don't rediscover them:

- **Cloudflare 1010**: Are.na's API sits behind Cloudflare, which blocks default Python `urllib`/`requests` User-Agents as bot traffic (HTTP 403 with body `error code: 1010`). The client always sets a real browser-shape User-Agent — you'll never see this error.
- **v2 is deprecated**: bare `Authorization: Bearer` writes against `/v2/...` endpoints look fine but return 401 Invalid Credentials with v3-issued PATs. Always use `/v3/...`.
- **There is no `DELETE /v3/blocks/{id}`**: blocks can't be deleted via API. To remove a block from a channel, use `arena block disconnect <connection-id>`. The block persists; only its appearance in that channel goes away.
- **`channel_ids` requires integer ids, not slugs**: a slug like `schizocollage` returns 422. Use `arena channel info <slug>` to fetch the integer id, then pass it.
- **Write scope is mandatory for any POST/PUT/DELETE**: a read-only PAT returns 401 on writes. The doctor command verifies this.

## Capabilities not in v0.1

- **File upload** via presigned S3 (`POST /v3/uploads/presign` two-step flow) — useful for local files and durable archival of fragile IPFS sources. v0.2.
- **Comments** on blocks. v0.2.
- **Search** (`GET /v3/search`) — Premium-only on Are.na's side. Will degrade gracefully when added.
- **Async batch** (`POST /v3/blocks/batch`) — Premium-only.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

PRs welcome. The skill follows Hermes' bundled-skill conventions (see [`skills/arena/SKILL.md`](skills/arena/SKILL.md) for the load-bearing instruction file and [`skills/arena/references/api-reference.md`](skills/arena/references/api-reference.md) for the v3 endpoint catalog).

For changes that affect the agent-facing surface (CLI commands, SKILL.md text), bump the minor version in `skills/arena/SKILL.md` frontmatter and add a CHANGELOG entry.

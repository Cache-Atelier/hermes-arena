# Are.na v3 API reference (cheat sheet)

The endpoints `arena` wraps in v0.1, plus the ones we don't yet (with reasons). Pinned to the OpenAPI snapshot at `openapi-snapshot.json`.

Base URL: `https://api.are.na/v3`
Auth: `Authorization: Bearer {PAT}` (write scope required for any POST/PUT/DELETE)
Rate limits per Are.na tier: Guest 30 / Free 120 / Premium 300 / Supporter 600 — per minute.

---

## Channels

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| GET | `/channels/{slug-or-id}` | Channel metadata, owner, counts, `can.*` permissions | `arena channel info` |
| POST | `/channels` | Create channel | `arena channel create` |
| PUT | `/channels/{slug-or-id}` | Update channel | `arena channel update` |
| DELETE | `/channels/{slug-or-id}` | Delete channel (irreversible) | *(not in v0.1)* |
| GET | `/channels/{slug-or-id}/contents` | Paginated blocks + sub-channels | `arena channel list-contents` |
| GET | `/channels/{slug-or-id}/connections` | Paginated connections | `arena channel list-connections` |
| GET | `/channels/{slug-or-id}/followers` | Paginated followers | *(not in v0.1)* |

Pagination: `?page=N&per=N` (per defaults to 24, max 100).

---

## Blocks

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| GET | `/blocks/{id}` | Block metadata + content | `arena block info` |
| POST | `/blocks` | Create block (type inferred from `value`) | `arena block create` |
| PUT | `/blocks/{id}` | Update block | `arena block update` |
| POST | `/blocks/batch` | Async batch — **Premium only** | *(planned v0.2)* |
| GET | `/blocks/batch/{batch_id}` | Batch status — Premium only | *(planned v0.2)* |
| GET | `/blocks/{id}/connections` | Where this block appears | *(planned v0.2)* |
| GET | `/blocks/{id}/comments` | Block comments | *(planned v0.2)* |
| POST | `/blocks/{id}/comments` | Add comment | *(planned v0.2)* |

**Block type inference from `value`**:
- URL pointing to image (JPG/PNG/GIF/WebP) → `Image` block
- URL pointing to other web content → `Link` or `Embed` block (Are.na decides based on Content-Type and OG metadata)
- Plain text (anything not parsing as a URL) → `Text` block

There is **no `DELETE /v3/blocks/{id}`**. To remove a block from a channel, delete the connection. To delete a block entirely, the user must do it in the web UI.

---

## Connections

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| POST | `/connections` | Add a block (or channel) to one or more channels | `arena block connect` |
| DELETE | `/connections/{id}` | Remove a block from a channel (block persists) | `arena block disconnect` |
| POST | `/connections/{id}/move` | Reposition connection within channel | *(not in v0.1)* |

Body for POST `/connections`:
```json
{
  "connectable_id": <block-or-channel-id>,
  "connectable_type": "Block" | "Channel",
  "channel_ids": [<int>, ...]
}
```

---

## Users

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| GET | `/me` | Authenticated user (verifies token) | `arena user me` (also used by `arena doctor`) |
| GET | `/users/{slug-or-id}` | Public user profile | `arena user info` |
| GET | `/users/{slug-or-id}/contents` | Paginated user's blocks/channels | `arena user contents` |
| GET | `/users/{slug-or-id}/followers` | Followers | *(not in v0.1)* |
| GET | `/users/{slug-or-id}/following` | Following | *(not in v0.1)* |

---

## Search (Premium-only on Are.na)

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| GET | `/search` | Full-text + filter search | *(planned v0.2 with graceful degradation)* |

Parameters: `query`, `type` (Block/Channel/User/Group/Image/Link/Text/Attachment), `scope` (`all`/`my`), `user_id`, `group_id`, `channel_id`, `ext` (file extension), `sort` (score_desc/created_at_desc/random), `after` (ISO 8601), pagination.

---

## Uploads (presigned S3 — planned v0.2)

| Method | Path | What | `arena` subcommand |
|---|---|---|---|
| POST | `/uploads/presign` | Get presigned S3 URLs for direct upload (up to 50 files) | *(planned v0.2)* |

Two-step flow:
1. POST `/uploads/presign` with `[{filename, content_type}, ...]` — returns presigned URLs.
2. PUT each file to its returned URL with matching Content-Type, within 1 hour.
3. Reference the resulting S3 URL as `value` in a normal block create.

Useful for hosting local files durably on Are.na's S3 (instead of pointing at fragile IPFS gateways).

---

## Comments (planned v0.2)

| Method | Path | What |
|---|---|---|
| GET | `/blocks/{id}/comments` | List comments |
| POST | `/blocks/{id}/comments` | Add a comment (body supports @mentions) |
| DELETE | `/comments/{id}` | Delete (author-only) |

---

## Auth scopes

- `read` — read-only. Returns 401 on any POST/PUT/DELETE.
- `write` — full read + write. Required for everything except pure GETs of public resources.

There is no separate `destroy` scope; deletions use `write`. There is no `admin` scope.

---

## Error response format

JSON body:
```json
{
  "error": "Not Found",
  "code": 404,
  "details": {
    "message": "The resource you requested could not be found."
  }
}
```

Cloudflare-level errors (e.g. bot blocking) return a plain-text body like `error code: 1010` instead of the v3 JSON shape. The client detects and surfaces these distinctly.

---

## Notable response headers

- `X-RateLimit-Limit` — requests allowed in the window
- `X-RateLimit-Remaining` — remaining in this window
- `X-RateLimit-Reset` — Unix timestamp when the window resets
- `X-RateLimit-Tier` — `guest` | `free` | `premium` | `supporter`
- `X-RateLimit-Window` — always 60 (seconds)

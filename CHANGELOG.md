# Changelog

## v0.1.0 — 2026-05-01

Initial release. A Hermes Agent skill for the Are.na v3 API.

### Added

- Single `arena` CLI entrypoint with subcommands for channels, blocks, connections, and users
- `arena doctor` — verifies token, reachability, and Cloudflare-UA passthrough
- `arena channel info | create | update | list-contents | list-connections`
- `arena block info | create | update | batch | connect | disconnect`
- `arena user me | info | contents`
- Manifest format for `arena block batch` (JSON; throttled per-block)
- `ArenaClient` Python class encapsulating auth, real browser User-Agent (Cloudflare 1010 workaround), rate-limit-aware retry on 429, exponential backoff on 5xx, structured error normalization
- SKILL.md following Hermes' bundled-skill conventions (xurl pattern); includes Secret Safety, Quick Reference, Common Workflows, Error Handling, Pitfalls, Agent Workflow sections
- Examples directory with annotated manifest and recipe walkthroughs
- API reference cheat sheet pinned to a snapshot of the official Are.na OpenAPI spec
- CI smoke test (gated by `ARENA_API_KEY` GitHub Actions secret)

### Known limitations (deferred to v0.2+)

- File upload via presigned S3 flow (`POST /v3/uploads/presign`) — needed for local-file ingestion and durable IPFS rehosting
- Comments on blocks (`/v3/blocks/{id}/comments`)
- Search (`GET /v3/search`) — Premium-gated on Are.na
- Async batch (`POST /v3/blocks/batch`) — Premium-gated on Are.na

### Notes

The skill encapsulates several non-obvious gotchas:

- Are.na's v3 API is deprecated; v3 PATs do not authenticate against v2 endpoints
- `DELETE /v3/blocks/{id}` does not exist; the disconnect operation (`DELETE /v3/connections/{id}`) is the correct path for removing a block from a channel
- `channel_ids` accepts integer ids, not slugs
- The Cloudflare front-door blocks default Python User-Agents — the client always sets a real browser-shape UA

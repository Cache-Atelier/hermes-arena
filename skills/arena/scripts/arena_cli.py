"""arena_cli — CLI dispatcher for the hermes-arena skill.

argparse subparsers, one handler per subcommand. The agent (or a human) invokes
the `arena` entrypoint, which calls `arena_cli.main()`.

Output convention:
- All commands print JSON to stdout on success (parseable by the agent).
- Errors go to stderr with a structured envelope. Exit code 1 on failure.
- `--pretty` renders JSON indented (default is compact single-line).

Auth: reads `ARENA_API_KEY` from environment. Never reads or prints the token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from arena_client import ArenaAPIError, ArenaClient


# ----------------------------------------------------------------------
# Output helpers
# ----------------------------------------------------------------------


def _emit(data: Any, pretty: bool) -> None:
    if data is None:
        return
    indent = 2 if pretty else None
    print(json.dumps(data, indent=indent, default=str))


def _emit_error(exc: Exception) -> int:
    if isinstance(exc, ArenaAPIError):
        envelope = {"ok": False, "error": exc.as_dict()}
    elif isinstance(exc, ValueError):
        envelope = {"ok": False, "error": {"status": 0, "message": str(exc)}}
    else:
        envelope = {"ok": False, "error": {"status": 0, "message": f"{type(exc).__name__}: {exc}"}}
    print(json.dumps(envelope, indent=2), file=sys.stderr)
    return 1


def _client() -> ArenaClient:
    key = os.environ.get("ARENA_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "ARENA_API_KEY is not set in the environment. Set it via "
            "`hermes config set ARENA_API_KEY <token>` or add it to ~/.hermes/.env. "
            "Generate a token at https://www.are.na/developers/personal-access-tokens "
            "(write scope, from the account that owns your target channels)."
        )
    return ArenaClient(key)


# ----------------------------------------------------------------------
# Subcommand handlers
# ----------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    try:
        client = _client()
    except ValueError as exc:
        return _emit_error(exc)

    report: dict[str, Any] = {"ok": True, "checks": {}}

    # Token + reachability
    try:
        me = client.me()
        report["checks"]["auth"] = {
            "ok": True,
            "user_slug": me.get("slug"),
            "user_id": me.get("id"),
            "user_name": me.get("name"),
        }
    except ArenaAPIError as exc:
        report["ok"] = False
        report["checks"]["auth"] = {"ok": False, "error": exc.as_dict()}
        _emit(report, pretty=True)
        return 1

    # Optional channel write-access check
    if args.channel:
        try:
            ch = client.verify_channel_writable(args.channel)
            report["checks"]["channel_write_access"] = {
                "ok": True,
                "channel_slug": ch.get("slug"),
                "channel_id": ch.get("id"),
                "owner_slug": (ch.get("owner") or {}).get("slug"),
                "can": ch.get("can"),
            }
        except ArenaAPIError as exc:
            report["ok"] = False
            report["checks"]["channel_write_access"] = {"ok": False, "error": exc.as_dict()}

    _emit(report, pretty=True)
    return 0 if report["ok"] else 1


def cmd_channel_info(args: argparse.Namespace) -> int:
    try:
        _emit(_client().get_channel(args.slug_or_id), args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_channel_create(args: argparse.Namespace) -> int:
    try:
        ch = _client().create_channel(
            title=args.title,
            visibility=args.visibility,
            description=args.description,
        )
        _emit(ch, args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_channel_update(args: argparse.Namespace) -> int:
    try:
        ch = _client().update_channel(
            args.slug_or_id,
            title=args.title,
            description=args.description,
            visibility=args.visibility,
        )
        _emit(ch, args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_channel_list_contents(args: argparse.Namespace) -> int:
    try:
        _emit(
            _client().list_channel_contents(args.slug_or_id, page=args.page, per=args.per, sort=args.sort),
            args.pretty,
        )
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_channel_list_connections(args: argparse.Namespace) -> int:
    try:
        _emit(
            _client().list_channel_connections(args.slug_or_id, page=args.page, per=args.per),
            args.pretty,
        )
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_block_info(args: argparse.Namespace) -> int:
    try:
        _emit(_client().get_block(args.id), args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_block_create(args: argparse.Namespace) -> int:
    try:
        block = _client().create_block(
            value=args.value,
            channel_ids=[args.channel_id],
            title=args.title,
            description=args.description,
            alt_text=args.alt_text,
            original_source_url=args.original_source_url,
        )
        _emit(block, args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_block_update(args: argparse.Namespace) -> int:
    try:
        block = _client().update_block(
            args.id,
            title=args.title,
            description=args.description,
            content=args.content,
            alt_text=args.alt_text,
        )
        _emit(block, args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_block_batch(args: argparse.Namespace) -> int:
    try:
        with open(args.manifest, "r") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        return _emit_error(ValueError(f"Could not read manifest at {args.manifest}: {exc}"))

    blocks = manifest.get("blocks") or []
    if not blocks:
        return _emit_error(ValueError("Manifest has no `blocks` array."))

    channel_ref = manifest.get("channel")
    if not channel_ref:
        return _emit_error(ValueError("Manifest is missing `channel` (slug or integer id)."))

    throttle_ms = int(manifest.get("throttle_ms", 700))
    throttle_s = max(throttle_ms / 1000.0, 0.0)

    try:
        client = _client()
    except ValueError as exc:
        return _emit_error(exc)
    client.throttle_s = throttle_s

    # Resolve channel slug → id
    try:
        channel_obj = client.get_channel(channel_ref)
        channel_id = int(channel_obj["id"])
    except Exception as exc:
        return _emit_error(exc)

    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for idx, entry in enumerate(blocks):
        value = entry.get("value")
        if not value:
            results.append({"index": idx, "ok": False, "error": "missing `value`"})
            failed += 1
            continue
        try:
            block = client.create_block(
                value=value,
                channel_ids=[channel_id],
                title=entry.get("title"),
                description=entry.get("description"),
                alt_text=entry.get("alt_text"),
                original_source_url=entry.get("original_source_url"),
                original_source_title=entry.get("original_source_title"),
                metadata=entry.get("metadata"),
            )
            results.append(
                {"index": idx, "ok": True, "block_id": block.get("id"), "type": block.get("type")}
            )
            succeeded += 1
        except ArenaAPIError as exc:
            results.append({"index": idx, "ok": False, "error": exc.as_dict()})
            failed += 1
        except Exception as exc:
            results.append({"index": idx, "ok": False, "error": str(exc)})
            failed += 1

    summary = {
        "ok": failed == 0,
        "channel": channel_obj.get("slug"),
        "channel_id": channel_id,
        "total": len(blocks),
        "succeeded": succeeded,
        "failed": failed,
        "throttle_ms": throttle_ms,
        "results": results,
    }
    _emit(summary, args.pretty)
    return 0 if failed == 0 else 1


def cmd_block_connect(args: argparse.Namespace) -> int:
    try:
        _emit(
            _client().connect_block(args.id, [args.channel_id]),
            args.pretty,
        )
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_block_disconnect(args: argparse.Namespace) -> int:
    try:
        _client().disconnect(args.connection_id)
        _emit({"ok": True, "deleted_connection_id": args.connection_id}, args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_user_me(args: argparse.Namespace) -> int:
    try:
        _emit(_client().me(), args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_user_info(args: argparse.Namespace) -> int:
    try:
        _emit(_client().get_user(args.slug_or_id), args.pretty)
    except Exception as exc:
        return _emit_error(exc)
    return 0


def cmd_user_contents(args: argparse.Namespace) -> int:
    try:
        _emit(
            _client().list_user_contents(args.slug_or_id, page=args.page, per=args.per, type_filter=args.type),
            args.pretty,
        )
    except Exception as exc:
        return _emit_error(exc)
    return 0


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------


def _make_pretty_parent() -> argparse.ArgumentParser:
    """A parent parser carrying just --pretty, inherited by every subparser
    so the flag works in any position (e.g. `arena channel info foo --pretty`
    as well as `arena --pretty channel info foo`)."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--pretty",
        action="store_true",
        help="Emit indented JSON (default: single-line).",
    )
    return parent


def build_parser() -> argparse.ArgumentParser:
    pretty_parent = _make_pretty_parent()
    parser = argparse.ArgumentParser(
        prog="arena",
        parents=[pretty_parent],
        description=(
            "Are.na v3 API client. Set ARENA_API_KEY (write scope) in your env. "
            "Output is JSON. Use --pretty for indented output."
        ),
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    # doctor
    p = sub.add_parser("doctor", parents=[pretty_parent], help="Verify token, reachability, and (optional) channel write access.")
    p.add_argument("--channel", help="Optional channel slug or id to verify write access on.")
    p.set_defaults(handler=cmd_doctor)

    # channel
    p = sub.add_parser("channel", help="Channel operations.")
    chsub = p.add_subparsers(dest="chcmd", required=True)

    cp = chsub.add_parser("info", parents=[pretty_parent], help="Get channel by slug or id.")
    cp.add_argument("slug_or_id")
    cp.set_defaults(handler=cmd_channel_info)

    cp = chsub.add_parser("create", parents=[pretty_parent], help="Create a new channel.")
    cp.add_argument("--title", required=True)
    cp.add_argument("--visibility", default="closed", choices=["public", "closed", "private"])
    cp.add_argument("--description", default=None)
    cp.set_defaults(handler=cmd_channel_create)

    cp = chsub.add_parser("update", parents=[pretty_parent], help="Update channel metadata.")
    cp.add_argument("slug_or_id")
    cp.add_argument("--title", default=None)
    cp.add_argument("--description", default=None)
    cp.add_argument("--visibility", default=None, choices=["public", "closed", "private"])
    cp.set_defaults(handler=cmd_channel_update)

    cp = chsub.add_parser("list-contents", parents=[pretty_parent], help="Paginated channel contents.")
    cp.add_argument("slug_or_id")
    cp.add_argument("--page", type=int, default=1)
    cp.add_argument("--per", type=int, default=24)
    cp.add_argument("--sort", default=None)
    cp.set_defaults(handler=cmd_channel_list_contents)

    cp = chsub.add_parser("list-connections", parents=[pretty_parent], help="Paginated channel connections.")
    cp.add_argument("slug_or_id")
    cp.add_argument("--page", type=int, default=1)
    cp.add_argument("--per", type=int, default=24)
    cp.set_defaults(handler=cmd_channel_list_connections)

    # block
    p = sub.add_parser("block", help="Block operations.")
    bsub = p.add_subparsers(dest="bcmd", required=True)

    bp = bsub.add_parser("info", parents=[pretty_parent], help="Get block by id.")
    bp.add_argument("id", type=int)
    bp.set_defaults(handler=cmd_block_info)

    bp = bsub.add_parser("create", parents=[pretty_parent], help="Create a single block (value can be URL or text).")
    bp.add_argument("--value", required=True)
    bp.add_argument("--channel-id", dest="channel_id", required=True, type=int)
    bp.add_argument("--title", default=None)
    bp.add_argument("--description", default=None)
    bp.add_argument("--alt-text", dest="alt_text", default=None)
    bp.add_argument("--original-source-url", dest="original_source_url", default=None)
    bp.set_defaults(handler=cmd_block_create)

    bp = bsub.add_parser("update", parents=[pretty_parent], help="Update block metadata.")
    bp.add_argument("id", type=int)
    bp.add_argument("--title", default=None)
    bp.add_argument("--description", default=None)
    bp.add_argument("--content", default=None, help="Markdown content (Text blocks only).")
    bp.add_argument("--alt-text", dest="alt_text", default=None)
    bp.set_defaults(handler=cmd_block_update)

    bp = bsub.add_parser("batch", parents=[pretty_parent], help="Batch-create blocks from a manifest JSON file.")
    bp.add_argument("--manifest", required=True, help="Path to manifest JSON. See examples/manifest.example.json.")
    bp.set_defaults(handler=cmd_block_batch)

    bp = bsub.add_parser("connect", parents=[pretty_parent], help="Add an existing block to an additional channel.")
    bp.add_argument("id", type=int, help="Block id to connect.")
    bp.add_argument("--channel-id", dest="channel_id", required=True, type=int)
    bp.set_defaults(handler=cmd_block_connect)

    bp = bsub.add_parser(
        "disconnect",
        parents=[pretty_parent],
        help=(
            "Remove a block from a channel. Note: this deletes the *connection*, not the block. "
            "Are.na's API does not support deleting blocks themselves."
        ),
    )
    bp.add_argument("connection_id", type=int)
    bp.set_defaults(handler=cmd_block_disconnect)

    # user
    p = sub.add_parser("user", help="User operations.")
    usub = p.add_subparsers(dest="ucmd", required=True)

    up = usub.add_parser("me", parents=[pretty_parent], help="Get the authenticated user.")
    up.set_defaults(handler=cmd_user_me)

    up = usub.add_parser("info", parents=[pretty_parent], help="Get a user by slug or id.")
    up.add_argument("slug_or_id")
    up.set_defaults(handler=cmd_user_info)

    up = usub.add_parser("contents", parents=[pretty_parent], help="Paginated list of a user's blocks/channels.")
    up.add_argument("slug_or_id")
    up.add_argument("--page", type=int, default=1)
    up.add_argument("--per", type=int, default=24)
    up.add_argument("--type", default=None, help="Block or Channel.")
    up.set_defaults(handler=cmd_user_contents)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())

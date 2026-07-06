#!/usr/bin/env python3
"""Track and resume batch translation progress via meta.json."""

import argparse
import sys
from pathlib import Path

from sub_common import load_meta, mark_progress, next_batch_hint, save_meta


def cmd_status(batches_dir: Path) -> int:
    meta = load_meta(batches_dir)
    last = int(meta.get("last_completed_batch", 0))
    total = int(meta.get("batch_count", 0))
    nxt = next_batch_hint(meta)
    updated = meta.get("progress_updated_at") or "(never)"

    print(f"Batches dir: {batches_dir.resolve()}")
    print(f"Progress: {last}/{total} batches completed")
    print(f"Updated: {updated}")
    if nxt is None:
        print("Next: (all batches marked complete)")
    else:
        print(f"Next: batch_{nxt:03d}.json → batch_{nxt:03d}.vi.json")
    if meta.get("partial_job"):
        tr = meta.get("time_range", {})
        print(f"Partial job: {tr.get('start')} – {tr.get('end')} ({meta.get('total_cues')} cues)")
    return 0


def cmd_mark(batches_dir: Path, batch_num: int) -> int:
    meta = mark_progress(batches_dir, batch_num)
    print(f"Marked complete: batch {batch_num}/{meta['batch_count']}")
    nxt = next_batch_hint(meta)
    if nxt:
        print(f"Next: batch_{nxt:03d}.json")
    else:
        print("All batches marked complete.")
    return 0


def cmd_reset(batches_dir: Path) -> int:
    meta = load_meta(batches_dir)
    meta["last_completed_batch"] = 0
    meta["progress_updated_at"] = None
    save_meta(batches_dir, meta)
    print("Progress reset to 0.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Track subtitle batch translation progress.")
    parser.add_argument("batches_dir", type=Path, help="Directory with meta.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show progress and next batch")

    mark_parser = sub.add_parser("mark", help="Mark batch N as completed")
    mark_parser.add_argument("batch", type=int, help="Batch number (1-based)")

    sub.add_parser("reset", help="Reset progress to 0")

    args = parser.parse_args()
    if not args.batches_dir.is_dir():
        print(f"Error: batches dir not found: {args.batches_dir}", file=sys.stderr)
        return 1

    try:
        if args.command == "status":
            return cmd_status(args.batches_dir)
        if args.command == "mark":
            return cmd_mark(args.batches_dir, args.batch)
        if args.command == "reset":
            return cmd_reset(args.batches_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Side-by-side spot-check for pivotal scenes from context.md."""

import argparse
import json
import re
import sys
from pathlib import Path

from sub_common import load_meta, parse_range, parse_time_to_ms

CUE_RANGE_PATTERN = re.compile(r"(?:cue\s*)?(\d+)\s*[-–]\s*(\d+)", re.IGNORECASE)
CUE_SINGLE_PATTERN = re.compile(r"(?:cue\s*)?#?\s*(\d+)\b", re.IGNORECASE)
TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)\s*[-–]\s*(\d{1,2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)"
)


def extract_pivotal_specs(context_text: str) -> list[dict]:
    specs: list[dict] = []
    in_section = False

    for line in context_text.splitlines():
        if line.strip().startswith("## Pivotal scenes"):
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            break
        if not in_section or not line.strip().startswith("|"):
            continue
        if "---" in line or "cue range" in line.lower():
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("...", ""):
            continue

        scene = cells[0]
        locator = cells[1]
        spec: dict = {"scene": scene, "cue_ids": set()}

        match = CUE_RANGE_PATTERN.search(locator)
        if match:
            start_id, end_id = int(match.group(1)), int(match.group(2))
            spec["cue_ids"] = set(range(start_id, end_id + 1))
        else:
            for single in CUE_SINGLE_PATTERN.finditer(locator):
                spec["cue_ids"].add(int(single.group(1)))

        time_match = TIME_RANGE_PATTERN.search(locator)
        if time_match:
            spec["time_start"] = time_match.group(1)
            spec["time_end"] = time_match.group(2)

        if spec["cue_ids"] or spec.get("time_start"):
            specs.append(spec)

    return specs


def load_cue_maps(batches_dir: Path, meta: dict) -> tuple[dict[int, dict], dict[int, str]]:
    source: dict[int, dict] = {}
    translated: dict[int, str] = {}

    for batch_name in meta.get("batches", []):
        src_path = batches_dir / batch_name
        vi_path = batches_dir / batch_name.replace(".json", ".vi.json")
        if not src_path.is_file():
            continue

        batch = json.loads(src_path.read_text(encoding="utf-8"))
        for cue in batch.get("cues", []):
            source[cue["id"]] = cue

        if vi_path.is_file():
            vi_batch = json.loads(vi_path.read_text(encoding="utf-8"))
            for cue in vi_batch.get("cues", []):
                translated[cue["id"]] = cue.get("text", "")

    return source, translated


def cues_in_time_range(source: dict[int, dict], start_ms: int, end_ms: int) -> set[int]:
    ids: set[int] = set()
    for cue_id, cue in source.items():
        try:
            cue_start = parse_time_to_ms(cue["start"])
            cue_end = parse_time_to_ms(cue["end"])
        except ValueError:
            continue
        if cue_start < end_ms and cue_end > start_ms:
            ids.add(cue_id)
    return ids


def print_cues(title: str, cue_ids: list[int], source: dict, translated: dict[int, str]) -> None:
    print(f"\n=== {title} ({len(cue_ids)} cues) ===")
    if not cue_ids:
        print("  (no cues matched)")
        return

    for cue_id in cue_ids:
        cue = source.get(cue_id)
        if not cue:
            print(f"  [{cue_id}] (not in batches — check range/split)")
            continue
        src_text = cue.get("text", "").replace("\\N", " | ")
        vi_text = translated.get(cue_id, "(not translated yet)")
        print(f"  [{cue_id}] {cue.get('start')} → {cue.get('end')}")
        print(f"    SRC: {src_text[:120]}")
        print(f"    VI : {vi_text[:120]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Spot-check pivotal scenes from context.md.")
    parser.add_argument("batches_dir", type=Path, help="Directory with context.md and batches")
    parser.add_argument(
        "--context",
        type=Path,
        default=None,
        help="Path to context.md (default: <batches_dir>/context.md)",
    )
    parser.add_argument(
        "--max-per-scene",
        type=int,
        default=12,
        help="Max cues to print per scene (default: 12)",
    )
    args = parser.parse_args()

    batches_dir = args.batches_dir
    context_path = args.context or (batches_dir / "context.md")
    if not context_path.is_file():
        print(f"Error: context not found: {context_path}", file=sys.stderr)
        return 1

    try:
        meta = load_meta(batches_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    specs = extract_pivotal_specs(context_path.read_text(encoding="utf-8"))
    if not specs:
        print("No pivotal scene cue ranges found in context.md (fill ## Pivotal scenes table).")
        return 1

    source, translated = load_cue_maps(batches_dir, meta)
    print(f"Loaded {len(source)} source cues, {len(translated)} translated.")

    for spec in specs:
        title = spec["scene"]
        cue_ids: set[int] = set(spec.get("cue_ids") or [])
        if spec.get("time_start") and spec.get("time_end"):
            start_ms, end_ms = parse_range(f"{spec['time_start']}-{spec['time_end']}")
            cue_ids |= cues_in_time_range(source, start_ms, end_ms)

        ordered = sorted(cue_ids)
        if len(ordered) > args.max_per_scene:
            ordered = ordered[: args.max_per_scene]
            title = f"{title} (first {args.max_per_scene})"

        print_cues(title, ordered, source, translated)

    missing = sum(1 for cue_id in source if cue_id not in translated)
    if missing:
        print(f"\nNote: {missing} cues not translated yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

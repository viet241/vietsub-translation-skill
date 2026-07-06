#!/usr/bin/env python3
"""Merge translated JSON batches back into a subtitle file."""

import argparse
import json
import sys
from pathlib import Path

import pysubs2

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from sub_common import load_meta  # noqa: E402


def load_translations(batches_dir: Path, meta: dict) -> dict[int, str]:
    translations: dict[int, str] = {}
    missing_batches: list[str] = []

    for batch_name in meta.get("batches", []):
        vi_name = batch_name.replace(".json", ".vi.json")
        vi_path = batches_dir / vi_name
        if not vi_path.is_file():
            missing_batches.append(vi_name)
            continue

        batch = json.loads(vi_path.read_text(encoding="utf-8"))
        for cue in batch.get("cues", []):
            cue_id = cue["id"]
            if cue_id in translations:
                raise ValueError(f"Duplicate cue id {cue_id} in {vi_name}")
            translations[cue_id] = cue["text"]

    if missing_batches and not meta.get("partial_job"):
        raise FileNotFoundError(
            "Missing translated batch files:\n  " + "\n  ".join(missing_batches)
        )
    return translations


def expected_cue_ids_from_batches(batches_dir: Path, meta: dict) -> set[int]:
    ids: set[int] = set()
    for batch_name in meta.get("batches", []):
        batch_path = batches_dir / batch_name
        if not batch_path.is_file():
            continue
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        for cue in batch.get("cues", []):
            ids.add(cue["id"])
    return ids


def merge_subtitles(source: Path, batches_dir: Path, output: Path, encoding: str) -> dict:
    meta = load_meta(batches_dir)
    translations = load_translations(batches_dir, meta)
    partial = bool(meta.get("partial_job"))

    if source.resolve() != Path(meta["source_file"]).resolve():
        print(
            f"Warning: source file differs from meta.source_file ({meta['source_file']})",
            file=sys.stderr,
        )

    subs = pysubs2.load(str(source), encoding=encoding)
    events = [event for event in subs if event.text.strip()]

    if len(events) != meta.get("total_cues_in_source", meta.get("total_cues", 0)):
        if not partial:
            raise ValueError(
                f"Cue count mismatch: source has {len(events)}, "
                f"meta expects {meta.get('total_cues_in_source', meta.get('total_cues'))}"
            )

    if partial:
        expected_ids = expected_cue_ids_from_batches(batches_dir, meta)
        missing = sorted(expected_ids - set(translations))
        if missing:
            raise ValueError(f"Partial job missing translations for cue ids: {missing[:15]}")
        merged_count = 0
        for index, event in enumerate(events):
            cue_id = index + 1
            if cue_id in translations:
                event.text = translations[cue_id]
                merged_count += 1
    else:
        expected_ids = set(range(1, len(events) + 1))
        if set(translations) != expected_ids:
            missing = sorted(expected_ids - set(translations))
            extra = sorted(set(translations) - expected_ids)
            raise ValueError(f"Translation ids mismatch. Missing: {missing[:10]}, extra: {extra[:10]}")

        for index, event in enumerate(events):
            cue_id = index + 1
            event.text = translations[cue_id]
        merged_count = len(events)

    subs.save(str(output), encoding="utf-8")
    return {
        "merged_cues": merged_count,
        "partial_job": partial,
        "output": str(output.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge translated JSON batches into subtitle file.")
    parser.add_argument("source", type=Path, help="Original .srt / .ass / .ssa file")
    parser.add_argument("batches_dir", type=Path, help="Directory with meta.json and batch_*.vi.json")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output subtitle path")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"Error: source not found: {args.source}", file=sys.stderr)
        return 1
    if not args.batches_dir.is_dir():
        print(f"Error: batches dir not found: {args.batches_dir}", file=sys.stderr)
        return 1

    try:
        meta = load_meta(args.batches_dir)
        result = merge_subtitles(args.source, args.batches_dir, args.output, meta.get("encoding", "utf-8"))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result["partial_job"]:
        print(f"Partial merge: updated {result['merged_cues']} cues -> {result['output']}")
    else:
        print(f"Merged {result['merged_cues']} cues -> {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

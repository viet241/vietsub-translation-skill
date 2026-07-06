#!/usr/bin/env python3
"""Split SRT/ASS subtitle files into JSON batches for cue-safe translation."""

import argparse
import json
import re
import sys
from pathlib import Path

import pysubs2

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from sub_common import (  # noqa: E402
    detect_encoding,
    event_overlaps_range,
    parse_range,
    recommend_batch_size,
)


def format_timestamp(ms: int, fmt: str) -> str:
    if fmt == "srt":
        hours = ms // 3_600_000
        ms %= 3_600_000
        minutes = ms // 60_000
        ms %= 60_000
        seconds = ms // 1_000
        millis = ms % 1_000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
    return pysubs2.time.ms_to_str(ms)


def subtitle_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return "srt"
    if suffix in (".ass", ".ssa"):
        return "ass"
    raise ValueError(f"Unsupported format: {suffix}. Use .srt, .ass, or .ssa")


def load_subs(path: Path, encoding: str) -> pysubs2.SSAFile:
    return pysubs2.load(str(path), encoding=encoding)


SPEAKER_TAG_PATTERN = re.compile(r"^\s*-?\s*\[([^\]]+)\]")


def extract_speaker(event: pysubs2.SSAEvent, fmt: str) -> str | None:
    """Best-effort speaker hint for xưng hô decisions."""
    if fmt == "ass" and getattr(event, "name", None):
        name = event.name.strip()
        if name:
            return name

    match = SPEAKER_TAG_PATTERN.match(event.text)
    if match:
        return match.group(1).strip()

    return None


def cue_payload(event: pysubs2.SSAEvent, cue_id: int, fmt: str, prev_text, next_text) -> dict:
    payload = {
        "id": cue_id,
        "start": format_timestamp(event.start, fmt),
        "end": format_timestamp(event.end, fmt),
        "text": event.text,
        "speaker": extract_speaker(event, fmt),
        "prev_text": prev_text,
        "next_text": next_text,
    }
    if fmt == "ass":
        payload["style"] = event.style
    return payload


def split_batches(
    source: Path,
    output_dir: Path,
    batch_size: int | None,
    title: str | None,
    time_range: str | None = None,
    auto_batch_size: bool = False,
) -> dict:
    fmt = subtitle_format(source)
    encoding = detect_encoding(source)
    subs = load_subs(source, encoding)

    all_events = [event for event in subs if event.text.strip()]
    all_texts = [event.text for event in all_events]

    range_meta = None
    selected: list[tuple[int, pysubs2.SSAEvent]] = []
    if time_range:
        range_start_ms, range_end_ms = parse_range(time_range)
        for cue_id, event in enumerate(all_events, start=1):
            if event_overlaps_range(event.start, event.end, range_start_ms, range_end_ms):
                selected.append((cue_id, event))
        range_meta = {
            "start": time_range.split("-")[0].strip(),
            "end": time_range.split("-")[-1].strip(),
            "start_ms": range_start_ms,
            "end_ms": range_end_ms,
        }
    else:
        selected = list(enumerate(all_events, start=1))

    id_to_text = {cue_id: all_texts[cue_id - 1] for cue_id, _ in selected}
    selected_texts = [event.text for _, event in selected]

    use_auto = auto_batch_size or (fmt == "ass" and batch_size is None)
    if use_auto:
        resolved_batch_size, karaoke_stats = recommend_batch_size(fmt, selected_texts, batch_size)
        batch_size_mode = "auto"
    else:
        resolved_batch_size = batch_size or 50
        karaoke_stats = None
        batch_size_mode = "fixed"

    output_dir.mkdir(parents=True, exist_ok=True)

    batch_files: list[str] = []
    batch_count = (
        (len(selected) + resolved_batch_size - 1) // resolved_batch_size if selected else 0
    )

    for batch_index in range(batch_count):
        start = batch_index * resolved_batch_size
        end = min(start + resolved_batch_size, len(selected))
        cues = []
        for offset in range(start, end):
            cue_id, event = selected[offset]
            prev_text = id_to_text.get(cue_id - 1)
            next_text = id_to_text.get(cue_id + 1)
            cues.append(cue_payload(event, cue_id, fmt, prev_text, next_text))

        batch_name = f"batch_{batch_index + 1:03d}.json"
        batch_path = output_dir / batch_name
        batch_path.write_text(
            json.dumps(
                {
                    "batch": batch_index + 1,
                    "batch_total": batch_count,
                    "cues": cues,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        batch_files.append(batch_name)

    meta = {
        "source_file": str(source.resolve()),
        "format": fmt,
        "encoding": encoding,
        "title": title or infer_title(source),
        "total_cues_in_source": len(all_events),
        "total_cues": len(selected),
        "batch_size": resolved_batch_size,
        "batch_size_mode": batch_size_mode,
        "karaoke_stats": karaoke_stats,
        "batch_count": batch_count,
        "batches": batch_files,
        "partial_job": bool(time_range),
        "time_range": range_meta,
        "last_completed_batch": 0,
        "progress_updated_at": None,
    }
    (output_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def infer_title(path: Path) -> str:
    name = path.stem
    name = re.sub(r"\.(vi|en|jp|ja|ko|zh|chs|cht)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[\[\](){}]", " ", name)
    name = re.sub(r"[_\.]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description="Split subtitle file into JSON batches.")
    parser.add_argument("source", type=Path, help="Source .srt / .ass / .ssa file")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <source_stem>_batches/)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Cues per batch (default: 50 for SRT; ASS uses auto unless set)",
    )
    parser.add_argument(
        "--auto-batch-size",
        action="store_true",
        help="ASS: shrink batch size when \\k karaoke density is high (default for ASS)",
    )
    parser.add_argument("--title", type=str, default=None, help="Movie/show title for research context")
    parser.add_argument(
        "--range",
        type=str,
        default=None,
        help="Time range to split, e.g. 00:15:00-00:45:00 (keeps original cue ids)",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"Error: file not found: {args.source}", file=sys.stderr)
        return 1
    if args.batch_size is not None and args.batch_size < 1:
        print("Error: --batch-size must be >= 1", file=sys.stderr)
        return 1

    output_dir = args.output_dir or args.source.parent / f"{args.source.stem}_batches"
    try:
        meta = split_batches(
            args.source,
            output_dir,
            args.batch_size,
            args.title,
            args.range,
            auto_batch_size=args.auto_batch_size,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Split {meta['total_cues']} cues into {meta['batch_count']} batches")
    print(f"Batch size: {meta['batch_size']} ({meta['batch_size_mode']})")
    if meta.get("karaoke_stats"):
        ks = meta["karaoke_stats"]
        print(
            f"  Karaoke density: {ks['cues_with_karaoke']}/{ks['total_cues']} cues with \\k "
            f"(avg {ks['avg_k_tags']:.1f} tags/cue)"
        )
    if meta.get("partial_job"):
        tr = meta["time_range"]
        print(f"Partial range: {tr['start']} – {tr['end']} (source has {meta['total_cues_in_source']} cues)")
    print(f"Title hint: {meta['title']}")
    print(f"Output: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

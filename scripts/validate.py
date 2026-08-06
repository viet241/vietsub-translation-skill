#!/usr/bin/env python3
"""Validate translated subtitle output against source structure."""

import argparse
import json
import re
import sys
from pathlib import Path

import chardet
import pysubs2

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from sub_common import mark_progress  # noqa: E402

ASS_TAG_PATTERN = re.compile(r"\{[^}]*\}")
KARAOKE_TAG_PATTERN = re.compile(r"\\[kK][fF]?\d+")
FORBIDDEN_TABLE_PATTERN = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$"
)

# Built-in xưng hô / tone patterns. Each entry: (regex, message, severity)
# severity: "error" or "warning"
DEFAULT_XUNGHO_RULES: list[tuple[str, str, str]] = [
    (
        r"(?i)\bvâng thưa\s*[,.]?\s*$",
        'Incomplete honorific: "vâng thưa" needs an object (e.g. "vâng ạ", "thưa thầy")',
        "error",
    ),
    (
        r"(?i)\bkhông thưa\s*[,.]?\s*$",
        'Incomplete honorific: "không thưa" needs an object (e.g. "không ạ", "không thưa thầy")',
        "error",
    ),
    (
        r"(?i)\bông\s+Clark\b",
        'School context: use "thầy Clark", not "ông Clark"',
        "warning",
    ),
    (
        r"(?i)\btôi là ông\s+Clark\b",
        'Self-intro as teacher: use "Tôi là thầy Clark"',
        "error",
    ),
    (
        r"(?i)(?<![\wÀ-ỹ])bạn(?![\wÀ-ỹ])",
        'Neutral "bạn" detected — use relationship-specific pronoun from context.md',
        "warning",
    ),
    (
        r"(?i)gọi thầy là thưa\b",
        'Broken phrasing: "gọi thầy" or "thưa thầy", not "gọi thầy là thưa"',
        "error",
    ),
]


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()
    guess = chardet.detect(raw)
    encoding = guess.get("encoding") or "utf-8"
    for candidate in (encoding, "utf-8-sig", "utf-8", "cp1252"):
        try:
            raw.decode(candidate)
            return candidate
        except UnicodeDecodeError:
            continue
    return "utf-8"


def load_events(path: Path, encoding: str) -> list[pysubs2.SSAEvent]:
    subs = pysubs2.load(str(path), encoding=encoding)
    return [event for event in subs if event.text.strip()]


def count_tags(text: str) -> tuple[int, int]:
    return len(ASS_TAG_PATTERN.findall(text)), len(KARAOKE_TAG_PATTERN.findall(text))


def batch_number_from_name(name: str) -> int | None:
    match = re.search(r"batch_(\d+)", name)
    return int(match.group(1)) if match else None


def validate_batches(batches_dir: Path, through_batch: int | None = None) -> list[str]:
    errors: list[str] = []
    context_path = batches_dir / "context.md"
    if not context_path.is_file():
        errors.append(
            "Missing context.md in batches dir — write context (Step 0) before split or translate"
        )
    else:
        import importlib.util

        check_path = Path(__file__).parent / "check_context.py"
        if check_path.is_file():
            spec = importlib.util.spec_from_file_location("check_context", check_path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            for issue in mod.check_context(context_path, strict=False):
                if "recommended" in issue:
                    continue
                errors.append(f"context.md: {issue}")

    meta_path = batches_dir / "meta.json"
    if not meta_path.is_file():
        return [f"Missing {meta_path}"]

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    seen_ids: set[int] = set()
    partial = bool(meta.get("partial_job"))
    in_progress = through_batch is not None

    for batch_name in meta.get("batches", []):
        batch_num = batch_number_from_name(batch_name)
        if through_batch is not None and batch_num is not None and batch_num > through_batch:
            continue

        vi_name = batch_name.replace(".json", ".vi.json")
        vi_path = batches_dir / vi_name
        if not vi_path.is_file():
            if in_progress:
                continue
            errors.append(f"Missing translated batch: {vi_name}")
            continue

        batch = json.loads(vi_path.read_text(encoding="utf-8"))
        for cue in batch.get("cues", []):
            cue_id = cue.get("id")
            text = cue.get("text", "")
            if cue_id in seen_ids:
                errors.append(f"Duplicate cue id {cue_id} in {vi_name}")
            seen_ids.add(cue_id)
            if not text.strip():
                errors.append(f"Empty translation for cue id {cue_id} in {vi_name}")

    if in_progress:
        return errors

    expected = meta.get("total_cues", 0)
    if not partial and len(seen_ids) != expected:
        errors.append(f"Batch ids count {len(seen_ids)} != meta.total_cues {expected}")

    return errors


def parse_forbidden_defaults(context_path: Path) -> list[tuple[str, str, str]]:
    """Parse ## Forbidden defaults table from context.md into audit rules."""
    if not context_path.is_file():
        return []

    rules: list[tuple[str, str, str]] = []
    in_section = False
    for line in context_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("## Forbidden defaults"):
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            break
        if not in_section:
            continue
        if line.strip().startswith("|") and "---" not in line:
            match = FORBIDDEN_TABLE_PATTERN.match(line.strip())
            if not match:
                continue
            never, use_instead, when = (cell.strip() for cell in match.groups())
            if never.lower() in ("never use", "..."):
                continue
            phrase = never.strip('"').strip("'")
            if not phrase or phrase.startswith("..."):
                continue
            escaped = re.escape(phrase)
            rules.append(
                (
                    escaped,
                    f'Forbidden default "{phrase}" — use: {use_instead} ({when})',
                    "warning",
                )
            )
    return rules


# Signs of broken post-processing or bad regex glossary (e.g. `[gentle music]` as char class)
CORRUPTION_PATTERNS: list[tuple[str, str]] = [
    (r"\[[^\]]*\[", "Nested `[` inside translated text — likely broken glossary regex"),
    (r"\{nhạc", "Malformed tag starting with `{nhạc`"),
    (r"\[nhạc\[", "Nested `[nhạc[` corruption"),
    (r"\]\w+\[", "Adjacent bracket fragments like `]word[`"),
]


def audit_corruption(
    batches_dir: Path,
    source_dir: Path | None = None,
    through_batch: int | None = None,
) -> list[tuple[str, str]]:
    """Detect corrupted translation output (regex glossary bugs, tag breakage)."""
    issues: list[tuple[str, str]] = []
    vi_files = sorted(batches_dir.glob("batch_*.vi.json"))
    if not vi_files:
        return issues

    for vi_path in vi_files:
        batch_num = batch_number_from_name(vi_path.name)
        if through_batch is not None and batch_num is not None and batch_num > through_batch:
            continue
        vi_data = json.loads(vi_path.read_text(encoding="utf-8"))

        for cue in vi_data.get("cues", []):
            text = cue.get("text", "")
            cue_id = cue.get("id")
            for pattern, message in CORRUPTION_PATTERNS:
                if re.search(pattern, text):
                    issues.append(
                        (
                            f"Cue {cue_id} in {vi_path.name}: {message} — \"{text[:70]}\"",
                            "error",
                        )
                    )
                    break

    return issues


def audit_xungho(batches_dir: Path, through_batch: int | None = None) -> list[tuple[str, str]]:
    """Audit translated batches for xưng hô and tone issues.

    Returns list of (message, severity) where severity is 'error' or 'warning'.
    """
    issues: list[tuple[str, str]] = []
    context_path = batches_dir / "context.md"
    rules = list(DEFAULT_XUNGHO_RULES)
    rules.extend(parse_forbidden_defaults(context_path))

    if not context_path.is_file():
        issues.append(
            (
                "context.md not found in batches dir — xưng hô audit uses built-in rules only",
                "warning",
            )
        )

    vi_files = sorted(batches_dir.glob("batch_*.vi.json"))
    if not vi_files:
        if through_batch is None:
            issues.append(("No batch_*.vi.json files found for xưng hô audit", "error"))
        return issues

    for vi_path in vi_files:
        batch_num = batch_number_from_name(vi_path.name)
        if through_batch is not None and batch_num is not None and batch_num > through_batch:
            continue
        batch = json.loads(vi_path.read_text(encoding="utf-8"))
        for cue in batch.get("cues", []):
            text = cue.get("text", "")
            cue_id = cue.get("id")
            for pattern, message, severity in rules:
                if re.search(pattern, text):
                    issues.append(
                        (
                            f"Cue {cue_id} in {vi_path.name}: {message} — \"{text[:60]}\"",
                            severity,
                        )
                    )

    return issues


def validate_files(source: Path, output: Path) -> list[str]:
    errors: list[str] = []
    source_events = load_events(source, detect_encoding(source))
    output_events = load_events(output, detect_encoding(output))

    if len(source_events) != len(output_events):
        errors.append(
            f"Cue count mismatch: source={len(source_events)}, output={len(output_events)}"
        )
        return errors

    for index, (src, out) in enumerate(zip(source_events, output_events), start=1):
        if src.start != out.start or src.end != out.end:
            errors.append(f"Cue {index}: timestamp mismatch")
        if src.style != out.style:
            errors.append(f"Cue {index}: ASS style mismatch ({src.style} vs {out.style})")

        src_tags, src_karaoke = count_tags(src.text)
        out_tags, out_karaoke = count_tags(out.text)
        if src_tags != out_tags:
            errors.append(f"Cue {index}: ASS override tag count mismatch ({src_tags} vs {out_tags})")
        if src_karaoke != out_karaoke:
            errors.append(f"Cue {index}: karaoke tag count mismatch ({src_karaoke} vs {out_karaoke})")
        if not out.text.strip():
            errors.append(f"Cue {index}: empty output text")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate subtitle translation output.")
    parser.add_argument("source", type=Path, help="Original subtitle file")
    parser.add_argument(
        "target",
        type=Path,
        nargs="?",
        default=None,
        help="Merged output subtitle file (optional if --batches-dir is set)",
    )
    parser.add_argument(
        "--batches-dir",
        type=Path,
        default=None,
        help="Validate translated JSON batches before merge",
    )
    parser.add_argument(
        "--audit-xungho",
        action="store_true",
        help="Audit xưng hô / tone patterns in translated batches (requires --batches-dir)",
    )
    parser.add_argument(
        "--fail-on-xungho",
        action="store_true",
        help="Treat xưng hô warnings as errors (use with --audit-xungho)",
    )
    parser.add_argument(
        "--audit-corruption",
        action="store_true",
        help="Detect corrupted translations (nested brackets, tag breakage)",
    )
    parser.add_argument(
        "--through-batch",
        type=int,
        default=None,
        metavar="N",
        help="Only audit batches 001..N (for incremental checks during translation)",
    )
    parser.add_argument(
        "--after-batch",
        type=int,
        default=None,
        metavar="N",
        help="After batch N: corruption audit through N + mark progress (replaces separate progress mark)",
    )
    args = parser.parse_args()

    if args.after_batch is not None:
        if not args.batches_dir:
            print("Error: --after-batch requires --batches-dir", file=sys.stderr)
            return 1
        if args.after_batch < 1:
            print("Error: --after-batch must be >= 1", file=sys.stderr)
            return 1
        args.through_batch = args.after_batch
        args.audit_corruption = True

    errors: list[str] = []
    if args.batches_dir:
        errors.extend(validate_batches(args.batches_dir, through_batch=args.through_batch))
        if args.audit_corruption:
            for message, severity in audit_corruption(
                args.batches_dir, through_batch=args.through_batch
            ):
                if severity == "error":
                    errors.append(f"Corruption: {message}")
                else:
                    print(f"Corruption warning: {message}")
        if args.audit_xungho:
            xungho_issues = audit_xungho(args.batches_dir, through_batch=args.through_batch)
            for message, severity in xungho_issues:
                if severity == "error" or args.fail_on_xungho:
                    errors.append(f"Xưng hô {severity}: {message}")
                else:
                    print(f"Xưng hô warning: {message}")
    if args.target:
        if not args.target.is_file():
            print(f"Error: target not found: {args.target}", file=sys.stderr)
            return 1
        errors.extend(validate_files(args.source, args.target))

    if not args.batches_dir and not args.target:
        print("Error: provide target output file and/or --batches-dir", file=sys.stderr)
        return 1

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    if args.after_batch is not None:
        vi_path = args.batches_dir / f"batch_{args.after_batch:03d}.vi.json"
        if not vi_path.is_file():
            print(f"Error: missing {vi_path.name} — translate before --after-batch", file=sys.stderr)
            return 1
        try:
            mark_progress(args.batches_dir, args.after_batch)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Batch {args.after_batch} OK — progress marked.")

    print("Validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check subtitle file encoding before split — catch GBK/UTF-8 mojibake early."""

import argparse
import sys
from pathlib import Path

from sub_common import detect_encoding_info


def assess(path: Path) -> tuple[int, list[str]]:
    info = detect_encoding_info(path)
    issues: list[str] = []
    exit_code = 0

    encoding = (info["encoding"] or "").lower()
    confidence = info["confidence"]
    utf8_ok = info["utf8_ok"]
    mojibake_hits = info["mojibake_hits"]
    best_encoding = (info["best_encoding"] or "").lower()
    cjk_count = info["cjk_count"]
    utf8_cjk = info["utf8_cjk"]

    print(f"File: {path}")
    print(f"Size: {info['byte_size']:,} bytes")
    print(f"chardet: {info['encoding']} (confidence {confidence:.0%})")

    if not utf8_ok:
        exit_code = 1
        issues.append(
            f"File is not valid UTF-8. Detected {info['encoding']} — convert before split."
        )
    elif encoding not in ("utf-8", "utf-8-sig", "ascii") and confidence >= 0.7:
        if cjk_count > utf8_cjk + 5 and mojibake_hits >= 3:
            exit_code = 1
            issues.append(
                f"Likely mojibake: UTF-8 decode has {mojibake_hits} suspicious markers "
                f"but {best_encoding} has more CJK ({cjk_count} vs {utf8_cjk})."
            )
        elif mojibake_hits >= 8:
            exit_code = 1
            issues.append(
                f"High mojibake score ({mojibake_hits}) — file may be GBK/GB18030 read as UTF-8."
            )

    if exit_code == 0 and utf8_ok and mojibake_hits > 0:
        print(f"Note: {mojibake_hits} minor mojibake markers — spot-check a few lines.")

    if exit_code == 1:
        print("\nRecommended fix:")
        if "gb" in encoding or "gb" in best_encoding:
            print(f"  iconv -f GB18030 -t UTF-8 {path.name} > {path.stem}.utf8{path.suffix}")
        else:
            print(f"  Re-save as UTF-8, then run split on the UTF-8 copy.")
        print("  python3 <skill-root>/scripts/preflight_encoding.py <utf8-file>")

    return exit_code, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight subtitle encoding check.")
    parser.add_argument("source", type=Path, help="Source .srt / .ass / .ssa file")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"Error: file not found: {args.source}", file=sys.stderr)
        return 1

    code, issues = assess(args.source)
    if issues:
        print("\nPreflight FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        return code

    print("\nPreflight OK — safe to split.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

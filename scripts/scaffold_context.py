#!/usr/bin/env python3
"""Scaffold context.md from template + subtitle skim (agent completes via research)."""

import argparse
import re
import sys
from pathlib import Path

import pysubs2

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from sub_common import detect_encoding, extract_glossary_candidates  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_ROOT / "templates" / "context.template.md"
GLOSSARY_TEMPLATE = SKILL_ROOT / "templates" / "glossary.template.md"

NAME_PATTERN = re.compile(
    r"(?:Mr\.|Mrs\.|Ms\.|Miss|Dr\.)\s+[A-Z][a-z]+|"
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)
BRACKET_SPEAKER = re.compile(r"\[([^\]]+)\]")
SOUND_CUE = re.compile(r"^\[[^\]]+\]$")

GLOSSARY_POINTER = (
    "See `glossary.md` for skimmed terminology (verify Vietnamese via web search).\n\n"
    "| Source | Vietnamese | Keep / translate | Notes |\n"
    "|--------|------------|------------------|-------|\n"
    "| (high-frequency terms) | ... | translate | in glossary.md |\n"
)


def skim_subtitle(path: Path) -> dict:
    encoding = detect_encoding(path)
    subs = pysubs2.load(str(path), encoding=encoding)
    texts = [e.text for e in subs if e.text.strip()]

    names: set[str] = set()
    speakers: set[str] = set()
    samples: list[str] = []

    for text in texts:
        for m in BRACKET_SPEAKER.finditer(text):
            tag = m.group(1).strip()
            if not SOUND_CUE.match(f"[{tag}]"):
                speakers.add(tag)
        for m in NAME_PATTERN.finditer(text):
            word = m.group(0)
            if word.lower() not in {"i", "the", "new", "york", "yes", "no", "okay"}:
                names.add(word)
        if len(samples) < 8 and 20 < len(text) < 120:
            samples.append(text.replace("\\N", " ")[:100])

    glossary_candidates = extract_glossary_candidates(texts)

    return {
        "cue_count": len(texts),
        "texts": texts,
        "names": sorted(names)[:25],
        "speakers": sorted(speakers)[:20],
        "samples": samples,
        "glossary_candidates": glossary_candidates,
    }


def build_glossary(title: str, candidates: list[tuple[str, int, str]]) -> str:
    if GLOSSARY_TEMPLATE.is_file():
        header = GLOSSARY_TEMPLATE.read_text(encoding="utf-8")
        header = header.replace("<Title>", title)
    else:
        header = f"# Glossary: {title}\n\n"

    rows = []
    for term, count, kind in candidates:
        note = f"skim ×{count}"
        if kind == "cjk":
            note += ", CJK"
        rows.append(f"| {term} | ... | translate | {note} |")

    if not rows:
        rows.append("| ... | ... | translate | verify via web |")

    body = "\n".join(rows)
    if "| Source |" in header:
        return header.replace("| ... | ... | translate | verify via web |", body)
    return header.rstrip() + "\n\n| Source | Vietnamese | Keep / translate | Notes |\n|--------|------------|------------------|-------|\n" + body + "\n"


def build_scaffold(title: str, skim: dict, *, with_glossary: bool) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    out = template.replace("<Title>", title).replace("<Year if known>", "")

    if skim["names"] or skim["speakers"]:
        hint_rows = []
        for n in skim["names"][:12]:
            hint_rows.append(f"| {n} | (research role) | | | skim from sub |")
        for s in skim["speakers"][:8]:
            if s not in skim["names"]:
                hint_rows.append(f"| [{s}] | speaker tag | | | from ASS tag |")
        if hint_rows:
            char_section = "\n".join(hint_rows)
            out = out.replace(
                "| ... | ... | ... | polite / rough / comic / technical | ... |",
                char_section,
            )

    if with_glossary and skim["glossary_candidates"]:
        out = out.replace(
            "> **Large glossaries:** put bulk entries in `glossary.md` (same folder). Keep only high-frequency terms here. Agent reads both files.\n\n"
            "| Source | Vietnamese | Keep / translate | Notes |\n"
            "|--------|------------|------------------|-------|\n"
            "| ... | ... | ... | ... |\n\n"
            "<!-- If using glossary.md: replace table above with one line: \"See glossary.md for full term list.\" -->",
            GLOSSARY_POINTER,
        )

    notes = [
        f"<!-- Auto-scaffold: {skim['cue_count']} cues skimmed. Agent MUST complete all sections via web search + full sub read. -->",
        "",
        "## Research notes (from subtitle skim)",
        "",
        f"- **Cue count:** {skim['cue_count']}",
        "",
        "### Name / tag hints (verify and expand)",
        "",
    ]
    for n in skim["names"][:15]:
        notes.append(f"- {n}")
    for s in skim["speakers"][:10]:
        notes.append(f"- [{s}]")
    notes.append("")
    notes.append("### Sample dialogue lines (for tone / register research)")
    notes.append("")
    for s in skim["samples"]:
        notes.append(f"- {s}")
    notes.append("")

    return out.rstrip() + "\n\n" + "\n".join(notes) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold context.md from template + sub skim.")
    parser.add_argument("subtitle", type=Path, help="Source .srt / .ass / .ssa")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output context.md path")
    parser.add_argument("--title", type=str, default=None, help="Title override")
    parser.add_argument(
        "--glossary",
        action="store_true",
        help="Also write glossary.md beside context.md from repeated terms in the sub",
    )
    args = parser.parse_args()

    if not args.subtitle.is_file():
        print(f"Error: subtitle not found: {args.subtitle}", file=sys.stderr)
        return 1
    if not TEMPLATE.is_file():
        print(f"Error: template not found: {TEMPLATE}", file=sys.stderr)
        return 1

    title = args.title or args.subtitle.stem
    skim = skim_subtitle(args.subtitle)
    use_glossary = args.glossary and bool(skim["glossary_candidates"])
    content = build_scaffold(title, skim, with_glossary=use_glossary)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Scaffolded: {args.output.resolve()}")
    print(f"  Cues skimmed: {skim['cue_count']}")

    if args.glossary:
        glossary_path = args.output.parent / "glossary.md"
        if use_glossary:
            glossary_path.write_text(
                build_glossary(title, skim["glossary_candidates"]),
                encoding="utf-8",
            )
            print(f"  Glossary: {glossary_path.resolve()} ({len(skim['glossary_candidates'])} candidates)")
        else:
            print("  Glossary: no repeated terms found — glossary.md not created")

    print("  Next: complete all sections via research, then run check_context.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

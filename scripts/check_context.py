#!/usr/bin/env python3
"""Verify context.md meets minimum quality before split/translate."""

import argparse
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from sub_common import CONTEXT_SIZE_STRICT_CHARS, CONTEXT_SIZE_WARN_CHARS  # noqa: E402

REQUIRED_SECTIONS = [
    "Translation register",
    "Synopsis",
    "Characters",
    "xưng hô",
    "Register phases",
    "Domains & terminology",
    "Slang & idiom",
    "Tone & emotional",
    "Forbidden defaults",
    "Glossary",
]

OPTIONAL_BUT_RECOMMENDED = [
    "Setting & culture",
    "Songs, rap",
    "Pivotal scenes",
]

PLACEHOLDER_PATTERNS = [
    r"<Title>",
    r"<Year if known>",
    r"<register>",
    r"<3–5 sentences",
    r"^\|\s*\.\.\.\s*\|",
]


def section_present(text: str, keyword: str) -> bool:
    key = keyword.lower()
    for line in text.splitlines():
        if line.startswith("## ") and key in line.lower():
            return True
    return False


def extract_section(text: str, keyword: str) -> str:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and keyword.lower() in line.lower():
            start = i + 1
            break
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def count_table_rows(section_body: str) -> int:
    rows = 0
    for line in section_body.splitlines():
        line = line.strip()
        if line.startswith("|") and "---" not in line and "..." not in line:
            headerish = line.lower()
            if "speaker" in headerish or "name" in headerish or "domain" in headerish:
                continue
            if "never use" in headerish or "source" in headerish:
                continue
            if "phase" in headerish and "approx" in headerish:
                continue
            rows += 1
    return rows


def check_context(path: Path, strict: bool) -> list[str]:
    issues: list[str] = []
    if not path.is_file():
        return [f"Missing context file: {path}"]

    text = path.read_text(encoding="utf-8")
    if len(text.strip()) < 800:
        issues.append("context.md too short (<800 chars) — expand to full translator brief")

    for section in REQUIRED_SECTIONS:
        if not section_present(text, section):
            issues.append(f"Missing required section: ## {section}")

    for section in OPTIONAL_BUT_RECOMMENDED:
        if not section_present(text, section):
            issues.append(f"Missing recommended section: ## {section}")

    phases = extract_section(text, "Register phases")
    if phases and count_table_rows(phases) < 2:
        issues.append(
            "Register phases table needs at least 2 phases (relationships change mid-story)"
        )

    chars = extract_section(text, "Characters")
    if chars and count_table_rows(chars) < 2:
        issues.append("Characters table needs at least 2 filled rows")

    glossary = extract_section(text, "Glossary")
    glossary_path = path.parent / "glossary.md"
    uses_external_glossary = "glossary.md" in glossary

    if uses_external_glossary and not glossary_path.is_file():
        issues.append("context.md references glossary.md but file is missing")
    elif glossary_path.is_file():
        ext_rows = count_table_rows(glossary_path.read_text(encoding="utf-8"))
        if ext_rows < 3:
            issues.append("glossary.md needs at least 3 filled entries")
    elif glossary and count_table_rows(glossary) < 3:
        issues.append("Glossary needs at least 3 filled entries (or move to glossary.md)")

    size = len(text)
    if size > CONTEXT_SIZE_STRICT_CHARS and not glossary_path.is_file():
        issues.append(
            f"context.md too large ({size:,} chars, max ~{CONTEXT_SIZE_STRICT_CHARS:,}) — "
            "move bulk glossary to glossary.md beside context.md"
        )
    elif size > CONTEXT_SIZE_WARN_CHARS:
        issues.append(
            f"context.md large ({size:,} chars) — recommended: move glossary to glossary.md"
        )

    placeholder_hits = sum(1 for pat in PLACEHOLDER_PATTERNS if re.search(pat, text, re.M))
    if placeholder_hits >= 2:
        issues.append(
            f"Template placeholders still present ({placeholder_hits} hits) — complete research first"
        )

    if strict:
        return [i for i in issues if "recommended" not in i]
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check context.md quality before translation.")
    parser.add_argument("context", type=Path, help="Path to context.md")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing recommended sections as errors",
    )
    args = parser.parse_args()

    issues = check_context(args.context, args.strict)
    if issues:
        print("context.md check failed:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("context.md check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

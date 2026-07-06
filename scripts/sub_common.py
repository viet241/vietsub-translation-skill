"""Shared helpers for vietsub scripts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import chardet

MOJIBAKE_MARKERS = re.compile(
    r"[ÃÂÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÙÚÛÜÝÞß]|ï¼|ã€|æ—|è¯|ä¸"
)
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
KARAOKE_TAG_PATTERN = re.compile(r"\\[kK][fF]?\d+")
ASS_OVERRIDE_PATTERN = re.compile(r"\{[^}]*\}")
CJK_TERM_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,8}")
EN_TERM_PATTERN = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b|\b[a-z]{5,}\b"
)

EN_STOPWORDS = frozenset(
    {
        "about", "after", "again", "against", "because", "before", "being",
        "between", "could", "every", "first", "found", "great", "have",
        "having", "little", "might", "never", "other", "really", "right",
        "should", "still", "their", "there", "these", "think", "those",
        "through", "under", "until", "very", "want", "what", "when",
        "where", "which", "while", "with", "would", "your", "hello",
        "thank", "thanks", "please", "sorry", "okay", "yes", "yeah",
    }
)

CONTEXT_SIZE_WARN_CHARS = 12_000
CONTEXT_SIZE_STRICT_CHARS = 18_000


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


def detect_encoding_info(path: Path) -> dict:
    raw = path.read_bytes()
    guess = chardet.detect(raw)
    encoding = guess.get("encoding") or "utf-8"
    confidence = float(guess.get("confidence") or 0.0)

    utf8_ok = True
    try:
        utf8_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_ok = False
        utf8_text = ""

    best_text = utf8_text
    best_encoding = "utf-8"
    if not utf8_ok:
        for candidate in (encoding, "gb18030", "gbk", "big5", "cp1252"):
            if not candidate:
                continue
            try:
                best_text = raw.decode(candidate)
                best_encoding = candidate
                break
            except UnicodeDecodeError:
                continue

    sample = best_text[:8000] if best_text else ""
    mojibake_hits = len(MOJIBAKE_MARKERS.findall(sample))
    cjk_count = len(CJK_PATTERN.findall(sample))

    utf8_cjk = len(CJK_PATTERN.findall(utf8_text[:8000])) if utf8_ok else 0

    return {
        "encoding": encoding,
        "confidence": confidence,
        "utf8_ok": utf8_ok,
        "best_encoding": best_encoding,
        "mojibake_hits": mojibake_hits,
        "cjk_count": cjk_count,
        "utf8_cjk": utf8_cjk,
        "byte_size": len(raw),
    }


def parse_time_to_ms(value: str) -> int:
    value = value.strip().replace(".", ",")
    if "," in value:
        time_part, frac = value.split(",", 1)
        millis = int(frac.ljust(3, "0")[:3])
    else:
        time_part = value
        millis = 0

    parts = [int(part) for part in time_part.split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0, parts[0], parts[1]
    else:
        raise ValueError(f"Invalid timestamp: {value}")

    return ((hours * 3600) + (minutes * 60) + seconds) * 1000 + millis


def parse_range(value: str) -> tuple[int, int]:
    value = value.strip()
    for sep in ("-", ",", "–"):
        if sep in value:
            start_raw, end_raw = value.split(sep, 1)
            start_ms = parse_time_to_ms(start_raw.strip())
            end_ms = parse_time_to_ms(end_raw.strip())
            if end_ms <= start_ms:
                raise ValueError(f"Range end must be after start: {value}")
            return start_ms, end_ms
    raise ValueError(f"Invalid range (use START-END): {value}")


def event_overlaps_range(start_ms: int, end_ms: int, range_start: int, range_end: int) -> bool:
    return start_ms < range_end and end_ms > range_start


def load_meta(batches_dir: Path) -> dict:
    meta_path = batches_dir / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing meta.json in {batches_dir}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(batches_dir: Path, meta: dict) -> None:
    (batches_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mark_progress(batches_dir: Path, batch_num: int) -> dict:
    meta = load_meta(batches_dir)
    batch_count = int(meta.get("batch_count", 0))
    if batch_num < 0 or batch_num > batch_count:
        raise ValueError(f"batch_num must be 0..{batch_count}, got {batch_num}")
    meta["last_completed_batch"] = batch_num
    meta["progress_updated_at"] = datetime.now(timezone.utc).isoformat()
    save_meta(batches_dir, meta)
    return meta


def next_batch_hint(meta: dict) -> int | None:
    last = int(meta.get("last_completed_batch", 0))
    total = int(meta.get("batch_count", 0))
    nxt = last + 1
    if nxt > total:
        return None
    return nxt


def strip_ass_markup(text: str) -> str:
    text = ASS_OVERRIDE_PATTERN.sub(" ", text)
    text = KARAOKE_TAG_PATTERN.sub(" ", text)
    return text.replace("\\N", " ").replace("\\n", " ")


def karaoke_stats_for_texts(texts: list[str]) -> dict:
    counts = [len(KARAOKE_TAG_PATTERN.findall(text)) for text in texts]
    total = len(counts)
    with_k = sum(1 for count in counts if count > 0)
    return {
        "total_cues": total,
        "cues_with_karaoke": with_k,
        "karaoke_ratio": (with_k / total) if total else 0.0,
        "avg_k_tags": (sum(counts) / total) if total else 0.0,
        "max_k_tags": max(counts) if counts else 0,
    }


def recommend_batch_size(fmt: str, texts: list[str], requested: int | None = None) -> tuple[int, dict | None]:
    """Return (batch_size, karaoke_stats). stats is None for plain SRT without auto logic."""
    if fmt != "ass":
        return requested or 50, None

    stats = karaoke_stats_for_texts(texts)
    ratio = stats["karaoke_ratio"]
    avg = stats["avg_k_tags"]

    if ratio >= 0.35 or avg >= 2.5:
        auto_size = 15
    elif ratio >= 0.15 or avg >= 1.0:
        auto_size = 22
    else:
        auto_size = 30

    if requested is None:
        return auto_size, stats
    return min(requested, auto_size), stats


def extract_glossary_candidates(
    texts: list[str],
    *,
    min_en_count: int = 3,
    min_cjk_count: int = 2,
    limit: int = 50,
) -> list[tuple[str, int, str]]:
    """Return (term, count, kind) sorted by frequency."""
    from collections import Counter

    cjk_counts: Counter[str] = Counter()
    en_counts: Counter[str] = Counter()

    for text in texts:
        clean = strip_ass_markup(text)
        for term in CJK_TERM_PATTERN.findall(clean):
            if len(term) >= 2:
                cjk_counts[term] += 1
        for term in EN_TERM_PATTERN.findall(clean):
            key = term.lower()
            if key in EN_STOPWORDS:
                continue
            en_counts[term] += 1

    merged: dict[str, tuple[int, str]] = {}
    for term, count in cjk_counts.items():
        if count >= min_cjk_count:
            merged[term] = (count, "cjk")
    for term, count in en_counts.items():
        if count >= min_en_count:
            prev = merged.get(term)
            if prev is None or count > prev[0]:
                merged[term] = (count, "en")

    ranked = sorted(merged.items(), key=lambda item: (-item[1][0], item[0]))
    return [(term, count, kind) for term, (count, kind) in ranked[:limit]]

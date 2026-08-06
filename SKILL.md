---
name: vietsub
description: >-
    Agent-only subtitle translation (SRT/ASS/SSA → Vietnamese). No Google Translate
    or external MT. Uses context.md brief, JSON batches, split/merge/validate scripts.
    Triggers: phụ đề, subtitle translation, SRT, ASS, SSA.
disable-model-invocation: true
---

# Subtitle Translation

Translate subtitle files into **Vietnamese** (any source language → Vietnamese).

**Never translate raw subtitle files line-by-line.** Use the cue-based workflow below.

## Agent-only (hard rule)

All translation **must be performed by the Cursor agent (LLM)** reading `context.md` (+ `glossary.md` if present).

| Allowed | Forbidden |
|---------|-----------|
| Agent writes `batch_NNN.vi.json` cue by cue | `deep_translator`, `googletrans`, `argostranslate`, any MT API |
| Skill scripts (split, merge, validate, progress, spot_check, preflight) | `curl` to translate endpoints, `pip install` MT libs mid-job |
| Agent edits individual cues after audit | Regex bulk-replace on `.vi.json` **instead of** re-translating |

**There is no `translate.py`.** Before merge, report must state **"Translation method: agent-only (LLM). No external MT services used."**

---

## `context.md` — single source of truth

Job-specific rules live here. Priority: `context.md` / `glossary.md` > generic fallbacks below.

1. **Complete `context.md` before split** — never split or translate without it.
2. **Re-read at the start of each batch** (or keep in memory for the session).
3. **Update immediately** when a batch reveals new characters, phases, domains, or glossary terms.
4. Keep `context.md` ≤ ~12K chars; bulk terms → `glossary.md` beside it (agent reads both).

```
preflight_encoding  →  context.md  →  check_context.py  →  split  →  translate  →  validate  →  merge
```

Templates: `templates/context.template.md`, `templates/glossary.template.md`

---

## Install

```bash
python3 -m pip install -r requirements.txt   # macOS/Linux
py -m pip install -r requirements.txt        # Windows
```

Skill root: `~/.cursor/skills/vietsub` (macOS/Linux) or `%USERPROFILE%\.cursor\skills\vietsub` (Windows).

---

## Workflow

```
Task Progress:
- [ ] Step 0: preflight_encoding → scaffold/research → context.md → check_context.py --strict
- [ ] Step 1: split_batches.py (optional --range) → JSON batches
- [ ] Step 2: Translate batches sequentially; progress.py mark; incremental validate every 2–3 batches
- [ ] Step 3: validate.py --audit-corruption (full)
- [ ] Step 4: validate.py --audit-xungho --fail-on-xungho (full)
- [ ] Step 5: spot_check.py → pivotal scenes
- [ ] Step 6: merge_batches.py → output file
- [ ] Step 7: validate.py source + output; final report
```

### Step 0 — Preflight + `context.md`

```bash
python3 <skill-root>/scripts/preflight_encoding.py "input.srt"
python3 <skill-root>/scripts/scaffold_context.py "input.srt" \
  --title "Original Title" --glossary -o "./movie_batches/context.md"
```

Research: read **entire** sub + web search. Fill all sections — especially **Translation register**, **Register phases**, **Relationships & xưng hô**, **Pivotal scenes** (use cue ranges like `120-145`).

```bash
python3 <skill-root>/scripts/check_context.py "./movie_batches/context.md" --strict
```

### Step 1 — Split

```bash
python3 <skill-root>/scripts/split_batches.py "input.srt" \
  --title "Tên phim" -o "./movie_batches"

# ASS/karaoke: auto batch size from \k density (default for .ass)
python3 <skill-root>/scripts/split_batches.py "input.ass" \
  --title "Tên phim" --auto-batch-size -o "./movie_batches"

# Trial segment only (keeps original cue ids; partial merge):
python3 <skill-root>/scripts/split_batches.py "input.srt" \
  --range 00:15:00-00:45:00 -o "./movie_batches"
```

SRT default batch size: **50**. ASS without `--batch-size`: **auto** (15 / 22 / 30 by `\k` density).

### Step 2 — Translate + progress

Resume: `python3 <skill-root>/scripts/progress.py ./movie_batches status`

For each `batch_NNN.json` → `batch_NNN.vi.json` (only edit `text`). Sequential order.

**After each batch** (audit + mark in one step):

```bash
python3 <skill-root>/scripts/validate.py "input.srt" \
  --batches-dir "./movie_batches" --after-batch N
```

**Every 2–3 batches** is enough; use the same command after the latest completed batch.

**Per-cue:** phase → speaker/listener → xưng hô → tone → domain/slang → dialogue vs non-dialogue → meaning+attitude. Preserve ASS tags (`{...}`, `\k`, `\N`).

### Step 3–4 — Full audits

```bash
python3 <skill-root>/scripts/validate.py "input.srt" \
  --batches-dir "./movie_batches" --audit-corruption

python3 <skill-root>/scripts/validate.py "input.srt" \
  --batches-dir "./movie_batches" --audit-xungho --fail-on-xungho
```

Corrupted cues: re-translate from `batch_NNN.json`, not `.vi.json`.

### Step 5 — Spot-check

```bash
python3 <skill-root>/scripts/spot_check.py ./movie_batches
```

Reads **Pivotal scenes** cue ranges / timestamps from `context.md`; prints SRC vs VI side-by-side.

### Step 6–7 — Merge & final validate

```bash
python3 <skill-root>/scripts/merge_batches.py "input.srt" "./movie_batches" -o "input.vi.srt"
python3 <skill-root>/scripts/validate.py "input.srt" "input.vi.srt"
```

Partial jobs (`--range`): merge updates only translated cue ids; rest stays source text.

---

## Translation rules (compact)

| Cue type | Style |
|----------|-------|
| **Hội thoại** | Văn nói xuôi — natural speech, not hàn lâm |
| **Khác** (sounds, signs, VO) | Dịch ý — clear, concise |
| **Rap/song** | Rhythm per `context.md` |

**Meaning first (hard rule):** Always translate the **full** meaning of each cue — names, numbers, objects, conditions, attitude. Never drop, abbreviate, or mid-cut a sentence to look shorter. Natural `\N` line breaks are fine; length is **not** a limit and is **not** validated.

**Never default `you` → "bạn"** when relationship is known — use `context.md` xưng hô tables; phase overrides baseline.

**Xưng hô disclaimer:** source subs often omit explicit relationships (especially English). Inference + audit reduce errors but cannot guarantee correctness — research and spot-check pivotal scenes.

**Corruption:** never regex-replace `[sound cues]`; use exact dict lookup; `re.escape()` for glossary regex. Fix garbled/duplicated text by re-translating from source JSON — never by stripping meaning.

---

## When blocked

| Issue | Action |
|-------|--------|
| Preflight encoding fail | Convert to UTF-8 (`iconv -f GB18030 -t UTF-8 …`) then re-run |
| Corrupted `.vi.json` | Re-translate from source JSON; `--audit-corruption` |
| Session interrupted | `progress.py status` → resume next batch |
| Xưng hô audit warnings | Fix from `context.md`; do not merge |
| context.md too large | Move glossary to `glossary.md` |

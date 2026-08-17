---
name: native-subtitle-quote-image
description: Turn a public YouTube interview URL into a 3:4 vertical "video-frame strip" quote collage (1080x1440) for Xiaohongshu / WeChat, with verified quotes, zh/en/bilingual outputs, contact sheet and publish copy drafts. Use when the user provides a YouTube link and wants 金句图 / quote cards / 金句截图 / 语录拼贴 / 访谈金句.
---

# native-subtitle-quote-image

You (the Claude/GLM session) are the **editor**: angle choice, quote selection,
translation, and copywriting happen in this conversation. The repo CLI
(`bin/qcard`) does every deterministic step: transcript fetch, video download,
frame scoring, rendering, validation. **Never call an LLM API from scripts.**

## Invocation

```
/native-subtitle-quote-image '<youtube-url>' --count 6 --mode pair --style classic --yes
```

`$ARGUMENTS` grammar: `<url>` (required), `--count N` (4-8, default 6),
`--mode pair|inline|all` (default pair), `--style classic`, `--yes` (skip
confirmations for downloads). Always single-quote the URL in shell commands.

## Orchestration — follow exactly, in order

1. **Parse `$ARGUMENTS`**: url, count, mode, style, yes. Missing url → ask once.
2. **`bin/qcard preflight`** — abort on FAIL with the printed fix hints.
3. **`bin/qcard fetch '<url>'`** — creates and prints `work/<video-id>/` as JSON
   with `work_dir`, `agent_input`, `title`, `duration_sec`,
   `transcript_language`. If the transcript needs a different language track,
   re-run with `--languages en,zh`.
4. **Read** `work/<id>/agent_input.md` (the whole file — do not sample only the
   beginning), plus `work/<id>/transcript/meta.json` for context.
5. **Edit in-session** (you, not a script):
   a. Propose **3 distinct angles** → write `work/<id>/angles.json`
      (schema in references/quote-selection.md; every angle has
      novelty/coherence/platform_fit scores and risk_notes).
   b. Pick the strongest angle and select `count` quotes (default 6) forming a
      narrative line: Hook → Problem → Insight → Evidence → Method → Close.
      Score each quote /100 per the rubric in references/quote-selection.md.
   c. Translate: display_zh natural & compact, **never more absolute than the
      original**; display_en only cleans disfluencies/case/punct, no rewrites.
   d. Write `work/<id>/selection.json` exactly per the schema
      (references/quote-selection.md §selection.json contract). source_text
      MUST be contiguous transcript text; start/end in numeric seconds.
6. **`bin/qcard validate <work-dir>`** — must print `validate: OK`. Fix every
   ERROR by editing the JSON (source_text mismatch = re-find the real sentence;
   do not relax the validator).
7. **`bin/qcard build <work-dir> --mode all --style classic`** — downloads
   ≤720p video (skipped if cached), samples candidates per quote window (±2s
   padding because sentence times are estimates), scores them, writes
   contact_sheet.jpg, renders 01_zh.png / 02_en.png / 03_bilingual.png +
   publish_xhs.md / publish_wechat.md + manifest.json.
8. **Visually verify** by opening the outputs (Read the PNGs). Check: 1080×1440,
   no clipped/overflowing text, bands not crossing strip edges, rounded corners
   intact, zh/en pair use identical frames in identical order. If a chosen
   frame is bad (eyes closed, mid-transition, unrelated b-roll), either set
   `frame_time_sec` in selection.json (pick a better time from contact_sheet)
   or reword — then `bin/qcard rerender <work-dir> --mode pair`. At least one
   look→fix→regenerate iteration is expected.
9. **`bin/qcard open <work-dir>`** (macOS `open`; elsewhere prints path).
10. **Final reply MUST list the actual generated files** (absolute paths),
    the angle chosen, and the quote count. Never reply with just "done".

## Failure handling — do not improvise past these

| Failure | Action |
|---|---|
| No captions at all (`Transcripts disabled`) | Report clearly; offer that a local SRT could be supported later; **do not** add Whisper in this MVP. |
| Video private/deleted/region-locked/age-restricted | Report the exact error; stop. |
| IP blocked / bot detected | Upstream skill already retried alt clients + yt-dlp fallback. If still failing, report the reason and suggest waiting; **never** read browser cookies without explicit user approval (env `YOUTUBE_TRANSCRIPT_COOKIES_FROM_BROWSER` must be user-set). |
| Subtitle OK but video download fails | Keep angles.json/selection.json, report "渲染未完成" with the download error; never fake screenshots. |
| Font missing | preflight lists every path tried; report verbatim with install hint. |
| Single candidate frame fails | Already auto-retried other candidates; only fail if every candidate failed. |
| Text overflow (`overflow:` error, exit 3) | Swap that quote for a shorter complete sentence — do not hand-truncate mid-idea, do not shrink below floor. |

## Editing loop (user revisions)

After any selection.json edit: `bin/qcard rerender <work-dir> --mode …` only —
it touches no network. Common asks mapped to edits:
- swap/keep quotes → edit quotes[] then rerender
- different angle → rewrite selection.json angle + quotes from angles.json, validate, build
- specific frame → set frame_time_sec (pick from contact_sheet.jpg), rerender
- inline 5-quote version → keep 5 quotes, `--mode inline`

## References

- `references/quote-selection.md` — angle rubric, quote scoring, JSON schemas
- `references/layout-spec.md` — classic layout metrics & pixel rules

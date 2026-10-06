# ffman, phase 6: stage B -- exact, idiomatic, researched

Phase 5 closed stage A: the Python ffman equals the bash one on every
invocation of its suites, then replaced it ([`ffman-python.md`](ffman-python.md)).
Stage A had to copy bash -- its arithmetic, its parsers' quirks, its order, its
shape. Phase 6 removes what was copied for equality alone, and improves on bash
where the improvement can be proven. This plan replaces the main plan's
phase-6 list (§6 carries its items). Reviewed once (findings applied: §8).

## 1. Principles

- **Every change to behaviour follows G4** (the main plan, §8): a
  `CHANGELOG.md` entry, a test that fails on the old behaviour and passes on
  the new, a `07-tools.md` row. A change of form only (a move, a type, a
  split) changes no output, which the outcome report shows (6.0).
- **Proof without an oracle.** The bash comparison is gone; a change is proven
  against its stated rule, as phase 3's corrections were: the rule written
  down with its source; the old answer shown to break it, on a measured set;
  the new one never breaking it. Where an output changes, the **outcome
  report** says how much: the inputs that change, the size of each change (px,
  ms, a filter's parameter), and why the new value is the right one.
- **Pinned tests change with the behaviour.** Tests pin stage A's exact
  values: 5 files exact ASS (`\pos(960,981)`, `\fscx118`, event times), 9
  exact filter parameters, 3 import `fmt.py` themselves. A change updates
  the tests that pin what it changes, in the same commit: the updated test is
  G4's failing-then-passing test. A pinned test that changes when its box did
  not mean to change it is a regression.
- **Decide before doing.** Every refusal comes from the options and the probe,
  before any work: bash's order kept work ahead of refusals (§2, F6).
- **The contract moves with the code.** `ffman-spec.md` is the command line's
  contract (grammar, messages); `CHANGELOG.md` gains a "Stage B" section; a
  box that changes either changes it in the same commit.
- **Effects are researched before they are changed** (§4).
- **One box at a time**, reviewed with the efficient-reason and
  efficient-code-review skills; nothing assumed, everything shown.

## 2. Findings (assessed at 6defa91; reviewed at a48dcb7)

### F1. awk's arithmetic, mirrored: 62 uses in 9 modules

`fmt.py` reproduces the bash ffman's number *text*: `calc` (a float printed
`%.6g`, six significant digits, each step reading the last one's text),
`round_int` (awk's `int(x + 0.5)` on that already rounded text: two roundings),
`awk_number` (a field's leading numeric prefix, else 0), `awk_print`,
`sort_n_key` (GNU `sort -n`'s key). Uses (names imported from `fmt`, counted
in each module's syntax tree): `effects/filters.py` 18, `subs/ass.py` 15,
`subs/ingest.py` 15, `subs/layout.py` 7, `camcorder.py` 2, `mosh.py` 2,
`geometry.py` 1 (`awk_print`, a message's text; its sizes are exact since
phase 3, with its own `round_int` on `Fraction`s), `jobs/convert_options.py`
1, `jobs/convert.py` 1. The tests import it too (`test_ingest.py`,
`suite/test_subtitles.py`, `test_geometry.py`).

| Area              | Where                                     | Now                                                                                                                                                                                                                                                         | The outcome at stake                                          |
| ----------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Placement         | `subs/ass.py`                             | canvas width, margin (px), outline and shadow through `calc`; `\pos` **truncated**: x is `int(px / 2)` (853 for a 1707-wide canvas: the centre is 853.5; libass renders a fractional `\pos` -- shown: half a pixel moved 257 of 382 lit pixels), y `int(y)` | text up to 1 px off; style sizes at 6 digits                  |
| Bar               | `subs/layout.py`                          | the bar's share and centre as `calc` text, compared as text-rounded floats; the 7 sample times as text                                                                                                                                                      | a bar at the threshold found or missed by rounding            |
| Sizes             | `camcorder.py`, `effects/filters.py` (CA) | the stamp's width, CA's scaled sizes: rounded twice                                                                                                                                                                                                         | ±1 px                                                         |
| Filter parameters | `effects/filters.py`                      | blur's SAR and sigma, CA's scale `k = px / w`, halation's sigma, VHS's four sigmas (`h / 906`, `/1811`, `/113.2`, `/452.8`), its drop, band and jump: text at 6 digits                                                                                      | a parameter at 6 significant digits; an integer rounded twice |
| Timing            | `subs/ingest.py`, `jobs/convert.py`       | times read from exact decimal text **through a float** (`seconds * 1000 + 0.5`); a gap's shares rounded on floats; the SRT clip **truncated** (bash's `printf "%d"`)                                                                                        | a millisecond at an exact half                                |
| Highlight         | `subs/ass.py`                             | the pop's peak `100 + int(45 / chars)`, truncated, where the rule is `1 + 0.45/chars` and `\fscx` takes decimals                                                                                                                                            | 7 letters peak at 106%, not 106.43%                           |

A gap's words are apportioned correctly: each start is the cumulative share,
rounded, so the spans sum to the gap by construction. ASS's 10 ms resolution
(`_cs10`, and the 10 ms base each untimed word gets) is the format's: kept.

### F2. Compensations: work done because the numbers were inexact

Read, not searched: `subs/ass.py`, `subs/layout.py`, `subs/ingest.py`'s
normalisers and placement, every commented literal and every floor in
`effects/filters.py`, `resize.py`, `gif.py`, `light.py`, `camcorder.py`,
`geometry.py`, `plan.py`, `encode.py`.

- **Datamosh's half-frame tolerance** (`mosh.py`): each heal time is `calc`
  text (a cut's time + seconds), kept by `noise=drop` within half a frame of
  `pts*tb`, a float comparison; the forced keyframes are times as text. Exact:
  each heal's frame index, `eq(n, N)`; keyframes forced by frame number.
- **CRT's gain times 1.01** (`effects/filters.py`, `_crt`): undocumented --
  no word in the code or `07-tools.md`. A margin against clipping, a
  compensation, or a choice: the CRT research decides.
- Rules, not compensations: the 400 ms hold that keeps a word up across a
  short gap; the 10 ms base; `height - 1 - lowest` (the rows below the
  picture); window clamps; the minimum sizes (`max(..., 1)`, `2`); x264's
  and Opus's limits; the bar blur's clamp.

### F3. Bash's way, written in Python

- **Ingest emulates jq and gawk** (`subs/ingest.py`, 604 lines): jq's `@tsv`
  escapes and `tonumber` grammar (`_jq_tsv`, `_jq_number`, `_tonumber`,
  `_jq_order`, `_jq_ge`, `_jq_lt`, `_jq_ms`), gawk's FPAT CSV split
  (`_csv_fields`), awk's records ("awk sees no record after the last
  newline"), awk's `split` (`ass._fields`). Python's `json` and `csv` read
  these formats with typed values.
- **A transcript's backslash is burned doubled** -- jq's `@tsv` escaped it and
  nothing undid it.
- **Numbers carried as text**: `Style.size`/`margin`/`bar_y`, `Bar.y`,
  `ConvertOptions.font_size` and `margin_bottom` ("a fraction as text, as the
  bash ffman carried it"), `Mosh.rate`, `plan`'s `fps` ("as bash printed it,
  %.6f"), every `probe` rate, duration and time base -- re-parsed where used.
  ffprobe's JSON gives strings: `probe.py` is where they become `Fraction`s.
- **Reading ffmpeg's log**: `layout.bar_height` finds the frame's height by
  scraping ffmpeg's human-readable log ("Output #0", a `Stream #0:0` line, a
  `WxH`) -- a height ffman's own plan already knows; cropdetect's rows can
  come as structured metadata -- shown: `metadata=print` gives `lavfi.cropdetect.y1`, `y2`, `h` -- not log text.
- **Bash's order**: `jobs/convert.py` runs "in the order its bash command ran"
  -- F6.
- **Shaped by bash's control flow**: `_place` (76 lines, four complexity
  rules suppressed: "bash's place(), rule for rule").
- **Grammar and messages** (in scope): the parser follows bash's grammar,
  including an optional value taken unless the next token starts with `-` and
  a letter ("`-1` is a value, and a bad one"); `checks.py` keeps bash's
  `is_uint`/`is_num` (no sign, no leading zero, no exponent); messages keep
  bash's text. Changed through the spec.
- **The camcorder's text** emulates gawk's `strftime` in the C locale: English
  names, fixed -- a choice to state, not an accident to copy.
- **Provenance as justification**: 182 lines in 24 modules cite bash ("as
  bash", "bash's ...") as the reason for code -- 44 comments, 138 docstrings,
  none in code (parsed). Stage B states each rule
  and its source instead; bash stays in the history (`CHANGELOG.md`,
  `07-tools.md`).

### F4. Architecture

- `subs/ingest.py` (604): readers for seven formats (SRT, VTT, LRC, CSV, TSV,
  whisper-cli's and WhisperX's JSON) in six functions, jq's and gawk's
  emulations, two normalisers, the placement.
- `effects/filters.py` (432): every effect's filters in one module.
- `jobs/convert.py` (479): four flows, the passes and the render.
- `plan.py` (461): streams, outputs and their refusals, YouTube's video and
  sound.
- `subs/ass.py` wraps by an em estimate, not the font's metrics; `_plain`
  re-estimates libass's own wrap to count lines over the frame.
- Imports against the layers (today's graph, parsed): `plan` and `resize`
  import `jobs.convert_options` -- the planners' input lives in a job;
  `resize` (graph) imports `geometry` (plan) for the sizes it reads
  (`Displayed`, `Target`); `run` imports `options` for `PROG`, the program's
  name in messages.

### F5. DRY

- Rationals parsed in four modules, two notations: ffprobe's `N:D` SAR
  (`geometry._SAR`), and `N/D` (`effects/filters.py` the SAR, `mosh.py` its
  `_RATE` and two splits, `plan.fps_of`). Once, in `probe.py`.
- `f"file:{...}"` ten times (nine lines) in three modules: one helper.
- Constants in `07-tools.md` and inline in the code (VHS's 906 and 1811 as
  literals in a tuple): named constants with their source and row, as the
  main plan asks (§4, "constants carry provenance") -- per effect, §4.

### F6. Work before refusals (demonstrated)

`burn` decides an existing output, the output's kind and the loop checks
after the bar detection, the camcorder, the subtitles and -- for the kind --
the passes. `convert -i v.mp4 --burn-subs t.srt --vfx datamosh -o out.png`
ran 1 ffprobe and 9 ffmpeg (7 cropdetect samples, a scene detection over the
whole video, a full datamosh render) before "overlay output must be a video":
minutes of work on a long video, for an answer the command line held.
`attach` refuses an existing output after reading the transcript (cheap).
`resize` and `youtube` check first.

### F7. An option ignored where it is elsewhere refused (found by the outcome report)

`-b` and `--resize-mode` without a size are refused when burning subtitles
(`plan.select_flow`) and silently ignored when only effects run: `-b --vfx
invert` gives `--vfx invert`'s commands exactly (case `vfx/bblur-ignored`).
Bash's; one answer for every flow belongs to 6.10.

### F8. What each container holds (ffmpeg n8.1.2: source, measured)

A convert across container families drops every subtitle and attachment
(`plan/streams.py` `tracks`), and a container change alone is "nothing to do"
(`plan/flows.py`): `-i a.webm -o a.mp4` is refused, though copying works (VP9
and Opus into MP4: 1.46 MB of 1.45, nothing re-encoded).

| Muxer (extensions)          | Subtitles held as they are                        | Attachments      | Custom tags              | Cover art                |
| --------------------------- | ------------------------------------------------- | ---------------- | ------------------------ | ------------------------ |
| mp4 (`.mp4`)                | mov_text, dvd_subtitle, ttml (`movenc.c`)         | job fails        | with `use_metadata_tags` | kept                     |
| mov (`.mov`)                | mov_text, eia_608 (`isom.c`)                      | job fails        | with `use_metadata_tags` | dropped silently         |
| ipod (`.m4v` `.m4a` `.m4b`) | mov_text (`movenc.c`)                             | job fails        | with `use_metadata_tags` | kept                     |
| matroska (`.mkv` `.mka`)    | SRT, ASS, WebVTT, VobSub, DVB, PGS (`matroska.c`) | kept             | kept                     | written as a video track |
| webm (`.webm`)              | WebVTT (`matroskaenc.c`)                          | dropped silently | kept                     | job fails                |

Text subtitles convert into one another directly (decoders and encoders for
SRT, ASS, WebVTT, mov_text): WebVTT into MP4 needs no SRT step. Converting
loses what the target cannot say -- ASS's styles into mov_text or WebVTT,
WebVTT's cue settings into mov_text (kept when copied into Matroska or WebM).
Image subtitles never become text (no OCR). Chapters and stream languages
cross into all five; a cover into Matroska kept as a cover takes extracting
and attaching (`matroskaenc.c` has no attached-picture handling).

### F9. Metadata files (ffmpeg n8.1.2: source, measured)

ffmetadata is ffmpeg's text form of a file's tags and chapters (a demuxer and
a muxer), not a stream. Ogg (`.ogg` `.oga` `.opus` `.ogv` `.spx`) and FLAC
store tags as Vorbis comments (`oggenc.c`, `flacenc.c`); Matroska, only inside
a FLAC track's header. Chapters as Vorbis comments (`CHAPTERxxx`) are written
for Opus alone: FLAC's muxer passes none, Ogg's only to Opus headers -- into
Ogg Vorbis or FLAC they are lost (measured: 2 of 2 back from `.opus`, 0 from
`.ogg` and `.flac`). Read back, every Ogg stream's chapter comments are chapters,
and FLAC's embedded cue sheet is chapters too (`flacdec.c`). ffmpeg reads no
`.cue` file. So a cue sheet, an ffmetadata or a Vorbis text crosses containers
only as an attachment (Matroska) -- or converted, which nothing does yet.
Extensions: ffmpeg registers `.ffmeta` for ffmetadata (`ffmetaenc.c`; its
reader knows a file by its first line, `;FFMETADATA`, whatever its name);
Vorbis comments as text have none (`vorbiscomment(1)`'s example: `file.txt`;
`metaflac` takes any name); a cue sheet is `.cue`.

`metaflac` (FLAC's own metadata editor; 1.5.0, nixpkgs' at this pin, built from
its release and run): its tag files are `NAME=value` lines without escapes -- a
two-line value exported is refused by its own import (atomically). Its cue
import fills FLAC's `CUESHEET` block, which keeps positions only: ffmpeg reads
it as chapters, untitled (`TITLE`, `PERFORMER` dropped; 44.1 kHz and 48 kHz
alike) -- or titled with the track's ISRC, when it has one (6.6.1, cue). `CHAPTERxxx`/`CHAPTERxxxNAME` comments in FLAC ffmpeg reads as titled
chapters -- so ffmpeg's `-metadata` can carry them where its muxer writes none.
A whole cue sheet kept as a `CUESHEET` comment (`--set-tag-from-file`) is
text only to ffmpeg; mpv reads it as chapters (6.6.1, cue: source).
What crosses between the three, and what does not:
[`ffman-mappings.md`](ffman-mappings.md). Pictures it imports are covers to ffmpeg.

## 3. Target architecture

```
src/ffman/
  cli.py  errors.py               errors.py: the one error, PROG
  options.py  values.py          the grammar; value checks (was checks.py)
  media/                          the only processes: ffprobe, ffmpeg, the tools
    probe.py                      JSON -> typed Media (Fractions)
    run.py                        Runner, signals, workdir
    paths.py                      file: URLs; output paths (was output.py)
  plan/                           pure decisions, every refusal (was plan.py)
    flows.py  outputs.py  streams.py  youtube.py  geometry.py  encode.py
    request.py                    ConvertOptions: what a job asks, checked
  graph/                          filtergraphs as data (__init__.py: the model)
    resize.py  light.py  gif.py  sizes.py (Displayed, Target)
  effects/                        __init__.py (the registry); one module an effect
    spec.py  frame.py  stages.py  the definition's types; the frame; the stages
    blur.py  pixelate.py  invert.py  chromatic_aberration.py  halation.py
    datamosh.py  camcorder.py  vhs.py  dither.py  crt.py
  subs/
    transcript.py                 Chunk, Word, Transcript, Row, Reading: the types
    ingest.py                     ingest(): the readers, then the normalisers
    readers/                      __init__.py (by format)  subrip.py (SRT, VTT)  lrc.py
                                  table.py  whisper.py
    normalize.py                  cues, words, their placement
    layout.py  ass.py  srt.py     placement; the writers
  meta/                           metadata files: ffmetadata, Vorbis comments, cue sheets
    model.py                      the one model: tags as written, exact times, a cue's disc
    ffmetadata.py                 ffmpeg's text form: read as ffmpeg reads it, written exactly
    vorbis.py                     Vorbis comments as text (vorbiscomment -e's form), chapters too
    cue.py                        cue sheets: read as the readers in use agree, written as all accept
    convert.py                    between the three: the mappings' rows, each loss noted
    files.py                      a file's format: by its extension, first line or --preset
    fields.py                     one field table: ffmetadata's key, Vorbis' name, a cue's command
    edit.py                       meta's edits: declarative, in the output's words
    chapters.py                   meta's chapter edits; in a cue, its tracks
    time.py                       meta's one time syntax: exact, never MM:SS:FF
  jobs/convert/                   __init__.py: the package's docstring alone
    dispatch.py  options.py       which flow; validate (the grammar's answer -> ConvertOptions)
    resize.py  burn.py  attach.py  youtube.py
    passes.py  render.py  output.py  the effects' passes; the render; writing, encoders
    metadata.py                   a metadata file, or a media file's, written as one (spec 3.9)
  jobs/meta/                      ffman meta (spec 8): options.py, run.py; io.py, convert's too
```

Dependencies point down: `cli` → `jobs` → `plan`, `effects`, `subs`, `meta` →
`graph` → `media`'s types, `values`, `errors`; the module graph has no cycle.
Only `media` runs processes, driven by `jobs`; `plan`, `graph`, `effects`,
`subs` and `meta` are pure -- no file, no OS, the architecture test holds it (the readers' file reads its listed exception, 6.3's to close). `ConvertOptions` -- the planners' input -- is `plan/request.py`,
which `jobs` validates from the grammar's answer; resize's own terms (its modes,
the bar blur) are `graph/resize.py`'s, and `head` takes them, not the options;
`PROG` is `errors.py`'s. An
architecture test (an AST walk of the imports) fails on an import against the
direction or a cycle. The names are the target; each move's box confirms them
against the code it moves.

## 4. The effects: research first

Ten effects (`ffman effects`): `blur`, `pixelate`, `invert`,
`chromatic-aberration`, `halation`, `datamosh`, `camcorder`, `vhs`, `dither`,
`crt`. For each, in turn, before any change to it:

1. **Research** what the effect is physically or digitally (VHS: the format's
   bandwidth, noise, head switching, chroma; CRT: the beam, the mask, the
   phosphors; halation: film's layers; ...), its specifications, and the best
   algorithm for its defaults -- from primary sources (standards, papers,
   manufacturers' data, ffmpeg's filter sources), each claim with its source.
2. **A skill**, `.agents/skills/vfx-<effect>/SKILL.md`: what the effect is,
   its parameters and their physical meaning, the default and why, how ffman
   builds it, how to measure it -- every figure sourced, every measurement a
   script beside it (`scripts/`), run. Its frontmatter passes skill-creator's
   `quick_validate.py` (only `name`, `description` and the allowed keys; the
   name kebab-case, at most 64 characters; the description at most 1024, no
   angle brackets); `package_skill.py` makes `vfx-<effect>.skill`, presented
   to the owner to save in Claude.
3. **Expand this plan**: the research's findings become the effect's code
   boxes.
4. **Then change the code**, under G4.

Already flagged, to fold into each effect's research:

| Effect                 | Flagged                                                                                                                                                        |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| all                    | resizing in gamma, not linear light (every resize, effects or none)                                                                                            |
| `blur`                 | its SAR and sigma through `calc` (F1)                                                                                                                          |
| `pixelate`             | ignores SAR (a review finding)                                                                                                                                 |
| `chromatic-aberration` | its scale `k = px / w` and sizes through `calc`; `px`'s auto `(shorter + 67) // 135`; prints `setsar=1` resized, `1/1` not (bash's text: `Frame.squared`, 6.0) |
| `halation`             | ignores SAR; its sigma through `calc`                                                                                                                          |
| `datamosh`             | the half-frame tolerance and time-text keyframes (F2)                                                                                                          |
| `camcorder`            | its width rounded twice; gawk's `strftime` (F3)                                                                                                                |
| `vhs`                  | four sigmas and three sizes through `calc`; constants inline, against their source                                                                             |
| `dither`               | auto 16 colours: the reason, against the source                                                                                                                |
| `crt`                  | decodes images with 2.4, not sRGB (a review finding); the gain's undocumented 1.01 (F2)                                                                        |

## 5. Skills

Skills live in `.agents/skills/<skill-name>/`;
[`.agents/skills/README.md`](../.agents/skills/README.md) states their format, sources
and packaging, and `AGENTS.md` routes there. Every skill is validated and
packaged as §4 says, and its `.skill` presented to the owner.

## 6. Carried from the main plan

- **D2, the default encode** -- a delivery default, `--lossless` explicit; it
  applies to burned subtitles too.
- **A transcript's backslash burned doubled** (F3).
- **Exact numbers**: `fmt.py`'s scaffolding replaced with exact arithmetic
  (F1) -- here by area.
- **Stage 4 in `convert`**: GIF, `--loop`/`--loop-reverse` from any input; any
  compatible output format.
- **The review findings**: resizing in linear light; SAR for pixelate and
  halation; CRT through `light.py` (§4).
- **`--attachment`, `--cover`, `--metadata`, `--title`.**
- **`-v/--verbose`**, held back in phase 4 until it has a meaning.
- *Done already*: fuzz.py's invariants as a Hypothesis property -- ported in
  phase 4 (S158, S159: `tools/ffman/tests/test_transcript_fuzz.py`).

## 7. Checklist

Each box: plan its change, show its outcome (or show none), review, commit.

**6.0 Foundations** (form only)

- [x] The outcome report, first: `python -m tests.outcome` (`tools/ffman/tests/outcome/`; `tools/ffman/AGENTS.md`, "The outcome report") runs a fixed corpus under `--dry-run` -- which runs ffman's read-only work too (the probe, bar detection, scene cuts), so one mode suffices -- and records each case's exit status, commands, notes and refusals, and work files (ASS, SRT); `compare REV` diffs a revision against this tree: identical, same graph (filtergraphs ffmpeg reads the same, by `tools/ffman/tests/support/filtergraph.py`), or changed. Every later box shows its diff (empty for form only). *Done: 341 cases (every flow, effect, transcript, hostile transcript and refusal; environments through `Case.env`), reaching 96% of `src` -- the rest real writes, signals, failing tools, invariants and the clock, each named in AGENTS.md. Shown: two reports identical (341); eight one-line mutations each caught on exactly its cases (a filter's parameter 4, the pop 6, the SRT 22, a note 1, a refusal 1, the status 118, an x264 option 167, the camcorder 3); a rename 341 identical; an escaping change 81 same graph, 0 changed; `compare HEAD` 341 identical; the tool's 21 tests catch five mutations of it. Found on the way and fixed: ten cases with no job (coverage showed them refused before their path); an installed ffman answering for the commit (cases run `python -S`: 9.9.9 from the commit's pyproject, not 2.0.0.dev0); HDR and BT.2020 sources untagged (`h264_metadata`, read back by ffprobe); escaped paths leaking (named however escaped); a refused graph crashing the diff; a src without its pyproject recording 341 crashes (refused); a revision read as an option (resolved first). And F7.*
- [x] Skills' home: `.agents/skills-map-project/` → `.agents/skills/map-project/`, every reference updated; `AGENTS.md` routes `.agents/skills/`; the doc map places it. *Done: moved by `git mv` (five renames, history kept); `.agents/skills/README.md` states the convention (skill-creator's format, its validator and packager, sources) and `AGENTS.md` routes to it; the doc map excludes `map-project/` (vendored -- shown: upstream through the repository's `dprint.json` is byte for byte this copy) and places `.agents/skills/` (the README, concept band); the Nix map's only changes the renamed paths in computed fields. Every old path gone but this plan's. Validated (skill-creator's `quick_validate.py`) before and after the move; packaged as `map-project.skill`. The files this box and the last wrote pass dprint (the plan and tools/ffman/AGENTS.md formatted, content shown unchanged).*
- [x] Typed numbers at the boundary: `probe.py` parses rates, time bases, durations and SARs into `Fraction`s; the four parsers (F5) use them; output text unchanged -- in the effect modules too, form only, no flagged item touched (§4). *Done: `probe.py` types ffprobe's numbers once, in the forms its source prints (fftools/textformat/avtextformat.c, n8.1.2: ratios `%d%c%d`, times `%f`; an optional field is absent from JSON, never "N/A"): a `Rational` for a ratio -- exact and unreduced, `0/0` kept, since its users tell `0/0` from other ratios, which a `Fraction` cannot hold -- a `Fraction` for a duration, an `int` for the sample rate; the SAR a `Fraction` past geometry (ffprobe reduces it: av_guess_sample_aspect_ratio). Gone: geometry's `_SAR`, the blur's partition, mosh's `_RATE` and splits, `fps_of`'s text, encode's `_TIME_BASE`. Shown: each pinned text table passes unchanged through `Rational.parse` (every consumer's old answers, row for row); text outside `%d` reads None (boundary tests); zero kept apart from absent (`"0.000000"` was true, `Fraction(0)` is not); CA's `setsar=1` resized, `1/1` not, kept by `Frame.squared` (bash's text, flagged in §4). `compare HEAD`: 343 identical -- two cases added, CA after a resize, the one text no case compared (a branch within one line: invisible to coverage). Suite 818 at 100%, matrix 761; ruff, basedpyright, vulture. Caught on the way: a `NameError` at import (a class's annotation naming itself: `Self`).*
- [x] One `file:` helper (F5). *Done: `output.file_url` (where §3 puts file URLs, beside the output paths); all ten uses in three modules call it. Its reason, from source (libavformat/avio.c url_find_protocol, file.c; n8.1.2): a name's leading `[A-Za-z0-9+-.]` run before a `:` is a protocol, and the file protocol takes one `file:` off -- shown against the pin: ffprobe refuses `a:b.png` ("Protocol not found") and opens `file:a:b.png` (a test). Outputs need none: the paths ffman makes are absolute (Python 3.13's mkstemp and mkdtemp, shown for a relative `a:b`), and a real run into `a:b/x.mp4` writes. `compare HEAD` 343 identical; suite 820 at 100%. Seen, left for a behaviour box: the mosh render is read once with `file:` and once without (`jobs/convert.py`, absolute either way).*

**6.1 Architecture** (form only)

- [x] The architecture test (§3's direction, no cycles), passing on today's tree but for its listed exceptions (`plan` and `resize` → `jobs.convert_options`; `resize` → `geometry`; `run` → `options`), which the moves below close. *Done: `tools/ffman/tests/test_architecture.py` reads the import graph from the source's syntax trees (every import, wherever it stands; a name that is a submodule counts as that module; a relative import fails, the package having none) and holds four rules: every module has a layer (§3's, numbered 0-5 on today's names); the upward imports are EXCEPTIONS exactly -- a new one fails, and so does one a move closed but did not strike; no cycle (one is reported as itself); only the media layer imports `subprocess` (§3's "only media runs processes": `run`, and `probe` for a type). The exceptions are four, not three: `resize` (graph) imports `geometry` (plan), which the plan's review missed -- added here, to F4 and to the moves' box. Shown: each rule broken in a scratch copy fails its test (a module unplaced, an import upward, a cycle within a layer, `subprocess` in `gif`, an exception stale).*
- [x] `media/`, `plan/`, `graph/`, `values.py`: the moves (§3); `ConvertOptions` below the planners; the sizes `resize` reads (`Displayed`, `Target`) below the graph; `PROG` to `errors.py`. *Done: `git mv` for the moves (`checks` → `values`; `probe`, `run`, `output` → `media/`; `graph.py` → `graph/__init__.py`, `from ffman.graph import` unchanged; `resize`, `light`, `gif` → `graph/`; `geometry`, `encode` → `plan/`). `plan.py` split by syntax-tree node into `plan/flows.py`, `outputs.py`, `streams.py`, `youtube.py` -- every node and character placed, one call across them (`youtube` → `outputs.is_image`), no cycle. `Displayed` and `Target` → `graph/sizes.py`; `ConvertOptions` and its literal types → `plan/request.py` (the planners' layer: it holds effect requests; `validate` stays in `jobs`); resize's own terms (`ResizeMode`, `RESIZE_MODES`, `BBLUR_MAX`, `bblur_on`) → `graph/resize.py`, and `head` takes `mode` and `bblur`; `PROG` → `errors.py`. Imports rewritten by a codemod from the syntax trees, name by name, each name's home read from the new modules' own definitions; the two imports inside a test's script string, which no syntax tree shows, by hand, and every string searched; the one comment inside an import the codemod dropped (a suppression), found by comparing every import's comments with HEAD's, restored. The architecture test: every module placed, EXCEPTIONS empty. `compare HEAD` 343 identical; docs' module paths followed (07-tools.md's 20 rows, AGENTS.md's layout by layer, a run-book, two comments).*
- [x] `effects/`: one module an effect -- first, so each effect's research reads one module. *Done: each of the ten in `effects/<effect>.py` -- its definition (`EFFECT`: name, stage, parameters and their checks, once in the registry's tuple), its builder (`build`, once `filters.py`'s private one), its helpers and constants; `mosh.py` and `camcorder.py` moved in by `git mv` (`datamosh.py`, `camcorder.py`). Shared, so no cycle: `spec.py` (`Stage`, `Param`, `Effect`, `Request`, `between`, `asked`), `frame.py` (`Frame`), `stages.py` (the stage sets, `Effects`, `apply`, `chain`; `PRE`/`POST` keyed by each module's own `EFFECT.name`); `__init__.py` the registry, in bash's order. The dither's `paletteuse` step, inline in `chain`, its own `dither.use_palette`. A duplicate found and removed: `_curves`, identical in `resize` and the effects, one `graph.light.curves`. Composed from syntax-tree segments, not retyped; basedpyright caught what merging two modules into one made of the camcorder -- `datetime` the class where it had been the module (every `camcorder:date=` would have raised `TypeError`), and two `_time`s (the check is `_is_time`) -- and ruff a definition used before its check was defined (`datamosh`, `camcorder`: a `NameError` at import). The codemod dropped the registry's own submodule import (taking the package's name for itself), restored. The architecture test: the effects' modules placed, no cycle. Docs: 07-tools.md's six rows, AGENTS.md's layout.*
- [x] `subs/`: transcript, readers, normalisation apart. *Done: `subs/ingest.py` (604 lines) split by syntax-tree node, every node placed once: `transcript.py` the types (`Chunk`, `Word`, `Transcript`, `Row`, and `Reading`, the readers' answer -- spelled out three times, now named); `readers/` one module a format (`subrip`, `lrc`, `table`, `whisper` -- the jq emulation whisper's alone, its only user) and `__init__.py` the dispatch; `normalize.py` (`cues`, `words`, their placement); `ingest.py` keeps `ingest()` and its history. §3 had `ingest()` in `transcript.py`: with the types it imports, the readers and normalisers would import it back -- a cycle -- so the types stand alone. Callers call through the module (`readers.read`, `normalize.words`); locals named like their module's function renamed (`found`, `placed_words`). The codemod's "defined here" rule took a package's own submodules for its names (6.1.3's registry, restored by hand then, dropped again now): fixed, and shown -- `effects/__init__.py` equals HEAD's after a rerun. 07-tools.md's ten rows cite where each behaviour now is; its "Hostile transcripts" row still tells of a jq path rule (`-` gets `./`) that no Python reader needs -- for 6.12's docs. The architecture test places the seven modules.*
- [x] `jobs/convert/`: one module a flow, the passes and the render shared. *Done: `jobs/convert.py` (479 lines) split by syntax-tree node, each segment cut from its predecessor's end (the source's spacing kept: the neighbour check finds none changed), every node placed once; `convert_options.py` → `convert/options.py` by `git mv`. Each flow a module with `run` (`resize`, `burn` -- its bar and subtitles with it --, `attach`, `youtube`); shared: `passes.py` (`frame_for`, `camcorder`, `effects`: the mosh and palette passes), `render.py` (`Render`, and `Passes`, the render's input -- in `passes` it made `render` and `passes` import each other), `output.py` (`write` through the partial file, `encoders`: attach writes but never renders, so not `render`'s). The dispatch is `dispatch.py`, not `__init__.py` as §3 had it: siblings import each other through the package (`from ffman.jobs.convert import output`), and basedpyright counts the package's `__init__` -- an `__init__` importing the flows is a cycle to it (shown in a scratch package; `import a.b as b` instead, ruff's PLR0402 refuses). Caught by checking what the renames did, before any test: two locals named `passes` the module's name (an `UnboundLocalError` in every resize and burn), and a keyword renamed with its function (`output.encoders=`, a syntax error). An orphan comment, `sub_codec_for`'s, whose constant (`SUBTITLE_CODECS`) phase 4's dead-code removal took (1ba4418), above `SAFE_PATH` (now `burn._SAFE_PATH`), removed. The test's `_frame` is `passes.frame_for`, public: its private-use suppression gone. Docs: 07-tools.md's five rows, AGENTS.md's layout.*
- [x] Numbers carried as text become typed (F3) where no effect is touched: `Style`, `Bar`, `ConvertOptions`, the YouTube plan (effects' own in their boxes). *Done: `ConvertOptions.font_size`, `margin_bottom` and `bblur` (`BBlur`: a sigma, or auto), `Style.size`, `margin`, `bar_y`, `Bar.y`, and the YouTube plan's `fps` (`fps_of`: the value bash's %.6f denoted, or None) are `Fraction`s, each exactly the number stage A's text denoted -- awk's rounding kept (6.4 makes it exact); the command line's text becomes them once, in `validate`, its refusals still quoting it. Read where `awk_number(text)` was: `float()`, the same double -- a property test over the grammar's decimals and `calc`'s outputs. `fps_of` is `round(x, 6)`: equal to %.6f read back on 210,004 rationals, 10,001 exact ties (half to even), and a property test. Printed by `values.decimal`, the shortest exact decimal (any other fraction refused, never rounded). One change, G4: a number in another spelling is written as its value -- `--font-size 057.50` is `57.5` in the ASS and its note, `--bblur 012.50` is `12.5` in gblur; libass rendered the three spellings to one frame (a control, 58, differed); CHANGELOG "Changed (phase 6)", its test failing on HEAD, 07-tools.md's Rendering and Blurred borders rows; four corpus cases show it (`*-spelled`): `compare HEAD` 344 identical, 3 changed -- each in the spelled number alone (the gblur case "changed", not "same graph": the report's same graph is the same parse, and `012.50` is not `12.5` as text; ffmpeg's reading them alike is the render's proof, a frame blurred with each, identical). The 57/64 defaults and the margin's default, each once now.*

**6.2 Decide before doing** (G4)

- [x] Every flow refuses before any work (F6): `burn`'s output, kind and loop checks before bar detection, the camcorder, the subtitles and the passes; `attach`'s output before the transcript. A test counts the processes run before each refusal: none. *Done (G4): each flow probes, decides, reads the transcript, works -- `burn` decides its output, kind, fonts and size after the probe; `attach` its output before writing the track; `resize` and `burn` their encoding (`render.encoding`: `GifEncoding`, `ImageEncoding`, `VideoEncoding` -- `Render` carries it, not a `kind` beside it) and the pixel format (`stages.check_restorable`; `chain`'s refusal an invariant) before the camcorder and the passes; what this ffmpeg encodes asked last, so a transcript's refusal starts nothing. Failures stay where they happen (ffmpeg's, an optimiser's, an empty output). Measured, every corpus case under an audit hook on process starts and files written, old and new: 121 refusals, every message and status the same (beyond the corpus: one message corrected, several faults heard in the new order -- 6.2's review); refused after work 5 (`burn/to-png`'s 9 ffmpeg and an ASS, `env/fonts-colon`'s 7 bar samples, three the reading found -- an output existing in `burn` and `attach`, a codec with effects -- now corpus cases), now none, none doing more. `compare HEAD`: 345 identical, 5 changed -- in work alone (files, a printed render, its note), no message. `test_convert_job`'s order test fails on the old code in all five. A `match` whose last arm fell through by coverage's count is `case _:`, the checker's narrowing holding the union (a fourth type refused, shown). The CHANGELOG's section is "Stage B", as §1 says (6.1.6 had named it otherwise). Carried to 6.10: the camcorder passes FFMAN_FONTS_DIR to its filter unchecked, `burn` refuses it -- one rule.*

**6.3 Idiomatic ingest** (G4 where outputs differ)

- [x] JSON through `json`, CSV/TSV through `csv`, typed values -- each difference in what is read listed and decided (the hostile transcripts and the property tests are the measure). From 6.1.4's review, for this rewrite: one text-cleaning rule (tags are stripped twice today, `readers/subrip._plain` and `normalize._clean`, each a different bash step); `readers/whisper.py` ordered by format, the jq emulation apart; `readers.read`'s `file` and `path`, one value. From 6.1's review: the readers read the transcript's file themselves (`readers/__init__.py`, `readers/whisper.py`: §3's planners are pure) -- a reader takes the bytes, the job reads the file; the architecture test's IMPURE then empty. *Done (G4): readers yield typed records (`transcript.Cue`, `Timing`, `Reading`: ms, None for no time), not TSV text; `json` and `csv` read the formats, jq's `@tsv`, `tonumber`, order and gawk's FPAT gone; one number grammar for a time read from text (`readers/fields.number`: a decimal, finite) in every format; one text rule (`subs/markup.py`, the subtitle readers' and the normalisers'); `readers/whisper.py` by format; `readers.read(fmt, data, name)`; `ingest(name, data)` pure, the job reading the file (`media.paths.read_file`, "no such file" kept), the architecture test's IO_CALLS now with the filesystem's queries (`ingest`'s `is_file` had passed) and IMPURE empty; `fmt.sort_n_key`, unused, gone. Each difference decided: a JSON text as written (a backslash single -- 6.3.2's -- a CR a break); a time not a number no time, in every format (awk: 0 ms); a value of the wrong kind no value, not the file's refusal; a DTW window not given in numbers unchecked (offsets used); a CSV header naming start and end in any order (bash's rule left a reordered one garbage, which a refusal would only have hidden); a quoted CSV field whole across lines; a `t_dtw` given as a decimal string read; WhisperX seconds past a double's range in ms no time (an `OverflowError` the rewrite first had, caught in review); cues sorted by value. Measured: `compare HEAD` 347 identical, 5 changed, each one of these; the hostile and property tests; `test_ingest.py`'s new cases each failing on the old code. CHANGELOG "Stage B"; 07-tools.md's "Transcript values" row, and three rows corrected (jq's clauses gone with jq).*
- [x] The doubled backslash fixed. *Done (G4; the fix landed with 6.3.1, no `@tsv` between): one backslash in every format, read once -- `test_ingest.py`'s `test_a_backslash_is_one_in_every_format`, each of SRT, VTT, LRC, CSV, TSV, whisper-cli JSON (and its words) and WhisperX JSON (and its words), read, burned and attached. Before 6.3.1, run on the same inputs: the two JSON formats doubled it -- in their cues and words, burned `//` where one `/` stands for it, and `\\` in an attached SRT track (counted: 2) -- the others never did. Researched, kept: `\` is burned as `/` and braces as parentheses -- libass's `ass_get_next_char` reads `\N`, `\n`, `\h`, `\{`, `\}` in text (0.17.1 and master the same), and ffman's override blocks follow words, so a word ending in `\` would open `\{`; showing them as written is a product choice, carried to 6.10. No product code changed.*
- [x] `_place` rewritten as Python, its rules stated, within the property tests' invariants. *Done (form only): `_place` is one sentence's words and its window, its six rules stated in its docstring and each a step -- `_within` (a start clamped, or none), `_anchors` (index and start of each time to trust), `_share` (10 ms each where there is room, the rest by characters) -- typed, its four complexity suppressions gone; `words` groups runs with `itertools.groupby`. Every `num(None)` the old code guarded was unreachable (only anchors' and tested values met it). Shown: the old and the new, run on 400,000 random sentence sets under eight seeds (about 1.6 million words: starts before, at and past the window, ties, out-of-order words, windows too small for 10 ms each, split runs, words of no sentence) -- not one word or count differs; the run reached every line and branch of the new code. The property tests' invariants hold (suite); `compare HEAD` all identical. 07-tools.md's two placement rows made exact ("at or past", "where the gap allows").*

**6.4 Exact arithmetic, outside the effects** (G4; outcome report each)

- [x] Timing: times from their decimal text to integer milliseconds, no float; shares rounded exactly; the SRT clip by a stated rule. *Done (G4): a time is read exactly from its decimal text (`readers/fields.exact`: a `Fraction`, in bounded work -- see 6.4.1's review; JSON through `json.loads(parse_float=fields.json_number)`, a number as text still printed as before, `default=float`) and is whole milliseconds, rounded half up -- `fields.ms`, one rule for every format (bash: SubRip and LRC half up through a float, WhisperX half away from zero, CSV, TSV and whisper-cli fractions kept and truncated); past a double's range none. Readers deliver integers; `normalize` is integer arithmetic (a share `(2·rest·done + total) // (2·total)`), shown identical to its float form on integer inputs (100,000 sentence sets, 200,000 cue lists); ASS centiseconds `(ms + 5) // 10`, the same for every integer. The SRT clip, a stated rule in `srt` (which now takes the duration): the media's duration in whole ms, floored -- no cue outlasts it: exact whenever the duration is whole ms (SRT's and Matroska's resolution), and, when it is not, the earlier neighbour, since a cue past the end lengthens the file (measured: an MP4 of 1.005500 s, a cue to 1006 ms, became 1.006000 s). Measured, float against exact: seconds to ms, 185 of 200,001 values on a 0.1 ms grid; the clip, 1,482 of 200,001 whole-ms durations (1.005 s was 1004). Shown: `test_ingest.py`'s tests (old: 500, 500, 500, 999, 999 and 1004); two corpus cases built to show it -- `burn/hostile/half-ms.srt` (0.50, 4.02 → 0.51, 4.03) and `attach/clip` (a 1.005 s source: `,004` → `,005`) -- `compare HEAD` 352 identical, those 2 changed. CHANGELOG; 07-tools.md's Transcript values and Attach rows.*
- [x] Placement and the bar: exact values; `\pos` exact (fractional where the centre is); the bar's threshold and centre exact; sample times exact. *Done (G4): the formats from libass's own reading (0.17.1, `ass_parse.c`, `ass.c`): `\pos`, size, outline, shadow are doubles (`argtod`, `FPVAL`), PlayResX and the margins integers (`INTVAL`, `parse_int_header`). So in `ass.py` every value exact -- the integers rounded half up once (`values.round_half_up`, which `geometry`, `fields.ms` and `ass` now share: one rule written three times before), the doubles written as their exact decimal or the double nearest it (`_number`; `values.terminates`) -- line positions exact (bash: truncated or rounded). Proved on this build: `\pos(853,985)` and `(853.0,985.0)` render alike, `(853.5,985.8)` moves 8,691 pixels. The bar (`layout.py`): the share, threshold and centre exact (a bar exactly a line tall, 19 of 288 rows at size 57, was missed by bash's six digits), the samples at their exact seconds. Decided here though wrapping is 6.5's: the wrap estimate exact -- 88% of 1920 px in 0.55 x 64 glyphs is 48, a float made it 47 (and 26 for 27 at 1080); the comparison with the old float put back held the same 32 cases to placement alone (7,007 `\pos` lines, 31 styles, nothing else), so the rest is the wrap's. Found on the way: four test parsers read `\pos` as integers -- one failed, three passed by skipping every fractional line (a line below the frame unchecked); one decimal `POS` (`tests/support/subtitles.py`), and every placed event must yield one (shown: lines pushed 400 px down now fail both fuzz properties and the suite's). Tests failing on the old code: the header, two positions, a half-pixel centre, the bar's threshold and centre, the sample times, a 48-character line.*
- [x] Bar detection without ffmpeg's log: the height from the plan, the rows from `metadata=print`. *Done (no outcome changed): the rows from `metadata=mode=print:file=-` after cropdetect -- stdout (`f_metadata.c`: "-" is pipe:1), a `frame:` line then `key=value`s; cropdetect sets `lavfi.cropdetect.y1`/`y2` from the very values it logs (`vf_cropdetect.c`, n8.1.2), shown frame for frame on this build (15 and 13 frames, a black start's y2 under its y1 included). `bar_rows` reads them, a value not a row skipped (never a crash); the detection runs at `-v error`. The height the plan's (`shown`, the frame the ASS is drawn for): instrumented first, the log's height equalled it in every detection the corpus, suite and matrix run (360, heights 90 to 720, resized and with effects). `bar_height`, its log patterns and `fmt.awk_number` gone; awk's prefix rule kept, pinned on `fields.prefix`. `compare HEAD` 354 identical -- every burn's bar as before.*
- [x] Highlight: the pop's peak exact (`1 + 0.45/chars`); whether its settle (150 ms past the peak) may outlive a short word -- a design question, decided with its source. *Done (G4), decided with its sources: libass draws no event past its end and counts `\t` from the start (`ass_parse.c`, 0.17.1); bash's help promised "colour + smooth scale" (`ffman.sh:1470`); the timing (90 ms rise, 150 ms settle) had no recorded reason, the peak its measured one (kept). Measured: bash's settle was cut on every word under 240 ms (visibly, at 24-30 fps, to ~270 ms) -- rendered, its last frame 106.9% of its size; simulated with libass's formula (agreeing with the renders to the pixel), 4.6-8.6% at 24-30 fps. Three rules weighed -- bash's; done by the word's end (halves it, up to 7.4% left); done a frame before (none) -- the last chosen (the user's call): the window is the word less a frame (`Video.frame_time`, the source's -- a burn keeps its frames; `youtube` now shares its rate rule), the rise half of it (90 ms at most: bash's own rule when the frame is unknown), the settle by its end, a word no longer than a frame gold at once (a `\t` ending at 0 runs the whole event: never written); plain's fade the same. Rendered at 24/25/30 fps, 27 cases: the last frame 100.0% of settled (bash: up to 108.0%). The peak exact (`_number`). `compare HEAD` 334 identical, 20 changed: 537 lines of timings and peaks, 9 of words no longer than a frame gold at once, nothing else. Tests failing on the old code: the popped word, done by its last frame, a word within a frame, plain's fade, the exact peak, the frame time.*
- [x] `geometry.py`'s message without `awk_print`. *Done (G4): the size's ratio reduced, as --aspect-ratio states one (`w / h`: the sizes are integers) -- "are 16:9", exact at any size, never ambiguous (a near miss reads `8889:5000`, where a rounding could read as the ratio it is not). bash's `calc | cut -c1-6`, shown on the real code: `1.7777:1` for 16:9, `123456:1` for 12345678:1, `1.2345:1` for 1234567.5:1. Tests failing on the old code: the 64:35 case and two at the extremes. CHANGELOG.*

**6.5 Subtitles, beyond arithmetic**

- [x] Line wrapping: the font's metrics against the em estimate -- research libass's wrapping and what the highlight layers need, then decide. *Done (G4), researched and decided with the user. libass (0.17.1 source): wraps by shaped glyphs at PlayResX less the margins (90% here), a font sized to usWinAscent + usWinDescent, kerning off unless the script says (a calloc'd track); nixpkgs' libass has no libunibreak, so it breaks only at spaces -- rendered, a Japanese plain line ran past the margins, unbroken. The highlight layers need ffman's breaks (alike on both). So ffman breaks every line in every mode (`WrapStyle: 2`, plain's with `\N`), at the BBC's width -- 68% of 16:9, 90% of 4:3: 1.2 heights -- inside libass's 90%; Netflix's 42 characters agree. Measured, the em estimate filled 49-76% of libass's width on ordinary text, 111% on wide glyphs. Widths from the shipped font's advances (`subs/metrics.py`, standard library, bounded against hostile fonts): equal to HarfBuzz's on every character of all 16 shipped fonts -- the dependency weighed and declined: kerning moves a line -3.9% to +0.14% (median -0.3%), ligatures never widen, and the fonts libass falls back to cannot be known by any library here. The shipped fonts proven: the release's NAR hash is nixpkgs' (fetchzip), the local copies identical. Unspaced text breaks between characters, a mark with its own; the estimate stays for another --font, a missing file, a character the font lacks. With it, as mpv sets its own text: `Kerning: yes` (rendered: 487 to 469 px) and `Encoding -1` (each text's direction, and whole-text layout). The local gates and the corpus now carry the shipped fonts (Nix's suite always did; HEAD passed under them first). Rendered with them: the Japanese line in 2 lines within its width, the wide text within its line. `compare HEAD`: 263 identical, 91 changed -- each, on its full script, the header and its lines' breaks and places only, every event group's words and highlight the same (3,708 groups; a planted word and a planted highlight both caught). Tests failing on the old code: the header, the estimated and measured widths, plain's breaks, unspaced text, a mark; the reader branch by branch on fonts built to order (fontTools reads each as asked).*
- [x] Line breaking for unspaced scripts by their rules: kinsoku (no line opening on `。`, `、`, a closing bracket), Thai by its words (a preposed vowel, `เ`, opens its syllable; Thai needs a dictionary) -- from 6.5.1, which breaks them between characters, never inside a cluster. *Done (G4), option A with the user (no dependency). The rules researched, not recalled: UAX #14's classes (Unicode 15.1's LineBreak.txt -- Python's unicodedata is 15.1 too), PropList's Logical_Order_Exception (Thai's, Lao's, New Tai Lue's, Tai Viet's preposed vowels); every Thai character is SA -- UAX #14 leaves it to a dictionary. Measured against ICU 74.2 (PyICU, researched aside): its strict breaker and ffman's agree on 339 of 339 break positions over 31 Japanese and Chinese texts, the corpus's own included -- the two first misses were rules (LB22's ellipsis, LB25's prefix and postfix), now in; on Thai, ffman keeps every ICU word break, none after a preposed vowel, 59% of its own inside a word -- the dictionary's cost (ICU 31 MB, PyICU 8 MB, no types) declined. `subs/breaks.py` takes the cluster rules from ass.py; its table generated by `tests/support/linebreak.py` and checked against the UCD where present; words carry their gap, glued where no break may part them (kinsoku between Whisper's timed words too: a lone 、 never opens a line); a run wider than a line starts its own, then breaks between its units (CSS's overflow-wrap -- the first form broke it on the line it began, two words' fragments on one line, which the corpus showed); a mark advances nothing, estimated or missing from the font. Also closed: 6.5.1 broke unspaced text only when a whole chunk had no space -- a Japanese run in spaced text stayed one 41-character line. Corpus: two transcripts on which the old code breaks wrongly (`の|、`, `ます|。`, `และเ|รา`; the first drafts did not, so did not show it). `compare HEAD`: 351 identical, 5 changed -- those two and the three huge-font cases (words wider than a line, now broken), each the breaks and places alone. Tests failing on the old code: the emergency, its own line, a run in spaced text, timed punctuation, a mark's width (both paths); the rule pair by pair and ICU's strict breaks recorded (new module).*
- [x] `--highlight-colorize COLOUR`: the highlighted word's colour, a hex `#RRGGBB` (gold stays the default) -- with `chunk-word` or `word-highlight` and a burn, refused elsewhere as `--highlight-mode` is; `subs/colorize.py` and its one seam, `_gold`. (Researched: gold is applied in one place; libass interpolates `\t`'s `\1c` linearly in RGB, rendered.) *Done (G4). `subs/colorize.py` (`Colour`, `GOLD`, `parse`; ASS's byte order from `parse_color_tag`, gold's string unchanged), `Style.colorize`, `_gold` become `_colour_in` -- the one seam; the option declared, validated in `_burn` with `--highlight-mode`'s overlay check made one loop over both, carried by `ConvertOptions` (layer 3, as `subs`) to `burn.py`'s `Style`. Tests: parsing and its refusals (`#FFF`, `##`, a name, a space), blue first, the default and a given colour, the four refusals (no highlighting overlay, a name, empty, no burn), the script's colour; rendered through the CLI, a green word with no gold (gold is 255 off in red: no false pass). Corpus: `burn/colorize` (on `wx.json`, which chunk-word accepts -- its first two forms, `words.srt` and the word-level `words.ojf.json`, showed refusals instead), its plain-mode and bad-value refusals (360 cases).*
- [x] Motions: `rainbow` (each letter its own hue, the spectrum across the word, a 2 s cycle), `lsd` (saturated, letters a third of the wheel apart, 1 s), `iridescent`/`iridescence` (a pastel sheen, 3 s) -- six keyframes a cycle, exact at any saturation (to 1e-16); at most 3 flashes a second (WCAG 2.3.1: a pair of opposing changes of 10% relative luminance, or any involving saturated red), counted in the tests. (Rendered: per-letter colour tags move no pixel.) *Done (G4). Established first: libass reads `\t`'s times as whole ms (`dtoi32(argtod(...))`) and mixes each tag from the colour before it (chains are paths); WCAG 2.2's red flash (R/(R+G+B) >= 0.8, linear; 0.2 in u'v'). `colorize.py`: `Motion`, the three (`iridescence` the same object), `type Colorize`, `parse` by name in any case, `keyframes` (the fade's colour, then each sixth to the first past the end -- no freeze); `ass.py`: `_in` (the fade-in, one rule, never negative), `_lit` (a colour's fade, byte-identical), `_letters` (each cluster its block, through `_colour_in`). Rendered: each letter within 3 levels of its predicted colour; a popped word's scale reaches every letter (179 px, gold and lsd). Flashes counted high per WCAG 2.2 on every letter of 1-8 letter words, 0.3-4 s: rainbow 2/1, lsd 3/2 -- at the limit, not over -- iridescent 1/0; a planted 300 ms turn, 7/4 (the counter discriminates). Tests: names, the wheel's six exact, the spread across a word, the pastel's floor, the flashes, per-letter blocks under a pop, a lit chunk's spaces, rendered through the CLI (hues apart; gold would show one). Corpus: rainbow (chunk-word pop), lsd (word-highlight), Iridescence (chunk-word) -- 363 cases.*
- [x] Colour names: `gold`, `red`, `amber`, `teal`, `violet`... in any case, beside `#RRGGBB`. *Done (G4), researched first: CSS's named colours are the standard, but dark against the black outline (indigo 1.62:1, purple 2.23, blue 2.44, green 4.09, teal 4.40) and without amber; Tailwind CSS's palette (v3.4.17, its source fetched) at shade 400 is the darkest at which all 22 hues keep 7:1 (WCAG AAA; indigo 7.04), its 500 losing 11, its 300 paler beside white words. Gold stays #FFD700 (bash's, CSS's); CSS's synonyms grey, magenta, aqua; no white, no black. The table generated from the source and checked entry by entry; a test holds every name to 7:1. Two tests used `green` and `gold` as values to refuse -- now names: changed (`glitter`), the corpus refusal too. Corpus: `burn/colorize-name` (Teal), 364 cases. Reviewed: the help had lost its default to fit a line -- now a constant joined by an explicit `+`, with ruff's ISC003 off (basedpyright refuses implicit concatenation, which ISC003 asks for; a decision recorded in pyproject).*
- [x] `--font-color` and `--outline-color` (`#RRGGBB` or a name, with any burn): the text's colours, white and black by default. No outline given: black or white, whichever contrasts more with the fill -- never under sqrt(21), 4.58:1 (WCAG AA), over every colour; the highlighted word its own (a gold word on a black font's white outline would be 1.4:1), and the highlight fades in from the font's colours, not white. `white` and `black` join the names; a highlight the font's colour is noted. (Researched: libass's `\3c` mixes as `\1c`; `--vfx invert` is ffmpeg's `negate` on pixels -- no colour code to share.) *Done (G4). `colorize.py`: `WHITE`, `BLACK` (names now), `luminance`, `contrast`, `outline_for` (a motion: the best worst over its six keyframes, exactly -- each segment moves one channel, one way), `Colour.code` beside `ass`. `ass.py`: `HIGHLIGHTING` once (the options' copy gone), `Style.text`, `.outline`, `.text_outline()`; the header's colours; `_fade` from the font's colours, `\3c` only where the lit word's outline differs (the default writes none) -- its outline the paint's, not each letter's start (a first form gave a motion's letters each their own). The fade's start now `&H00FFFFFF&` beside the old `&HFFFFFF&`: one colour (50 frames rendered, 0 px apart). Options: one helper for both. Tests: the outline's rule and floor, contrast's numbers, the header, the fade, the outline's three cases, the note, the options; rendered through the CLI, black text outlined white, red text set apart from the same burn in white (a first criterion, pure red, missed thin strokes at 4:2:0; the motions box found this note and two docstrings blaming testsrc2's red bar -- the suite's clip is run.sh's dark gradient, testsrc2 only in a reproduction of mine). Corpus: four (368). Reviewed: the outlines were computed per highlighted word (WCAG's `** 2.4` each time) -- 40% slower on 5,000 words (0.223 to 0.311 s); now once a script (0.216).*
- [x] Their motions: every visible letter its own chain (`\1c`, `\3c`), through one painter wherever text is written; the phase by absolute time, so colours flow across events; the motion budget bounds it. A motion's outline: the one with the best worst contrast over its turn -- never a black-white flip, which would flash (rainbow and lsd: black, 2.44:1 at blue; iridescent 10.81). *Done (G4). The places text is written mapped first (`_plain`, `_block`/`_line` on both layers, `_word`). `colorize.py`: `keyframes(..., start)` -- the phase by absolute time (a second event from 1000 ms continues one event's keyframes exactly) -- `colour_at`, `_lag` once. `ass.py`: `_paint` (unchanged text without a motion: every existing output byte-identical), `_chain`, `_budget` (an event's: a plain subtitle's lines decided once -- a first form budgeted each line, ten lines ten budgets, which its test caught); `_Lines.first`, `.letters` (a letter's place across its subtitle); `_letters` the lit word's from each letter's own colour; `_solid` for the style line. Caught by the tests: a shadowed local wrote the outline's colour as its width (the header tests); an outline chain ran on past a held run (`end if end else dur`, found by FURB110). Corrected: box 1's notes blamed testsrc2 -- the suite's clip is run.sh's dark gradient; the rainbow highlight test re-checked there (gold 1 hue, rainbow 4). Letters counted in every layout: 3-5% on 5,000 words, kept. Corpus: three (371); the font-colour refusal moved to glitter, rainbow being a colour now.*
- [x] `rectangle`, in reverse video: the box the font's colour, its text the outline's -- white and black by default. (Swapped against RGB-negated: teal's box teal with black text, 11.28:1, against white with red text, 5.05:1; reverse video keeps the colour chosen and the pair's contrast.) A second style, `BorderStyle=3`, for the lit word (libass boxes each glyph: the hidden neighbours' boxes hidden too). Never over a neighbour, in `plain` and `pop`: libass double-scales a box from each glyph's origin (rendered: up to 119 px over neighbours' outlines), so the box's padding pops, not the text -- from `pad` to `pad + R`, the room beside the word and between lines less the neighbour's outline; abutting words a 1 px box, no pop. (Rendered: 30 cases, 0 px covered.) *Done (G4). `colorize.py`: `Rectangle` (`RECTANGLE`), `type Highlight`, `parse_highlight` (the font's and the outline's stay `parse`'s: no rectangle there). `ass.py`: `_edges` once (the header's outline and the box's), a `Box` style only with it (the default's header unchanged), the box's padding and pop's rise once a script, `_box` (the padding's pop, never `\fscx`), reverse video in `_lit` and `_boxed_letters` (`_chain` with the roles swapped), the lit events in `Box`. Rendered, ffman's own scripts: 0 px of a neighbour's outline under a box over 30 cases (3 sizes, plain and a pop's peak, 1-9 letters, lines wrapped); the default seen, black on white. Tests: the value, the style, reverse video at 2.8 (computed by hand: room min(0.15 x 64 - 4, 80 - 64 - 4) = 5.6, half), the pop to 4.6 and back with no `\fscx`, abutting a unit and still, word-highlight's, motions on the box and the letters; through the CLI, a white box where gold was (1,194 px more, the test asking 500). Reviewed: `self.boxed` for the branch, `isinstance` kept where it narrows the type. No cost: 0.234 s on 5,000 words (HEAD 0.243). Corpus: four (375).*
- [x] The bar a resize makes, blurred: placement from the plan, detection its fallback. *Done (G4), asked by the user (apollo.webm, 320x240, fit 9:16 with `--bblur`: no bar found; without `--bblur`, 92 of 320). Established: detection reads black rows on the planned picture, and a blurred bar has none; ffmpeg's fit (`scale_eval.c`: tmp_h rounded to the nearest multiple, then floored) and its placement round in ways a model would have to copy -- so the plan is measured, not modelled: a white frame of the source's stored size, pixels and format through the render's own head with its blur filled black (`head(measure=True)`), into the same cropdetect. A first design padded black, set aside for a hand-built pad and overlay that rounded a row apart (1363 against 1364) -- unrepresentative, their formats not the render's: ffman's own padded and blurred fits agree (186, 556; found in the review); the head read as itself is exact by construction all the same. The real render, a band at the source's foot, settled it: 186 rows, the measurement's. `_bar`: a fit with blurred bars, the plan's (`_planned`; the message "a blurred bar"); else detected (`_detected`), as before -- its seven blurred samples spared. Shown: the user's command, its subtitles centred in the blurred bar. Tests: the measured head the render's but its blur (as text), the bar's word, the measurement's command; through the CLI, the note's rows the rendered frame's, 186 (failing on the old code). Corpus: `burn/bblur-bar` (16:9 into 9:16), 376 cases. (Superseded by the next box: read before what modifies it.)*
- [x] The bar read before what modifies it: the source through the resize alone, no effect. *Done (G4), asked by the user (the last box kept a source's own bars uncounted in a blurred fit: "shouldn't this be detected before source modification?"). Established: detection read the frame after the resize and after the effects before the text; no effect there moves the picture, each recolours or draws -- and they disguised the bar: `invert` hid it, `blur` took 6 rows of 92, chromatic aberration 1; the plan alone (the last box's white frame) missed a source's own (109 against 92). So one path: the real frames through the resize alone, its blur filled black (`head(measure=True)`) -- the source's bars and the resize's, as the render places them; the white frame, `_planned` and `planned_args`, gone. Shown on real frames first: apollo 92 and a letterboxed source 109, the black fit and the blurred alike. The real-render test's band now grey (black would be the source's own bar). Tests failing on the old code: a source's own bar in a blurred fit, invert, blur, chromatic aberration. S247 departed from, with the user: bash found no bar under an inverted letterbox (read after the effect, its bar white), its text at the margin -- on that same white bar; now the bar, 160 of 360, the text centred in it (rendered: legible by its outline, as at the margin). The note says black: the picture's bar before the effect. Corpus: `burn/bblur-boxed`, `burn/bar-invert` (378 cases). compare HEAD: 375 identical, 3 changed -- the two (126 of 320: bars.mp4's own 60 rows with the fit's; 60 of 240 inverted, none before) and `burn/resize-vfx`, unpredicted: its command's labels only (va2 to va; renamed, byte-identical) -- the old detection applied VHS through the render's own Effects, a read-only pass taking the render's labels: a coupling gone.*
- [x] The player as ffman burns: mpv's subtitles and `occivink.crop`. *Done, asked by the user. mpv.conf takes ffman's plain style at mpv's 720 lines (options.rst at v0.41.0: scaled pixels at a 720-line window): font, size 38, outline 1.65 (mpv's own defaults too -- ffman copied them), sub-margin-y 40 (60 at 1080, 5.573%), sub-margin-x 64 (5% of a 16:9 width; mpv's margin is a size, so other ratios differ), sub-pos 100 (was 105). `tests/test_mpv_conf.py` holds them to ffman's own style line, two thirds (failing on the old mpv.conf; skipped where the tree is ffman alone, as in Nix). `occivink.crop` removed with its bindings (c, Alt+c, C) and notes; blur-edges, built from its source, now fetches occivink/mpv-scripts itself at occivink.nix's commit and hash -- the NAR hash recomputed from GitHub's tarball: equal, one store path; packages.nix parses (tree-sitter-nix). The run-book's item 15 checks that fetch now, not crop.*

**6.6 Metadata and streams kept** (F8, F9; G4 each; research and skills before
any code -- §4's way; the spec first where the command line changes)

Three metadata formats, converted into one another; files of them read and
written by `convert` and a new `ffman meta`; and every convert keeping what
its target can hold, the converters carrying attached metadata where the
target holds it otherwise. In order:

*6.6.1 Research* (no code; each box's findings the next boxes' sources)

- [x] ffmetadata, all of it: ffmpeg's documentation (`doc/metadata.texi`) and
      `ffmetaenc.c`/`ffmetadec.c` at n8.1.2 -- the header, comments, escaping,
      line continuation, sections (global, `[STREAM]`, `[CHAPTER]` with
      `TIMEBASE`/`START`/`END`), what a reader refuses; ffmpeg's generic keys
      (`avformat.h`) and each container's mapping of them (the muxers' tables:
      MP4 atoms, Matroska tags, Vorbis comments). Measured: every key and a
      chapter round-tripped through each container ffman writes. *Done (research). `.agents/skills/ffmetadata/references/format.md`, measured by its `scripts/measure.py` (run). The source differs from the documentation: the probe checks `;FFMETADATA` alone (the version unread); sections are exact, case-sensitive lines -- a `[chapter]` makes its lines global tags; `TIMEBASE`, `START`, `END` in that order, a missing `START` logged and defaulted; a backslash makes any byte literal (`\n` is `n`); keys match without case, the last wins; a line without `=` and a comment's continued line are dropped. ffmpeg's writer escapes no carriage return, which its reader ends a line at: only an escaped one round-trips. Keys: avformat.h's 21 and two modifiers. Through twelve containers, of 23 (`encoder` always ffmpeg's): Matroska, Ogg, Opus, FLAC, MP3 keep all (Matroska upper-cased; Ogg's at the stream); MP4 12, MOV 9, WAV 10, AVI 9 (`album` back as `product`), MPEG-TS 2; chapters exact in Matroska, MP4, MOV, MP3, Opus (starts only), none in Ogg Vorbis, FLAC, WAV, AVI, TS. Three faults of the measurement found and fixed before recording: codec options before an `-i` (theirs), tags read at the global level only, a pipe cut short. Reviewed (owner's request): the record corrected in six places -- a negative `START` the reader keeps, `fftools`' `copy_chapters` clamping (not the reader); `[STREAM]` applied only by `-map_metadata:s:...`, a media file's stream tags exported only by `-map 0 -c copy` or `-map_metadata 0:s:0` (Ogg's are its stream's); MP4's whole `ilst` (six numeric atoms, `©too` defaulting to ffmpeg's name); AVI's `product` from `avidec.c`'s own table; MPEG-TS's service name from `title`; a chapter without `END` losing the line read in its place (the source's reading had missed it) -- each now measured by the script, with the empty key and value, `NUL`, an escaped CR and MP4 with `use_metadata_tags` (all 23).*
- [x] Vorbis comments, all of it: the Vorbis I specification §5 (vendor
      string, `NAME=value`, the name's characters and case), Xiph's field
      names, the chapter extension (`CHAPTERxxx`, `CHAPTERxxxNAME`,
      `CHAPTERxxxURL`), `METADATA_BLOCK_PICTURE`, keys in use (`ALBUMARTIST`,
      `TRACKNUMBER`, `DISCNUMBER`, `REPLAYGAIN_*`, `CUESHEET`), ffmpeg's
      mapping (`vorbiscomment.c`). Xiph's own format, not ffmetadata's: its
      specification defines the comments inside a stream only, so the text
      file `vorbiscomment` names (`NAME=value` a line) is the tools'
      convention -- vorbis-tools' `vorbiscomment -l`/`-c`, with its `-e`
      escapes, and FLAC's `metaflac --export-tags-to`/`--import-tags-from`,
      without multi-line values (F9): the form decided from them, with sources. *Done (research). `.agents/skills/vorbiscomment/references/format.md`, measured by its `scripts/measure.py` (its own Ogg and FLAC readers: every comment seen as bytes), with ffmpeg 8.1.2, `metaflac` 1.5.0 and `vorbiscomment` 1.4.3 (built from its tag against libogg 1.3.6 and libvorbis 1.3.7: nixpkgs' pins). Sources: the Vorbis I spec (libvorbis 1.3.7), RFC 7845 5.2, RFC 9639 8.6-8.8 with its errata, the Xiph wiki (VorbisComment, Chapter Extension), Picard's tag mapping (87 names in use). Found: the name ranges differ (FLAC's RFC allows `~`; the Vorbis spec, libFLAC and `vorbiscomment` refuse it); names may repeat -- ffmpeg joins them with `;`, indistinguishable from a `;` in a value, and drops empty values and names; ffmpeg writes keys unchecked (a name holding `=`); **ffmpeg's chapter writer (Opus) puts every start with a fraction of 0.5 s or more a second late** (`av_rescale` rounding; unchanged in master); its reader takes `01.5` as 1.005 s, drops chapters without a fraction or of 100 hours and more, and leaves a `NAME` before its time a plain tag. The text form: `vorbiscomment -e` escapes `\n` `\r` `\\` (skips bad lines, exit 0); `metaflac` escapes nothing, refuses blank and `#` lines atomically, and drops an unterminated last line silently; both write the same comments from single-line values. Decided: ffman's text form (UTF-8, LF on every line, `vorbiscomment -e`'s escapes, names 0x20-0x7D but `=`, no `NUL`, a malformed line refused with its number). Reviewed: Picard's count corrected (87 names, 85 tags), source-only claims marked, three cases measured. Reviewed again (owner's request): `CUESHEET` as a comment added (metaflac's convention; to ffmpeg a plain tag); the six Ogg codecs whose headers ffmpeg writes comments into, from source; the vendor (`Lavf...`, `ffmpeg` bitexact) measured, not exported on reading; `vorbiscomment` refuses Opus, `metaflac` FLAC-in-Ogg; order stated as the spec has it (none). And found: **ffmpeg reorders comments** -- `av_dict_set` moves the last entry into a replaced key's place (`libavutil/dict.c`), and `encoder` is replaced on every write: chapter comments by `-metadata` into FLAC came out `NAME` first, a title lost; Ogg kept the order. All measured by the script.*
- [x] Cue sheets, all of it: the CDRWIN format -- every command (`CATALOG`,
      `CDTEXTFILE`, `FILE`, `FLAGS`, `INDEX`, `ISRC`, `PERFORMER`, `POSTGAP`,
      `PREGAP`, `REM`, `SONGWRITER`, `TITLE`, `TRACK`), its values and limits
      (`MM:SS:FF` at 75 frames a second, 99 tracks, quoting, encodings), the
      `REM` conventions in use (`GENRE`, `DATE`, `DISCID`, `COMMENT`,
      `REPLAYGAIN_*`); sources: CDRWIN's guide, libcue's grammar, readers in
      use; FLAC's `CUESHEET` block and comment (`metaflac`'s import and export,
      F9). *Done: `.agents/skills/cue/references/format.md`, `scripts/measure.py` (33
      cases through libcue, metaflac at CD-DA and 48 kHz, ffmpeg), `scripts/cuedump.c`
      (libcue 2.3.0's public API; libcue built here with bison and flex from Ubuntu's
      archive). CDRWIN's guide is only on the Internet Archive, unreachable here: its
      rules come from GNU ccd2cue 0.5's free rendering and quotations of it -- and GNU's
      one slip (the first index "of the current TRACK"; CDRWIN: of a file) recorded.
      mpv 0.41.0 read in source only. Found: no reader agrees with another -- libcue
      checks almost nothing (times unchecked, numbers ignored, a bare number read as
      frames, an unquoted multi-word string lost, `REM` values cut to one word, a
      spurious "syntax error" for every sheet ending in a newline, no `CATALOG` getter);
      metaflac keeps no text, ignores `FILE` (a multi-file sheet refused at CD-DA, stored
      wrong otherwise), exports non-CD offsets as sample numbers, and silently drops a
      `CATALOG` behind a UTF-8 BOM; mpv refuses a whole sheet for one unknown command
      (libcue's own `COMPOSER` among them); ffmpeg reads no `.cue`, and of FLAC's block
      makes chapters from each track's first index point (`INDEX 00`: the pregap opens
      the chapter) titled with its ISRC. The form every measured reader accepts is
      recorded. Reviewed (owner's request): the block's rules from libFLAC's
      `format.h` and `format.c` ("at most 100 index points" was unproven: index
      numbers 0-99 are what is enforced); `flac --cuesheet` shares metaflac's parser;
      found -- ffmpeg drops a FLAC's block, copied or encoded, writing no chapters
      in its place; mpv reads a `CUESHEET` tag as chapters at `INDEX 01` when a file
      has none (`demux.c`); libcue keeps quoted `REM` values whole (only
      `REPLAYGAIN_*` cut); metaflac accepts offsets past the stream's end, which
      ffmpeg makes a chapter without length. All measured but mpv's.*
- [x] The mappings between the three, and what each loses: ffmetadata and
      Vorbis (keys, chapters as `CHAPTERxxx`, streams' sections; repeated names
      against unique keys -- ffmpeg's `;` join -- and `COMMENT`/`DESCRIPTION`,
      `ENCODEDBY`/`encoded_by` as tools write them); either and
      cue (chapters and tracks, `INDEX 01` and `START`, a chapter's `END` from
      the next index or the duration, `PERFORMER`/`TITLE`/`SONGWRITER` and
      their keys, `REM` and the rest, 1/75 s rounding). A table, each row
      sourced; what cannot cross stated, so a conversion notes it. *Done:
      [`ffman-mappings.md`](ffman-mappings.md) (two tables, each row sourced, its
      loss stated) and [`ffman-mappings.py`](ffman-mappings.py) (parts A-E, run;
      the vorbiscomment skill's readers imported -- its script now takes its
      tools in `main()`, output unchanged). Sources: FFmpeg's converters both
      ways, mpv's and Kodi's cue mappings (source), cuetools' `cuetag.sh` (built,
      run), Picard's definitions where no reader maps a field (`CATALOG` is
      `BARCODE`, not `CATALOGNUMBER`; `SONGWRITER` nearest `WRITER`). Found:
      `COMMENT` with `DESCRIPTION` -- ffmpeg keeps the first in order; Ogg merges
      global tags into a stream's, the stream's winning, FLAC drops `[STREAM]`;
      chapters vanish from a stream copy with `-fflags +bitexact` and no tags
      (the writer's `if (m)`); `-map_metadata -1` drops chapter titles,
      `-map_metadata:g -1` does not; cue times cross into ffmetadata exactly
      (`TIMEBASE=1/75`), into Vorbis within 1/3 ms and back exactly, while 92.5%
      of milliseconds do not survive a cue; mpv and Kodi end a track at the next
      `INDEX 01`, libcue at `INDEX 00`. Refuted: chapters lost by encoding with
      `+bitexact` (the encoder's tag remains). Corrected in the cue record:
      mpv converts a `.cue`'s charset (uchardet). Reviewed (owner's request): every
      direction covered -- a table of the six (ffmetadata, Vorbis, cue: each into
      the others; the same format into itself is each skill's round trip); table 1
      completed at its edges (F: a key with `=` read back as another key, a
      non-ASCII key written and read by ffmpeg, empty values dropped back, CR
      breaking ffmetadata, a picture no tag, `CUESHEET` exact); table 2 completed
      (`FILE`, a track's `REM`, libcue's commands -- G: cuetag's `ARTIST` is the
      composer before the performer); table 3 new, into cue -- no tool writes one
      (`cueconvert`: cue and TOC only) -- its rows proven by building five sheets
      from them and reading each back (H: libcue, metaflac with ffmpeg, cuetag).
      Found in the review: Kodi reads `REM DATE "1991"` as no year
      (`ExtractNumericInfo`), so the cue skill's rule "REM values quoted when they
      hold spaces" was wrong for numbers and gains (`-7.03 dB`) -- corrected
      there and in its record, the skill re-checked and re-packaged; a cue-born
      first chapter after 0 comes back at 0 from FLAC's block (ffmpeg's `INDEX
      00` rule).*

*6.6.2 Skills* (§5; validated, packaged, presented -- before any code)

- [x] `ffmetadata`: the specification, every key and value, examples, sources. *Done: `.agents/skills/ffmetadata/` -- `SKILL.md` (218 lines: the grammar and ffmpeg's reading of every edge, the rules for a writer whose files read back exactly, the 21 keys with meanings and values, chapters, streams, what each container keeps, examples, sources), `references/format.md`, `scripts/measure.py` (which reads and checks the skill's own example). `quick_validate.py`: valid; packaged (`ffmetadata.skill`: those three files). Three test prompts (`evals/evals.json`, not packaged) answered by the skill and run: an audiobook's file into `.m4b` (tags, three chapters exact, an escaped `;`), a custom tag kept into MP4 by `use_metadata_tags`, an Ogg's tags exported by `-map_metadata 0:s:0`.*
- [x] `vorbiscomment`: the same, its text form as decided. *Done: `.agents/skills/vorbiscomment/` -- `SKILL.md` (203 lines: the format by its specifications, names and values, the chapter extension with the rules to write it exactly and ffmpeg's two faults -- its seconds rounded, its order not kept --, what ffmpeg does with comments, the two tools' text forms and ffman's decided grammar, examples, sources), `references/format.md`, `scripts/measure.py` (its part F checks the skill from its own text: the example file read as described and equal through `vorbiscomment -e`, the metaflac and ffmpeg chapter commands). `quick_validate.py`: valid; packaged (three files, each identical to the committed one). Three test prompts (`evals/evals.json`) answered by the skill and run: FLAC chapter titles lost to ffmpeg's order (metaflac keeps it), multi-line lyrics into `.ogg`, a chapter at 1:30.5 into `.opus` (ffmpeg's own: 91.5 s; the comments: 90.5).*
- [x] `cue`: the same. *Done: `.agents/skills/cue/` -- `SKILL.md` (158 lines: the format with every command, practice, how the four readers disagree, FLAC's block and the `CUESHEET` tag, rules to write a sheet every reader accepts -- times by integer arithmetic to the nearest frame, at most 6.67 ms off -- and to read one correctly, examples, sources), `references/format.md`, `scripts/measure.py` (its last part checks the skill from its own text: the example through libcue, metaflac and ffmpeg -- chapters at 0, 255 and 542.987 s --, the three commands as written, the `CUESHEET` tag byte-equal, the time rule over every millisecond to an hour), `scripts/cuedump.c`. `quick_validate.py`: valid; packaged (four files, each identical to the committed one). Three test prompts (`evals/evals.json`) run: a FLAC's block lost through ffmpeg and carried by metaflac; a podcast's sheet with half-frame times (12:30.5 -> `12:30:38`); a chapter titled with its ISRC.*

*6.6.3 The converters* (pure: no ffmpeg; from the skills)

- [x] The model: one metadata representation -- global tags, chapters at exact
      times, streams' tags, a cue's files and tracks -- and its notes of what
      a format cannot hold; refusals name the line. *Done:
      `src/ffman/meta/` (layer 3, pure; the architecture test failed on its two
      modules until they had their layer), `model.py`: `Tag`s as written (order,
      repeats, case: names compared without ASCII case only -- ffmpeg's
      `av_tolower` folds A-Z, Vorbis names are ASCII), `Chapter`s at exact
      `Fraction` seconds (an end optional: Vorbis and cue give none), streams'
      tags, a cue's `Disc` (files, tracks, each `Index` naming its file: EAC's
      track over two files fits), `Written` (a writer's text and its notes),
      `exact` and `nearest` (the mappings' rounding, a half up: `values.round_half_up`, the
      codebase's own).
      Invariants every format shares raise `ValueError` (the codebase's
      `__post_init__`). `errors.refuse_at`: `SOURCE:LINE: message`, lines from
      1 -- the GNU Coding Standards' form (4.4) after ffman's `ffman: error:`.
      26 tests (every frame to an hour through milliseconds and back; Hypothesis
      on the rounding); suite 1121 passed at 100% coverage, the corpus 378
      identical, the matrix 761 passed, ruff and basedpyright clean. No
      behaviour changes (no command reaches it yet): no CHANGELOG row. §3 and
      `AGENTS.md` name the package. Reviewed (owner's request): `nearest` now
      `values.round_half_up` (it had re-implemented it); `values` renamed
      `values_of` (the module `ffman.values` beside it); `Track.text` and
      `Disc.text` renamed `cdtext` (CD-Text's, as libcue names it, beside
      `cdtextfile`); the rising check one helper (`_rising`), its messages
      unchanged (the tests pin them); the citation style `section 3`. Proven:
      `cli.main` prints `refuse_at`'s refusal as `ffman: error: album.cue:12:
      ...`, exit 1; no product module imports `meta`.*
- [x] ffmetadata: reader and writer, round trip exact. *Done:
      `src/ffman/meta/ffmetadata.py`. The reader agrees with ffmpeg on every file
      it reads right, and refuses, naming the line, what it reads otherwise than
      written -- found in `ffmetadec.c` and measured: a line without `=`
      (dropped), `[chapter]` (global tags), a repeated key (the last kept), a
      line ending in an escaped `\\` (**the next line read into it**: no value
      can end in `\\` -- ffmpeg cannot read back its own export of one), a
      comment ending in `\\`, a comment with `=` ending the file (**read as a
      tag**), a CR alone (it ends a tag's line, not a chapter's), a NUL, and
      chapter times not plain integers (`START=12abc` read as 12, `TIMEBASE=1`
      as 1/10^9). The writer escapes the CR ffmpeg's forgets, writes exact
      times (1/1000 where it divides, else the least time base; past `%d`,
      nanoseconds, noted), fills a missing end from the next chapter or the
      duration, and notes and leaves out what ffmpeg cannot read back. 59
      tests: every refusal with its line; round trip 400 examples (read of
      write is the model, write of read the text); ffmpeg as oracle -- ffprobe
      reads ffman's files as ffman's model (40 examples), and shows each new
      refusal's reason. The skill gained the findings (rule 7, five reading
      rows, six measured edges; re-packaged). Gates: suite 1179 passed at 100%
      coverage (the example inlined -- the build has no skill; a test holds the
      copy equal where the repository is); matrix 761 passed; ruff and
      basedpyright clean. Reviewed (owner's request), four passes:
      **a crash** -- `START=` or `TIMEBASE=` of thousands of digits reached
      `int()`, which refuses 4300 (`sys.int_info`): now refused first, past 19
      significant digits; a line in a message one line, 60 characters at most
      (`_shown`: a joined line spanned several, a huge one was echoed whole);
      `_ends` quadratic, now by bisection (100,000 chapters: 0.74 s); the two
      escape loops replaced by two regexes beside the tokenizer's; the header's
      message ("must begin"); the docstring exact that the time lines' one form
      is stricter than `sscanf`; the oracle test's `end or start` explicit; the
      strategy `ffmetadata_models` (not the module's name). Each rewrite proven
      against the committed code, differentially (20,000 inputs each).*
- [x] Vorbis text: reader and writer, round trip exact. *Done:
      `src/ffman/meta/vorbis.py`, the skill's decided form (a comment a line,
      every line ending LF; names ASCII 0x20-0x7D but `=` and `~`; values with
      `\\` `\n` `\r` alone; anything else refused, the line named). Chapters are
      the Chapter Extension's (`CHAPTERxxx=HH:MM:SS.mmm`, `NAME`, `URL`); from
      `ogm_chapter`'s source, a name ffmpeg may read as a chapter's though not the
      extension's is refused (`CHAPTER01`; `CHAPTER1000NAME`, chapter 100's to its
      `sscanf`), a chapter's comment before its time or repeated too; every other
      name a tag (`CHAPTER000ARTIST`, ffmpeg's own writer's). The writer times by
      division (the skill's rule), and notes and leaves out what the form cannot
      hold (rounding, past 99 h or 1000 chapters, ends, chapter tags but `NAME`
      and `URL`, a name not Vorbis' or a chapter's, a NUL, streams, a disc).
      Proven: vorbiscomment 1.4.3 `-w -e` stores ffman's comments byte for byte
      and `-l -e` gives back ffman's text exactly (the form is its own); the
      skill's example written back byte for byte. 48 tests -- round trip 400
      examples; ffmpeg as oracle (ffman's text, unescaped independently, in a
      FLAC: ffprobe reads its tags and chapters as the model, 40 examples; and
      shows each chapter refusal's reason); found by it: an empty title is no
      comment to ffmpeg (`if (!tl || !vl)`). Reviewed: messages exact (a URL
      repeated is joined, not "kept last"), ffmpeg's lengths named, `shown` moved
      to `errors.py` and one ffprobe helper in `tests/support/media.py` (DRY).
      Gates: suite 1228 passed at 100% coverage; matrix 761 passed; ruff and
      basedpyright clean. Reviewed (owner's request), four passes:
      **a coverage illusion** -- the round trip's and the oracle's names could not
      spell "chapter" (letters a, b, z), so neither had tested a chapter-like tag:
      now drawn too (`CHAPTER1`, `CHAPTER1000`, `chapter000artist` ...), and ffmpeg
      confirms each a tag; the two dead filters gone. The two writers' notes one
      shape, `model.left_out` -- `{what}: {why}: left out` for all that is dropped,
      the readers' words for the same facts; `errors.shown` and `left_out` tested
      directly; `_a_chapters` named. Checked: RFC 9639's 8.1 and 8.6 (Xiph's map).*
- [x] Cue: reader and writer, round trip exact within its frames. *Done:
      `src/ffman/meta/cue.py`. Reader: the skill's reading -- commands without
      case, BOM, CR LF, quoted strings to the next quote, unquoted to the line's
      end, the disc's lines before its first TRACK, EAC's layout accepted;
      refused, the line named: an unknown command or line, one out of place or
      repeated, a malformed CATALOG/ISRC/flag/number/time, a track without INDEX
      01, a FILE no INDEX follows, a time going back in its file, an INDEX 02+
      in a new FILE, a NUL, a lone CR. Keywords stored upper case (the writer
      writes them so); libcue's CD-Text read. The model's Disc and Track now
      hold the cue structure (tracks and indexes one more each, an INDEX 01,
      files in turn, from 01 one file, never back). Writer: what every reader
      accepts; noted and left out -- a string with a quote, a break or a NUL,
      or ending in `\`; libcue's CD-Text; a bad CATALOG/ISRC/flag; EAC's INDEX
      00 in the file before; noted -- a REM's ends trimmed, over 80 characters,
      a FILE name a quote cannot hold (written as readers lose least).
      Proven: 500 discs (202 multi-file) written without notes and read back
      equal; libcue reads all 500 as the model (one-off); the skill's example
      read as stated and written back byte for byte. Found: the property test
      caught the reader refusing the standard multi-file layout (fixed); libcue
      -- a value ending in `\` swallows the lines after, an INDEX after 01 in a
      new FILE and every track after EAC's layout misplaced (all measured, in
      the cue skill, with `CDTEXTFILE` added to its rule 2). Reviewed: a REM's
      ends changed silently (now noted), a no-break-space line dropped silently
      (now refused), `_BREAKS` named. 74 tests. Gates: suite 1318 passed at
      100% coverage; matrix 761 passed; ruff and basedpyright clean. Reviewed (owner's request), to
      convergence: `LIBCUE_CDTEXT` checked against libcue's scanner (equal);
      the strategy reached every edge but track 99 (first track drawn to 95) --
      now to 99, 2000 discs round-tripped; a FILE name no quote holds is now
      always unquoted -- measured, a quoted one ending in `\` makes libcue fail
      the whole sheet -- its note as measured (mpv no name; libcue none with a
      space), a claim first written from assumption, caught against the
      measurement; the model's docstrings true to it (its invariants the
      format's; keywords upper case, text as written).*
- [x] Every conversion between the three through the model: property tests
      (exact where lossless; each loss noted), corpus cases. *Done:
      `src/ffman/meta/convert.py`, `convert(meta, source, target, media=,
      durations=)`: the mappings' rows as two field tables (the disc's, a
      track's: ffmetadata's key, Vorbis' name, the cue's command) and ffmpeg's
      four names, each direction reading them; each loss noted, the target
      writer's own left to it. ffmetadata/Vorbis: the four names and a
      chapter's title renamed, a repeated name joined with `;` (noted). Cue
      into either: a track a chapter at INDEX 01, exact (frames/75), placed
      past the files before it (their durations required), ends at the next
      start; what nothing maps noted once a kind. Into a cue: chapters sorted
      (noted), INDEX 01 at the nearest frame (noted), track 1 after 0 its INDEX
      00 at 0, gaps, overlaps, the last end and past 99 noted, REM quoted only
      for spaced text. Two rows kept where the mappings dropped them
      (`CATALOG` as `BARCODE`, a track's `ISRC`, into ffmetadata: its keys are
      free), marked in the record. The Vorbis writer now notes only ends a
      reader cannot recover (at the next start: none lost). Proven: every
      direction, 1000 models each, a change in meaning only with a note (found
      by it: no chapters made one track unnoted, now noted); the whole
      disc through ffmetadata and Vorbis exact, ffmetadata and Vorbis through
      each other the same in meaning, no notes. Cases, pinned text and notes
      (the outcome corpus gains them with the command line, 6.6.4): an EAC
      sheet into both and back; ffmpeg's export into Vorbis and cue; the Vorbis
      skill's example into both. Reviewed: `_cue_lines` one for the disc and a
      track, `Track.start_index`, positions and asserts gone. 29 tests. Gates:
      suite 1348 passed at 100% coverage; matrix 761 passed; ruff and
      basedpyright clean. Reviewed (owner's request), to
      convergence: the property "each loss noted" was near vacuous in four
      directions (995-1000 of 1000 models noted anyway) -- every direction now
      has its silent path tested, ffmetadata and Vorbis through a cue exact
      (models from whole discs); `_meaning` per format, a chapter's title
      alone unified, which unmasked a silent change: an ffmetadata chapter's
      own `name` key became a Vorbis title -- now noted, left out; the tables
      carry their holder (`_Table`), no identity test.*
- [x] Interoperable: `metaflac` the oracle (`pkgs.flac`, in the checks) --
      its exported tags and cue sheets read by ffman, ffman's read by it,
      where the formats meet (single-line values). *Done: `pkgs.flac` in the
      checks' inputs (not `ffmanRuntime`: ffman never runs it; nixpkgs' pin is
      FLAC 1.5.0, read at the locked revision), a `metaflac` fixture holding
      the pin. `tests/test_meta_metaflac.py`, on a CD-DA FLAC: tags set by
      metaflac and exported, read by ffman as the model; ffman's tag file
      imported and exported by metaflac byte for byte (single-line values
      without `\`; an escape past that, metaflac's literal text); random discs
      through FLAC's CUESHEET block exactly as it keeps them (no text, PRE
      alone, AUDIO or DATA, the lead-in and lead-out REM lines after the last
      track -- measured, added to the cue skill); metaflac's export of an EAC
      sheet pinned and read; its 48 kHz export (sample numbers) refused by
      ffman, the line named. Reviewed: the strategies reach every case (no
      coverage illusion); a full disk, found when the tests filled /tmp (a 7 MB
      FLAC copied per example, 3.3 GB): now silence (98 kB) and one working
      copy -- 216 kB at most, measured. Gates: suite 1357 passed at 100%
      coverage (the 6 run, metaflac on the gate's PATH as in the check);
      matrix 761 passed; ruff and basedpyright clean; the Nix expression
      parsed (tree-sitter, a broken copy refused). Reviewed (owner's request), to
      convergence: the test's own `run()` was `tests/support/media.tool()`
      (removed); its silent CD-DA FLAC now `conftest`'s `cd_flac`, which the
      Vorbis oracles use too instead of an ffmpeg run an example (`CD_SECONDS`
      in `tests/support/media.py`: no import from conftest); both fixtures'
      version checks through `tool` (two `noqa` gone). 35 lines fewer.*

*6.6.3 reviewed whole (owner's request), to convergence -- what only shows
across its boxes: a public name is one another module or a test uses
(`ffmetadata`'s `HEADER`, `VERSION`, `NANOSECONDS`, `cue`'s CD-Text tuples and
80, `convert`'s tables and `BARCODE` made private, by token; the model's
ranges stay its contract); no logic doubled across modules (nine names in two,
each its format's own); the readers on a BOM, CR LF, a lone CR and a NUL each
as their formats' readers do -- but the cause unseen: `errors.shown` now writes
what prints nothing (`\ufeff`, `\t`, `\x00`, `\xa0`), ffmetadata's refusal
quotes the line it found (or says the file is empty), and a Vorbis file with
CR line ends is refused for its CR, not its missing break. Gates: suite 1358
passed at 100% coverage; matrix 761 passed; ruff and basedpyright clean.*

*6.6.4 The command line* (`ffman-spec.md` first, then help; completion is 6.11's)

- [x] `convert` with metadata files: `.ffmeta` (ffmpeg's: ffmetadata, no
      `--preset`), `.txt` in (ffmetadata or vorbiscomment, told by its first
      line) and `.cue`, in and out; `--preset ffmetadata` (the default) or
      `vorbiscomment` for a `.txt` out, from a `.ffmeta`, `.txt` or `.cue`; a media file's tags and chapters out to either; what cannot be
      (a metadata file into a picture flow) refused. *Done: spec 3.9 first (and
      3.6's `--preset`, 3.8's order); `meta/files.py` (a file's format: its
      extension, a `.txt`'s first line, `--preset`), `jobs/convert/metadata.py`,
      `Flow.METADATA` first with every refusal. A media file's tags and
      chapters: probed first (every flow's refusals), ffmpeg's ffmetadata export
      with `+bitexact`, and the tags ffmpeg drops either way -- `encoder`
      (`mux.c`), `creation_time`, `company_name`, `product_name`,
      `product_version` (`ffmpeg_mux_init.c`), found when a corpus case lacked
      `creation_time` -- restored from the probe (`Media.tags`). Output as
      3.1; notes on stderr; an empty result refused; strict UTF-8, the byte
      named. `--normalize` needs `--preset youtube`. 23 tests; 15 corpus cases
      (393): against HEAD, 375 identical, 18 changed -- the 15, the help's
      line, the two messages. Reviewed: a missing or non-media input refused
      as every flow does (was a misread export), the spec's rule stated once,
      README examples; the previous commit's unformatted test line (`ruff
      format --check` now in every gate). Gates: suite 1381 passed at 100%
      coverage; matrix 761 passed; ruff (check, format) and basedpyright
      clean.*
- [x] `ffman meta`, its spec (8) and tags: a metadata file written or edited
      -- input any (a media file's exported), output any, as convert's;
      `--set`, `--add`, `--unset`, `--clear` in ffmpeg's generic keys
      (`avformat.h`), each format's spelling from one field table shared with
      the converter; declarative (a fixed order, contradictions refused). *Done: spec 8 first; `meta/fields.py`
      (the converter's tables moved, one source), `meta/edit.py`
      (`Edits`, `apply` in each format's model; a cue's disc fields one each),
      `jobs/meta/` (options, run; `io.py`, moved from convert's flow, which
      shares it), `media/paths.new_output`, `META` and its Tags group, the
      command. Found in building: removing after converting noted losses of
      what was removed -- now removals in the source's words, then the
      conversion, then additions. 49 tests (a property: a set key holds its
      one value, every other tag untouched); 7 corpus cases (400): against
      HEAD 392 identical -- convert's 15 metadata cases among them, the IO move
      proven -- 8 changed (the 7, the top help). Gates: suite 1415 passed at
      100% coverage; matrix 761 passed; ruff check and format, basedpyright
      clean. Reviewed (owner's request), to
      convergence: spec 8 named 3 of meta's 12 messages -- now every one, and
      the removal rule; `--unset` of what a cue cannot hold was refused where
      the tag formats find nothing to remove -- now nothing to remove in each;
      a cue made from a metadata file named that file as its media (`FILE
      "x.ffmeta"`, convert's too since its metadata box) -- now the input's
      stem, noted (`io.cue_media`, both flows; spec 3.9); `GENERIC` private.
      Against e0666f3: 398 identical, 2 changed (the two cues from ffmetadata:
      the note). Suite 1416 passed at 100% coverage; matrix 761 passed.*
- [x] `ffman meta` chapters, one exact time syntax (`62.5`, `1:02.5`,
      `1:01:02.5`, `4650f`; never `MM:SS:FF`, which reads as `H:M:S`):
      `--chapter`, `--retitle`, `--chapter-set`, `--drop-chapter`,
      `--clear-chapters`; in a cue, a track. *Done: spec 8 first;
      `meta/time.py` (four forms, digit runs bounded), `meta/chapters.py`
      (`ChapterEdits`; numbered edits in the input's words, before
      converting; `--chapter` after the last chapter starting no later; in a
      cue a track at the nearest frame, renumbered, unused files dropped,
      track 1 holding the time before it; refused inside another track or in
      a cue over several files); `key`, `spelled` to `fields.py`, `put` to
      the model, so `edit.py` and `chapters.py` share them without a cycle.
      Found in building: a new chapter at 0 left track 1 empty; a retitle
      twice named `--chapter-set`; a track's REM branch unreachable (no
      track field is quoted). Reviewed: `bisect` on Vorbis' unordered
      chapters (no defined place: now after the last no later); Vorbis'
      `NAME` set twice through `--retitle` and `--chapter-set` (a silent
      last-wins: now refused); two suppressions replaced by typed code. 51
      tests (properties: time order kept, a drop takes the input's Nth); 4
      corpus cases (404): against 0a21562, 399 identical, 5 changed. Gates:
      suite 1467 passed at 100% coverage; matrix 761 passed; ruff check and
      format, basedpyright clean. Reviewed again (owner's request),
      to convergence: the spec had drifted from the code in five messages
      (three reworded in review, two never listed) -- now the code's; the
      edit's and the chapters' "set where it stood, its spelling kept" one
      helper (`model.set_where`). Against 515cc91: 404 identical.*
- [x] `ffman meta`, a cue's own: `--catalog`, `--isrc`, `--flags`,
      `--pregap`, `--file`. *Done: spec 8 first. Decided:
      no `--catalog` or `--isrc` -- `--set barcode=` and `--chapter-set
      N:ISRC=` are those edits already (the field table's); a second flag
      each would say one thing two ways -- each now refused unless well formed,
      for a cue. `--flags N=` and `--pregap N=TIME` (`INDEX 00`, the pregap in
      the file; `PREGAP` is silence it has not): a cue's tracks, so its input a
      cue -- N its track N, applied before converting, as every edit of N (a
      conversion into a cue sorts chapters: N would move); `--file NAME`: the
      cue's one FILE, the stem's guess and its note replaced. `cue.py`'s
      `is_catalog`, `is_isrc`, `are_flags`, its reader's and writer's checks
      too; `ChapterText` (the parser's input; `parse_chapters` split into its
      checks). 21 tests; 3 corpus cases (407): against 7d798ef, 403
      identical, 4 changed (the 3, meta's help). Gates: suite 1484 passed at
      100% coverage; matrix 761 passed; ruff check and format, basedpyright
      clean. Reviewed (owner's request), to
      convergence: `--file` with a name no cue holds (a space or quote
      first, a line break, a NUL) reached the writer's guard -- a Python
      traceback, not a refusal (shown): now refused before any work
      (`cue.is_file_name`, the writer's guard too; spec 8). Tested: a pregap
      on EAC's layout lands in its INDEX 01's file. Every message checked in
      spec 8 (13, all there). Against b2d5e33: 407 identical.*
- [x] `ffman meta -o -`: the result to stdout (inspection, pipes). *Done:
      spec 8 first. Its format `-p`'s (`ffmetadata`, `vorbiscomment`, `cue` --
      `cue` stdout's alone: a `.txt` holds ffmetadata or Vorbis), else the
      input's if a metadata file (inspection shows it as read), else
      ffmetadata. No partial file, no path printed; notes on stderr, stdout
      the text alone; an empty result printed empty (a pipe takes it); a new
      cue's FILE `media`, noted. `run.py` one pipeline (`_edited`), two ends
      (`write_output`, `io.print_output`); `files.format_of`, `Preset`.
      Found: the help told nothing of `-` (usage, `-o`, `-p`: now said); a
      disc's TITLE is `ALBUM` (my test's expectation, not the code). 9 tests;
      2 corpus cases (409), run for real -- no file written -- so their
      stdout recorded: against d0eb79c, 406 identical, 3 changed. Gates:
      suite 1497 passed at 100% coverage; matrix 761 passed; ruff check and
      format, basedpyright clean. Reviewed (owner's request), to
      convergence: stdout in a non-UTF-8 locale's encoding (latin-1) met a
      Japanese title with a `UnicodeEncodeError` traceback (shown) -- now
      UTF-8 bytes to its buffer, whatever the locale (spec 8; a test with a
      latin-1 stdout). A closed pipe: `| true` exits 141, silent (spec 2);
      `| head -c 10` exited 0 with 18 MB written -- bare Python the same in
      this sandbox (its pipe took the whole write), not ffman. Against
      ebc0d39: 409 identical.*
- [x] A metadata file applied to a media convert (`--metadata FILE`): decided
      here, and 6.10's `--attachment`, `--cover`, `--metadata`, `--title` box
      narrowed to what remains. *Done: spec 3.10 first.
      ffmpeg's `copy_meta` (source): a global `-map_metadata N` leaves each
      stream's tags to the automatic copy, and two `-map_metadata` merge --
      so the file **replaces** the global tags and chapters, every stream's
      own kept, through one mapping (`plan/streams.kept_metadata`), never
      two. The file read in any format, converted to ffmetadata (a cue's last
      track ending with the media), its stream sections noted not applied
      (`jobs/meta/io.applied`); after the output's kind is checked, before
      any pass (F6). In every flow that keeps metadata (picture, tracks,
      YouTube); alone, a flow of its own (`Flow.TAGS`, `jobs/convert/tags.py`:
      streams copied, the container the input's -- across containers is
      6.6.5's). Refused: not a metadata file, a GIF or an image, a changed
      container alone, a cue over several files, in the metadata job. 6.10's
      box narrowed to `--attachment`, `--cover`, `--title`. Found: the
      architecture table's layer-4 block out of order since the meta box
      (sorted). 12 tests, real ffmpeg (the language kept, each); 3 corpus
      cases (412): against cede5e3, 408 identical, 4 changed. Gates: suite
      1510 passed at 100% coverage; matrix 761 passed; ruff check and format,
      basedpyright clean. Reviewed (owner's request), to
      convergence: `attach` and `youtube` read the file before their own
      refusals -- `--add-subs` onto an output that exists reported the
      file's syntax error, not the output (shown); the four flows' repeated
      line now one helper, `tags.metadata_file`, each calling it after its
      refusals (a test: an existing output first, in every flow). The name
      `prepared` was taken -- `resize` and `burn` hold a local of it (ruff's
      F823). Every message checked in spec 3.10 (6, all there). Against
      1f81b12: 412 identical.*

*6.6.4 reviewed whole (owner's request), to convergence -- what only shows
across its boxes.* Hostile values for every option it added, run in-process
(121 runs; an exception escaping `main` the defect): the time syntax (to
99,999 hours) outran what a cue's `MM:SS:FF` holds (999,999 minutes), so a
far `--chapter`, and a far chapter converted into a cue (6.6.3's, by
`convert` and by `meta`), met the writer's guard as a traceback (shown, three
routes). Now `cue.LAST_FRAME` and `LAST_TIME` state the range once: a
conversion leaves such chapters out, noted (as the 99-track cut); `--chapter`
refuses one; the writer's guard through them (spec 3.9, 8). Not defects:
a NUL in a path (no argv carries one), and the harness's own StringIO
stdout, which has no buffer. Swept: no stale names, no ghost `--catalog`
or `--isrc`, one plan number in source (`tags.py`'s docstring: now the
reason). Against cedc514: 412 identical. Suite 1515 passed at 100%
coverage; matrix 761 passed; ruff check and format, basedpyright clean.

*6.6.5 Streams kept* (one stream plan, every convert flow; F8)

- [x] A container change is a job: copied (a remux), `--video-codec`
      (lossless), `--audio-codec` and `--preset` re-encoding; the same family
      with nothing asked still nothing to do (M066). *Done: spec 3.11 first.
      `Flow.REMUX` (`jobs/convert/remux.py`, `tags.py` folded in): another
      extension, a codec, `--metadata`, with no size, effect or burn; each
      stream copied unless a codec is asked (3.3's lossless; `sound`); into
      its own container whole (covers, data -- as `-map 0` kept them), else
      the picture alone (`0:V`: covers are box 5's). What a container holds
      **asked of the pinned ffmpeg** (`output.holds`): the planned command
      with `-t 0` opens each encoder and writes the header, no frame
      (measured: H.264 encoded or copied into WebM fails, VP9 and Opus pass,
      FFV1 into MP4 passes -- against memory); a failure retried per kind
      names it (`output.check_held`, `Held`). The picture's flow asks too:
      a resize from H.264 into WebM failed after its work (found, fixed).
      Decided: the same extension with nothing asked is nothing to do (M066);
      `.mp4` to `.mov` a remux -- another muxer (F8: MOV drops covers);
      the owner confirmed. Found: the trial lacked the metadata input (index 1);
      it marked every job's record with a work directory (78 records) -- now
      a directory of its own, `ffman-trial.`, the codebase's convention;
      a same-container copy dropped covers and data -- whole again (a cover
      measured kept). 14 tests (real ffmpeg); 3 corpus cases (415): against
      26c8ec0, 405 identical, 10 changed, each expected. Gates: suite 1533
      passed at 100% coverage; matrix 761 passed; ruff check and format,
      basedpyright clean. Reviewed (owner's request), to
      convergence: `--lossless` alone counted as asking a codec, so a
      refusal named `--video-codec h264`, a flag never given (shown) -- now
      asked means `--video-codec`, in both flows; `--video-codec`'s help
      said "default: the source's", false for a remux (a copy) -- now says
      both; the picture's encode arguments one helper
      (`output.lossless_picture`, the remux's and the trial's). Proven fine:
      `--audio-codec none` leaves no sound (`-an` over the map), audio-only
      remuxes, MP3 into M4A refused by the trial. Against baca688: 414
      identical, 1 changed (the help).*
- [x] Subtitles: copied where held; text into the target's (mov_text; SRT,
      ASS as ASS, WebVTT in Matroska; WebVTT); images where held, else left
      with a note naming the track -- resize, effects and burn too. *Done: spec 3.12 first.
      Each subtitle stream decided alone (`jobs/convert/subtitles.py`), by
      the remux's trial: the copy, then `mov_text`, `webvtt`, `srt`, `ass` --
      the first held, no table. Measured with subtitle-only trials: SRT and
      ASS into MP4 and MOV take `mov_text`, into WebM `webvtt`, into
      Matroska a copy (ASS as ASS); AVI, FLV and Ogg hold none. An image
      subtitle passes the copy alone (F8, no OCR); no image source could be
      made here -- ffmpeg encodes no bitmap from text -- so that path rests on
      F8's measurement and the same code. Each conversion and each loss noted,
      the track named (language, title). In the remux and the picture's flow
      (resize, effects, burn). The probe reads each subtitle stream
      (`Subtitle`: codec, language, title) instead of a count; attachments
      named so (`attachments`, `attachment_args`), the family rule theirs
      until their box. Found: an AVI copy of H.264 refused -- ffmpeg itself
      fails it (shown), the trial right; a test's private import and its
      suppression -- now the public `kept()`; the spec's attachment note
      still pointed to `--add-subs` (the old combined note's). 12 tests
      (real ffmpeg; a real attachment through both flows); 1 corpus case
      (416): against 80825e2, 412 identical, 4 changed -- every one an input
      with subtitles. Gates: suite 1539 passed at 100% coverage; matrix 761
      passed; ruff check and format, basedpyright clean. Reviewed (owner's request), to
      convergence: 20 subtitle tracks cost 40 trials, each opening the input
      (0.83 s against 0.17 s, a tiny file: seconds on a disc rip) -- the trial
      sees only the codec, so one answer a codec a job (0.18 s, the same 20
      `mov_text`; an unknown codec never shared); a test counts the trials
      per track and the kept numbered in turn around one left out. Out of
      scope, found: `--preset youtube` drops subtitle tracks without a note
      -- carried as a box, the owner's call. Against c3e8f4f: 416
      identical.*
- [x] Tags and chapters: always; the MP4 family with `use_metadata_tags`;
      chapters into Ogg Vorbis, Theora, Speex, FLAC -- and Opus -- as `CHAPTERxxx`
      comments, in order (FLAC by `metaflac`: ffmpeg's `-metadata` can reorder them,
      a title lost; Ogg by `-metadata`, the order checked) (the converter; ffmpeg's muxers write none
      there, and its Opus one puts starts of a fraction of 0.5 s or more a
      second late; its readers take them as titled chapters, FLAC measured, F9). A
      FLAC `CUESHEET` block too, for players reading only that -- `metaflac`
      (`flac` may be a runtime dependency of ffman: the owner's decision) --
      decided here, measured against the comments. A source FLAC's block is
      carried by `metaflac` too: ffmpeg writes none and drops it, copied or
      encoded again (6.6.1, cue: measured). *Done in two steps, spec
      3.13 first. Owner's decisions: the MP4 family keeps iTunes' atoms
      (`use_metadata_tags` writes `mdta` alone, `movenc.c`) -- custom tags
      noted; the CUESHEET block carried from a source FLAC, never made --
      measured against the comments: a FLAC with both reads back in ffmpeg
      and mpv as untitled chapters (`flacdec.c` by track number,
      `avpriv_new_chapter` overwriting); `flac` in `ffmanRuntime`. Tags: the
      job's own trial read back (`output.trial`). Chapters into Ogg and FLAC
      as CHAPTERxxx by `-metadata`, ffmpeg's off: measured, Vorbis lost them,
      Opus put them a second late, and `-metadata` lost the last title in all
      three -- `dict.c` moves the last entry into a replaced one's slot,
      `mux.c` replaces `encoder`: so `encoder=` first (FLAC's comments then in
      exact order; FLAC needs no metaflac). Implied ends dropped before
      converting: only a gap noted. `output.write` finishes on the partial
      before the rename. Found: a path parsed from argv; two corpus cases
      exercising nothing; an unreachable branch (FLAC into FLAC keeps every
      sample: measured) removed; a dry run printing metaflac with no block.
      Not checked here: `pkgs/default.nix`'s syntax (no nix: the flake check).
      13 tests (real ffmpeg, metaflac); corpus 418: against 352cb84, 416
      identical, 2 changed (the new). Gates: suite 1552 passed at 100%
      coverage; matrix 761 passed; ruff check and format, basedpyright
      clean. Reviewed (owner's request), to
      convergence: `--add-subs` and `--preset youtube` dropped a custom tag
      without a note -- "every convert flow" kept by three of five (shown);
      both now tag too, YouTube's trial with its own mapping (its real one
      counts the normalised audio, absent from a trial and under
      --dry-run: an index would point elsewhere). `Given.applied` a Path:
      four flows build it alike. Against 077ccab: 418 identical. Reviewed a third time (owner's
      request), for what lies between the box's own parts: step 1 read a
      source's chapters through ffmpeg, and step 2 found ffmpeg misreads a
      FLAC holding a block -- so FLAC into FLAC wrote that misreading as the
      output's comments: titles Two and Three gone, times 1.7 s and 2.5 s
      written 0 and 1 (shown; data the box itself lost). A FLAC's chapters
      now from its own comments (`metaflac`, the CHAPTERxxx lines, the Vorbis
      reader, their format kept -- `NAME` read as ffmetadata would lose the
      titles again). And a false note: ffmpeg ends a comment's last chapter
      at the duration rounded to 1/1000 s (3.007 for 3.0065) -- the last end
      now implied within a millisecond, the others exactly. Against 5cd1cf4:
      419 identical. Reviewed a fourth time (owner's
      request), the skills reread and their failure modes countered
      (familiarity: values traced, not prose re-read; a fix widened around).
      Found: the third review's fix refused a whole job over a malformed
      chapter comment ffmpeg skips (shown) -- now read as ffmpeg reads it,
      noted; and every title with a backslash or a line break was altered
      into Ogg and FLAC, silently (shown: `a\b` written `a\\b`) -- the
      Vorbis writer's text form, escapes and all, went to `-metadata`, which
      takes values raw: `vorbis.comments` now gives the raw pairs, `write`
      escapes them (its output byte-identical: its tests and the metaflac
      oracle unchanged). Swept: no other `-metadata` takes file text. Against
      7bd9030: 419 identical. Reviewed a fifth time (owner's
      request): the skills and the depth techniques reread -- invariant
      hunting the one my reviews lacked, each fix checked one hop. The
      invariant, now written: a chapter title passes through ffman unchanged
      through any chain of conversions. Violated (shown): the fourth review
      wrote a line break raw, and the third read a FLAC's comments by
      metaflac's text export, where a value's line break cannot be told from
      two comments -- ffman's own FLAC lost the rest of the title at the next
      hop. Now `media/flac.py` reads the comment block byte-exact (each
      comment's length), `vorbis.text` the writer's escaping, the reader the
      same; a test each way a file is not one (11), and the invariant through
      two hops. Against 1adedbb: 419 identical. Reviewed a sixth time (owner's
      request), nix at hand (nix-portable 2.20.6: its git the system's,
      cache.nixos.org not reachable here, so evaluated, never built):
      `pkgs/default.nix` parses and evaluates; flac 1.5.0 in the runtime
      package's derivation and the checks'. Invariants proven through
      chains: chapter times and titles through MKA -> FLAC -> Ogg -> FLAC; a
      CUESHEET block through two FLACs, CD audio too; source metadata never
      fails a job. Omissions, by the project's own rule: a new runtime tool
      gets a job in `ffman-installed` -- none had (a wrapper without metaflac
      would pass every check); now one, its script as nix renders it run here,
      failing without metaflac. And `ffman-lint`'s vulture -- never in my
      gates -- had failed since 6.6.3: `values_of`, then `same_name`, dead
      product code tested by itself; removed, `folded` now tested in their
      place. Against 13b551c: 419 identical. Reviewed a seventh time, bounded
      by the stop rule (an independent angle, its end defined): spec 3.13 read
      bottom-up as prose -- it still said a FLAC's chapters were read by
      metaflac, the third review's mechanism the fifth replaced (a text export
      cannot tell a line break from two comments); now it says the block,
      byte-exact. No other document claimed it. The code unchanged this round:
      its gates at 013b43d stand.*
- [x] Attachments: kept into Matroska; elsewhere, metadata files among them
      (ffmetadata, Vorbis text, cue) converted into the target's tags and
      chapters (automatically, 6.6.3's converters); the rest left with a note
      (MP4 fails on them, WebM drops them silently). *Done: spec 3.14 first.
      Measured: ffprobe names each attachment (filename, mimetype);
      `-dump_attachment` extracts it byte-identical, then exits non-zero (no
      output given) -- so the file, not the status, is the answer. Into
      Matroska carried as they are (3.3's family rule, every flow's).
      Elsewhere the first attached metadata file that applies, by its
      filename, tried in order, goes through `applied()` as `--metadata`
      would (it replaces; `--metadata` wins) -- one entry point,
      `tagging.metadata_file` (moved there from `remux` in review), in all five flows; each refused one noted with
      its reason, never a refusal of the job; those after, noted left out.
      `Media.attachments` a tuple of `Attachment` (by filename: the mimetype
      measured, then dropped -- vulture: nothing read it). Found: a note
      claimed a readme.txt a metadata file, and order decided correctness
      (a refused first left the cue untried) -- now tried in order, no claim
      made; `runner.workdir` touched before any attachment, a scratch
      directory for every job (108 records) -- now only on a dump; an
      assertion of mine near-tautological -- exact. 6 tests (real ffmpeg);
      against d43047d: 419 identical. Gates: suite 1577 passed at 100%
      coverage; matrix 761 passed; ruff, vulture, basedpyright clean. Reviewed (owner's request), by
      invariants: an attached cue's chapters reach FLAC's comment path too
      (titled, the one note a true millisecond rounding); a `SET.CUE` is
      recognised (`ext_of` folds case). Structure: `metadata_file` and
      `_attached` lived in a flow, `remux`, and four flows imported it --
      moved to `tagging`, beside `Given`, their one concern (where a job's
      tags and chapters come from). Found stale since the remux box:
      07-tools named `jobs/convert/tags.py`, deleted then. Against c1685b7:
      419 identical.*
- [x] Cover art: kept where held; into Matroska extracted and attached; else
      left with a note (MOV drops it silently, WebM fails). *Done: spec 3.15 first.
      Measured: MP4, M4A, FLAC, MP3 keep a cover copied attached_pic; MOV
      drops it silently; Matroska writes it as a video track; WebM, Ogg,
      Opus fail on one; a header trial cannot read a cover back (-t 0 writes
      no packet), so its exit alone decides. Matroska's cover art from its
      specification: JPEG and PNG, `cover.(jpg|png)`, the cover first; ffmpeg
      reads the attachment back as a cover. `covers.kept` (`Job`: the input,
      the job's own trial, the streams before): into Matroska extracted
      byte-exact and attached; into MOV noted; elsewhere copied if the job's
      trial holds it. In the remux, the picture flows, YouTube; the remux's
      own container now `0:V?` plus the cover. `output.Kept` shared with
      subtitles. Found in building: a cover-only trial said FLAC and MP3
      hold none (an audio muxer refuses no sound) -- now the job's own;
      `cover` used before its definition in YouTube; probe edits lost by my
      script (asserted now); a YouTube cover-first bug suspected, not
      reproducible (the MP4 muxer reorders): a question, no change. Proven
      by chain: M4A -> MKA -> FLAC -> MP4, the cover byte-identical. 10
      tests; against 031429e: 417 identical, 2 changed (0:v? to 0:V?, no
      cover in either). Gates: suite 1586 passed at 100% coverage; matrix
      761 passed; ruff, vulture, basedpyright clean. Reviewed (owner's request), by
      the paths the box's tests had not run: a resize and a re-encoding remux
      keep a cover (shown); YouTube said `a .mp4 holds none` -- false, MP4
      holds one. Its video options were written for every video stream:
      `-vf` filtered the copied cover (an ffmpeg error), and `-profile:v
      high` reached the PNG's encoder, which cannot parse it (each isolated by
      elimination). Every option now `:v:0`, the picture's alone, and a test
      that every one is; YouTube's real encodes unchanged (the matrix).
      Against 688ffe2: 404 identical, 15 changed -- the YouTube cases, their
      option spellings alone (no status or note). Asked by the owner, whether a
      cover needs an aspect ratio: none -- every format keeps it as it is
      (shown, landscape and portrait). But Matroska names it by orientation,
      as its specification says (matroska.org, RFC 9559's Cover Art):
      `cover_land. Reviewed a third time (owner's
      request): spec 3.15 read against the code's notes -- it listed two of
      five; now one form,`the cover (CODEC): WHY: left out`, every WHY named.
      The JPEG path, never run end to end:`cover_land.jpg`,`image/jpeg`,
      byte-identical, back into M4A -- now a test. No source changed
      (shown): cc292ad's outcome and matrix stand.*` wider than tall (its example 960x600), `cover.*` square
      or portrait, case-sensitive. ffman named every one `cover` -- now
      `_named` follows it from the cover's size (the probe's `Cover` holds
      width and height; unknown, `cover`). Measured first: ffprobe sizes PNG
      and JPEG covers; ffmpeg reads `cover_land.png` back as a cover, so it
      round-trips. Found: 07-tools' cover row broken since 688ffe2 -- a `|`
      in `cover.(png|jpg)` split its cell; rewritten without one. Against
      4e136fc: 419 identical.*
- [x] `--preset youtube` drops an input's subtitle tracks without a note
      (found in 6.6.5's subtitles review; bash's preset did the same). *Done:
      the owner's call -- carried, as every flow (3.12): `mov_text` in its MP4,
      each conversion and loss noted; the first pass untouched. Reviewed again (owner's request):
      input 0 the source in its final pass (the subtitle maps right); an
      attachment dropped without a note by YouTube and `--add-subs` alike
      (shown) -- both now ask `attachments()`, the one policy every flow
      shares (a Matroska output from `--add-subs` measured keeping it); the
      YouTube tests' preset setup one fixture (three copies), the attached
      source one fixture (two). Against e197b3d: 419 identical.*
- [x] Proven: sources carrying every kind of stream, each container pair's
      outcome and notes measured; the corpus, README, 07-tools, CHANGELOG.
      *Step 1 (fixes the measurement found): one Matroska source with every
      kind (video, audio, SRT, a font and a cue attached, a cover, chapters,
      a custom tag) into twelve targets. Found: into FLAC the picture vanished
      without a note (`flacenc.c` drops it at warning level, shown) -- now not
      mapped, noted; a refused job (WebM, AVI, MP3, Ogg, Opus) said an
      attached cue was applied before refusing -- `metadata_file` now returns
      its notes (`tagging.Applied`), told after the refusals; the note now
      says the cue applies in place of the media's. Every kind, after:
      held, or noted. Against 4ad9632: 419 identical. Step 2: the measured table a matrix test
      (`tests/suite/test_streams_proven.py`, nine targets: status, every
      stream, every note). Step 3: the corpus builds `all.mkv` (EVERYTHING,
      last, its attachments METADATA's), five `proven/*` cases -- whose
      records showed the step-1 fix half done: `applied()` itself told the
      cue's conversion notes before the refusal; it now returns them too,
      `--metadata`'s alike (spec 3.10). Step 4: README (what a conversion
      keeps), 07-tools, CHANGELOG. Against 7bfd301: 420 identical, 4 changed
      -- the proven cases: three reordered, the refused one stripped of
      false notes. Gates: suite 1593 passed at 100% coverage; matrix 770
      passed; ruff, vulture, basedpyright clean. Reviewed (owner's request): a
      metadata note told exactly once in all five flows (shown); the FLAC
      rule ignored what was asked -- `--video-codec ffv1` into `.flac` wrote
      the file without its picture (shown): now refused before any work;
      `--lossless`, whose sound a FLAC holds, still noted. Against 9705dfd:
      424 identical.*

*6.6.6 Review*

- [x] The section reviewed whole: formats, converters, command line, streams.
      *In progress. Sweeps across the section, one concern each (the
      boxes had their own reviews): 07-tools' 52 references -- every one
      exists; the left-out notes -- one grammar (3.12's `--` its spec's);
      the flows' notes loops -- `--add-subs` alone never asked covers.kept,
      so into Matroska a cover became a plain video track, first in the file
      (shown): its maps now all but covers, the cover placed as every flow's
      (spec 3.15). Against 2d929da: 396 identical, 28 changed -- `attach/*`,
      their maps alone. Gates: suite 1595 passed at 100% coverage (287 s:
      past my gate's own 280 s cap, which had cut three runs off silently --
      uncapped now); matrix 770 passed; ruff, vulture, basedpyright clean. Sweep 5, error
      handling: three local catches of a refusal, each told or noted; one
      note printed at once, as F4's -- `_media_chapters`', not reproducible
      before a refusal (its flows check first), yet the one place left
      breaking the rule every job note follows: returned now, told with the
      job's others. Against 0ea5f42: 424 identical. Sweep 6, the spec's
      promise that every message is specified: 25 messages' fixed words
      searched in the spec -- 3 absent (an attached file's `ffmpeg dumped
      none`, which the cover said as `extracted`: one phrasing now; the
      CUESHEET's `metaflac failed`; `ffman meta`'s `nothing to write`):
      each specified. Sweep 4: no broad video map left (`0:v?`, `-map 0`).
      Against 6dfe189: 424 identical.*

**6.7 Its own workspace and repository** (the owner's: PyPI, MIT OR Apache-2.0,
Python >= 3.13, a flake building all; before 6.8, so `subverter` is born a package)

Decided, with the owner: a uv workspace (docs.astral.sh/uv, "Using workspaces":
one lockfile, members editable to each other; uv's own split, core apart from
CLI) of three packages -- `ffman` (the CLI and its jobs), `ffmeta` (`meta/`),
`subverter` (`subs/readers/`, the cue model; 6.8's converter); `ffman-core` not
split (no consumer but `ffman`); `media/`, `graph/`, `effects/`, the burn
pipeline stay in `ffman` (measured: each imports `media` or `graph`). Its own
repository, `veramachine/ffsuite` (the owner's: an organization for the NixOS
project's repositories; the repository named for the tools it holds, `ffsuite` -- `fftools`,
first chosen, is another's project on PyPI; first planned as `veralvx/ffman`), history kept -- its authorship one, unified before its first push
(the owner's decision: trees, dates and messages kept, the hashes messages cite
re-pointed); nixos-config takes it as a flake input -- not a submodule (a second pin beside `flake.lock`; Nix >= 2.27 needs
`inputs.self.submodules`). Nix builds it from source with nixpkgs' builders
(`pypa-install-hook`: `installer`, bytecode at levels 0 and 1, measured); uv is
the development tool; uv2nix only once a dependency is missing from nixpkgs.
Names free on PyPI (measured: `ffman`, `ffmeta`, `subverter`, 404).

*6.7.1 Research* (done before the section, its facts the boxes' ground)

- [x] Measured: the tools by call site -- `ffmpeg`, `ffprobe` (7 modules: all);
      `ffmpeg-normalize` (`youtube.py`: one feature; on PyPI); `metaflac`
      (`cuesheet.py`: one rare feature); `oxipng`, `jpegoptim`, `gifsicle`
      (`plan/encode.optimizer`). No check before use: a missing optimiser
      fails the job, nothing written (shown); a missing `metaflac` fails every
      FLAC to FLAC, a cue sheet or not. The font: `FFMAN_FONTS_DIR` alone (the
      Nix wrapper's), libass's `fontsdir` and ffman's measuring both; two files
      used, IBM Plex Sans Regular and Bold, 276 KB (OFL-1.1). Read: csan
      (`checks.yml` uv matrix, `publish.yml` Trusted Publishing, `release.yml`,
      `Justfile` groups), imi (dependency review, Dependabot automerge, audit,
      cocogitto -- monorepo package tags -- dprint, templates, CONTRIBUTING).

*6.7.2 The tools, by what each is* (in nixos-config first: the gates as ever)

- [x] `ffmpeg`, `ffprobe` required: looked up once (`shutil.which`) before any
      work; absent, refused: `ffprobe not found: install ffmpeg
      (https://ffmpeg.org)`. In the spec's opening (what ffman needs); a test on a
      `PATH` holding neither. *Done. Measured first: `meta` and
      `convert` on metadata files alone run with no ffmpeg at all -- a check at
      start would have refused them; so `dispatch` requires both for every
      flow but METADATA, after choosing it. The runner names any tool missing
      at launch (`missing`), the one place every launch passes, `shutil.which`
      deciding it is the tool and not another file (typeshed's `filename` is
      `Any`: no second boundary). Shown: ffprobe without ffmpeg refused before
      any work, no work directory left; `meta` on media refused naming
      ffprobe. 7 tests; 424 identical; suite 1602 at 100% coverage; matrix
      770; ruff, vulture, basedpyright clean. Reviewed (owner's request): its
      test's "no work directory" assertion was vacuous -- the fake input fails
      at the probe, before any directory, the check or not; a mutation (the
      check removed) showed it never ran. Now a spy on the runner's two
      launches: none, not even the probe -- the same mutation fails it, the
      probe's argv shown. `_PROVIDERS`' repeated provider one constant; the
      spec's `meta` sentence unambiguous. A tool present but not executable
      is `not found`, as `execvp` sees it: right, no usable one.*
- [x] `ffmpeg-normalize` left as it is used today (the owner's decision):
      `env XDG_CONFIG_HOME=$FFMAN_NORMALIZE_HOME ffmpeg-normalize ...`, the
      command on `PATH`, its presets through `FFMAN_NORMALIZE_HOME`; Nix's
      `ffmpeg-normalize.override { ffmpeg = ffmpeg-full; }` on the wrapper's
      `PATH`, the presets directory generated. No Python dependency (on 26.05,
      nixos-config's pin, nixpkgs has no such Python package -- measured: the
      build's runtime-deps check would fail). For pip users, documented:
      `--preset youtube` needs ffmpeg-normalize on `PATH` and
      `FFMAN_NORMALIZE_HOME`, refused otherwise as today. Re-assessed at NixOS
      26.11 (nixos-unstable has `python3Packages.ffmpeg-normalize`, measured):
      a Python dependency, run as `sys.executable -m ffmpeg_normalize` (it has a
      `__main__`), `FFMPEG_PATH` handed the ffmpeg ffman runs (it reads it
      first, measured: `get_ffmpeg_exe`), the presets bundled. *Done: no code changed (shown, 0
      lines under `src`). Measured first, the case a pip user meets most --
      ffmpeg-normalize not on `PATH`: the note, `env`'s own line naming it,
      `ffmpeg-normalize failed`, nothing written -- refused as today, and
      unpinned (test 515's stub exists and fails); now pinned. Spec 1 states
      when it runs (`youtube_sound`: the sound not AAC LC 48 kHz stereo, or
      `--normalize`), its refusals word for word, the 26.11 re-assessment.
      Test 515's hand-made presets the `youtube_home` fixture. Suite 1603 at
      100% coverage; the outcome report and the matrix stand (no source
      changed). Reviewed (owner's request), by
      mutation: the pinning test passed with ffmpeg-normalize present -- a
      present one failing for its own reason (empty presets: PCM into
      `.m4a`) gives ffman the same words, so ffman's line cannot tell missing
      from failing. Now its cause asserted, `env`'s line through `capfd`
      (the child's descriptor); the mutation fails it. And my refactor had
      cut test 515's `assert not out.exists()` (left on the new test, twice):
      restored, 515's assertions identical to its original (shown).*
- [x] `metaflac` optional: a FLAC's CUESHEET block found by `media/flac.py`
      (block type 5: `media/flac.py` taught to list the blocks), `metaflac` asked
      only when there is one; absent: `the
      source's CUESHEET block: metaflac not found: left out`, the job done. A
      FLAC without one never needs it (today it fails: fixed). *Done. Found reading the carry:
      it ran `metaflac --export-cuesheet-to` to learn whether a block was
      there, after ffmpeg wrote -- so a missing metaflac failed every FLAC
      to FLAC, its encode wasted. Type 5 confirmed by `metaflac --list`
      ("type: 5 (CUESHEET)"). `media/flac.py`: one block walk (`_read`), two
      clients -- `comments` as before, `has_cuesheet`. The finisher: no
      block, nothing asked; `--metadata`'s note; metaflac absent, noted
      (`missing`'s words), the job done; an export failing with a block
      there refused, no longer silent. Shown end to end: no block without
      metaflac written, no note; a block without it, written and noted; with
      it, carried identical. Mutation-proven (three): the no-block test
      first passed with its guard removed -- the which-check also stops
      before a launch -- and now asserts the false note's absence too.
      Spec 1 (its `metaflac not found` example, now untrue, generalised),
      3.13; 07-tools; CHANGELOG. 424 identical; suite 1610 at 100%
      coverage; matrix 770; ruff, vulture, basedpyright clean. Reviewed (owner's request), by
      mutation: two more survived -- the export's refusal removed (the import
      of nothing then refused with the same words) and the two checks
      swapped (no test held `--metadata` without metaflac). Now the export
      test asserts no import tried, and a test holds the replace note, not
      `metaflac not found`, without metaflac; both mutations fail them.
      `finisher`'s docstring had drifted: it now says what it does. The
      source's change docstring-only (syntax trees compared with HEAD's):
      the outcome report and the matrix stand; suite 1611.*
- [x] The optimisers optional: `optimizer` asks `shutil.which`; absent, warned
      once, `oxipng not found: the .png written unoptimised`, the output kept,
      exit 0. Each tool's case tested; corpus `env/` cases without them. *Done. In `output._produce`, the
      one place an optimiser runs: `shutil.which` first; absent, noted
      (`missing`'s words), the partial finished and renamed, exit 0; present
      and failing, refused as before (test_convert_job's, passing). Shown for
      each format with a `PATH` of ffmpeg and ffprobe alone; mutation-proven
      (the branch removed; noted then refused: both fail all three). Corpus:
      `no-optimisers/` built with ffmpeg and `which`'s ffprobe, three
      `env/no-*` cases; 427. Predicted before running, and so: 414
      identical, 13 changed -- the 10 `.png` cases (oxipng is not on the
      harness's PATH: its line now the note) and the three new; no status.
      Spec 3.7, CHANGELOG. Suite 1614 at 100% coverage; matrix 770 (its PATH
      has oxipng: the real path still run); ruff, vulture, basedpyright
      clean. Reviewed (owner's request): spec 1's
      cross-reference named 3.13 alone, not 3.7's optimisers; 07-tools' GIF
      and optimisers row said nothing of their being optional -- both now
      do. `_produce` tested `optimise is not None` twice: one guard, its two
      outcomes nested (427 identical: no behaviour changed). A wrapper over
      `shutil.which` for the two optional tools weighed and declined: one
      stdlib call, the notes rightly differ, the shared wording already
      `missing`'s.*
- [x] Spec 3.x and the README: each tool, what it serves, what works without. *Done.
      The inventory from the code, not from the boxes: eight programs --
      `env` (it launches ffmpeg-normalize) and `nproc` (the thread count,
      `cores`) beyond the boxes'. Each claim proven: `nproc` absent, one
      thread without a word (`OMP_NUM_THREADS=3` gives 3 with it, 1 without:
      the sandbox's single CPU no evidence alone); `FFMAN_FONTS_DIR` unset, a
      burn done with no `fontsdir` -- `font_metrics` None, "its lines
      estimated". Spec 1: a table, each tool's use and its absence; the
      environment table's `FFMAN_*` rows say what unset does, and
      `OMP_NUM_THREADS` added. README: "What it needs". Only documents
      changed (shown); suite 1614 (the README in the package's source set). Reviewed (owner's request), each
      cell re-proven: the normaliser's row said `ffmpeg-normalize failed` for
      both its tools -- without `env`, `env not found` (shown); the variables'
      row called `OMP_NUM_THREADS` a ceiling -- it is a minimum (3 on one
      CPU), `OMP_THREAD_LIMIT` the maximum (3 and 2 give 2), as GNU's manual
      says; "cgroup quotas" true from coreutils 9.8 alone (its NEWS; 9.4
      here) -- `cores`' docstring, its source, too; the README's metadata
      sentence read as `meta` needing nothing. Docstring-only in the source
      (syntax trees compared); suite 1614.*
- [x] Without `nproc`, Python's count (the owner's decision): `cores` falls
      back to `os.process_cpu_count` -- affinity, or `PYTHON_CPU_COUNT` -- and
      1 only if Python has none, noted (`nproc not found: N threads, as
      Python counts the processors`; `nproc gave no count` when it fails);
      it used one thread, silently (macOS ships no `nproc`). `Runner`
      counts on first use, so a job running no ffmpeg never asks, never
      notes (shown: `meta` on metadata files silent). *Done. Proven: 32 by
      `PYTHON_CPU_COUNT` reaches ffmpeg as `-threads 33` (its flag only past
      16, bash's `ffargs`); `PYTHON_CPU_COUNT` read at startup alone
      (measured), so the tests monkeypatch Python's count. Mutations fail
      their tests -- the CLI eager (its `nproc` note, not a NameError, shown),
      the fallback 1, the note removed. Tests needing `nproc` absent from
      their own subject -- the optimisers' and the corpus's `no-optimisers`
      PATH -- now hold it: 427 identical. Spec 1's two tables, README,
      CHANGELOG. Suite 1617 at 100% coverage; matrix 770; ruff, vulture,
      basedpyright clean. Found, older and apart: four signal tests leak a
      file under `-W error` (the same at HEAD). Reviewed (owner's request): its reason,
      as I gave it, was false -- "it used one thread, silently". Below 16
      ffman passes no thread flag (`ffmpeg_args`) and ffmpeg threads itself;
      the count sets FFV1's slices past four and the threads past 16 alone
      (shown: 1 and 4 processors give identical commands; 07-tools' Threads
      row had said so all along). The old fallback's cost: FFV1 at its four
      slices on a larger machine, ffmpeg's cap past 16. The note said
      "4 threads" for a processor count: now "4 processors, as Python
      counts them"; the spec's and README's rows, the CHANGELOG and `cores`'
      docstring say what the count serves; 07-tools gains the fallback.
      427 identical; suite 1617; matrix 770.*
- [x] The leaked pipe (the owner's: fix it): the signal test opened its job
      with `stdout=PIPE` and never closed it -- a test's leak, not ffman's.
      *Done: `subprocess.Popen` as a context manager (it closes and waits);
      its assertions identical, line for line. Proven both ways under `-W
      error`: four pass, and fail with the fix alone reverted. Why it hid:
      no warning failed the suite -- now `filterwarnings = ["error"]`, after
      the whole suite (1617) and the matrix (770) passed under `-W error`;
      the configuration alone, without `-W`, fails the leak and passes the
      fix (in the gate's environment: the ad-hoc one lacks pytest-timeout,
      whose `timeout` option it warns of). AGENTS: a warning fails the
      suite.*

*6.7.3 The font*

- [x] The two Plex files bundled, unmodified (the OFL's Reserved Font Name:
      no subsetting), with `OFL.txt`, as `src/ffman/fonts/`; found by
      `FFMAN_FONTS_DIR` if set, else the package's own, as a real directory
      (`importlib.resources.as_file`: libass takes a path) -- pip and Nix alike;
      the wrapper stops setting it. Neither readable: libass's fontconfig
      default and the width estimate (today's), noted once. *Done. The source proven, not
      assumed: nixpkgs pins IBM Plex 1.1.0 by `fetchzip` from IBM's release;
      nix, fetching and unpacking it itself, reproduces the pinned hash
      (`sha256-mK+8...`; my own unpacking had not -- zipfile drops the
      permission bits a tree hash counts), and its Regular, Bold and licence
      are byte-identical to the files bundled. One resolver,
      `jobs/convert/fonts.py`, for the two readers -- the burn checked the
      variable's path, the camcorder did not (now refused alike: a latent
      bug). The package's own folder as is where its path is safe (a Nix
      store path is; a venv under a spaced folder is not, measured), else
      copied into the work directory -- one mechanism for a spaced path and
      a zip, so not `as_file`, whose temporary lifetime a job outlives. A
      folder lacking the font noted once a job (weakly keyed by the runner).
      Nix: `FFMAN_FONTS_DIR` gone from `ffmanEnv` -- wrapper, tests, shell
      alike; evaluated, the derivation no longer holds `ibm-plex`. The wheel
      hatchling builds carries the three files, identical. `test_metrics`'
      shipped-font test now runs anywhere (it skipped unless the variable
      was set); the corpus copies ffman's own (its records now the same on
      every machine). Mutation-proven (four), the camcorder's among them.
      Gates without the variable, as Nix now: 427 identical; suite 1624 at
      100% coverage; matrix 770 (real burns: the rendering unchanged); ruff,
      vulture, basedpyright clean. Spec, README, 07-tools, CHANGELOG.*
- [x] Proven: the bundled files byte-identical to nixpkgs' `ibm-plex` ones
      (`cmp`); the burn and camcorder records differing only in the fonts
      directory's path (the outcome report); a burn from a pip-installed wheel. *Done. (1) The committed files
      `cmp`-equal nix's own fetched release; to the installed file, not the
      source alone: `installFonts` is `install -m644` (read), and each font
      exists once in the tree -- no collision chooses another. (2) Bundled
      against the old Nix path, the burn's and the camcorder's commands and
      notes identical but for that path (and the work directory's random
      name); the commands only point at the scripts, so the scripts
      themselves -- the burn's lines broken by the font's metrics -- kept
      and compared: identical. (3) A wheel built from HEAD, pip-installed in
      a clean venv: a real burn, its fonts in its own `site-packages`; from
      a venv under "My Venv", `WORKDIR/fonts` -- the copy route; both
      decoded frames pixel-identical to a burn with the old Nix fonts
      (lossless, `framemd5`). Controls: without Plex, and without captions,
      the frames differ -- the comparison sees the font. Pinned: a test
      that the bundled files are the release's three, by SHA-256 (one byte
      appended, a stray file added: it fails). No source changed; suite
      1625.
- [x] 6.7.3 reviewed whole (owner's request). *Found: the camcorder's stamp
      is drawn in IBM Plex Mono (its script's Style line), which ffman never
      carried -- nor did Nix (`families = [ "sans" ]`): it is fontconfig's,
      the host's (here none: DejaVu Sans Bold substituted, `fc-match`). So
      the CHANGELOG's and README's "the camcorder's stamp render alike" was
      false: both, and spec 3's row, now say so. The "not in" note fired for
      a job not drawing with Plex Sans (shown: `--font "DejaVu Sans"`, an
      empty folder) -- `fonts_dir` now takes the job's family, noting only
      ffman's own missing; the burn passes `--font`'s, the camcorder
      `STAMP_FONT` (a test holds it to the script's Style). `Frame`'s
      `camcorder`/`fonts`, a state now impossible (a stamp without fonts),
      one `Stamp(script, fonts)`. Stale: `camcorder`'s docstring, `frame`'s
      comment, AGENTS' corpus lines. Shown: another family renders alike
      with ffman's folder or none. Mutation-proven (two). 427 identical;
      suite 1629 at 100% coverage; matrix 770.*
- [x] Owner's decision: carry IBM Plex Mono Bold too, so the camcorder's
      stamp renders alike everywhere, as the captions now do? (One more
      file of the same 1.1.0 release, the `mono` family, OFL.) *Done: carried.
      Its need measured first: the stamp's one style is Plex Mono, bold, no
      inline override (8 dialogue lines) -- the Bold alone. Proven as the
      Sans: nix, fetching IBM's `mono` release itself, reproduces the pinned
      hash (`sha256-OwUm...`); the Bold exists once in the tree; its licence
      is the Sans' byte for byte -- one `OFL.txt`. `fonts.py`: one table of
      what ffman carries, each family's files and what a job gets without
      them; the note per family, once a job; the copy route copies all.
      `STAMP_FILE` beside `STAMP_FONT`. Shown: the camcorder's frames with
      the bundled Bold equal those with nix's own, and differ from the old
      substitute's (an empty folder). The corpus copies every carried font
      (427 identical); the copy test holds the Bold (mutation: three caught).
      Wheel: the four files, identical. Suite 1629 at 100% coverage; matrix
      770. The documents' caveats reversed: the stamp renders alike. Reviewed (owner's request): the note
      said "the system's default font" -- measured against a private
      fontconfig holding Plex Mono, libass takes the system's own when it has
      it (`fc-match` finds it; the frames leave the substitute's), though it
      renders a little apart from ffman's copy, the same file (fontconfig's
      settings, not isolated): now "the system's font in its place", both
      families; spec 3 says so. The camcorder's template takes `STAMP_FONT`
      (`{font}`, it was formatted already): the family written once. The
      told set made only for a family ffman carries. 427 identical; suite
      1629; matrix 770.*

*6.7.4 The repository*

- [x] Extracted with its history and its documents', on a fresh clone --
      nixos-config's own history never rewritten (the owner's): `git
      filter-repo` keeping `tools/ffman/` (to the root), the five
      `ffman-mappings.{md,py}`, `-phase6`, `-python`, `-spec` (to `docs/`),
      the bash origin `tools/ffman.sh` and `tools/ffman-tests/` (to `bash/`:
      history alone, removed at HEAD), and the skills `ffmetadata`,
      `vorbiscomment`, `cue` (as they are: the meta tests' oracles); 07-tools'
      ffman section copied into `docs/decisions.md` (a part of a shared file:
      its history stays in nixos-config). *Done. The plan's paths were short
      three ways, each measured: `ffman-mappings.py` beside its `.md`; the
      bash origin, gone at HEAD, its history ffman's; the three skills, which
      tests read at `parents[3]`. No file ever moved into these paths from
      outside them (every rename internal). nixos-config proven untouched --
      its HEAD, 956 commits, clean tree, history and refs hashed before and
      after: identical (the clone read it under a throwaway
      `GIT_CONFIG_GLOBAL`, git's real configuration neither read nor
      written). The history complete: 215 commits for 215 that touched the
      paths; the 240 files at HEAD each its original's blob; per-file
      history equal through renames. Made whole in one commit: every link
      and citation re-pointed (`decisions.md`, `docs/`); the harness's
      export, `src` and `pyproject.toml` -- one path built of segments,
      `"tools" / "ffman" / "src"`, missed by a search for the joined string,
      caught by its own run; `test_mpv_conf` left for nixos-config (6.7.8).
      Found: in nixos-config and in Nix's check, four tests had never run --
      the three oracles and `mpv.conf`'s, each skipped "not in this tree";
      the oracles' skips removed, a missing skill now fails (shown). ruff's
      scope kept (`.agents`, `docs`, `bash` excluded: 182 files, 183 less the
      moved test). 427 identical (the harness against this history); suite
      1632, no skip; matrix 770. From here ffman's work is in this
      repository; nixos-config's `tools/ffman` and its plan copies frozen
      until 6.7.8 removes them. Reviewed (owner's request), each of
      my own checks' blind spots searched: the docs I had called historical
      held four broken links (the living plan's one); the CHANGELOG two dead
      references; 23 citations in the short form `plans/ffman-...` (source,
      tests, spec, decisions) that no search for `.agents/` or `../../`
      could find -- all re-pointed, the code's changes comment-only (14
      files, syntax trees identical). README's and AGENTS' Nix instructions
      named nixos-config's flake as this one's: now qualified, 6.7.7 to
      rewrite them. My dprint run reformatted `ffman-python.md` whole and
      corrupted it (`>=` read as a quote, `> =`): restored, its one link
      alone; 6.7.9's `dprint.json` excludes it. The tag carried,
      `ffman-bash-final`, is ffman's own (its bash's last; no `src/`).
      Suite 1632.*
- [x] The layout (each entry built by the box named):

      ffsuite/
        pyproject.toml          the workspace's root, no project of its own
                                (uv's virtual root): [tool.uv.workspace]
                                members = ["packages/*"], the dev group, the
                                tools' configuration (6.7.5; virtual: below)
        uv.lock                 (6.7.5)
        justfile  cog.toml  dprint.json  .pre-commit-config.yaml
                                CONTRIBUTING.md (6.7.9)
        flake.nix  flake.lock  nix/      (6.7.7)
        LICENSE-MIT  LICENSE-APACHE (6.7.5)
        README.md  AGENTS.md  .gitignore     the repository's (here)
        docs/                   the spec, the plans, decisions.md (here),
                                upgrading.md (6.7.8)
        .agents/skills/         cue, ffmetadata, vorbiscomment: ffmeta's
                                tests' oracles (here)
        packages/ffman/         pyproject.toml, README.md, CHANGELOG.md,
                                LICENSE-MIT, LICENSE-APACHE, src/ffman/ (cli,
                                jobs, plan, graph, effects, media, subs -- the
                                burn pipeline -- fonts/: Plex Sans, Plex Mono
                                Bold, OFL.txt), tests/ (suite/, outcome/,
                                support/, fixtures/, test_architecture.py,
                                test_workspace.py, the rest) (below)
        packages/ffmeta/        pyproject.toml, README.md, LICENSE-MIT,
                                LICENSE-APACHE, src/ffmeta/
                                (+ py.typed), tests/ (the test_meta_* files)
                                (6.7.5, 6.7.6)
        packages/subverter/     pyproject.toml, README.md, LICENSE-MIT,
                                LICENSE-APACHE,
                                src/subverter/
                                (+ py.typed), tests/ (the readers' tests)
                                (6.7.5, 6.7.6)
        .github/                workflows/, dependabot.yml, ISSUE_TEMPLATE/,
                                PULL_REQUEST_TEMPLATE.md (6.7.9)

      *Done: the design, checked; its files are its boxes'. uv's own
      documentation: "Every workspace needs a root, which is also a
      workspace member" -- a root project with accompanying libraries, its
      most common layout. Against the extraction: the tree lacked
      `.gitignore`, `.agents/skills/`, `docs/`'s contents and `bash/`, now
      named. Each entry's owner found by meaning (my literal search missed
      the flake's, whose box names it "Its flake"): two gaps, given to 6.7.5
      -- the packages' README files (each its PyPI page: a `readme` field,
      no box writing it) and the root's sdist, which hatchling fills with
      every tracked file (measured from HEAD: `.agents`, `docs`, `tests`
      too; `packages/` would follow). Reviewed with 6.7.4 whole: two more
      owners missing, found by reading each claim in context -- `uv.lock`,
      which my table gave 6.7.9 on a literal match (it only checks it), and
      the `LICENSE` files `license-files` names (no box wrote them): both
      6.7.5's now.*
- [x] ffman under `packages/`, beside its libraries (the owner's decision, before the first
      push; the repository then named `fftools`, now `ffsuite`: below). *Done: `git mv` of `src`,
      `tests`, `README.md`, `CHANGELOG.md` to `packages/ffman/` (192 renames, their history
      followed), its licence copies held to the root's like the libraries'; its own
      `pyproject.toml` (its project, its sdist and wheel, its pytest rules for its sdist); the
      root a virtual one -- the workspace, the dev group, the tools' configuration -- proven
      first in miniature on uv 0.11.32 and the pin's 0.11.21 (lock, sync, run, build). The
      lock: the dev group to the workspace's manifest, ffman's source `packages/ffman`, no
      version moved; both uv versions accept it. `test_workspace`: the root no project, its
      members exactly the three; each library's shared fields ffman's; every pytest option a
      package sets the root's but where its tests are -- each new rule failed by its mutation.
      The outcome harness reads both layouts (`git cat-file -e`: `ls-tree` given two paths
      lists the folder's contents, measured), its import path tested on each. Nix: ffman's
      root `packages/ffman`; the pytest checks build ffman from its own source and run from a
      writable copy of the workspace (`preCheck`). A new root README, the repository's; ffman's
      README links absolute (its PyPI page); AGENTS, decisions repointed. Proven: suite 1719
      at 100% (1714 and the five new tests, predicted); outcome report against the commit
      before the move, 427 identical; the three wheels' code and data unchanged, their
      METADATA alone differing -- each README's new text, ffman's changelog URL; `nix flake
      check --no-build`, the libraries' derivations differing by their source alone (the
      README); ruff, basedpyright, vulture clean. Reviewed: that record had said the libraries'
      wheels byte-identical and their derivations unchanged -- measured before their READMEs
      were edited, now corrected (both revisions built and evaluated). The outcome harness's
      docstring still sent it to the repository's root (refused there: no `tests`); its import
      path took a root-layout tree kept in a folder named `packages` for a member (a test
      failing on it, and one on a lone tree's neighbour); AGENTS lost the verdicts' names;
      ffman's README, its PyPI page, lacked the libraries' licence section; ruff's first-party
      roots named `tests`' folder, not its import root (no import moved). Suite 1721 (two new
      tests); outcome 427 identical against the commit before the move and against it; sdists
      375, 55, 1245.*
- [x] The repository renamed `veramachine/ffsuite` (the owner's decision, before the first
      push: `fftools` is another's project on PyPI, an unrelated one -- measured -- so the name
      would be read as it). No package of that name: a meta-package re-exporting the three was
      declined -- `pip install ffman` already installs all three, ffmeta's and subverter's
      top-level names collide (`Error`, `read`), its version would break with any of theirs
      (Azure's `azure` meta-package deprecated for that), and a placeholder is name squatting
      (PEP 541). The name checked free by PyPI's own similarity rule (warehouse's
      `ultranormalize_name`: separators dropped, `l`/`i` read `1`, `o` `0`) over its 906,870
      projects -- `ffkit` and `fftoolkit` taken that way; `ffman`, `ffmeta`, `subverter` free.
      *Done: every reference (URLs, README titles, the flake's `nix run` line, the plan's
      boxes, `origin`) -- ffmpeg's own `fftools/` paths kept.*
- [x] Published fresh (the owner's decision, the bash past): `veramachine/ffsuite` begins at
      one commit, its tree the one built above (measured: every file and mode equal). The
      history before -- ffman's own in nixos-config, kept there whole, never rewritten, its tag
      `ffman-bash-final` on `tools/ffman.sh` -- and the extraction's commits from 6.7.4 to the
      push stay unpublished. The docs' commit hashes are nixos-config's (71, each found there)
      but one, 6.7.6's base `7b8c433`, that history's record alone (the other hex in the docs:
      digests and numbers, each read). *Done: what pointed into the old history points to
      nixos-config's -- the spec's source and decisions' (its `tools/ffman.sh` at its tag); the
      layout's `bash/` gone, ruff's exclusion of it dropped (the files it checks the same, 211);
      ffman's README, its PyPI page, tells the bash ffman retired, no history named.*

*6.7.5 The packages and their pyproject.toml*

- [x] Root (`ffman`): `name`, `version`, `description`, `readme`, `license = "(MIT OR Apache-2.0) AND OFL-1.1"` (the owner's: MIT or Apache-2.0,
      the user's choice, in place of AGPL-3.0; the wheel carries the fonts: PEP
      639's expression is what is distributed. The parentheses are the meaning:
      SPDX applies AND before OR (3.0.1, Annex B), so without them it would
      read "MIT, or Apache-2.0 and OFL" -- and the PyPA's parser takes both
      spellings, measured), `license-files = ["LICENSE-MIT", "LICENSE-APACHE",
      "src/ffman/fonts/OFL.txt"]`, `requires-python = ">=3.13"`, `authors`,
      `keywords`, `classifiers` (csan's set, 3.13 and 3.14, `Typing :: Typed` -- but no
      `License ::` one: with a license expression PyPI MUST reject the upload,
      PEP 639; hatchling builds it regardless, measured),
      `[project.urls]`, `[project.scripts] ffman = "ffman.cli:main"`,
      `dependencies = ["ffmeta>=0.1,<0.2", "subverter>=0.1,<0.2"]` (each library's next breaking version kept out;
      first versions: `ffmeta`, `subverter` 0.1.0, `ffman` 2.0.0),
      `[tool.uv.sources]` the two `{ workspace = true }`, `[tool.uv.workspace]
      members = ["packages/*"]`, `[dependency-groups] dev` (pytest, pytest-cov,
      pytest-timeout, pytest-xdist, hypothesis, syrupy, numpy, ruff,
      basedpyright, ty, vulture -- floors at nixpkgs' versions then),
      `[build-system]` hatchling (proven in nixpkgs), the tool tables (ruff,
      basedpyright, pytest, coverage, vulture) shared. `LICENSE-MIT` and
      `LICENSE-APACHE` written -- MIT's text as SPDX lists it, its copyright
      line the owner's (the name asked here), and Apache-2.0's from
      apache.org, each hash recorded -- at the root and in each package, a
      copy: `license-files` is each `pyproject.toml`'s own
      folder's, and `"../LICENSE"` -- which hatchling takes -- writes an sdist
      member `pkg-0.1/../LICENSE`, which tar refuses as escaping the archive,
      and no wheel builds from it (all measured).
      Each wheel's `dist-info/licenses/` checked -- `LICENSE-MIT`,
      `LICENSE-APACHE`, and ffman's `OFL.txt` (hatchling carries all three
      and names each, measured): hatchling 1.32.4 builds without a listed file, silently
      (measured: exit 0, no warning, no file, the `License-File` line
      dropped). `uv.lock` generated and committed
      (no box made it; 6.7.9's CI only checks it): `uv lock --check`
      passing, `uv sync --locked` installing, pytest run from it. *Done. csan's conventions from
      its own `pyproject.toml` (fetched): authors and maintainers "VERA LVX",
      its URL keys, its classifier shape -- but `Operating System :: POSIX`,
      not its "OS Independent": ffman calls `os.killpg`, `SIGHUP`,
      `process_group` (`media/run.py`). 14 classifiers, each in PyPI's own
      list (`trove-classifiers`). `Typing :: Typed` was untrue -- no
      `py.typed`: added (basedpyright `all`, zero errors), in the wheel.
      `hatchling>=1.26.2`: its changelog's first release with
      `license-files` in PEP 639's final form; nixpkgs' 1.29.0 within.
      `LICENSE-MIT`: SPDX's text, "Copyright (c) 2026 veralvx" (the owner's
      handle; ffman's history begins 2026-09-27), sha256 bb99fc5b...7872.
      `LICENSE-APACHE`: the ASF's, from its site's repository
      (`apache/www-site`; apache.org itself unreachable here), equal to
      SPDX's but for whitespace, sha256 cfc7749b...3d30. The wheel: all three
      licence files, each a `License-File`, the expression, no `License ::`;
      `twine check --strict` passes. It writes Metadata 2.5 -- PyPI
      accepts it (Warehouse's `SUPPORTED_METADATA_VERSIONS` on main holds
      "2.5"). The dev group is pinned to the nixpkgs pin's versions,
      exactly, not floored: floored, the lock took newer ones, and on the
      same code ruff 0.16 (its `ALL` grown: CPY001, PLR0917, 216) and
      basedpyright with numpy 2.5's stubs (24) disagreed with Nix's -- one
      verdict only when the versions are one. `uv lock` (uv 0.11.21, nixpkgs'),
      `uv lock --check` and `uv sync --locked`: exit 0; from that
      environment ruff, format, vulture, basedpyright clean, the suite
      1632 at 100%. Reviewed: of the lock's nine transitive packages, three
      differ from nixpkgs' -- `packaging`, `pygments` (no verdict) and
      `coverage` 7.16.2 against 7.14.1, the 100% gate's measurer: pinned
      too (the gate passes under it); numpy 2.4.4 has CPython 3.14 wheels
      (21, as for 3.13), so the CI matrix's 3.14 gets binaries.
      `dependencies` and `[tool.uv.sources]` for `ffmeta` and
      `subverter` move to the box that makes them (no workspace source
      resolves before its package exists), which re-locks.*
- [x] `ffmeta`, `subverter`: each its own `pyproject.toml` -- name, version,
      readme, `license = "MIT OR Apache-2.0"` (no fonts), `requires-python`, classifiers, no
      dependencies, hatchling, `py.typed`. *Done, from one template: `0.1.0.dev0`, the root's authors and
      hatchling floor, `MIT OR Apache-2.0` with `LICENSE-MIT` and
      `LICENSE-APACHE` copies (byte-equal to the root's), `Operating System
      :: OS Independent` -- neither imports anything platform-bound
      (measured), unlike ffman -- 12 classifiers each in PyPI's list; the
      names still free (404). Each package's frame: `src/<name>/__init__.py`
      (its purpose) and `py.typed` -- its code is the move's -- and a short
      README, true but brief: hatchling reads it to build, and the next box
      writes it whole. The branch renamed `main` (csan's, and every URL's;
      no commit changed). Proven: the lock's members ffman, ffmeta,
      subverter; `uv lock --check`, `uv sync --locked` (and
      `--all-packages`: all three import from their `src`); `uv build
      --package` each -- its wheel's two licences, `py.typed`, the
      expression, no `License ::`, no `Requires-Dist`; its sdist its own
      files; `twine check --strict` four times PASSED. Each sdist holds the
      repository's `.gitignore`: hatchling looks for it up to `.git` and
      force-includes it (its `config.py`, `sdist.py`, read) -- by design.
      Reviewed: "cannot drift" was false as written -- the template a
      one-off script -- now true: `tests/test_workspace.py` holds each
      package's licence files byte-equal to the root's, its authors,
      maintainers, `requires-python`, `[build-system]` and Python
      classifiers equal to the root's, and the root's expression exactly
      `(` + the packages' + `) AND OFL-1.1`; four kinds of drift, each
      failing it. Measured for the move: `ffmeta>=0.1,<0.2` resolves with
      the members at `0.1.0.dev0` (uv takes a workspace member as its
      source). The gate copies what git tracks (and untracked, not
      ignored): suite 1638. Reviewed again: a comment misplaced ("the
      standard library alone" above the classifiers: now beside
      `dependencies = []`, and the classifiers' says why OS Independent); the
      test parsed each file twice (now once) and never checked the box's "no
      dependencies" (now does: a dependency added fails it; the floor's
      mutation re-proven on the rewritten test).*
- [x] Each package's `README.md` written: its PyPI page (the `readme`
      field names it; nothing else writes it). The root's sdist scoped
      (`[tool.hatch.build.targets.sdist]`): ffman's own -- `src`, its
      `tests`, the README, CHANGELOG, LICENSE -- never `packages/` (hatchling
      takes every tracked file otherwise: measured). *Done. The READMEs:
      what each package is, its formats in a table (each claim checked
      against the code -- ffmeta keeps `[STREAM]` sections, its model a
      cue sheet's disc too; the readers' six formats their `FORMATS`),
      installing, the licence; every link absolute (a PyPI page has no
      repository beside it), each file it names present. No usage example
      yet: the public names are the move's `__all__` -- that box writes the
      example and a test that runs it. The sdist: unscoped it held
      `packages/` (12 files), `docs/`, `.agents/`, `uv.lock`. Scoped to
      `src`, `tests`, `CHANGELOG.md` (hatchling adds the README, licences,
      `pyproject.toml`), it was proven by its own tests, unpacked: 9 failed
      -- `test_workspace` (it tests the repository: excluded) and the three
      oracle tests (they read `SKILL.md`: those three files included, while
      the tests are ffman's) -- then 1632 passed, none failed. `twine check
      --strict` on all six artefacts; the repository's suite 1638.
      Reviewed: the READMEs' strongest claims proven, not read. "No file
      opened": `meta/` holds no `open`, `Path`, `os` or file read or write.
      "Never dropped in silence": an ffmetadata of tags, a stream and a
      chapter -- to a cue sheet, `convert` notes all five losses (its
      tags, the stream's, the chapter's end); to Vorbis comments, `convert`
      none but `write` two (the stream's tags, the chapter's end): what a
      format's fields cannot take is noted converting, what its structure
      cannot, writing. Nothing changed.*
- [x] `meta/` to `ffmeta`, `subs/readers/` and the cue model
      (`transcript.py`, `markup.untagged`) to `subverter`; each its own error
      (`ffmeta.Error`, `subverter.Error`) in place of `ffman.errors`, and its
      own of `values`' helpers; `ffman` catches and words them as today.
      Imports rewritten; the public names declared (`__all__`). Each package's
      README gains its usage, from those names, and a test that runs it. *Done.
      Moved by `git mv` (17 renames: history follows). The dependencies
      measured first: the moving code needed ffman's `refuse`, `refuse_at`,
      `shown`, `round_half_up`, and `markup.untagged` -- which moved too,
      ffman's `clean` importing it back. Each package's `_errors` and
      `_values` hold what it uses (subverter's first held two unused copies:
      coverage caught them -- vulture could not, a name used elsewhere --
      removed); `test_copies` holds each copy to ffman's on any input (a
      mutation surviving -- halves rounded down -- until halves were drawn
      on purpose). Imports rewritten by rule (44 files); one form, `from
      ffman.subs import readers`, escaped rule and search, caught by its own
      import. `REFUSALS` in `ffman.errors`: the CLI catches all three, each
      inner site exactly what its block raises. `__all__` from each module's
      own definitions; the roots re-export the API (`Cue` found missing by
      using it), each `Error` named by its package. A cycle (`files` importing
      its package's root, which re-exports it): the aliased module import,
      ruff's PLR0402 silenced on those lines with the reason -- the one form
      basedpyright and ruff could both accept. `ffman` depends on both;
      coverage, basedpyright, vulture reach them (vulture told
      `__module__` is read). The READMEs' usage as doctests, run from their
      `pycon` fences alone (dprint drops the blank line a whole-file doctest
      needs: shown). ffman's sdist: its own tests from it alone, the
      libraries installed -- the repository's tooling excluded (the outcome
      harness runs each case under `-S`, its commit's sources only, so it
      needs `packages/`). Proven: 427 identical against HEAD; suite 1643
      at 100% for all three; matrix 770; ruff, basedpyright, vulture clean;
      the three wheels each its own code (none moved left in ffman's), its
      dependencies, its licences; `twine check --strict` x6; ffman's sdist
      1613 passed, none failed. Reviewed: my record said each inner
      site catches exactly what its block raises -- the attached file's
      caught `REFUSALS`, subverter's too, which its block cannot raise (its
      six modules reach subverter only by `errors` importing it): now
      `(FfmanError, ffmeta.Error)`, 427 identical, both its paths covered.
      ffman's 58 imports of the libraries all public (each name in its
      module's `__all__`, or a module); no `FfmanError` left outside
      `errors.py`. AGENTS names `REFUSALS`.*
- [x] 6.7.5 reviewed whole (owner's request). *Each box was proven from the
      working tree, whose gate copies untracked files too -- a file left
      uncommitted would pass here and fail a clone. So the section's proof
      is a fresh clone of the commits alone: its own `uv sync --locked` (22
      installed), all three packages imported from it, the suite 1643 at
      100% (5607 statements, all three), ruff, format, basedpyright and
      vulture clean under its own configuration, `uv lock --check` passing,
      all six artefacts built from it and `twine check --strict` PASSED x6.
      subverter's purity, its README's claim, proven as ffmeta's was: no file
      or OS operation in either library. Every inheritance 6.7.5 owed has
      landed; what it passes on is 6.7.6's.*
- [x] The two open choices, left to my recommendation (the owner's): the
      dev group stays pinned exactly to the nixpkgs pin's versions -- one
      verdict for CI and Nix (with floors, ruff 0.16 and numpy 2.5's stubs
      disagreed on the same code, measured); Development Status by each
      package's stage -- ffman, 2.0.0, a working tool's successor held by
      100% coverage, the matrix and the outcome corpus, "5 -
      Production/Stable"; ffmeta and subverter, 0.1.0, their API declared
      just now, 0.x promising no stability, "4 - Beta". *Done: valid in
      PyPI's list, in the wheel's metadata, `twine check --strict` passing.* basedpyright's
      `include` and vulture's `paths` widened to the packages' `src` and
      `tests` (today the root's only: moved code would go unchecked; ruff
      already reaches `packages/`).
- [x] All three at `0.1.0` (the owner's decision: young tools, none yet stable -- ffman's
      2.0.0, a successor's number, dropped). *Done: the three versions; ffman "4 - Beta", as
      its libraries; its dependencies `>=0.1,<0.2` -- the `.dev0` floor had served dev
      versions alone, and named a pre-release, it opened pre-releases to pip and uv (PEP 440;
      shown: `SpecifierSet(">=0.1.0.dev0,<0.2").prereleases` true, the new one unset); the
      lock relocked, nothing else moved; the README's image tag. Proven: the wheels installed
      by uv pip and by pip (`pip check` clean), `ffman --version` 0.1.0; suite 1728 at 100%;
      sdists 1251, 375, 55; outcome 426 identical, one changed -- `cli/version`; the flake's
      packages and image at 0.1.0 (`nix flake check --no-build --all-systems`); both uv
      versions accept the lock.*

*6.7.6 The tests*

- [x] Moved: `test_meta_*` to `packages/ffmeta/tests/`, the readers' to
      `packages/subverter/tests/`; ffman's stay. With them the helpers they use
      (measured: `tests.support.metadata`'s strategies, `media`'s `tool` and
      `metadata_seen`, `flac`'s `with_comments`; conftest's `ffmpeg` and
      `metaflac` fixtures) -- each package's own; ffmpeg and metaflac stay
      `ffmeta`'s test oracles, never its runtime. Three test trees: pytest's
      `--import-mode=importlib`, each helper package its own name (no two
      `tests`). pytest from the root over all three; coverage 100% per
      package. The moved meta tests read their oracles at the root's
      `.agents/skills/` (`parents[3]` from `packages/ffmeta/tests/`).
      Their sdists then: ffman's drops the three `SKILL.md` it holds for
      them; ffmeta's cannot reach `../../.agents` (an upward path breaks an
      sdist, 6.7.4) -- copies held equal by a test, or the oracle tests kept
      out of its sdist: decided there, each sdist's tests run from it. `test_readmes`
      and `test_copies` go with them: each package tests its own README,
      and the copies' test reads all three packages (the repository's). *Done. What moves
      decided by each file's imports, through its helpers, not its name:
      `test_meta_command` is ffman's (its `meta` command); of the other
      eight, three reached ffman only through `tests.support.media`, whose
      four helpers they use need it not -- ffmeta's copies them; `metadata`
      and `flac`, used by nothing that stays, moved. Measured: subverter's
      own tests were `test_fields` alone. 9 test files and 2 helpers by `git
      mv` (11 renames), dropping the `meta_` prefix. Each tree its helper
      package (`ffmeta_support`), `pythonpath` naming it (pytest's docs:
      importlib changes no `sys.path`) and basedpyright's `extraPaths` the
      same roots; no `__init__.py` in a library's tests (another `tests`):
      ruff's INP001 excepted there, with why. The examples, which the
      oracles and the format tests share, into `ffmeta_support.examples`
      (test modules import none of each other under importlib). The oracles:
      `test_skills.py`, left out of ffmeta's sdist -- no copies. Each
      package its README test and its pytest rules (held to the root's by
      `test_workspace`, as the oracles' pins: a pin moved alone, warnings
      loosened, each fails it). `test_copies` stays ffman's: it runs from
      ffman's sdist, the libraries installed. Proven: 1646, the count
      predicted -- none lost or doubled; 100% for each package over the run;
      the matrix 770 under importlib; each sdist its own tests from it alone
      -- ffman 1244, ffmeta 347 (350 less the oracles), subverter 21; no
      source changed. Reviewed: Hypothesis' settings are
      process-global -- in one run from the root the last conftest's
      profile governs all three trees, so each tree's must be one: now held
      by `test_workspace` (a profile randomised, one with fewer examples:
      each fails it, its message the three profiles side by side). No dead
      helper left (`Seen` types `metadata_seen`, still used), no stale name
      cited.*
- [x] Each library's own tests cover it alone, 100%: measured from its own
      tree, ffmeta 99% (`files.py` 67%, its `_errors` guard), subverter 54%
      (the readers 21-65%: ffman's ingest tests ran them). Published alone,
      a library's tests must test it: reader tests for subverter, `files`
      tests for ffmeta -- written, not moved. *Done. Every
      expectation worked by hand from a recorded rule -- decisions.md's
      rows, the readers' docstrings, the spec (3.13's formats, its preset
      refusals), ffman's test_ingest's refusal words -- never from a run:
      what a reader yields before ffman's normalising. Where a test and the
      code first disagreed, the test was wrong, each shown: a message's
      `(.` read as regex (escaped); "past a double" is past its range,
      ~1.8e308, not past 1e303 (`_LONGEST`, read; the test now straddles it).
      `test_readers.py` (subverter: every format, its refusals, the
      boundaries) and `test_files.py` (ffmeta: formats by name and first
      line, the presets, `refuse_at`'s guard). Mutation-proven: four across
      them, each failing (one first missed by its anchor -- retried).
      From its own tests: subverter 54% to 100% (53), ffmeta 99% to 100%
      (376); from its own sdist alone, 100% each (subverter 53, ffmeta 373:
      the oracles not needed for it). Suite 1705 -- my prediction's 1704
      had a stale base (the profiles' guard, added since): exact. No
      source changed. Reviewed: a test imported `Timing` from
      `subverter.transcript` -- the type of `read`'s words, yet not at the
      root, as `Cue` had not been. One rule decides now: a root exports every
      type its API takes or returns, directly or as a field. Derived from the
      annotations, it found ffmeta's `Tag`, `Chapter`, `Disc`, `File`,
      `Index`, `Track` (what `Metadata` is made of) and subverter's `Timing`
      missing: exported, and a `test_api.py` in each package holds the rule
      (`Timing` unexported again: fails, naming it). Its first form too
      complex and leaking `typing`'s `Any`: split in two, cast to shape.
      427 identical; suite 1707.*
- [x] `test_architecture.py`: `ffmeta` and `subverter` import nothing of
      `ffman` nor of each other (uv cannot ensure it: its docs say so). *Done -- not in
      `test_architecture`, which is ffman's and ships in its sdist without
      `packages/`: the boundary is each library's, so each carries
      `tests/test_imports.py`, run from its own sdist too. One rule, stronger
      than the box's: itself and the standard library alone
      (`sys.stdlib_module_names`) -- ffman, the other library and any third
      party alike, as `dependencies = []` declares; a relative or a dynamic
      import (`importlib`, `__import__`) refused, this reader not seeing where
      it leads. Eight forbidden imports, each inserted in turn, each failing
      it by file, line and module (one inside a function). The other way is
      ffman's, so in `test_architecture`: every name ffman takes from a
      library -- `from`, `import`, an attribute of a bound module -- public
      (no private part; in its module's `__all__`, or a public submodule): 62
      found. Mutations: a private module, either form; a private name; a name
      a module only imports (`Format` from `files`); `ffmeta._errors` as an
      attribute -- each failing it; a public submodule passing (control). One
      mutation of mine first broke ffman's import, not the rule: placed where
      the module is bound, caught. The three test files both libraries carry
      held identical but for the package's name (`test_workspace`; one copy
      edited alone fails it), `test_api`'s docstring made generic for it. The
      environment was reset before this box: rebuilt -- the lock's Python
      tools by `uv sync --locked`, FLAC 1.5.0 and FFmpeg 8.1.2 from their
      sources (cache.nixos.org refused by the session's network policy),
      oxipng from crates.io, jpegoptim 1.5.6 from its repository (Ubuntu's
      1.4.7 lacks `--auto-mode`), the presets folder by the local Nix from
      nixos-config's file, as `pkgs/default.nix` builds it; ffmpeg's version
      string from `RELEASE`, not `git describe` (`n8.1.2` would fail the pin's
      check). Before committing, my own review: two blind spots closed --
      `builtins.__import__` (an attribute) and a private part deep in a chain
      (`ffmeta.model._x`), each caught -- and a false positive found by its
      control: a dunder (`ffmeta.__name__`) is every module's protocol, now
      public. Proven: suite 1713 at 100%, the count predicted; 427 identical;
      matrix 770; each sdist its own tests -- ffman 1245, ffmeta 375,
      subverter 55, each library 100%; ruff, basedpyright, vulture, the lock
      clean; no source changed. Reviewed: the reader followed `import`'s
      names alone, and deeper only private parts -- `from ffmeta import
      vorbis`, then `vorbis._NAME`, `vorbis.re`; `ffmeta.cue.re`; a class's
      `Metadata._x`: each passed it (proven). Now every import binds its local
      name to a dotted path, an attribute chain extends it, and each module
      along it is read: in its `__all__`, or a public submodule; past the
      modules, no private part (scope not read: a collision fails, never
      passes). 66 found; thirteen mutations fail it (a star import too), nine
      controls pass. The copies' guard printed the packages' names, not the
      drift: now the lines that differ. `test_imports` says what it refuses:
      `importlib` whole, against the running Python's list (3.13, the floor;
      a later one may add names).*
- [x] 6.7.6 reviewed whole (owner's request). *Found, each proven before
      its fix and after: ffman's and ffmeta's trees carry the same oracle
      tools (four fixtures; `tool`, `Seen`, `metadata_seen`, `CD_SECONDS`),
      held by the pin's string alone -- now every definition both carry is
      held identical, comments aside (a pin, `cd_flac`, `metadata_seen` or
      an annotated `CD_SECONDS` changed in one tree fails it; it replaces the
      pin test). `test_api` skipped an exported type alias -- one naming an
      unexported class passed; now fails. The dispatcher's refusals matched
      unanchored -- a tail added passed; now whole. Three reader tests,
      appended for coverage, moved into their formats' sections. One ruff
      list for the three trees (`**/tests/**`: ruff applies every pattern a
      file matches, measured), `INP001` alone the libraries'. Stale: the meta
      tests' comments on their moved example copies, the skills README's
      `test_meta_*`. Proven from a fresh clone of the commits: its own `uv
      sync --locked`; suite 1714 at 100%, the count predicted; ruff,
      basedpyright, vulture, the lock clean; each sdist from it -- ffman
      1245, ffmeta 375 and subverter 55, each library 100% line and branch;
      the outcome report against the section's base (7b8c433) 427 identical:
      the section changed no behaviour.*

*6.7.7 Its flake*

- [x] `packages`: `ffmeta`, `subverter`, `ffman` (wrapped, its runtime:
      ffmpeg-full, flac, oxipng, jpegoptim, gifsicle, and ffmpeg-normalize on
      ffmpeg-full, as today; its presets directory as `FFMAN_NORMALIZE_HOME`).
      The presets in both, apart (the owner's decision): ffman's repository its
      own file (`nix/ffmpeg-normalize-presets.nix`: its youtube-aac, today's
      values, and the native twin derived), from which its flake builds the
      default `FFMAN_NORMALIZE_HOME` -- the variable still an override;
      nixos-config's home its own file, as today. No check that the two are
      equal: each its owner's. No
      `pythonRecompileBytecodeHook`: an opt-in repair for bytecode that is not
      reproducible (nixpkgs #81441; removed as a default in 2020), which would
      delete the installer's bytecode and write `-OO`'s alone -- ffman's is
      reproducible already (measured: two installs by `installer` on 3.13, 178
      `.pyc`, 89 plain and 89 `opt-1`, byte-identical), `default = ffman`; `apps.default`, so `nix run
      github:veramachine/ffsuite -- convert ...` works. *Done: `flake.nix`,
      `flake.lock` (nixpkgs at nixos-config's node, `nixos-26.05` 4c78701:
      Python 3.13.15, ffmpeg-full 8.1.2, FLAC 1.5.0, hatchling 1.29.0),
      `nix/packages.nix`, `nix/ffmpeg-normalize-presets.nix`; nixos-config's
      two systems. Each package from its own `pyproject.toml` (name,
      version, description, licences from its SPDX expression, homepage),
      its tests run apart; `PATH` set to `runtime`, the presets
      `--set-default` (nixpkgs' `make-wrapper.sh`, run: unset, the package's;
      set, the user's). Found: ffman's `ffmeta>=0.1,<0.2` excluded the
      libraries' own `0.1.0.dev0` (PEP 440) -- pip, uv pip and nixpkgs'
      runtime check each refused the wheels; now `>=0.1.0.dev0,<0.2`, all
      three accept (uv's lock unchanged: a workspace source keeps no
      specifier). Beyond the box: `overlays.default`, ffman on a consumer's
      own nixpkgs -- nixos-config's ffmpeg-full carries FDK, the flake's
      cannot (evaluated: the overlaid build's ffmpeg-full and normalize on
      `PATH`, stock's absent). Proven where nothing builds (cache.nixos.org
      refused): nixpkgs fetched at the rev by git, its NAR hash the lock's;
      `nix flake check --no-build --all-systems` passes; each wheel from the
      flake's sources identical to the repository's (84, 19, 17 files); the
      presets' JSON byte-identical to those ffman ran with; nixfmt 1.5.0
      (the pin's) clean; suite 1714 at 100%; outcome 427 identical. The
      owner's to run: `nix build`, `nix run . -- --version`. Reviewed: each
      package now refuses an interpreter below its `requires-python` at
      evaluation (`disabled`, the floor read from the file: 3.12 refused,
      each by name; 3.13 and 3.14 evaluate; a range not a bare floor fails,
      saying so) -- the overlay builds on a consumer's Python, which nothing
      checked; the derivations unchanged (`disabled` is the builder's own).
      Verified, not assumed: nixpkgs' ffmpeg-full is built
      `--disable-libfdk-aac` (the native twin's reason), its `ffmpeg` and
      `ffprobe` in the `bin` output `PATH` takes; `.gitignore` holds
      `result`.*
- [x] `checks`: each package's tests, the matrix, lint, types, vulture, the
      installed check (its `metaflac` job; a job without the optimisers; a job
      with `FFMAN_NORMALIZE_HOME` set, the user's folder used -- 6.7.7's
      `--set-default`, untested until here), nixfmt on the Nix files (a
      `formatter`, as nixos-config's), each
      on Python 3.13 and 3.14. The source fileset holds `.agents/skills` (the
      meta tests' oracles: without them they fail now, no longer skip),
      `packages/` and the licence files (`test_workspace` reads them); the
      checks run pytest from the root (its `testpaths`, `pythonpath`). README's
      and AGENTS' Nix instructions -- nixos-config's flake's until now
      (`nix develop .#ffman`, the checks' names) -- rewritten for this flake
      (AGENTS' runtime rule already, 6.7.7's first box). `devShells.default`: uv, Python, ruff,
      basedpyright, just, dprint, cocogitto, pre-commit.
      *Done: `nix/checks.nix` -- on 3.13 and 3.14 each: `tests` (pytest
      from the root over the installed packages, `pytestCheckHook`, 100%),
      `matrix`, `installed` (`nix/installed.sh`), `types`, `vulture`; `lint`
      once (ruff, nixfmt, shellcheck: no interpreter); `nix/shell.nix` (uv on
      nixpkgs' Python, its downloads off -- shown: an absent Python refused,
      not fetched -- the box's tools, nixfmt, shellcheck, the runtime and
      presets); `formatter` nixfmt-tree (below); AGENTS' checks, its layout's `nix/`,
      decisions' header rewritten. The installed check gained its two jobs:
      `FFMAN_NORMALIZE_HOME` set, the user's (empty) folder refused by name;
      a wrapper without the optimisers (`wrapperArgs`, one definition), each
      output written and noted. Found: basedpyright resolved none of the
      workspace in a clean environment -- 6.7.6's `extraPaths` hid `src`,
      the venv's editable installs hid it here -- now the three sources in
      `extraPaths` (0 errors, 3.13 and 3.14, the repo's venv too). The
      checks' source holds no Nix file: an edit there reruns lint alone
      (shown). Python 3.14 met first here: suite 1714 at 100%. Proven where
      nothing builds: `nix flake check --no-build`, 11 checks a system; each
      check's command run in its own conditions -- the suite against the
      installed wheels from the fileset alone, `env -i`, both Pythons (1714,
      100%); the matrix the same (770 and 770); `installed.sh` itself over
      wrappers by nixpkgs' `make-wrapper.sh` (both pass; the old `--set`
      wrapper, a lean wrapper with optimisers, a missing `$lean`, each
      failing it); lint, types, vulture in the checks' read-only source; the
      lean `PATH` the runtime less the three. `syrupy`, in the dev group, is
      used by no test: not in the checks (the group is 6.7.5's). Reviewed:
      the emulation's own gaps attacked -- nixpkgs' Python builds export
      `PYTHONHASHSEED=0` (its `setup-hook.sh`), which my runs had not: the
      suite and the matrix again with it, both Pythons, all passing; the
      installed ffman importable in pytest's phase by the install hook's
      `PYTHONPATH` export (`pypa-install-hook.sh`, traced); no test needs the
      network, git or `/usr/bin/env`. `installed.sh` piped metaflac into
      `grep -q`: under `pipefail` a match found still fails when the writer
      is cut off (shown: 141) -- now captured, then matched; a wrapper
      without metaflac fails it there. Decisions' header: `lint` once.*
- [x] 6.7.7 reviewed whole (owner's request). *Every name the section
      retired swept across the repository: decisions still said
      `ffmanRuntime` twice and that the wrapper sets the presets -- now
      `runtime` in `nix/packages.nix`, the presets a default (and a 6.7.3
      leftover there, a doubled parenthetical on the fonts' hashes, made
      one). `formatter` was `pkgs.nixfmt`, whose directory argument -- `nix
      fmt`'s -- nixfmt itself calls deprecated: now `nixfmt-tree`, treefmt
      over the same nixfmt 1.5.0 (its inputs read). `with pkgs;` and `with
      python3Packages;` made explicit references; `installed.sh`'s failures
      to stderr; three lines past 100 columns shortened (a fourth, a Nix
      string nixfmt keeps, left: rewriting it would change a derivation
      unbuildable here). Proven: of all 32 derivations, the six predicted
      changed (lint, the installed checks) and the rest identical;
      `installed.sh` again on both Pythons, its mutations failing it on
      stderr; `nix flake check --no-build`; nixfmt, shellcheck clean. Built
      by the owner, where cache.nixos.org answers: `nix build` and `nix flake
      check` clean.*
- [x] The presets in the wheel (the owner's decision: the packages go to PyPI too, where a
      Nix-built folder never reaches -- from PyPI, `--preset youtube` refused its normalising,
      `FFMAN_NORMALIZE_HOME is not set`). *Done: `ffman/normalize/` in the package, an
      `XDG_CONFIG_HOME` -- `ffmpeg-normalize/presets/youtube-aac.json` and its native twin,
      written from `nix eval` of the retired `nix/ffmpeg-normalize-presets.nix`, equal value for
      value (and to the presets the suite had run with); its comments now decisions' packaging
      paragraph. ffman's own when the variable is unset or empty, as its fonts -- one helper,
      `jobs/convert/carried.py`, hands both over: the package's folder, or a copy in the work
      directory where a zip holds it (fonts.py's copy loop now that helper's: OFL.txt copied
      with the fonts). The wrapper sets `PATH` alone; the checks and the dev shell set nothing.
      The outcome report names the commit's src `$SRC`. Proven: suite 1725 at 100% (1721, the
      three tests of `test_carried.py`, a naming case), every real normalisation -- the suite's
      and the matrix's M7 -- on the carried presets (the gate sets no variable); six mutations
      each failing a test (no default, a nested folder not copied, a zip read as a path, the
      twin drifting, a preset missing, the fonts' safe path dropped); ffmpeg-normalize 1.42 on
      each preset, no option skipped; the built wheel installed in a clean venv: a 44.1 kHz mono
      source normalised to AAC 48 kHz stereo, no variable set; ffman's sdist 1248 from
      extraction; outcome against HEAD 426 identical, one changed -- `env/no-normalize-home`,
      the refusal now the run; `nix flake check --no-build`, the presets in ffman's Nix source,
      the wrapper's arguments `PATH` alone.*
- [x] Platforms (the owner's decisions): Windows refused clearly, Apple silicon in the flake,
      a container image. *Done. Windows: `ffman/__main__.py`, the command's entry now
      (pyproject's scripts), checks the platform before importing the command line -- whose
      tool handling names SIGHUP, absent there: the import alone failed, a traceback (shown) --
      and refuses, pointing to WSL. The reasons, each from its source: process groups and
      `killpg` POSIX's, SIGHUP, SIGKILL, SIGPIPE Unix's (Python's documentation); `C:\` no
      filter-safe path; no `env`; ffmpeg-normalize's `%APPDATA%` (its `_presets.py`). macOS:
      `aarch64-darwin` in the flake's systems, every runtime tool available there (evaluated);
      Intel Macs left, nixpkgs 26.05 their last. Two tests read `/proc`, absent on macOS -- one
      would fail, the other pass on nothing -- now `ps` (`tests/support/processes.py`, nixpkgs'
      `unixtools.ps` in the checks), a zombie excluded as before (shown on procps); the signal
      test kills its tree when a check fails, which had waited out its 600 s sleeps (found by
      mutation). The image: `nix/image.nix`, `streamLayeredImage` -- ffman, its runtime, tini as
      PID 1, `/tmp` 1777, `HOME=/tmp` -- `packages.<linux>.image` on ffmpeg-full with FDK
      (`withUnfree`, the one package let through `allowUnfreePredicate`): built for the owner,
      never published (ffmpeg's configure: "nonfree and unredistributable"); `overlays.default`'s
      `ffman-image` on a consumer's ffmpeg-full. Proven: suite 1728 at 100% (1725, the two
      Windows tests -- in-process, and a fresh Python with SIGHUP, SIGKILL, SIGPIPE and `killpg`
      removed -- and the README's image tag held to the version), the matrix 770; mutations: the
      command line imported first, no check, a wrong tag -- each failing; the outcome report 427
      identical (the driver runs `python -m ffman`); the wheels installed in a clean venv, the
      script `ffman.__main__:main`; ffman's sdist 1251, ffmeta's 375, subverter's 55;
      `nix flake check --no-build --all-systems`: the three systems' checks, the image's closure
      one ffmpeg-full, `--enable-libfdk-aac --enable-nonfree`, with tini and ffman. Not here:
      building the image, and anything on a Mac -- the owner's, and 6.7.9's macOS jobs.
      Reviewed with the rename and the presets (owner's request): the flake's comment claimed
      the owner's whole tuning for the image (FDK alone is ffman's; the rest a system's, through
      `ffman-image`); the changelog measured the Windows refusal against a traceback, not the
      bash ffman; a test's comment sat on the wrong line; `ps`'s arguments a `Final` tuple; the
      Windows script's name told apart from the message's. Checked and sound: the image's
      closure follows its config (dockerTools' `closureRoots`: the base JSON), its `/tmp` mode
      kept (the layer tarred as built); a passing signal test's cleanup a no-op (`Popen.kill`
      polls first). Suite 1728 again at 100%; `nix flake check --no-build --all-systems`.*

*6.7.8 Into nixos-config*

- [x] `inputs.ffman` (`inputs.nixpkgs.follows = "nixpkgs"`), its package in
      the system's through `overlays.default` (the system's ffmpeg-full, FDK
      kept; 6.7.7); `tools/ffman`, ffman's part of `pkgs/default.nix`, its
      checks and its dev shell removed; nixos-config's own references to it
      (`AGENTS.md`, 07-tools' section, the doc map and review maps under
      `.agents/review/`) pointed at the new repository. Its home presets stay
      its own (`home/ffmpeg-normalize-presets.nix`, unchanged: the owner's
      decision, 6.7.7). `test_mpv_conf` re-homed here -- it holds
      `home/config/mpv.conf` to ffman's style -- reading ffman's package,
      `mpv.conf` in its fileset. ffman's skills -- `cue`, `ffmetadata`,
      `vorbiscomment` -- removed from nixos-config's `.agents/skills/` (they
      live in ffman's: the owner's decision; `map-project`, generic, stays),
      with its index's, `AGENTS.md`'s and the review checklist's references
      to them pointed at ffman's repository. Proven: the flake evaluates, the
      system's closure holds `ffman`. *Done, on nixos-config at its last delivered
      commit (253c5eb; its own history never rewritten). The input named for the
      repository, `ffsuite`, `nixpkgs` followed; locked by hand at the pushed commit (dd0e31a)
      -- its NAR hash computed from the commit's tree, as GitHub's tarball unpacks (shown on
      the ten other inputs: each git tree's NAR hash equal to its lock's), and `nix flake lock
      --offline` leaves the file unchanged. `modules/tools.nix` applies `overlays.default`
      and selects `pkgs.ffman` (the media set). nixos-config's checks re-export ffsuite's on
      the system's Python (`-py` from `python3.pythonVersion`, refused if ffsuite has none):
      `ffman-tests`, `-matrix`, `-installed`, `-types`, `-vulture`, `-lint`. Removed:
      `tools/ffman`, ffman's part of `pkgs/default.nix` (now nixfmt-clean, the one construct
      that was not gone with it), its export and dev shell, the three skills (each file
      byte-identical here) and ffman's five plans (here, and newer); the 07-tools section's
      61 decision areas each found in `decisions.md`. `test_mpv_conf` re-homed as
      `tests/mpv/` with its check (`mpv-conf`): its imports were stale -- `Transcript` and
      `Chunk` are subverter's now (shown: it failed to import against this ffman) -- and its
      skip gone (the file is always there). Found by its blast radius: the evaluation
      harness (`scripts/eval-report.sh`) clones and overrides every input and builds a
      wrapper flake that passes its own `inputs` to the modules -- without ffsuite there,
      every variant would fail; added. The ISO carries every lock node (13 now, 8 direct;
      `ffsuite` among them, evaluated) -- its counts and the installer's and harness's
      comments follow. Run-book 11.49's ffman facts moved to `docs/upgrading.md`
      (blur-edges' fetch and mpv's defaults stay nixos-config's), the item put back in
      section 11 (it sat under 12) and 6.5 counting `ffsuite` among the inputs a channel
      moves. Proven, offline, the inputs fetched by git and admitted by their lock's NAR
      hash: every check, package and dev shell evaluates on both systems; the five hosts'
      toplevels; on each media host and both generic ISOs, `ffman-0.1.0` on the system's own
      `ffmpeg-full` (the same derivation, `--enable-libfdk-aac`); the ISOs with their
      inputs as store paths (their `fetchTree` needs network here, and fails alike at
      253c5eb); harness cells (a tool, the hostname seed, three x86 variants) passing; the
      mpv test against this ffman, from a read-only copy of its check's fileset, and failing
      on a mutated `mpv.conf`; review maps regenerated (their selftest passing; at 253c5eb
      they had been current). `nix flake check` whole exceeds this sandbox's memory, at
      253c5eb too: the owner's to run, with the build.*

*6.7.9 Its tooling* (adapted from csan and imi; each file its source)

- [ ] Workflows: `checks.yml` (csan's: uv, `uv sync --locked`, ruff,
      basedpyright, ty, vulture, pytest; 3.13 and 3.14; `uv lock --check`),
      `nix.yml` (`nix flake check` on Linux and on macOS, Apple silicon: the
      ffmpeg-bound tests, the matrix, the
      outcome report -- they need the pinned ffmpeg 8.1.2, not a runner's
      `apt` one; `checks.yml` runs the rest), `dependency-review.yml` (imi's; paths
      `pyproject.toml`, `uv.lock`, workflows), `dependabot-automerge.yml`
      (imi's; guard `veramachine/ffsuite`), `security.yml` (imi's audit as
      pip-audit on `uv export`: daily, and on the lock),
      `style-check-cocogitto.yml`, `style-check-dprint.yml` (imi's),
      `release.yml` and `publish.yml` (a package's tag, `ffmeta-v1.2.0`:
      `uv build --package`, `uv publish`, Trusted Publishing).
- [ ] `dependabot.yml`: `uv` and `github-actions` (imi's schedule, groups,
      cooldown, labels, `chore` prefix). Issue templates (bug, feature,
      documentation, `config.yml`) and the PR template, imi's, adapted.
- [ ] `CONTRIBUTING.md` imi's, its tools ffman's (uv, just, Nix); `cog.toml`
      imi's with `[packages]` for the three (their own tags); `dprint.json`
      imi's, excluding `docs/ffman-python.md` (a finished record it cannot
      round-trip: a line's `>=` read as a quote, `> =`; measured); the
      `justfile` (csan's groups and aliases, imi's `checks`, `cog`,
      `dprint-check`, `audit`, `release`); `.pre-commit-config.yaml` (ruff,
      dprint, `uv lock --check`, cocogitto's commit-message check).

- [ ] The owner's, outside any file: the GitHub repository and its settings
      (auto-merge allowed, branch protection requiring the checks, a `pypi`
      environment); on PyPI, a pending Trusted Publisher per project
      (`ffman`, `ffmeta`, `subverter`: repository, workflow, environment).

*6.7.10 Proven*

- [ ] In `veramachine/ffsuite`: the suite at 100% per package, the matrix, ruff,
      basedpyright, vulture; the outcome report against nixos-config's last
      ffman commit -- identical but 6.7.2's and 6.7.3's changes, each listed;
      `nix flake check`, on Linux and on a Mac -- macOS claimed (READMEs,
      classifiers) only once its checks pass; each package built (`uv build`)
      and installed in a clean venv, `ffman` run with only ffmpeg on `PATH`;
      the image built and run (the owner's: `docker load`, a conversion).

*6.7.11 Review*

- [ ] The section reviewed whole.

**6.8 Subtitle formats** (each into each other; research and skills before code, as 6.6; G4 each)

Converted into one another, every direction: SubRip (`.srt`), WebVTT (`.vtt`),
ASS (`.ass`), whisper-cli's and WhisperX's JSON (`.json`: `-oj`'s
`transcription[]`, WhisperX's `segments[]`) and whisper-cli's full JSON
(`-ojf`: tokens and their DTW times) -- by chunk or, where the source times
them, by word. Today ffman reads all but ASS (`subs/readers`: chunks and
words, integer ms) and writes SRT (`subs/srt.py`) and its burn's styled ASS.

*6.8.1 Research* (no code; each box's findings the next boxes' sources)

- [x] Measured first, before choosing (the owner's question): ffmpeg 8.1.2
      against ffman's own readers, on SRT, VTT and ASS inputs built to probe
      timing, formatting, line breaks, `&` and `<`, styles, positions,
      speakers. ffmpeg converts all six ways among SRT, VTT, ASS, but: its
      VTT writer leaves `&` and `<` unescaped (invalid WebVTT; read back,
      `A & B < C` lost `< C`) -- unrepairable after, a literal `<` and a tag
      alike; into ASS, start and duration rounded apart (an end +-10 ms);
      down-conversion drops VTT speakers, classes, cue settings and ASS
      positions, colours without a word; it reads LRC, not JSON, CSV, TSV.
      ffman's readers (`subs/readers/`: SRT, VTT, LRC, CSV, TSV, JSON; no
      ASS; writers `ass.py` for burning, `srt.py` for `--add-subs`, no VTT)
      keep milliseconds and text exactly, join lines (made to re-wrap), and
      carry tags as raw text. *Recommended (owner to confirm): ffman's own
      converter on a cue model keeping line breaks, formatting, speakers --
      ffman must parse every input to note what is lost, its VTT writer
      must be its own, the transcripts need its readers; ffmpeg the oracle
      where it is right. Skills first: SRT, WebVTT, ASS.*
- [ ] Found by that measurement, an older defect: a burned VTT shows its
      escapes -- `A &amp; B &lt; C` on screen (shown: the job's own ASS).
      ffman's VTT reader decodes no character reference, nor does anything
      after it. To fix first, its own box: proven by a burned frame's ASS.
- [ ] Each format from its source: SubRip (no standard: as ffmpeg's
      `subrip` reads and writes it -- libass renders ASS alone, SubRip once
      converted), WebVTT (W3C), ASS (v4.00+, Aegisub and libass),
      whisper.cpp's `-oj`/`-ojf` writer (`output_json`), WhisperX's writer --
      every field, its times' precision, what styling, position and word
      timing each holds.
- [ ] What ffmpeg converts between them (its `subrip`, `webvtt`, `ass`
      demuxers, muxers, decoders, encoders), measured both ways -- text,
      markup, positions, overlaps, empty cues, word timing -- against what
      ffman's readers already do; JSON: none in ffmpeg, so ffman's.
- [ ] Words and chunks: how each holds word times (`-ojf`'s tokens, WhisperX's
      `words`, WebVTT's inline `<hh:mm:ss.ttt>`, ASS's `\k`); a chunk's words
      from none (impossible: noted), chunks from words (by segment); what a
      by-word output is in each (a cue a word, or timed within the chunk).
- [ ] The mappings, every direction (a record as `ffman-mappings.md`): what
      crosses, what is lost, ffmpeg's or ffman's -- measured, each row sourced.

*6.8.2 Skills* (validated, packaged, presented -- before any code)

- [ ] Skills for the formats the research finds no skill covers (ASS; WebVTT;
      whisper JSON), as 6.6.2's.

*6.8.3 The converters* (pure, from the skills)

- [ ] The model: `Transcript` kept or grown (ASS's styles and positions?) --
      decided from the research.
- [ ] Readers and writers each format lacks (an ASS reader; WebVTT, plain ASS,
      `-oj`, `-ojf` and WhisperX writers): round trip exact where the
      formats meet, each loss noted; ffmpeg where it measured equal or better.
- [ ] By word or by chunk: an output that holds either takes the choice (its
      flag decided in the spec), refused where the input times no words.
- [ ] Every conversion between the five: property tests, corpus cases.

*6.8.4 The command line* (`ffman-spec.md` first)

- [ ] `convert -i talk.json -o talk.vtt` -- or a command of its own, decided
      in the spec -- its help, its corpus cases.

*6.8.5 Review*

- [ ] The section reviewed whole.

**6.9 The effects** (§4; each box is research and skill, its code boxes added after)

- [ ] `blur`
- [ ] `pixelate`
- [ ] `invert`
- [ ] `chromatic-aberration`
- [ ] `halation`
- [ ] `datamosh`
- [ ] `camcorder`
- [ ] `vhs`
- [ ] `dither`
- [ ] `crt`
- [ ] Resizing in linear light (every resize): researched as the effects are, after those sharing its light handling.

**6.10 Product** (G4 each; the spec first where the command line changes)

- [ ] Grammar: the optional-value rule, `values.py`'s number grammar -- reviewed against the spec, changed through it. From 6.4.1's review: `is_num` accepts any length, and a value past 4300 digits (`--font-size 999...`, 5000 nines) is a traceback -- `Fraction`'s `int` conversion; the command line's numbers want the bounded reading the transcripts got (`fields.exact`), or a length. From 6.4.2's review: a font size past a double (400 digits) is an `OverflowError` -- older too (stage A's floats failed at 310 digits; the exact code at 400).
- [ ] Messages: the spec's text reviewed for the user, not for bash. From 6.2: `FFMAN_FONTS_DIR` is refused by `burn` where ffmpeg's filter syntax splits it, yet passed unchecked to the camcorder's filter, which ffman's graph escapes -- one rule for both. From 6.3.2: a transcript's `\` and braces are burned as `/` and parentheses -- shown as written, braces would take libass's `\{`, `\}`, and a `\` before `N`, `n`, `h` or ffman's own block an invisible separator, its rendering to prove (font, HarfBuzz).
- [ ] `-b` and `--resize-mode` without a size: one answer in every flow -- refused, or applied (F7).
- [ ] D2, the default encode.
- [ ] Stage 4: GIF and `--loop`/`--loop-reverse` from any input; any compatible output.
- [ ] `--attachment`, `--cover`, `--title` (`--metadata FILE`: done in 6.6.4, spec 3.10;
      `--title` beside it: a convert's one tag, or `--metadata` enough).
- [ ] `-v/--verbose`, its meaning defined in the spec first.

**6.11 Completion and manual** (the last work before the close: every command and option settled)

- [ ] Assessed, then done: shell completion (bash, zsh, fish; generated
      from the option table, so it cannot drift), installed by
      `installShellCompletion`; a man page (written, or generated from the same
      table and the spec), installed by `installManPage` -- both nixpkgs'
      `installShellFiles` hooks; or both. What each gives (each shell's needs,
      `man ffman`, `--help` beside it), decided with the owner; each tested in
      the checks.

**6.12 Close**

- [ ] No stage-A scaffolding: `fmt.py` and its tests' imports gone; no comment justifies code by bash alone (a check: each "bash" in `src/` is history beside a stated rule); every effect has its skill, packaged; the spec and `CHANGELOG.md` current; `nix flake check` green. 07-tools.md's rows describe the Python, not bash's tools ("Hostile transcripts": bash's `fuzz.py`, retired in phase 5, as its finder; its jq path rule went with jq, in 6.3). From 6.4.5: `options._margin` reads `N%` through `awk_print` -- a value, not a message: `12.3456789%` is kept as 123457/1000000, and `150%` refused as `1.5`, not as typed. From 6.5's review: the tests hold ~40 trailing-comment wraps (`)  # ...`, the formatter's shape around a long assertion) -- comments above, as `src` has since 6.4.

## 8. Review (at a48dcb7)

The first draft, reviewed end to end. Applied: refusals after work found and
demonstrated (F6, 6.2); the compensation reading done here, not deferred (F2);
a false claim withdrawn (that a gap's shares might not sum to it: they are
cumulative); the outcome report first; the typing and the ingest rewrite
before exact arithmetic; the camcorder's width into its effect; pinned tests'
policy; the skills' home, format and delivery; the target tree; rationals in
four modules, not three; readers counted; the import graph checked against the target (two layer breaks); `\pos` fractions and cropdetect's metadata shown; grammar, messages and provenance
comments planned; each effect box research and skill first.

Section 6.0, reviewed end to end (at e4ef39b; three iterations, to none found).
Fixed: the outcome driver let a failed capture read as ffman's own error (ffman
catches the OSError) -- now kept from ffman and refused by the report (status
125, shown both ways by a test); `Frame` allowed `squared` with a SAR other than
1 and nine places built the squared frame by hand -- `__post_init__` refuses
it, `Frame.resized` builds it; `Rational.parse` took any separator, crashing on
an empty one -- `Literal["/", ":"]`; `Rational.value` and `text`'s separator
were dead (vulture matched them by name to `parsed.value`) -- removed; the
duration and sample-rate grammars untested -- tested; the driver crashed on
bad arguments or no TMPDIR -- refused; two docstrings stale from 6.0.3, one
test comment misplaced, AGENTS.md silent on the report's refusals.

Box 6.1.4, reviewed end to end (at a5a630a; two iterations, to none found).
Fixed: constants written together came apart -- the 6.1.3 and 6.1.4 splitters
joined every definition with blank lines (6.1.2's kept the source's spacing):
eight groups, two here, six in `effects/`, rejoined, a neighbour-spacing check
showing none left (the check's own off-by-one found because it disagreed with
the text); `ingest.py`'s docstring repeated what `readers/` and `normalize.py`
now say -- each fact once, with its code (the times' unit, milliseconds,
said only there, now with the types); a docstring's bash command line,
not in this tree to check, now what the code shows. Shown sound: the import
graph one-way, every public name used outside its module, every `subs` and
`effects` module importable first and alone. Carried to 6.3: tag stripping
twice, `whisper.py`'s order, `read`'s file and path.

Section 6.1, reviewed end to end (3171ca3..4c333be; two iterations, to none
found), aimed at what box-by-box reviews could not see. Fixed: 6.1.2 left
`graph.py` named in three places its sweep did not search (07-tools.md's
Filtergraph text row, `graph/light.py`'s docstring, a test's comment); §3's
"planners are pure" was not so -- two readers read the transcript's file -- and
nothing held it: the architecture test now does (no file, no OS in layers 2-3,
shown failing three ways), the readers its listed exception, 6.3's box to
close; its docstring named two of its rules, now all four; `test_output.py`,
named for a module 6.1.2 renamed, is `test_paths.py`. Shown sound: every path
the current docs cite exists, but other projects' sources; no public name dead
(each of 51 without product use outside its module used within it); one pair
of functions shaped alike (`probe._seconds`, `_count`), two grammars, kept;
every module importable first and alone; the four splits' spacing as written.
Carried: 07-tools.md's "Hostile transcripts" row cites bash's `fuzz.py`, to
6.10 with that row's jq rule.

Section 6.2, reviewed end to end (55137be..d565f3b; three iterations, to none
found), testing what the corpus could not: commands where two checks contend,
run on the old code and the new. Found: the CHANGELOG's "every message is as
it was" held for the corpus only -- `--add-subs` to an output without an
extension now says `output needs an extension`, as the spec's `-o` requires
and every other flow said, where bash said "a . file cannot carry a subtitle
track" (its empty extension read as a container); and a command with several
faults now hears of the options and the probe before the transcript. Both
written down (CHANGELOG, 07-tools.md), tested (fails on the old code in all
three), pinned by two corpus cases.

Section 6.3, reviewed end to end (38dfa03..48e5eea; three iterations, to none
found), adversarially: inputs past what Python's float, int, csv and json hold,
run on the code before 6.3 and after. Found and fixed -- seven crashes, a
traceback each: a CSV/TSV field past `csv`'s 128 KiB (6.3's: gawk had no
limit) now refused by name; six older -- a JSON integer past a double (a time,
a `t_dtw`), JSON nested past the recursion limit, an LRC minute and a SubRip
hour past a double -- now no time, or refused by name; every format's time
fields probed at the extremes after, none crashing; `test_ingest.py`'s
`PAST_LIMITS` pins them (CHANGELOG, 07-tools.md). The cues' sort moved from
`ingest` into `normalize.cues`, which says it orders them -- timed cues only,
by their start before clamping; shown identical on 300,000 cue lists.
`read_file` reads once (no check-then-read race); the formats named once in
the dispatch; the readers' patterns named.

Box 6.4.1, reviewed end to end (335556a..d19bc98; three iterations, to none
found), aimed at what exactness made possible. Found: a `Fraction` of a text
is exact and unbounded -- `1e999999999` builds a billion-digit integer, more
than 4300 digits overflow `int`'s conversion -- so six inputs hung ffman
(killed at 15 s: an exponent, huge or tiny, in CSV, SubRip, a JSON string or
number) and four crashed or were refused (5000 digits in CSV, SubRip, LRC, a
JSON fraction); the code before answered each at once. Fixed: one bounded path,
`fields.exact`, the only text-to-`Fraction` -- a first digit past 10^308 no
number, under 10^-400 zero, 400 significant digits read and a sticky 1 for the
rest; shown to round as the unbounded `Fraction` 180,000 times (half-ms
boundaries with 600-digit tails, 3000-digit numbers, exponents at both bounds),
and in `test_fields.py` by a property whose strategy reaches the hard case --
removing the sticky digit fails it, five runs of five (its first strategy
missed it: four rare conditions at once). Every probe answers at once, as the
old code did (`test_ingest.py`'s `BOUNDLESS`). `ms(number(...))`, thirteen
times, is `fields.time_ms`.

Box 6.4.2, reviewed end to end (f854818..938dd05; two iterations, to none
found), from what exactness made possible. `bar_times`' `decimal()` cannot
refuse: every duration is ffprobe's `%f` text (`probe._seconds`, its only
source), and an eighth of a decimal is one. A font size past a double is an
`OverflowError`, older than this box (carried to 6.10's grammar box). Found: the
exact writer cost three times the floats' (2.79 s for 0.92 s on 5,000
sentences, 65,000 words) -- profiled, not guessed: 410,000 `decimal` calls,
each computing its places twice (`terminates`, then `decimal`), and formatting
the same centre and the same line's y for every event. Now
`values.finite_decimal` (places once; `terminates` gone), the centre written
once a script and each y once (a dict on the writer, no global cache): 1.17 s,
every mode's script byte-identical to before. `POS` reads every form `_number`
writes (`e+16`); a ternary wrapped around its comment, an early return; no such
wrap left in `src`.
In its proofs, `test_a_pop_grows_only_the_word` failed once in eight runs --
passing alone, in context, under load. Its clip's `gradients` defaults to a
random seed and a rotation (this ffmpeg's help): each session drew another
moving background, against a check that only the word changes; seeds 19 and 59
of 72 fail every time, and pass still. The clip pinned (`seed=1:speed=0`). A
sweep of the inputs for the like: `test_blurs`' `geq` `random()` follows its
slicing -- 8 threads drew other blocks than 1 (`8689e9c7` against `0b51fdb3`),
so a many-core builder tested another picture; now in the main graph on one
thread, its picture this one's (`0b51fdb3`, also with `-threads 8`). VHS's
`noise` is unseeded but not random (`vf_noise.c`: -1 is 123457; 1 and 8
threads alike).

Box 6.4.3, reviewed end to end (c16deb7..2a0adf2; two iterations, to none
found), from what reading stdout made possible. The code's own detection on a
real file through the real runner: stdout holds nothing but `frame:` headers
and `key=value` lines (420 of 420 -- the null muxer writes none), stderr is
empty at `-v error`, the row is the picture's; `capture` drains both pipes
(`communicate`), no deadlock; a sample prints one frame past `-frames:v`, as
the log did. The planned height rests on an invariant -- the effects before the
subtitles keep the frame's size -- true by construction (only chromatic
aberration and VHS use size-changing filters, both restore it; CRT is after
the subtitles) but unguarded: `test_effects` measured size, format and frames
for seven effects, not camcorder, from a hand-written list. Now camcorder too
(it keeps them), and a test that every staged effect (`PRE`, `POST`) is
measured -- shown failing, and naming `camcorder`, without it. The findings'
own words about the log (§F) stay: history, resolved by the box.

Box 6.4.4, reviewed end to end (c6dfb27..265202b; two iterations, to none
found), from what it made load-bearing -- the frame passed being the output's.
Burn is the script's one caller (`--preset youtube` refuses `--burn-subs`:
shown); a burn keeps the source's frames -- a GIF changes only their display
delays (the content, animation and all, rendered at the source's times),
datamosh re-times at the average rate, `frame_rate`'s choice. A slideshow's
long frames leave most words gold at once: right -- no frame could show a
pop. Found: the threshold stated loosely ("under ~250 ms"): by the rule the
settle was cut on every word under 240 ms, and with the simulator, visibly to
266-275 ms at 24-30 fps (250 at 60) -- now said so in the code, 07-tools.md,
the CHANGELOG and this plan; the gold and white as named constants
(`_GOLD`: #FFD700, ASS's &HBBGGRR&). Its first matrix failed 106 of 761 -- the sandbox's disk full (4 KB free: old pytest directories and pip/uv caches); freed, the same code passed all 761.

Box 6.4.5, reviewed end to end (1c09157..46b4835; two iterations, nothing
found), from what `w / h` can meet: a zero or negative size and a zero ratio
part are refused before the planner (run: "must be a positive integer",
"parts must be positive"), so the division cannot fail on input; a decimal
--aspect-ratio (2.39:1) reads well beside the reduced ratio. The only other
ratio written as text is chromatic aberration's SAR -- an ffmpeg argument in
ffmpeg's `num/den`, not a message: nothing to share. geometry.py's mentions
of awk are history beside its rule. No code changed; HEAD's proofs stand.

Section 6.5, reviewed end to end (8f59ae0..f66189f; two iterations, to none
found), from what owning every break made load-bearing. Found and fixed: the
units kept a mark by its combining class -- Thai's vowels are marks of class
0, so a line could open on one (`สวัสดี` split `ว`|`ั`); and a Devanagari
conjunct split past its virama, an emoji family at its joiners. Now `_joins`:
a mark by its category (Mn, Mc, Me), a character past a virama (class 9),
either side of a zero-width joiner; tested on the property -- no line opens on a
mark or joiner, none ends on a virama or joiner -- with breaks shifted mid-unit
(its first form passed the old code by parity: 22 characters a line, units of
2). The font matched as libass matches it (`ass_strcasecmp`): `-f "ibm plex
sans"` is measured. Shown: libass draws the face ffman measures -- a bold
render's ink inside Bold's advances (0.989-0.996), outside SemiBold's
(1.003-1.010), Medium's, ExtraLight's (a first check, rendered with estimated
breaks, compared two lines with one: redone). Carried: Thai's word breaking to
the follow-up box; the tests' trailing-comment wraps to 6.12.

Section 6.5, reviewed again with its second box (8f59ae0..8d9ba27; two
iterations, to none found), from how the boxes meet. A timed word wider than a
line: alone on its own line, whole -- its highlight is one, so it cannot break;
the docstring now says so. Hostile sizes, timed: 50,000 unspaced kanji 0.68 s,
a letter and 50,000 marks 0.15 s, 50,000 Latin letters 0.61 s -- linear. One
field splitter (breaks.py's; fields.py's whitespace is a number's, apart).
Found: "a mark" written out four times (`_joins`, `_base`, `Metrics.width`,
`ass._estimate`) -- now `breaks.is_mark`, once; and a count added a boolean --
now plainly.

Section 6.4, reviewed as it now stands (335556a..bd35901, its code since
reshaped by 6.5; two iterations, to none found), from how 6.5 meets it. Found
and fixed, both where the boxes meet: the pop's peak grows each side into ~45%
of a space (bash's rule), and 6.5 made unspaced timed words abut -- rendered,
a Japanese pop at its peak covered 35 px of its neighbours' ink, a spaced one
none; now a word with no space beside it (line edges count) pops unscaled,
and the Japanese covers 0, the English unchanged. The peak counted code
points: a decomposed é peaked lower -- now glyphs (`is_mark`). DRY: ASS's
centiseconds rounded half up by hand, `(ms + 5) // 10` -- the rule now once,
`values.div_half_up` ((2n + d) // 2d; equal to floor(n/d + 1/2) on 202,904
pairs), `round_half_up` through it; a Fraction there cost 45% on 15,000 events
(0.243 to 0.353 s), the integer form none (0.247). Held: the floats left are
the documented ones; the y cache is keyed by the exact y. (A test edit cut a
constant between two tests -- restored from HEAD, every removed line read.) The corpus had no pop on abutting words -- the fix invisible to it: `burn/chunk-pop-ja` added (357 cases).

The motions box, reviewed (0eb9c20; two iterations, to none found), from
libass's rules and hostile sizes. Found and fixed: keyframe times rounded onto
their predecessor -- in a 701-letter rainbow without a fade, one letter's chain
began `[0, 0, 334]`, a `\t(0,0,...)`, which libass runs to the event's end
(`t2 == 0`); a first scan missed it, sampling letter counts that share a factor
with 6 (a boundary that near 0 needs s.n + 6k = 1: n coprime with 6, over 666)
-- now a keyframe on the last moves a ms on. Unbounded cost: a hostile 2,000
letters lit 60 s in lsd made 19.5 MB of script in 14 s, parsed by libass each
frame -- now a run over 10,000 keyframes (a long cue, 84 letters 7 s, ~3,500)
keeps each letter's first colour and is noted: 0.07 MB, 0.05 s. `script`'s note
became notes (a tuple), `burn.py` says each. Held: the budget's estimate bounds
the keyframes from above; the flash counts unchanged; a normal lit run (1,200
\t) costs 0.4 ms a frame.

The colour boxes, reviewed together (7500cde..644cb3d: the text's colours,
their motions, the rectangle; two iterations, to none found), from where they
meet. Found and fixed: the motion budget was an event's for plain subtitles
but each word's in a line -- chunk-word draws a line an event: a 76-letter
line, measured with the shipped font, carried 26,980 \t, 2.7 times the
budget, unnoted; now one budget a line event (`_line_budget`). A lit run's
budget left out the outline's motion its letters carried -- a gold highlight
under one was never held; now counted. DRY: the per-letter loop written three
times (`_letters`, `_boxed_letters`, `_paint`) now `_per_letter`; a \t chain
twice, now `_steps`; whether a lit word's colours are written whole or by
letter decided in three places, three forms -- now one predicate, `whole`,
proven over every combination (2 modes, 2 highlight modes, 4 highlights, 2
fonts, 3 outlines: 192 lit events, each written one way). Tests failing on
the old code: a line's budget, the outline counted. Coverage then found a path no test took -- `--overlay-mode word` under a font in motion, `_paint` budgeting itself: tested.

Section 6.5, reviewed whole (8f59ae0..e791231; two iterations, to none
found), from how its early and late boxes meet. Found: two documents the
later boxes made false -- 07-tools.md's Highlight colour row ("no white, no
black") and the README's names, both now naming them. Architecture: ass.py
had grown to 654 lines and 46 functions, a third of them colour with state of
their own -- now subs/paint.py's Painter (203 lines; ass.py 495), built from
the three colours and the box's measures, not the Style (ass imports paint:
no cycle); ass keeps layout and timing, _box (the pop's curve) and
_line_budget (a line's letters) among them. UNKNOWN, defined in both, now
metrics.py's. _SPACE's comment off its trailing wrap, and the two space
estimates' opposite safeties stated (wrapping's 0.55, wide: lines break early;
the box's 0.15, narrow: it fits). Proven unchanged: every lit word written
one way over 96 combinations (192 events), the corpus identical.

The bar's two commits, reviewed (b1e5ed1..0fb7f24; two iterations, to none
found), from what they claim. Found false: that ffman's padded and blurred fits
place the picture a row apart -- stated in head's docstring, a test's, the
Placement row and the plan, from a hand-built overlay whose formats were not
the render's. ffman's own heads agree on every case measured (4:2:0 640x480
into 360x640, 186 both; into 1080x1920, 556 both; 4:2:2 and 4:4:4 555): each
statement corrected. measure=True stays -- the blurred head read as itself is
exact by construction, for any format; the padded one agrees only as measured.
DRY: "a fit with blurred bars", written in head's match and in burn, is
blurred_fit, once. Types: the bar's word a BarKind (Literal black, blurred).

# ffman (Python) changes from the bash ffman

Intended changes only: everything else is the bash ffman's behaviour, checked
against it (docs/ffman-python.md, G1-G5). Each entry has a test that fails on
the bash behaviour and a row in docs/decisions.md.

## Corrected (stage A: proven, G4)

- **Sizes are computed exactly.** Resize targets follow the rule docs/decisions.md
  documents -- the nearest size (even for video), halves up; a ratio and both
  sides agreeing within 1 px -- which the bash ffman's awk arithmetic broke by
  rounding twice: a 4093-wide target of a 7291x3454 video was 4094x1940, now
  4094x1938 (the true height is 1938.996); a tie such as a 7-px width for a
  21:9 video went down to 6, now up to 8; 5481x2348 at 21:9, exactly 1 px from
  the ratio, was refused, now accepted. Measured on 1 M realistic requests:
  2103 differ, each where bash broke the rule.
- **A word's share of a gap is by characters.** Words without a usable time
  share the gap between their neighbours by length; the bash ffman's gawk
  measured that length in bytes under a non-UTF-8 locale (C, POSIX) and in
  characters under UTF-8, so "é" took the share of "bb" or of "a" depending on
  the user's environment. Now characters, whatever the locale -- the bash
  ffman's own answer on a UTF-8 system (tests/equivalence/test_ingest_bash.py).

## Stage B (phase 6)

- **`ffman meta`: a metadata file written or edited from the command line**
  (spec 8): `--set`, `--add`, `--unset`, `--clear` in ffmpeg's generic keys,
  written in the output's own words (ffmetadata, Vorbis comments, a cue's disc
  fields); from a metadata or media file, or from nothing. The edits are
  declarative: a key set twice, or set and unset, is refused. Chapters too
  (`--chapter TIME[..END][=TITLE]`, `--retitle`, `--chapter-set`,
  `--drop-chapter`, `--clear-chapters`; in a cue, its tracks), in one exact
  time syntax: `62.5`, `1:02.5`, `1:01:02.5`, `4650f` -- never `MM:SS:FF`.
  A cue sheet's own: `--flags N=…`, `--pregap N=TIME` (its `INDEX 00`),
  `--file NAME`; its CATALOG (`--set barcode=`) and ISRC (`--chapter-set
  N:ISRC=`) refused unless well formed. `-o -`: the result to stdout
  (inspection, pipes), in the input's format or `-p`'s (`cue` too).
- `convert --metadata FILE`: a metadata file's tags and chapters applied to the
  output, in place of the media's (each stream's own tags kept); alone, a job
  of its own -- a remux.
- A container or a codec changed is a job, a remux: each stream copied unless
  `--video-codec`, `--audio-codec` or `--lossless` asks; whether the output
  holds each is asked of ffmpeg before any work (a header-only trial), the
  picture's flow too -- a resize into WebM from H.264 failed after its work.
- Subtitle streams kept, each on its own, in every video output: copied where
  held, else converted to the target's text (mov_text, WebVTT), else left out
  -- each conversion and each loss noted, the track named. They used to be
  dropped whole across container families.
- Tags and chapters kept: each tag an output holds not is noted (MP4's iTunes
  atoms keep a set); chapters into Ogg and FLAC as `CHAPTERxxx` comments, where
  ffmpeg wrote none (Vorbis lost them, Opus put them a second late). A source
  FLAC's CUESHEET block, which ffmpeg drops, carried into a FLAC output by
  `metaflac` -- `flac` now a runtime dependency.
- An attached metadata file (ffmetadata, Vorbis text, cue) applied where
  attachments are not held, as `--metadata` would apply it: the first that
  applies, each other noted; into Matroska, attachments carried as they are.
- Cover art kept in every video and sound output: copied where held (MP4,
  M4A, FLAC, MP3), attached into Matroska as `cover.png`/`cover.jpg`, noted
  where not (MOV drops it silently; WebM and Ogg fail on one) -- it used to be
  lost without a word.
- Into FLAC, a picture that is no cover is noted as left out (ffmpeg's muxer
  dropped it at warning level).
- ffman's metadata files and transcript readers are their own packages, ffmeta
  and subverter (MIT OR Apache-2.0, the standard library alone): ffman depends on
  them and words their refusals as before (`ffman: error: ...`).
- ffman carries its fonts: IBM Plex Sans (Regular, Bold), the captions', and IBM
  Plex Mono Bold, the camcorder's stamp's (OFL): both render alike however ffman
  was installed -- the stamp had been the host's Plex Mono, or a substitute.
  `FFMAN_FONTS_DIR` stays an override, now checked for the camcorder too.
- On Windows, ffman refuses at once and points to WSL: its tool handling is POSIX's
  (process groups, SIGHUP), as the bash ffman's shell was.
- ffman carries its ffmpeg-normalize presets (`youtube-aac` and its native twin), as
  its fonts: `--preset youtube` normalises however ffman was installed -- unset,
  `FFMAN_NORMALIZE_HOME` had refused the job (`packaging error`) outside the Nix
  package. Set, it is used: the bash package had forced its presets over the user's.
- Without nproc (macOS ships none), ffman counts the processors as Python does
  and says so; it counted one, silently -- FFV1 then kept its default four slices,
  and past 16 processors ffmpeg its own cap (below, ffmpeg threads itself). A job
  running no ffmpeg never asks.
- The image optimisers (oxipng, jpegoptim, gifsicle) are optional: one not
  installed is noted (`oxipng not found: the .png written unoptimised`), the
  output kept. A failing one still ends the job.
- metaflac is optional: asked only when a source FLAC has a CUESHEET block
  (ffman reads the blocks itself); not installed, the block is noted as left
  out and the job completes. A FLAC without one never needed it, and failed.
- A missing tool is named, and what to install: `ffmpeg not found: install
  ffmpeg (https://ffmpeg.org)`. `convert` looks ffmpeg and ffprobe up before any
  work; metadata files alone still need neither.
- A refused job tells only its refusal: a metadata file's notes, `--metadata`'s
  or an attached one's, come after the job's checks.
- **Metadata files: `convert` reads and writes ffmetadata, Vorbis comments and
  cue sheets** (`.ffmeta`, `.txt`, `.cue`): one into another, or a media file's
  tags and chapters into any (spec 3.9). A `.txt` is told by its first line, or
  written by `--preset ffmetadata` (the default) or `vorbiscomment`; each loss
  is a note, each malformed line refused with its number. `--normalize` now
  needs `--preset youtube`, the only preset it means.
- **Numbers are written as their value.** A number given in another spelling
  -- `--font-size 057.50`, `--bblur 012.50` -- is written to the subtitles and
  the filtergraph, and echoed in notes, as its value (`57.5`, `12.5`): ffman
  carries numbers typed, no longer the text as typed. libass and ffmpeg read
  both spellings alike (a frame rendered with each: identical).
- **Refusals come before any work.** Every refusal comes from the options, the
  probe and the transcript -- what ffmpeg can encode asked last -- before a
  pass, a file or the render: bash decided an overlay's output, its kind, the
  fonts' path, an effect's pixel format and the codec after its passes, and an
  attach's output after writing the track. `--burn-subs t.srt --vfx datamosh -o
  x.png` ran 9 ffmpeg (7 bar samples, a scene detection, a datamosh render)
  before "overlay output must be a video"; now none. A command with one fault
  gets the message it got (the corpus' 121 refusals, each the same), but one:
  `--add-subs` to an output without an extension says so -- `output needs an
  extension`, as the spec's `-o` and every other flow -- where bash said "a .
  file cannot carry a subtitle track". A command with several hears first of the
  options and the probe, then of the transcript.
- **Transcripts are read as their formats write them.** JSON through `json`,
  CSV and TSV through `csv`, the values typed -- not jq's `@tsv` text nor gawk's
  fields. So: a JSON text keeps a backslash single -- jq's `@tsv` doubled it and
  nothing undid it: burned, `//` where one `/` stands for it, and `\\` in an
  attached track -- and reads a CR as a break (it showed as `\r`); a time that
  is not a number is no time, its cue dropped, in every format (awk read a CSV
  or TSV one as 0 ms); a JSON value of the wrong kind is no value, where jq's
  failure refused the whole file; a CSV header names start and end in any order
  (only one starting with `start` was a header, the rest read as a cue); a
  quoted CSV field is read whole across lines. Five corpus transcripts read
  differently, each for one of these.
- **A transcript Python cannot hold is refused, never a crash.** A time past a
  double's range -- a JSON integer, an LRC minute, a SubRip hour -- is no
  time; JSON nested past Python's recursion limit is refused as such; a CSV or
  TSV field past `csv`'s 128 KiB is refused, naming the limit (no subtitle's
  text is that long; bash's gawk read it). Each was a Python traceback.
- **Times are exact, to the millisecond.** A time is read from its decimal
  text -- JSON's numbers included -- never through a float, and rounded half up
  to the whole millisecond, one rule in every format (bash had three: SubRip and
  LRC half up, WhisperX half away from zero, CSV, TSV and whisper-cli
  truncated). So `00:00:04,0245` is 4025 ms, burned at 4.03 s (it was 4024 and
  4.02), and a CSV time of 999.5 ms is 1000. An attached track is clipped at
  the media's duration in whole ms, floored: 1.005 s is 1005 ms (it was 1004).
- **Subtitles are placed exactly.** libass places text to a fraction of a pixel,
  and bash truncated it: a line is now at its exact position (981.6, not 981; a
  1985-wide canvas centred at 992.5, not 992); the canvas width and margins are
  rounded once, outline and shadow written as near as libass holds. A bar under
  the picture exactly one line of text tall is used (bash's six digits fell just
  under: 19 of 288 rows at size 57), and its samples are taken at their exact
  seconds. A line holds what its width allows: 48 characters at 1920 px and
  size 64, where a float allowed 47 -- some sentences wrap differently.
- **The pop is smooth on short words too.** libass stops drawing a word when it
  ends, so bash's pop -- settling 150 ms after its peak, whatever the word --
  was cut on every word under 240 ms: its last frame up to 8% larger than the
  next, a jump -- visible, at 24-30 fps, on words to about 270 ms. Now the pop rises and settles before the word's
  last frame, at the video's frame rate; a word no longer than a frame turns
  gold at once. Plain's colour fade likewise. The pop's peak is exact
  (1 + 0.45/chars: 106.43% for seven letters, not 106%).
- **A size and a ratio that disagree are stated exactly.** `-w 1920 -H 1080
  -a 4:3` reads "are 16:9", where bash cut awk's six-digit text to six
  characters: `1.7777:1` -- and at the extremes `123456:1` for 12345678:1,
  `1.2345:1` for 1234567.5:1.
- **Lines are broken by their width, kerned, in their own direction.** ffman
  breaks every subtitle line itself, plain mode's too: a line holds the BBC's
  width (1.2 times the frame's height), measured by the shipped font's own
  glyph widths -- so ordinary text fills its line, and wide text no longer runs
  past the frame. Japanese and Chinese, which libass could not break here (it is
  built without Unicode line breaking), break between characters. The text is
  kerned, and Hebrew or Arabic takes its own direction.
- **Japanese and Chinese lines break by their rules.** No line opens on `、`,
  `。`, a closing bracket, `！`, a small kana or `ー`, nor ends on an opening
  bracket or `￥` -- Unicode's line-breaking rules (UAX #14), strict, as ICU's
  strict line breaker breaks them; a Latin word inside stays whole; a long run
  inside spaced text breaks too. Thai breaks between syllables (never after a
  vowel written before its consonant), not yet by its words. A word wider than
  a line starts its own and breaks there, rather than run off the frame.
- **A popped word no longer covers its neighbours in Japanese or Chinese.** A
  word with no space beside it pops in colour, unscaled; a spaced word grows as
  before, and an accented word alike however it is encoded.
- **`--highlight-colorize #RRGGBB`: the highlighted word in a colour of your
  own** (gold stays the default), with `--overlay-mode chunk-word` or
  `word-highlight`.
- **`--highlight-colorize rainbow`, `lsd` or `iridescent`: the highlighted
  word's letters in turning hues** -- a moving spectrum, a vivid one, a pastel
  sheen -- never flashing more than three times a second; a run too long to
  move keeps its hues still, and says so.
- **A highlight colour by name**: `--highlight-colorize teal` (or `gold`,
  `amber`, `violet`... any case) -- each a shade bright enough against the black
  outline.
- **`--font-color` and `--outline-color`: the text's own colours** (white and
  black by default). Without an outline colour, ffman picks black or white,
  whichever stands out more -- the highlighted word too.
- **The text and its outline in motion**: `--font-color` and `--outline-color`
  take `rainbow`, `lsd` and `iridescent` too -- every letter, flowing on from
  one subtitle event to the next.
- **`--highlight-colorize rectangle`: the spoken word boxed in reverse video**
  -- a box in the text's colour, the word in its outline's; with
  `--highlight-mode pop`, the box pops around the word, never over its
  neighbours.
- **Subtitles find the bar under the picture however it looks.** A bar a resize
  makes is found blurred (`--bblur`) as well as black, a video's own black bars
  count with it, and no effect hides it any more (`--vfx invert` did).

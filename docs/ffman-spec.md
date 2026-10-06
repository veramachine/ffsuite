# ffman: the command-line spec

**Status: frozen for phase 1 (plan: [`ffman-python.md`](ffman-python.md)).**
Every value, range and message below is taken from the bash implementation
(nixos-config's `tools/ffman.sh` at its tag `ffman-bash-final`), not from its help
text. **A** marks behaviour stage A reproduces exactly. **B** marks what arrives in stage B.
**New** marks surface that exists from phase 1 and has no bash counterpart.

## 1. Invocation

```
ffman [-h | --help | --version]
ffman COMMAND [OPTIONS]
```

- **Commands:** `convert`, `effects` (phase 1); `concat`, `transcribe`,
  `probe` (phase 7). Any other word is refused: `unknown command: X (see
  ffman --help)`. No command: usage on stderr, exit 1.
- **Platform** (New): POSIX's -- ffman runs its tools in their own process
  group and stops them by it, on SIGINT, SIGTERM and SIGHUP. On Windows,
  refused before anything else: `ffman runs on Linux and macOS; on Windows, run
  it in WSL`.
- **Tools** (New): ffmpeg and ffprobe, on `PATH`. `convert` looks both up
  before any work -- but for metadata files alone (3.9), which need neither --
  refused: `ffmpeg not found: install ffmpeg (https://ffmpeg.org)` (and
  `ffprobe ...` alike). Any other tool ffman needs, missing, is refused
  by its name (`TOOL not found`); an optional one is noted instead (3.7, 3.13); `meta` needs ffmpeg and ffprobe only for a media
  file.
- **ffmpeg-normalize** (as before; re-assessed at NixOS 26.11): `--preset
  youtube` runs it when the sound is not AAC LC, 48 kHz, stereo already, or with
  `--normalize` -- as `env XDG_CONFIG_HOME=H ffmpeg-normalize ...`, H ffman's
  own presets (carried in its package, `ffman/normalize`, however installed) or,
  set, `FFMAN_NORMALIZE_HOME`. Refused before it runs: `missing ffmpeg-normalize
  preset P in D`; not on `PATH`, `env` names it and the job is refused:
  `ffmpeg-normalize failed`. A pip install needs it on `PATH`.

The tools at a glance -- each a program on `PATH` (the Nix package brings them
all):

| Tool                        | Serves                                                                                                                                                                                 | Without it                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| ffmpeg, ffprobe             | every job on media                                                                                                                                                                     | refused, before any work; metadata files need neither                                     |
| ffmpeg-normalize, `env`     | `--preset youtube`'s sound, when not AAC LC 48 kHz stereo or `--normalize`                                                                                                             | that job refused (`ffmpeg-normalize failed`; without `env`, `env not found`)              |
| metaflac                    | a source FLAC's CUESHEET block, carried (3.13)                                                                                                                                         | noted, left out; the job done                                                             |
| oxipng, jpegoptim, gifsicle | PNG, JPEG, GIF outputs optimised losslessly (3.7)                                                                                                                                      | noted, written unoptimised; the job done                                                  |
| nproc                       | the processor count -- FFV1's slices past four, ffmpeg's threads past its cap of 16 (below, ffmpeg threads itself); it honours OpenMP's variables, cgroup v2 quotas from coreutils 9.8 | Python's count of the processors usable (`os.process_cpu_count`), noted; 1 if it has none |

- **Old commands** (`resize`, `overlay`, `attach`) are refused, printing the
  equivalent (D4, §7).
- **Values:** `--opt VALUE` and `--opt=VALUE`. An empty `--opt=` is refused
  (`option --opt requires a value`), as is a missing value (`option --opt
  requires a value`). An unknown option: `convert: unknown option: X (see ffman
  convert --help)`; a flag given a value (`--overwrite=1`) is unknown as a whole.
- **Optional values** (`-b/--bblur` only, now that the effects are specs):
  bare means `auto`. The next token is taken as the value unless it starts
  with `-` followed by a letter or `-`. So `-1` is a value, and a bad one,
  exactly as bash (`optval`).
- **An empty value given apart** (`-o ""`) is accepted by the parser, as by
  bash's `take`; what it then means is each option's, as bash tested it
  (probed on bash, 17 options): **unset** for `-i` (so: required), `-o`
  (the default output), `-w`, `-H`, `-a`, `-p`, `--video-codec`,
  `--audio-codec`, `--font-size`, `--burn-subs`, `--add-subs`, `--language`;
  **a value, validated** for `-r`, `-b`, `--overlay-mode`, `--highlight-mode`,
  `--margin-bottom` (each refused, with its own message) and `--vfx`; **kept
  as given** for `-f/--font` (an empty family name).
- **Global options on every command:** `-h/--help`, `-y/--overwrite`,
  `--dry-run` (New). `--dry-run` prints each command that
  writes, shell-quoted, one per line, and runs none of them; the read-only
  analyses its commands depend on still run; nothing is written.
  `-v/--verbose` waits for stage B and a meaning: this spec gave it none, and
  stage A had accepted it and done nothing with it (vulture found the field
  never read) -- an option that does nothing is not offered.
- **Messages** keep bash's text. The old command's prefix (`resize:`,
  `overlay:`, `attach:`) becomes `convert:` where a prefix remains; where
  a message names an old flag, it names the new one.

## 2. Exit status and signals (A)

| Case                                                 | Result                                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| success                                              | 0                                                                                           |
| any refusal or failure                               | 1, stderr `ffman: error: MESSAGE`                                                           |
| stdout's reader gone (`ffman … \| head`)             | 141, silent (A: bash died of SIGPIPE)                                                       |
| the environment (a folder not writable, a disk full) | 1, stderr `ffman: error: STRERROR: FILE` (New: bash printed the failing tool's own message) |
| SIGINT / SIGTERM / SIGHUP                            | 130 / 143 / 129                                                                             |

On a signal, ffman sends TERM to the tool's process group, polls every 0.3 s
for up to 3 s, then sends KILL. On any exit it removes the partial output
and the work directory. The first signal resets the handlers, so a second one
acts at once. A signal exits silently (bash printed nothing).

## 3. `convert`

### 3.1 I/O

| Option             | Value      | Rule and message                                                                                                                                                |
| ------------------ | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-i/--input FILE`  | path       | required: `convert: --input is required`                                                                                                                        |
| `-o/--output FILE` | path       | the extension is required and selects the container: `output needs an extension (it selects the container): X`. Default `STEM.ffman.EXT` beside the input (New) |
| `--in-place`       | flag (New) | replaces the input. Exclusive with `-o`: `--in-place and --output exclude each other`                                                                           |
| `-y/--overwrite`   | flag       | an existing output needs it: `output exists: X (use --overwrite to replace it)`                                                                                 |

- Writes go to a hidden partial file beside the output (`.ffman.XXXXXX.EXT`),
  renamed into place on success (A). An empty result is refused: `ffmpeg
  produced no output` (A). The result takes the replaced file's permissions,
  or 0666 less the umask (A). Folders are created only when writing (A).
- The output may equal the input only with `--in-place` (New; bash allowed it
  implicitly): `the output is the input: use --in-place to replace it: X`.
  `--in-place` writes through the input's real path, so a symlinked input's
  target is replaced, not the link (A).

### 3.2 Picture (A)

| Option                  | Value                                             | Rule and message                                                                                                                                                                                                    |
| ----------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-w/-W/--width N`       | integer ≥ 1                                       | `--width must be a positive integer: X`                                                                                                                                                                             |
| `-H/--height N`         | integer ≥ 1                                       | `--height must be a positive integer: X`                                                                                                                                                                            |
| `-a/--aspect-ratio A:B` | `^[0-9]+(\.[0-9]+)?:[0-9]+(\.[0-9]+)?$`, both > 0 | `--aspect-ratio must look like 16:9 or 2.39:1: X`; `--aspect-ratio parts must be positive: X`; with `-w` and `-H`, they must agree: `--width W and --height H are R:1, which is not the requested --aspect-ratio X` |
| `-r/--resize-mode M`    | `fit` (default), `cover`, `stretch`               | `--resize-mode must be stretch, cover or fit: X`                                                                                                                                                                    |
| `-b/--bblur [SIGMA]`    | `auto`, or a number 0–1024 (0 = off)              | `--bblur must be auto or a number from 0 to 1024: X`; only with `fit`: `--bblur only applies to --resize-mode fit (the only mode with borders); got --resize-mode M`                                                |

With burned subtitles, `--bblur` or `--resize-mode` needs a size or a
ratio: `--bblur and --resize-mode need a size or a ratio to resize to (-w, -H
or -a)`.

A video cannot become an image (`a video cannot be resized into an image
(.EXT)`), and an image cannot become a video other than a GIF (`an image
cannot be resized into a video (.EXT)`).

Sizes follow bash's rules computed exactly (Corrected, G4): the true value
rounded half up -- to the nearest even, at least 2, for video -- and a ratio
agreeing with both sides when either is within 1 px. bash rounded twice
(`%.6g`, then to the integer) and so broke those rules in 0.2% of realistic
requests: a size 2 px off, a tie rounded down, a size exactly 1 px from the
ratio refused.

### 3.3 Effects: `--vfx SPEC` (New surface, A processing), `--afx SPEC` (phase 7)

Grammar (plan §3.3): `NAME[:ARG[,ARG…]]`, where `ARG` is either a leading
`VALUE` (the main parameter) or `KEY=VALUE`. No value means auto; the same
effect twice is refused.

| Effect                 | Parameters (the main one first) | Range and message (bash)                                                                                                                                                                              |
| ---------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `blur`                 | `sigma`                         | auto, or > 0 and ≤ 1024: `--blur must be auto or a sigma above 0, up to 1024`                                                                                                                         |
| `pixelate`             | `size`                          | auto, or an integer 2–1024: `--pixelate must be auto or a block size from 2 to 1024 px`                                                                                                               |
| `invert`               | none                            |                                                                                                                                                                                                       |
| `chromatic-aberration` | `px`                            | auto, or an integer 1–255: `--chromatic-aberration must be auto or a shift from 1 to 255 px`                                                                                                          |
| `halation`             | none                            |                                                                                                                                                                                                       |
| `camcorder`            | `date`, `time`                  | `date`: a real date, `YYYY-MM-DD` or `YYYY:MM:DD`, one separator throughout: `--date must be a real date, YYYY-MM-DD or YYYY:MM:DD`. `time`: `HH:MM:SS`, 24-hour: `--time must be HH:MM:SS (24-hour)` |
| `datamosh`             | `seconds`                       | auto, or > 0: `--datamosh must be auto or the seconds each mosh lasts`; needs a moving source: `--datamosh melts scene cuts: it needs a moving source`                                                |
| `vhs`                  | none                            |                                                                                                                                                                                                       |
| `dither`               | `colours`                       | auto (16), or an integer 2–256: `--dither must be auto or a palette size from 2 to 256 colours`                                                                                                       |
| `crt`                  | none                            |                                                                                                                                                                                                       |

In the new messages, the effect's spec replaces the old flag: bash's `--blur
must be auto or a sigma above 0, up to 1024: X` is `--vfx blur: must be auto or
a sigma above 0, up to 1024: X`; a named parameter keeps its name (`--vfx
camcorder: date must be a real date, …`). Checked against bash's
`fx_validate` on 124 values: identical, except that a date from 0001-01-01 is
required (New: GNU date also takes 0000, which the clock's calendar cannot
render). The grammar's own refusals (New): `--vfx: unknown effect: X (see
ffman effects)`, `--vfx E takes no value: SPEC`, `--vfx E takes named values
(date=, time=): SPEC`, `--vfx E: only the first value may go without a name:
SPEC`, `--vfx E: unknown parameter: K (KNOWN)`, `--vfx E: K given twice`,
`--vfx E given twice`. The old flags are refused with their spec:
`--blur 8` → `--vfx blur:8`, `--camcorder --date D --time T` → `--vfx
camcorder:date=D,time=T`.

### 3.4 Burned subtitles (A; from `overlay`)

| Option               | Value                                                           | Rule and message                                                                                                                                   |
| -------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--burn-subs FILE`   | srt, vtt, lrc, csv, tsv, json (whisper-cli, WhisperX), ass, ssa | the source must be a video: `convert: --burn-subs needs a video, not an image`                                                                     |
| `--overlay-mode M`   | `plain` (default), `chunk-word`, `word`, `word-highlight`       | `--overlay-mode must be plain, chunk-word, word or word-highlight: X`; ass/ssa only `plain`; word timing requirements as bash (its three messages) |
| `--highlight-mode M` | `plain` (default), `pop`                                        | `--highlight-mode must be plain or pop: X`; only with `chunk-word` or `word-highlight`                                                             |
| `-f/--font NAME`     | family, no comma (default IBM Plex Sans)                        | `--font must not contain a comma: X`                                                                                                               |
| `--font-size N`      | a positive number: points on a 1080-line frame                  | `--font-size must be a positive number: X`                                                                                                         |
| `--margin-bottom M`  | a fraction in [0, 1) or a percentage                            | `--margin-bottom must be a fraction in [0, 1) or a percentage: X`                                                                                  |

- The styling options need `--burn-subs`: `--X needs --burn-subs` (New).
- The old `-s/--standard`, `--chunk-word`, `--word` and `--word-highlight`
  keep their refusals (`X is now --overlay-mode Y`).
- The output must be a video: `the output must be a video to burn subtitles
  into`.

### 3.5 Soft subtitles (A; from `attach`)

| Option            | Value                                   | Rule and message                                                                                                                                                                      |
| ----------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--add-subs FILE` | repeatable; the same formats as burning |                                                                                                                                                                                       |
| `--language CODE` | repeatable; `^[a-z]{3}$` (ISO 639-2)    | `--language must be a three-letter ISO 639-2 code (eng, por, ...): X`; zero, or one per `--add-subs`: `each --add-subs takes one --language: got N --language for M --add-subs` (New) |

- A subtitle-only job copies every other stream (A).
- The container must carry subtitles: `a .EXT file cannot carry a subtitle
  track; give --output with .mka or .m4a (audio), .mkv or .mp4 (video)`.
- Stage A accepts one `--add-subs`, as bash did (`--add-subs given N times: one track per run, for now`). Several arrive in stage B.
- Without `--language`, no language tag is written (A: bash read it from
  `--language` only). Taking it from the transcript or the file name arrives
  in stage B.

### 3.6 Encoding and audio

| Option            | Value                                                                                                               | Stage                                                | Rule and message                                                                                                                                                                                                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--video-codec C` | `h264`/`avc`/`x264`/`libx264`, `hevc`/`h265`/`x265`/`libx265`, `vp9`/`libvpx-vp9`, `av1`/`aom`/`libaom-av1`, `ffv1` | A (lossless encoders)                                | `no lossless encoder for video codec 'C'; choose --video-codec h264, hevc, vp9, av1 or ffv1`; `copy` when the picture changes: `--video-codec copy is impossible here: the picture is re-rendered`; missing encoder: `this ffmpeg has no E encoder`                                                                  |
| `--audio-codec C` | `copy` (default), `none`, `flac`, `aac`, `opus`, `mp3`, `vorbis`, `alac`, `pcm`                                     | A                                                    | `unsupported --audio-codec 'C' (copy, none, flac, aac, opus, mp3, vorbis, alac, pcm)`                                                                                                                                                                                                                                |
| `-p/--preset P`   | `youtube` (alias `yt`); `ffmetadata`, `vorbiscomment` (New: a `.txt` output's format, 3.9)                          | A                                                    | `unknown preset: X (youtube, ffmetadata, vorbiscomment)`; `youtube` excludes `--lossless`, `--video-codec`, `--audio-codec`: `--preset youtube sets the codecs: --X cannot be added` (New); output `.mp4`: `YouTube's container is MP4: --output must end in .mp4`; SDR only; bt709/bt601 matrices (bash's messages) |
| `--normalize`     | flag                                                                                                                | A                                                    | only with `--preset youtube`: `--normalize needs --preset youtube` (New: bash had no other place for it)                                                                                                                                                                                                             |
| `--lossless`      | flag                                                                                                                | A: the default when video is re-encoded; B: explicit | excludes `--crf`, `--preset`                                                                                                                                                                                                                                                                                         |
| `--crf N`         | per codec: x264/x265 0–51, vp9/av1 0–63                                                                             | B                                                    | excludes `--lossless`, `--preset`                                                                                                                                                                                                                                                                                    |

### 3.7 GIF (A)

- A `.gif` output selects the GIF pipeline.
- `--loop` (forever) and `--loop-reverse` (forward, then back) need a `.gif`
  output (`--loop and --loop-reverse need a .gif output`) and a moving source
  (`--loop and --loop-reverse need a moving source: an image makes a one-frame
  GIF`).
- Giving both is refused: `--loop and --loop-reverse exclude each other` (New; in bash the last one won).
- Image and GIF outputs are optimised losslessly, in place before the rename (A):
  PNG by `oxipng -o max`, JPEG by `jpegoptim --auto-mode`, GIF by `gifsicle -O3`.
  Each optimiser is optional (New): not on `PATH`, noted -- `TOOL not found: the
  .EXT written unoptimised` -- the output kept, the job done. A failing one ends
  the job: `TOOL failed (its message is above)` (Surface: bash exited with the
  tool's status, silently).

### 3.8 Flows: what a job does (plan.py)

Stage A's `convert` does what one of the bash commands did, chosen by the
options; a job no bash command did is refused, for now (New messages): making
those work -- a remux, a codec change alone, a preset with a resize -- is
stage B's, each with its own proof (G4). In order:

0. A metadata file in or out (New, 3.9): that job alone.
1. `--preset youtube`: bash's `convert`. With a picture option (`-w`, `-H`,
   `-a`, `-b`, `-r`, `--vfx`, `--burn-subs`; a GIF's `--loop`, `--loop-reverse`)
   or `--add-subs`: `--preset youtube
   is a job of its own: X cannot be added, for now`.
2. `--add-subs`: bash's `attach` -- the track added, every other stream
   copied. With a picture option or a codec option (`--video-codec`,
   `--audio-codec`, `--lossless`): `--add-subs copies the picture and the
   sound: X cannot be added, for now`.
3. A picture option: bash's `overlay` with `--burn-subs`, else its `resize`.
4. Another extension, a codec or `--metadata`, and none of 3.'s: a remux (3.11).
5. Nothing asked: `convert: nothing to do: give a size (-w, -H, -a), an effect
   (--vfx), subtitles (--burn-subs, --add-subs), another container, a codec
   (--video-codec, --audio-codec) or --preset`.

Each flow then decides every stream as its bash command did (A), with its
refusals -- each before any work, from the options, the probe and the transcript
(stage B: bash refused some after its passes and its writes): a video into an
image, an image into a video (not a GIF), `overlay needs a video, not an image:
X`, `overlay output must be a video`, the loop rules (3.7), `--datamosh melts
scene cuts: it needs a moving source`; a picture re-encoded losslessly in the
source's codec or `--video-codec`'s (`copy` refused), a GIF, or one image frame
(`unsupported image output '.EXT' (png, jpg, webp, avif, tiff)`); every audio
stream under `--audio-codec` (a video output only); subtitle streams as
3.12's; attachments carried within one container family, else dropped with a
note: `attachments are not carried into .EXT (another container family)`
(Surface: bash's named `attach`, for the subtitles it then dropped too).

### 3.9 Metadata files (New, 6.6)

`.ffmeta`, `.txt` and `.cue` are metadata files: ffmetadata, Vorbis comments in
ffman's text form, cue sheets -- the formats are the skills' (`.agents/skills`),
what crosses between them `ffman-mappings.md` (`packages/ffmeta/src/ffmeta`).

| Input, output      | The job                                                                                                                                                                                                                                                                                       |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| metadata, metadata | read, converted, written in the output's format                                                                                                                                                                                                                                               |
| media, metadata    | the media's global tags and chapters: ffmpeg's ffmetadata export with `-fflags +bitexact` (else ffmpeg adds its own `encoder`); the tags it drops either way -- `encoder` (`mux.c`), `creation_time`, `company_name`, `product_name`, `product_version` (`ffmpeg_mux_init.c`) -- from ffprobe |
| metadata, media    | refused: `a metadata file makes a metadata file: X`                                                                                                                                                                                                                                           |

- **Formats.** `.ffmeta` is ffmetadata, `.cue` a cue sheet; a `.txt` input is
  ffmetadata when its first line begins `;FFMETADATA`, else Vorbis comments. A
  `.txt` output is `--preset ffmetadata` (the default) or `vorbiscomment`.
  A `.ffmeta` or `.cue` output takes none: `--preset P: a .EXT output is FORMAT`;
  a `.txt` preset with a media output: `--preset P is for a .txt output`.
- **The file.** UTF-8 (a cue's BOM skipped): else `not UTF-8: FILE (byte N)`. A
  line the format refuses: `FILE:LINE: MESSAGE` (the readers', 6.6.3).
- **A cue sheet.** A chapter past a cue's last time (`999999:59:74`, MM:SS:FF's
  last) left out, noted. Written from media, its `FILE` names the input; from
  another metadata file, which names no media, the input's stem, noted: `the
  cue's FILE: STEM, the media a metadata file does not name -- check it`. Read, one
  over several files is refused: its tracks are placed by the files'
  durations, which a metadata file does not hold.
- **Losses** are notes on stderr (`ffman: NOTE`): the conversion's, then the
  writer's -- what the output's format cannot hold.
- **Output.** The default `STEM.ffman.EXT` takes the input's extension (a file
  rewritten in ffman's form); `--in-place`, `-y`, the partial file and the
  printed path as 3.1. `--dry-run`: read, converted, its notes shown; nothing
  written.
- **Nothing else.** Any other option: `a metadata file is a job of its own: X
  cannot be added`.

## 4. `effects` (New)

```
ffman effects [video] [NAME]
```

Prints the catalogue, generated from the registry: each effect in stage order,
each parameter's range (read from its refusal's text) and what leaving it out
means. `NAME` shows one effect; `audio` arrives with the audio effects (phase
7). Refused: `unknown effect: X (see ffman effects)`, `effects: unexpected: …
(see ffman effects --help)`.

## 5. Environment (A)

| Variable               | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FFMAN_FONTS_DIR`      | a fonts directory for libass, in place of ffman's own (IBM Plex Sans, the captions'; IBM Plex Mono Bold, the camcorder's stamp's: carried, 6.7.3) -- for a burn and the camcorder alike. Characters ffmpeg's filter syntax splits on: refused. Lacking it: the system's font in its place (its own Plex if installed -- rendered a little apart all the same -- else a substitute), noted; the captions' line widths then estimated |
| `FFMAN_NORMALIZE_HOME` | an `XDG_CONFIG_HOME` of ffmpeg-normalize presets (`ffmpeg-normalize/presets/NAME.json`), in place of ffman's own (carried in the package). Unset or empty: ffman's own                                                                                                                                                                                                                                                              |
| `OMP_NUM_THREADS`      | the processor count's minimum, as `nproc` reads it (even above the processors); `OMP_THREAD_LIMIT` its maximum. Without `nproc`, neither read: Python's count, which `PYTHON_CPU_COUNT` overrides                                                                                                                                                                                                                                   |
| `FFMAN_NO_FDK=1`       | a test hook: act as if `libfdk_aac` were absent                                                                                                                                                                                                                                                                                                                                                                                     |

## 6. Defaults that change in stage B

| Now (A)                                               | B                                                                                        |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| video re-encodes losslessly in the source's codec     | D2's delivery default; `--lossless` keeps the old behaviour                              |
| one `--add-subs`; its language only from `--language` | several; the language also from the transcript (whisper JSON) or a `name.por.srt` suffix |
| `--video-codec` lists lossless encoders only          | delivery encoders with `--crf`                                                           |

## 7. Migration messages (D4)

| Old                                              | Message                                                                                                                                                                                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ffman resize …`                                 | `resize is now: ffman convert …` (the same options)                                                                                                                                                         |
| `ffman overlay -i F --input-subs S …`            | `overlay is now: ffman convert -i F --burn-subs S …`                                                                                                                                                        |
| `ffman attach -i F --input-subs S [-l L] [-o O]` | `attach is now: ffman convert -i F --add-subs S [--language L] (-o O \| --in-place)`                                                                                                                        |
| `--input-video`, `--input-media`                 | `X is now --input`                                                                                                                                                                                          |
| `--input-subs`                                   | `--input-subs is now --burn-subs (burn in) or --add-subs (a track)`                                                                                                                                         |
| each old effect flag                             | `--X is now --vfx X`, then the form its values take, from the effects registry: `(a value: --vfx X:VALUE)`, or camcorder's `(its values: --vfx camcorder:date=D,time=T)`; none for an effect without values |
| `--date`, `--time`                               | `--date and --time are now parameters: --vfx camcorder:date=D,time=T`                                                                                                                                       |
| `-l`                                             | `-l is now --language`                                                                                                                                                                                      |

### 3.10 `--metadata FILE` (New)

A metadata file's tags and chapters applied to a media output: `.ffmeta`,
`.txt` (ffmetadata or Vorbis comments, told by its first line) or `.cue`,
converted to ffmetadata (3.9's notes; a cue's last track ends with the media)
and given to ffmpeg as one more input. They **replace** the media's: its
global tags and chapters are the file's (`-map_metadata N -map_chapters N`,
ffmpeg's `copy_meta`), each stream's own tags kept. To merge, `meta` first:
`ffman meta -i film.mkv -o m.ffmeta`, edited, applied.

- In every flow that keeps metadata: a picture's (resize, effects, burned
  subtitles), `--add-subs`, `--preset youtube`.
- Alone: a job of its own, 3.11's -- a remux, the file's tags and chapters
  applied.
- Refused, each before any work: `--metadata takes a metadata file (.ffmeta,
  .txt, .cue): X`; `--metadata: a .EXT holds no tags or chapters` (a GIF, an
  image); `--metadata: a cue over N files describes N media`; in
  the metadata job, 3.9's `a metadata file is a job of its own`. Noted: `the
  file's stream sections: not applied -- each stream keeps its own tags`.

Its notes -- the file's conversion, its stream sections -- are told with the
job's others, after its refusals (F6): a refused job tells its refusal alone.

### 3.11 A container or a codec changed (New)

Another extension, `--video-codec`, `--audio-codec`, `--lossless` or
`--metadata`, with no size, effect or burned subtitles: a **remux** -- each
stream copied as it is unless a codec is asked for -- into its own container
whole (a cover, a data stream too, as a plain copy), elsewhere the picture
alone (the picture then encoded
losslessly, as 3.3's; the sound as `--audio-codec` says). Its subtitles as
3.12's, its attachments as 3.3's; an attached picture (a cover) not carried (6.6.5
decides it). The same extension with nothing asked is still `nothing to do`.

Whether the output holds each stream is **asked of ffmpeg** before any work:
the planned command, with `-t 0`, writes only the header (each encoder
opened), into a scratch file of the output's extension. A failure is told by
kind, retried alone: `a .EXT holds no CODEC video, the source's: --video-codec
to give one it holds` (`audio`: `--audio-codec`); an asked one, `--video-codec C: a .EXT
holds no C`; neither alone: `a .EXT holds not these streams together: MESSAGE`.
The picture's flow (resize, effects, burn) asks the same of its encoder. A GIF or an image
is a picture made anew, not a remux: `convert: a .EXT is a picture made anew:
give a size (-w, -H, -a) or an effect`.

### 3.12 Subtitle streams kept (New)

Each of the input's subtitle streams, in a video output (a remux, a resize,
effects, burned subtitles, `--preset youtube`), on its own: the first of these the output holds --
asked of ffmpeg as 3.11's, a trial each -- **copied as it is**, else converted
to `mov_text`, `webvtt`, `srt` or `ass`, in that order -- one answer a codec, the trial seeing no more of a stream. So
Matroska keeps SRT,
ASS and WebVTT as they are; the MP4 family takes `mov_text`, WebM `webvtt`. An
image subtitle passes the copy alone -- no conversion makes text of a picture
-- so it is kept where held. Each conversion noted (it loses what the target
cannot say: ASS's styles into `mov_text`): `subtitle track N (LANGUAGE,
TITLE): CODEC converted to TARGET`; each left out noted: `subtitle track N
(LANGUAGE, TITLE): CODEC -- a .EXT holds it neither as it is nor as text: left
out`. Attachments, in every video flow (`--add-subs` and `--preset
youtube` too): 3.3's family rule, its note.

### 3.13 Tags and chapters kept (New)

Every video or sound output keeps the input's tags and chapters (or
`--metadata`'s, 3.10), each as the output holds it:

- **Tags** the output holds not are told: the job's own mapping written into a
  header-only trial (3.11's) and read back, so `the tags K1, K2: a .EXT holds
  them not: left out` -- the MP4 family keeps iTunes' set (`movenc.c`'s
  `ilst`: title, artist, album, date, genre...), not `use_metadata_tags`'s
  `mdta`, which would drop iTunes' atoms for every tag (the owner's choice). A
  trial ffprobe cannot read back (Matroska, WebM, Ogg, FLAC hold any key) is
  taken as holding them all.
- **Chapters** into Ogg (`.ogg`, `.oga`, `.ogv`, `.spx`, `.opus`) and FLAC,
  where ffmpeg's muxers write none (and its Opus one writes starts a second
  late), as `CHAPTERxxx` comments -- 6.6.3's converter, its notes -- by
  `-metadata`, ffmpeg's chapters off (`-map_chapters -1`). `encoder` is
  removed first: ffmpeg's dictionary moves its last entry into the slot of one
  replaced (`dict.c`), and the muxer replaces `encoder` -- else the last
  chapter's title would move ahead of its time, and be lost.
  The chapters a FLAC source holds are read from its own comment block,
  byte-exact (`media/flac.py`): ffmpeg reads a FLAC with a CUESHEET block merged
  with the block's tracks, titles lost; and a text export (`metaflac
  --export-tags-to`) cannot tell a value's line break from two comments.
  An end is noted only when it says more than the
  comments imply: the next one's start, exactly; the last one's, the media's
  end within a millisecond (ffmpeg rounds a comment's last end so).
  Each comment goes to `-metadata` raw, as ffmpeg takes it -- not the text
  form's escapes (a `\` doubled, a line break written `\n`). A FLAC's chapter
  comments malformed are read as ffmpeg reads them, noted: `the source's
  chapter comments: WHY: read as ffmpeg reads them` -- never a refusal of the
  job.
- **A source FLAC's CUESHEET block**, which ffmpeg drops, carried into a FLAC
  output by `metaflac` -- optional: asked only when ffman finds a block (its
  type, read from the file); not on `PATH`, `the source's CUESHEET block:
  metaflac not found: left out`, the job done -- never made from
  chapters (the owner's decision): a FLAC holding both the block and the
  comments reads back, in ffmpeg and mpv, as untitled chapters (`flacdec.c`
  makes the block's tracks chapters by track number; `avpriv_new_chapter`
  overwrites the comments' of the same id). With `--metadata`, whose chapters
  replace the source's: `the source's CUESHEET block: --metadata's chapters
  replace it: left out`. `metaflac` failing, the job is refused, its output
  unwritten: `metaflac failed (its message is above)`.

### 3.14 Attached metadata files (New)

Into Matroska an input's attachments are carried as they are (3.3's family
rule). Elsewhere -- where none is held (MP4 fails on them, WebM drops them) --
an attached metadata file (`.ffmeta`, `.txt`, `.cue`, by its filename) is
applied as `--metadata` would apply it (3.10: its tags and chapters replace
the media's), the first one that applies (tried in order); `--metadata` given, it wins. Noted: `the
attached NAME: its tags and chapters applied, in place of the media's` (told
with the job's other notes, after its refusals: F6); `the attached NAME: FIRST
applied already: left out`; `the attached NAME: WHY: left out` (WHY: the refusal reading it, or `ffmpeg
extracted none`) -- never a refusal of the job.

### 3.15 Cover art (New)

A cover -- a picture marked `attached_pic`, as MP4, FLAC, MP3 hold one and
ffmpeg reads a Matroska `cover.*` attachment -- kept in every video or sound
output (`--add-subs` too, its maps all but covers), the first one (others noted):

- **Into Matroska**, extracted (byte-exact) and attached as `cover.png` or
  `cover.jpg` -- `cover_land.*` wider than tall -- its mimetype set (Matroska's
  cover art: JPEG and PNG alone, its names case-sensitive; a
  Matroska muxer would write it as a video track). Another codec: noted, left
  out. Carried after the input's own attachments where those are carried
  (ffmpeg appends `-attach` after the mapped streams; Matroska asks the cover
  first -- only a Matroska input with a cover-as-track meets both).
- **Into MOV**: noted, left out -- MOV's muxer drops it without a word
  (measured).
- **Into FLAC, a picture not a cover**: not mapped, noted -- `flacenc.c` takes
  one and drops it at warning level (`not an attached picture. Ignoring`):
  `the picture (CODEC): a .flac holds covers alone: left out`. Asked for by
  `--video-codec`, refused before any work: `--video-codec CODEC: a .flac holds
  pictures as covers alone` (`--lossless` asks the sound too, which a FLAC holds:
  noted).
- **Elsewhere**: copied with `attached_pic`, after the pictures, if a header
  trial (3.11's) holds it; else noted (WebM, Ogg fail on one: measured).

Notes: `the cover (CODEC): WHY: left out`, WHY one of `a .EXT holds none`, `a
.mov drops it, its muxer silent`, `Matroska's covers are JPEG or PNG`, `ffmpeg
extracted none`; and `the cover: one kept, not two: left out`.

## 8. `meta` (New, 6.6)

```
ffman meta [-i FILE] (-o FILE | -o - | --in-place) [TAG EDITS] [CHAPTER EDITS] [CUE EDITS] [-p P] [-y] [--dry-run]
```

A metadata file written or edited (`docs/ffman-phase6.md` 6.6.4): read as
`convert` reads one (3.9; a media file's tags and chapters too), converted to
the output's format, edited, written. Without `-i`, an empty one; `-o` is then
required: `meta: --output is required without --input`. The output, `-p`,
`-y`, `--in-place`, `--dry-run` and the notes as 3.9.

**Keys** are ffmpeg's generic ones (`avformat.h`: `title`, `artist`, `album`,
`album_artist`, `date`, `genre`, `track`, `disc`, `comment`, `composer`...),
any case, or Vorbis' own (`ALBUMARTIST`, `TRACKNUMBER`, `DISCNUMBER`,
`DESCRIPTION`). Each is written in the output's spelling, from the field table
the converter maps by (`packages/ffmeta/src/ffmeta/fields.py`): ffmetadata's generic key,
Vorbis' name (its four, else upper case), a cue's command. Another key is
written as given -- a cue has none: `--set K: a cue sheet holds no K (it
holds: FIELDS)`.

**Edits** say what the result holds, so their order on the line is none of
theirs: `--clear` (every tag), then `--unset K` (each value of K; a K the
input holds none of, or a cue cannot hold, is nothing to remove), `--set K=V`
(K's one value, where K stood, else last), `--add K=V` (one more value: Vorbis
keeps both; ffmetadata joins them with `;`, noted). What goes is removed in the
input's words, before converting, so nothing removed is noted lost; what comes
is added in the output's.

**Refused**, each before any work: `--set needs KEY=VALUE: X` (no `=`, or an
empty key; `--add` alike); `--unset needs a KEY`; `--set K twice: --add gives
another value`; `--set K and --unset K contradict` (`--add` alike); `--set K: a
cue sheet holds no K (it holds: FIELDS)`; `--add K: a cue sheet holds one K`;
`--in-place and --output exclude each other`; `meta: --output is required
without --input`; `unknown preset: X (ffmetadata, vorbiscomment)`; `meta writes
a metadata file (.ffmeta, .txt, .cue): X`; a preset as 3.9's. A value the
format cannot hold is the writer's to note (3.9).

**Chapters** (in a cue sheet, a track). A **time** is `SECONDS`, `M:SS` or
`H:MM:SS`, each with an optional `.FRACTION`, or `FRAMESf` (1/75 s): exact;
never `MM:SS:FF`, which would read as `H:MM:SS`. Else `a time is SECONDS, M:SS
or H:MM:SS (each with a .fraction) or FRAMESf: X`. **N** is the input's chapter
N, from 1.

- `--clear-chapters` (every chapter), `--drop-chapter N`, `--retitle N=TITLE`
  (`--chapter-set N:title=TITLE`), `--chapter-set N:K=V` (K as a tag's: a cue's
  track holds `title`, `performer`, `ISRC`, its gains) -- in the input's words,
  before converting, so N is always the input's.
- `--chapter TIME[..END][=TITLE]`: one more, in time order, in the output's
  words. In a cue: a track at the nearest frame (noted when moved), its end
  left out (noted: a track ends where the next starts); the tracks numbered
  again, track 1 holding the time before it (`INDEX 00` at 0, the convention
  convert writes); a new cue's `FILE` the output's stem, noted.
- **Refused:** `a chapter number is 1, 2, 3...: X`; `--retitle needs
  N=TITLE: X`; `--chapter-set needs N:KEY=VALUE: X`; `chapter N: the input has
  M chapters` (any N an edit names past them); `--drop-chapter N and --retitle
  N contradict` (`--chapter-set` alike); `chapter N's K set twice` (by
  `--retitle` or `--chapter-set`; in Vorbis, `NAME` is the title);
  `--clear-chapters and --drop-chapter N contradict` (each edit of an input
  chapter alike); `--chapter-set N:K: a cue's track holds no K (it holds:
  FIELDS)`; `--chapter X: its end before its start`; in a cue, `--chapter T:
  inside track N (its INDEX II at frame F)` and `--chapter T: a cue over N
  files: which one the track is in cannot be told`; `--chapter T: past a cue's
  last time (999999:59:74)`.

**A cue sheet's own.** Its `CATALOG` is `--set barcode=EAN` and a track's ISRC
`--chapter-set N:ISRC=CODE` (the field table's): for a cue, each is refused
unless well formed -- `--set barcode: a cue's CATALOG is 13 digits: X`,
`--chapter-set N:ISRC: a cue's ISRC is CCOOOYYSSSSS (12): X` -- where a
conversion's writer notes and leaves one out (3.9).

- `--flags N=FLAGS` (`DCP`, `4CH`, `PRE`, `SCMS`, comma-separated, any case;
  empty: none) and `--pregap N=TIME` (track N's `INDEX 00`, the pregap in the
  file -- not `PREGAP`, silence it has not; empty: none): a cue's tracks, so
  its input a cue sheet, N its track N, applied before converting as the
  other edits of N.
- `--file NAME`: the media its one `FILE` names (`WAVE`), the stem's guess
  (3.9) and its note replaced.
- **Refused:** `--flags needs N=FLAGS: X` (`--pregap`: `N=TIME`); `FLAGS are
  DCP, 4CH, PRE, SCMS, each once: X`; `--flags N twice` (`--pregap` alike);
  `--drop-chapter N and --flags N contradict` (`--pregap` alike; with
  `--clear-chapters` alike); `--flags edits a cue's tracks: the input is
  FORMAT` (`--pregap` alike); `--file names a cue's media: the output is
  FORMAT`; `--file: a cue over N files names N`; `--file: a cue's FILE name has no line
  break or NUL, no space at either end, no quote first: X`; `--pregap N=T: after its
  INDEX 01 (frame F)`; `--pregap N=T: inside track M (its INDEX II at frame
  F)`.

**`-o -`**: the result to stdout -- inspection, pipes. Its format: `-p`'s
(`ffmetadata`, `vorbiscomment` or `cue`, this one stdout's alone), else the
input's if a metadata file, else ffmetadata. No partial file, no path printed,
`-y` moot; the notes on stderr, so stdout is the text alone, in UTF-8 whatever the
locale (as a metadata file); an empty result
prints nothing (a pipe takes it: no "nothing to write"); `--dry-run` prints
nothing. A new cue's `FILE` there, the edits naming none, is `media`, noted.
Refused: `--preset cue: a .txt output is ffmetadata or Vorbis comments`;
`unknown preset: X (ffmetadata, vorbiscomment, cue)`. To a file, an empty result is
refused: `nothing to write: no tag or chapter of SOURCE is one TARGET holds`.

---
name: cue
description: Cue sheets (.cue) - the CDRWIN format by its free rendering (GNU ccd2cue) with every command (CATALOG, CDTEXTFILE, FILE, FLAGS, INDEX, ISRC, PERFORMER, POSTGAP, PREGAP, REM, SONGWRITER, TITLE, TRACK), MM:SS:FF times at 75 frames a second, EAC's layouts and REM conventions (GENRE, DATE, DISCID, COMMENT, REPLAYGAIN_*), how libcue, metaflac, mpv and ffmpeg each read them (and disagree), FLAC's CUESHEET block and the CUESHEET tag. Use this whenever reading, writing, validating or converting a cue sheet; splitting or chaptering an album rip by one; importing or exporting one with metaflac or flac --cuesheet; turning one into chapters (or chapters into one); explaining a track that starts late, a lost title, catalog or REM, or a cue sheet a player refuses; or working on ffman's cue code (--preset cue, ffman meta, cue sheets as chapters) - even when the request only says .cue, album image, or CUE file.
---

# Cue sheets

A text file laying out a CD's tracks over one or more audio files. There is no
formal specification: CDRWIN's guide (its Appendix A) is the original, and
readers disagree about almost everything past it. Everything here is read in
GNU ccd2cue's rendering of that guide, Hydrogenaudio's account of practice, RFC
9639 and the readers' sources, and measured with the versions this repository
pins (libcue 2.3.0, metaflac 1.5.0, ffmpeg 8.1.2; mpv 0.41.0 by source). The full
tables are in [references/format.md](references/format.md);
[scripts/measure.py](scripts/measure.py) re-measures them
(`python3 scripts/measure.py FFMPEG METAFLAC CUEDUMP`, with
[scripts/cuedump.c](scripts/cuedump.c) built against libcue).

## The format

One command a line, any case, any indentation; strings with spaces in double
quotes, **with no escape** -- a quoted string cannot hold `"`.

```
CATALOG 0123456789012            13 digits; disc; once; first
CDTEXTFILE "disc.cdt"            disc; once
PERFORMER "Artist"               disc (before FILE) or track (before INDEX);
TITLE "Album"                    once each; at most 80 characters
SONGWRITER "Writer"
REM GENRE "Rock"                 anywhere; ignored by the format
FILE "album.flac" WAVE           BINARY MOTOROLA AIFF WAVE MP3; FLAC goes as WAVE
  TRACK 01 AUDIO                 01-99, each one more; AUDIO or a data mode
    FLAGS DCP PRE                DCP 4CH PRE SCMS; once; before INDEX
    ISRC GBAYE7900001            12 characters: 5 alphanumeric, 7 digits
    PREGAP 00:02:00              silence before, not in the file
    INDEX 00 03:58:20            the pregap, in the file
    INDEX 01 04:00:00            the track's start; 02-99 sub-indexes
    POSTGAP 00:02:00             silence after, not in the file
```

Times are `mm:ss:ff`, frames at 75 a second (588 samples at 44.1 kHz), relative
to the start of the current `FILE`; the first index of a file is `00:00:00`.
`INDEX 01` is the track's start; `INDEX 00` begins its pregap, which belongs to
it -- so the previous track ends at `INDEX 00`.

## In practice

`REM` carries what the format lacks, `REM TAG value`: EAC writes `REM GENRE`,
`REM DATE`, `REM DISCID` (its CDDB1 id) and `REM COMMENT "ExactAudioCopy ..."`;
players and libcue use `REM REPLAYGAIN_ALBUM_GAIN -7.03 dB` and its `_PEAK`,
`_TRACK_GAIN`, `_TRACK_PEAK`; cdrdao and ImgBurn read `REM UPC` and `REM
DISCID` into CD-Text. FLAC and WavPack files are named with the type `WAVE`.

EAC's layouts: one file; one file with a hidden track before track 1 (`INDEX 00
00:00:00`, `INDEX 01` later); a file a track, the gap prepended to the next
track (`INDEX 00 00:00:00`, `INDEX 01 00:00:28`) or recreated by `PREGAP`; and a
non-compliant one, the gap appended to the previous file -- an `INDEX 00` before
the next `FILE` -- which foobar2000 and Kodi refuse and libcue misreads (every
track after it in the file before, measured): mpv alone reads it right.

## The readers disagree

| Reader                      | Strict about                                                                                                                                | Loses or misreads                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| libcue (most software)      | nothing: times, numbers and order unchecked                                                                                                 | an unquoted string of several words (gone); a bare number as frames; `REPLAYGAIN_*` values past their first word; `REM` but `DATE`, `GENRE`, gains; strings past 1,022 characters; a quoted value ending in `\` (its escape: the lines after swallowed, to the next quote); an `INDEX` after `01` in a new `FILE` (read in the one before); every track after EAC's layout (in the file before); prints "syntax error" for every sheet ending in a newline |
| metaflac, `flac --cuesheet` | at CD-DA (16-bit, 44.1 kHz): sequential tracks 1-99 and indexes, `ss` < 60, `ff` < 75, the first index at `00:00:00`, an `INDEX 01` a track | all text -- titles, performers, `REM`; `FLAGS` but `PRE`; `FILE` (a multi-file sheet refused at CD-DA, stored wrong otherwise); a `CATALOG` behind a UTF-8 BOM                                                                                                                                                                                                                                                                                             |
| mpv (source)                | any command it does not know: the whole sheet refused (libcue's `COMPOSER` too)                                                             | `INDEX 02`+; non-`AUDIO` tracks; an unquoted `FILE`                                                                                                                                                                                                                                                                                                                                                                                                        |
| ffmpeg                      | --                                                                                                                                          | reads no `.cue` at all                                                                                                                                                                                                                                                                                                                                                                                                                                     |

## FLAC's CUESHEET block and the CUESHEET tag

The block holds a catalog, a lead-in, a CD-DA flag and tracks -- each an offset
in samples to its **first** index point, a number, an ISRC, pre-emphasis and its
index points -- ending with a lead-out (170 for CD-DA, else 255). No text.
`metaflac --import-cuesheet-from` writes it, `--export-cuesheet-to` reads it
back: `INDEX` in `mm:ss:ff` for CD-DA but **in sample numbers otherwise**, which
other readers take for frames or refuse.

ffmpeg reads the block as chapters starting at each track's first index point
-- `INDEX 00` when there is one, so a pregap opens the chapter -- titled with the
track's **ISRC**. It writes no block: a FLAC through ffmpeg, copied or encoded
again, loses its cue sheet and gains no chapters. Carry it with metaflac.

A whole sheet can ride in a `CUESHEET` tag (`metaflac
--set-tag-from-file=CUESHEET=album.cue`). ffmpeg keeps it as text; mpv, when the
file has no chapters, reads it with its `.cue` parser -- one file, at least one
`AUDIO` track -- and makes chapters at each `INDEX 01`, with titles.

## Writing one every reader accepts

1. UTF-8, no BOM, LF line ends; commands in upper case.
2. Only `CATALOG`, `CDTEXTFILE`, `PERFORMER`, `TITLE`, `SONGWRITER`, `REM`,
   `FILE`, `TRACK`, `FLAGS`, `ISRC`, `PREGAP`, `INDEX`, `POSTGAP` -- nothing
   libcue-only (`CDTEXTFILE`: libcue reads it, metaflac ignores it, measured;
   mpv knows and ignores it).
3. Strings quoted, at most 80 characters, without `"` nor a `\` ending them
   (libcue's escape). A `REM` text quoted when
   it holds a space (`REM GENRE "Alternative Rock"`); a number or a gain never
   (`REM DATE 1991`, `REM REPLAYGAIN_ALBUM_GAIN -7.03 dB`): Kodi reads a number
   only when its first character is a digit, a gain from a fixed column.
4. One `FILE "name" WAVE` (several: each at a track's start, never between its
   `INDEX 00` and `01` nor after `01`); tracks `01`-`99` in order, each `AUDIO`;
   indexes numbered `00` or `01` first and one more each; the first index
   `00:00:00`.
5. Times from whole milliseconds by integer arithmetic: `frames = (ms * 75 +
   500) // 1000` (to the nearest frame -- a cue time cannot hold most
   milliseconds; the error is at most 6.7 ms), then `mm = frames // 4500`,
   `ss = frames // 75 % 60`, `ff = frames % 75`, each two digits (`mm` more if
   need be).

Back to milliseconds exactly: `frames * 1000 / 75` is a fraction; keep it one
(or as samples: `frames * 588` at 44.1 kHz) until the last step.

## Reading one correctly

Commands without case; a UTF-8 BOM skipped; CR before LF dropped; a quoted
string to the next `"` (no escapes), an unquoted one to the end of the line;
each `INDEX` relative to the `FILE` it falls under -- to place a multi-file
sheet in one stream, add the durations of the files before it; a track starts
at `INDEX 01` and its pregap at `INDEX 00`; `PREGAP` and `POSTGAP` are silence
not in any file; a `REM` value is the rest of its line. Refuse, with the line
number, what cannot be placed: a track without `INDEX 01`, a time with `ss` > 59
or `ff` > 74, indexes going back in time within a file.

## Examples

An album, one file:

```
REM GENRE "Alternative Rock"
REM DATE 1991
PERFORMER "My Band"
TITLE "The Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Opening"
    PERFORMER "My Band"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "The Road"
    INDEX 00 04:15:00
    INDEX 01 04:17:52
  TRACK 03 AUDIO
    TITLE "Arrival"
    INDEX 01 09:02:74
```

Tracks start at 0, 257.693 s (`04:17:52`: 19,327 frames) and 542.987 s; track
2's pregap begins at 255 s, so ffmpeg's chapter from a FLAC block starts there.

The tools:

```sh
metaflac --import-cuesheet-from=album.cue album.flac        # the block: no text kept
metaflac --export-cuesheet-to=- album.flac
metaflac --set-tag-from-file=CUESHEET=album.cue album.flac  # the whole sheet, as a tag
```

## Sources

GNU ccd2cue 0.5 manual, Appendices A and C (CDRWIN's guide, on the Internet
Archive only, through it and its quotations); Hydrogenaudio Knowledgebase, "Cue
sheet"; RFC 9639, Section 8.7; FLAC 1.5.0 (`grabbag/cuesheet.c`, `format.h`,
`format.c`, `metaflac`); libcue 2.3.0 (`cue_scanner.l`, `cue_parser.y`,
`libcue.h`); mpv 0.41.0 (`demux/cue.c`, `demux/demux.c`); FFmpeg n8.1.2
(`flacdec.c`, `flacenc.c`). Measurements: `scripts/measure.py`.

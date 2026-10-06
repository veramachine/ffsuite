# Cue sheets: the format, its commands, the readers, FLAC's block

Sources -- there is no formal specification:

- **CDRWIN User's Guide, Appendix A** (Golden Hawk Technology): the original,
  "widely accepted" as the specification (Kodi, Hydrogenaudio, Wikipedia). Its
  copies are on the Internet Archive, which this research could not reach; its
  rules are taken from the free rendering below and from quotations of it
  (named where used).
- **GNU ccd2cue 0.5 manual** (2015), Appendices A and C: every command, its
  values, contexts, repetition and order -- written to make the format
  "available under a free documentation license".
- **Hydrogenaudio Knowledgebase, "Cue sheet"**: practice -- EAC's layouts,
  `REM` metadata, quoting.
- **RFC 9639, Section 8.7** (with errata): FLAC's `CUESHEET` block.
- Readers, at nixpkgs' pins: **libcue 2.3.0** (`cue_scanner.l`,
  `cue_parser.y`, `libcue.h`; built, measured through `../scripts/cuedump.c`);
  **FLAC 1.5.0** (`share/grabbag/cuesheet.c` -- the parser of both `metaflac
  --import-cuesheet-from` and `flac --cuesheet` --, `include/FLAC/format.h`,
  `libFLAC/format.c`; measured); **mpv 0.41.0** (`demux/cue.c`, `demux/demux.c`;
  source only -- not built here); **FFmpeg n8.1.2** (`flacdec.c`, `flacenc.c`;
  measured -- it reads no `.cue`: `Invalid data found`).
- Measured: `../scripts/measure.py` (34 cases and an offset past the end, each through libcue, metaflac at
  CD-DA and 48 kHz, and ffmpeg).

## The format (CDRWIN, as GNU renders it)

A text file of commands, one a line; commands without case ("not case
sensitive": CDRWIN, quoted in cuetools #65); indentation free; blank lines
ignored. Three contexts: none (the disc), `FILE`, `TRACK`. Only `FILE`, `TRACK`,
`INDEX` and `REM` repeat within their context. Strings with spaces are quoted
(`"..."`); there is no escape.

| Command                                     | Value                                                                                                                                                                                                    | Where; repeats; order                                     |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `CATALOG mcn`                               | 13 decimal digits, UPC/EAN (a 12-digit UPC with a leading `0`: HA)                                                                                                                                       | disc; once; first                                         |
| `CDTEXTFILE name`                           | a CD-Text file; quoted if spaces                                                                                                                                                                         | disc; once; after `CATALOG`                               |
| `TITLE`, `PERFORMER`, `SONGWRITER` `string` | at most 80 characters; quoted if spaces                                                                                                                                                                  | disc (before `FILE`) or track (before `INDEX`); once each |
| `FILE name type`                            | `BINARY`, `MOTOROLA` (raw data), `AIFF`, `WAVE`, `MP3` (44.1 kHz, 16-bit, stereo); FLAC and WavPack written as `WAVE` (HA)                                                                               | disc; repeats; introduces its tracks                      |
| `TRACK nn type`                             | 1-99, each one more than the last (the first may be over 1); `AUDIO`, `CDG`, `MODE1/2048`, `MODE1/2352`, `MODE2/2336`, `MODE2/2352`, `CDI/2336`, `CDI/2352` (`MODE2/2048`, `MODE2/2324` GNU's additions) | within a `FILE`; repeats                                  |
| `FLAGS f...`                                | `DCP` (copy permitted), `4CH`, `PRE` (pre-emphasis), `SCMS`                                                                                                                                              | track; once; before `INDEX`                               |
| `ISRC code`                                 | 12 characters, `CCOOOYYSSSSS`: 5 alphanumeric, 7 digits; audio only                                                                                                                                      | track; once; before `INDEX`                               |
| `PREGAP mm:ss:ff`                           | silence before the track, not in the file                                                                                                                                                                | track; once; before `INDEX`                               |
| `INDEX nn mm:ss:ff`                         | 00 the pregap (in the file), 01 the track's start, 02-99 sub-indexes                                                                                                                                     | track; repeats; numbers one more each; the first 0 or 1   |
| `POSTGAP mm:ss:ff`                          | silence after the track, not in the file                                                                                                                                                                 | track; once; after `INDEX`                                |
| `REM comment`                               | ignored, to the end of the line                                                                                                                                                                          | anywhere; repeats                                         |

Times are `mm:ss:ff`: minutes, seconds, frames -- 75 frames a second (588
samples at 44.1 kHz) -- relative to the start of the current `FILE`. The first
index of a file is `00:00:00` (CDRWIN, as quoted; GNU's text says "of the
current TRACK", which a single-file sheet's second track contradicts). Only
`INDEX 01` is in the disc's table of contents. Encoding: unspecified (libyal's
analysis: no restriction on the text).

## In practice (Hydrogenaudio, EAC)

`REM` carries the metadata the format lacks, `REM TAG value` (quoted if
spaces): EAC writes `REM GENRE`, `REM DATE`, `REM DISCID` (its CDDB1 id),
`REM COMMENT "ExactAudioCopy v0.95b4"`; `REM UPC` (12 or 13 digits) and `REM
DISCID` cdrdao and ImgBurn write to CD-Text; `REM REPLAYGAIN_ALBUM_GAIN`,
`_ALBUM_PEAK`, `_TRACK_GAIN`, `_TRACK_PEAK` libcue models (its `RemType`).
Quotes are customary, not required by some readers (ImgBurn): unquoted, a
string may hold quotes (`TITLE Theme Of "Rome"`), but none can begin with one.

Layouts EAC writes: one file; one file with a hidden track before track 1
(`INDEX 00 00:00:00`, `INDEX 01` later); a file a track with the gap prepended
to the next (`INDEX 00 00:00:00`, `INDEX 01 00:00:28`), or recreated (`PREGAP
00:00:28`); and a non-compliant one, the gap appended to the previous file --
`INDEX 00` before the next `FILE` command -- which spec-following readers
(foobar2000) refuse.

## The readers

| Behaviour                 | libcue 2.3.0                                                                                                                                                                                                   | metaflac 1.5.0 (`--import-cuesheet-from`)                                                                           | mpv 0.41.0 (source)                                                                                                             |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| commands it uses          | all, plus CD-Text's `COMPOSER` `ARRANGER` `MESSAGE` `DISC_ID` `GENRE` `UPC_EAN` `SIZE_INFO` `TOC_INFO1/2`, and `FILE ... FLAC`                                                                                 | `CATALOG` `FLAGS` `TRACK` `INDEX` `ISRC`, `REM FLAC__lead-in/-out`                                                  | `FILE` `TRACK` `INDEX` `TITLE` `PERFORMER`                                                                                      |
| the rest                  | an unknown word: "bad character" each letter, skipped                                                                                                                                                          | silently ignored -- `FILE`, `TITLE`, `PERFORMER`, `PREGAP`, `POSTGAP` ...                                           | known ones ignored; **any other command: the whole file refused**                                                               |
| `REM`                     | `DATE`, `GENRE` (as CD-Text), `REPLAYGAIN_*` (**the first word only**: `-7.03 dB` read `-7.03`); quoted values kept whole (`GENRE "Alternative Rock"`); others dropped                                         | `FLAC__lead-in`, `FLAC__lead-out` (with case); others ignored                                                       | ignored                                                                                                                         |
| `CATALOG`                 | parsed, but no getter in its API                                                                                                                                                                               | kept (13 digits at CD-DA)                                                                                           | ignored                                                                                                                         |
| quoting                   | `"..."` or `'...'`; `\"` inside kept with its backslash -- so a value ending in `\` runs on to the next quote, lines and a `FILE` swallowed (measured); **unquoted: one word** -- `TITLE Theme Of "Rome"` lost | no strings kept                                                                                                     | quotes stripped if at both ends; `FILE` must be quoted                                                                          |
| strings' length           | 1,022 characters kept (a 1024-byte buffer); 80 not enforced                                                                                                                                                    | lines of 4,095 bytes at most (source)                                                                               |                                                                                                                                 |
| times                     | `mm:ss:ff` unchecked (`00:60:00` 60 s, `00:01:75` 2 s); a bare number read as **frames**                                                                                                                       | `mm:ss:ff`, `ss` < 60, `ff` < 75, at any rate; not CD-DA, sample numbers too                                        | minutes any digits, `ss` and `ff` two at most; invalid: 0                                                                       |
| numbering                 | `TRACK`'s number ignored (tracks by order); `INDEX` order unchecked                                                                                                                                            | CD-DA: tracks 1-99 sequential, indexes sequential; otherwise tracks 1-254 (255 the lead-out), indexes sequential    | only `AUDIO` tracks counted                                                                                                     |
| `INDEX 00` / `01` / `02`+ | pregap / start / kept                                                                                                                                                                                          | all kept                                                                                                            | pregap / start / ignored                                                                                                        |
| first index               | anything                                                                                                                                                                                                       | CD-DA: the first track's `00:00:00`; otherwise anything                                                             | anything                                                                                                                        |
| several `FILE`s           | each track its file, positions within it -- but an `INDEX` after `01` in a new `FILE` stays in the one before, and every track after EAC's layout too (measured)                                               | `FILE` ignored: offsets taken in the one FLAC stream -- CD-DA refuses them (not increasing), otherwise stored wrong | each track its file                                                                                                             |
| case; CRLF; tabs          | accepted                                                                                                                                                                                                       | accepted                                                                                                            | case-insensitive; line breaks stripped                                                                                          |
| UTF-8 BOM                 | three "bad character" messages, then read                                                                                                                                                                      | **glued to the first word: a `CATALOG` first is dropped silently**                                                  | skipped                                                                                                                         |
| encodings                 | bytes kept, Latin-1 too                                                                                                                                                                                        | --                                                                                                                  | UTF-8, a BOM's charset, else uchardet's guess (nixpkgs builds it in), converted (`charset_conv.c`); its probe tolerates Latin-1 |
| on success                | "syntax error" on stderr for every sheet ending in a newline (its end-of-file token; the parse unaffected); line numbers about twice the real ones                                                             | exit 0                                                                                                              | --                                                                                                                              |

## FLAC's CUESHEET block (RFC 9639, 8.7; libFLAC's `format.h`, `format.c`)

A catalog number (0-128 bytes of ASCII 0x20-0x7E), lead-in samples, a CD-DA
flag, and tracks -- each an offset in samples from the stream's start (the
format's text: "the offset to the first index point of the track", unlike a
CD's table of contents, which holds `INDEX 01`), a number (never 0), a
12-character ISRC, audio or not, pre-emphasis, and index points (offsets from
the track's, in samples; the first numbered 0 or 1, each one more) -- ending
with a lead-out track: 170 for CD-DA, else 255. CD-DA (libFLAC's legality check):
a lead-in of at least two seconds, tracks 1-99, every offset a multiple of 588
samples; index numbers 0-99 (metaflac's parser). **No text**: titles,
performers and `REM` cannot be stored.

`metaflac` treats a stream as CD-DA when it is mono or stereo, 16-bit, 44.1 kHz.
Its export (measured):

- `FILE "<the flac's own path>" FLAC`; `TRACK nn AUDIO` (else `DATA`); of the
  flags, only `FLAGS PRE` (`DCP`, `4CH`, `SCMS` are not in the block); `ISRC`;
  `CATALOG`.
- `INDEX` as `mm:ss:ff` for CD-DA, **as sample numbers otherwise**
  (`INDEX 01 132300`) -- which libcue reads as frames, CD-DA metaflac refuses.
- `REM FLAC__lead-in` (88200 for CD-DA, else 0) and `REM FLAC__lead-out
  <170|255> <the stream's length in samples>` -- after the last track, so a
  reader takes them for its `REM` lines (ffman's metaflac tests).

ffmpeg reads the block as chapters (`flacdec.c`, measured): a chapter a track,
starting at the track's offset -- **its first index point, `INDEX 00` when
there is one**, so a pregap opens the chapter (EAC's track 2, `INDEX 00
02:47:74`, `INDEX 01 02:48:27`: the chapter at 167,987 ms); ending where the
next begins, the last at the stream's end -- an offset past the end (metaflac
accepts one: measured) ends the chapter before at the end and is itself a
chapter without length. Its title is **the track's ISRC**
(passed as the title), else none. **It writes no block** (`flacenc.c` has
none): a FLAC through ffmpeg -- copied or encoded again -- loses its cue sheet,
and no chapters are written in its place (measured).

A whole cue sheet in a `CUESHEET` Vorbis comment is, to ffmpeg, plain text. mpv
reads it (`demux.c`, source): when the file has no chapters, it takes the
`cuesheet` tag -- name without case, the file's or its first stream's --
through the same parser as a `.cue` (one unknown command and it is ignored),
requires at least one `AUDIO` track and every track naming the same file, and
makes a chapter at each track's `INDEX 01` with its `TITLE` and `PERFORMER`.

## What every measured reader accepts

From the table above (libcue, metaflac at any rate, mpv's source): a UTF-8 file
without a BOM, LF; commands in upper case; strings quoted, at most 80
characters, with no `"` inside; a `REM` text quoted when it holds a space, a number or a gain never (Kodi's
`CueDocument.cpp`: `REM DATE "1991"` is no year); only
`CATALOG`, `CDTEXTFILE` (measured), `FILE "..." WAVE`, `TRACK nn AUDIO` (01-99, sequential), `TITLE`,
`PERFORMER`, `SONGWRITER`, `FLAGS`, `ISRC`, `PREGAP`, `INDEX` (00 or 01 first,
sequential), `POSTGAP`, `REM`; `INDEX` times `mm:ss:ff` with `ss` < 60 and `ff`
< 75, the first at `00:00:00`; one `FILE`. Even then libcue keeps only the first
word of a `REPLAYGAIN_*` value, and `metaflac` keeps no text.

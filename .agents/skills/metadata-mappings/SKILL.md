---
name: metadata-mappings
description: Field-by-field mappings between FFmpeg's ffmetadata, Vorbis comments and cue sheets, in every direction - album, album artist, genre, date, disc, ReplayGain, CATALOG as BARCODE, ISRC; chapters as [CHAPTER], CHAPTERxxx and CHAPTERxxxNAME, TRACK and INDEX 01; times between TIMEBASE, milliseconds and 75 frames a second; ffmpeg's renames (album_artist ALBUMARTIST, track TRACKNUMBER, disc DISCNUMBER, comment DESCRIPTION) - and what cannot cross (chapter ends, pregaps, SONGWRITER, REM COMMENT, stream tags, a track's performer in Vorbis). Use this whenever converting tags or chapters from one of the three to another - a cue sheet into chapters or a FLAC's or Opus' tags, chapters into a cue sheet, ffmpeg's ffmetadata into Vorbis comments or back; explaining a tag or a chapter renamed or lost on the way; or working on ffmeta's convert.py or fields.py - even when the request only says tags, chapters, .cue to .txt, or metadata conversion.
---

# ffmetadata, Vorbis comments, cue sheets: the mappings

How each format's fields and chapters map to the others', every direction, and
what cannot cross. The formats themselves are their skills' --
[ffmetadata](../ffmetadata/SKILL.md), [vorbiscomment](../vorbiscomment/SKILL.md),
[cue](../cue/SKILL.md): read by one, map by this one, write by the other.
Everything here is read in the readers' and writers' sources and measured with
the versions ffsuite pins (FFmpeg n8.1.2, metaflac 1.5.0, vorbis-tools 1.4.3,
cuetools 1.4.1, libcue 2.3.0; mpv 0.41.0 and Kodi 21.2 by source). The full
tables, a row per element with its source, are in
[references/mappings.md](references/mappings.md);
[scripts/measure.py](scripts/measure.py) re-measures them (`python3
scripts/measure.py FFMPEG CUETAG VORBISCOMMENT METAFLAC CUEDUMP`, CUEDUMP the
cue skill's `cuedump.c` built against libcue; the vorbiscomment skill beside
this one, whose readers it imports).

No common tool converts a cue sheet: ffmpeg reads and writes none, metaflac
keeps its layout without text, cuetools' `cuetag.sh` tags one file a track.
ffmpeg converts ffmetadata and Vorbis only through a media file. ffmeta does all
six directions (below).

## The fields

What has a place in two or three of the formats; a disc's field is a file's
global tag, a track's a chapter's tag. This is ffmeta's table (`fields.py`),
which its tests hold this one to:

| Holds | ffmetadata              | Vorbis                  | Cue                         |
| ----- | ----------------------- | ----------------------- | --------------------------- |
| disc  | `album`                 | `ALBUM`                 | `TITLE`                     |
| disc  | `album_artist`          | `ALBUMARTIST`           | `PERFORMER`                 |
| disc  | `genre`                 | `GENRE`                 | `REM GENRE`                 |
| disc  | `date`                  | `DATE`                  | `REM DATE`                  |
| disc  | `disc`                  | `DISCNUMBER`            | `REM DISCNUMBER`            |
| disc  | `REPLAYGAIN_ALBUM_GAIN` | `REPLAYGAIN_ALBUM_GAIN` | `REM REPLAYGAIN_ALBUM_GAIN` |
| disc  | `REPLAYGAIN_ALBUM_PEAK` | `REPLAYGAIN_ALBUM_PEAK` | `REM REPLAYGAIN_ALBUM_PEAK` |
| disc  | `BARCODE`               | `BARCODE`               | `CATALOG`                   |
| track | `title`                 | `NAME`                  | `TITLE`                     |
| track | `performer`             | --                      | `PERFORMER`                 |
| track | `ISRC`                  | --                      | `ISRC`                      |
| track | `REPLAYGAIN_TRACK_GAIN` | --                      | `REM REPLAYGAIN_TRACK_GAIN` |
| track | `REPLAYGAIN_TRACK_PEAK` | --                      | `REM REPLAYGAIN_TRACK_PEAK` |

- A Vorbis chapter holds its title alone (`CHAPTERxxxNAME`), so a track's `--`
  fields have no place there -- unless the album is split one file a track, as
  `cuetag.sh` does (`TITLE`, `ALBUM`, `TRACKNUMBER`, `TRACKTOTAL`,
  `ARTIST` and `PERFORMER`, `ISRC`; nothing from `REM` or `CATALOG`).
- A disc's `PERFORMER` is the album artist (Kodi; mpv shows it as the file's
  performer); `artist` alone has no disc field. A track's `PERFORMER` is mpv's
  chapter `performer`.
- `CATALOG` is the release's barcode (MusicBrainz Picard's `BARCODE`, not
  `CATALOGNUMBER`, the label's); back into a cue only as 13 digits.
- `REM` values: `REM GENRE` quoted when it holds a space; `REM DATE`, `REM
  DISCNUMBER` and gains never -- Kodi reads a number only when its first
  character is a digit, a gain from a fixed column. A gain crosses whole
  (`-7.03 dB`); libcue keeps its first word.
- Lost from a cue: `SONGWRITER` (none maps it; at most Picard's `WRITER`, not
  `COMPOSER`), `REM COMMENT` (EAC's version), `REM DISCID` (CDDB's, not
  MusicBrainz'), every other `REM`, `CDTEXTFILE`, `FILE`'s name and type,
  `FLAGS`, a data track's mode. libcue's own `COMPOSER`, `ARRANGER`, `MESSAGE`
  and `GENRE` commands make mpv refuse the whole sheet.
- Lost into a cue: every tag not in the table (`artist`, `title`, `composer`,
  `comment`, ...), the streams' tags, a chapter's other tags; any value with a
  line break; a `"` in a quoted value -- `TITLE`, `PERFORMER`, a `REM GENRE`
  with a space (a `REM DATE 19"91` is written as is). A quoted string past 80
  characters is kept, but noted.

## ffmetadata and Vorbis: ffmpeg's renames

ffmpeg renames four of its generic keys into Vorbis' names and back
(`ff_vorbiscomment_metadata_conv`); every other key crosses as written, its case
kept -- `title=T` stays lower case in Vorbis, `ARTIST` upper case in ffmetadata.

| ffmetadata     | Vorbis        |
| -------------- | ------------- |
| `album_artist` | `ALBUMARTIST` |
| `track`        | `TRACKNUMBER` |
| `disc`         | `DISCNUMBER`  |
| `comment`      | `DESCRIPTION` |

- A Vorbis name repeated (`ARTIST=A`, `ARTIST=B`) is one ffmetadata key,
  joined: `ARTIST=A\;B` -- a `;` in a value and two values then read alike.
- `COMMENT` with `DESCRIPTION`: ffmpeg keeps the first in order, drops the other.
- `ENCODEDBY` and `ENCODED_BY` stay apart from `encoded_by`; ffmpeg replaces
  `encoder` with its own.
- `[STREAM]` sections: into Ogg the global tags merge into the stream's
  comments, the stream's winning; into FLAC the global tags alone. Out of Ogg the
  comments are the stream's: `-map_metadata 0:s:0`.
- At the edges: a key holding `=` is split at the first one when read back; a
  key outside 0x20-0x7D is no valid Vorbis name (ffmpeg writes it anyway); an
  empty value is written, and dropped when read back; a CR in a Vorbis value
  ends ffmetadata's line; a language suffix (`title-eng`) is a plain name to
  Vorbis; `METADATA_BLOCK_PICTURE` is an attached-picture stream to ffmpeg, no
  tag; the vendor string is not exported. A whole cue sheet in a `CUESHEET` tag
  crosses exactly, its lines kept.

## Chapters

|            | ffmetadata          | Vorbis                                                       | Cue                                     |
| ---------- | ------------------- | ------------------------------------------------------------ | --------------------------------------- |
| A chapter  | `[CHAPTER]`         | `CHAPTERxxx`, `000`-`999` by position                        | `TRACK nn`, `01`-`99`                   |
| Its start  | `TIMEBASE`, `START` | `CHAPTERxxx=HH:MM:SS.mmm`                                    | `INDEX 01 mm:ss:ff`                     |
| Its end    | `END`               | none: the next start, or the media's end                     | none: the next `INDEX 01`, or the media |
| Its title  | `title`             | `CHAPTERxxxNAME`                                             | the track's `TITLE`                     |
| Other tags | any                 | `CHAPTERxxx<KEY>`: ffmpeg reads it back as a tag of the file | the track fields above                  |

- Neither Vorbis nor a cue holds an end: a gap or an overlap between chapters
  does not cross, nor the last chapter's end -- the media's duration, which a
  writer of ffmetadata needs from the media.
- ffmpeg writes Vorbis chapters into Opus alone (`oggenc.c`): Ogg Vorbis and
  FLAC get none. `-map_metadata -1` drops the chapters' titles too
  (`-map_metadata:g -1` drops only the global tags); a stream copy with
  `-fflags +bitexact` and no tag writes no comment at all, its chapters lost.
- A cue track's pregap (`INDEX 00`) has no chapter: mpv and Kodi count it in the
  track before (which ends at the next `INDEX 01`), libcue in its own track,
  and ffmpeg's chapters from a FLAC `CUESHEET` block start at it. Lost too:
  `INDEX 02` and after, `PREGAP`, `POSTGAP`, track numbers not from 1.
- A sheet over several `FILE`s is one stream: each `INDEX` plus the durations of
  the files before it, which the sheet does not hold; the files' bounds are lost.
- Into a cue: chapters in time order, at most 99. A first chapter after 0 gives
  track 1 an `INDEX 00 00:00:00` before its `INDEX 01`: the time before it is
  track 1's (libcue starts track 1 at the `INDEX 01`, ffmpeg's FLAC block at 0).

## Times

- A cue's `mm:ss:ff` counts 75 frames a second. Into ffmetadata exactly:
  `TIMEBASE=1/75`, `START` in frames (ffmpeg keeps both).
- Into Vorbis' milliseconds: `frames * 40 / 3` to the nearest -- at most 1/3 ms
  off, never a tie; back to frames exactly.
- Milliseconds into a cue: `frames = (ms * 75 + 500) // 1000`, at most 20/3 ms
  (6.67 ms) off; then `mm = frames // 4500`, `ss = frames // 75 % 60`,
  `ff = frames % 75`. Only 7.5% of milliseconds survive ms to frames to ms.
- ffmpeg writes a Vorbis chapter's time (into Opus) with its whole seconds
  **rounded** (`vorbiscomment.c`): a start half a second or more past a second
  comes out a second late -- 113/75 s (1.507 s) as `00:00:02.507`, 257.693 s as
  `00:04:18.693`. Write them from whole milliseconds by division (the
  vorbiscomment skill), as ffmeta and ffman do; keep times as fractions until
  that last step.

## Converting

ffmeta (ffsuite's `packages/ffmeta`, `pip install ffmeta` once published;
Python 3.13, text in and text out) maps by the rows above and notes every loss:

```python
from fractions import Fraction
import ffmeta

meta = ffmeta.read(text, "cue", "album.cue")  # "ffmetadata", "vorbis" or "cue"
converted = ffmeta.convert(meta, "cue", "ffmetadata")  # into a cue: media="album.flac"
written = ffmeta.write(converted.meta, "ffmetadata", duration=Fraction(600))  # the last end
print(written.text, *converted.notes, *written.notes, sep="\n")
```

A cue over several files needs `durations=` (each file's length in seconds, but
the last's). ffman's commands convert by ffmeta, each note printed; `ffman meta`
knows no media length, so it refuses a cue over several files and ends the last
chapter where it starts (noted); `convert --metadata` ends it with the media:

```sh
ffman meta -i album.cue -o album.ffmeta                  # or -o album.txt -p vorbiscomment
ffman meta -i album.ffmeta --file album.flac -o album.cue
ffman convert -i album.flac --metadata album.cue -o album.opus --audio-codec opus
```

ffmpeg alone, between ffmetadata and Vorbis, through media -- the last
command's chapters a second late past half a second (Times); `-map 0:a`, since
a FLAC's cover is a picture stream that Opus cannot hold:

```sh
ffmpeg -i in.flac -f ffmetadata in.ffmeta                         # FLAC's comments
ffmpeg -i in.opus -map_metadata 0:s:0 -f ffmetadata in.ffmeta     # Ogg's: the stream's
ffmpeg -i in.flac -i in.ffmeta -map 0:a -map_metadata 1 -map_chapters 1 -c:a libopus out.opus
```

## Examples

A cue sheet, its media 600 s long:

```
REM GENRE "Alternative Rock"
REM DATE 1991
REM COMMENT "ExactAudioCopy v1.6"
CATALOG 0123456789012
PERFORMER "My Band"
TITLE "The Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Opening"
    PERFORMER "Guest"
    ISRC GBAYE7900001
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "The Road"
    INDEX 00 04:15:00
    INDEX 01 04:17:52
```

As ffmetadata:

```
;FFMETADATA1
album_artist=My Band
album=The Album
genre=Alternative Rock
date=1991
BARCODE=0123456789012
[CHAPTER]
TIMEBASE=1/75
START=0
END=19327
title=Opening
performer=Guest
ISRC=GBAYE7900001
[CHAPTER]
TIMEBASE=1/75
START=19327
END=45000
title=The Road
```

As Vorbis comments:

```
ALBUMARTIST=My Band
ALBUM=The Album
GENRE=Alternative Rock
DATE=1991
BARCODE=0123456789012
CHAPTER000=00:00:00.000
CHAPTER000NAME=Opening
CHAPTER001=00:04:17.693
CHAPTER001NAME=The Road
```

Lost into both: `REM COMMENT` and track 2's pregap (`INDEX 00 04:15:00`); into
Vorbis also track 1's `PERFORMER` and `ISRC`, and track 2's start moves to the
nearest millisecond (19,327 frames are 257,693.33 ms).

Back the other way, ffmetadata with a first chapter at 30 s:

```
;FFMETADATA1
album=The Album
album_artist=My Band
artist=My Band
genre=Alternative Rock
date=1991
comment=Ripped in 2026
[CHAPTER]
TIMEBASE=1/1000
START=30000
END=257693
title=Opening
performer=Guest
[CHAPTER]
TIMEBASE=1/1000
START=257693
END=600000
title=The Road
```

As a cue sheet, its media `album.flac`:

```
REM GENRE "Alternative Rock"
REM DATE 1991
TITLE "The Album"
PERFORMER "My Band"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Opening"
    PERFORMER "Guest"
    INDEX 00 00:00:00
    INDEX 01 00:30:00
  TRACK 02 AUDIO
    TITLE "The Road"
    INDEX 01 04:17:52
```

Lost: `artist` and `comment` (no cue field) and the last chapter's end; track
2's start moves to the nearest frame (257,693 ms is 19,326.975 frames).

## Sources

FFmpeg n8.1.2 (`vorbiscomment.c`, `oggparsevorbis.c`, `oggenc.c`, `flacenc.c`,
`metadata.c`, `fftools/ffmpeg_mux_init.c`); mpv 0.41.0 (`demux/demux_cue.c`,
`demux/demux.c`, `misc/charset_conv.c`); Kodi 21.2 (`xbmc/CueDocument.cpp`);
cuetools 1.4.1 (`cuetag.sh`, `cueprint.c`); libcue 2.3.0; MusicBrainz Picard's
tag definitions (`picard-docs`, `variables/tags_*.rst`); the three formats'
skills. Measurements: `scripts/measure.py`, parts A-H of
[references/mappings.md](references/mappings.md).

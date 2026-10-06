---
name: vorbiscomment
description: Vorbis comments - the NAME=value tags of Ogg Vorbis, Opus (OpusTags), FLAC (VORBIS_COMMENT, "FLAC tags"), Speex and Theora - by their specifications (Vorbis I, RFC 7845, RFC 9639), with field names, repeated names, the CHAPTERxxx chapter extension, METADATA_BLOCK_PICTURE cover art, ReplayGain and R128 gains, CUESHEET, what ffmpeg writes and reads (and gets wrong), and the text form vorbiscomment and metaflac read and write. Use this whenever reading, writing, editing, validating or converting Vorbis comments or a text file of them; tagging Ogg, Opus or FLAC files with ffmpeg, metaflac or vorbiscomment; carrying tags or chapters into or out of these files; explaining a lost, merged or shifted tag or chapter; or working on ffman's vorbiscomment code (the .txt variant, --preset vorbiscomment, ffman meta) - even when the request only says FLAC tags, Ogg tags or opus metadata.
---

# Vorbis comments

The tag format of Ogg Vorbis, Opus, Speex, Theora and FLAC: a list of
`NAME=value` comments. It is Xiph's own format, not a variant of ffmpeg's
ffmetadata. Everything here is read in its specifications and the tools' sources
and measured with the versions this repository pins (ffmpeg 8.1.2, metaflac
1.5.0, vorbiscomment 1.4.3); the full tables are in
[references/format.md](references/format.md), and
[scripts/measure.py](scripts/measure.py) re-measures them
(`python3 scripts/measure.py FFMPEG METAFLAC VORBISCOMMENT`), reading every
comment as bytes with its own Ogg and FLAC readers.

## The format

A vendor string, then the comments: each a 32-bit little-endian length and that
many bytes, nothing terminated.

- **A comment** is `NAME=value`, split at the first `=`.
- **Names** are ASCII 0x20-0x7D except `=`, compared without case. FLAC's RFC
  also allows `~` (0x7E), but its own library (libFLAC) and `vorbiscomment`
  refuse it: keep to 0x20-0x7D. Names are not internationalized; any name may
  be used, without prefix.
- **Values** are UTF-8 and may hold line breaks.
- **Names may repeat** -- three `ARTIST` comments are "permissible, and
  encouraged" -- so a comment list is not a dictionary. Order has no meaning in
  the specification, but tools keep it and pictures rely on it.

| Carrier       | Comment header                     | Limits                                                        |
| ------------- | ---------------------------------- | ------------------------------------------------------------- |
| Vorbis        | `\x03vorbis` ... and a framing bit | 2^32-1 comments of up to 2^32-1 bytes; the header is required |
| Opus          | `OpusTags` ..., no framing bit     | readers may ignore what lies past 61,440 bytes                |
| FLAC          | metadata block 4, no framing bit   | one block a file, 16 MiB in all                               |
| Speex, Theora | their magic, no framing bit        |                                                               |

## Names and values

No name is required. The Vorbis specification proposes `TITLE`, `VERSION`,
`ALBUM`, `TRACKNUMBER`, `ARTIST`, `PERFORMER`, `COPYRIGHT`, `LICENSE`,
`ORGANIZATION`, `DESCRIPTION`, `GENRE`, `DATE`, `LOCATION`, `CONTACT`, `ISRC`.
In use, music taggers follow MusicBrainz Picard's 87 names (`ALBUMARTIST`,
`TRACKTOTAL`, `DISCNUMBER`, `COMMENT`, `ARTISTSORT`, `MUSICBRAINZ_*`, ... --
all listed in [references/format.md](references/format.md)).

| Name                                        | Value                                                                                 |
| ------------------------------------------- | ------------------------------------------------------------------------------------- |
| `DATE`, `ORIGINALDATE`                      | ISO 8601: `YYYY-MM-DD`, `YYYY-MM` or `YYYY` (the wiki's proposal)                     |
| `TRACKNUMBER`, `DISCNUMBER`                 | a number; totals in `TRACKTOTAL`/`TOTALTRACKS`, `DISCTOTAL`/`TOTALDISCS`              |
| `ENCODER`                                   | the application -- the vendor string names the codec library                          |
| `REPLAYGAIN_TRACK_GAIN`, `_ALBUM_GAIN`      | `-7.03 dB`; `_PEAK` `1.21822226` -- not in Opus (RFC 7845: SHOULD NOT)                |
| `R128_TRACK_GAIN`, `R128_ALBUM_GAIN` (Opus) | Q7.8 dB, an integer -32768 to 32767, optional sign, at most 6 characters, one of each |
| `WAVEFORMATEXTENSIBLE_CHANNEL_MASK` (FLAC)  | `0x` and hexadecimal: the channels present                                            |
| `METADATA_BLOCK_PICTURE`                    | a FLAC picture block in base64 (no line feeds, padding kept); repeatable, in order    |
| `COVERART`                                  | deprecated raw base64 -- convert to `METADATA_BLOCK_PICTURE`                          |
| `CUESHEET`                                  | a whole cue sheet in one comment (metaflac's convention); to ffmpeg plain text        |

## Chapters

The Chapter Extension (Xiph wiki):

```
CHAPTER000=00:00:00.000
CHAPTER000NAME=Opening
CHAPTER001=00:12:30.500
CHAPTER001NAME=The road
CHAPTER001URL=https://example.org/road
```

`CHAPTERxxx` is a start, `Hour:Min:Seconds.fraction`; `xxx` runs 000-999, so at
most 1000 chapters. `NAME` is the title, `URL` optional. There is no end: a
chapter ends where the next begins.

Write chapters so every reader takes them exactly -- ffmpeg's reader is strict:

1. Three digits, from `000`; the `NAME` comment after its `CHAPTERxxx` (a
   `NAME` before it stays a plain tag in ffmpeg).
2. The time `HH:MM:SS.mmm` from whole milliseconds, by division, never rounding:
   `h = ms // 3600000`, `m = ms // 60000 % 60`, `s = ms // 1000 % 60`,
   `ms % 1000`.
3. Always three fractional digits: ffmpeg reads `01.5` as 1.005 s and drops a
   time without a fraction.
4. At most 99 hours: ffmpeg reads two hour digits.

**Do not let ffmpeg write them.** Its writer (Opus is the only container it
writes chapters to) computes whole seconds by rounding, so every start with a
fraction of half a second or more comes out a second late -- 0.5 s as
`00:00:01.500`, 59.5 s as `00:01:00.500` -- and reads back that way. FFmpeg's
current source has the same code. Its FLAC and Ogg Vorbis muxers write no
chapters at all.

**Nor trust its order.** ffmpeg keeps tags in a dictionary that, when it
replaces a key it holds, moves its last entry into that key's place
(`libavutil/dict.c`). It replaces `encoder` on every write, so comments given
with `-metadata` can come out reordered -- a `NAME` before its time, its title
lost (measured: FLAC, `-c copy`). Write chapter comments with a tool that keeps
the order given -- `metaflac --set-tag` for FLAC -- and read the result back.

## What ffmpeg does with them

- **Writing**: global tags into the stream's comment header, keys as given, with
  four renamings -- `album_artist` as `ALBUMARTIST`, `track` `TRACKNUMBER`,
  `disc` `DISCNUMBER`, `comment` `DESCRIPTION` -- and no check of the name: it
  will write a name holding `=`. Vendor `Lavf...` (`ffmpeg` with
  `-fflags +bitexact`), and an `encoder` tag.
- **Reading**: repeated names joined with `;` -- `ARTIST=A` and `ARTIST=B` read
  as `ARTIST=A;B`, the same as a single `ARTIST=A;B`; an empty value, an empty
  name, or a comment without `=`, dropped; the four renamings back; a valid
  `METADATA_BLOCK_PICTURE` as a cover, an invalid one dropped; ReplayGain tags
  also as gain data. Picard's `COMMENT` stays `COMMENT`, not ffmpeg's
  `comment`.

## The text form

The specifications define comments inside a stream only. As text, two tools set
the convention -- a comment a line -- and differ:

| Measured                 | `vorbiscomment` (Ogg Vorbis only) | `metaflac` (FLAC only)                    |
| ------------------------ | --------------------------------- | ----------------------------------------- |
| line breaks in a value   | `-e`: `\n`, `\r`, `\\` escapes    | none: its export cannot be imported again |
| a malformed line         | skipped, the rest written, exit 0 | the whole import refused                  |
| blank and `#` lines      | skipped                           | refused                                   |
| a last line without `\n` | read                              | **dropped silently**                      |
| CRLF                     | the CR stays in the value         | the CR stays in the value                 |

Single-line values without backslashes read the same in both.

ffman's form (decided from the above; a file `ffman` reads and writes):

```
file     = *line
line     = name "=" value LF            ; every line, the last too
name     = 1*(%x20-3C / %x3E-7D)        ; ASCII but "=", "~" and controls
value    = *(char / "\\" / "\n" / "\r") ; ABNF literals: backslash-backslash,
                                        ; backslash-n, backslash-r: a \, LF, CR
char     = any UTF-8 character but "\", LF, CR and NUL
```

UTF-8; no other backslash sequence, no `NUL`, no blank or comment lines -- a
malformed line refused with its number, the whole file. An empty value is kept
(the specification allows it), though ffmpeg would drop it. Without backslashes
or line breaks in its values, such a file is also a valid `metaflac` tag file.

## Examples

A file in ffman's form:

```
TITLE=The Long Way
ARTIST=Ana Souza
ARTIST=Rui Lima
DATE=2026-10-03
TRACKNUMBER=1
TRACKTOTAL=12
DESCRIPTION=Unabridged\nread by the authors
CHAPTER000=00:00:00.000
CHAPTER000NAME=Departure
CHAPTER001=00:12:30.000
CHAPTER001NAME=The Road
CHAPTER002=00:41:05.500
CHAPTER002NAME=Arrival
```

Two `ARTIST` comments; `DESCRIPTION` spans two lines; the chapters start at 0,
750 s and 2465.5 s.

The tools:

```sh
vorbiscomment -l -e song.ogg > tags.txt            # list, escaped
vorbiscomment -w -e -c tags.txt song.ogg new.ogg   # replace them all
metaflac --export-tags-to=tags.txt song.flac
metaflac --remove-all-tags --import-tags-from=tags.txt song.flac
metaflac --set-tag="ARTIST=Ana Souza" song.flac
```

Chapters into FLAC, in order (`metaflac` appends each `--set-tag` as given):

```sh
metaflac --set-tag=CHAPTER000=00:00:00.000 --set-tag=CHAPTER000NAME=Departure \
  --set-tag=CHAPTER001=00:12:30.000 --set-tag="CHAPTER001NAME=The Road" song.flac
```

Into Ogg, through ffmpeg -- then check the order it wrote:

```sh
ffmpeg -i in.ogg -c copy -metadata CHAPTER000=00:00:00.000 \
  -metadata CHAPTER000NAME=Departure -metadata CHAPTER001=00:12:30.000 \
  -metadata CHAPTER001NAME="The Road" out.ogg
```

## Sources

The Vorbis I comment specification (libvorbis 1.3.7, `doc/v-comment.html`); RFC
7845, Section 5.2; RFC 9639, Sections 8.6-8.8 and 10.1, with its errata; the
Xiph wiki's VorbisComment and Chapter Extension pages; MusicBrainz Picard's tag
mapping; FFmpeg n8.1.2 (`vorbiscomment.c`, `oggparsevorbis.c`, `oggenc.c`,
`flacenc.c`, `flacdec.c`, `replaygain.c`) and master; vorbis-tools 1.4.3
(`vcomment.c`); FLAC 1.5.0 (`metaflac`, `libFLAC/format.c`). Measurements:
`scripts/measure.py`.

---
name: ffmetadata
description: The ffmetadata format, exactly as FFmpeg reads and writes it - the ;FFMETADATA1 text file of a media file's tags, stream tags and chapters (extension .ffmeta) - with its grammar, escaping, chapter time bases, every generic key and modifier, and what each container (MP4, MOV, M4A, MKV, WebM, Ogg, Opus, FLAC, MP3, WAV, AVI, MPEG-TS) keeps of it. Use this whenever reading, writing, validating, editing or converting an ffmetadata file; exporting or importing tags and chapters with ffmpeg (-f ffmetadata, -map_metadata, -map_chapters); explaining why a tag or chapter vanished through a container; or working on ffman's metadata code (.ffmeta and .txt files, ffman meta, metadata carried across containers) - even when the request only says metadata file, chapters file, or tags.
---

# ffmetadata

ffmpeg's own text form of a file's metadata: global tags, each stream's tags,
and chapters. ffmpeg exports it (`-f ffmetadata`) and reads it back as an input
whose tags and chapters are mapped into an output. Everything below is FFmpeg
n8.1.2's behaviour, read in its source and measured; the full tables and the
evidence are in [references/format.md](references/format.md), and
[scripts/measure.py](scripts/measure.py) re-measures all of it against any
ffmpeg (`python3 scripts/measure.py /path/to/ffmpeg`).

The documentation (`doc/metadata.texi`) is shorter and kinder than the code.
Where they differ, this skill follows the code, because a file has to work in
the program that reads it.

## The format

```
file     = header *line
header   = ";FFMETADATA" version EOL          ; version "1" -- never checked
line     = comment / empty / section / tag
comment  = (";" / "#") *char EOL              ; the line's first byte only
section  = "[STREAM]" EOL / "[CHAPTER]" EOL chapter-times
chapter-times = ["TIMEBASE=" int "/" int EOL] "START=" int EOL "END=" int EOL
tag      = key "=" value EOL                   ; split at the first unescaped "="
EOL      = LF / CR LF / CR                     ; unescaped
```

- **Header.** `;FFMETADATA1`. ffmpeg recognises a file by the prefix
  `;FFMETADATA` alone, then skips the line as a comment. Without it, ffmpeg does
  not recognise the file (it still reads it given `-f ffmetadata`).
- **Order.** Global tags first, then `[STREAM]` and `[CHAPTER]` sections in any
  order, each running to the next section or the end of the file.
- **Sections** are matched as whole lines, exactly and with case: `[chapter]` is
  not a section -- its lines become global tags, silently.
- **Escaping.** A backslash makes the next byte literal, whichever byte it is.
  So `=`, `;`, `#`, `\` and a line break inside a key or value must be escaped
  (`\=`, `\;`, `\#`, `\\`, `\` then a real line break), and `\n` written as two
  characters reads as a plain `n` -- there are no C escapes.
- **Whitespace belongs to the tag**: `k = v` is key `k` and value `v`.
- **UTF-8**, by the documentation; nothing checks it.

What ffmpeg's reader does with the rest -- know this before trusting a file:

| Line                                                    | ffmpeg's reading                                                                                                          |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| no `=`                                                  | dropped, silently                                                                                                         |
| `k=`                                                    | a tag with an empty value                                                                                                 |
| `=v`                                                    | a tag with an empty key                                                                                                   |
| `Title=a`, later `title=b`                              | one tag, `title=b`: keys match without case, last wins                                                                    |
| a comment ending in `\`                                 | the next line joins the comment: lost                                                                                     |
| a comment with `=` ending the file, no line break       | read as a tag (`;x=y`: key `;x`)                                                                                          |
| an unescaped carriage return in a value                 | ends the line: the rest is lost                                                                                           |
| a chapter without `START`                               | an error logged; start 0 or the last chapter's end                                                                        |
| a chapter without `END`                                 | an error logged; the line read in its place is lost; written back with `END=0`                                            |
| a `NUL` byte                                            | ends the line: the rest is lost                                                                                           |
| a value ending in `\` (escaped `\\`), then a line break | the next line is read into it                                                                                             |
| lines ended by CR alone                                 | tags read; a chapter's times not: the chapter broken                                                                      |
| `START=12abc`, `TIMEBASE=1`                             | 12; `1/1000000000` (`sscanf` takes a number's leading digits, a sign and spaces too; without `/D` the default 10^9 stays) |

## Writing a file ffmpeg reads back exactly

ffmpeg's own writer (`ffmetaenc.c`) gets one thing wrong: it escapes `#` `;` `=`
`\` and line feeds, but not carriage returns, which its reader ends lines at.
So a value holding a CR does not survive ffmpeg's own export. A writer that
must round-trip:

1. Start with `;FFMETADATA1` and a line feed.
2. Escape `#` `;` `=` `\`, line feed and carriage return in every key and value
   with a backslash. Keys and values are otherwise written as they are.
3. Write global tags, then one `[STREAM]` a stream in order, then chapters.
4. Give every chapter `TIMEBASE`, `START` and `END`, in that order, then its
   tags -- the reader takes them in no other order.
5. Avoid duplicate keys differing only in case: only the last survives.
6. Do not write a `NUL`: the reader ends the line there, and nothing escapes it.
7. Do not end a value in `\`: written `\\`, it still escapes the line break
   after it, and the next line is read into the value (the reader looks one byte
   back). Only a file's last line, with no line break, can end in one.

ffmpeg writes `encoder=Lavf...` into every file it produces and replaces a given
`encoder`; expect it in any export.

## Keys and values

The generic keys (`avformat.h`): demuxers export a container's tags under these
names where they have them, and leave the rest as the container stores them.

| Key                | Meaning                                 | Value                                                                           |
| ------------------ | --------------------------------------- | ------------------------------------------------------------------------------- |
| `album`            | the set this work belongs to            | text                                                                            |
| `album_artist`     | the set's main creator, if not `artist` | text ("Various Artists")                                                        |
| `artist`           | the work's main creator                 | text                                                                            |
| `comment`          | any further description                 | text                                                                            |
| `composer`         | who composed it, if not `artist`        | text                                                                            |
| `copyright`        | the copyright holder                    | text                                                                            |
| `creation_time`    | when the file was made                  | ISO 8601 (`2026-10-03T12:00:00.000000Z`)                                        |
| `date`             | when the work was made                  | ISO 8601 (`2026-10-03`)                                                         |
| `disc`             | the subset's number                     | `current` or `current/total`                                                    |
| `encoder`          | software that made the file             | text -- ffmpeg sets its own                                                     |
| `encoded_by`       | who made the file                       | text                                                                            |
| `filename`         | the original file name                  | text                                                                            |
| `genre`            | the genre                               | text                                                                            |
| `language`         | the work's main language                | ISO 639-2; several comma-separated                                              |
| `performer`        | who performed it, if not `artist`       | text                                                                            |
| `publisher`        | the label                               | text                                                                            |
| `service_name`     | a broadcast channel's name              | text                                                                            |
| `service_provider` | a broadcast service's provider          | text                                                                            |
| `title`            | the work's name                         | text                                                                            |
| `track`            | the work's number in its set            | `current` or `current/total`                                                    |
| `variant_bitrate`  | an HLS or DASH variant's total bitrate  | integer: its `BANDWIDTH`, bits a second (RFC 8216); set by `hls.c`, `dashdec.c` |

Any other key is allowed (`x_custom=...`); whether it survives depends on the
container. Two modifiers may follow a key, in this order: `-` and an ISO 639-2/B
language (`title-ger`), then `-sort` (`artist-sort=Beatles, The`). Containers
also have keys of their own -- MP4's `show`, `season_number`, `compilation`,
`media_type`; MOV's `make`, `model`, `location` -- listed in
[references/format.md](references/format.md).

## Chapters

```
[CHAPTER]
TIMEBASE=1/1000
START=0
END=60000
title=Opening
```

`START` and `END` are integers in `TIMEBASE` units -- nanoseconds without a
`TIMEBASE`. Give one: ffmpeg's own exports always do. The reader accepts a
negative `START`; ffmpeg's command line clamps every chapter it copies to the
output (start at least 0, end at most `-t`) and drops chapters wholly outside it
(`fftools/ffmpeg_mux_init.c`, `copy_chapters`). Matroska stores chapters in
nanoseconds; MP4 and MP3 keep the given time base.

## Streams

`[STREAM]` sections are the ffmetadata input's streams 0, 1, ... in order. They
reach an output only through a stream mapping -- `-map_metadata 1` copies the
global tags alone:

```sh
ffmpeg -i in.mkv -i meta.ffmeta -map 0 -map_metadata 1 -map_metadata:s:a:0 1:s:0 -c copy out.mkv
```

Exporting is the mirror: by default only global tags and chapters are written.
Add `-map 0 -c copy` for a `[STREAM]` section a stream, or `-map_metadata 0:s:0`
to export one stream's tags as the global ones. Ogg, Vorbis and Opus files keep
their tags on the stream, so their default export holds only `encoder`.

## What each container keeps

Measured with the 21 generic keys, two modifiers, a custom key and two
chapters (`encoder` aside):

| Container       | Tags kept (of 23)                           | Chapters            |
| --------------- | ------------------------------------------- | ------------------- |
| `.mkv`, `.webm` | 23 (names upper-cased)                      | exact (nanoseconds) |
| `.ogg` (Vorbis) | 23, on the stream                           | none                |
| `.opus`         | 23, on the stream                           | starts only         |
| `.flac`         | 23                                          | none                |
| `.mp3`          | 23 (ID3v2; others as `TXXX`)                | exact               |
| `.mp4`, `.m4a`  | 12 (all with `-movflags use_metadata_tags`) | exact               |
| `.mov`          | 9                                           | exact               |
| `.wav`          | 10 (RIFF INFO)                              | none                |
| `.avi`          | 9 (`album` back as `product`)               | none                |
| `.ts`           | 2 (`service_name`, `service_provider`)      | none                |

Which key each container writes under which name, and what each loses, is in
[references/format.md](references/format.md).

## Examples

A file with every feature, as ffmpeg reads it:

```
;FFMETADATA1
title=bike\\shed
;this line is a comment
artist=FFmpeg troll team
x_custom=a\=b
artist-sort=troll team, FFmpeg
[STREAM]
language=eng
[CHAPTER]
TIMEBASE=1/1000
START=0
END=60000
title=chapter \#1
[CHAPTER]
TIMEBASE=1/1000
START=60000
END=120000
title=two\
lines
```

`title` is `bike\shed`; `x_custom` is `a=b`; the first chapter's title is
`chapter #1`, the second's spans two lines.

Export a file's metadata, edit it, put it back without re-encoding:

```sh
ffmpeg -i in.mkv -f ffmetadata meta.ffmeta
ffmpeg -i in.mkv -i meta.ffmeta -map 0 -map_metadata 1 -map_chapters 1 -c copy out.mkv
```

Into MP4, keeping custom keys:

```sh
ffmpeg -i in.mkv -i meta.ffmeta -map 0 -map_metadata 1 -map_chapters 1 -c copy \
  -movflags use_metadata_tags out.mp4
```

## Sources

FFmpeg n8.1.2: `doc/metadata.texi`; `libavformat/ffmetadec.c`, `ffmetaenc.c`,
`ffmeta.h`, `avformat.h` (the generic keys); the muxers' tables -- `movenc.c`,
`matroska.c`, `vorbiscomment.c`, `id3v2.c`, `riff.c`, `avidec.c`,
`mpegtsenc.c`; `fftools/ffmpeg_mux_init.c` (`copy_chapters`). Measurements:
`scripts/measure.py`, run against ffmpeg 8.1.2.

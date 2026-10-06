# Vorbis comments: the format, its field names, ffmpeg, the text form

Sources, each at the version this repository's nixpkgs pins or as fetched on
2026-10-03:

- Vorbis I comment specification: libvorbis v1.3.7, `doc/v-comment.html`.
- Opus: RFC 7845, Section 5.2 (`OpusTags`; RFC 8486 updates it for channel
  mappings only).
- FLAC: RFC 9639, Sections 8.6-8.8 and 10.1, with its verified errata (EID
  8256, 8810: neither about metadata).
- Xiph wiki: `VorbisComment` (oldid 16339), `Chapter_Extension` (oldid
  15985).
- MusicBrainz Picard's tag mapping (`picard-docs`, `appendices/tag_mapping.rst`,
  master): the names in use, as RFC 9639 Section 8.6.1 suggests.
- FFmpeg n8.1.2: `libavformat/vorbiscomment.c`, `oggparsevorbis.c`,
  `oggenc.c`, `flacenc.c`, `flacdec.c`, `replaygain.c`; FFmpeg master
  (`vorbiscomment.c`, 2026-10-03) for the chapter writer.
- vorbis-tools 1.4.3 (`vorbiscomment/vcomment.c`, built against libogg 1.3.6
  and libvorbis 1.3.7); FLAC 1.5.0 (`src/metaflac/`, `src/libFLAC/format.c`).
- Measured: `../scripts/measure.py`, which reads every comment as bytes with
  its own Ogg and FLAC readers.

## The format

A vendor string, then a list of comments, each `NAME=value`: lengths 32-bit
little-endian, strings not terminated. The name ends at the first `=`; names are
compared without case (A-Z equal to a-z); values are UTF-8, "8 bit clean" --
line breaks included. Names may repeat: three `ARTIST` comments are "permissible,
and encouraged" (Vorbis spec). The specification gives order no meaning; the
wiki makes picture order significant, and both tools keep the order (measured).

| Carrier                  | Magic before it | Framing bit | Name characters       | Limits                                                                                                                                        |
| ------------------------ | --------------- | ----------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Vorbis (Vorbis I spec)   | `\x03vorbis`    | yes         | 0x20-0x7D but `=`     | 2^32-1 comments of 2^32-1 bytes; header mandatory                                                                                             |
| Opus (RFC 7845, 5.2)     | `OpusTags`      | no          | as Vorbis             | lengths within the packet; MAY reject over 120 MB, MAY ignore comments past 61,440 bytes; trailing data kept if its first byte's low bit is 1 |
| FLAC (RFC 9639, 8.6)     | a type-4 block  | no          | U+0020-U+007E but `=` | one block a file; 16 MiB (24-bit block size)                                                                                                  |
| Theora, Speex (RFC 7845) | their own       | no          | as Vorbis             |                                                                                                                                               |

The name ranges differ: RFC 9639 allows `~` (0x7E), the Vorbis specification
does not -- and neither does FLAC's reference implementation: libFLAC's
`FLAC__format_vorbiscomment_entry_name_is_legal` rejects anything above 0x7D
(measured: `metaflac` refuses `A~B=x`). An empty name passes libFLAC's check.
In FLAC-in-Ogg the comment block SHOULD be the first header packet after the
first (RFC 9639, 10.1). In a Theora file, the first stream's comments cover the
multiplexed group (wiki).

## Field names and values

No name is mandatory. The Vorbis specification proposes fifteen: `TITLE`,
`VERSION`, `ALBUM`, `TRACKNUMBER`, `ARTIST`, `PERFORMER`, `COPYRIGHT`,
`LICENSE`, `ORGANIZATION`, `DESCRIPTION`, `GENRE`, `DATE`, `LOCATION`,
`CONTACT`, `ISRC`. Names are not internationalized; vendors may add their own,
with no prefix.

| Convention                                                        | Where defined           | Value                                                                                                                                                                                                               |
| ----------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WAVEFORMATEXTENSIBLE_CHANNEL_MASK`                               | RFC 9639, 8.6.2         | `0x` and hexadecimal (zero-padding allowed); name and value without case; FLAC's only standard name                                                                                                                 |
| `R128_TRACK_GAIN`, `R128_ALBUM_GAIN`                              | RFC 7845, 5.2.1         | Q7.8 dB: an integer -32768..32767, optional sign, leading zeros, at most 6 characters, no spaces; one of each; added to the header's output gain                                                                    |
| `ENCODER`                                                         | RFC 7845, 5.2; wiki     | the application (the vendor string is the codec library)                                                                                                                                                            |
| no `REPLAYGAIN_*` in Opus                                         | RFC 7845, 5.2.1         | SHOULD NOT                                                                                                                                                                                                          |
| `METADATA_BLOCK_PICTURE`                                          | wiki                    | a FLAC picture block (RFC 9639, 8.8), base64 (RFC 4648, 4: no line feeds, padding kept); repeatable; types 1 and 2 once each; order significant; MIME `image/`, `image/png`, `image/jpeg`, `-->` (a link), or empty |
| `COVERART`                                                        | wiki                    | deprecated: raw base64 of an image -- convert to `METADATA_BLOCK_PICTURE`                                                                                                                                           |
| `CUESHEET`                                                        | `metaflac(1)`           | a whole cue sheet as one comment (`--set-tag-from-file="CUESHEET=image.cue"`); ffmpeg: a plain (multi-line) tag, no chapters (measured)                                                                             |
| `CHAPTERxxx`, `CHAPTERxxxNAME`, `CHAPTERxxxURL`                   | wiki, Chapter Extension | below                                                                                                                                                                                                               |
| dates                                                             | wiki (proposal)         | ISO 8601: `YYYY-MM-DD`, `YYYY-MM`, `YYYY`                                                                                                                                                                           |
| `REPLAYGAIN_TRACK_GAIN` `_TRACK_PEAK` `_ALBUM_GAIN` `_ALBUM_PEAK` | wiki                    | `-7.03 dB`, `1.21822226`                                                                                                                                                                                            |
| `GEO_LOCATION`                                                    | wiki                    | `latitude;longitude[;elevation]`, decimal, C locale                                                                                                                                                                 |
| `RIGHTS`, `RIGHTS-DATE`, `RIGHTS-URI`                             | wiki                    | a proposal, not adopted                                                                                                                                                                                             |

In use -- the 87 Vorbis names of MusicBrainz Picard's tags (85 tags, the totals
under two names each; 7 have none), the list RFC 9639 points to: `ACOUSTID_ID`, `ACOUSTID_FINGERPRINT`, `ALBUM`, `ALBUMARTIST`,
`ALBUMARTISTSORT`, `ALBUMSORT`, `ARRANGER`, `ARTIST`, `ARTISTSORT`, `ARTISTS`,
`ASIN`, `BARCODE`, `BPM`, `CATALOGNUMBER`, `COMMENT`, `COMPILATION`, `COMPOSER`,
`COMPOSERSORT`, `CONDUCTOR`, `COPYRIGHT`, `DATE`, `DIRECTOR`, `DISCNUMBER`,
`DISCSUBTITLE`, `ENCODEDBY`, `ENCODERSETTINGS`, `ENGINEER`, `GENRE`, `GROUPING`,
`KEY`, `ISRC`, `LANGUAGE`, `LICENSE`, `LYRICIST`, `LYRICS`, `MEDIA`, `DJMIXER`,
`MIXER`, `MOOD`, `MOVEMENTNAME`, `MOVEMENTTOTAL`, `MOVEMENT`, `MUSICBRAINZ_*`
(`ARTISTID`, `DISCID`, `ORIGINALARTISTID`, `ORIGINALALBUMID`, `TRACKID`,
`ALBUMARTISTID`, `RELEASEGROUPID`, `ALBUMID`, `RELEASETRACKID`, `TRMID`,
`WORKID`), `FINGERPRINT`, `MUSICIP_PUID`, `ORIGINALFILENAME`, `ORIGINALDATE`,
`ORIGINALYEAR`, `PERFORMER` (`artist (instrument)`), `PRODUCER`,
`RATING:user@email`, `LABEL`, `RELEASECOUNTRY`, `RELEASEDATE`, `RELEASESTATUS`,
`RELEASETYPE`, `REMIXER`, `REPLAYGAIN_*` (`ALBUM_GAIN`, `ALBUM_PEAK`,
`ALBUM_RANGE`, `REFERENCE_LOUDNESS`, `TRACK_GAIN`, `TRACK_PEAK`, `TRACK_RANGE`),
`SCRIPT`, `SHOWMOVEMENT`, `SUBTITLE`, `DISCTOTAL` and `TOTALDISCS`, `TRACKTOTAL`
and `TOTALTRACKS`, `TRACKNUMBER`, `TITLE`, `TITLESORT`, `WEBSITE`, `WORK`,
`WRITER`. Picard writes `COMMENT` (the specification has `DESCRIPTION`) and
`ENCODEDBY`.

## Chapters (the Chapter Extension)

`CHAPTERxxx=HH:MM:SS.sss`, `xxx` 000-999 (1000 chapters at most): a chapter's
start, `Hour:Min:DecimalSeconds`; `CHAPTERxxxNAME=` its title (UTF-8);
`CHAPTERxxxURL=` optional. No end: a chapter ends where the next starts (ffmpeg:
the last at the stream's end). The wiki's example starts at 001. No nesting
(WebVTT recommended for that).

## ffmpeg

**Who writes comments.** Ogg (`oggenc.c`: Vorbis and Theora, Speex, Opus, FLAC
and VP8 headers) and FLAC (`flacenc.c`); Matroska only inside a FLAC track's
header. The vendor string is ffmpeg's library (`Lavf62.12.102`), or `ffmpeg`
with `-fflags +bitexact` (measured); its reader exports no vendor string
(measured). The renamings below are applied before writing.
Global tags go into the stream's comment header and read back as the stream's
tags. Chapters are written for Opus alone: FLAC's muxer passes none, Ogg's only
to Opus headers.

**The mapping** (`ff_vorbiscomment_metadata_conv`, both ways): `ALBUMARTIST`
album_artist, `TRACKNUMBER` track, `DISCNUMBER` disc, `DESCRIPTION` comment.
Every other key passes by name, written as given (lower-case `title` stays
lower-case; `encoded_by` is not Picard's `ENCODEDBY`; Picard's `COMMENT` is not
ffmpeg's `comment`).

**The writer** (`ff_vorbiscomment_write`), measured:

| Behaviour                                                                                                                                                                                            | Measured                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| keys written unchecked                                                                                                                                                                               | `with space=c` (legal), `tilde~=d` (illegal but in FLAC's RFC), `k=eq=e` from an escaped ffmetadata key: a name holding `=`, unreadable                                                          |
| chapters numbered from `CHAPTER000`, titles as `NAME`, no ends; other chapter tags as `CHAPTERxxx<KEY>` and at most 1000 (source)                                                                    | `CHAPTER000=...`, `CHAPTER000NAME=...`                                                                                                                                                           |
| **chapter starts with a fraction of 0.5 s or more written one second late** (whole seconds by `av_rescale`, rounding to nearest; milliseconds apart)                                                 | 500 ms as `00:00:01.500`, 1600 as `02.600`, 59.5 s as `00:01:00.500`, 59:59.6 as `01:00:00.600` -- read back as written. Unchanged in FFmpeg master                                              |
| `encoder` set to ffmpeg's own                                                                                                                                                                        | `encoder=Lavf62.12.102`                                                                                                                                                                          |
| **comment order not kept** when a key it holds is replaced: `av_dict_set` moves the dictionary's last entry into the replaced key's place (`libavutil/dict.c`); `encoder` is replaced on every write | FLAC, `-c copy`, chapters by `-metadata`: written `CHAPTER001NAME`, `CHAPTER000`, `CHAPTER000NAME`, `CHAPTER001`, `encoder` -- the second title lost on reading; Ogg Vorbis kept the order given |

**The reader** (`ff_vorbis_comment`, used by Ogg and FLAC), measured on crafted
comments:

| Comments                                               | ffmpeg's reading                                               |
| ------------------------------------------------------ | -------------------------------------------------------------- |
| `ARTIST=A`, `ARTIST=B`                                 | `ARTIST=A;B`: repeated names joined with `;`                   |
| `ARTIST=A`, `artist=B`                                 | `artist=A;B`: matched without case, the later name's case kept |
| `ARTIST=A;B`                                           | the same as two: the join cannot be told apart                 |
| `EMPTY=`, `=v`, `justtext`                             | each dropped (the specification allows an empty value)         |
| `A~B=x`, `Title=x`, `LYRICS=one`LF`two`                | kept as they are                                               |
| `ALBUMARTIST` `TRACKNUMBER` `DISCNUMBER` `DESCRIPTION` | album_artist, track, disc, comment                             |
| `CHAPTER000=00:00:01.5`                                | 1005 ms: the fraction read as milliseconds (`%03d`)            |
| `CHAPTER000=00:05:00` (no fraction)                    | no chapter: the comment (and its `NAME`) kept as plain tags    |
| `CHAPTER000=1:02:03.004`                               | 3723004 ms                                                     |
| `CHAPTER000=100:00:00.000`                             | no chapter (hours `%02d`): a plain tag                         |
| `CHAPTER01=...` / `CHAPTER1=...`                       | a chapter / a plain tag (two digits or three)                  |
| `chapter002=...`, `chapter002name=...`                 | a chapter: matched without case                                |
| `CHAPTER003NAME` before `CHAPTER003`                   | the chapter untitled; the `NAME` kept as a plain tag           |
| `CHAPTER004URL=...`                                    | a plain tag                                                    |
| `METADATA_BLOCK_PICTURE=` (valid)                      | a cover (attached picture)                                     |
| `METADATA_BLOCK_PICTURE=AAAA`                          | dropped, with a warning                                        |

`REPLAYGAIN_TRACK_GAIN`, `_TRACK_PEAK`, `_ALBUM_GAIN`, `_ALBUM_PEAK` become
ReplayGain side data as well (FLAC, Ogg Vorbis: `replaygain.c`); Opus's
`R128_*` are not read as gains -- no file of ffmpeg's names them.

## The text form

The specifications define comments inside a stream only. As text, two tools set
the convention -- one comment a line, `NAME=value`:

| Behaviour, measured             | `vorbiscomment` 1.4.3 (`-w -c`, `-l`)                                          | `metaflac` 1.5.0 (`--import-tags-from`, `--export-tags-to`) |
| ------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| what it edits                   | Ogg Vorbis only: an `.opus` refused (measured)                                 | FLAC only: FLAC-in-Ogg (`.oga`) refused (measured)          |
| a value's line break            | `-e`: `\n`; without it, the line spills                                        | spills on export; refused on import (no `=`)                |
| escapes                         | `-e`: `\n` `\r` `\\` `\0`, both ways; others an error                          | none: backslashes literal                                   |
| `\0`                            | accepted, the value cut there (its manual: a bug)                              | --                                                          |
| a malformed line                | skipped with "bad comment", the rest written, exit 0                           | the whole import refused, exit 1 (atomic)                   |
| an empty line, a `#` line       | skipped (no `=`)                                                               | refused: the format has neither                             |
| a last line without a line feed | read                                                                           | **dropped, silently** (exit 0)                              |
| CRLF                            | the CR kept in the value                                                       | the CR kept in the value                                    |
| names                           | 0x20-0x7D but `=`; `~` refused                                                 | the same; an empty name accepted                            |
| case                            | kept                                                                           | kept                                                        |
| invalid UTF-8                   | with `-R`: that line refused, the rest written; else converted from the locale | refused (even raw)                                          |
| line length                     | unbounded (source)                                                             | 65,535 bytes, else the import aborts                        |
| repeated names                  | kept, in order                                                                 | kept, in order                                              |

Where they meet: one file of single-line values without backslashes -- repeated
names and values holding `=` included -- both wrote byte for byte the same
comments.

**Decided -- ffman's `vorbiscomment` text form** (from the above):

1. UTF-8, LF; every line ends with one, the last too (`metaflac` drops an
   unterminated last line).
2. One comment a line, `NAME=value`, split at the first `=`; repeated names kept
   in order (the specification encourages them).
3. Names of 0x20-0x7D but `=`, not empty: what every tool accepts (`~`: FLAC's
   RFC allows it, its library and `vorbiscomment` do not; ffmpeg drops an empty
   name).
4. In values, `\` `\n` `\r` written as `\\`, `\n`, `\r` -- `vorbiscomment -e`'s
   escapes, the only lossless line form; any other backslash sequence refused.
   A file without backslashes or line breaks in its values reads the same in
   both tools.
5. No `NUL` (no tool keeps one: `vorbiscomment` cuts it, `metaflac` and ffmpeg
   use C strings): refused.
6. No comment or blank lines: a malformed line refused with its number, the
   whole file (`metaflac`'s way: atomic).
7. An empty value kept (the specification allows it), noted where ffmpeg would
   drop it.

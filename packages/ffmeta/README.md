# ffmeta

Media metadata files read, written and converted through one model: FFmpeg's
ffmetadata, Vorbis comments, and cue sheets.

It is pure -- text in, text out: no ffmpeg, no file opened. A file read becomes
one model -- its tags, its streams' tags, its chapters, a cue sheet's disc;
written in another format, what that format cannot hold is told as a note, never
dropped in silence.

| Format         | What it is                                                           |
| -------------- | -------------------------------------------------------------------- |
| ffmetadata     | FFmpeg's `;FFMETADATA1` text: global and stream tags, chapters       |
| Vorbis comment | `NAME=value` lines, as `vorbiscomment` and `metaflac` read and write |
| Cue sheet      | the CDRWIN format: an album's tracks, their times and fields         |

What crosses between them, field by field and with its reasons, is
[ffman's mappings](https://github.com/veramachine/ffsuite/blob/main/docs/ffman-mappings.md).

## Installing

```sh
pip install ffmeta
```

Python 3.13 or later; the standard library alone.

## Using it

```pycon
>>> import ffmeta
>>> text = ";FFMETADATA1\ntitle=Album\n\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=60000\ntitle=One\n"
>>> meta = ffmeta.read(text, "ffmetadata", "album.ffmeta")
>>> converted = ffmeta.convert(meta, "ffmetadata", "vorbis")
>>> written = ffmeta.write(converted.meta, "vorbis")
>>> print(written.text, end="")
title=Album
CHAPTER000=00:00:00.000
CHAPTER000NAME=One
>>> converted.notes + written.notes
('chapter ends: Vorbis comments hold none (a chapter ends where the next begins): left out',)
>>> ffmeta.read("title=x\n", "ffmetadata", "bad.ffmeta")
Traceback (most recent call last):
  ...
ffmeta.Error: bad.ffmeta:1: not ffmetadata: the first line must begin ;FFMETADATA: title=x
```

What crosses into the target is converted; what does not is a note, from
`convert` (a field the target lacks) or `write` (a structure it lacks). A text
that cannot be read is refused: `ffmeta.Error`, its message the reason.

## Licence

Part of [ffsuite](https://github.com/veramachine/ffsuite), beside ffman: its own package.
Licensed under either of
[MIT](https://github.com/veramachine/ffsuite/blob/main/packages/ffmeta/LICENSE-MIT)
or [Apache-2.0](https://github.com/veramachine/ffsuite/blob/main/packages/ffmeta/LICENSE-APACHE),
at your option.

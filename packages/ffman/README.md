# ffman

Opinionated media conversion on ffmpeg: resize, effects, subtitles, encoding.
One command, `convert`, transforms one media file; `effects` lists the video
effects. Lossless by default: a resize keeps the source's codec and loses
nothing.

## Running it

On Linux or macOS; on Windows, in WSL (ffman refuses to run on Windows itself: it handles its
tools as POSIX does). From its flake -- on Linux (x86_64, aarch64) or macOS (Apple silicon: not
yet tested) -- the tools it runs come with it:

```sh
nix run github:veramachine/ffsuite -- convert -i in.mp4 -w 1280
```

Or as a container image, built from the flake on Linux, its ffmpeg with Fraunhofer's FDK AAC --
for your own use: ffmpeg's own build calls such an ffmpeg "nonfree and unredistributable", so no
binary cache holds it either (it builds from source). Docker, from the folder of your files:

```sh
nix build github:veramachine/ffsuite#image && ./result | docker load
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" ffman:0.1.0 convert -i in.mp4 -w 1280
```

`ffman convert --help` lists every option; `ffman effects`, the effects and
their values. `--dry-run` prints the plan and every ffmpeg command, and writes
nothing. Without `-o`, the output is `STEM.ffman.EXT` beside the input;
`--in-place` replaces the input.

## What it needs

The Nix package and the image bring everything. Installed any other way, ffman needs
**ffmpeg** (with ffprobe) on `PATH`; the rest only for what they serve:

| Tool                         | For                                                                    | Without it                              |
| ---------------------------- | ---------------------------------------------------------------------- | --------------------------------------- |
| ffmpeg-normalize (and `env`) | `--preset youtube`, when the sound needs normalising                   | that job is refused                     |
| metaflac (flac)              | a FLAC's cue sheet carried into a FLAC                                 | noted and left out; the job completes   |
| oxipng, jpegoptim, gifsicle  | PNG, JPEG, GIF outputs optimised losslessly                            | noted; written unoptimised              |
| nproc (coreutils)            | the processor count: FFV1's slices past four, ffmpeg's threads past 16 | Python's count of the processors, noted |

ffman carries its fonts, IBM Plex Sans for burned captions and IBM Plex Mono for
the camcorder's stamp (`FFMAN_FONTS_DIR` names another folder), and the ffmpeg-normalize
presets `--preset youtube` uses (`FFMAN_NORMALIZE_HOME` names another: an `XDG_CONFIG_HOME`,
its presets in `ffmpeg-normalize/presets/`). Converting metadata files alone (with `meta` or
`convert`, no media) needs none of the tools.

## Examples

```sh
# a 9:16 story, the bars filled with the picture, blurred
ffman convert -i trip.mp4 -a 9:16 -w 1080 -b -o trip.story.mp4
# burned subtitles, the spoken word highlighted (word timings: whisper-cli -ojf, WhisperX)
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode chunk-word --highlight-mode pop
# the same, the spoken word in a colour of your own
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode chunk-word --highlight-colorize '#00BFFF'
# ...or by name, any case: gold, red, orange, amber, yellow, lime, green, emerald, teal, cyan
# (aqua), sky, blue, indigo, violet, purple, fuchsia (magenta), pink, rose, slate, gray (grey),
# zinc, neutral, stone, white, black
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode chunk-word --highlight-colorize teal
# the text in a colour, outlined by contrast (black or white) unless --outline-color says
ffman convert -i talk.mp4 --burn-subs talk.srt --font-color amber
# the spoken word boxed in reverse video: the box the text's colour, the word its outline's
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode chunk-word --highlight-colorize rectangle
# ...or the text itself in motion, outlines too
ffman convert -i talk.mp4 --burn-subs talk.srt --font-color iridescent --outline-color lsd
# ...or its letters in hues that turn: rainbow, lsd, iridescent
ffman convert -i talk.mp4 --burn-subs talk.json --overlay-mode chunk-word --highlight-colorize rainbow
# a subtitle track, nothing re-encoded
ffman convert -i film.mkv --add-subs film.srt --language eng --in-place
# for YouTube: H.264 High, two passes, AAC
ffman convert -i clip.mov -p youtube -o clip.mp4
# a cue sheet as Vorbis comments (a .txt: -p ffmetadata, the default, or vorbiscomment)
ffman convert -i album.cue -o album.txt -p vorbiscomment
# a media file's tags and chapters, as ffmetadata (or a .txt, a .cue)
ffman convert -i film.mkv -o film.ffmeta
# a metadata file edited (keys: ffmpeg's generic ones, any case), or written anew
ffman meta -i album.cue --in-place --set genre='Alt Rock' --set date=1991
ffman meta -o tags.txt -p vorbiscomment --set title=Song --add artist=A --add artist=B
# chapters (a cue's tracks): TIME as 62.5, 1:02.5, 1:01:02.5 or 4650f (frames)
ffman meta -i book.ffmeta --in-place --chapter 12:30=Road --retitle 1=Departure
# a cue sheet's own: its media, a track's flags and pregap (INDEX 00)
ffman meta -i album.cue --in-place --file album.flac --flags 2=PRE --pregap 2=4:15
# to stdout: a file's tags and chapters, as read (or -p ffmetadata, vorbiscomment, cue)
ffman meta -i film.mkv -o -
# a metadata file's tags and chapters, applied: alone (streams copied), or with any job
ffman convert -i film.mkv -o tagged.mkv --metadata chapters.cue
# another container: a remux, each stream copied (or encoded, when asked)
ffman convert -i clip.webm -o clip.mp4
ffman convert -i clip.mp4 -o clip.webm --video-codec vp9 --audio-codec opus
# effects, in any combination
ffman convert -i home.mp4 --vfx vhs --vfx camcorder:date=1998-07-04 -o home.vhs.mp4
# a GIF that loops
ffman convert -i trip.mp4 -w 480 --loop -o trip.gif
```

## What a conversion keeps

Every stream an input carries is kept where the output holds it, and named
where it does not (`ffman: ... left out`) -- never dropped without a word:

- subtitles, copied or turned into the output's own text (`mov_text` in MP4,
  WebVTT in WebM);
- tags and chapters (into Ogg and FLAC, as `CHAPTERxxx` comments);
- attachments into Matroska; elsewhere an attached cue, ffmetadata or Vorbis
  comments file is applied as `--metadata` would apply it;
- the cover, copied, or into Matroska attached as `cover.png` (`cover_land`
  when wider than tall).

The rules, each measured:
[`ffman-spec.md`](https://github.com/veramachine/ffsuite/blob/main/docs/ffman-spec.md) 3.12 to 3.15.

## More

- The command line's contract:
  [`ffman-spec.md`](https://github.com/veramachine/ffsuite/blob/main/docs/ffman-spec.md).
- Every decision, with its evidence and the module it lives in:
  [`docs/decisions.md`](https://github.com/veramachine/ffsuite/blob/main/docs/decisions.md).
- Changes to behaviour:
  [`CHANGELOG.md`](https://github.com/veramachine/ffsuite/blob/main/packages/ffman/CHANGELOG.md).
- Working on it: [`AGENTS.md`](https://github.com/veramachine/ffsuite/blob/main/AGENTS.md).

It replaced a bash ffman (retired in phase 5 of
[`ffman-python.md`](https://github.com/veramachine/ffsuite/blob/main/docs/ffman-python.md)),
after equalling it on every invocation of the bash suites.

## Licence

Part of [ffsuite](https://github.com/veramachine/ffsuite), beside its libraries ffmeta and
subverter. Licensed under either of
[MIT](https://github.com/veramachine/ffsuite/blob/main/packages/ffman/LICENSE-MIT)
or [Apache-2.0](https://github.com/veramachine/ffsuite/blob/main/packages/ffman/LICENSE-APACHE),
at your option; its fonts, IBM Plex, under the
[OFL](https://github.com/veramachine/ffsuite/blob/main/packages/ffman/src/ffman/fonts/OFL.txt).

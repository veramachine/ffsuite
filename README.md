# ffsuite

ffman, a command-line media converter on ffmpeg -- resize, effects, burned subtitles, encoding,
metadata files; lossless by default -- and the two Python libraries it is built from: ffmeta
for metadata files and subverter for subtitles and transcripts. A uv workspace of three packages,
each its own pyproject.toml, published on its own:

| Package                                     | What                                                                                                                 |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [`ffman`](packages/ffman/README.md)         | the command line: resize, effects, subtitles, encoding, metadata files -- lossless by default                        |
| [`ffmeta`](packages/ffmeta/README.md)       | metadata files -- ffmetadata, Vorbis comments, cue sheets -- read, written and converted                             |
| [`subverter`](packages/subverter/README.md) | subtitles and transcripts -- SubRip, WebVTT, LRC, CSV, TSV, whisper-cli's and WhisperX's JSON -- read into one model |

## Install

From PyPI, on Python 3.13 or later. ffman runs ffmpeg, which it needs on `PATH` (the other tools:
[what it needs](packages/ffman/README.md#what-it-needs)); the libraries need the standard library
alone:

```sh
uv tool install ffman          # or: pipx install ffman
pip install ffmeta subverter
```

From the flake, ffman with every tool it runs, on Linux (x86_64, aarch64) or macOS (Apple
silicon):

```sh
nix run github:veramachine/ffsuite -- convert -i in.mp4 -w 1280   # in.ffman.mp4, 1280 wide
```

ffman is also a container image, `ghcr.io/veramachine/ffman`, and runs on Windows through WSL:
[ffman's README](packages/ffman/README.md#running-it).

Working on them: [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md). Licensed under
either of [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option; ffman's fonts, IBM
Plex, under the [OFL](packages/ffman/src/ffman/fonts/OFL.txt).

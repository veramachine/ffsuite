# ffsuite

Media tools on ffmpeg, and the libraries they are built from. A uv workspace of three
packages, each its own pyproject.toml, published on its own:

| Package                                     | What                                                                                                                 |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [`ffman`](packages/ffman/README.md)         | the command line: resize, effects, subtitles, encoding, metadata files -- lossless by default                        |
| [`ffmeta`](packages/ffmeta/README.md)       | metadata files -- ffmetadata, Vorbis comments, cue sheets -- read, written and converted                             |
| [`subverter`](packages/subverter/README.md) | subtitles and transcripts -- SubRip, WebVTT, LRC, CSV, TSV, whisper-cli's and WhisperX's JSON -- read into one model |

ffman, from the flake, on Linux (x86_64, aarch64) or macOS (Apple silicon: not yet tested) -- the
tools it runs come with it (a container image too, and Windows through WSL: ffman's README):

```sh
nix run github:veramachine/ffsuite -- convert -i in.mp4 -w 1280
```

Working on them: [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`AGENTS.md`](AGENTS.md). Licensed under
either of [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option; ffman's fonts, IBM
Plex, under the [OFL](packages/ffman/src/ffman/fonts/OFL.txt).

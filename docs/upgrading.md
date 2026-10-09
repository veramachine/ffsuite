# At a nixpkgs bump

ffman holds to behaviour of the tools nixpkgs pins -- whisper-cli's and WhisperX's outputs,
ffmpeg's filters and encoders, libass, mpv's defaults -- each read in its source or measured,
then held by the suite. At every bump of `flake.lock`, and of nixos-config's channel (its
input follows it), re-check these, then run the checks: `nix flake check` (the suite, the
matrix, the installed binary, on each Python). Moved from nixos-config's channel run-book (its
11.49); nixos-config's own couplings stay there.

1. whisper-cli still prints a leading space and has no option to drop it, `-ojf` still turns on
   token timestamps, and `t_dtw` is still in 10 ms units (`cli.cpp`, `whisper.cpp`).
2. the `-ojf` layout (`transcription[].tokens[]` with `offsets` and `t_dtw`, `[_…]` special
   tokens) and the CSV header with an optional `speaker` column.
3. SVT-AV1 still lacks 4:4:4 (else AVIF could move to it) and libaom `-crf 0` is still lossless.
4. `oxipng -o max` exists in the pinned oxipng (10.x).
5. `yuvj444p` is still accepted by the mjpeg encoder.
6. libass `fontsdir` still non-recursive, and the pinned IBM Plex Sans still ships `.otf`.
7. x264 still embeds its settings string, which the suite reads.
8. colour tags: 8.1.2 ignores `-color_primaries`/`-color_trc` as encoder options, so `convert`
   tags frames with `setparams` -- keep that even if a release honours the options again, since
   it works on both.
9. `-enc_time_base:v demux` and `-movflags negative_cts_offsets` still exist (the former needs
   ffmpeg >= 7), and ffprobe still reports rotation in `side_data_list[].rotation`.
10. `overlay`'s default format is still yuv420 (why the blur path sets `format=auto`).
11. a `-ojf` segment's token offsets still lie inside its own window (the DTW fallback relies on
    it), and `t_dtw` is still -1 without `--dtw`.
12. WhisperX is not pinned by this flake -- when its writers (`utils.py`: srt/vtt/tsv/json,
    `--highlight_words`) or alignment (`alignment.py`: omitted times, nearest interpolation)
    change, regenerate the `wx*` fixtures with its own writers.
13. whisper-cli JSON still names the language in `result.language` (the no-space-script rule
    reads it).
14. mpv's sub_style_conf defaults (sub/osd.c) and its 720-line canvas -- ffman's plain style
    copies them -- and cropdetect's log line (y1/y2) and options round/reset/skip.
15. gblur's sigma is still the Gaussian's standard deviation in pixels and steps still runs 1-6
    (the blur and the bar blur use steps=6, halation and VHS 3; `ffmpeg -h filter=gblur`).
16. `-noaccurate_seek` still starts at the keyframe before -ss, and a raw stream still yields no
    frames after `-ss 0` (`subs/layout.py` samples it unseeked).
17. palettegen still reserves a transparency slot by default; negate is still 255-v; gblur still
    one sigma for all planes; mergeplanes still needs equal SARs; -enc_time_base demux still
    fails on split-and-merged graphs.
18. noise's uniform mode still adds RAND_N(s) - s/2 (odd s unbiased), chromashift still reads
    y - offset (positive: down), and swscale still dithers when it reduces bit depth (why bar
    blur blurs 8-bit sources at 8 bits).
19. geq still clamps float output to [0, 1] (the CRT masks are stored / K); a looped generated
    source blended in still keeps frames and timestamps; CRT-Royale's beam defaults still
    0.02-0.3, power 1/3, geometry flat.
20. MAX_AUTO_THREADS still 16 in libavcodec and libavutil (else `media/run.py`'s threshold
    moves); ffv1enc still starts at 2x2 slices; vp9_set_row_mt still needs GOOD in one pass.
21. gblur's steps still 1-6 (6 the most accurate); lutrgb still takes 16-bit val
    (`graph/light.py`); color_transfer still 'iec61966-2-1' for sRGB in ffprobe.
22. the dependency groups' pins and uv's `required-version` (`pyproject.toml`) set to the new
    nixpkgs' versions, then `uv lock`: the `pins` check names each one left behind. A new
    pytest's strictness options are on (`strict = true`): a new failure, even before
    collection, may be one.
23. the image, which no check builds (the FDK ffmpeg, from source): `nix build .#image.stream &&
    ./result | docker load`, then a conversion in it (ffman's README).

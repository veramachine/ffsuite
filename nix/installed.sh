# shellcheck shell=bash
# The installed ffman, as a user runs it: its wrapper alone gives its PATH
# (env -i: nothing of the builder's). One job per runtime tool -- an effect into Matroska, a burn
# (the bundled font), YouTube with forced normalisation (ffmpeg-normalize, env, the presets the
# package carries), a PNG, a JPEG, a GIF (oxipng, jpegoptim, gifsicle), a FLAC's CUESHEET block
# (metaflac) -- each output probed; the user's presets over ffman's; the optimisers optional. The
# suite cannot see this: it calls main() in-process. Given: $ffman, the wrapped binary; $lean,
# the same wrapped over the runtime less the optimisers. Run from nix/checks.nix.
set -euo pipefail
: "${ffman:?the wrapped ffman}" "${lean:?the wrapper without the optimisers}"

gen() { ffmpeg -v error -y "$@"; }
run() { env -i HOME="$TMPDIR" TMPDIR="$TMPDIR" "$ffman" "$@"; }
fail() {
  echo "$1" >&2
  exit 1
}

gen -f lavfi -i testsrc2=s=320x180:r=25:d=1 -f lavfi -i sine=d=1:r=48000 -ac 2 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac v.mp4
gen -f lavfi -i testsrc2=s=320x180 -frames:v 1 i.png
printf '1\n00:00:00,100 --> 00:00:00,900\nhello\n' >s.srt

run --version
run convert -i v.mp4 -w 160 --vfx invert -o fx.mkv
run convert -i v.mp4 --burn-subs s.srt -o burnt.mp4
run convert -i v.mp4 -p youtube --normalize -o yt.mp4
run convert -i i.png -w 160 -o small.png
run convert -i i.png -w 160 -o small.jpg
run convert -i v.mp4 -w 160 -o loop.gif

# metaflac on the wrapper's PATH: a source FLAC's CUESHEET block carried
gen -f lavfi -i sine=d=1:r=44100 -ac 2 -sample_fmt s16 cd.flac
printf 'FILE "cd.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n' >cd.cue
metaflac --import-cuesheet-from=cd.cue cd.flac
run convert -i cd.flac -o carried.flac --audio-codec flac
# captured, not piped to grep -q: under pipefail, a writer cut off by grep's early exit fails
sheet=$(metaflac --export-cuesheet-to=- carried.flac) || fail "carried.flac: no CUESHEET block"
[[ $sheet == *"INDEX 01"* ]] || fail "carried.flac: its CUESHEET block has no track"

# FFMAN_NORMALIZE_HOME, set: the user's folder used, not the package's -- an empty one refused
mkdir mine
if env -i HOME="$TMPDIR" TMPDIR="$TMPDIR" FFMAN_NORMALIZE_HOME="$PWD/mine" "$ffman" \
  convert -i v.mp4 -p youtube --normalize -o mine.mp4 2>mine.err; then
  fail "FFMAN_NORMALIZE_HOME set: the package's presets used, not the user's"
fi
refused="^ffman: error: missing ffmpeg-normalize preset youtube-aac[a-z-]* in $PWD/mine\$"
grep -q "$refused" mine.err || fail "FFMAN_NORMALIZE_HOME set: $(cat mine.err)"

# without the optimisers: each output written unoptimised, and said so
run_lean() { env -i HOME="$TMPDIR" TMPDIR="$TMPDIR" "$lean" "$@" 2>>lean.err; }
run_lean convert -i i.png -w 160 -o lean.png
run_lean convert -i i.png -w 160 -o lean.jpg
run_lean convert -i v.mp4 -w 160 -o lean.gif
for said in "oxipng not found: the .png" "jpegoptim not found: the .jpg" \
  "gifsicle not found: the .gif"; do
  grep -qF "$said written unoptimised" lean.err || fail "no note: $said written unoptimised"
done

for f in fx.mkv burnt.mp4 yt.mp4 small.png small.jpg loop.gif lean.png lean.jpg lean.gif; do
  kind=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of csv=p=0 "$f")
  [[ $kind == video ]] || fail "$f: no picture"
done

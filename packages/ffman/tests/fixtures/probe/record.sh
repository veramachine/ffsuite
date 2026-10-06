#!/usr/bin/env bash
# Re-records the ffprobe JSON these tests read: ffmpeg/ffprobe 8.1.2 (the pin),
# the command bash's probe ran (ffprobe -v error -show_streams -show_format -of
# json -- file:F). Each file stands for a case the probe must get right.
set -euo pipefail
here=$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")") # before the cd: the name may be relative
[[ $(ffprobe -version | head -1) == "ffprobe version 8.1.2 "* ]] || { echo "record.sh: needs ffprobe 8.1.2 (the pin) first on PATH" >&2; exit 1; }
work=$(mktemp -d) && trap 'rm -rf -- "$work"' EXIT && cd "$work"
F=(ffmpeg -v error -y)
"${F[@]}" -f lavfi -i "testsrc2=s=640x360:r=25:d=1" -f lavfi -i "sine=d=1:r=48000" -ac 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -metadata creation_time=2019-06-01T12:34:56.000000Z h264_aac.mp4 # plain; a creation time
"${F[@]}" -display_rotation:v 90 -i h264_aac.mp4 -c copy rotated.mp4                                                # a display matrix
"${F[@]}" -f lavfi -i "testsrc2=s=720x480:r=30000/1001:d=1" -vf setsar=32/27 -c:v ffv1 anamorphic.mkv                 # SAR 32:27, NTSC rate
"${F[@]}" -f lavfi -i "color=c=red:s=64x64" -frames:v 1 cover.png
"${F[@]}" -f lavfi -i "sine=d=1:r=44100" -i cover.png -map 0 -map 1 -c:a aac -c:v png -disposition:v:0 attached_pic cover_art.m4a # cover art: no picture
printf '1\n00:00:00,000 --> 00:00:01,000\nHi\n' >s.srt && printf 'font' >f.ttf
"${F[@]}" -i h264_aac.mp4 -i s.srt -map 0 -map 1 -c copy -c:s srt -metadata:s:s:0 language=por -attach f.ttf -metadata:s:t mimetype=application/x-truetype-font subs_attach.mkv
# HDR10's tags set on the frames: ffmpeg 8.1.2's output -color_trc/-color_primaries did not reach libx265 here
"${F[@]}" -f lavfi -i "testsrc2=s=320x180:r=24:d=1" -vf "setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=tv,format=yuv420p10le" -c:v libx265 -x265-params log-level=none hdr10.mkv
"${F[@]}" -f lavfi -i "testsrc2=s=320x240:r=25:d=1" -vf setfield=tff -flags +ildct+ilme -c:v libx264 -pix_fmt yuv420p interlaced.mp4
"${F[@]}" -f lavfi -i "testsrc2=s=160x90" -frames:v 1 image.png
"${F[@]}" -f lavfi -i "testsrc2=s=160x90:r=10:d=1" anim.gif
for f in h264_aac.mp4 rotated.mp4 anamorphic.mkv cover_art.m4a subs_attach.mkv hdr10.mkv interlaced.mp4 image.png anim.gif; do
  ffprobe -v error -show_streams -show_format -of json -- "file:$f" >"$here/$f.json"
done

"""The outcome report's fixed corpus: deterministic sources, the fixture transcripts, the cases.

Built once per report, outside any commit's code, so two commits are measured
on the same inputs. Each source is there for a path it reaches; every source
but the stills and the raw stream carries one creation time, so the camcorder
never reads the clock. Each case is ffman's arguments under an id; a case meant
for a path is checked to reach it (coverage, measured when the corpus changes:
AGENTS.md).
"""

import shutil
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final

from tests.support.transcripts import HOSTILE

EVERYTHING: Final = "all.mkv"  # every kind of stream (6.6.5, proven): built last, by hand
FIXTURES: Final = Path(__file__).resolve().parent.parent / "fixtures" / "transcripts"
CREATED: Final = "2001-02-03T04:05:06Z"
# ffman's environment, inside the corpus (so canonical as $CORPUS/...): fonts are only
# text in its commands; the presets must exist, by the names plan.youtube_sound picks.
FONTS: Final = "fonts"
NORMALIZE: Final = "normalize"
PRESETS: Final = ("youtube-aac", "youtube-aac-native")

_LAVFI: Final = ("-f", "lavfi", "-i")
_PICTURE: Final = (*_LAVFI, "testsrc2=s=320x180:r=25:d=0.4")
_SOUND: Final = (*_LAVFI, "sine=d=0.4:r=48000", "-ac", "2")
_H264: Final = ("-c:v", "libx264", "-pix_fmt", "yuv420p")
_AAC: Final = ("-c:a", "aac")
# -threads 1: the encoders' output fixed; +bitexact: Matroska's UIDs, not random
_FIXED: Final = ("-threads", "1", "-fflags", "+bitexact")
_UNDATED: Final = (".png", ".jpg", ".gif", ".h264")  # no container date to set


def _colour(primaries: int, transfer: int, matrix: int) -> tuple[str, ...]:
    """H.273's codes into the H.264 stream itself (libx264 left them unwritten): ffprobe reads them."""
    vui = f"colour_primaries={primaries}:transfer_characteristics={transfer}:matrix_coefficients={matrix}"
    return ("-bsf:v", f"h264_metadata={vui}")


# name -> ffmpeg's arguments, inputs first (a source made from another names it)
SOURCES: Final[dict[str, tuple[str, ...]]] = {
    "v.mp4": (*_PICTURE, *_SOUND, *_H264, *_AAC),
    "mute.mp4": (*_PICTURE, *_H264),
    "v265.mp4": (
        "-i",
        "v.mp4",
        "-c:v",
        "libx265",
        "-x265-params",
        "log-level=error",
        "-c:a",
        "copy",
    ),
    "v9.webm": ("-i", "v.mp4", "-c:v", "libvpx-vp9", "-b:v", "500k", "-c:a", "libopus"),
    "cuts.mp4": (  # a scene cut at 1 s, for datamosh
        *(*_LAVFI, "testsrc2=s=320x180:r=25:d=1"),
        *(*_LAVFI, "smptehdbars=s=320x180:r=25:d=1"),
        *("-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", *_H264),
    ),
    "bars.mp4": (*_PICTURE, *_SOUND, "-vf", "pad=320:240:0:0", *_H264, *_AAC),  # a black bar
    "sar.mp4": (*_PICTURE, *_SOUND, "-vf", "setsar=4/3", *_H264, *_AAC),  # anamorphic
    "rot.mp4": ("-display_rotation", "90", "-i", "v.mp4", "-c", "copy"),
    "tracks.mkv": (
        "-i",
        "v.mp4",
        "-i",
        str(FIXTURES / "regular.srt"),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
    ),
    "hd.mp4": (*_LAVFI, "testsrc2=s=1920x1080:r=25:d=0.2", *_H264, "-preset", "ultrafast"),
    "m4v.avi": (*_PICTURE, "-c:v", "mpeg4"),  # a codec with no lossless encoder
    "v601.mp4": (*_PICTURE, *_H264, *_colour(6, 6, 6)),  # BT.601 (smpte170m) throughout
    "v2020.mp4": (*_PICTURE, *_H264, *_colour(9, 1, 9)),  # BT.2020 primaries and matrix, SDR
    "hdr.mp4": (*_PICTURE, *_H264, *_colour(9, 16, 9)),  # BT.2020, PQ (smpte2084)
    "rgb.mkv": (*_PICTURE, "-c:v", "ffv1", "-pix_fmt", "gbrp"),
    "v60.mp4": (*_LAVFI, "testsrc2=s=320x180:r=60:d=0.4", *_H264),
    "ntsc.mp4": (*_LAVFI, "testsrc2=s=320x180:r=30000/1001:d=0.4", *_H264),
    "inter.mp4": (*_PICTURE, *_H264, "-flags", "+ildct+ilme", "-top", "1"),
    "v.h264": (
        "-i",
        "v.mp4",
        "-map",
        "0:v",
        "-c",
        "copy",
        "-bsf:v",
        "h264_mp4toannexb",
    ),  # no duration
    "p.png": (*_PICTURE, "-frames:v", "1"),
    "p.jpg": (*_PICTURE, "-frames:v", "1"),
    "g.gif": _PICTURE,
    "a.m4a": (*_SOUND, *_AAC),
    # 48 240 samples: ffprobe's "1.005000" s -- 1004 ms through a float, 1005 exactly
    "d1005.mka": (
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:r=48000",
        "-af",
        "atrim=end_sample=48240",
        "-c:a",
        "flac",
    ),
}
# whisper-cli -ojf with a token whose text is a number: jq refused it (ingest's last guard)
_UNREADABLE_OJF: Final = (
    '{"transcription": [{"offsets": {"from": 0, "to": 1000}, "text": " hi",'
    ' "tokens": [{"text": 5, "offsets": {"from": 0, "to": 500}}]}]}'
)
_ASS: Final = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, \
BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,IBM Plex Sans,57,&H00FFFFFF,&H00000000,&H00000000,0,0,1,2,0,2,40,40,54

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.30,Default,,0,0,0,,an ASS line
"""


def build(corpus: Path, ffmpeg: str) -> None:
    """Make the sources, copy the transcripts, add the hand-made files."""
    corpus.mkdir(parents=True)
    for name, args in SOURCES.items():
        dated = () if name.endswith(_UNDATED) else ("-metadata", f"creation_time={CREATED}")
        argv = [ffmpeg, "-v", "error", "-nostdin", "-y", *args, *_FIXED, *dated, name]
        _ = subprocess.run(argv, cwd=corpus, check=True, capture_output=True)  # noqa: S603 -- ffmpeg
    for transcript in sorted(FIXTURES.iterdir()):
        _ = shutil.copy(transcript, corpus / transcript.name)
    (corpus / "hostile").mkdir()
    for name, text in HOSTILE.items():
        _ = (corpus / "hostile" / name).write_text(text)
    _ = shutil.copy(corpus / "v.mp4", corpus / "noext")
    _ = (corpus / "t.ass").write_text(_ASS)
    _ = (corpus / "badtoken.json").write_text(_UNREADABLE_OJF)
    _ = (corpus / "bad.mp4").write_text("not media\n")
    _ = shutil.copy(corpus / "v.mp4", corpus / "exists.mp4")
    for name, text in METADATA.items():  # spec 3.9's files: each format, and what each refuses
        _ = (corpus / name).write_bytes(text)
    (corpus / FONTS).mkdir()
    # ffman's own fonts (6.7.3), so each burn measures its lines as it does: on every machine
    for font in Path(str(resources.files("ffman") / "fonts")).glob("*.otf"):  # every one it carries
        _ = shutil.copy(font, corpus / FONTS / font.name)
    presets = corpus / NORMALIZE / "ffmpeg-normalize" / "presets"
    presets.mkdir(parents=True)
    for preset in PRESETS:
        _ = (presets / f"{preset}.json").write_text("{}\n")
    # a PATH holding ffmpeg and ffprobe alone: the optimisers optional (6.7.2)
    found = {
        name: shutil.which(name) for name in ("ffprobe", "nproc")
    }  # nproc: the optimisers alone missing
    absent = [name for name, path in found.items() if path is None]
    if absent:
        msg = f"not on PATH, the corpus needs them: {', '.join(absent)}"
        raise RuntimeError(msg)
    (corpus / "no-optimisers").mkdir()
    for name, target in (("ffmpeg", ffmpeg), *found.items()):
        (corpus / "no-optimisers" / name).symlink_to(str(target))
    # every kind of stream (6.6.5, proven): tracks.mkv's, a cue and a font attached, a cover,
    # custom tags -- built last, its attachments METADATA's files
    _ = (corpus / "f.ttf").write_bytes(b"\x00\x01font")
    attach = ["-attach", "album.cue", "-metadata:s:t:0", "mimetype=text/plain"]
    attach += ["-attach", "f.ttf", "-metadata:s:t:1", "mimetype=font/ttf"]
    attach += [
        "-attach",
        "p.png",
        "-metadata:s:t:2",
        "mimetype=image/png",
        "-metadata:s:t:2",
        "filename=cover.png",
    ]
    given = [
        "-i",
        "tracks.mkv",
        "-i",
        "custom.ffmeta",
        "-map",
        "0",
        "-map_metadata",
        "1",
        "-c",
        "copy",
    ]
    argv = [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-y",
        *given,
        *attach,
        *_FIXED,
        "-metadata",
        f"creation_time={CREATED}",
        EVERYTHING,
    ]
    _ = subprocess.run(argv, cwd=corpus, check=True, capture_output=True)  # noqa: S603 -- ffmpeg


_SHEET: Final = b'REM GENRE "Ska"\nTITLE "Album"\nFILE "album.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Two"\n    SONGWRITER "S"\n    INDEX 00 00:58:00\n    INDEX 01 01:00:00\n'
_FFMETA: Final = b";FFMETADATA1\nalbum=Album\nartist=A\\;B\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=60500\ntitle=One\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=60500\nEND=90000\ntitle=Two\n"
METADATA: Final[dict[str, bytes]] = {
    "album.cue": _SHEET,
    "album.ffmeta": _FFMETA,
    "custom.ffmeta": b";FFMETADATA1\ntitle=T\nMOOD=calm\n",  # a key iTunes' atoms hold not
    "ffm.txt": _FFMETA,
    "comments.txt": b"ALBUM=Album\nARTIST=A\nARTIST=B\nCHAPTER000=00:00:00.000\nCHAPTER000NAME=One\n",
    "empty.txt": b"",
    "latin1.cue": b'TITLE "Caf\xe9"\nFILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n',
    "bad.cue": b'FILE "a" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:61:00\n',
    "two.cue": b'FILE "1" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "2" WAVE\n  TRACK 02 AUDIO\n    INDEX 01 00:00:00\n',
}


@dataclass(frozen=True, slots=True)
class Case:
    """One invocation: a stable id, ffman's arguments (the command first), its own environment.

    ``env`` overrides the report's, ``{corpus}`` in a value naming the corpus.
    """

    id: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


def _c(case_id: str, *args: str) -> Case:
    return Case(case_id, args)


def _env(case_id: str, env: dict[str, str], *args: str) -> Case:
    return Case(case_id, ("convert", "--dry-run", *args), tuple(sorted(env.items())))


def _conv(case_id: str, *args: str) -> Case:
    return Case(case_id, ("convert", "--dry-run", *args))


_EFFECTS: Final = (
    "blur", "pixelate", "invert", "chromatic-aberration", "halation", "vhs", "dither", "crt",
)  # fmt: skip
_VALUED: Final = (("blur", "3"), ("pixelate", "8"), ("chromatic-aberration", "4"), ("dither", "8"))
_VCODECS: Final = ("h264", "hevc", "vp9", "av1", "ffv1")
_ACODECS: Final = ("copy", "none", "flac", "aac", "opus", "mp3", "vorbis", "alac", "pcm")
_MODES: Final = (
    ("plain", None), ("word", None), ("word-highlight", "plain"), ("word-highlight", "pop"),
    ("chunk-word", "plain"), ("chunk-word", "pop"),
)  # fmt: skip
_WORDED: Final = ("words.srt", "wx.json", "words.ojf.json", "wx-highlight.srt", "wx.tsv")
_CAM: Final = ("-i", "v.mp4", "--vfx")
_SRT: Final = ("-i", "v.mp4", "--burn-subs", "regular.srt")
_YT: Final = ("-p", "youtube", "-o", "y.mp4")


def _cli() -> list[Case]:
    return [
        _c("cli/help", "--help"),
        _c("cli/convert-help", "convert", "--help"),
        _c("cli/effects", "effects"),
        _c("cli/effects-blur", "effects", "blur"),
        _c("cli/effects-unknown", "effects", "sepia"),
        _conv("meta/cue-to-vorbis", "-i", "album.cue", "-o", "o.txt", "-p", "vorbiscomment"),
        _conv("meta/cue-to-ffmeta", "-i", "album.cue", "-o", "o.ffmeta"),
        _conv("meta/ffmeta-to-cue", "-i", "album.ffmeta", "-o", "o.cue"),
        _conv("meta/txt-ffmetadata-to-cue", "-i", "ffm.txt", "-o", "o.cue"),
        _conv("meta/txt-vorbis-to-ffmeta", "-i", "comments.txt", "-o", "o.ffmeta"),
        _conv("meta/media-to-cue", "-i", "v.mp4", "-o", "o.cue"),
        _conv("meta/default-rewritten", "-i", "album.cue"),
        _conv("meta/refused-media-out", "-i", "album.cue", "-o", "o.mp4"),
        _conv("meta/refused-picture", "-i", "album.cue", "-o", "o.txt", "-w", "100"),
        _conv("meta/refused-preset-cue", "-i", "album.cue", "-o", "o.cue", "-p", "vorbiscomment"),
        _conv("meta/refused-preset-media", "-i", "v.mp4", "-w", "100", "-p", "ffmetadata"),
        _conv("meta/refused-not-utf8", "-i", "latin1.cue", "-o", "o.txt"),
        _conv("meta/refused-line", "-i", "bad.cue", "-o", "o.txt"),
        _conv("meta/refused-two-files", "-i", "two.cue", "-o", "o.txt"),
        _conv("meta/refused-empty", "-i", "empty.txt", "-o", "o.txt", "-p", "vorbiscomment"),
        _c("cli/meta-help", "meta", "--help"),
        _c(
            "meta/new-vorbis",
            "meta",
            "--dry-run",
            "-o",
            "n.txt",
            "-p",
            "vorbiscomment",
            "--set",
            "title=T",
            "--add",
            "artist=A",
            "--add",
            "artist=B",
        ),
        _c(
            "meta/edit-cue",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "e.cue",
            "--set",
            "genre=Alt Rock",
            "--set",
            "album=LP",
        ),
        _c(
            "meta/unset-before-converting",
            "meta",
            "--dry-run",
            "-i",
            "comments.txt",
            "-o",
            "e.ffmeta",
            "--unset",
            "artist",
        ),
        _c(
            "meta/refused-cue-field",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "e.cue",
            "--set",
            "artist=X",
        ),
        _c(
            "meta/refused-contradiction",
            "meta",
            "--dry-run",
            "-o",
            "n.txt",
            "--set",
            "a=1",
            "--unset",
            "a",
        ),
        _c("meta/refused-no-output", "meta", "--dry-run", "--set", "a=1"),
        _c(
            "meta/chapters-vorbis",
            "meta",
            "--dry-run",
            "-o",
            "c.txt",
            "-p",
            "vorbiscomment",
            "--chapter",
            "1:30.5=Verse",
            "--chapter",
            "0..60=Intro",
        ),
        _c(
            "meta/chapters-cue",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "c.cue",
            "--chapter",
            "1:20=Mid",
            "--retitle",
            "2=Second",
            "--drop-chapter",
            "1",
        ),
        _c(
            "meta/refused-chapter-inside",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "c.cue",
            "--chapter",
            "59",
        ),
        _c("meta/refused-time", "meta", "--dry-run", "-o", "c.txt", "--chapter", "01:02:03:04"),
        _c(
            "meta/cue-own",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "o.cue",
            "--flags",
            "2=PRE",
            "--pregap",
            "2=0:59",
            "--file",
            "a.flac",
        ),
        _c(
            "meta/refused-flags-input",
            "meta",
            "--dry-run",
            "-i",
            "album.ffmeta",
            "-o",
            "o.cue",
            "--flags",
            "1=PRE",
        ),
        _c(
            "meta/refused-catalog",
            "meta",
            "--dry-run",
            "-i",
            "album.cue",
            "-o",
            "o.cue",
            "--set",
            "barcode=123",
        ),
        _c("meta/stdout", "meta", "-i", "album.cue", "-o", "-"),  # no file written: no --dry-run
        _c("meta/stdout-vorbis", "meta", "-i", "album.cue", "-o", "-", "-p", "vorbiscomment"),
        _c(
            "convert/metadata-alone",
            "convert",
            "--dry-run",
            "-i",
            "tracks.mkv",
            "-o",
            "o.mkv",
            "--metadata",
            "album.cue",
        ),
        _c(
            "convert/metadata-resize",
            "convert",
            "--dry-run",
            "-i",
            "v.mp4",
            "-o",
            "o.mp4",
            "-w",
            "320",
            "--metadata",
            "album.ffmeta",
        ),
        _c(
            "convert/refused-metadata-container",
            "convert",
            "--dry-run",
            "-i",
            "tracks.mkv",
            "-o",
            "o.mp4",
            "--metadata",
            "album.ffmeta",
        ),
        _c("convert/remux-container", "convert", "--dry-run", "-i", "v9.webm", "-o", "o.mp4"),
        _c("convert/remux-codec", "convert", "--dry-run", "-i", "v.mp4", "--audio-codec", "flac"),
        _c("convert/refused-remux-held", "convert", "--dry-run", "-i", "v.mp4", "-o", "o.webm"),
        _c("convert/subtitles-to-mp4", "convert", "--dry-run", "-i", "tracks.mkv", "-o", "o.mp4"),
        _c(
            "convert/chapters-opus",
            "convert",
            "--dry-run",
            "-i",
            "a.m4a",
            "-o",
            "o.opus",
            "--audio-codec",
            "opus",
            "--metadata",
            "album.ffmeta",
        ),
        _c(
            "convert/tags-mp4",
            "convert",
            "--dry-run",
            "-i",
            "a.m4a",
            "-o",
            "o.mp4",
            "--metadata",
            "custom.ffmeta",
        ),
        _c("cli/none"),
        _c("cli/unknown-command", "frobnicate"),
        _c("cli/migrated-command", "resize"),
        _c("cli/version", "--version"),
        _c("cli/effects-help", "effects", "--help"),
        _c("cli/effects-extra", "effects", "blur", "crt"),
        _conv("cli/migrated-flag", "-i", "v.mp4", "--blur"),
        _conv("cli/empty-equals", "-i", "v.mp4", "-w", "160", "--output="),
        _conv("cli/attached", "-i", "v.mp4", "-w160"),
        _conv("cli/missing-value", "-i", "v.mp4", "-w"),
        _conv("cli/equals-value", "-i", "v.mp4", "--width=160"),
        _conv("cli/empty-value", "-i", "v.mp4", "-w", "160", "-o", ""),
        _conv("cli/flag-equals", "-i", "v.mp4", "-w", "160", "--overwrite=yes"),
        _c("cli/unknown-option", "convert", "-i", "v.mp4", "--frobnicate"),
        _c("cli/no-input", "convert", "--dry-run"),
        _conv("cli/nothing-to-do", "-i", "v.mp4"),
    ]


def _resize() -> list[Case]:
    w = ("-i", "v.mp4", "-w", "160")
    cases = [
        _conv("resize/w", *w),
        _conv("resize/h", "-i", "v.mp4", "-H", "90"),
        _conv("resize/wh", "-i", "v.mp4", "-w", "160", "-H", "90"),
        _conv("resize/odd", "-i", "v.mp4", "-w", "161"),
        _conv("resize/a-fit", "-i", "v.mp4", "-w", "200", "-a", "1:1"),
        _conv("resize/a-cover", "-i", "v.mp4", "-w", "200", "-a", "1:1", "-r", "cover"),
        _conv("resize/a-stretch", "-i", "v.mp4", "-w", "200", "-a", "1:1", "-r", "stretch"),
        _conv("resize/h-aspect", "-i", "v.mp4", "-H", "90", "-a", "1:1"),
        _conv("resize/bblur-auto", "-i", "v.mp4", "-w", "108", "-a", "9:16", "-b"),
        _conv("resize/bblur-5", "-i", "v.mp4", "-w", "108", "-a", "9:16", "-b", "5"),
        _conv("resize/bblur-spelled", "-i", "v.mp4", "-w", "108", "-a", "9:16", "-b", "012.50"),
        _conv("resize/a-only", "-i", "v.mp4", "-a", "2.39:1"),
        _conv("resize/tiny", "-i", "v.mp4", "-w", "2", "-a", "100:1"),
        _conv("resize/png-unusable", "-i", "p.png", "-w", "1", "-a", "100:1"),
        _conv("resize/sar", "-i", "sar.mp4", "-w", "160"),
        _conv("resize/rot", "-i", "rot.mp4", "-w", "90"),
        _conv("resize/hevc", "-i", "v265.mp4", "-w", "160"),
        _conv("resize/vp9", "-i", "v9.webm", "-w", "160"),
        _conv("resize/png", "-i", "p.png", "-w", "100"),
        _conv("resize/jpg", "-i", "p.jpg", "-w", "100", "-o", "small.jpg"),
        _conv("resize/gif-in", "-i", "g.gif", "-w", "100"),
        _conv("resize/mute", "-i", "mute.mp4", "-w", "160"),
        _conv("resize/tracks", "-i", "tracks.mkv", "-w", "160"),
        _conv("resize/tracks-webm", "-i", "tracks.mkv", "-w", "160", "-o", "x.webm"),
        _conv("resize/no-duration", "-i", "v.h264", "-w", "160", "-o", "x.mp4"),
        _conv("resize/in-place", *w, "--in-place"),
        _conv("resize/exists", *w, "-o", "exists.mp4"),
        _conv("resize/exists-y", *w, "-o", "exists.mp4", "-y"),
        _conv("resize/to-mkv", *w, "-o", "x.mkv"),
        _conv("resize/to-webm", *w, "-o", "x.webm"),
        _conv("resize/to-mov", *w, "-o", "x.mov"),
        _conv("resize/video-to-png", *w, "-o", "x.png"),
        _conv("resize/png-to-mp4", "-i", "p.png", "-w", "100", "-o", "x.mp4"),
        _conv(
            "encode/ffv1-hd", "-i", "hd.mp4", "-w", "1280", "--video-codec", "ffv1", "-o", "x.mkv"
        ),
        _conv("encode/no-lossless", "-i", "m4v.avi", "-w", "160"),
        _conv("encode/rgb", "-i", "rgb.mkv", "-w", "160"),
    ]
    cases += [_conv(f"encode/v-{c}", *w, "--video-codec", c, "-o", f"x-{c}.mkv") for c in _VCODECS]
    cases += [_conv(f"encode/a-{c}", *w, "--audio-codec", c, "-o", f"x-{c}.mkv") for c in _ACODECS]
    return cases


def _effects() -> list[Case]:
    cases = [_conv(f"vfx/{e}", "-i", "v.mp4", "--vfx", e) for e in _EFFECTS]
    cases += [_conv(f"vfx/{e}-png", "-i", "p.png", "--vfx", e) for e in _EFFECTS]
    cases += [_conv(f"vfx/{e}-sar", "-i", "sar.mp4", "--vfx", e) for e in _EFFECTS]
    cases += [_conv(f"vfx/{e}-{v}", "-i", "v.mp4", "--vfx", f"{e}:{v}") for e, v in _VALUED]
    return [
        *cases,
        _conv("vfx/vhs-hd", "-i", "hd.mp4", "--vfx", "vhs"),
        _conv("vfx/crt-hd", "-i", "hd.mp4", "--vfx", "crt"),
        _conv("vfx/datamosh", "-i", "cuts.mp4", "--vfx", "datamosh"),
        _conv("vfx/datamosh-heal", "-i", "cuts.mp4", "--vfx", "datamosh:0.5"),
        _conv("vfx/datamosh-png", "-i", "p.png", "--vfx", "datamosh"),
        _conv("vfx/datamosh-zero", "-i", "cuts.mp4", "--vfx", "datamosh:0"),
        _conv("vfx/camcorder", *_CAM, "camcorder"),
        _conv("vfx/camcorder-date", *_CAM, "camcorder:date=2020-01-02"),
        _conv(
            "vfx/camcorder-png", "-i", "p.png", "--vfx", "camcorder:date=2020-01-02,time=13:14:15"
        ),
        _conv("vfx/camcorder-positional", *_CAM, "camcorder:2020-01-02,13:14:15"),
        _conv("vfx/camcorder-unnamed", *_CAM, "camcorder:2020-01-02"),
        _conv("vfx/camcorder-unknown", *_CAM, "camcorder:zone=1"),
        _conv("vfx/camcorder-repeat", *_CAM, "camcorder:date=2020-01-02,date=2020-01-03"),
        _conv("vfx/camcorder-bad-date", *_CAM, "camcorder:date=2020-13-40"),
        _conv("vfx/camcorder-bad-time", *_CAM, "camcorder:time=25:00:00"),
        _conv("vfx/camcorder-mixed-date", *_CAM, "camcorder:date=2020-01:02"),
        _conv("vfx/chain", "-i", "v.mp4", *[a for e in _EFFECTS for a in ("--vfx", e)]),
        _conv("vfx/with-resize", "-i", "v.mp4", "-w", "160", "--vfx", "vhs", "--vfx", "crt"),
        _conv("vfx/ca-resized", "-i", "v.mp4", "-w", "160", "--vfx", "chromatic-aberration"),
        _conv("vfx/ca-sar-resized", "-i", "sar.mp4", "-w", "160", "--vfx", "chromatic-aberration"),
        _conv("vfx/to-gif", "-i", "v.mp4", "--vfx", "dither", "-o", "x.gif"),
        _conv("vfx/unknown", "-i", "v.mp4", "--vfx", "sepia"),
        _conv("vfx/bad-value", "-i", "v.mp4", "--vfx", "blur:0"),
        _conv("vfx/blur-abc", "-i", "v.mp4", "--vfx", "blur:abc"),
        _conv("vfx/blur-two-values", "-i", "v.mp4", "--vfx", "blur:3,4"),
        _conv("vfx/pixelate-1", "-i", "v.mp4", "--vfx", "pixelate:1"),
        _conv("vfx/dither-300", "-i", "v.mp4", "--vfx", "dither:300"),
        _conv("vfx/twice", "-i", "v.mp4", "--vfx", "blur", "--vfx", "blur"),
        _conv("vfx/no-value", "-i", "v.mp4", "--vfx", "invert:3"),
    ]


def _burn() -> list[Case]:
    transcripts = sorted(p.name for p in FIXTURES.iterdir())
    burn = ("-i", "v.mp4", "--burn-subs")
    cases = [_conv(f"burn/{t}", *burn, t) for t in transcripts]
    cases += [
        _conv(f"burn/chunk-word/{t}", *burn, t, "--overlay-mode", "chunk-word") for t in transcripts
    ]
    cases += [_conv(f"burn/hostile/{h}", *burn, f"hostile/{h}") for h in sorted(HOSTILE)]
    for t in _WORDED:
        for mode, light in _MODES:
            extra = ("--highlight-mode", light) if light else ()
            mode_id = f"burn/{mode}-{light or 'none'}/{t}"
            cases.append(_conv(mode_id, *burn, t, "--overlay-mode", mode, *extra))
    bars = ("-i", "bars.mp4", "--burn-subs")
    chunk_pop = ("--overlay-mode", "chunk-word", "--highlight-mode", "pop")
    return [
        *cases,
        _conv("burn/ass", *burn, "t.ass"),
        _conv("burn/ass-word", *burn, "t.ass", "--overlay-mode", "word"),
        _conv("burn/bar", *bars, "regular.srt"),
        _conv(
            "burn/bblur-boxed", *bars, "regular.srt", "--bblur", "-a", "9:16"
        ),  # its own bar, and the fit's
        _conv("burn/bar-invert", *bars, "regular.srt", "--vfx", "invert"),  # read before the effect
        _conv(
            "burn/bblur-bar", *burn, "regular.srt", "--bblur", "-a", "9:16"
        ),  # the plan's, blurred
        _conv("burn/bar-chunk-pop", *bars, "words.srt", *chunk_pop),
        _conv("burn/chunk-pop-ja", *burn, "cli-ja.json", *chunk_pop),  # abutting words: unscaled
        _conv("burn/bar-margin", *bars, "regular.srt", "--margin-bottom", "8%"),
        _conv("burn/huge-bar", *bars, "regular.srt", "--font-size", "300"),
        _conv("burn/margin", *_SRT, "--margin-bottom", "0.1"),
        _conv("burn/margin-spelled", *_SRT, "--margin-bottom", "0.050"),
        _conv("burn/font-size", *_SRT, "--font-size", "40"),
        _conv("burn/font-size-spelled", *_SRT, "--font-size", "057.50"),  # printed as its value
        _conv("burn/font", *_SRT, "-f", "DejaVu Sans"),
        _conv("burn/huge-plain", *_SRT, "--font-size", "900"),
        _conv("burn/huge-plain-spelled", *_SRT, "--font-size", "0900.0"),  # the note: its value
        _conv(
            "burn/huge-chunk",
            *burn,
            "wx.json",
            "--overlay-mode",
            "chunk-word",
            "--font-size",
            "900",
        ),
        _conv("burn/resize-vfx", *_SRT, "-w", "160", "--vfx", "vhs"),
        _conv("burn/odd-width", *_SRT, "-w", "161"),
        _conv("burn/bblur", *_SRT, "-w", "108", "-a", "9:16", "-b"),
        _conv("burn/no-duration", "-i", "v.h264", "--burn-subs", "regular.srt", "-o", "x.mp4"),
        _conv("burn/to-png", *_SRT, "--vfx", "datamosh", "-o", "x.png"),
        _conv("burn/on-png", "-i", "p.png", "--burn-subs", "regular.srt"),
        _conv("burn/pop-plain-mode", *burn, "words.srt", "--highlight-mode", "pop"),
        _conv("burn/colorize", *burn, "wx.json", *chunk_pop, "--highlight-colorize", "#00FF00"),
        _conv("burn/colorize-name", *burn, "wx.json", *chunk_pop, "--highlight-colorize", "Teal"),
        _conv(
            "burn/colorize-rainbow", *burn, "wx.json", *chunk_pop, "--highlight-colorize", "rainbow"
        ),
        _conv(
            "burn/colorize-lsd",
            *burn,
            "words.srt",
            "--overlay-mode",
            "word-highlight",
            "--highlight-colorize",
            "lsd",
        ),
        _conv(
            "burn/colorize-iridescence",
            *burn,
            "wx.json",
            "--overlay-mode",
            "chunk-word",
            "--highlight-colorize",
            "Iridescence",
        ),
        _conv("burn/colorize-plain-mode", *burn, "words.srt", "--highlight-colorize", "#00FF00"),
        _conv(
            "burn/bad-colorize", *burn, "words.srt", *chunk_pop, "--highlight-colorize", "glitter"
        ),
        _conv("burn/font-color", *_SRT, "--font-color", "black"),
        _conv("burn/outline-color", *_SRT, "--font-color", "teal", "--outline-color", "red"),
        _conv("burn/font-highlight", *burn, "wx.json", *chunk_pop, "--font-color", "#1E3A8A"),
        _conv("burn/bad-font-color", *_SRT, "--font-color", "glitter"),
        _conv(
            "burn/rectangle",
            *burn,
            "wx.json",
            "--overlay-mode",
            "chunk-word",
            "--highlight-colorize",
            "rectangle",
        ),
        _conv(
            "burn/rectangle-pop", *burn, "wx.json", *chunk_pop, "--highlight-colorize", "rectangle"
        ),
        _conv(
            "burn/rectangle-word",
            *burn,
            "words.srt",
            "--overlay-mode",
            "word-highlight",
            "--highlight-colorize",
            "rectangle",
        ),
        _conv(
            "burn/rectangle-motion",
            *burn,
            "wx.json",
            *chunk_pop,
            "--highlight-colorize",
            "rectangle",
            "--font-color",
            "rainbow",
        ),
        _conv("burn/font-rainbow", *_SRT, "--font-color", "rainbow"),
        _conv("burn/outline-lsd", *burn, "wx.json", *chunk_pop, "--outline-color", "lsd"),
        _conv(
            "burn/font-motion-highlight", *burn, "wx.json", *chunk_pop, "--font-color", "iridescent"
        ),
        _conv("burn/bad-margin", *_SRT, "--margin-bottom", "2"),
        _conv("burn/bad-size", *_SRT, "--font-size", "x"),
        _conv("burn/font-comma", *_SRT, "-f", "A,B"),
        _conv("burn/missing", *burn, "nothing.srt"),
        _conv("burn/bad-token", *burn, "badtoken.json", "--overlay-mode", "chunk-word"),
    ]


def _attach() -> list[Case]:
    srt = ("-i", "v.mp4", "--add-subs", "regular.srt")
    formats = [*sorted(p.name for p in FIXTURES.iterdir()), "t.ass"]
    cases = [_conv(f"attach/{t}", "-i", "v.mp4", "--add-subs", t, "-o", "x.mkv") for t in formats]
    two = (*srt, "--language", "eng", "--add-subs", "wx.srt", "--language", "por", "-o", "x.mkv")
    return [
        *cases,
        _conv("attach/mp4", *srt),
        _conv("attach/webm", "-i", "v9.webm", "--add-subs", "regular.srt"),
        _conv("attach/webm-to-mp4", "-i", "v9.webm", "--add-subs", "regular.srt", "-o", "x.mp4"),
        _conv("attach/avi", *srt, "-o", "x.avi"),
        _conv("attach/language", *srt, "--language", "por", "-o", "x.mkv"),
        _conv("attach/bad-language", *srt, "--language", "english"),
        _conv("attach/two", *two),
        _conv("attach/onto-track", "-i", "tracks.mkv", "--add-subs", "wx.srt"),
        _conv("attach/language-alone", "-i", "v.mp4", "--language", "por"),
        # the SRT clip: the duration in whole ms, floored (bash's float made 1.005 s 1004)
        _conv("attach/clip", "-i", "d1005.mka", "--add-subs", "regular.srt", "-o", "clip.mka"),
    ]


def _youtube() -> list[Case]:
    sources = (
        ("v", "v.mp4"), ("vp9", "v9.webm"), ("mute", "mute.mp4"), ("sar", "sar.mp4"),
        ("png", "p.png"), ("audio", "a.m4a"), ("bt601", "v601.mp4"), ("bt2020", "v2020.mp4"),
        ("hdr", "hdr.mp4"), ("rgb", "rgb.mkv"), ("60fps", "v60.mp4"), ("ntsc", "ntsc.mp4"),
        ("interlaced", "inter.mp4"), ("no-duration", "v.h264"), ("hd", "hd.mp4"),
    )  # fmt: skip
    cases = [_conv(f"youtube/{n}", "-i", s, *_YT) for n, s in sources]
    return [
        *cases,
        _conv("youtube/yt", "-i", "v.mp4", "-p", "yt", "-o", "y.mp4"),
        _conv("youtube/subtitles", "-i", "tracks.mkv", "-p", "yt", "-o", "y.mp4"),  # carried (3.12)
        _conv("proven/mp4", "-i", "all.mkv", "-o", "all.mp4"),  # every kind: held, or noted
        _conv("proven/mov", "-i", "all.mkv", "-o", "all.mov"),
        _conv("proven/flac", "-i", "all.mkv", "-o", "all.flac", "--audio-codec", "flac"),
        _conv("proven/mkv", "-i", "all.mkv", "-o", "all2.mkv", "--audio-codec", "flac"),
        _conv("proven/webm-refused", "-i", "all.mkv", "-o", "all.webm"),
        _conv("youtube/normalize", "-i", "v.mp4", *_YT, "--normalize"),
        _conv("youtube/to-mkv", "-i", "v.mp4", "-p", "youtube", "-o", "y.mkv"),
    ]


def _gif() -> list[Case]:
    return [
        _conv("gif/once", "-i", "v.mp4", "-o", "x.gif"),
        _conv("gif/loop", "-i", "v.mp4", "--loop", "-o", "x.gif"),
        _conv("gif/loop-reverse", "-i", "v.mp4", "--loop-reverse", "-w", "160", "-o", "x.gif"),
        _conv("gif/loop-png", "-i", "p.png", "-w", "100", "--loop", "-o", "x.gif"),
        _conv("gif/loop-mp4", "-i", "v.mp4", "-w", "160", "--loop"),
    ]


def _refusals() -> list[Case]:
    w = ("-i", "v.mp4", "-w", "160")
    return [
        _conv("refuse/bad-width", "-i", "v.mp4", "-w", "abc"),
        _conv("refuse/zero-width", "-i", "v.mp4", "-w", "0"),
        _conv("refuse/bad-aspect", "-i", "v.mp4", "-a", "wide"),
        _conv("refuse/aspect-zero", "-i", "v.mp4", "-a", "0:1"),
        _conv("refuse/disagree", "-i", "v.mp4", "-w", "100", "-H", "100", "-a", "16:9"),
        _conv("refuse/bad-mode", *_SRT, "--overlay-mode", "karaoke"),
        _conv("refuse/mode-alone", *w, "--overlay-mode", "word"),
        _conv("refuse/no-file", "-i", "nothing.mp4", "-w", "160"),
        _conv("refuse/not-media", "-i", "bad.mp4", "-w", "160"),
        _conv("refuse/audio-only", "-i", "a.m4a", "-w", "160"),
        _conv("refuse/in-place-and-o", *w, "--in-place", "-o", "x.mp4"),
        _conv("refuse/same-file", *w, "-o", "v.mp4"),
        # refused before any work (F6): the passes, the bar's detection, a file written, all after
        _conv("refuse/mosh-no-lossless", "-i", "m4v.avi", "-w", "160", "--vfx", "datamosh"),
        _conv("refuse/burn-exists", *_SRT, "-o", "exists.mp4"),
        _conv(
            "refuse/attach-exists", "-i", "v.mp4", "--add-subs", "regular.srt", "-o", "exists.mp4"
        ),
        # the options' refusal before the transcript's; an output without an extension, as such
        _conv(
            "refuse/burn-exists-empty",
            "-i",
            "v.mp4",
            "--burn-subs",
            "hostile/empty.srt",
            "-o",
            "exists.mp4",
        ),
        _conv(
            "refuse/attach-no-extension",
            "-i",
            "v.mp4",
            "--add-subs",
            "regular.srt",
            "-o",
            "newfile",
        ),
        _conv("refuse/burn-and-add", *_SRT, "--add-subs", "regular.srt"),
        _conv("refuse/loop-both", *w, "--loop", "--loop-reverse", "-o", "x.gif"),
        _conv("refuse/bblur-bad", "-i", "v.mp4", "-w", "108", "-a", "9:16", "-b", "x"),
        _conv("refuse/bblur-cover", "-i", "v.mp4", "-w", "200", "-a", "1:1", "-r", "cover", "-b"),
        _conv("refuse/bblur-alone", *_SRT, "-b"),
        _conv(
            "vfx/bblur-ignored", "-i", "v.mp4", "-b", "--vfx", "invert"
        ),  # F7: ignored, not refused
        _conv("refuse/bad-vcodec", *w, "--video-codec", "mpeg2"),
        _conv("refuse/vcodec-copy", *w, "--video-codec", "copy"),
        _conv("refuse/bad-acodec", *w, "--audio-codec", "wav"),
        _conv("refuse/normalize-alone", *w, "--normalize"),
        _conv("refuse/bad-preset", "-i", "v.mp4", "-p", "tiktok"),
        _conv("refuse/preset-codec", "-i", "v.mp4", *_YT, "--video-codec", "hevc"),
        _conv("refuse/preset-resize", "-i", "v.mp4", *_YT, "-w", "160"),
        _conv("refuse/bmp", "-i", "p.png", "-w", "100", "-o", "x.bmp"),
        _conv("refuse/no-ext", *w, "-o", "x"),
        _conv("refuse/input-no-ext", "-i", "noext", "-w", "160"),
        _conv("refuse/in-place-no-ext", "-i", "noext", "-w", "160", "--in-place"),
    ]


def _environments() -> list[Case]:
    """What only the environment reaches: thread counts, the packaging's variables."""
    ffv1 = ("-i", "hd.mp4", "-w", "1280", "--video-codec", "ffv1", "-o", "x.mkv")
    normalize = ("-i", "v.mp4", *_YT, "--normalize")
    return [
        _env("env/threads-8-ffv1", {"OMP_NUM_THREADS": "8"}, *ffv1),
        _env("env/threads-32-ffv1", {"OMP_NUM_THREADS": "32"}, *ffv1),
        _env("env/threads-32-resize", {"OMP_NUM_THREADS": "32"}, "-i", "v.mp4", "-w", "160"),
        _env("env/threads-32-youtube", {"OMP_NUM_THREADS": "32"}, "-i", "v.mp4", *_YT),
        _env("env/no-normalize-home", {"FFMAN_NORMALIZE_HOME": ""}, *normalize),
        _env("env/missing-preset", {"FFMAN_NORMALIZE_HOME": "{corpus}/fonts"}, *normalize),
        _env("env/fonts-colon", {"FFMAN_FONTS_DIR": "{corpus}/a:b"}, *_SRT),
        _env(
            "env/no-oxipng",
            {"PATH": "{corpus}/no-optimisers"},
            "-i",
            "p.png",
            "-w",
            "16",
            "-o",
            "o.png",
        ),
        _env(
            "env/no-jpegoptim",
            {"PATH": "{corpus}/no-optimisers"},
            "-i",
            "p.jpg",
            "-w",
            "16",
            "-o",
            "o.jpg",
        ),
        _env(
            "env/no-gifsicle",
            {"PATH": "{corpus}/no-optimisers"},
            "-i",
            "v.mp4",
            "-w",
            "16",
            "-o",
            "o.gif",
        ),
    ]


def cases() -> list[Case]:
    """Every case, ids unique."""
    every = [*_cli(), *_resize(), *_effects(), *_burn(), *_attach(), *_youtube(), *_gif()]
    every += [*_refusals(), *_environments()]
    ids = [c.id for c in every]
    if len(set(ids)) != len(ids):
        msg = "duplicate case ids"
        raise ValueError(msg)
    return every

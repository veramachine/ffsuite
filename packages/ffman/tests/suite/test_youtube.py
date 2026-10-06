"""--preset youtube (bash's convert): run.sh's checks, ported (G3). Ids: the bash checks' numbers.

check.py's youtube() is ported whole: every requirement the preset claims, from
the probe, x264's own record of its options, and the MP4 box tree.
"""

import re
from fractions import Fraction
from pathlib import Path

import pytest

from ffman.plan.youtube import youtube_kbps
from tests.support.measures import red, sub_sync, sync, unmet
from tests.support.media import ff, tool


@pytest.fixture(scope="module")
def uploads(files: Path) -> Path:
    """run.sh's ok.mp4 (compliant), iv.mp4 (interlaced BT.601, 16 kHz mono), hdr.mp4 (PQ)."""
    gen = ["ffmpeg", "-v", "error", "-y"]
    picture = ["-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=1"]
    _ = tool(
        *gen,
        *picture,
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=48000",
        "-ac",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        str(files / "ok.mp4"),
    )
    tags = "setfield=tff,format=yuv420p,setparams=color_primaries=smpte170m:color_trc=smpte170m:colorspace=smpte170m"
    interlaced = [
        "-flags",
        "+ilme+ildct",
        "-c:v",
        "libx264",
        "-x264-params",
        "tff=1",
        "-c:a",
        "aac",
        "-ac",
        "1",
    ]
    _ = tool(
        *gen,
        *picture,
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=16000",
        "-vf",
        tags,
        *interlaced,
        str(files / "iv.mp4"),
    )
    pq = "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc"
    _ = tool(
        *gen,
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=320x180:r=25:d=0.2",
        "-vf",
        pq,
        "-c:v",
        "libx265",
        "-x265-params",
        "log-level=error",
        str(files / "hdr.mp4"),
    )
    return files


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_compliant_source(
    uploads: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:
    ok = str(uploads / "ok.mp4")
    assert ff(capsys, "-i", ok, "-o", "yt_ok.mp4", "-p", "youtube")[0] == 0
    assert unmet(ffprobe, "yt_ok.mp4") == []  # S084: every requirement

    def sound(path: str) -> str:
        return tool(
            ffmpeg, "-v", "error", "-i", path, "-map", "0:a", "-c", "copy", "-f", "md5", "-"
        )

    assert sound("yt_ok.mp4") == sound(ok)  # S085: its audio copied


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_an_interlaced_bt601_source(
    uploads: Path, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S086
    status, err = ff(capsys, "-i", str(uploads / "iv.mp4"), "-o", "yt_iv.mp4", "-p", "yt")
    assert status == 0, err
    assert unmet(ffprobe, "yt_iv.mp4") == []  # deinterlaced, converted, normalised


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize(
    ("source", "output", "message"),
    [
        pytest.param("hdr.mp4", "h.mp4", "HDR input", id="S087"),
        pytest.param("ok.mp4", "y.mkv", "container is MP4", id="S088"),
    ],
)
def test_youtube_refusals(
    uploads: Path, capsys: pytest.CaptureFixture[str], source: str, output: str, message: str
) -> None:
    status, err = ff(capsys, "-i", str(uploads / source), "-p", "youtube", "-o", output)
    assert (status, message in err) == (1, True)


@pytest.mark.parametrize(
    ("width", "height", "fps", "kbps"),
    [
        pytest.param(1920, 800, 25, 8000, id="S112"),
        pytest.param(1080, 1920, 25, 8000, id="S113"),
        pytest.param(2560, 1080, 25, 16000, id="S114"),
        pytest.param(640, 360, 25, 1000, id="S115"),
        pytest.param(854, 480, 25, 2500, id="S116"),
        pytest.param(1920, 1080, 60, 12000, id="S117"),
        pytest.param(3840, 2160, 30, 45000, id="S118"),
    ],
)
def test_the_bitrate_classes(width: int, height: int, fps: int, kbps: int) -> None:
    assert youtube_kbps(width, height, Fraction(fps)) == kbps


def flash_and_beep(files: Path, rate: int, *, flat: bool = False) -> Path:
    """run.sh's: a white flash top-left and a beep, both at 1 s (on a flat picture: for text)."""
    path = files / f"{'flat' if flat else 'cs'}{rate}.mp4"
    picture = "color=c=0x203040:s=320x180:r=25:d=2" if flat else "testsrc2=s=320x180:r=25:d=2"
    beep = f"aevalsrc='if(between(t,1,1.2),sin(2*PI*1000*t),0)':s={rate}:d=2"
    flash = "drawbox=x=0:y=0:w=24:h=24:color=white:t=fill:enable='gte(t,1)'"
    enc = ["-c:v", "libx264", "-bf", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2"]
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        picture,
        "-f",
        "lavfi",
        "-i",
        beep,
        "-vf",
        flash,
        *enc,
        str(path),
    )
    return path


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_an_rgb_source(
    files: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str]
) -> None:  # S119
    rgb = files / "rgb.mov"
    red_ = [
        "-f",
        "lavfi",
        "-i",
        "color=c=0xFF0000:s=320x180:r=25:d=1",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1:r=48000",
    ]
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        *red_,
        "-ac",
        "2",
        "-c:v",
        "png",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        str(rgb),
    )
    assert ff(capsys, "-i", str(rgb), "-o", "rgb_yt.mp4", "-p", "yt", "-y")[0] == 0
    r, g, b = red(ffmpeg, ffprobe, "rgb_yt.mp4")
    assert (r >= 240, g <= 8, b <= 8) == (True, True, True), (r, g, b)  # BT.601's matrix gives G 23


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
@pytest.mark.parametrize("rate", [pytest.param(48000, id="S120"), pytest.param(16000, id="S121")])
def test_the_audio_trails_by_its_priming(
    files: Path, ffmpeg: str, ffprobe: str, capsys: pytest.CaptureFixture[str], rate: int
) -> None:
    # the picture trails nothing; the audio trails by its encoder's priming, which only an edit
    # list (YouTube forbids them) could remove: 1024 samples at 48 kHz, copied or native; FDK 2048
    fdk = "libfdk_aac" in tool(ffmpeg, "-hide_banner", "-encoders")
    prime = 43 if rate == 16000 and fdk else 21
    assert (
        ff(capsys, "-i", str(flash_and_beep(files, rate)), "-o", f"cv{rate}.mp4", "-p", "yt", "-y")[
            0
        ]
        == 0
    )
    assert -prime - 4 <= 1000 * sync(ffmpeg, ffprobe, f"cv{rate}.mp4") <= -prime + 4


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_without_fdk(
    files: Path, ffprobe: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FFMAN_NO_FDK", "1")
    status, err = ff(
        capsys, "-i", str(flash_and_beep(files, 16000)), "-o", "nat.mp4", "-p", "yt", "-y"
    )
    assert status == 0, err
    assert re.findall(r"preset youtube-aac[a-z-]*", err) == ["preset youtube-aac-native"]  # S122
    assert unmet(ffprobe, "nat.mp4") == []  # S123


@pytest.mark.ffmpeg
@pytest.mark.usefixtures("here")
def test_a_transport_stream(
    files: Path, ffmpeg: str, ffprobe: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ts = files / "ts.ts"
    _ = tool(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        str(flash_and_beep(files, 48000, flat=True)),
        "-c",
        "copy",
        "-f",
        "mpegts",
        str(ts),
    )
    cue = tmp_path / "sync.srt"
    _ = cue.write_text("1\n00:00:01,000 --> 00:00:02,000\nSYNC\n\n")
    argv = [
        "-i",
        str(ts),
        "--burn-subs",
        str(cue),
        "--font-size",
        "300",
        "--video-codec",
        "ffv1",
        "-o",
        "ts_o.mkv",
        "-y",
    ]
    assert ff(capsys, *argv)[0] == 0  # S124: it starts at 1.4 s; the picture on time
    assert abs(sync(ffmpeg, ffprobe, "ts_o.mkv")) < 0.005  # S125: picture and audio together
    late = sub_sync(ffmpeg, ffprobe, "ts_o.mkv", 90, 1.0)
    assert 0 <= late <= 0.9  # S126: on the first frame at or after its event

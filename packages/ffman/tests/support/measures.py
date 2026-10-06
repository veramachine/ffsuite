"""check.py's measures of pictures and sound, in Python: its numpy was counts and means."""

import json
import math
import re
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import numpy as np

from tests.support.media import raw, tool

if TYPE_CHECKING:
    from numpy.typing import NDArray

type Image = NDArray[np.float64]  # frames, a frame, a profile: float64 throughout
AUDIO_RATE: Final = 48000  # the sound decoded to, for a sample's time


@dataclass(frozen=True, slots=True)
class Frames:
    """The picture's frames as stored (grey, one byte a pixel), and their times."""

    times: list[float]
    width: int
    height: int
    pixels: list[bytes]  # a frame each


def _streams(ffprobe: str, path: str) -> list[dict[str, object]]:
    shown = tool(ffprobe, "-v", "error", "-show_streams", "-of", "json", path)
    return cast("list[dict[str, object]]", json.loads(shown)["streams"])


def frames(ffmpeg: str, ffprobe: str, path: str, crop: str | None = None) -> Frames:
    """check.py's frames: every frame, as stored (``crop=W:H:X:Y`` first, if given)."""
    video = next(s for s in _streams(ffprobe, path) if s["codec_type"] == "video")
    w, h = cast("int", video["width"]), cast("int", video["height"])
    if crop is not None:
        size = re.match(r"crop=(\d+):(\d+)", crop)
        assert size is not None, crop
        w, h = int(size[1]), int(size[2])
    picked = ["-vf", crop] if crop is not None else []
    pixels = raw(
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-map",
        "0:v:0",
        *picked,
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    )
    stamps = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        path,
    )
    times = [float(x) for x in stamps.replace(",", " ").split()]  # an mp4 adds an empty field
    size_ = w * h
    return Frames(times, w, h, [pixels[i : i + size_] for i in range(0, len(pixels), size_)])


def sync(ffmpeg: str, ffprobe: str, path: str) -> float:
    """check.py's sync: the white flash (top-left) less the beep, in seconds (negative: audio late)."""
    flash = frames(ffmpeg, ffprobe, path, "crop=16:16:0:0")
    seen = next(
        t for t, px in zip(flash.times, flash.pixels, strict=True) if sum(px) / len(px) > 200
    )
    samples = raw(
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(AUDIO_RATE),
        "-",
    )
    loud = array("f")
    loud.frombytes(samples)
    if sys.byteorder == "big":  # f32le: little-endian, whatever the host
        loud.byteswap()
    first = next(i for i, x in enumerate(loud) if abs(x) > 0.2)
    audio = next((s for s in _streams(ffprobe, path) if s["codec_type"] == "audio"), None)
    start = float(cast("str", audio["start_time"])) if audio and "start_time" in audio else 0.0
    return seen - (start + first / AUDIO_RATE)


def sub_sync(ffmpeg: str, ffprobe: str, path: str, band_top: int, event: float) -> float:
    """check.py's sub_sync: how late the subtitle first shows after its event, in frames' steps.

    Onset against the first frame, not a fixed count: small text at a low
    resolution once fooled a fixed threshold by a frame.
    """
    shot = frames(ffmpeg, ffprobe, path)
    band = band_top * shot.width
    bright = [sum(1 for v in px[band:] if v > 230) for px in shot.pixels]
    onset = next(t for t, n in zip(shot.times, bright, strict=True) if n > bright[0] + 8)
    step = (shot.times[-1] - shot.times[0]) / (len(shot.times) - 1)
    return (onset - event) / step


def red(ffmpeg: str, ffprobe: str, path: str) -> tuple[int, int, int]:
    """check.py's red: the centre pixel through the file's BT.709 tags (BT.601 would give G 23)."""
    video = next(s for s in _streams(ffprobe, path) if s["codec_type"] == "video")
    w, h = cast("int", video["width"]), cast("int", video["height"])
    as709 = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24"
    rgb = raw(
        ffmpeg, "-v", "error", "-i", path, "-frames:v", "1", "-vf", as709, "-f", "rawvideo", "-"
    )
    at = ((h // 2) * w + w // 2) * 3
    return rgb[at], rgb[at + 1], rgb[at + 2]


def _mean(values: "Image") -> float:
    """All the values' mean (numpy 2.4's stubs type it Any; a float64 is a float)."""
    return cast("float", values.mean())


def _std(values: "Image") -> float:
    return cast("float", values.std())


def _sum(values: "Image") -> float:
    return cast("float", values.sum())


def _max(values: "Image") -> float:
    return cast("float", values.max())


def _min(values: "Image") -> float:
    return cast("float", values.min())


def _rgb_frames(ffmpeg: str, ffprobe: str, path: str, count: int) -> "Image":
    video = next(s for s in _streams(ffprobe, path) if s["codec_type"] == "video")
    w, h = cast("int", video["width"]), cast("int", video["height"])
    pixels = raw(
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-frames:v",
        str(count),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    )
    return np.frombuffer(pixels, np.uint8).reshape(-1, h, w, 3).astype(np.float64)


def effect_property(ffmpeg: str, ffprobe: str, name: str, out: str, ref: str) -> tuple[bool, str]:  # noqa: C901, PLR0911 -- check.py's fx_prop, effect by effect
    """check.py's fx_prop: an effect's measurable property, against the same render without it.

    20 frames of a still picture, averaged (noise the effects add cancels). The
    source is black with a white box from x=200: a sharp edge, a highlight.
    numpy's stubs (2.4, the pin's) type a reduction along an axis as Any: each
    is cast where it is made; the whole-array ones go through _mean, _max, _min.
    """
    a, b = _rgb_frames(ffmpeg, ffprobe, out, 20), _rgb_frames(ffmpeg, ffprobe, ref, 20)
    if a.shape != b.shape:
        return False, f"shape {a.shape} vs {b.shape}"
    am, bm = cast("Image", a.mean(0)), cast("Image", b.mean(0))
    height, width, _ = cast("tuple[int, int, int]", am.shape)  # an averaged RGB frame
    if name == "pixelate":  # 8 px blocks
        h, w = (height // 8) * 8, (width // 8) * 8
        blocks = am[:h, :w].reshape(h // 8, 8, w // 8, 8, 3)
        spread = _max(cast("Image", blocks.max((1, 3))) - cast("Image", blocks.min((1, 3))))
        return spread <= 2, f"largest spread inside a block {spread:.1f}"
    if name == "invert":
        err = _mean(np.abs(am - (255 - bm)))
        return err < 3, f"mean |out - (255 - in)| {err:.2f}"
    row = slice(height // 2 - 20, height // 2 + 20)

    def edge(channel: "Image") -> float:  # the first column past half height, sub-pixel
        p = cast("Image", channel[row].mean(0))
        past: NDArray[np.bool_] = p > 128
        i = int(np.argmax(past))
        v = cast("list[float]", p.tolist())  # a float64 profile
        return i - 1 + (128 - v[i - 1]) / (v[i] - v[i - 1])

    def rise(channel: "Image") -> float:  # the edge's 10-90% width, px
        p = cast("Image", channel[row].mean(0))
        return float(np.argmax(p > 229.5) - np.argmax(p > 25.5))

    if name == "ca":  # radial, blue outermost; 4:2:0 halves colour: sign and size (exact on a PNG)
        d = edge(am[..., 0]) - edge(am[..., 2])
        want = 6 * (width / 2 - 200) / (width / 2)
        return 0.5 * want < d < 1.5 * want, f"R-B {d:+.2f} px at x=200 (radial: {want:+.2f})"
    if name == "halation":  # glow in the dark just outside the box
        ring = (slice(row.start, row.stop), slice(170, 195))
        d0 = _mean(bm[ring][..., 0]) - _mean(bm[ring][..., 2])
        d1 = _mean(am[ring][..., 0]) - _mean(am[ring][..., 2])
        return d1 > d0 + 3, f"R-B just outside the highlight {d0:.1f} -> {d1:.1f}"
    if name == "blur":  # a sharp edge widens
        r0, r1 = rise(cast("Image", bm.mean(-1))), rise(cast("Image", am.mean(-1)))
        return r1 > r0 + 3, f"edge rise {r0:.0f} -> {r1:.0f} px"
    if name == "vhs":  # tape noise (its bandwidth is measured at 1080 lines)
        noise = _mean(cast("Image", a.std(0)))
        return noise > 2, f"frame-to-frame noise {noise:.2f}"
    if name == "crt":  # no geometry (televisions corrected it): the box's edge stays at x=200

        def column(rows: slice) -> float:
            p = cast("Image", am[rows].mean((0, 2)))
            half = (_min(p) + _max(p)) / 2
            past: NDArray[np.bool_] = p > half
            i = int(np.argmax(past))
            v = cast("list[float]", p.tolist())  # a float64 profile
            return i - 1 + (half - v[i - 1]) / (v[i] - v[i - 1])

        e = [column(slice(top, top + 20)) for top in (10, height // 2, height - 30)]
        return max(abs(x - e[1]) for x in e) < 0.5, "edge column top/middle/bottom " + " ".join(
            f"{x:.2f}" for x in e
        )
    return False, f"unknown effect {name}"


def frames_of(
    ffmpeg: str, path: str, pix_fmt: str, shape: tuple[int, ...], count: int | None = None
) -> "Image":
    """Decoded frames as float64, ``shape`` a frame's (rgb24 (h, w, 3), gray16le (h, w), yuv444p (3, h, w))."""
    limit = ["-frames:v", str(count)] if count is not None else []
    data = raw(
        ffmpeg, "-v", "error", "-i", path, *limit, "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"
    )
    # 16 bits a component, little-endian: ffmpeg names them by their bits a pixel (gray16le,
    # rgb48le, rgba64le); everything else here is 8 bits
    kind = np.dtype("<u2") if pix_fmt.endswith(("16le", "48le", "64le")) else np.dtype(np.uint8)
    return np.frombuffer(data, kind).reshape(-1, *shape).astype(np.float64)


def _row(values: "Image", index: int) -> "Image":
    """One row along the first axis -- a frame of frames, a line of a frame (numpy 2.4's stubs: Any)."""
    return cast("Image", values[index])


def halation_tint(ffmpeg: str, out: str, source: str) -> tuple[float, float, float]:
    """run.sh's: the glow beside an 80 px light at (280, 140), R, G and B (640x360, one frame)."""
    shape = (360, 640, 3)
    glow = _row(frames_of(ffmpeg, out, "rgb24", shape), 0) - _row(
        frames_of(ffmpeg, source, "rgb24", shape), 0
    )
    r, g, b = cast("list[float]", cast("Image", glow[170:190, 370:380].mean((0, 1))).tolist())
    return r, g, b


def lateral_shift(ffmpeg: str, path: str) -> tuple[float, float]:
    """run.sh's: R less B, each line's centroid -- at the centre (x 280-360), and 280 px out (x 0-90)."""
    rows = _row(frames_of(ffmpeg, path, "rgb24", (360, 640, 3)), 0)[150:210]
    a = cast("Image", rows.mean(0))

    def centroid(channel: int, lo: int, hi: int) -> float:
        weights = a[lo:hi, channel]
        return _sum(weights * np.arange(lo, hi)) / _sum(weights)

    return centroid(0, 280, 360) - centroid(2, 280, 360), centroid(0, 0, 90) - centroid(2, 0, 90)


def crt_line(ffmpeg: str, out: str, source: str) -> tuple[int, float, float]:
    """run.sh's crtline: the scanlines' frequency (cycles a picture height), the linear light kept,
    and the gaps' depth -- in linear light (2.4), on a flat grey field at 1080 rows."""
    shape = (1080, 640)
    o = (_row(frames_of(ffmpeg, out, "gray16le", shape), 0) / 65535) ** 2.4  # linear light
    i = (_row(frames_of(ffmpeg, source, "gray16le", shape), 0) / 65535) ** 2.4
    profile = cast("Image", o[:, 100:540].mean(1))
    spectrum = np.abs(np.fft.rfft(profile - _mean(profile)))
    middle = profile[200:880]
    frequency = int(np.argmax(spectrum[1:])) + 1
    return (
        frequency,
        _mean(o) / _mean(i),
        (_max(middle) - _min(middle)) / (_max(middle) + _min(middle)),
    )


def vhs_response(ffmpeg: str, out: str, source: str, plane: int) -> float:
    """run.sh's vhsresp: a sine's amplitude after the tape over before, on one plane of yuv444p."""

    def amplitude(path: str) -> float:
        planes = frames_of(ffmpeg, path, "yuv444p", (3, 1080, 1920), 10)
        a = cast("Image", cast("Image", planes[:, plane].mean(0))[520:560].mean(0))[60:-60]
        return (_max(a) - _min(a)) / 2

    return amplitude(out) / amplitude(source)


def edge_width(ffmpeg: str, path: str) -> int:
    """run.sh's edgew: the 10-90% width, in light, of the edge in a 360x640 bar-blurred border."""
    linear = (_row(frames_of(ffmpeg, path, "rgb48le", (640, 360, 3), 1), 0) / 65535) ** 2.4
    p = cast("Image", linear[20:120].mean(0))  # (360, 3): a profile a channel
    c = int(np.argmax(np.abs(_row(p, -1) - _row(p, 0))))  # the channel the edge is in
    rising = cast("float", p[-1, c]) > cast("float", p[0, c])
    q = p[:, c] if rising else -p[:, c]
    lo, hi = _min(q), _max(q)
    return int(np.argmax(q > lo + 0.9 * (hi - lo))) - int(np.argmax(q > lo + 0.1 * (hi - lo)))


def vhs_noise(ffmpeg: str, path: str, width: int, height: int) -> tuple[float, float]:
    """run.sh's vnoise: luma and chroma RMS on flat grey, clear of the switching band (4 frames)."""
    a = frames_of(ffmpeg, path, "yuv444p", (3, height, width), 4)
    inside = a[:, :, height // 8 : height // 2, width // 8 : -width // 8]
    return _std(inside[:, 0]), _std(inside[:, 1])


def colour_edge(ffmpeg: str, path: str) -> float:
    """run.sh's droop measure: the row, sub-pixel, where a horizontal Cb edge crosses its middle."""
    cb = cast("Image", frames_of(ffmpeg, path, "yuv444p", (3, 1080, 1920), 4)[:, 1].mean(0))
    p = cast("Image", cb[:, 400:1500].mean(1))
    v = cast("list[float]", p.tolist())
    m = (v[300] + v[800]) / 2
    past: NDArray[np.bool_] = p > m
    i = int(np.argmax(past))
    return i - 1 + (m - v[i - 1]) / (v[i] - v[i - 1])


def head_switching(ffmpeg: str, path: str) -> tuple[int, int]:
    """run.sh's: of the bottom 40 rows, how many have the bar's edge at x 938 (moved), how many at 900."""
    grey = cast("Image", frames_of(ffmpeg, path, "gray", (1080, 1920), 4).mean(0))
    edges = [int(np.argmax(_row(grey, r) > 128)) for r in range(1040, 1080)]
    return sum(1 for x in edges if x == 938), sum(1 for x in edges if x == 900)


def _srgb_to_linear(values: "Image") -> "Image":
    """sRGB's transfer, decoded (the PNGs here are sRGB)."""
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def light(ffmpeg: str, ffprobe: str, path: str, rows: tuple[int, int] | None = None) -> float:
    """run.sh's light: the mean light (sRGB decoded) of the frame, or of rows a:b."""
    video = next(s for s in _streams(ffprobe, path) if s["codec_type"] == "video")
    w, h = cast("int", video["width"]), cast("int", video["height"])
    linear = _srgb_to_linear(_row(frames_of(ffmpeg, path, "rgb48le", (h, w, 3), 1), 0) / 65535)
    return _mean(linear[rows[0] : rows[1]] if rows else linear)


def red_green_dip(ffmpeg: str, path: str) -> tuple[float, float]:
    """run.sh's: across a red|green edge (row 180, 640x360), the lowest luminance, and red's own."""
    rgb = _srgb_to_linear(_row(frames_of(ffmpeg, path, "rgb48le", (360, 640, 3), 1), 0) / 65535)
    line = _row(rgb, 180)
    y = 0.2126 * line[:, 0] + 0.7152 * line[:, 1] + 0.0722 * line[:, 2]
    return _min(y[250:390]), cast("float", y[100])


def roundness(ffmpeg: str, path: str) -> float:
    """run.sh's: a blurred dot's width over its height on screen, at SAR 2:1 (2 * sx / sy; 1 is round)."""
    a = (_row(frames_of(ffmpeg, path, "gray16le", (240, 320), 1), 0) / 65535) ** 2.4
    y, x = np.indices((240, 320))  # mgrid's grids, typed
    m = _sum(a)
    cx, cy = _sum(a * x) / m, _sum(a * y) / m
    sx = math.sqrt(_sum(a * (x - cx) ** 2) / m)
    sy = math.sqrt(_sum(a * (y - cy) ** 2) / m)
    return 2 * sx / sy


def border_detail(ffmpeg: str, path: str) -> float:
    """run.sh's detail: the top border's neighbour differences at the blur's own scale (45 columns)."""
    small = ["-vf", "crop=iw:ih*0.2:0:0,scale=45:16:flags=area"]
    data = raw(
        ffmpeg,
        "-v",
        "error",
        "-i",
        path,
        "-frames:v",
        "1",
        *small,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray16le",
        "-",
    )
    a = np.frombuffer(data, np.dtype("<u2")).reshape(16, 45).astype(np.float64) / 257
    return _mean(np.abs(np.diff(a, axis=1)))


def _extent(values: "NDArray[np.intp]") -> tuple[int, int]:
    """The least and the greatest, as Python ints (numpy 2.4's stubs type each Any)."""
    return int(cast("int", values.min())), int(cast("int", values.max()))


def pop(ffmpeg: str, ffprobe: str, path: str, peak: float, settled: float) -> tuple[bool, str]:
    """check.py's pop: between the pop's peak and its settled frame, only the popped word changes,
    and it grows about its own centre (the word: the settled frame's gold)."""
    shot = frames(ffmpeg, ffprobe, path)
    w, h = shot.width, shot.height

    def at(t: float) -> int:  # the frame showing t
        return max(k for k, p in enumerate(shot.times) if p <= t + 1e-6)

    a, b = (
        np.frombuffer(shot.pixels[at(t)], np.uint8).reshape(h, w).astype(np.int64)
        for t in (peak, settled)
    )
    ys, xs = np.nonzero(np.abs(a - b) > 24)
    if xs.size == 0:
        return False, "nothing changed: no pop"
    passthrough = [
        "-map",
        "0:v:0",
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    rgb = raw(ffmpeg, "-v", "error", "-i", path, *passthrough)
    s = cast("NDArray[np.uint8]", np.frombuffer(rgb, np.uint8).reshape(-1, h, w, 3)[at(settled)])
    gold = (s[:, :, 0] > 200) & (s[:, :, 1] > 150) & (s[:, :, 2] < 90)
    gy, gx = np.nonzero(gold)
    if gx.size == 0:
        return False, "no highlighted word found"
    (x0, x1), (y0, y1) = _extent(xs), _extent(ys)  # what changed
    (w0, w1), (h0, h1) = _extent(gx), _extent(gy)  # the word
    ww, hh = w1 - w0, h1 - h0
    inside = (
        x0 >= w0 - 0.12 * ww - 6
        and x1 <= w1 + 0.12 * ww + 6
        and y0 >= h0 - 0.2 * hh - 6
        and y1 <= h1 + 0.2 * hh + 6
    )
    dy = abs((y0 + y1) / 2 - (h0 + h1) / 2)
    return inside and dy <= 2, f"change x{x0}-{x1} y{y0}-{y1} vs word x{w0}-{w1} y{h0}-{h1}"


_CONTAINERS: Final = (b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"udta")


def boxes(
    buf: bytes, off: int, end: int, depth: int, out: list[tuple[int, str]]
) -> list[tuple[int, str]]:
    """check.py's boxes: the MP4 box tree, as (depth, type)."""
    while off + 8 <= end:
        size = int.from_bytes(buf[off : off + 4], "big")  # a 32-bit size, then a four-byte type
        kind = buf[off + 4 : off + 8]
        if size == 1:  # a 64-bit size follows
            size = int.from_bytes(buf[off + 8 : off + 16], "big")
        if size < 8:
            break
        out.append((depth, kind.decode("latin1")))
        if kind in _CONTAINERS:
            _ = boxes(buf, off + 8, off + size, depth + 1, out)
        off += size
    return out


def unmet(ffprobe: str, path: str) -> list[str]:
    """check.py's youtube: the requirements the file misses (none: compliant) -- the probe,
    x264's own record of its options, the MP4 box tree."""
    shown = tool(ffprobe, "-v", "error", "-show_streams", "-of", "json", path)
    streams = cast("list[dict[str, object]]", json.loads(shown)["streams"])
    v = next(s for s in streams if s["codec_type"] == "video")
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    data = Path(path).read_bytes()
    m = re.search(rb"x264 - core \d+.*?options: ([^\x00]+)", data)
    opts = (
        dict(kv.split("=", 1) for kv in m[1].decode(errors="replace").split() if "=" in kv)
        if m
        else {}
    )
    num, den = (int(x) for x in str(v["avg_frame_rate"]).split("/"))
    half = num / den / 2
    gop = int(half) + (1 if half - int(half) > 0.5 else 0)
    tree = boxes(data, 0, len(data), 0, [])
    top = [t for d, t in tree if d == 0]
    checks = {
        "H.264 High": (v["codec_name"], v.get("profile")) == ("h264", "High"),
        "progressive": v.get("field_order", "progressive") == "progressive",
        "2 B-frames": opts.get("bframes") == "2",
        "closed GOP": opts.get("open_gop") == "0",
        f"GOP {gop}": opts.get("keyint") == str(gop),
        "CABAC": opts.get("cabac") == "1",
        "two-pass": opts.get("rc") == "2pass",
        "4:2:0": v["pix_fmt"] == "yuv420p",
        "BT.709": (v.get("color_space"), v.get("color_transfer"), v.get("color_primaries"))
        == ("bt709",) * 3,
        "limited range": v.get("color_range") == "tv",
        "AAC-LC 48k stereo": a is not None
        and (a["codec_name"], a.get("profile"), a["sample_rate"], a["channels"])
        == ("aac", "LC", "48000", 2),
        "moov first": "moov" in top and top.index("moov") < top.index("mdat"),
        "no edit list": "elst" not in [t for _, t in tree],
    }
    return [k for k, ok in checks.items() if not ok]


def _times(ffprobe: str, path: str) -> list[float]:
    """The picture's frame times, as check.py's frames() read them (an mp4 adds an empty field)."""
    stamps = tool(
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        path,
    )
    return [float(x) for x in stamps.replace(",", " ").split()]


def text_band(ffmpeg: str, ffprobe: str, path: str, ref: str, t: float, what: str) -> float | None:
    """check.py's text_band: where the subtitles are at ``t``, as a fraction of the height --
    their rows' centre (``what="centre"``) or lowest row; None if none show.

    The rows are those where the frame differs from the same frame of ``ref`` (the
    source, or the same resize without subtitles): the picture's own colours never
    count. The frame is the output's at ``t``, and the same index of ``ref``.
    """
    video = next(s for s in _streams(ffprobe, path) if s["codec_type"] == "video")
    w, h = cast("int", video["width"]), cast("int", video["height"])
    i = max(k for k, p in enumerate(_times(ffprobe, path)) if p <= t + 1e-6)

    def rgb(source: str) -> "NDArray[np.int64]":
        passthrough = [
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
        data = raw(ffmpeg, "-v", "error", "-i", source, *passthrough)
        frame = cast("NDArray[np.uint8]", np.frombuffer(data, np.uint8).reshape(-1, h, w, 3)[i])
        return frame.astype(np.int64)

    changed = cast("NDArray[np.bool_]", np.abs(rgb(path) - rgb(ref)).max(axis=2) > 60)
    counts = cast("NDArray[np.int64]", changed.sum(axis=1))  # a row's changed pixels
    rows = np.nonzero(counts > 2)[0]
    if rows.size == 0:
        return None
    lo, hi = _extent(rows)
    return ((lo + hi) / 2 if what == "centre" else hi) / h

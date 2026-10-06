"""The mappings between ffmetadata, Vorbis comments and cue sheets, measured.

Usage: python3 ffman-mappings.py FFMPEG CUETAG VORBISCOMMENT METAFLAC CUEDUMP  (ffprobe beside
ffmpeg; CUETAG is cuetools' cuetag.sh, its cueprint beside it; CUEDUMP the cue skill's cuedump.c,
built against libcue). Prints what it found; ffman-mappings.md's measured rows are
this output (ffmpeg n8.1.2, cuetools 1.4.1). Comments are read as bytes, in order, by the
vorbiscomment skill's readers.
"""

import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
from itertools import pairwise
from pathlib import Path

FFMPEG, CUETAG, VORBISCOMMENT, METAFLAC, CUEDUMP = sys.argv[1:6]
FFPROBE = str(Path(FFMPEG).with_name("ffprobe"))

_READERS = (
    Path(__file__).resolve().parents[2] / "skills/vorbiscomment/scripts/measure.py"
)
_spec = importlib.util.spec_from_file_location("vorbiscomment_measure", _READERS)
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)

FFMETA = """;FFMETADATA1
title=T
artist=A;B
album_artist=AA
track=3
disc=1
comment=C
encoded_by=E
composer=Co
performer=P
date=2026
genre=G
Custom Key=v
[STREAM]
title=S
[CHAPTER]
TIMEBASE=1/1000
START=0
END=1500
title=One
artist=CA
[CHAPTER]
TIMEBASE=1/75
START=113
END=375
title=Two
"""

COMMENTS = [
    b"ARTIST=A",
    b"ARTIST=B",
    b"COMMENT=c",
    b"DESCRIPTION=d",
    b"ENCODEDBY=e",
    b"ENCODED_BY=f",
    b"ALBUMARTIST=aa",
    b"TRACKNUMBER=3",
    b"DISCNUMBER=1",
    b"Title=t",
    b"REPLAYGAIN_TRACK_GAIN=-6.00 dB",
    b"CHAPTER000=00:00:01.000",
    b"CHAPTER000NAME=One",
    b"CHAPTER000URL=http://example.org/",
    b"CHAPTER000ARTIST=ca",
]

CUE = """REM GENRE "Alternative Rock"
REM DATE 1991
REM DISCID 860B640B
REM COMMENT "ExactAudioCopy v1.6"
REM DISCNUMBER 1
REM REPLAYGAIN_ALBUM_GAIN -7.03 dB
CATALOG 0123456789012
PERFORMER "Disc Artist"
TITLE "The Album"
SONGWRITER "Disc Writer"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "One"
    PERFORMER "Track Artist"
    SONGWRITER "Track Writer"
    ISRC GBAYE7900001
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Two"
    INDEX 00 03:58:20
    INDEX 01 04:00:00
"""


def run(*argv: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        env=env,
    )


def chapters(path: Path) -> list[tuple[str, str, dict]]:
    shown = json.loads(
        run(FFPROBE, "-v", "error", "-show_chapters", "-of", "json", str(path)).stdout
        or "{}"
    )
    return [
        (c["start_time"], c["end_time"], c.get("tags", {}))
        for c in shown.get("chapters", [])
    ]


def ffmetadata_to_vorbis(work: Path) -> None:
    print(
        "== A. ffmetadata into Vorbis comments, through ffmpeg (raw comments, in order)"
    )
    meta = work / "in.ffmeta"
    meta.write_text(FFMETA)
    for ext, codec in (("opus", "libopus"), ("ogg", "libvorbis"), ("flac", "flac")):
        out = work / f"a.{ext}"
        done = run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=10", "-i", str(meta),
                   "-map", "0", "-map_metadata", "1", "-map_metadata:s:a:0", "1:s:0",
                   "-map_chapters", "1", "-c:a", codec, str(out))  # fmt: skip
        comments = (
            [c.decode() for c in vc.comments_of(out)]
            if done.returncode == 0
            else done.stderr
        )
        print(f"  .{ext}: {comments}")
        print(f"         read back as chapters: {chapters(out)}")
    # Chapters with no global or stream tags. -map_metadata -1 would drop the chapters' titles too
    # (fftools: it sets every manual flag); :g and :s:0 drop only those tags.
    only = work / "chapters.ffmeta"
    only.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n"
    )
    src = work / "src.opus"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        "-c:a",
        "libopus",
        str(src),
    )
    for codec in ("libopus", "copy"):
        for label, extra in (
            ("default", []),
            ("-fflags +bitexact", ["-fflags", "+bitexact"]),
        ):
            out = work / "only.opus"
            run(FFMPEG, "-v", "error", "-y", "-i", str(src), "-i", str(only), "-map", "0",
                "-map_metadata:g", "-1", "-map_metadata:s:0", "-1", "-map_chapters", "1",
                *extra, "-c:a", codec, str(out))  # fmt: skip
            got = [c.decode() for c in vc.comments_of(out)]
            print(f"  chapters, no tags, -c:a {codec:7} {label:17}: comments {got}")
    out = work / "minus-one.opus"
    run(FFMPEG, "-v", "error", "-y", "-i", str(src), "-i", str(only), "-map", "0",
        "-map_metadata", "-1", "-map_chapters", "1", "-c:a", "libopus", str(out))  # fmt: skip
    print(
        f"  -map_metadata -1 instead: comments {[c.decode() for c in vc.comments_of(out)]}"
    )


def vorbis_to_ffmetadata(work: Path) -> None:
    print("\n== B. Vorbis comments into ffmetadata, through ffmpeg")
    base = work / "base.flac"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=d=10",
        "-c:a",
        "flac",
        str(base),
    )
    flac = work / "b.flac"
    vc.with_comments(base, COMMENTS, flac)
    exported = run(
        FFMPEG, "-v", "error", "-i", str(flac), "-f", "ffmetadata", "-"
    ).stdout
    print("  FLAC:", " | ".join(line for line in exported.splitlines() if line))
    for order in ([b"COMMENT=c", b"DESCRIPTION=d"], [b"DESCRIPTION=d", b"COMMENT=c"]):
        out = work / "order.flac"
        vc.with_comments(base, order, out)
        shown = json.loads(
            run(FFPROBE, "-v", "error", "-show_format", "-of", "json", str(out)).stdout
        )
        meta = run(
            FFMPEG, "-v", "error", "-i", str(out), "-f", "ffmetadata", "-"
        ).stdout.splitlines()[1:]
        print(
            f"  {[o.decode() for o in order]}: ffprobe {shown['format'].get('tags', {})}; ffmpeg's output {meta}"
        )
    text = work / "b.txt"
    text.write_bytes(b"".join(c + b"\n" for c in COMMENTS))
    ogg, tagged = work / "b-in.ogg", work / "b.ogg"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=d=10",
        "-c:a",
        "libvorbis",
        str(ogg),
    )
    run(VORBISCOMMENT, "-w", "-c", str(text), str(ogg), str(tagged))
    for label, maps in (
        ("global only", []),
        ("-map_metadata 0:s:0", ["-map_metadata", "0:s:0"]),
    ):
        out = run(
            FFMPEG, "-v", "error", "-i", str(tagged), *maps, "-f", "ffmetadata", "-"
        ).stdout
        print(
            f"  Ogg Vorbis, {label}:",
            " | ".join(line for line in out.splitlines() if line),
        )


def cue_to_vorbis(work: Path) -> None:
    print(
        "\n== C. A cue sheet into Vorbis comments, through cuetools' cuetag.sh (text mode)"
    )
    cue = work / "sheet.cue"
    cue.write_text(CUE)
    targets = [work / "t1.txt", work / "t2.txt"]
    env = {"PATH": f"{Path(CUETAG).parent}:/usr/bin:/bin"}
    done = run("sh", CUETAG, str(cue), *map(str, targets), env=env)
    for n, target in enumerate(targets, 1):
        shown = target.read_text().splitlines() if target.exists() else done.stderr
        print(f"  track {n}: {shown}")


def arithmetic() -> None:
    """Every frame to 100 hours, every millisecond to an hour; integers only.

    A frame is 1000/75 = 40/3 ms: |40f/3 - m| = |40f - 3m| / 3, so the worst error is exact.
    """
    print("\n== D. Times between the three (exact integer arithmetic)")
    worst, back, frames_max = 0, True, 100 * 3600 * 75
    for f in range(frames_max + 1):
        m = (80 * f + 3) // 6  # 40f/3 to the nearest ms (floor(40f/3 + 1/2))
        worst = max(worst, abs(40 * f - 3 * m))
        back = back and (m * 75 + 500) // 1000 == f  # the cue skill's ms -> frames
    ties = any(
        (40 * f) % 3 * 2 == 3 for f in range(3)
    )  # a fraction of 1/2: never, 40f mod 3 is 0, 1, 2
    print(f"  frames -> ms (nearest): worst error {worst}/3 ms; a tie possible: {ties}")
    print(f"  frames -> ms -> frames: every frame to 100 h back exactly: {back}")
    ms_max = 3_600_000
    kept = sum(
        1 for ms in range(ms_max + 1) if (((ms * 75 + 500) // 1000) * 80 + 3) // 6 == ms
    )
    print(
        f"  ms -> frames -> ms: {kept} of {ms_max + 1} milliseconds to an hour back exactly ({kept / (ms_max + 1):.4%})"
    )


def timebase_75(work: Path) -> None:
    print("\n== E. A cue time in ffmetadata as TIMEBASE=1/75, through ffmpeg")
    meta = work / "e.ffmeta"
    meta.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/75\nSTART=19327\nEND=40724\ntitle=Two\n"
    )
    mkv, again = work / "e.mkv", work / "again.ffmeta"
    run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=600", "-i", str(meta),
        "-map", "0", "-map_chapters", "1", str(mkv))  # fmt: skip
    print(f"  .mkv: {chapters(mkv)}")
    run(FFMPEG, "-v", "error", "-y", "-i", str(meta), "-f", "ffmetadata", str(again))
    kept = [
        line
        for line in again.read_text().splitlines()
        if line.startswith(("TIMEBASE", "START", "END"))
    ]
    print(f"  ffmetadata again: {kept}")


def edges(work: Path) -> None:
    """ffmetadata <-> Vorbis: the elements one format can hold and the other cannot."""
    print("\n== F. ffmetadata <-> Vorbis: keys, values and pictures at the edges")
    meta = work / "f.ffmeta"
    meta.write_bytes(
        b";FFMETADATA1\n"
        b"a\\=b=v\n"  # a key holding '=' (escaped)
        b"t\xc3\xadtulo=v\n"  # a key outside Vorbis' 0x20-0x7D
        b"empty=\n"
        b"lyrics=one\\\ntwo\n"  # a value on two lines
        b"title-eng=English\n"  # ffmpeg's language suffix
        b'CUESHEET=FILE "a.flac" WAVE\\\n  TRACK 01 AUDIO\\\n    INDEX 01 00:00:00\\\n\n'
    )
    for ext, codec in (("flac", "flac"), ("opus", "libopus")):
        out = work / f"f.{ext}"
        run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=2", "-i", str(meta),
            "-map", "0", "-map_metadata", "1", "-c:a", codec, str(out))  # fmt: skip
        print(
            f"  ffmetadata -> .{ext}: {[c for c in vc.comments_of(out) if not c.startswith(b'encoder')]}"
        )
        maps = ["-map_metadata", "0:s:0"] if ext == "opus" else []
        back = run(
            FFMPEG, "-v", "error", "-i", str(out), *maps, "-f", "ffmetadata", "-"
        ).stdout.splitlines()
        edge = [line for line in back if line.startswith(("a", "t\u00ed", "empty"))]
        print(f"    read back: {edge}")
    png = work / "p.png"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=red:s=8x8",
        "-frames:v",
        "1",
        str(png),
    )
    base = work / "f-base.flac"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=d=2",
        "-c:a",
        "flac",
        str(base),
    )
    picture = b"METADATA_BLOCK_PICTURE=" + base64.b64encode(
        vc.picture_block(png.read_bytes())
    )
    comments = [b"EMPTY=", b"=noname", b"LYRICS=one\ntwo", b"CR=a\rb", b"title-eng=English",
                b"CUESHEET=FILE \"a.flac\" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n", picture]  # fmt: skip
    flac = work / "f-vorbis.flac"
    vc.with_comments(base, comments, flac)
    exported = run(
        FFMPEG, "-v", "error", "-i", str(flac), "-f", "ffmetadata", "-"
    ).stdout
    print(f"  Vorbis -> ffmetadata: {exported.splitlines()[1:]!r}")
    streams = json.loads(
        run(FFPROBE, "-v", "error", "-show_streams", "-of", "json", str(flac)).stdout
    )["streams"]
    print(
        f"  the picture, to ffmpeg: {[(s['codec_type'], s.get('disposition', {}).get('attached_pic')) for s in streams]}"
    )


def libcue_extras(work: Path) -> None:
    print("\n== G. libcue's CD-Text extras through cuetag.sh")
    cue = work / "g.cue"
    cue.write_text(
        'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    COMPOSER "Track Composer"\n'
        '    MESSAGE "A message"\n    GENRE "Rock"\n    PERFORMER "Track Artist"\n    INDEX 01 00:00:00\n'
    )
    target = work / "g.txt"
    run(
        "sh",
        CUETAG,
        str(cue),
        str(target),
        env={"PATH": f"{Path(CUETAG).parent}:/usr/bin:/bin"},
    )
    print(
        f"  track 1: {target.read_text().splitlines() if target.exists() else 'none'}"
    )


def to_cue(
    tags: dict[str, str], chapters: list[tuple[int, int, str, str]]
) -> tuple[str, list[str]]:
    """ffmetadata's or Vorbis' tags and chapters (start ms, end ms, title, performer) into a cue
    sheet, by ffman-mappings.md's rows and the cue skill's writing rules only; returns the sheet
    and its losses."""
    notes: list[str] = []

    def quoted(value: str, what: str) -> str | None:
        if '"' in value or "\n" in value or "\r" in value:
            notes.append(f"{what}: holds a quote or a line break, which cue cannot")
            return None
        if len(value) > 80:
            notes.append(f"{what}: over 80 characters")
        return f'"{value}"'

    head = []
    if (barcode := tags.get("barcode", "")).isdigit() and len(barcode) == 13:
        head.append(f"CATALOG {barcode}")
    if "genre" in tags and (genre := quoted(tags["genre"], "genre")):
        head.append(
            f"REM GENRE {genre if ' ' in tags['genre'] else tags['genre']}"
        )  # quoted for a space
    for key, cmd in (
        ("date", "DATE"),
        ("disc", "DISCNUMBER"),
    ):  # numbers: never quoted (Kodi)
        if key in tags:
            head.append(f"REM {cmd} {tags[key]}")
    for key in (
        "replaygain_album_gain",
        "replaygain_album_peak",
    ):  # gains: never quoted (Kodi)
        if key in tags:
            head.append(f"REM {key.upper()} {tags[key]}")
    for key, cmd in (("album", "TITLE"), ("album_artist", "PERFORMER")):
        if key in tags and (value := quoted(tags[key], key)):
            head.append(f"{cmd} {value}")
    known = {
        "barcode",
        "genre",
        "date",
        "disc",
        "replaygain_album_gain",
        "replaygain_album_peak",
        "album",
        "album_artist",
    }
    notes += [f"tag {key}: no cue field" for key in tags if key not in known]

    ordered = sorted(chapters)
    if len(ordered) > 99:
        notes.append(f"chapters past 99: {len(ordered) - 99} dropped")
        ordered = ordered[:99]
    if not ordered:
        notes.append("no chapter: one track at 0")
        ordered = [(0, 0, "", "")]
    for (_, end, *_), (start, *_) in pairwise(ordered):
        if end != start:
            notes.append(
                f"a chapter ending at {end} ms, the next at {start}: {'a gap' if end < start else 'an overlap'}, which cue cannot"
            )

    def at(ms: int) -> str:
        f = (ms * 75 + 500) // 1000
        return f"{f // 4500:02d}:{f // 75 % 60:02d}:{f % 75:02d}"

    body = ['FILE "album.flac" WAVE']
    for n, (start, _, title, performer) in enumerate(ordered, 1):
        body.append(f"  TRACK {n:02d} AUDIO")
        if title and (value := quoted(title, f"chapter {n} title")):
            body.append(f"    TITLE {value}")
        if performer and (value := quoted(performer, f"chapter {n} performer")):
            body.append(f"    PERFORMER {value}")
        if n == 1 and start > 0:
            body.append("    INDEX 00 00:00:00")
            notes.append("first chapter after 0: track 1's INDEX 00 at 0")
        body.append(f"    INDEX 01 {at(start)}")
        if start * 75 % 1000:
            notes.append(f"chapter {n} at {start} ms: to the nearest frame")
    return "\n".join(head + body) + "\n", notes


def into_cue(work: Path) -> None:
    """Directions 3 and 4: no tool writes a cue from either; the sheet is built from the rows and
    read back by libcue, metaflac (with ffmpeg's chapters of its block) and cuetag.sh."""
    print("\n== H. ffmetadata or Vorbis into cue: built by the rows, read back")
    flac = work / "h.flac"
    run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1500",
        "-sample_fmt", "s16", "-c:a", "flac", str(flac))  # fmt: skip
    tags = {"album": "The Album", "album_artist": "Band", "genre": "Alternative Rock", "date": "1991",
            "disc": "1", "replaygain_album_gain": "-7.03 dB", "barcode": "0123456789012",
            "composer": "Someone", "comment": "a note"}  # fmt: skip
    cases = {
        "plain": [
            (0, 257693, "One", "Band"),
            (257693, 542987, "Two", ""),
            (542987, 600000, "Three", "Guest"),
        ],
        "first after 0": [(30000, 60000, "One", ""), (60000, 90000, "Two", "")],
        "gap, overlap": [
            (0, 20000, "One", ""),
            (30000, 70000, "Two", ""),
            (60000, 90000, "Three", ""),
        ],
        "quote, line break, 100 characters": [
            (0, 1000, 'Say "hi"', ""),
            (1000, 2000, "a\nb", ""),
            (2000, 3000, "x" * 100, ""),
        ],
        "100 chapters": [(i * 10000, (i + 1) * 10000, f"C{i}", "") for i in range(100)],
    }
    for label, marks in cases.items():
        cue_text, notes = to_cue(tags, marks)
        cue = work / "h.cue"
        cue.write_text(cue_text)
        dumped = run(CUEDUMP, str(cue)).stdout.split("\n")
        starts = [
            line.split("start=")[1].split()[0] for line in dumped if " start=" in line
        ]
        titles = [
            line.split("TITLE=[")[1][:-1]
            for line in dumped
            if "track" in line and "TITLE=[" in line
        ]
        disc = [
            line.strip()
            for line in dumped
            if line.strip().startswith("disc ") and "tracks=" not in line
        ]
        m = work / "h-m.flac"
        m.write_bytes(flac.read_bytes())
        imported = run(METAFLAC, f"--import-cuesheet-from={cue}", str(m))
        block = (
            [round(float(c[0]) * 1000) for c in chapters(m)]
            if imported.returncode == 0
            else []
        )
        targets = [work / f"h{i}.txt" for i in range(1, min(len(marks), 3) + 1)]
        run(
            "sh",
            CUETAG,
            str(cue),
            *map(str, targets),
            env={"PATH": f"{Path(CUETAG).parent}:/usr/bin:/bin"},
        )
        tagged = targets[0].read_text().splitlines() if targets[0].exists() else []
        print(f"  {label}:")
        print(f"    notes: {notes}")
        print(f"    sheet: {[line.strip() for line in cue_text.splitlines()][:9]}")
        print(
            f"    libcue: disc {disc}; starts (frames) {starts[:4]}{'...' if len(starts) > 4 else ''} ({len(starts)}); titles {[t[:12] for t in titles[:4]]}"
        )
        print(
            f"    metaflac CD: exit {imported.returncode} {imported.stderr.strip()[-60:]!r}; ffmpeg chapters (ms) {block[:4]}{'...' if len(block) > 4 else ''} ({len(block)})"
        )
        print(f"    cuetag track 1: {tagged}")


def main() -> None:
    print(run(FFMPEG, "-version").stdout.splitlines()[0])
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        ffmetadata_to_vorbis(work)
        vorbis_to_ffmetadata(work)
        cue_to_vorbis(work)
        timebase_75(work)
        edges(work)
        libcue_extras(work)
        into_cue(work)
    arithmetic()


if __name__ == "__main__":
    main()

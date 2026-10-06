"""ffmetadata, measured: the format's edges through ffmpeg's own reader and writer, and every
generic key, two modifiers, a custom key and two chapters round-tripped through each container.

Usage: python3 measure.py [FFMPEG]  (default: ffmpeg on PATH; ffprobe beside it). Prints what
it found; references/format.md's tables are this output, at ffmpeg n8.1.2.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG = sys.argv[1] if len(sys.argv) > 1 else "ffmpeg"
FFPROBE = str(Path(FFMPEG).with_name("ffprobe")) if "/" in FFMPEG else "ffprobe"

# avformat.h's generic keys (n8.1.2), each a value naming itself; two modifiers; a custom key
GENERIC = (
    "album", "album_artist", "artist", "comment", "composer", "copyright", "creation_time",
    "date", "disc", "encoder", "encoded_by", "filename", "genre", "language", "performer",
    "publisher", "service_name", "service_provider", "title", "track", "variant_bitrate",
)  # fmt: skip
VALUES = {k: f"v-{k}" for k in GENERIC} | {
    "creation_time": "2026-10-03T12:00:00.000000Z",
    "date": "2026-10-03",
    "disc": "1/2",
    "track": "3/12",
    "language": "eng",
    "variant_bitrate": "128000",
    "title-eng": "v-title-eng",
    "artist-sort": "v-artist-sort",
    "x_custom": "v-x_custom",
}
CHAPTERS = (
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=One\n"
    "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\nEND=2000\ntitle=Two\n"
)

# the containers ffman's outputs reach, each with an audio encoder it holds -- given after the
# inputs: an option before an -i is that input's
CONTAINERS = {
    "mp4": "aac", "mov": "aac", "m4a": "aac", "mkv": "flac", "webm": "libopus", "ogg": "libvorbis",
    "opus": "libopus", "flac": "flac", "mp3": "libmp3lame", "wav": "pcm_s16le", "avi": "pcm_s16le",
    "ts": "mp2",
    "mp4+mdta": "aac",  # .mp4 with -movflags use_metadata_tags
}  # fmt: skip

EDGES = {  # an ffmetadata body each, after its header -- the format's edges
    "specials": "k\\=\\;\\#\\\\=a\\=b\\;c\\#d\\\\e",
    "newline": "k=line one\\\nline two",
    "backslash-n": "k=a\\nb",
    "cr": "k=a\rb",
    "case dup": "Title=first\ntitle=second",
    "spaces": "k = v ",
    "no equals": "just text\nk=v",
    "comment continued": "; a comment\\\nk=swallowed?\nj=after",
    "[chapter] lower": "[chapter]\nTIMEBASE=1/1000\nSTART=0\nEND=5\ntitle=t",
    "no START": "[CHAPTER]\nTIMEBASE=1/1000\nEND=5\ntitle=t",
    "no TIMEBASE": "[CHAPTER]\nSTART=0\nEND=1000000000\ntitle=t",
    "negative START": "[CHAPTER]\nTIMEBASE=1/1000\nSTART=-5\nEND=5",
    "empty value": "k=\nj=after",
    "empty key": "=v\nj=after",
    "no END": "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\ntitle=t",
    "NUL": "k=a\x00b\nj=after",
    "escaped \\ ending a line": "k=x\\\\\nnext=1\nj=after",
    "START=12abc": "[CHAPTER]\nTIMEBASE=1/1000\nSTART=12abc\nEND=5000",
    "TIMEBASE=1": "[CHAPTER]\nTIMEBASE=1\nSTART=5\nEND=5000",
}


def ff(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [FFMPEG, "-v", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def read_back(path: Path) -> tuple[dict[str, tuple[str, str]], list[tuple[str, str]]]:
    """A file's tags by key -- (value, where: format, program or stream) -- and its chapters'
    (start-end at their time base, title), as ffprobe reads them: every level, not only the
    global tags an ffmetadata export carries (Ogg's are its stream's, MPEG-TS's its program's)."""
    shown = subprocess.run(
        [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-show_programs",
         "-show_chapters", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    d = json.loads(shown.stdout)
    tags: dict[str, tuple[str, str]] = {}
    levels = [
        ("format", [d.get("format", {})]),
        ("program", d.get("programs", [])),
        ("stream", d.get("streams", [])),
    ]
    for where, items in levels:
        for item in items:
            for key, value in item.get("tags", {}).items():
                tags.setdefault(key, (value, where))
    chapters = [
        (
            f"{c['start']}-{c['end']} @{c['time_base']}",
            c.get("tags", {}).get("title", ""),
        )
        for c in d.get("chapters", [])
    ]
    return tags, chapters


def edges(work: Path) -> None:
    """Each edge: written, read by ffmpeg (probed, and forced), written back by ffmpeg."""
    print("== the format's edges: written -> ffmpeg read it -> ffmpeg wrote it")
    texts = {name: f";FFMETADATA1\n{body}\n" for name, body in EDGES.items()}
    texts |= {"version 2": ";FFMETADATA2\nk=v\n", "no header": "k=v\n"}
    texts |= {  # no final line break, and lines ended by CR alone
        "escaped \\, file end": ";FFMETADATA1\nk=x\\\\",
        "CR line ends": ";FFMETADATA1\rk=v\r[CHAPTER]\rTIMEBASE=1/1000\rSTART=0\rEND=5\rtitle=t\r",
        "comment ending file": ";FFMETADATA1\nk=v\n;x=y",
    }
    for name, text in texts.items():
        src, out = work / "edge.ffmeta", work / "edge-out.ffmeta"
        src.write_bytes(text.encode())
        done = ff("-f", "ffmetadata", "-i", str(src), "-f", "ffmetadata", str(out))
        probed = (
            ff("-i", str(src), "-f", "ffmetadata", str(work / "auto.ffmeta")).returncode
            == 0
        )
        got = (
            out.read_text(encoding="utf-8").split("\n", 1)[1]
            if done.returncode == 0
            else "(refused)"
        )
        note = f"  [{done.stderr.strip()[:70]}]" if done.stderr.strip() else ""
        print(f"  {name:18} {'probed' if probed else 'not probed':10} {got!r}{note}")


def containers(work: Path) -> None:
    """Every key and two chapters through each container: kept, renamed, or lost -- and where."""
    meta = work / "all.ffmeta"
    body = "".join(f"{k}={v}\n" for k, v in VALUES.items())
    meta.write_text(f";FFMETADATA1\n{body}{CHAPTERS}", encoding="utf-8")
    print(
        "\n== every key and two chapters through each container (read back by ffprobe)"
    )
    for ext, codec in CONTAINERS.items():
        out = work / f"c.{ext.split('+')[0]}"
        inputs = ["-f", "lavfi", "-i", "sine=d=2", "-i", str(meta)]
        maps = ["-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c:a", codec]
        maps += ["-movflags", "use_metadata_tags"] if ext.endswith("+mdta") else []
        made = ff(*inputs, *maps, str(out))
        if made.returncode:
            print(f"  .{ext}: not written: {made.stderr.strip()[:80]}")
            continue
        tags, chapters = read_back(out)
        by_value = {v: k for k, (v, _) in tags.items()}
        kept = [k for k, v in VALUES.items() if tags.get(k, ("", ""))[0] == v]
        renamed = [
            f"{k}>{by_value[v]}"
            for k, v in VALUES.items()
            if k not in kept and v in by_value
        ]
        lost = [k for k, v in VALUES.items() if k not in kept and v not in by_value]
        changed = [
            f"{k}={tags[k][0]!r}"
            for k in VALUES
            if k in tags and tags[k][0] != VALUES[k]
        ]
        where = sorted({w for k, (_, w) in tags.items() if k.lower() != "encoder"})
        print(
            f"  .{ext}: kept {len(kept)}/{len(VALUES)} (at {', '.join(where) or '-'}); chapters {chapters}"
        )
        for label, items in (
            ("renamed", renamed),
            ("lost", lost),
            ("changed", changed),
        ):
            if items:
                print(f"      {label + ':':8} {' '.join(items)}")


def streams_and_export(work: Path) -> None:
    """What the edges cannot show through an ffmetadata write: the reader's own values, stream
    sections applied, a media file's tags exported."""
    print("\n== the reader, stream sections, export")
    # an escaped carriage return, read and kept in a file (ffmpeg's writer would not escape it)
    src = work / "cr.ffmeta"
    src.write_bytes(b";FFMETADATA1\nk=a\\\rb\nj=after\n")
    ff("-f", "ffmetadata", "-i", str(src), "-f", "lavfi", "-i", "anullsrc=d=0.1", "-map", "1",
       "-map_metadata", "0", "-c:a", "pcm_s16le", str(work / "cr.mka"))  # fmt: skip
    print(
        f"  escaped CR, kept in a file: k={read_back(work / 'cr.mka')[0].get('K', ('?',))[0]!r}"
    )
    # a negative START, as the reader holds it: ffprobe on the file, no copy between
    src.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=-5\nEND=5\n", encoding="utf-8"
    )
    _, chapters = read_back(src)
    print(f"  START=-5, read (ffprobe, no copy): {chapters}")
    # a [STREAM] section: reaching an output stream with, and without, a stream mapping
    src.write_text(
        ";FFMETADATA1\ntitle=G\n[STREAM]\ntitle=S0\nlanguage=por\n", encoding="utf-8"
    )
    for label, extra in (
        ("-map_metadata 1", []),
        ("+ -map_metadata:s:a:0 1:s:0", ["-map_metadata:s:a:0", "1:s:0"]),
    ):
        out = work / "st.mka"
        ff("-f", "lavfi", "-i", "sine=d=1", "-i", str(src), "-map", "0", "-map_metadata", "1", *extra,
           "-c:a", "flac", str(out))  # fmt: skip
        shown = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "stream_tags=title", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True,
        )  # fmt: skip
        print(f"  [STREAM] {label:28}: stream title {shown.stdout.strip() or '-'}")
    # an Ogg file's tags, exported three ways
    ogg = work / "s.ogg"
    meta = work / "m.ffmeta"
    meta.write_text(";FFMETADATA1\ntitle=T\n", encoding="utf-8")
    ff(
        "-f",
        "lavfi",
        "-i",
        "sine=d=1",
        "-i",
        str(meta),
        "-map",
        "0",
        "-map_metadata",
        "1",
        "-c:a",
        "libvorbis",
        str(ogg),
    )
    for label, extra in (
        ("default", []),
        ("-map 0 -c copy", ["-map", "0", "-c", "copy"]),
        ("-map_metadata 0:s:0", ["-map_metadata", "0:s:0"]),
    ):
        out = work / "export.ffmeta"
        ff("-i", str(ogg), *extra, "-f", "ffmetadata", str(out))
        has = "title=T" in out.read_text(encoding="utf-8")
        sections = out.read_text(encoding="utf-8").count("[STREAM]")
        print(
            f"  an .ogg exported, {label:20}: title {'there' if has else 'absent'}, [STREAM] sections {sections}"
        )


def example(work: Path) -> None:
    """SKILL.md's example, read by ffmpeg: its text taken from the skill itself."""
    skill = (Path(__file__).parent.parent / "SKILL.md").read_text(encoding="utf-8")
    text = skill.split("A file with every feature, as ffmpeg reads it:\n\n```\n", 1)[
        1
    ].split("```", 1)[0]
    src = work / "example.ffmeta"
    src.write_text(text, encoding="utf-8")
    tags, chapters = read_back(src)
    print("\n== SKILL.md's example, as ffmpeg reads it")
    print(f"  tags: {dict((k, v) for k, (v, _) in tags.items())}")
    print(f"  chapters: {chapters}")


def main() -> None:
    version = subprocess.run(
        [FFMPEG, "-version"], capture_output=True, text=True, check=True
    )
    print(version.stdout.splitlines()[0])
    with tempfile.TemporaryDirectory() as tmp:
        edges(Path(tmp))
        containers(Path(tmp))
        streams_and_export(Path(tmp))
        example(Path(tmp))


if __name__ == "__main__":
    main()

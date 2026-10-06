"""Vorbis comments, measured: what ffmpeg writes and reads, and what metaflac and vorbiscomment
read and write as text -- each comment seen as bytes, by this script's own Ogg and FLAC readers.

Usage: python3 measure.py FFMPEG METAFLAC VORBISCOMMENT  (ffprobe beside ffmpeg). Prints what it
found; references/format.md's measured tables are this output (ffmpeg n8.1.2, metaflac 1.5.0,
vorbiscomment from vorbis-tools 1.4.3).
"""

import base64
import json
import shlex
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# The tools, from the command line (main); empty on import, so other scripts may use
# the readers below (ogg_packets ... with_comments), which need none.
FFMPEG = FFPROBE = METAFLAC = VORBISCOMMENT = ""


def run(*argv: str, stdin: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(argv), input=stdin, capture_output=True, check=False)


# -- the instruments: comments as bytes, without ffmpeg between -------------------------------


def ogg_packets(data: bytes, count: int) -> list[bytes]:
    """The first ``count`` packets of the first logical stream (RFC 3533's pages)."""
    packets, current, pos, serial = [], b"", 0, None
    while pos < len(data) and len(packets) < count:
        assert data[pos : pos + 4] == b"OggS", "an Ogg page"
        nsegs = data[pos + 26]
        lacing = data[pos + 27 : pos + 27 + nsegs]
        page_serial = struct.unpack_from("<I", data, pos + 14)[0]
        body = pos + 27 + nsegs
        serial = page_serial if serial is None else serial
        for size in lacing:
            if page_serial == serial:
                current += data[body : body + size]
                if size < 255:
                    packets.append(current)
                    current = b""
            body += size
        pos = body
    return packets[:count]


def comment_list(packet: bytes) -> tuple[str, list[bytes]]:
    """A comment header's vendor and its comments, raw: a Vorbis, Opus or FLAC one."""
    for magic in (b"\x03vorbis", b"OpusTags"):
        if packet.startswith(magic):
            packet = packet[len(magic) :]
            break
    (vlen,) = struct.unpack_from("<I", packet, 0)
    vendor = packet[4 : 4 + vlen].decode("utf-8", "replace")
    pos = 4 + vlen
    (n,) = struct.unpack_from("<I", packet, pos)
    pos += 4
    comments = []
    for _ in range(n):
        (size,) = struct.unpack_from("<I", packet, pos)
        comments.append(packet[pos + 4 : pos + 4 + size])
        pos += 4 + size
    return vendor, comments


def flac_blocks(data: bytes) -> list[tuple[int, bytes]]:
    assert data[:4] == b"fLaC", "a FLAC file"
    blocks, pos = [], 4
    while True:
        head = data[pos]
        size = int.from_bytes(data[pos + 1 : pos + 4], "big")
        blocks.append((head & 0x7F, data[pos + 4 : pos + 4 + size]))
        pos += 4 + size
        if head & 0x80:
            return blocks + [(-1, data[pos:])]  # -1: the audio frames, kept as they are


def comments_of(path: Path) -> list[bytes]:
    data = path.read_bytes()
    if data[:4] == b"fLaC":
        block = next(b for t, b in flac_blocks(data) if t == 4)
        return comment_list(block)[1]
    return comment_list(ogg_packets(data, 2)[1])[1]


def with_comments(flac: Path, comments: list[bytes], out: Path) -> None:
    """A copy of ``flac``, its Vorbis comment block holding ``comments`` exactly."""
    vendor = b"measure.py"
    body = struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments))
    body += b"".join(struct.pack("<I", len(c)) + c for c in comments)
    blocks = [(t, b) for t, b in flac_blocks(flac.read_bytes()) if t not in (1, 4)]
    audio = blocks.pop()[1]
    blocks.insert(1, (4, body))
    raw = b"fLaC"
    for i, (t, b) in enumerate(blocks):
        raw += (
            bytes([t | (0x80 if i == len(blocks) - 1 else 0)])
            + len(b).to_bytes(3, "big")
            + b
        )
    out.write_bytes(raw + audio)


def probe(path: Path) -> dict:
    shown = run(
        FFPROBE,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-of",
        "json",
        str(path),
    )
    return json.loads(shown.stdout or b"{}")


def picture_block(png: bytes) -> bytes:
    """A FLAC picture block (RFC 9639, 8.8): a front cover, image/png."""
    mime, desc = b"image/png", b"cover"
    return (
        struct.pack(">II", 3, len(mime)) + mime + struct.pack(">I", len(desc)) + desc
        + struct.pack(">IIIII", 1, 1, 24, 0, len(png)) + png
    )  # fmt: skip


# -- A: ffmpeg's writer ----------------------------------------------------------------------------


def ffmpeg_writer(work: Path) -> None:
    print(
        "== A. ffmpeg's writer: what it puts in the comment header (bytes, read here)"
    )
    starts = [0, 500, 1600, 59500, 3599600]  # ms
    meta = ";FFMETADATA1\ntitle=T\n" + "".join(
        f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={s}\nEND={s + 1}\ntitle=at {s} ms\n"
        for s in starts
    )
    (work / "ch.ffmeta").write_text(meta, encoding="utf-8")
    out = work / "ch.opus"
    run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", "-i", str(work / "ch.ffmeta"),
        "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c:a", "libopus", str(out))  # fmt: skip
    written = [c.decode() for c in comments_of(out) if c.upper().startswith(b"CHAPTER")]
    print(f"  chapters at {starts} ms, as written: {written}")
    print(
        f"  as ffmpeg reads them back (ms): {[int(c['start']) for c in probe(out).get('chapters', [])]}"
    )
    keys = ";FFMETADATA1\nlower=a\nUPPER=b\nwith space=c\ntilde~=d\nk\\=eq=e\n"
    (work / "keys.ffmeta").write_text(keys, encoding="utf-8")
    out = work / "keys.flac"
    run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", "-i", str(work / "keys.ffmeta"),
        "-map", "0", "-map_metadata", "1", str(out))  # fmt: skip
    print(f"  keys as written (FLAC): {[c.decode() for c in comments_of(out)]}")


# -- B: ffmpeg's reader ----------------------------------------------------------------------------


def ffmpeg_reader(work: Path, flac: Path) -> None:
    print("\n== B. ffmpeg's reader: crafted comments (FLAC), as ffprobe shows them")
    png = run(FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=red:s=1x1", "-frames:v", "1",
              "-f", "image2pipe", "-c:v", "png", "-").stdout  # fmt: skip
    pic = base64.b64encode(picture_block(png))
    cases = {
        "repeated": [b"ARTIST=A", b"ARTIST=B"],
        "repeated, case": [b"ARTIST=A", b"artist=B"],
        "a ';' in a value": [b"ARTIST=A;B"],
        "empty value": [b"EMPTY=", b"KEPT=x"],
        "empty name": [b"=v", b"KEPT=x"],
        "no '='": [b"justtext", b"KEPT=x"],
        "tilde name": [b"A~B=x"],
        "case kept": [b"Title=x", b"genre=y"],
        "two lines": [b"LYRICS=one\ntwo"],
        "renamed": [
            b"ALBUMARTIST=a",
            b"TRACKNUMBER=1",
            b"DISCNUMBER=2",
            b"DESCRIPTION=d",
        ],
        "chapter 1.5": [b"CHAPTER000=00:00:01.5", b"CHAPTER000NAME=x"],
        "chapter no ms": [b"CHAPTER000=00:05:00", b"CHAPTER000NAME=x"],
        "chapter h:m:s.ms": [b"CHAPTER000=1:02:03.004"],
        "chapter 100 h": [b"CHAPTER000=100:00:00.000"],
        "chapter 2 digits": [b"CHAPTER01=00:00:01.000"],
        "chapter 1 digit": [b"CHAPTER1=00:00:01.000"],
        "chapter lowercase": [b"chapter002=00:00:02.000", b"chapter002name=low"],
        "NAME before time": [b"CHAPTER003NAME=early", b"CHAPTER003=00:00:03.000"],
        "URL": [b"CHAPTER004=00:00:04.000", b"CHAPTER004URL=http://x"],
        "picture": [b"METADATA_BLOCK_PICTURE=" + pic],
        "bad picture": [b"METADATA_BLOCK_PICTURE=AAAA", b"KEPT=x"],
    }
    for label, comments in cases.items():
        out = work / "case.flac"
        with_comments(flac, comments, out)
        d = probe(out)
        tags = {
            k: v
            for k, v in d.get("format", {}).get("tags", {}).items()
            if k.lower() != "encoder"
        }
        chapters = [
            (int(c["start"]), c.get("tags", {}).get("title", ""))
            for c in d.get("chapters", [])
        ]
        covers = [
            s["codec_name"]
            for s in d.get("streams", [])
            if s.get("disposition", {}).get("attached_pic")
        ]
        print(
            f"  {label:18} tags {tags}"
            + (f" chapters(ms) {chapters}" if chapters else "")
            + (f" covers {covers}" if covers else "")
        )


# -- C: metaflac -----------------------------------------------------------------------------------


def metaflac(work: Path, flac: Path) -> None:
    print("\n== C. metaflac's tag files")
    f = work / "m.flac"

    def fresh() -> None:
        f.write_bytes(flac.read_bytes())
        run(METAFLAC, "--remove-all-tags", str(f))

    imports = {
        "last line, no newline": b"A=1\nB=2",
        "CRLF": b"A=1\r\nB=2\r\n",
        "empty name": b"=v\n",
        "tilde name": b"A~B=x\n",
        "lowercase": b"title=x\n",
        "invalid UTF-8 (raw)": b"A=\xff\xfe\n",
        "line > 65535": b"A=" + b"x" * 70000 + b"\n",
        "comment-like line": b"# not a tag\nA=1\n",
        "empty line": b"A=1\n\nB=2\n",
    }
    for label, text in imports.items():
        fresh()
        src = work / "tags.txt"
        src.write_bytes(text)
        done = run(METAFLAC, "--no-utf8-convert", f"--import-tags-from={src}", str(f))
        got = [c[:40] for c in comments_of(f)]
        err = done.stderr.decode(errors="replace").strip().splitlines()
        print(
            f"  import {label:22} exit {done.returncode}: {got}"
            + (f"  [{err[-1][:70]}]" if err else "")
        )
    fresh()
    with_comments(flac, [b"A=1", b"LYRICS=one\ntwo", b"B=\\n"], f)
    exported = run(METAFLAC, "--no-utf8-convert", "--export-tags-to=-", str(f)).stdout
    print(f"  export of [A=1, LYRICS=one<LF>two, B=\\n]: {exported!r}")


# -- D: vorbiscomment, and one file read by both ---------------------------------------------------


def vorbiscomment(work: Path) -> None:
    print("\n== D. vorbiscomment's comment files (Ogg Vorbis)")
    ogg = work / "v.ogg"
    run(
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=d=1",
        "-c:a",
        "libvorbis",
        str(ogg),
    )
    out = work / "w.ogg"
    writes = {
        "-e: \\n \\r \\\\ \\0": (
            ["-e"],
            b"A=one\\ntwo\nB=cr\\rx\nC=back\\\\slash\nD=nul\\0after\n",
        ),
        "-e: unknown \\t": (["-e"], b"A=1\nB=tab\\tx\nC=3\n"),
        "-e: trailing \\": (["-e"], b"A=1\nB=end\\\nC=3\n"),
        "no -e: backslashes": ([], b"A=one\\ntwo\n"),
        "bad line skipped": ([], b"A=1\nno equals\nC=3\n"),
        "CRLF": ([], b"A=1\r\nB=2\r\n"),
        "tilde name": ([], b"A~B=x\nC=3\n"),
        "last line, no newline": ([], b"A=1\nB=2"),
        "lowercase": ([], b"title=x\n"),
        "empty and # lines": ([], b"A=1\n\n# c\nB=2\n"),
        "invalid UTF-8, -R": ([], b"A=\xff\nB=2\n"),
    }
    for label, (flags, text) in writes.items():
        src = work / "c.txt"
        src.write_bytes(text)
        done = run(
            VORBISCOMMENT, "-w", "-R", *flags, "-c", str(src), str(ogg), str(out)
        )
        got = comments_of(out) if done.returncode == 0 else []
        err = done.stderr.decode(errors="replace").strip().splitlines()
        print(
            f"  -w {label:22} exit {done.returncode}: {got}"
            + (f"  [{err[0][:60]}]" if err else "")
        )
    with_text = [b"A=1", b"LYRICS=one\ntwo", b"B=cr\rx"]
    flac_like = work / "l.ogg"
    src = work / "l.txt"
    src.write_bytes(b"A=1\nLYRICS=one\\ntwo\nB=cr\\rx\n")
    run(VORBISCOMMENT, "-w", "-R", "-e", "-c", str(src), str(ogg), str(flac_like))
    for flags in ([], ["-e"]):
        listed = run(VORBISCOMMENT, "-l", "-R", *flags, str(flac_like)).stdout
        print(
            f"  -l {' '.join(flags) or '(no -e)':4} of {[c.decode() for c in with_text]}: {listed!r}"
        )


def both(work: Path, flac: Path) -> None:
    print("\n== One text file, both tools (single-line values)")
    text = b"TITLE=Song\nARTIST=A\nARTIST=B\nComment=x=y\n"
    src = work / "both.txt"
    src.write_bytes(text)
    f = work / "b.flac"
    f.write_bytes(flac.read_bytes())
    run(
        METAFLAC,
        "--remove-all-tags",
        "--no-utf8-convert",
        f"--import-tags-from={src}",
        str(f),
    )
    ogg, out = work / "v.ogg", work / "b.ogg"
    run(VORBISCOMMENT, "-w", "-R", "-c", str(src), str(ogg), str(out))
    print(f"  metaflac      wrote {comments_of(f)}")
    print(f"  vorbiscomment wrote {comments_of(out)}")


def vendors_and_scope(work: Path, flac: Path) -> None:
    """The vendor string ffmpeg writes and reads; what each tool edits; a cue sheet as a comment."""
    print("\n== E. Vendor strings, the tools' scope, a CUESHEET comment")
    for label, extra in (
        ("default", []),
        ("-fflags +bitexact", ["-fflags", "+bitexact"]),
    ):
        for ext, codec in (("ogg", "libvorbis"), ("opus", "libopus"), ("flac", "flac")):
            out = work / f"vendor.{ext}"
            run(
                FFMPEG,
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=d=1",
                *extra,
                "-c:a",
                codec,
                str(out),
            )
            data = out.read_bytes()
            packet = (
                next(b for t, b in flac_blocks(data) if t == 4)
                if ext == "flac"
                else ogg_packets(data, 2)[1]
            )
            vendor, _ = comment_list(packet)
            print(f"  {label:18} .{ext:4} vendor {vendor!r}")
    unique = (
        work / "vendor-unique.flac"
    )  # with_comments' vendor, "measure.py": nowhere else
    with_comments(flac, [b"TITLE=t"], unique)
    shown = run(
        FFPROBE,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(unique),
    ).stdout
    print(
        f"  a vendor of its own ('measure.py') anywhere in ffprobe's output: {b'measure.py' in shown}"
    )
    opus, oga = work / "vendor.opus", work / "f.oga"
    run(FFMPEG, "-v", "error", "-y", "-i", str(flac), "-c:a", "flac", str(oga))
    listed = run(VORBISCOMMENT, "-l", str(opus))
    print(
        f"  vorbiscomment -l on .opus: exit {listed.returncode} {listed.stderr.decode(errors='replace').strip()[:70]!r}"
    )
    shown = run(METAFLAC, "--export-tags-to=-", str(oga))
    print(
        f"  metaflac on FLAC-in-Ogg (.oga): exit {shown.returncode} {shown.stderr.decode(errors='replace').strip()[:70]!r}"
    )
    cue = b'CUESHEET=FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
    out = work / "cue.flac"
    with_comments(flac, [cue], out)
    d = probe(out)
    print(
        f"  a CUESHEET comment, read: tags {d.get('format', {}).get('tags', {})} chapters {len(d.get('chapters', []))}"
    )


def parse_text(text: bytes) -> list[bytes]:
    """SKILL.md's text form, read by its grammar: the comments, unescaped; a bad line raises."""
    assert text.endswith(b"\n"), "every line ends with LF"
    comments = []
    for number, line in enumerate(text[:-1].split(b"\n"), 1):
        name, eq, value = line.partition(b"=")
        assert eq and name and all(0x20 <= c <= 0x7D and c != 0x3D for c in name), (
            f"line {number}: name"
        )
        out, i = bytearray(), 0
        while i < len(value):
            if value[i] == 0x5C:
                pair = value[i : i + 2]
                assert pair in (b"\\\\", b"\\n", b"\\r"), (
                    f"line {number}: escape {pair!r}"
                )
                out += {b"\\\\": b"\\", b"\\n": b"\n", b"\\r": b"\r"}[bytes(pair)]
                i += 2
            else:
                assert value[i] not in (0x00, 0x0A, 0x0D), f"line {number}: control"
                out.append(value[i])
                i += 1
        comments.append(name + b"=" + bytes(out))
    return comments


def skill(work: Path, flac: Path) -> None:
    """SKILL.md's claims, from its own text: the example file, and the chapter commands."""
    print("\n== F. SKILL.md, checked against itself")
    text = (Path(__file__).parent.parent / "SKILL.md").read_text(encoding="utf-8")

    def block(after: str) -> str:
        return text.split(after, 1)[1].split("```", 1)[0]

    def argv_of(after: str) -> list[str]:
        # as a shell reads it: a backslash-newline joins the lines first (shlex does not)
        return shlex.split(block(after + "\n\n```sh\n").replace("\\\n", ""))

    def chapters_of(path: Path) -> list[tuple[int, str | None]]:
        return [
            (int(c["start"]), c.get("tags", {}).get("title"))
            for c in probe(path).get("chapters", [])
        ]

    example = block("A file in ffman's form:\n\n```\n").encode()
    comments = parse_text(example)
    out = work / "example.flac"
    with_comments(flac, comments, out)
    tags = probe(out).get("format", {}).get("tags", {})
    print(f"  the example: {len(comments)} comments; ffmpeg reads tags {tags}")
    print(f"  ... and chapters (ms) {chapters_of(out)}")
    src, ogg, out = work / "ex.txt", work / "v.ogg", work / "ex.ogg"
    src.write_bytes(example)
    done = run(VORBISCOMMENT, "-w", "-R", "-e", "-c", str(src), str(ogg), str(out))
    same = done.returncode == 0 and comments_of(out) == comments
    print(
        f"  vorbiscomment -w -e, the example: exit {done.returncode}, comments equal to the grammar's: {same}"
    )
    argv = argv_of(
        "Chapters into FLAC, in order (`metaflac` appends each `--set-tag` as given):"
    )
    song = work / "song.flac"
    song.write_bytes(flac.read_bytes())
    done = run(METAFLAC, *argv[1:-1], str(song))
    order = [c.decode().split("=")[0] for c in comments_of(song)]
    print(
        f"  the metaflac command: exit {done.returncode}, written {order}, chapters (ms) {chapters_of(song)}"
    )
    argv = argv_of("Into Ogg, through ffmpeg -- then check the order it wrote:")
    meta = argv[argv.index("-c") : argv.index("out.ogg")]
    for ext, codec in (("ogg", "libvorbis"), ("opus", "libopus"), ("flac", "flac")):
        src = work / f"in.{ext}"
        run(
            FFMPEG,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=d=1",
            "-c:a",
            codec,
            str(src),
        )
        out = work / f"out.{ext}"
        made = run(FFMPEG, "-v", "error", "-y", "-i", str(src), *meta, str(out))
        order = [c.decode().split("=")[0] for c in comments_of(out)]
        print(
            f"  the ffmpeg command into .{ext:4}: exit {made.returncode}, written {order}, chapters (ms) {chapters_of(out)}"
        )


def main() -> None:
    global FFMPEG, FFPROBE, METAFLAC, VORBISCOMMENT
    FFMPEG, METAFLAC, VORBISCOMMENT = sys.argv[1:4]
    FFPROBE = str(Path(FFMPEG).with_name("ffprobe"))
    for tool in (FFMPEG, METAFLAC, VORBISCOMMENT):
        first = (
            run(tool, "-version").stdout
            or run(tool, "--version").stdout
            or run(tool, "-V").stdout
            or run(tool, "-V").stderr
        )
        print(first.decode(errors="replace").splitlines()[0])
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        flac = work / "base.flac"
        run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=6:sample_rate=44100", "-ac", "2",
            "-sample_fmt", "s16", str(flac))  # fmt: skip
        ffmpeg_writer(work)
        ffmpeg_reader(work, flac)
        metaflac(work, flac)
        vorbiscomment(work)
        both(work, flac)
        vendors_and_scope(work, flac)
        skill(work, flac)


if __name__ == "__main__":
    main()

"""Cue sheets, measured: each case read by libcue (cuedump.c), imported by metaflac into a CD-DA
(44.1 kHz, 16-bit, stereo) and a 48 kHz FLAC -- its export showing what the CUESHEET block kept
-- and that block read back by ffmpeg as chapters.

Usage: python3 measure.py FFMPEG METAFLAC CUEDUMP  (ffprobe beside ffmpeg). Prints what it found;
references/format.md's measured tables are this output (libcue 2.3.0, metaflac 1.5.0, ffmpeg
n8.1.2). mpv reads cue sheets too; it is not run here (references/format.md: its source).
"""

import json
import shlex
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

FFMPEG, METAFLAC, CUEDUMP = sys.argv[1:4]
FFPROBE = str(Path(FFMPEG).with_name("ffprobe"))

EAC = (
    'REM GENRE Ska\nREM DATE 1991\nREM DISCID D00DA810\nREM COMMENT "ExactAudioCopy v0.95b4"\n'
    "CATALOG 0123456789012\n"
    'PERFORMER "The Specials"\nTITLE "Singles"\nSONGWRITER "Dammers"\n'
    'FILE "a.flac" WAVE\n'
    '  TRACK 01 AUDIO\n    TITLE "Gangsters"\n    PERFORMER "The Specials"\n'
    "    ISRC GBAYE7900001\n    FLAGS DCP PRE\n    INDEX 01 00:00:00\n"
    '  TRACK 02 AUDIO\n    TITLE "Rudi"\n    INDEX 00 02:47:74\n    INDEX 01 02:48:27\n'
    "    INDEX 02 03:00:00\n"
    '  TRACK 03 AUDIO\n    TITLE "Nite Klub"\n    INDEX 01 04:00:00\n    POSTGAP 00:02:00\n'
)
ONE = 'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "{t}"\n    INDEX 01 00:00:00\n'
TWO = (
    'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n'
    '  TRACK 02 AUDIO\n    TITLE "Two"\n    INDEX 01 {i}\n'
)

CASES: dict[str, bytes] = {
    "EAC single file": EAC.encode(),
    "HTOA": (
        'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:30:00\n'
        "  TRACK 02 AUDIO\n    INDEX 01 01:00:00\n"
    ).encode(),
    "multi-file, gaps prepended": (
        'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
        'FILE "2.wav" WAVE\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n    INDEX 01 00:00:28\n'
    ).encode(),
    "multi-file, PREGAP": (
        'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
        'FILE "2.wav" WAVE\n  TRACK 02 AUDIO\n    PREGAP 00:00:28\n    INDEX 01 00:00:00\n'
    ).encode(),
    "multi-file, noncompliant": (
        'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
        '  TRACK 02 AUDIO\n    INDEX 00 02:47:74\nFILE "2.wav" WAVE\n    INDEX 01 00:00:00\n'
    ).encode(),
    "lowercase commands": b'file "a.flac" wave\n  track 01 audio\n    title "x"\n    index 01 00:00:00\n',
    "CRLF": ONE.format(t="x").replace("\n", "\r\n").encode(),
    "UTF-8 BOM": b"\xef\xbb\xbf" + ONE.format(t="x").encode(),
    "tabs": ONE.format(t="x").replace("  ", "\t").encode(),
    "UTF-8 BOM before CATALOG": b"\xef\xbb\xbf"
    + ("CATALOG 0123456789012\n" + ONE.format(t="x")).encode(),
    "UTF-8 title": ONE.format(t="Ação é ñ").encode(),
    "Latin-1 title": ONE.format(t="Ação").encode("latin-1"),
    "unquoted, quotes inside": b'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE Theme Of "Rome"\n    INDEX 01 00:00:00\n',
    "unquoted, one word": ONE.format(t="x")
    .replace('TITLE "x"', "TITLE S.O.S.")
    .encode(),
    "unknown command BOGUS": ONE.format(t="x")
    .replace("    INDEX", "    BOGUS 1\n    INDEX")
    .encode(),
    "escaped quote": b'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "A \\"B\\" C"\n    INDEX 01 00:00:00\n',
    "single quotes": b"FILE \"a.flac\" WAVE\n  TRACK 01 AUDIO\n    TITLE 'One Two'\n    INDEX 01 00:00:00\n",
    "title 100 chars": ONE.format(t="x" * 100).encode(),
    "title 1100 chars": ONE.format(t="y" * 1100).encode(),
    "seconds 60": TWO.format(i="00:60:00").encode(),
    "frames 75": TWO.format(i="00:01:75").encode(),
    "minutes 100": TWO.format(i="100:00:00").encode(),
    "index as samples": TWO.format(i="132300").encode(),
    "index 01 then 03": (
        'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n    INDEX 03 00:10:00\n'
    ).encode(),
    "tracks 01 then 03": TWO.replace("TRACK 02", "TRACK 03")
    .format(i="00:10:00")
    .encode(),
    "track 100": TWO.replace("TRACK 02", "TRACK 100").format(i="00:10:00").encode(),
    "FILE type FLAC": ONE.format(t="x").replace("WAVE", "FLAC").encode(),
    "COMPOSER (libcue's)": b'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    COMPOSER "c"\n    INDEX 01 00:00:00\n',
    "REM alone": b'REM\nFILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n',
    "CDTEXTFILE": b'CDTEXTFILE "disc.cdt"\nFILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n',
    "a value ending in \\": b'SONGWRITER "x\\"\nFILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n',
    "FILE after INDEX 01": (
        b'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\nFILE "2.wav" WAVE\n    INDEX 02 00:00:00\n'
    ),
    "noncompliant, 3 tracks": (
        b'FILE "1.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    INDEX 00 02:47:74\n'
        b'FILE "2.wav" WAVE\n    INDEX 01 00:00:00\n  TRACK 03 AUDIO\n    INDEX 01 03:00:00\n'
    ),
    "no INDEX 01": b'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 00 00:00:00\n',
    "first index 00:02:00": b'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:02:00\n',
    "no final newline": ONE.format(t="x").rstrip("\n").encode(),
    "REM values quoted": (
        'REM GENRE "Alternative Rock"\nREM DATE "1991"\nREM COMMENT "ExactAudioCopy v0.95b4"\n'
        + ONE.format(t="x")
    ).encode(),
    "REPLAYGAIN REMs": (
        "REM REPLAYGAIN_ALBUM_GAIN -7.03 dB\nREM REPLAYGAIN_ALBUM_PEAK 1.0\n"
        'FILE "a.flac" WAVE\n  TRACK 01 AUDIO\n    REM REPLAYGAIN_TRACK_GAIN -6.00 dB\n'
        "    INDEX 01 00:00:00\n"
    ).encode(),
}


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv), capture_output=True, text=True, errors="replace", check=False
    )


def libcue(cue: Path) -> str:
    done = run(CUEDUMP, str(cue))
    lines = [line.strip() for line in done.stdout.splitlines()]
    err = " ".join(done.stderr.split())
    return " | ".join(lines) + (f"  [stderr: {err[:90]}]" if err else "")


def metaflac(cue: Path, base: Path, work: Path) -> str:
    flac = work / "m.flac"
    flac.write_bytes(base.read_bytes())
    done = run(METAFLAC, f"--import-cuesheet-from={cue}", str(flac))
    if done.returncode:
        return f"refused: {' '.join(done.stderr.split())[-90:]}"
    exported = run(METAFLAC, "--export-cuesheet-to=-", str(flac)).stdout
    shown = json.loads(
        run(FFPROBE, "-v", "error", "-show_chapters", "-of", "json", str(flac)).stdout
        or "{}"
    )
    chapters = [
        (
            round(float(c["start_time"]) * 1000),
            round(float(c["end_time"]) * 1000),
            c.get("tags", {}).get("title", ""),
        )
        for c in shown.get("chapters", [])
    ]
    kept = " ; ".join(line.strip() for line in exported.splitlines() if line.strip())
    return f"kept: {kept} || ffmpeg chapters (start ms, end ms, title) {chapters}"


def carried(base: Path, work: Path) -> None:
    """Whether a FLAC's CUESHEET block survives ffmpeg -- copied, and encoded again."""
    cue, flac = work / "carry.cue", work / "carry.flac"
    cue.write_bytes(TWO.format(i="00:10:00").encode())
    flac.write_bytes(base.read_bytes())
    run(METAFLAC, f"--import-cuesheet-from={cue}", str(flac))
    print("\n== The CUESHEET block through ffmpeg")
    for label, codec in (("-c copy", ["-c", "copy"]), ("-c:a flac", ["-c:a", "flac"])):
        out = work / "carried.flac"
        run(FFMPEG, "-v", "error", "-y", "-i", str(flac), *codec, str(out))
        kept = run(METAFLAC, "--export-cuesheet-to=-", str(out))
        shown = json.loads(
            run(
                FFPROBE, "-v", "error", "-show_chapters", "-of", "json", str(out)
            ).stdout
            or "{}"
        )
        print(
            f"  {label:10} block kept: {kept.returncode == 0 and 'TRACK' in kept.stdout}; chapters {len(shown.get('chapters', []))}"
        )


def skill(base: Path, work: Path) -> None:
    """SKILL.md's claims, from its own text: the example, the commands, the time rule."""
    print("\n== SKILL.md, checked against itself")
    text = (Path(__file__).parent.parent / "SKILL.md").read_text(encoding="utf-8")
    example = text.split("An album, one file:\n\n```\n", 1)[1].split("```", 1)[0]
    album_cue, album = work / "album.cue", work / "album.flac"
    album_cue.write_bytes(example.encode())
    base = work / "ten-minutes.flac"  # long enough for the example's last track
    run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=600",
        "-sample_fmt", "s16", "-c:a", "flac", str(base))  # fmt: skip
    album.write_bytes(base.read_bytes())
    print(f"  libcue: {libcue(album_cue)}")
    print(f"  metaflac CD: {metaflac(album_cue, base, work)}")
    commands = text.split("The tools:\n\n```sh\n", 1)[1].split("```", 1)[0]
    for line in commands.splitlines():
        argv = shlex.split(line.split("  #", 1)[0])
        argv = (
            [METAFLAC]
            + [a.replace("album.cue", str(album_cue)) for a in argv[1:-1]]
            + [str(album)]
        )
        done = run(*argv)
        print(
            f"  `{line.split('  #')[0].strip()}`: exit {done.returncode}; {' '.join(done.stdout.split())[:120]}"
        )
    tags = json.loads(
        run(FFPROBE, "-v", "error", "-show_format", "-of", "json", str(album)).stdout
    )
    tag = tags.get("format", {}).get("tags", {}).get("CUESHEET")
    print(f"  the CUESHEET tag: equal to the example: {tag == example}")
    worst, back = Fraction(0), True
    for ms in range(0, 3_600_001):
        frames = (ms * 75 + 500) // 1000
        worst = max(worst, abs(Fraction(frames * 1000, 75) - ms))
        back = back and (Fraction(frames * 1000, 75) * 75 / 1000 == frames)
    print(
        f"  the time rule over every millisecond to an hour: worst error {float(worst):.4f} ms; frames back exactly: {back}"
    )


def main() -> None:
    for tool, flag in ((FFMPEG, "-version"), (METAFLAC, "--version")):
        print(run(tool, flag).stdout.splitlines()[0])
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        bases = {}
        for name, rate in (("cd", "44100"), ("48k", "48000")):
            bases[name] = work / f"{name}.flac"
            run(FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=stereo:d=360",
                "-sample_fmt", "s16", "-c:a", "flac", str(bases[name]))  # fmt: skip
        cue = work / "case.cue"
        cue.write_bytes(EAC.encode())
        direct = run(FFMPEG, "-v", "error", "-i", str(cue), "-f", "null", "-")
        print(
            f"ffmpeg -i a .cue: exit {direct.returncode} {' '.join(direct.stderr.split())[:80]!r}"
        )
        carried(bases["cd"], work)
        skill(bases["cd"], work)
        cue.write_bytes(
            TWO.format(i="08:00:00").encode()
        )  # past the 360 s stream's end
        print("\n== An index past the stream's end (the 360 s CD-DA file)")
        print(f"  metaflac CD:   {metaflac(cue, bases['cd'], work)}")
        for label, text in CASES.items():
            cue.write_bytes(text)
            print(f"\n== {label}")
            print(f"  libcue:        {libcue(cue)}")
            print(f"  metaflac CD:   {metaflac(cue, bases['cd'], work)}")
            print(f"  metaflac 48k:  {metaflac(cue, bases['48k'], work)}")


if __name__ == "__main__":
    main()
